#!/usr/bin/env python3
"""
test_layer0_ledger_complete.py — regression guard for the Layer 0 ledger.json
truncation bug (found 2026-07-21).

WHAT BROKE
`run_layer0` only persisted `ledger.json` at an in-loop checkpoint that runs
AFTER a fresh decompose. Cache-hit documents `continue` before that write. So on a
mostly-cached run, the last checkpoint reflected only the rows accumulated up to the
final *fresh* document; every cache-hit doc processed afterwards grew `all_rows` in
memory but was never persisted. `ledger.md` and `REPORT.md` were written post-loop
from the complete in-memory list, so they disagreed with the truncated `ledger.json`
(observed live: REPORT said 1126 elements, ledger.json held 43). The fix is a single
authoritative `ledger.json` write after the loop.

WHY THIS TEST IS FAST
The only slow, non-deterministic dependency is the model. We fake it at the
`_decompose_text_with_retry` seam (exactly as test_layer1_organize_batch.py fakes
`call_and_parse_with_retry`), so the REAL Layer 0 flow — scrub, content-hash cache
detection, checkpointing, and the final ledger write — runs in milliseconds with no
GPU, network, or private data. `layer0.project_dir` is patched to a temp directory so
the test never writes into the repo.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import layer0  # noqa: E402
from layer0 import number_paragraphs  # noqa: E402
from schema_validate import ELEMENT_TYPES  # noqa: E402

FIXTURE_SOURCES = BASE / "projects" / "_fixtures" / "ledger-mini" / "sources"

# A valid element_type so validate_layer0_elements() is happy and we don't trip the
# schema-error escalation path into a (also-faked) second pass.
_TYPES = list(ELEMENT_TYPES)
ETYPE = "lesson_content" if "lesson_content" in _TYPES else _TYPES[0]

# Known paragraph counts of the fixture docs (blank-line separated). One element per
# paragraph under the fake model, so the full corpus yields 4 + 3 + 2 = 9 elements.
EXPECTED_ELEMENTS_PER_DOC = {"aaaa01": 4, "aaaa02": 3, "aaaa03": 2}
EXPECTED_TOTAL = sum(EXPECTED_ELEMENTS_PER_DOC.values())


def _fake_decompose(
    cfg,
    role,
    rules,
    schema,
    priors_block,
    text,
    char_label,
    step,
    chunk_note="",
    timeout_seconds=None,
):
    """Deterministic stand-in for the model: emit exactly one confidently-cited
    element per paragraph. Returns (data, paragraphs) like the real function, using
    the real paragraph splitter so citations resolve through build_ledger_rows."""
    _, paragraphs = number_paragraphs(text)
    elements = [
        {
            "element_type": ETYPE,
            "excerpt_start_paragraph": i,
            "excerpt_end_paragraph": i,
            "inferred_position": "unknown",
            "inferred_timing": "unknown",
            "confidence": "high",
        }
        for i, _p in enumerate(paragraphs, start=1)
    ]
    return {"elements": elements, "escalate_to_tier2": False}, paragraphs


def _ledger_doc_ids(ledger_path: Path) -> set[str]:
    rows = json.loads(ledger_path.read_text())
    return {r["doc_id"] for r in rows}


def _report_element_count(l0_dir: Path) -> int:
    """The count REPORT.md advertises — the number ledger.json must match."""
    text = (l0_dir / "REPORT.md").read_text()
    m = re.search(r"\*\*Elements in ledger:\*\*\s*(\d+)", text)
    assert m, "REPORT.md missing '**Elements in ledger:**' line"
    return int(m.group(1))


def _run_in_tmp(fn):
    """Run `fn(tmp_project, sources)` with layer0 pointed at a hermetic temp project
    and the model + config faked. Sources are copied from the committed fixture so a
    test may safely mutate them (to force a cache miss)."""
    with tempfile.TemporaryDirectory() as td:
        tmp_project = Path(td) / "ledger-mini"
        sources = tmp_project / "sources"
        sources.mkdir(parents=True)
        for src in FIXTURE_SOURCES.glob("doc_*.txt"):
            shutil.copy(src, sources / src.name)

        with patch("layer0.project_dir", return_value=tmp_project), patch(
            "layer0.load_config", return_value={}
        ), patch(
            "layer0._decompose_text_with_retry", side_effect=_fake_decompose
        ):
            fn(tmp_project, sources)


def test_full_run_ledger_matches_report():
    """A clean full run persists EVERY element; ledger.json == REPORT.md == expected."""

    def body(tmp_project: Path, sources: Path):
        layer0.run_layer0("ledger-mini", sources, resume=True)
        l0_dir = tmp_project / "layer0"
        ledger_path = l0_dir / "ledger.json"

        rows = json.loads(ledger_path.read_text())
        assert len(rows) == EXPECTED_TOTAL, (
            f"ledger.json has {len(rows)} elements, expected {EXPECTED_TOTAL}"
        )
        # The core invariant the bug violated: on-disk ledger must equal what
        # REPORT.md (written post-loop from memory) advertises.
        assert len(rows) == _report_element_count(l0_dir)
        assert _ledger_doc_ids(ledger_path) == set(EXPECTED_ELEMENTS_PER_DOC)

    _run_in_tmp(body)


def test_mostly_cached_run_does_not_truncate_ledger():
    """THE regression: after a first (seeding) run, re-run with only the FIRST
    (sorted) doc changed. It decomposes fresh (firing the in-loop checkpoint early)
    while the later docs are cache hits that never re-trigger a write. The ledger
    must still contain ALL docs — pre-fix it truncated to just the fresh doc."""

    def body(tmp_project: Path, sources: Path):
        # First run seeds the ledger + content-hash cache for all three docs.
        layer0.run_layer0("ledger-mini", sources, resume=True)
        ledger_path = tmp_project / "layer0" / "ledger.json"
        assert _ledger_doc_ids(ledger_path) == set(EXPECTED_ELEMENTS_PER_DOC)

        # Change ONLY the alphabetically-first doc so its content_hash no longer
        # matches the cache -> it (and only it) re-decomposes. The later two docs
        # cache-hit and, crucially, are appended AFTER the last fresh checkpoint.
        first_doc = sources / "doc_aaaa01_Mini_Lesson_Plan.txt"
        first_doc.write_text(
            first_doc.read_text() + "\n\nExtension: research a plant native to Texas.\n"
        )

        layer0.run_layer0("ledger-mini", sources, resume=True)

        doc_ids = _ledger_doc_ids(ledger_path)
        assert doc_ids == set(EXPECTED_ELEMENTS_PER_DOC), (
            "ledger.json was truncated — cache-hit docs after the last fresh "
            f"decompose were dropped. Present: {sorted(doc_ids)}"
        )
        # And it still agrees with REPORT.md (now 5 + 3 + 2 = 10 elements).
        l0_dir = tmp_project / "layer0"
        rows = json.loads(ledger_path.read_text())
        assert len(rows) == _report_element_count(l0_dir)

    _run_in_tmp(body)


if __name__ == "__main__":
    test_full_run_ledger_matches_report()
    print("OK test_full_run_ledger_matches_report")
    test_mostly_cached_run_does_not_truncate_ledger()
    print("OK test_mostly_cached_run_does_not_truncate_ledger")
    print("ALL LAYER0 LEDGER-COMPLETENESS TESTS PASSED")
