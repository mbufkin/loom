#!/usr/bin/env python3
"""
coach_ab.py — a one-lesson A/B probe for a final "model's thoughts" pass.

Question we're testing (from the research in docs/LESSON-QUALITY-RESEARCH.md):
  Can the local 30B (Nemotron-3-Nano-30B on :8080) add *insight* on top of the
  deterministic checklist — specifically, can it judge CONTINUITY/COHERENCE
  (does the lesson hang together as a through-line) rather than just restating
  what's present or emitting generic "the teacher could…" tips?

It runs the SAME lesson through two prompts and prints both, side by side:
  A) BASELINE  — open-ended "review this lesson plan" (the naive pass; the
     literature says this triggers the 82%-restatement failure mode).
  B) CONTINUITY — a targeted read of the lesson's internal through-line, grounded
     in the lesson's own text, explicitly NOT teacher-improvement advice.

This is a throwaway experiment, not a pipeline stage — it reuses the real
model_chat() and the real lesson assembly so what we see is what the product
would see.

Usage:
  python3 experiments/coach_ab.py --project bluebonnet-math-2026 --lesson Module_5.pdf__L2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_lib import load_config, model_chat  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402


def assemble_lesson_text(elements) -> str:
    """Reconstruct the lesson as the model will see it: each element tagged with
    its id + type so the model can CITE (e.g. [E12 guided_practice] ...). We keep
    the whole arc (continuity needs the full sequence) but cap each excerpt so a
    62-element lesson stays a sane prompt size."""
    parts = []
    for el in elements:
        excerpt = (el.excerpt or "").strip()
        if not excerpt:
            continue
        etype = el.element_type or "unclear"
        parts.append(f"[{el.element_id} · {etype}]\n{excerpt[:600]}")
    return "\n\n".join(parts)


# --- Prompt A: the naive baseline ---------------------------------------------
BASELINE_SYS = (
    "You are an experienced instructional reviewer. Review the lesson plan the "
    "user provides and share your thoughts on its quality."
)
BASELINE_USER = "Here is a lesson plan. Please review it.\n\n{lesson}"


# --- Prompt B: the targeted CONTINUITY read -----------------------------------
# Designed against the research: (1) grounded in the lesson's own text with
# citations, (2) scoped to coherence/through-line ONLY, (3) explicitly forbids
# generic "the teacher could improve…" advice and forbids restating what's
# present — the two documented failure modes.
CONTINUITY_SYS = (
    "You are an instructional coach analyzing ONE thing only: the CONTINUITY of a "
    "lesson — whether it holds together as a single coherent arc.\n\n"
    "Trace the through-line: does the stated objective flow into the instruction, "
    "does the instruction set up the practice, and does the assessment actually "
    "measure the objective? Point out where the lesson CONNECTS well and where "
    "continuity BREAKS (a jump with no bridge, a practice that doesn't follow from "
    "the teaching, an assessment that measures something the objective never named).\n\n"
    "Rules:\n"
    "- Every observation must quote the lesson's own text and cite the element id "
    "in brackets, e.g. [E12].\n"
    "- Do NOT give generic teaching tips or 'the teacher could…' suggestions.\n"
    "- Do NOT simply restate what the lesson contains; only discuss how the parts "
    "connect (or fail to).\n"
    "- If continuity is strong, say so plainly and show the links; do not invent "
    "problems.\n"
    "Be concise: a short narrative read, then the specific connect/break points."
)
CONTINUITY_USER = (
    "Lesson elements (in document order), each tagged [id · type]:\n\n{lesson}"
)


def run_pass(cfg, label: str, system: str, user: str) -> None:
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    t0 = time.time()
    resp = model_chat(cfg, "analyst", messages, step=f"coach_ab:{label}", temperature=0.2)
    dt = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    print(content.strip())
    print(
        f"\n--- {dt:.1f}s · prompt {usage.get('prompt_tokens', '?')} tok · "
        f"completion {usage.get('completion_tokens', '?')} tok ---"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="One-lesson A/B: baseline vs continuity read.")
    ap.add_argument("--project", default="bluebonnet-math-2026")
    ap.add_argument(
        "--lesson",
        default="Module_5.pdf__L2",
        help="Substring of the lesson_id to target (default: alg1 module 5 L2).",
    )
    args = ap.parse_args()

    cfg = load_config()
    lessons = enumerate_lessons(args.project)
    target = next((l for l in lessons if args.lesson in l.lesson_id), None)
    if target is None:
        print(f"No lesson matching {args.lesson!r} in {args.project}.")
        print("Available:", [l.lesson_id for l in lessons][:20])
        return 1

    lesson_text = assemble_lesson_text(target.elements)
    print(f"Lesson: {target.title}")
    print(f"  id={target.lesson_id}  unit={target.unit_id}  elements={len(target.elements)}")
    print(f"  assembled prompt length: {len(lesson_text)} chars")

    run_pass(cfg, "A · BASELINE (open-ended review)", BASELINE_SYS, BASELINE_USER.format(lesson=lesson_text))
    run_pass(cfg, "B · CONTINUITY (targeted, grounded)", CONTINUITY_SYS, CONTINUITY_USER.format(lesson=lesson_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
