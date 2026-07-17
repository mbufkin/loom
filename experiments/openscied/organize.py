#!/usr/bin/env python3
"""
organize.py v1 — Organize classified chunks into an instructional sequence.
Reads 01-classification.json, applies merging logic and calendar alignment,
and writes 02-organized-sequence.json.
"""

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from audit_lib import log, load_config, project_dir, resolve_unit_paths


def merge_teacher_guidance(chunks: list) -> list:
    """Merge 'teacher_reference' chunks back into their parent lesson when they
    represent Additional Teacher Guidance embedded within a lesson.

    Strategy: Look for a 'teacher_reference' chunk whose chunk_id contains a lesson
    number (e.g. lesson-06), then find the lesson chunk with the matching lesson
    number and merge the guidance into it, regardless of position order.
    """
    merged = []
    skip_ids = set()

    # Pass 1: identify mapping of lesson_number → lesson chunk index
    lesson_map = {}  # lesson_number -> index in 'chunks'
    for i, chunk in enumerate(chunks):
        ci = chunk["classification"]
        ln = ci.get("lesson_number") or chunk.get("lesson_num")
        # Accept either non-teacher-reference classification OR lesson type from decomposition
        is_lesson = (
            ln is not None
            and (
                ci.get("pedagogical_type") != "teacher_reference"
                or chunk.get("type") == "lesson"
            )
            and chunk.get("type") != "assessment_resource"
            and chunk.get("type") != "front_matter"
        )
        if is_lesson:
            lesson_map[ln] = i

    # Pass 2: merge guidance into their corresponding lesson
    for i, chunk in enumerate(chunks):
        if chunk["chunk_id"] in skip_ids:
            continue

        ci = chunk["classification"]
        chunk_id = chunk["chunk_id"]

        # Extract lesson number from chunk_id (e.g., "lesson-06" → 6)
        m = re.search(r"(?:lesson|lesson[-\s]?)(\d+)", chunk_id)
        chunk_ln = int(m.group(1)) if m else None

        is_guidance = (
            ci.get("pedagogical_type") == "teacher_reference"
            and chunk_ln is not None
            and chunk_ln in lesson_map
            and chunk["type"] == "lesson"
        )

        if is_guidance:
            target_idx = lesson_map[chunk_ln]
            target_chunk = chunks[target_idx]

            log(
                f"  Merging {chunk_id} → {target_chunk['chunk_id']} (teacher guidance, L{chunk_ln})"
            )
            target_chunk["char_count"] += chunk["char_count"]
            target_chunk["page_end"] = max(
                target_chunk.get("page_end", 0) or 0,
                chunk.get("page_end", 0) or 0,
            )
            topics = set(target_chunk["classification"].get("key_topics", []))
            topics.update(ci.get("key_topics", []))
            target_chunk["classification"]["key_topics"] = sorted(topics)
            target_chunk["classification"]["has_embedded_guidance"] = True
            target_chunk["merged_chunks"] = target_chunk.get("merged_chunks", []) + [
                chunk_id
            ]
            skip_ids.add(chunk_id)
            continue

        merged.append(chunk)

    return merged


def merge_design_challenge(chunks: list) -> list:
    """Merge consecutive design_challenge chunks into a single Design Challenge unit."""
    merged = []
    skip_ids = set()
    i = 0

    while i < len(chunks):
        if chunks[i]["chunk_id"] in skip_ids:
            i += 1
            continue

        ci = chunks[i]["classification"]
        if ci.get("pedagogical_type") == "design_challenge":
            dc_group = [chunks[i]]
            j = i + 1
            while j < len(chunks):
                if chunks[j]["chunk_id"] in skip_ids:
                    j += 1
                    continue
                cj = chunks[j]["classification"]
                if cj.get("pedagogical_type") == "design_challenge":
                    dc_group.append(chunks[j])
                    skip_ids.add(chunks[j]["chunk_id"])
                    j += 1
                else:
                    break

            if len(dc_group) > 1:
                merged_chunk = deepcopy(dc_group[0])
                log(
                    f"  Merging design challenges: {' + '.join(c['chunk_id'] for c in dc_group)}"
                )
                total_days = 0
                all_topics = set()
                all_summaries = []
                merged_ids = []
                for dc in dc_group:
                    dci = dc["classification"]
                    total_days += dci.get("estimated_instructional_days") or 0
                    all_topics.update(dci.get("key_topics", []))
                    all_summaries.append(dci.get("summary", ""))
                    merged_ids.append(dc["chunk_id"])
                merged_chunk["char_count"] = sum(dc["char_count"] for dc in dc_group)
                merged_chunk["page_end"] = max(
                    dc.get("page_end", 0) or 0 for dc in dc_group
                )
                merged_chunk["title"] = "Engineering Design Challenge"
                merged_chunk["merged_chunks"] = (
                    merged_chunk.get("merged_chunks", []) + merged_ids
                )
                merged_chunk["classification"][
                    "estimated_instructional_days"
                ] = total_days
                merged_chunk["classification"]["key_topics"] = sorted(all_topics)
                merged_chunk["classification"]["summary"] = " ; ".join(all_summaries)
                merged_chunk["classification"]["is_full_lesson"] = True
                merged.append(merged_chunk)
            else:
                merged.append(chunks[i])
        else:
            merged.append(chunks[i])
        i += 1

    return merged


def assign_lesson_types(chunks: list) -> list:
    """Assign OpenSciEd-style lesson type labels based on pedagogical_type."""
    type_map = {
        "anchoring_phenomenon": "anchoring",
        "elicitation": "elicitation",
        "investigation": "investigation",
        "model_building": "model_building",
        "design_challenge": "design_challenge",
        "reading": "reading",
        "discussion": "discussion",
        "problem_set": "problem_set",
        "assessment": "assessment",
        "teacher_reference": "teacher_reference",
        "front_matter": "front_matter",
        "back_matter": "back_matter",
        "assessment_resource": "assessment_resource",
        "appendix": "appendix",
    }

    for chunk in chunks:
        ci = chunk["classification"]
        ped = ci.get("pedagogical_type", "")
        ci["lesson_type_label"] = type_map.get(ped, ped)
        ci["local_lesson_number"] = chunk.get("lesson_num") or chunk["chunk_id"]

    return chunks


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()

    cfg = load_config()
    root, manifest, unit_entry, out_dir = resolve_unit_paths(args.project, args.unit)

    # Load classification
    class_path = out_dir / "01-classification.json"
    if not class_path.is_file():
        log(f"ERROR: classification not found at {class_path} — run classify first")
        return 1

    with open(class_path) as f:
        classification = json.load(f)

    chunks = classification["chunks"]
    log(f"Loaded {len(chunks)} classified chunks")

    # --- Phase 1: Merge teacher guidance ---
    log("=== Phase 1: Merge Teacher Guidance ===")
    chunks = merge_teacher_guidance(chunks)
    log(f"  After merge: {len(chunks)} chunks")

    # --- Phase 2: Merge design challenge ---
    log("=== Phase 2: Merge Design Challenge ===")
    chunks = merge_design_challenge(chunks)
    log(f"  After merge: {len(chunks)} chunks")

    # --- Phase 3: Assign lesson types ---
    chunks = assign_lesson_types(chunks)

    # --- Phase 4: Build instructional sequence ---
    log("=== Phase 4: Instructional Sequence ===")

    # Non-instructional
    non_inst_types = {"front_matter", "back_matter", "appendix", "assessment_resource"}
    front = [
        c for c in chunks if c["classification"]["pedagogical_type"] in non_inst_types
    ]
    lessons = [c for c in chunks if c not in front]

    # Sort lessons by lesson number
    def lesson_key(c):
        ci = c["classification"]
        ln = ci.get("lesson_number")
        if ln is not None:
            return (0, ln)
        m = re.search(r"lesson[-\s]?(\d+)", c["chunk_id"])
        if m:
            return (0, int(m.group(1)))
        return (1, c["chunk_id"])

    lessons.sort(key=lesson_key)
    sequence = front + lessons

    # --- Phase 5: Calendar alignment ---
    log("=== Phase 5: Calendar Alignment ===")

    total_estimated_days = 0
    breakdown = []
    for c in sequence:
        ci = c["classification"]
        ped = ci.get("pedagogical_type", "unknown")
        days = ci.get("estimated_instructional_days") or 0

        if ped in non_inst_types:
            label = "non-instructional"
            break_days = 0
        else:
            label = "instructional"
            break_days = days
            total_estimated_days += break_days

        breakdown.append(
            {
                "chunk_id": c["chunk_id"],
                "title": c.get("title", ""),
                "pedagogical_type": ped,
                "lesson_type_label": ci.get("lesson_type_label", ped),
                "estimated_days": days,
                "category": label,
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "char_count": c.get("char_count", 0),
                "merged_chunks": c.get("merged_chunks", []),
                "summary": ci.get("summary", ""),
            }
        )

    # Load calendar for comparison
    import yaml

    calendar_days = 0
    calendar_data = unit_entry.get("calendar", {})
    if isinstance(calendar_data, str) and calendar_data.endswith(".yaml"):
        cal_path = root / calendar_data
        if cal_path.is_file():
            calendar_data = yaml.safe_load(cal_path.read_text())
    if isinstance(calendar_data, dict):
        calendar_days = calendar_data.get("unit_length_days", 0)

    discrepancy = total_estimated_days - calendar_days if calendar_days else 0

    log(f"\n  Calendar budget: {calendar_days} days")
    log(f"  Estimated need:  {total_estimated_days} days")
    log(f"  Discrepancy:     {'+' if discrepancy > 0 else ''}{discrepancy} days")
    if discrepancy > 0:
        log(f"  → Calendar is {discrepancy} days short — needs expansion")
    elif discrepancy < 0:
        log(f"  → Calendar has {-discrepancy} extra days — room for enrichment")
    else:
        log(f"  → Calendar and estimate match")

    # --- Phase 6: Write output ---
    output = {
        "project_id": args.project,
        "unit_id": args.unit,
        "source_file": classification.get("source_file"),
        "total_chars": classification.get("total_chars"),
        "total_estimated_days": total_estimated_days,
        "calendar_budget_days": calendar_days,
        "discrepancy_days": discrepancy,
        "chunks_before_merge": len(classification["chunks"]),
        "chunks_after_merge": len(sequence),
        "instructional_chunks": len(
            [b for b in breakdown if b["category"] == "instructional"]
        ),
        "non_instructional_chunks": len(
            [b for b in breakdown if b["category"] != "instructional"]
        ),
        "sequence": breakdown,
    }

    out_path = out_dir / "02-organized-sequence.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nWrote organized sequence to {out_path}")

    # Print summary
    log("\n=== Instructional Sequence ===")
    log(f"{'Chunk':30s} {'Type':25s} {'Days':>5s} {'Pages':>10s}")
    log("-" * 75)
    for b in breakdown:
        pages = f"{b['page_start']}-{b['page_end']}" if b["page_start"] else "—"
        days_str = str(b["estimated_days"]) if b["category"] == "instructional" else "—"
        merge_tag = " [merged]" if b.get("merged_chunks") else ""
        log(
            f"  {b['chunk_id']:28s} {b['lesson_type_label']:25s} {days_str:>5s} {pages:>10s}{merge_tag}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
