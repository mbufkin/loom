#!/usr/bin/env python3
"""
te_prepass.py — Teacher-Edition pre-pass: fan one multi-lesson Teacher Edition into
per-lesson child records so each lesson can flow through the same lesson-review
methods (the bake-off harness / Path A) as a natively discrete lesson.

The problem this solves (the "lesson atom" gap): a Bluebonnet/Eureka math Teacher
Edition is ONE PDF containing many lessons ("Lesson 1", "Lesson 2", ...). Loom's
lesson rung wants one lesson at a time. Rather than invent a bespoke parser, we
reuse a signal Layer 0 already captured — the "Lesson N" markers in element
excerpts — to split the TE's element stream into per-lesson segments.

Deterministic + offline: no model call, no invented content. A TE that lacks a
real multi-lesson structure (too few distinct "Lesson N" markers) is left alone
(returns no children) so we never manufacture lessons that aren't there.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from audit_lib import (
    atomic_write,
    classify_doc_type,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)

# "Lesson 12", "Lesson  3", "LESSON 1" — the marker Eureka/Bluebonnet TEs use to
# start each lesson. Word-bounded + digit so "lesson objectives" (no number) or a
# stray "lessons" never trip it.
LESSON_MARKER = re.compile(r"(?i)\blesson\s+(\d+)\b")
# A TE must show at least this many DISTINCT lesson numbers to be treated as a
# genuine multi-lesson container (2 is the minimum that makes "multi" meaningful;
# a glossary that says "Lesson 1" once is not a multi-lesson TE).
MIN_DISTINCT_LESSONS = 2


def _first_lesson_number(text: str) -> int | None:
    m = LESSON_MARKER.search(text or "")
    return int(m.group(1)) if m else None


def distinct_lesson_numbers(elements: list[dict]) -> set[int]:
    nums: set[int] = set()
    for el in elements:
        for m in LESSON_MARKER.findall(el.get("excerpt") or ""):
            nums.add(int(m))
    return nums


def looks_like_multi_lesson_te(elements: list[dict]) -> bool:
    """True when the element stream carries enough distinct 'Lesson N' markers to be
    a real multi-lesson container (the content-density confirmation of the filename
    guess classify_doc_type makes)."""
    return len(distinct_lesson_numbers(elements)) >= MIN_DISTINCT_LESSONS


def segment_te_document(elements: list[dict]) -> list[dict]:
    """Split a TE document's elements (in ledger order) into per-lesson segments by
    the running 'Lesson N' marker. Each element belongs to the most recently seen
    lesson number; elements before the first marker are front-matter and are NOT
    emitted as a lesson (they're module preamble, not a teachable lesson).

    Returns [{"lesson_number": int, "elements": [element dicts]}], ordered by first
    appearance — never merges two different lesson numbers, never invents a lesson."""
    segments: dict[int, list[dict]] = defaultdict(list)
    order: list[int] = []
    current: int | None = None
    for el in elements:
        n = _first_lesson_number(el.get("excerpt") or "")
        if n is not None:
            current = n
            if n not in segments:
                order.append(n)
        if current is not None:
            segments[current].append(el)
    return [{"lesson_number": n, "elements": segments[n]} for n in order]


def _te_docs(by_doc: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The documents in this ledger that are multi-lesson Teacher Editions — by
    filename type AND confirmed by the Lesson-N density signal (both must agree, so
    a mis-named file or a single-lesson TE is not force-split)."""
    out: dict[str, list[dict]] = {}
    for did, els in by_doc.items():
        source = els[0].get("source_file", did)
        if (
            classify_doc_type(source) == "teacher_edition_multi_lesson"
            and looks_like_multi_lesson_te(els)
        ):
            out[did] = els
    return out


def te_child_records(project_id: str) -> list[dict]:
    """Build per-lesson child records for every multi-lesson TE in the project.
    In-memory + deterministic; the harness consumes these directly and the CLI
    persists them for inspection. Child shape mirrors what enumerate_lessons needs."""
    root = project_dir(project_id)
    ledger_path = root / "layer0" / "ledger.json"
    if not ledger_path.is_file():
        return []
    ledger = json.loads(ledger_path.read_text())
    manifest = load_yaml(root / "manifest.yaml")

    doc_unit: dict[str, str] = {}
    for uid, unit in (manifest.get("units") or {}).items():
        for rel in unit.get("documents") or unit.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)

    by_doc: dict[str, list[dict]] = defaultdict(list)
    for el in ledger:
        by_doc[el["doc_id"]].append(el)

    from synthesize import readable_title_from_filename

    children: list[dict] = []
    for parent_id, els in _te_docs(by_doc).items():
        source = els[0].get("source_file", parent_id)
        base_title = readable_title_from_filename(source)
        for seg in segment_te_document(els):
            n = seg["lesson_number"]
            children.append(
                {
                    "project_id": project_id,
                    "lesson_id": f"{parent_id}__L{n}",
                    "parent_doc_id": parent_id,
                    "unit_id": doc_unit.get(parent_id, "(unlinked)"),
                    "lesson_number": n,
                    "title": f"{base_title} — Lesson {n}",
                    "elements": [
                        {
                            "element_id": e["element_id"],
                            "element_type": e.get("element_type", ""),
                            "excerpt": e.get("excerpt", ""),
                        }
                        for e in seg["elements"]
                    ],
                }
            )
    return children


def write_te_children(project_id: str) -> Path:
    """Persist one JSON per TE child lesson under layer_lesson/te_children/ and a
    manifest of them. Returns the output directory."""
    out_dir = project_dir(project_id) / "layer_lesson" / "te_children"
    out_dir.mkdir(parents=True, exist_ok=True)
    children = te_child_records(project_id)
    for child in children:
        atomic_write(
            out_dir / f"{child['lesson_id']}.json", json.dumps(child, indent=2)
        )
    parents = sorted({c["parent_doc_id"] for c in children})
    atomic_write(
        out_dir / "index.json",
        json.dumps(
            {
                "project_id": project_id,
                "te_parents": parents,
                "child_count": len(children),
                "children": [
                    {
                        "lesson_id": c["lesson_id"],
                        "parent_doc_id": c["parent_doc_id"],
                        "unit_id": c["unit_id"],
                        "lesson_number": c["lesson_number"],
                        "element_count": len(c["elements"]),
                    }
                    for c in children
                ],
            },
            indent=2,
        ),
    )
    log(
        f"te-prepass → {len(children)} child lesson(s) from {len(parents)} TE(s) "
        f"→ {out_dir}"
    )
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Teacher-Edition pre-pass — fan multi-lesson TEs into per-lesson children"
    )
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    validate_slug_id(args.project, "project id")
    try:
        write_te_children(args.project)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
