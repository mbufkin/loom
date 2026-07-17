#!/usr/bin/env python3
"""
classify.py v1 — Classify decomposed chunks by pedagogical type.
Reads 00-decomposition.json, sends each chunk to the analyst model
(Gemma), and writes 01-classification.json with pedagogical type,
estimated days, assessment types, and key topics.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from audit_lib import (
    log,
    load_config,
    model_chat,
    parse_model_json,
    project_dir,
    resolve_unit_paths,
)

CLASSIFY_SYSTEM_PROMPT = """You are a curriculum analyst evaluating a chunk of a science Teacher Edition PDF.

Classify this chunk by its pedagogical function. Return a JSON object with these fields:

{
  "pedagogical_type": string,  // one of: "anchoring_phenomenon", "elicitation", "investigation", "reading", "model_building", "problem_set", "discussion", "lab", "design_challenge", "assessment", "rubric", "teacher_reference", "front_matter", "back_matter"
  "confidence": float,         // 0.0 to 1.0
  "estimated_instructional_days": int | null,  // null if not instructional
  "has_formative_assessment": boolean,
  "has_summarive_assessment": boolean,
  "assessment_types": [string],  // e.g. ["exit_ticket", "check_for_understanding", "written_response", "performance_task"]
  "key_topics": [string],       // 2-5 key science topics in this chunk
  "summary": string,            // 1-2 sentence summary of what this chunk contains
  "is_full_lesson": boolean,    // true if this is a complete lesson
  "lesson_number": int | null,  // lesson number if applicable
  "lesson_title": string | null // lesson title if available
}

Examine the content carefully. Look for:
- Lesson structure: Learning Plan Snapshot, materials, steps
- Assessment type: embedded questions, exit tickets, performance tasks
- Activity type: hands-on lab, reading, discussion, model-building
- The "Where We Are Going" section for lesson goals

Respond with ONLY the JSON object, no other text."""


CLASSIFY_USER_TEMPLATE = """Here is a chunk from the OpenSciEd Teacher Edition for "Thermal Energy: Cup Design" (Unit 6.2).

Chunk: {chunk_id}
Title: {title}
Estimated position: page {page_range}
Chunk size: {char_count:,} characters

--- CHUNK CONTENT (TRUNCATED TO 80000 CHARS) ---
{content}
--- END CHUNK ---

Classify this chunk's pedagogical type, estimated days, assessment types, and key topics."""


def get_evidence_chunk(out_dir: Path) -> dict | None:
    """Load the decomposition output."""
    dec_path = out_dir / "00-decomposition.json"
    if not dec_path.is_file():
        log(f"ERROR: decomposition not found at {dec_path}")
        return None
    with open(dec_path) as f:
        return json.load(f)


def get_content(out_dir: Path) -> str | None:
    """Get the full document content from evidence."""
    ev_dir = out_dir / "evidence"
    if not ev_dir.is_dir():
        log(f"ERROR: evidence directory not found at {ev_dir}")
        return None
    ev_files = list(ev_dir.glob("*.json"))
    if not ev_files:
        log(f"ERROR: no evidence JSON files in {ev_dir}")
        return None

    with open(ev_files[0]) as f:
        record = json.load(f)
    content = record.get("content_clean", "")
    if not content:
        log("ERROR: no content_clean in evidence record")
        return None
    return content


def classify_chunk(cfg: dict, chunk: dict, full_content: str) -> dict:
    """Send one chunk to the model for classification."""
    chunk_id = chunk["chunk_id"]
    start = chunk["start_char"]
    end = chunk["end_char"]

    # Extract content from the full document
    chunk_content = full_content[start:end]

    # Truncate for the model if needed
    max_chars = 80000
    if len(chunk_content) > max_chars:
        chunk_content = chunk_content[:max_chars]
        chunk_content += f"\n\n[...CONTENT TRUNCATED from {chunk['char_count']:,} to {max_chars:,} chars...]"

    # Build page range string
    ps = chunk.get("page_start")
    pe = chunk.get("page_end")
    page_range = f"p.{ps}-{pe}" if ps else "N/A"

    user_msg = CLASSIFY_USER_TEMPLATE.format(
        chunk_id=chunk_id,
        title=chunk.get("title", "Untitled"),
        page_range=page_range,
        char_count=chunk.get("char_count", len(chunk_content)),
        content=chunk_content,
    )

    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    log(f"  Classifying {chunk_id} ({len(chunk_content):,} chars)...")

    try:
        resp = model_chat(
            cfg,
            "analyst",
            messages,
            f"classify-{chunk_id}",
            temperature=0.1,
            max_tokens=2048,
            retries=2,
        )
        model_text = resp["choices"][0]["message"]["content"]

        # Parse with flexible JSON extractor
        result = parse_model_json(model_text, context=f"classify-{chunk_id}")

        # Ensure required fields
        result.setdefault("pedagogical_type", "unknown")
        result.setdefault("confidence", 0.0)
        result.setdefault("estimated_instructional_days", None)
        result.setdefault("has_formative_assessment", False)
        result.setdefault("has_summarive_assessment", False)
        result.setdefault("assessment_types", [])
        result.setdefault("key_topics", [])
        result.setdefault("summary", model_text[:200])
        result.setdefault("is_full_lesson", False)
        result.setdefault("lesson_number", chunk.get("lesson_num"))
        result.setdefault("lesson_title", chunk.get("title"))

        log(
            f"    → {result['pedagogical_type']} | {result.get('estimated_instructional_days', '?')} days | conf={result['confidence']:.2f}"
        )

        return result

    except Exception as e:
        log(f"    ERROR: {e}")
        return {
            "pedagogical_type": "error",
            "confidence": 0.0,
            "estimated_instructional_days": None,
            "has_formative_assessment": False,
            "has_summarive_assessment": False,
            "assessment_types": [],
            "key_topics": [],
            "summary": f"Classification failed: {e}",
            "is_full_lesson": False,
            "lesson_number": chunk.get("lesson_num"),
            "lesson_title": chunk.get("title"),
            "error": str(e),
        }


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit to first N chunks (for testing)",
    )
    args = parser.parse_args()

    cfg = load_config()
    root, manifest, unit_entry, out_dir = resolve_unit_paths(args.project, args.unit)

    # Load decomposition
    decomposition = get_evidence_chunk(out_dir)
    if not decomposition:
        return 1

    # Load full content
    full_content = get_content(out_dir)
    if not full_content:
        return 1

    chunks = decomposition["chunks"]
    log(f"Loaded {len(chunks)} chunks from decomposition")
    log(f"Full document: {len(full_content):,} chars")

    # Limit for testing
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
        log(f"Testing mode: first {len(chunks)} chunks only")

    # Classify each chunk
    classifications = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        log(f"[{i + 1}/{total}] Processing {chunk['chunk_id']}...")
        result = classify_chunk(cfg, chunk, full_content)
        classifications.append(
            {
                "chunk_id": chunk["chunk_id"],
                "type": chunk["type"],
                "title": chunk.get("title"),
                "char_count": chunk.get("char_count", 0),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "classification": result,
            }
        )

        # Brief pause between chunks
        if i < total - 1:
            time.sleep(0.5)

    # Summary
    log(f"\n=== Classification Summary ===")
    lesson_days = 0
    for c in classifications:
        ci = c["classification"]
        days = ci.get("estimated_instructional_days") or 0
        lesson_days += days
        label = f"{ci['pedagogical_type']:25s}"
        days_str = (
            f"{days:3d} days" if ci.get("estimated_instructional_days") else "    --"
        )
        log(f"  {c['chunk_id']:25s} {label} {days_str}  {ci.get('summary', '')[:80]}")

    log(f"\nTotal estimated instructional days: {lesson_days}")

    # Write output
    output = {
        "source_file": decomposition.get("source_file"),
        "total_chars": decomposition.get("total_chars"),
        "total_estimated_days": lesson_days,
        "chunks": classifications,
    }

    out_path = out_dir / "01-classification.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nWrote classification to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
