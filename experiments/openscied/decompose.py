#!/usr/bin/env python3
"""
decompose.py v4 — Group pages into lesson chunks.
A lesson spans from its first page marker to just before the next lesson's
first page marker (or assessment/back-matter section).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from audit_lib import log, load_config, model_chat, project_dir, resolve_unit_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()

    root, manifest, unit_entry, out_dir = resolve_unit_paths(args.project, args.unit)
    evidence_dir = out_dir / "evidence"

    evidence_records = []
    for rel in unit_entry.get("documents", []):
        ev_path = evidence_dir / f"{rel}.json"
        if ev_path.is_file():
            with open(ev_path) as f:
                evidence_records.append(json.load(f))
    if not evidence_records:
        log("ERROR: no evidence records — run scrub first")
        return 1

    record = evidence_records[0]
    content = record.get("content_clean", "")
    log(f"Document: {record['source_file']} ({len(content):,} chars)")

    # === PHASE 1: Extract all page markers with lesson numbers ===
    # Pattern: "Unit 6.2 • Lesson N • 1/27/25 Page NNN"
    page_markers = []
    for m in re.finditer(
        r"Unit\s+\d+\.\d+\s+[•·]\s*(Lesson\s+(\d+))?\s*[•·]\s*\d+/\d+/\d+\s+Page\s+(\d+)",
        content,
    ):
        lesson_str = m.group(1)  # "Lesson 1" or None (for front/back matter)
        lesson_num = int(m.group(2)) if m.group(2) else None
        page_num = int(m.group(3))
        page_markers.append(
            {
                "pos": m.start(),
                "lesson_num": lesson_num,
                "page_num": page_num,
                "is_lesson_page": lesson_num is not None,
            }
        )

    # === PHASE 2: Identify assessment/back-matter start ===
    # The assessment section typically starts when we see "Overall Unit Assessment"
    # or "Lesson-by-Lesson Assessment Opportunities" or "Unit-Specific Teacher Materials"
    assessment_start = None
    for m in re.finditer(
        r"(Overall Unit Assessment|Lesson-by-Lesson Assessment Opportunities|Unit-Specific Teacher Materials)",
        content,
    ):
        if assessment_start is None or m.start() < assessment_start:
            assessment_start = m.start()

    # Also check: if page markers go past lesson 18, those are answer keys / rubrics
    # The last lesson 18 page has the teacher reference pages after it

    # === PHASE 3: Build lesson chunks ===
    chunks = []

    # Front matter: everything before first lesson page
    lesson_page_markers = [p for p in page_markers if p["is_lesson_page"]]

    if not lesson_page_markers:
        chunks.append(
            {
                "chunk_id": "full",
                "type": "unknown",
                "title": "Full Document",
                "start_char": 0,
                "end_char": len(content),
            }
        )
    else:
        first_lesson_pos = lesson_page_markers[0]["pos"]
        last_lesson_num = max(p["lesson_num"] for p in lesson_page_markers)

        # Front matter
        chunks.append(
            {
                "chunk_id": "front-matter",
                "type": "front_matter",
                "title": "Front Matter & Unit Overview",
                "start_char": 0,
                "end_char": first_lesson_pos,
                "page_start": None,
                "page_end": None,
            }
        )

        # Group lesson pages by lesson number
        lesson_groups = {}
        for p in lesson_page_markers:
            ln = p["lesson_num"]
            if ln not in lesson_groups:
                lesson_groups[ln] = []
            lesson_groups[ln].append(p)

        # Get TOC titles for each lesson
        toc_titles = {}
        for m in re.finditer(
            r"(Lesson\s+(\d+):\s*(.+?))\s*(?:\d+\s*)?(?:\n|$)", content[0:20000]
        ):
            toc_titles[int(m.group(2))] = m.group(1).strip()

        # Build each lesson chunk
        sorted_lessons = sorted(lesson_groups.keys())
        for i, ln in enumerate(sorted_lessons):
            pages = lesson_groups[ln]
            start_pos = pages[0]["pos"]

            # End: next lesson's first page, or assessment_start, or end of content
            if i + 1 < len(sorted_lessons):
                next_ln = sorted_lessons[i + 1]
                next_pages = lesson_groups[next_ln]
                end_pos = next_pages[0]["pos"]
            elif assessment_start and assessment_start > start_pos:
                end_pos = assessment_start
            else:
                end_pos = len(content)

            start_page = min(p["page_num"] for p in pages)
            end_page = max(p["page_num"] for p in pages)
            title = toc_titles.get(ln, f"Lesson {ln}")

            chunks.append(
                {
                    "chunk_id": f"lesson-{ln:02d}",
                    "type": "lesson",
                    "title": title,
                    "start_char": start_pos,
                    "end_char": end_pos,
                    "lesson_num": ln,
                    "page_start": start_page,
                    "page_end": end_page,
                }
            )

        # Back matter: assessment section and teacher reference materials
        # Everything after the last lesson chunk
        last_lesson = lesson_groups[sorted_lessons[-1]]
        last_lesson_end = chunks[-1]["end_char"]

        if last_lesson_end < len(content):
            # Check if there are lesson-specific materials (answer keys, rubrics)
            # that appear after the main assessment section
            # These are still part of the back matter but categorized separately

            remaining = content[last_lesson_end:]

            # Check for assessment section
            if (
                "Assessment and Scoring" in remaining[:5000]
                or "Overall Unit Assessment" in remaining[:5000]
            ):
                chunks.append(
                    {
                        "chunk_id": "assessment-section",
                        "type": "assessment_resource",
                        "title": "Assessment and Scoring Guides",
                        "start_char": last_lesson_end,
                        "end_char": len(content),
                    }
                )
            elif "Unit-Specific Teacher Materials" in remaining[:5000]:
                chunks.append(
                    {
                        "chunk_id": "teacher-reference",
                        "type": "teacher_reference",
                        "title": "Unit-Specific Teacher Materials",
                        "start_char": last_lesson_end,
                        "end_char": len(content),
                    }
                )
            else:
                chunks.append(
                    {
                        "chunk_id": "back-matter",
                        "type": "appendix",
                        "title": "Answer Keys, Rubrics & Teacher Reference",
                        "start_char": last_lesson_end,
                        "end_char": len(content),
                    }
                )

    # === PHASE 4: Fill gaps between chunks ===
    chunks.sort(key=lambda c: c["start_char"])
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        curr = chunks[i]
        if prev["end_char"] < curr["start_char"]:
            prev["end_char"] = curr["start_char"]

    # === PHASE 5: Output ===
    total_lesson_chars = sum(
        c["end_char"] - c["start_char"] for c in chunks if c["type"] == "lesson"
    )
    log(f"\nBuilt {len(chunks)} chunks:")
    for c in chunks:
        csize = c["end_char"] - c["start_char"]
        ln = c.get("lesson_num", "")
        ps = c.get("page_start", "")
        pe = c.get("page_end", "")
        page_range = f"p.{ps}-{pe}" if ps and pe else ""
        prefix = f"L{ln:02d}" if ln else ""
        log(
            f"  [{c['type']:22s}] {prefix:4s} {c['title'][:62]:62s} {csize:>8,}c  {page_range:>14s}"
        )

    log(
        f"\nLesson content: {total_lesson_chars:,} chars ({total_lesson_chars/len(content)*100:.0f}% of document)"
    )

    # Extract previews
    output = {
        "source_file": record["source_file"],
        "total_chars": len(content),
        "chunks": [],
    }
    for c in chunks:
        chunk_content = content[c["start_char"] : c["end_char"]]
        c["char_count"] = len(chunk_content)
        c["preview"] = chunk_content[:300].strip()
        output["chunks"].append(c)

    out_path = out_dir / "00-decomposition.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nWrote decomposition to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
