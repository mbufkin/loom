#!/usr/bin/env python3
"""
report_delivery.py — One bounded synthesis call for first-pass + teacher.

Mise en place (Layer 0→2, plus synthesize.py's deterministic tables) stays the
source of truth and IS the finding — every status/count in this report is
already computed and already cited before any model runs. This module's only
job is ONE model call per report (run_teacher_synthesis / run_first_pass_
synthesis) that reads that already-computed data and adds what a table can't:
priority ordering and cross-row/cross-unit root cause, in a short paragraph.

This replaced an earlier three-phase Findings→Patterns→Recommendations chain
(three separate model calls, each restating the same rows in a new JSON shape)
that (a) added no information beyond the tables it sat next to and (b) was the
source of a real JSON-parse failure mode that silently dropped whole sections
(see git history / dallas-career-2026 financial-literacy run). Plain-text
output sidesteps that failure mode entirely — a malformed response degrades to
odd prose instead of an exception. See docs/REPORT-DELIVERY.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audit_lib import (
    atomic_write,
    log,
    model_chat,
    project_dir,
)

# Rough char→token estimate for packing budgets (local Nemotron context).
CHARS_PER_TOKEN = 4
# Soft cap for packed JSON shown to the model (~28k tokens of input facts).
DEFAULT_TOKEN_BUDGET = 28_000
EXCERPT_MAX = 400

TEACHER_SYNTHESIS_RULES = """
You are a curriculum auditor writing ONE short synthesis note for a classroom
teacher / unit owner.

You are given a binary evidence table that is ALREADY COMPUTED and ALREADY
CORRECT — every row was verified against the written curriculum by an earlier
model pass. Do not recompute, re-judge, or contradict any row.

Your ONLY job: 2-4 sentences that add something the table alone doesn't show.
- Name the SINGLE highest-priority action first (author missing material /
  pull from another drive / drop from the day-grid / resolve a duplicate) and
  say which slot(s) it applies to.
- If several MISSING rows share one root cause (e.g. every day is missing
  lesson content), say that ONCE — don't repeat per day.
- If a PRESENT row's own evidence text implies the file may not really serve
  that slot, you may flag it, but never invent a claim the table doesn't
  support.
- Never write lesson content, assessments, rubrics, or rewrites.
- Never restate a row just to restate it — if a sentence would only repeat
  what the table already says, cut it.
- Plain language, no SET/coaching/observation jargon. Plain prose only — no
  headers, no bullet list, no JSON.
- Only refer to days that appear in CALENDAR SCOPE below. Do not say "every
  day" or name a day number that isn't listed there.
""".strip()


def run_teacher_synthesis(
    cfg: dict,
    *,
    project_id: str,
    unit_id: str,
    unit_title: str,
    evidence_table_md: str,
    l2_summary: str,
    day_labels: list[str],
    raw_dir: Path,
) -> tuple[str, str | None]:
    """One tight model call over the ALREADY-COMPUTED evidence table (synthesis,
    not restatement). Plain-text return — no JSON schema, so a malformed model
    response degrades to plain (possibly odd) prose instead of a parse
    exception that silently drops the whole section (see git history: the old
    3-phase JSON chain did exactly that on this same unit). Returns (text, error);
    text is '' on failure."""
    prompt = f"""{TEACHER_SYNTHESIS_RULES}

UNIT: {unit_title}

CALENDAR SCOPE (the ONLY days this unit has — do not reference any other day):
{', '.join(day_labels) if day_labels else '(no dated days — unit supporting materials only)'}

EVIDENCE TABLE (source of truth — do not contradict):
{evidence_table_md}

LESSON PLAN TEMPLATE CHECK:
{l2_summary or '(not judged / no lesson plans confirmed for this unit)'}
"""
    step = f"report-teacher-synthesis-{unit_id}"
    try:
        resp = model_chat(
            cfg,
            "analyst",
            [{"role": "user", "content": prompt}],
            step,
            temperature=0.2,
            max_tokens=400,
        )
        text = _extract_content(resp).strip()
        atomic_write(raw_dir / "synthesis.txt", text)
        return text, None
    except Exception as e:
        log(f"WARN: teacher synthesis failed ({project_id}/{unit_id}): {e}")
        atomic_write(raw_dir / "synthesis-error.txt", str(e))
        return "", str(e)


FIRST_PASS_SYNTHESIS_RULES = """
You are a curriculum auditor writing ONE short synthesis note for a district
curriculum review work session (course-wide scope, many units at once).

You are given an ALREADY-COMPUTED aggregate pack — status counts, a per-unit
rollup, systemic gaps that repeat across 3+ units, and Layer 2 lesson-plan
completeness. All of that is already correct and already tabulated in the
report around this note. Do not recompute or contradict any number in it.

Your ONLY job: one tight paragraph (aim for 3-6 sentences) that adds what the
tables can't show on their own:
- Name the ONE or TWO systemic patterns most worth spending work-session time
  on (e.g. one role missing across many units = fix the S&S once, not
  unit-by-unit; a cluster of units all missing the same component).
- If you name which units account for most of a gap, you MUST copy that
  ranking verbatim from the precomputed top_missing_units / top_mismatch_units
  lists in DATA. Do NOT compute your own ranking by eyeballing unit_rollup or
  mismatch_docs_high/low — those lists are for citing individual examples
  only, not for deriving "which units are worst." If top_missing_units /
  top_mismatch_units is empty or too thin to support a claim, don't make one.
- Recommendation options are limited to: author missing material, pull from
  another drive, drop/adjust the day-grid expectation, relocate a misfiled
  document, or mark an expected overlap in manifest.yaml. Never write lesson
  content, assessments, rubrics, or rewrites.
- Never restate a number that's already in the pack (e.g. "12 documents are
  incomplete") unless you're using it to justify a priority call.
- Only name units/roles that appear in DATA below — never invent one, and
  never attach a specific count/ranking claim to a unit unless that exact
  claim is computed for you in top_missing_units / top_mismatch_units.
- Plain language for CTE leads / unit owners. No SET/coaching/observation
  jargon. Plain prose only — no headers, no bullet list, no JSON.
""".strip()


def run_first_pass_synthesis(
    cfg: dict,
    *,
    project_id: str,
    packed: "PackedContext",
    raw_dir: Path,
) -> tuple[str, str | None]:
    """One tight model call over the ALREADY-COMPUTED course-wide aggregate pack
    (synthesis, not restatement) — the first-pass counterpart of
    run_teacher_synthesis(). Plain-text return; see that function's docstring
    for why (avoids the JSON-parse failure mode the old 3-phase chain hit).
    Returns (text, error); text is '' on failure."""
    unit_titles = sorted(
        {u.get("title") for u in (packed.payload.get("unit_rollup") or []) if u.get("title")}
    )
    prompt = f"""{FIRST_PASS_SYNTHESIS_RULES}

UNITS IN SCOPE (the ONLY units this pack covers):
{', '.join(unit_titles) if unit_titles else '(none)'}

DATA (aggregate pack — source of truth, do not contradict):
{json.dumps(packed.payload, indent=2, ensure_ascii=False)}
"""
    step = f"report-first-pass-synthesis-{project_id}"
    try:
        resp = model_chat(
            cfg,
            "analyst",
            [{"role": "user", "content": prompt}],
            step,
            temperature=0.2,
            max_tokens=600,
        )
        text = _extract_content(resp).strip()
        atomic_write(raw_dir / "synthesis.txt", text)
        return text, None
    except Exception as e:
        log(f"WARN: first-pass synthesis failed ({project_id}): {e}")
        atomic_write(raw_dir / "synthesis-error.txt", str(e))
        return "", str(e)


@dataclass
class PackedContext:
    """Curated facts for one delivery call."""

    audience: str  # "first-pass" | "teacher"
    scope_id: str  # project_id or unit_id
    payload: dict[str, Any]
    truncated: bool = False
    approx_tokens: int = 0


def _approx_tokens(obj: Any) -> int:
    return max(1, len(json.dumps(obj, ensure_ascii=False)) // CHARS_PER_TOKEN)


def _trunc_excerpt(text: str | None, limit: int = EXCERPT_MAX) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _extract_content(response: dict) -> str:
    return response["choices"][0]["message"]["content"]


def _raw_dir(project_id: str, report_id: str, scope_id: str) -> Path:
    safe = re.sub(r"[^a-z0-9._-]+", "-", scope_id.lower())
    d = project_dir(project_id) / "output" / "raw" / "reports" / report_id / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slim_mismatch(d: dict) -> dict:
    return {
        "doc_id": d.get("doc_id"),
        "title": d.get("title"),
        "parent_title": d.get("parent_title"),
        "matched_title": d.get("matched_title"),
        "parent_unit_id": d.get("parent_unit_id"),
        "matched_unit_id": d.get("matched_unit_id"),
        "excerpt": _trunc_excerpt(d.get("excerpt")),
        "corroboration": d.get("corroboration") or d.get("mismatch_corroboration"),
    }


def _top_units_by(rollup: list[dict], key: str, limit: int = 5) -> list[dict]:
    """Precomputed ranking so the model never has to eyeball unit_rollup /
    mismatch_docs_* itself to decide "which units are worst" — that kind of
    freeform aggregation over a raw list is exactly where a model confabulates
    a plausible-sounding but false claim (confirmed live: an earlier run named
    three real units as accounting for "most of the mismatch documents" when
    the pack actually contained exactly one mismatch_docs_high entry, and none
    of the three named units were it). Code computes the ranking; the model is
    only allowed to restate it."""
    ranked = sorted(
        (u for u in rollup if (u.get(key) or 0) > 0),
        key=lambda u: u[key],
        reverse=True,
    )[:limit]
    return [{"title": u.get("title"), key: u.get(key)} for u in ranked]


def pack_first_pass_context(
    project_id: str,
    agg: dict,
    agg2: dict,
    pacing: dict | None,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> PackedContext:
    """Course-level pack: aggregates + systemic gaps + top mismatches + L2 rollup."""
    payload: dict[str, Any] = {
        "audience": "first-pass",
        "project_id": project_id,
        "documents_judged": agg.get("documents_judged"),
        "elements_judged": agg.get("elements_judged"),
        "status_counts": agg.get("status_counts"),
        "finding_status_counts": agg.get("finding_status_counts"),
        "systemic_missing": agg.get("systemic_missing") or [],
        "review_queue_pending_pairs": agg.get("review_queue_pending_pairs"),
        "top_missing_units": _top_units_by(agg.get("unit_rollup") or [], "missing"),
        "top_mismatch_units": _top_units_by(agg.get("unit_rollup") or [], "mismatch"),
        "unit_rollup": [
            {
                "unit_id": u.get("unit_id"),
                "title": u.get("title"),
                "match": u.get("match"),
                "mismatch": u.get("mismatch"),
                "fulfilled": u.get("fulfilled"),
                "missing": u.get("missing"),
                "duplicate": u.get("duplicate"),
            }
            for u in (agg.get("unit_rollup") or [])
        ],
        "mismatch_docs_high": [
            _slim_mismatch(d) for d in (agg.get("mismatch_docs_high") or [])[:20]
        ],
        "mismatch_docs_low": [
            _slim_mismatch(d) for d in (agg.get("mismatch_docs_low") or [])[:10]
        ],
        "layer2": {
            "documents_judged": agg2.get("documents_judged"),
            "complete_count": agg2.get("complete_count"),
            "incomplete_count": agg2.get("incomplete_count"),
            "systemic_missing_components": agg2.get("systemic_missing_components")
            or [],
            "incomplete_docs": [
                {
                    "doc_id": d.get("doc_id"),
                    "title": d.get("title"),
                    "components_missing": d.get("components_missing"),
                }
                for d in (agg2.get("incomplete_docs") or [])[:25]
            ],
        },
        "pacing": pacing,
    }
    truncated = False
    # Drop low-priority mismatch samples first if over budget.
    while _approx_tokens(payload) > token_budget:
        truncated = True
        if payload.get("mismatch_docs_low"):
            payload["mismatch_docs_low"] = payload["mismatch_docs_low"][:-5] or []
            if not payload["mismatch_docs_low"]:
                payload.pop("mismatch_docs_low", None)
            continue
        if len(payload.get("mismatch_docs_high") or []) > 5:
            payload["mismatch_docs_high"] = payload["mismatch_docs_high"][:-5]
            continue
        if len(payload.get("unit_rollup") or []) > 8:
            # Keep units with the most missing/mismatch; drop quiet ones.
            roll = sorted(
                payload["unit_rollup"],
                key=lambda u: (u.get("missing") or 0) + (u.get("mismatch") or 0),
                reverse=True,
            )
            payload["unit_rollup"] = roll[: max(8, len(roll) - 4)]
            continue
        break
    return PackedContext(
        audience="first-pass",
        scope_id=project_id,
        payload=payload,
        truncated=truncated,
        approx_tokens=_approx_tokens(payload),
    )


def merge_narrative_after_marker(md: str, marker: str, narrative_md: str) -> str:
    """Insert narrative block immediately after a section that starts with `marker`.

    Finds the marker line, then inserts before the next `## ` heading (or at EOF).
    """
    if not narrative_md.strip():
        return md
    idx = md.find(marker)
    if idx < 0:
        # Fallback: append before the last non-goals / ignore section if present
        return md.rstrip() + "\n\n" + narrative_md.strip() + "\n"
    # End of the section that contains the marker: next ## after marker's line
    after = idx + len(marker)
    # Skip rest of current section body until next level-2 heading
    rest = md[after:]
    m = re.search(r"\n## ", rest)
    if not m:
        return md.rstrip() + "\n\n" + narrative_md.strip() + "\n"
    insert_at = after + m.start()
    return md[:insert_at] + "\n\n" + narrative_md.strip() + "\n" + md[insert_at:]
