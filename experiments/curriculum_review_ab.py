#!/usr/bin/env python3
"""
curriculum_review_ab.py — a two-stage, grounded CURRICULUM REVIEW pass.

Frame (per the director's steer): this is NOT teacher coaching. It evaluates the
MATERIAL as a curriculum artifact — what it does well, where it falls short — in
a reviewer's third-person voice, and it NEVER prescribes changes (auditor_only).

It applies the prompting research (docs/LESSON-QUALITY-RESEARCH.md + the 2026
LLM-judge / grounded-generation literature) to fix the two failures we saw in the
naive pass (fabricated citations + generic sprawl/rewriting):

  STAGE 1 — SELECT (extract-then-reason / "attribute first"):
     the model may ONLY pick verbatim spans tagged with their REAL element_ids.
     -> then we verify every id + quote against the actual elements IN CODE, so
        a hallucinated citation can never reach stage 2.

  STAGE 2 — EVALUATE (pinned G-Eval steps, reviewer voice, structured JSON):
     using ONLY the verified evidence, judge the through-line links and emit two
     evaluative buckets (does_well / falls_short), citation-first, no rewrites.
     -> then we audit stage-2 citations against real ids too (drop the rest).

Usage:
  python3 experiments/curriculum_review_ab.py --project bluebonnet-math-2026 \
      --lesson Module_5.pdf__L2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_lib import load_config, model_chat, parse_model_json  # noqa: E402
from lesson_bakeoff import enumerate_lessons  # noqa: E402

# Role -> canonical Layer 0 element_types (from completeness_core8.yaml). Reusing
# the taxonomy the pipeline ALREADY tags means the model never hunts 61 elements
# to find "the objective" — it only chooses among type-correct candidates, so it
# structurally cannot slot an instruction element into the objective role.
ROLES = ("objective", "instruction", "practice", "assessment")
ROLE_TYPES = {
    "objective": {"standards_objectives"},
    "instruction": {"direct_instruction"},
    "practice": {"guided_practice", "independent_practice"},
    "assessment": {"assessment_checkpoint"},
}
MAX_CANDS = 8  # cap per role so a 17-guided-practice lesson stays a sane prompt


def _norm(s: str) -> str:
    """Whitespace/case-normalize for tolerant verbatim matching."""
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _repair_bare_tags(text: str) -> str:
    """Small robustness patch: the model sometimes emits an unquoted tag token
    (`"assessment": E7`), which is invalid JSON. Quote any bare E<number> that sits
    in a value position so parse_model_json can read it. Cheap and safe — it only
    touches E-number tokens, never real content."""
    text = re.sub(r'(:\s*)(E\d+)(\s*[,}\]\n])', r'\1"\2"\3', text)  # value position
    text = re.sub(r'([\[,]\s*)(E\d+)(\s*[,\]])', r'\1"\2"\3', text)  # inside arrays
    return text


def assemble_tagged(elements) -> tuple[str, dict[str, dict]]:
    """Return (tagged_text, tag_map). We relabel each element with a SHORT, stable
    tag (E1, E2, …) because models reliably copy short handles but mangle/omit long
    opaque ids (the fabricated-`e1` failure we just saw). tag_map[tag] carries the
    REAL element_id + excerpt so we translate the model's tag citations back to real
    ids — and verify them — entirely in code."""
    tag_map: dict[str, dict] = {}
    parts = []
    for i, el in enumerate(elements, 1):
        ex = (el.excerpt or "").strip()
        if not ex:
            continue
        tag = f"E{i}"
        tag_map[tag] = {
            "real_id": el.element_id,
            "excerpt": ex,
            "etype": el.element_type or "unclear",
        }
        parts.append(f"[{tag} · {el.element_type or 'unclear'}]\n{ex[:600]}")
    return "\n\n".join(parts), tag_map


def build_candidates(tag_map: dict[str, dict]) -> dict[str, list[tuple[str, str]]]:
    """Group tags into per-role candidate lists by their Layer 0 element_type.
    Compound types (a|b) match if ANY part maps to the role. tag_map preserves
    document order, so candidates read top-to-bottom; we cap each list at MAX_CANDS."""
    cands: dict[str, list[tuple[str, str]]] = {r: [] for r in ROLES}
    for tag, m in tag_map.items():
        parts = {p for p in (m["etype"] or "").split("|") if p}
        for role, types in ROLE_TYPES.items():
            if parts & types:
                cands[role].append((tag, m["excerpt"]))
    return {r: v[:MAX_CANDS] for r, v in cands.items()}


# ---- STAGE 1: grounded selection --------------------------------------------
SELECT_SYS = (
    "You are locating evidence in a curriculum document. Do NOT evaluate yet. "
    "For each role, choose the ONE element that best represents it, chosen ONLY "
    "from that role's candidate list below. Return the element's TAG as a quoted "
    "JSON string (e.g. \"E7\"). You MUST pick a tag for every role that has "
    "candidates; return null ONLY when a role's candidate list is literally empty. "
    "Output strict JSON only."
)
SELECT_USER = (
    'JSON shape: {"objective": "E#" or null, "instruction": "E#" or null, '
    '"practice": "E#" or null, "assessment": "E#" or null}\n\n'
    "Candidates by role:\n%%CANDS%%"
)

# ---- STAGE 2: grounded evaluation (reviewer voice) --------------------------
EVAL_SYS = (
    "You are a CURRICULUM REVIEWER evaluating instructional material for a school "
    "district. You assess the MATERIAL itself for a curriculum director — you do "
    "NOT advise or coach whoever wrote it, and you do NOT suggest changes, "
    "rewrites, or additions. Third-person, evaluative voice.\n\n"
    "You are given verified evidence spans (each labeled with a short tag like E7). "
    "Judge how well the material holds together as a coherent lesson, using these "
    "fixed steps:\n"
    "  1. objective->instruction: does the instruction follow from the objective?\n"
    "  2. instruction->practice: does the practice follow from the instruction?\n"
    "  3. practice->assessment: does the assessment measure the objective?\n"
    "Return exactly three through_line entries, one per step above.\n\n"
    "Rules:\n"
    "- Cite element_ids BEFORE each claim, e.g. '[<id>] the assessment measures…'.\n"
    "- Use ONLY the element_ids provided in the evidence. If evidence is missing for "
    "a step, mark it CANNOT_ASSESS — do not invent a problem.\n"
    "- 'does_well' = evaluative strengths of the material; 'falls_short' = evaluative "
    "shortfalls (a broken through-line, an assessment that doesn't measure the "
    "objective, an isolated/orphaned part). DESCRIBE the shortfall; never prescribe a fix.\n"
    "- Be concise. Length is not rewarded.\n"
    "Output strict JSON only."
)
EVAL_USER = (
    "JSON shape (link is exactly one of the three step names; verdict is one of "
    "CONNECTS / BREAKS / CANNOT_ASSESS):\n"
    '{"through_line": ['
    '{"link": "objective->instruction", "verdict": "...", "element_ids": ["E#"], "reason": "one sentence"}, '
    '{"link": "instruction->practice", "verdict": "...", "element_ids": ["E#"], "reason": "one sentence"}, '
    '{"link": "practice->assessment", "verdict": "...", "element_ids": ["E#"], "reason": "one sentence"}], '
    '"does_well": [{"point": "...", "element_ids": ["E#"]}], '
    '"falls_short": [{"point": "...", "element_ids": ["E#"]}]}\n\n'
    "Verified evidence:\n%%EVIDENCE%%"
)


def stage1_select(cfg, candidates, tag_map):
    print(f"\n{'=' * 78}\nSTAGE 1 · grounded selection (type-filtered candidates)\n{'=' * 78}")
    # Show the per-role candidate lists the model must choose from.
    for role in ROLES:
        print(f"  {role:12} candidates: {[t for t, _ in candidates[role]] or '(none)'}")

    block_lines = []
    for role in ROLES:
        block_lines.append(f"{role} candidates:")
        if not candidates[role]:
            block_lines.append("  (none)")
        for tag, ex in candidates[role]:
            block_lines.append(f"  [{tag}] {ex[:180]}")
    block = "\n".join(block_lines)

    t0 = time.time()
    resp = model_chat(
        cfg,
        "analyst",
        [
            {"role": "system", "content": SELECT_SYS},
            {"role": "user", "content": SELECT_USER.replace("%%CANDS%%", block)},
        ],
        step="review:select",
        temperature=0.1,
        max_tokens=800,
    )
    dt = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    try:
        sel = parse_model_json(_repair_bare_tags(content), context="stage1 select")
    except Exception as e:  # noqa: BLE001
        print(f"  JSON parse failed ({e}); raw:\n{content}")
        return {}

    # Verification is now stricter: the pick must be in THIS role's candidate set,
    # so a type-mismatched slotting is impossible, not just improbable.
    role_tags = {r: {t for t, _ in candidates[r]} for r in ROLES}
    verified: dict[str, dict] = {}
    for role in ROLES:
        tag = sel.get(role)
        if isinstance(tag, dict):
            tag = tag.get("element_id")
        if not tag:
            why = "no candidates" if not candidates[role] else "model returned null"
            print(f"  {role:12} — CANNOT_ASSESS ({why})")
            continue
        if tag not in role_tags[role]:
            print(f"  {role:12} — ✗ REJECTED: {tag!r} is not a {role} candidate")
            continue
        ex = tag_map[tag]["excerpt"]
        verified[role] = {"tag": tag, "real_id": tag_map[tag]["real_id"], "excerpt": ex}
        print(f"  {role:12} — ✓ [{tag} → {tag_map[tag]['real_id']}] {ex[:55]}…")
    print(f"  --- {dt:.1f}s · {len(verified)}/4 roles verified ---")
    return verified


def stage2_evaluate(cfg, verified, valid_ids):
    print(f"\n{'=' * 78}\nSTAGE 2 · grounded evaluation (reviewer voice)\n{'=' * 78}")
    if not verified:
        print("  no verified evidence — skipping (honest: cannot assess).")
        return
    evidence = "\n".join(
        f"- {role}: [{v['tag']}] {v['excerpt'][:400]}" for role, v in verified.items()
    )
    t0 = time.time()
    resp = model_chat(
        cfg,
        "analyst",
        [
            {"role": "system", "content": EVAL_SYS},
            {"role": "user", "content": EVAL_USER.replace("%%EVIDENCE%%", evidence)},
        ],
        step="review:evaluate",
        temperature=0.2,
        max_tokens=1600,
    )
    dt = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    try:
        # NOTE: no _repair_bare_tags here. Stage 2 already quotes its element_ids,
        # and its `reason` strings legitimately contain literals like "[E34]" — the
        # repair regex would wrap those into ["E34"] and corrupt otherwise-valid JSON.
        out = parse_model_json(content, context="stage2 eval")
    except Exception as e:  # noqa: BLE001
        print(f"  JSON parse failed ({e}); raw:\n{content}")
        return

    def audit(ids):
        """Split cited ids into real vs fabricated (the self-audit step)."""
        good = [i for i in (ids or []) if i in valid_ids]
        bad = [i for i in (ids or []) if i not in valid_ids]
        return good, bad

    print("\nTHROUGH-LINE:")
    for link in out.get("through_line", []):
        good, bad = audit(link.get("element_ids"))
        flag = f"  ⚠ dropped fabricated: {bad}" if bad else ""
        print(f"  • {link.get('link'):24} {link.get('verdict'):13} {link.get('reason','')}")
        print(f"      cites {good}{flag}")

    for bucket, title in (("does_well", "WHAT IT DOES WELL"), ("falls_short", "WHERE IT FALLS SHORT")):
        print(f"\n{title}:")
        for item in out.get(bucket, []):
            good, bad = audit(item.get("element_ids"))
            flag = f"  ⚠ dropped fabricated: {bad}" if bad else ""
            print(f"  • {item.get('point','')}")
            print(f"      cites {good}{flag}")
    print(f"\n  --- {dt:.1f}s ---")


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-stage grounded curriculum review.")
    ap.add_argument("--project", default="bluebonnet-math-2026")
    ap.add_argument("--lesson", default="Module_5.pdf__L2")
    args = ap.parse_args()

    cfg = load_config()
    lessons = enumerate_lessons(args.project)
    target = next((l for l in lessons if args.lesson in l.lesson_id), None)
    if target is None:
        print(f"No lesson matching {args.lesson!r}. Available:",
              [l.lesson_id for l in lessons][:20])
        return 1

    _, tag_map = assemble_tagged(target.elements)
    valid_ids = set(tag_map)  # the short tags the model is allowed to cite
    candidates = build_candidates(tag_map)
    print(f"Lesson: {target.title}")
    print(f"  id={target.lesson_id}  elements={len(target.elements)}  "
          f"citable tags available={len(valid_ids)}")

    verified = stage1_select(cfg, candidates, tag_map)
    stage2_evaluate(cfg, verified, valid_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
