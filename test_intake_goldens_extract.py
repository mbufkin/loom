#!/usr/bin/env python3
"""Intake golden accountability (wayfinder #6 / #7 / #10 / #12).

Offline: real scrub/extract; mocked ingest organize via validate_coverage +
synthetic L0/route/L1 ledgers. No live models.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

ACCOUNT_PATH = BASE / "tests" / "fixtures" / "intake-goldens" / "account.py"


def _load_account():
    spec = importlib.util.spec_from_file_location("intake_goldens_account", ACCOUNT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_all_packs_stage_accountability() -> None:
    account = _load_account()
    packs = account.discover_packs()
    assert packs, "expected at least one pack under tests/fixtures/intake-goldens/packs/"
    for pack_dir in packs:
        cfg = account.load_pack(pack_dir)
        with tempfile.TemporaryDirectory(prefix=f"intake-{cfg['id']}-") as td:
            sources = Path(td) / "sources"
            account.materialize_sources(pack_dir, sources)
            account.run_pack_accountability(pack_dir, sources)


def test_pack_many_little_has_volume() -> None:
    """Many-little pack must keep several seed files (shape intent)."""
    account = _load_account()
    pack = BASE / "tests/fixtures/intake-goldens/packs/pack-many-little"
    seeds = list((pack / "seeds").rglob("*"))
    seed_files = [p for p in seeds if p.is_file()]
    assert len(seed_files) >= 4


def test_ingest_fails_closed_when_file_unassigned() -> None:
    """Accountability contract: an extract_ok file omitted from the plan must fail."""
    account = _load_account()
    pack = BASE / "tests/fixtures/intake-goldens/packs/pack-many-little"
    with tempfile.TemporaryDirectory(prefix="intake-unassigned-") as td:
        sources = Path(td) / "sources"
        account.materialize_sources(pack, sources)
        extract = account.classify_extract(sources)
        # Drop one extract_ok path from the mock plan on purpose.
        plan = account.build_mock_ingest_plan(pack, extract)
        victim = plan["units"][0]["source_files"].pop()
        records = [
            {"source_file": rel, "char_count_clean": row["char_count_clean"]}
            for rel, row in extract.items()
            if row["status"] == "extract_ok"
        ]
        from ingest import validate_coverage

        errors = validate_coverage(records, plan)
        assert errors, f"expected coverage error after dropping {victim}"
        assert any("unassigned" in e for e in errors)


if __name__ == "__main__":
    test_pack_many_little_has_volume()
    print("ok  test_pack_many_little_has_volume")
    test_all_packs_stage_accountability()
    print("ok  test_all_packs_stage_accountability")
    test_ingest_fails_closed_when_file_unassigned()
    print("ok  test_ingest_fails_closed_when_file_unassigned")
    print("ALL intake golden TESTS PASSED")
