#!/usr/bin/env python3
"""
curriculum_review.py — the two-stage, grounded per-lesson "curriculum review".

This is the productized form of experiments/curriculum_review_ab.py. For every
lesson it answers a curriculum director's question — *does this material hold
together?* — in a reviewer's voice, and it does so WITHOUT letting the model
hallucinate:

  STAGE 1 (select)  Pick the element that plays each pedagogical role
                    (objective / instruction / practice / assessment), choosing
                    ONLY from type-correct candidates drawn from the Layer 0
                    element_type taxonomy (completeness_core8). This makes a
                    mis-slotting error structurally impossible — the model can
                    only pick a `guided_practice` element for the practice role.

  STAGE 2 (evaluate) Judge the through-line between those verified spans, plus
                    what the material does well / where it falls short. Every
                    claim must cite a real tag; fabricated cites are dropped in a
                    deterministic self-audit.

Output (mirrors the lesson-quality plate so the UI reads it the same way):

  projects/<id>/[e2e/runs/<run>/]output/LESSON-CURRICULUM-REVIEW.json
  (grouped by unit_id; honors LOOM_E2E_RUN via project_dir)

WHY A SEPARATE STAGE
Like lesson_quality.py this is ADVISORY (model-based, never gates a verdict) and
NON-BLOCKING: if the model is offline or a lesson errors, we log and move on.

Usage:
  python3 curriculum_review.py --project bluebonnet-math-2026 --unit alg1-mod-2
  python3 curriculum_review.py --project bluebonnet-math-2026            # all units
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_lib import (  # noqa: E402
    load_config,
    log,
    model_chat,
    parse_model_json,
    project_dir,
)
from lesson_bakeoff import enumerate_lessons  # noqa: E402

SCORER_ID = "curriculum_review_2stage_v1"

# Role -> canonical Layer 0 element_types (from completeness_core8.yaml). Reusing
# the taxonomy the pipeline ALREADY tags means the model never hunts dozens of
# elements to find "the objective" — it only chooses among type-correct
# candidates, so it cannot slot an instruction element into the objective role.
ROLES = ("objective", "instruction", "practice", "assessment")
ROLE_TYPES = {
    "objective": {"standards_objectives"},
    "instruction": {"direct_instruction"},
    "practice": {"guided_practice", "independent_practice"},
    "assessment": {"assessment_checkpoint"},
}
MAX_CANDS = 8  # cap per role so a 17-guided-practice lesson stays a sane prompt


# ---- STAGE 1: grounded selection -------------------------------------------
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

# ---- STAGE 2: grounded evaluation (reviewer voice) -------------------------
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


def _extract_role_tag(content: str | None, role: str) -> str | None:
    """Pull the tag a role was assigned in Stage 1 WITHOUT trusting strict JSON.
    Local models emit the tag under wildly different quoting — `"E9"`, bare `E9`,
    escaped `\\"E6\\"`, even double-wrapped `"\\"E7\\""` — and a single bad escape
    makes the whole document unparseable. Stage 1 is just four tag picks, so we scan
    each role's value for the first E<number>, or honor an explicit null.

    Some hosted reasoning models return `content: null` (answer only in a separate
    reasoning channel) — treat that as empty so we don't crash the lab run.
    """
    if not content:
        return None
    m = re.search(rf'["\']?{role}["\']?\s*:\s*([^,}}\n]+)', content)
    if not m:
        return None
    value = m.group(1)
    if re.search(r'\bnull\b', value, re.IGNORECASE):
        return None
    tag = re.search(r'E\d+', value)
    return tag.group(0) if tag else None


def assemble_tagged(elements) -> dict[str, dict]:
    """Relabel each element with a SHORT, stable tag (E1, E2, …). Models reliably
    copy short handles but mangle long opaque ids. tag_map[tag] carries the REAL
    element_id + excerpt + element_type so we translate/verify citations in code."""
    tag_map: dict[str, dict] = {}
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
    return tag_map


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


def stage1_select(cfg, candidates, tag_map, *, verbose: bool = False) -> dict[str, dict]:
    """Return {role: {tag, real_id, excerpt}} for each role the model could ground.
    A pick is accepted ONLY if it is in that role's type-correct candidate set."""
    block_lines: list[str] = []
    for role in ROLES:
        block_lines.append(f"{role} candidates:")
        if not candidates[role]:
            block_lines.append("  (none)")
        for tag, ex in candidates[role]:
            block_lines.append(f"  [{tag}] {ex[:180]}")
    block = "\n".join(block_lines)

    role_tags = {r: {t for t, _ in candidates[r]} for r in ROLES}
    have_candidates = any(role_tags[r] for r in ROLES)

    # A single local model call is occasionally flaky (empty / malformed JSON). When
    # candidates clearly exist but we grounded nothing, retry ONCE at temp 0 before
    # giving up — cheap insurance against a one-off blip sinking a whole lesson.
    verified: dict[str, dict] = {}
    for attempt in (1, 2):
        resp = model_chat(
            cfg,
            "analyst",
            [
                {"role": "system", "content": SELECT_SYS},
                {"role": "user", "content": SELECT_USER.replace("%%CANDS%%", block)},
            ],
            step="review:select",
            temperature=0.0 if attempt == 2 else 0.1,
            max_tokens=800,
        )
        # Hosted reasoning models sometimes return content=null and park text in
        # reasoning_content — fall back so the lab doesn't crash mid-compare.
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning_content") or ""

        verified = {}
        for role in ROLES:
            tag = _extract_role_tag(content, role)
            if not tag or tag not in role_tags[role]:
                if verbose and attempt == 2 or verbose and not have_candidates:
                    print(f"  {role:12} — CANNOT_ASSESS")
                continue
            verified[role] = {
                "tag": tag,
                "real_id": tag_map[tag]["real_id"],
                "excerpt": tag_map[tag]["excerpt"],
            }
            if verbose:
                print(f"  {role:12} — ✓ [{tag}] {tag_map[tag]['excerpt'][:55]}…")

        # Success, or nothing more to gain from a retry (no candidates to ground).
        if verified or not have_candidates:
            break
        if verbose:
            print("  stage1 grounded 0 roles despite candidates — retrying once…")
    return verified


def stage2_evaluate(cfg, verified, valid_ids, *, verbose: bool = False) -> dict | None:
    """Return the audited evaluation dict (fabricated cites removed) or None."""
    if not verified:
        return None
    evidence = "\n".join(
        f"- {role}: [{v['tag']}] {v['excerpt'][:400]}" for role, v in verified.items()
    )
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
    msg = resp["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""
    try:
        # No _repair_bare_tags here — Stage 2 already quotes its element_ids and its
        # reason strings contain literal "[E34]" that the repair would corrupt.
        out = parse_model_json(content, context="stage2 eval")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"  stage2 JSON parse failed ({e}); raw:\n{content[:800]}")
        return None

    def clean(ids):
        """Deterministic self-audit: keep only cites that name a real, present tag."""
        return [i for i in (ids or []) if i in valid_ids]

    for link in out.get("through_line", []):
        link["element_ids"] = clean(link.get("element_ids"))
    for bucket in ("does_well", "falls_short"):
        for item in out.get(bucket, []):
            item["element_ids"] = clean(item.get("element_ids"))
    return out


def review_lesson(cfg, lesson, source_file=None, *, verbose: bool = False) -> dict:
    """Run both stages for one lesson and return a UI-ready record."""
    tag_map = assemble_tagged(lesson.elements)
    valid_ids = set(tag_map)
    candidates = build_candidates(tag_map)

    t0 = time.time()
    verified = stage1_select(cfg, candidates, tag_map, verbose=verbose)
    out = stage2_evaluate(cfg, verified, valid_ids, verbose=verbose) or {}
    dt = time.time() - t0

    # Evidence map for every cited tag, so the UI can show the actual quote (and the
    # role each cited span played) beneath the reviewer's sentences.
    cited: set[str] = set()
    for link in out.get("through_line", []):
        cited.update(link.get("element_ids", []))
    for bucket in ("does_well", "falls_short"):
        for item in out.get(bucket, []):
            cited.update(item.get("element_ids", []))
    tag_role = {v["tag"]: role for role, v in verified.items()}
    evidence = {
        tag: {
            "element_id": tag_map[tag]["real_id"],
            "excerpt": tag_map[tag]["excerpt"][:300],
            "role": tag_role.get(tag),
        }
        for tag in sorted(cited)
        if tag in tag_map
    }

    return {
        "lesson_id": lesson.lesson_id,
        "title": lesson.title,
        "unit_id": lesson.unit_id,
        "source_file": source_file,
        "scorer": SCORER_ID,
        "seconds": round(dt, 1),
        "roles_verified": len(verified),
        "roles": {
            role: (
                {"tag": v["tag"], "element_id": v["real_id"], "excerpt": v["excerpt"][:300]}
                if (v := verified.get(role))
                else None
            )
            for role in ROLES
        },
        "through_line": out.get("through_line", []),
        "does_well": out.get("does_well", []),
        "falls_short": out.get("falls_short", []),
        "evidence": evidence,
    }


def _doc_source_map(project: str) -> dict[str, str]:
    """doc_id -> sources/<file> so the UI can show raw lesson text (same convention
    as the lesson-quality plate).

    Educational note: honor project_dir() so LOOM_E2E_RUN trees get the same
    ledger the rest of the pipeline wrote — never hardcode live projects/<id>/.
    """
    ledger = project_dir(project) / "layer0" / "ledger.json"
    out: dict[str, str] = {}
    if ledger.is_file():
        for row in json.loads(ledger.read_text()):
            did, sf = row.get("doc_id"), row.get("source_file")
            if did and sf and did not in out:
                out[did] = f"sources/{sf}"
    return out


def _resolve_source(doc_source: dict[str, str], lesson_id: str) -> str | None:
    """Map a lesson to its raw source. Teacher-edition lessons are FANNED children
    ('<module>.pdf__L2'), whose parent module PDF is what the ledger actually holds,
    so fall back to the id before the '__L#' suffix when the exact id has no source."""
    if lesson_id in doc_source:
        return doc_source[lesson_id]
    parent = lesson_id.split("__", 1)[0]
    return doc_source.get(parent)


def generate(project: str, unit: str | None = None) -> Path:
    """Review every lesson (optionally filtered to one unit) and write the JSON plate
    the UI reads. Returns the JSON path. Existing units are preserved when a single
    unit is regenerated, so `--unit` runs are incremental, not destructive."""
    cfg = load_config()
    lessons = enumerate_lessons(project)
    if unit:
        lessons = [le for le in lessons if le.unit_id == unit]
    doc_source = _doc_source_map(project)
    log(f"curriculum-review: reviewing {len(lessons)} lessons"
        + (f" in unit {unit}" if unit else "") + f" with {SCORER_ID}")

    units: dict[str, list[dict]] = {}
    for le in lessons:
        try:
            rec = review_lesson(cfg, le, source_file=_resolve_source(doc_source, le.lesson_id))
        except Exception as e:  # noqa: BLE001 — advisory + non-blocking, per stage contract
            log(f"WARN: curriculum-review skipped {le.lesson_id}: {e}")
            continue
        units.setdefault(le.unit_id, []).append(rec)
        log(f"reviewed {le.title} ({rec['roles_verified']}/4 roles, {rec['seconds']}s)")

    # Same e2e isolation as lesson_quality: write under project_dir()/output/.
    out_dir = project_dir(project) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "LESSON-CURRICULUM-REVIEW.json"

    # Merge with any existing plate so a single-unit run doesn't wipe the others.
    payload = {"generated": "", "project": project, "scorer": SCORER_ID, "units": {}}
    if json_path.is_file():
        try:
            payload = json.loads(json_path.read_text())
            payload.setdefault("units", {})
        except Exception:  # noqa: BLE001
            payload = {"project": project, "scorer": SCORER_ID, "units": {}}
    payload["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload["scorer"] = SCORER_ID
    payload["units"].update(units)

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"curriculum-review: wrote {json_path}")
    return json_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-stage grounded per-lesson curriculum review.")
    ap.add_argument("--project", default="bluebonnet-math-2026")
    ap.add_argument("--unit", default=None, help="restrict to one unit_id (e.g. alg1-mod-2)")
    args = ap.parse_args()
    generate(args.project, args.unit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
