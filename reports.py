#!/usr/bin/env python3
"""
reports.py — Modular report registry (plates from mise en place).

Overnight Layer 0→2 fills ledgers. This module plates them into audience-specific
markdown (and PDF for first-pass). first-pass and teacher default to *hybrid*
delivery: code-locked tables + multi-phase curriculum-audit narrative
(see report_delivery.py). dashboard / review-queue stay code-only.

Every report is a registered id with status implemented|planned. CLI / run_project
can call one, many, or all *implemented* reports. Adding a plate later is one
registry entry + renderer — not a new orchestration path.

See docs/CHAMPION-REVIEW-MAP.md and docs/REPORT-DELIVERY.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from audit_lib import (
    atomic_write,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)
from layer1 import UNIT_SUPPORTING_SLOT

# delivery: "model" = hybrid narrative (default for first-pass/teacher);
#           "code"  = deterministic plates only (fast regen).
DELIVERY_MODEL = "model"
DELIVERY_CODE = "code"


@dataclass(frozen=True)
class ReportSpec:
    """One plate in the registry."""

    id: str
    status: str  # "implemented" | "planned"
    summary: str
    # scope: "project" (one artifact) | "unit" (fan-out per unit_id)
    scope: str = "project"
    # needs: soft deps for --list-reports help text only; writers degrade if missing
    needs: tuple[str, ...] = ()


# Planned ids appear in --list-reports but are excluded from --report all.
PLANNED_REPORTS: dict[str, ReportSpec] = {
    "ops": ReportSpec(
        id="ops",
        status="planned",
        summary="Operator health after a long run (uncited %, Layer 0-B, golden drift)",
        needs=("layer0", "layer1"),
    ),
    "document": ReportSpec(
        id="document",
        status="planned",
        summary="Deep-dive packet for one source document (filter teacher grain by doc_id)",
        scope="unit",
        needs=("layer0", "layer1", "layer2"),
    ),
}


def list_report_specs() -> list[ReportSpec]:
    """Implemented specs first (registry order), then planned stubs."""
    implemented = [REPORTS[k].spec for k in REPORTS]
    planned = list(PLANNED_REPORTS.values())
    return implemented + planned


def resolve_report_ids(raw: str) -> list[str]:
    """Parse --report value: 'all' | 'first-pass' | 'first-pass,dashboard,teacher'."""
    raw = (raw or "all").strip().lower()
    if raw == "all":
        return list(REPORTS.keys())
    ids = [p.strip() for p in raw.split(",") if p.strip()]
    if not ids:
        raise ValueError("--report produced an empty id list")
    unknown = [i for i in ids if i not in REPORTS and i not in PLANNED_REPORTS]
    if unknown:
        known = ", ".join(list(REPORTS) + list(PLANNED_REPORTS))
        raise ValueError(f"unknown report id(s): {unknown} — known: {known}")
    planned_only = [i for i in ids if i in PLANNED_REPORTS]
    if planned_only:
        raise ValueError(
            f"report id(s) not implemented yet: {planned_only} — "
            "see --list-reports (planned). Use an implemented id or --report all."
        )
    # Preserve order, dedupe
    out: list[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


@dataclass
class ReportContext:
    """Shared mise-en-place snapshot loaded once per synthesize invocation."""

    project_id: str
    root: Path
    out_dir: Path
    manifest: dict
    bucket_rows: list[dict]
    findings: list[dict]
    agg: dict
    agg2: dict
    pacing: dict | None
    title_map: dict[str, str]
    delivery: str = DELIVERY_MODEL


def load_report_context(
    project_id: str, delivery: str = DELIVERY_MODEL
) -> ReportContext:
    """Load Layer 1/2 + pacing once; all report writers share this."""
    # Local imports avoid circular import at module load (synthesize imports reports).
    from synthesize import (
        aggregate_layer1,
        aggregate_layer2,
        build_doc_title_map,
        load_layer1_data,
        load_layer2_data,
        _load_pacing_brief,
    )

    if delivery not in (DELIVERY_MODEL, DELIVERY_CODE):
        raise ValueError(
            f"delivery must be '{DELIVERY_MODEL}' or '{DELIVERY_CODE}', got {delivery!r}"
        )
    root = project_dir(project_id)
    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_yaml(root / "manifest.yaml")
    bucket_rows, findings = load_layer1_data(project_id)
    agg = aggregate_layer1(bucket_rows, findings, manifest)
    title_map = build_doc_title_map(manifest)
    agg2 = aggregate_layer2(load_layer2_data(project_id), title_map)
    pacing = _load_pacing_brief(project_id)
    return ReportContext(
        project_id=project_id,
        root=root,
        out_dir=out_dir,
        manifest=manifest,
        bucket_rows=bucket_rows,
        findings=findings,
        agg=agg,
        agg2=agg2,
        pacing=pacing,
        title_map=title_map,
        delivery=delivery,
    )


def persist_aggregate_stats(ctx: ReportContext) -> None:
    """Write aggregate-stats.json (golden / ops input) whenever any report runs."""
    import json

    atomic_write(
        ctx.out_dir / "aggregate-stats.json",
        json.dumps(
            {**ctx.agg, "layer2": ctx.agg2, "pacing_brief": ctx.pacing},
            indent=2,
            sort_keys=True,
        ),
    )


# --- Writers -----------------------------------------------------------------


def write_first_pass(
    ctx: ReportContext, unit_ids: list[str] | None = None
) -> list[Path]:
    """Course-level Curriculum Review Work Packet (+ GLOBAL-AUDIT.md alias + PDF)."""
    del unit_ids  # project-scoped
    from synthesize import render_global_audit_deterministic

    md = render_global_audit_deterministic(
        ctx.project_id, ctx.agg, ctx.agg2, ctx.pacing
    )
    # Title line: keep champion framing but name the plate first-pass in a subtitle.
    if md.startswith("# Curriculum Review Work Packet"):
        md = md.replace(
            "# Curriculum Review Work Packet",
            "# Curriculum Review Work Packet (first-pass)\n\n"
            "*Report id: `first-pass` — course-level structure check.*",
            1,
        )

    if ctx.delivery == DELIVERY_MODEL:
        from audit_lib import load_config
        from report_delivery import (
            _raw_dir,
            merge_narrative_after_marker,
            pack_first_pass_context,
            run_first_pass_synthesis,
        )

        import json as _json

        packed = pack_first_pass_context(ctx.project_id, ctx.agg, ctx.agg2, ctx.pacing)
        raw_dir = _raw_dir(ctx.project_id, "first-pass", ctx.project_id)
        atomic_write(
            raw_dir / "pack.json",
            _json.dumps(packed.payload, indent=2, ensure_ascii=False),
        )
        synthesis, err = run_first_pass_synthesis(
            load_config(),
            project_id=ctx.project_id,
            packed=packed,
            raw_dir=raw_dir,
        )
        if synthesis:
            narrative = (
                "## Work-session synthesis (model delivery)\n\n"
                f"{synthesis}\n\n"
                "*Tables and counts throughout this report are code-locked from "
                "Layer 1/2 ledgers — treat them as the inventory of record; this "
                "note only adds prioritization across them.*\n"
            )
        else:
            narrative = (
                "## Work-session synthesis (model delivery)\n\n"
                f"*(Synthesis note skipped: {err}. Tables below are unaffected.)*\n"
            )
        # Insert after the work-session agenda so tables remain the inventory of record.
        md = merge_narrative_after_marker(
            md, "## 1. Work-session agenda (start here)", narrative
        )

    first_pass = ctx.out_dir / "FIRST-PASS.md"
    alias = ctx.out_dir / "GLOBAL-AUDIT.md"
    atomic_write(first_pass, md)
    atomic_write(alias, md)  # one-release compat for PDF / ops paths

    # Lightweight SUMMARY.md (batch table) — still useful next to first-pass
    import json

    path_a_hunter = None
    path_a_coherent = None
    path_a_findings = ctx.root / "path_a" / "findings.json"
    if path_a_findings.is_file():
        try:
            pa = json.loads(path_a_findings.read_text(encoding="utf-8"))
            a3 = (pa.get("steps") or {}).get("A3") or {}
            a5 = (pa.get("steps") or {}).get("A5") or {}
            path_a_hunter = a5.get("hunter_core_present")
            path_a_coherent = a3.get("status") == "COHERENT"
        except Exception:
            pass

    lines = [
        "# Audit Batch Summary",
        "",
        f"Units in scope: {len(ctx.agg['unit_rollup'])}",
        f"Elements judged: {ctx.agg['elements_judged']}",
        "",
        "| Unit | Tier | MATCH | MISMATCH | Slot status |",
        "|------|------|-------|----------|-------------|",
    ]
    for u in sorted(ctx.agg["unit_rollup"], key=lambda x: x["title"]):
        # Per-unit Hunter from LESSON-PLAN.json when available (overrides project Path A)
        hunter = path_a_hunter
        lp_json = ctx.root / "output" / "teachers" / u["unit_id"] / "LESSON-PLAN.json"
        if lp_json.is_file():
            try:
                lp = json.loads(lp_json.read_text(encoding="utf-8"))
                hunter = (lp.get("summary") or {}).get("hunter_core_present", hunter)
            except Exception:
                pass
        tier = compute_curriculum_tier(
            missing=u.get("missing") or 0,
            fulfilled=u.get("fulfilled") or 0,
            hunter_present=hunter,
            path_a_coherent=path_a_coherent,
        )
        # Slot status stays factual; calendar GAPS must not redefine a Strong Path A tier.
        if u["mismatch"]:
            slot_status = "REVIEW"
        elif u["missing"]:
            slot_status = (
                "calendar gaps"
                if tier["tier"] == "Strong"
                else "GAPS"
            )
        else:
            slot_status = "OK"
        lines.append(
            f"| {u['title']} | **{tier['tier']}** | {u['match']} | {u['mismatch']} | {slot_status} |"
        )
    atomic_write(ctx.out_dir / "SUMMARY.md", "\n".join(lines) + "\n")

    try:
        from render_pdf import render_project_pdf

        render_project_pdf(ctx.project_id)
    except Exception as e:
        log(f"WARN: PDF render skipped: {e}")

    log(f"report first-pass → {first_pass} (+ GLOBAL-AUDIT.md alias)")
    return [first_pass, alias]


def write_dashboard(
    ctx: ReportContext, unit_ids: list[str] | None = None
) -> list[Path]:
    del unit_ids
    from synthesize import render_dashboard

    path = ctx.out_dir / "DASHBOARD.md"
    atomic_write(path, render_dashboard(ctx.project_id, ctx.agg, ctx.agg2))
    log(f"report dashboard → {path}")
    return [path]


def write_review_queue(
    ctx: ReportContext, unit_ids: list[str] | None = None
) -> list[Path]:
    """Refresh layer1/REVIEW-QUEUE.md from the current bucket ledger (HITL source)."""
    del unit_ids
    from layer1 import build_review_queue_md

    path = ctx.root / "layer1" / "REVIEW-QUEUE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, build_review_queue_md(ctx.bucket_rows, ctx.manifest))
    # Pointer in output/ so --report all leaves a breadcrumb next to other plates
    pointer = ctx.out_dir / "REVIEW-QUEUE.md"
    atomic_write(
        pointer,
        "# Review queue\n\n"
        "Human overlap calibration lives next to Layer 1 (source of truth):\n\n"
        f"- `{path.relative_to(ctx.root)}`\n\n"
        "Re-run: `python3 synthesize.py --project "
        f"{ctx.project_id} --report review-queue`\n",
    )
    log(f"report review-queue → {path}")
    return [path, pointer]


def _unit_doc_ids(manifest: dict, unit_id: str) -> set[str]:
    unit = manifest["units"].get(unit_id) or {}
    docs = unit.get("documents") or unit.get("source_files") or []
    return {doc_id_from_filename(p) for p in docs}


def _pacing_unit_row(project_id: str, unit_id: str) -> dict | None:
    """Optional start/end/days for this unit from pacing-plan.yaml."""
    path = project_dir(project_id) / "pacing-plan.yaml"
    if not path.is_file():
        return None
    pacing = load_yaml(path)
    for u in pacing.get("units") or []:
        if u.get("unit_id") == unit_id:
            return u
    return None


def _present_component_labels(present: list) -> str:
    from synthesize import _component_label

    if not present:
        return "none of the core four"
    if isinstance(present[0], dict):
        return (
            ", ".join(_component_label(c["component"]) for c in present)
            or "none of the core four"
        )
    return ", ".join(_component_label(c) for c in present) or "none of the core four"


def _day_label(day_id: str | None) -> str:
    if not day_id:
        return ""
    if day_id == UNIT_SUPPORTING_SLOT:
        return "Unit supporting materials"
    m = re.match(r"^d(\d+)$", str(day_id), re.I)
    return f"Day {m.group(1)}" if m else str(day_id)


def _finding_titles(ids: list | None, title_map: dict[str, str]) -> str:
    """fulfilled_by element ids -> comma-joined human titles (dedup, order-stable)."""
    out: list[str] = []
    for eid in ids or []:
        doc = str(eid).replace("CANDIDATE ", "").split("-e")[0]
        title = title_map.get(doc, doc)
        if title not in out:
            out.append(title)
    return ", ".join(out)


STATUS_DISPLAY = {
    "FULFILLED": "PRESENT",
    "MISSING": "MISSING",
    "DUPLICATE": "DUPLICATE",
    "CHECK_FAILED": "CHECK FAILED",
}


def compute_curriculum_tier(
    *,
    missing: int,
    fulfilled: int,
    hunter_present: int | None = None,
    hunter_total: int = 8,
    path_a_coherent: bool | None = None,
) -> dict:
    """Honest Weak / Developing / Strong from evidence counts — no invention.

    Path A / Hunter structure can earn Strong even when calendar-slot MISSING
    counts are elevated (slot gaps stay visible in SUMMARY; they must not
    override a strong lesson-plan plate).
    """
    slots = missing + fulfilled
    miss_rate = (missing / slots) if slots else 1.0
    hunter_rate = (
        (hunter_present / hunter_total)
        if hunter_present is not None and hunter_total
        else None
    )

    # Prefer Path A plate when present — calendar GAPS are a separate signal.
    if hunter_rate is not None:
        if hunter_rate < 0.5 or miss_rate >= 0.7:
            tier = "Weak"
            blurb = (
                "Many expected materials or Hunter elements are MISSING. "
                "Blanks are the signal — not a failure of the auditor."
            )
        elif hunter_rate >= 0.85 and miss_rate < 0.7:
            if path_a_coherent is False:
                tier = "Developing"
                blurb = (
                    "Structure is largely present, but Path A flagged coherence gaps "
                    "(objective / activities / assessment)."
                )
            else:
                tier = "Strong"
                blurb = (
                    "Written curriculum for this unit looks solid on structure and "
                    "coverage. Call a spade a spade — only minor suggestions apply."
                )
        else:
            tier = "Developing"
            blurb = (
                "Enough structure is present to teach from, but gaps or continuity "
                "issues remain."
            )
    elif miss_rate >= 0.45:
        tier = "Weak"
        blurb = (
            "Many expected materials are MISSING. "
            "Blanks are the signal — not a failure of the auditor."
        )
    elif miss_rate <= 0.15:
        tier = "Strong"
        blurb = (
            "Written curriculum for this unit looks solid on structure and "
            "coverage. Call a spade a spade — only minor suggestions apply."
        )
    else:
        tier = "Developing"
        blurb = (
            "Enough structure is present to teach from, but gaps or continuity "
            "issues remain."
        )
    return {
        "tier": tier,
        "blurb": blurb,
        "missing": missing,
        "fulfilled": fulfilled,
        "miss_rate": round(miss_rate, 3),
        "hunter_rate": round(hunter_rate, 3) if hunter_rate is not None else None,
    }


# Singular labels for the per-row "Expected" cell. Not derived from
# synthesize._role_label()'s plural forms via .rstrip("s") — that mangles
# "Quizzes" -> "Quizze" since the plural isn't a plain "+s" (irregular -es).
# A one-row-per-role table reads oddly in the plural ("Quizzes: PRESENT" for
# one quiz), so this is a small, closed enum kept in sync with _role_label's
# key set by test_schema_validate.py.
ROLE_SINGULAR = {
    "lesson_plan": "Lesson plan",
    "lesson_content": "Lesson content / slide",
    "exit_ticket": "Exit ticket",
    "quiz": "Quiz",
    "answer_key": "Answer key",
    "rubric": "Rubric",
    "worksheet": "Worksheet",
    "project_work": "Project",
    "presentation": "Presentation",
    "game_activity": "Game / activity",
    "lab_activity": "Lab",
    "flex_day": "Flex day",
    "other": "Other material",
}


def render_unit_evidence_table(unit_id: str, ctx: ReportContext) -> str:
    """Binary present/absent table for one unit, sourced entirely from Layer 1's
    own per-slot findings — no model call, no restated prose.

    Design rationale (docs/REPORT-DELIVERY.md; Fenwick English / CMSi curriculum
    audit model; UNC FPG curriculum-audit binary-evidence scoring): this audit
    answers "is the expected artifact present, yes or no" — a factual match/
    mismatch question, not a graded quality judgment. Layer 1's FULFILLED/
    MISSING/DUPLICATE/CHECK_FAILED taxonomy already IS that binary answer, and
    each row's `reasoning` field already explains WHY in the model's own words
    (see layer1.py Phase 3). A narrative layer restating those six facts in
    prose adds words, not information — so this renders the ledger directly."""
    from synthesize import _role_label

    unit = ctx.manifest["units"].get(unit_id) or {}
    cal_rel = unit.get("calendar")
    day_order: list[str] = []
    if cal_rel:
        try:
            cal = load_yaml(ctx.root / cal_rel)
            day_order = [d["id"] for d in cal.get("days") or []]
        except Exception:
            day_order = []
    day_order.append(UNIT_SUPPORTING_SLOT)
    order_index = {d: i for i, d in enumerate(day_order)}

    rows = [f for f in ctx.findings if f.get("unit_id") == unit_id]
    rows.sort(key=lambda f: order_index.get(f.get("day_id"), len(day_order)))

    if not rows:
        return (
            "No Layer 1 findings for this unit yet — run "
            f"`python3 layer1.py --project {ctx.project_id} --only-unit {unit_id}`.\n"
        )

    lines = [
        "| Day | Expected | Status | Evidence |",
        "|---|---|---|---|",
    ]
    last_day = None
    for f in rows:
        day = _day_label(f.get("day_id"))
        day_cell = day if day != last_day else ""
        last_day = day
        role_key = f.get("role") or "other"
        role = ROLE_SINGULAR.get(role_key, _role_label(role_key))
        status = f.get("status", "")
        display = STATUS_DISPLAY.get(status, status)
        if status == "FULFILLED":
            evidence = _finding_titles(f.get("fulfilled_by"), ctx.title_map) or "—"
        elif status == "DUPLICATE":
            cands = _finding_titles(f.get("fulfilled_by"), ctx.title_map)
            evidence = f"{cands or 'multiple candidates'} — resolve which is canonical"
        elif status == "CHECK_FAILED":
            evidence = "Layer 1 check failed for this slot — re-run; not a confirmed gap."
        else:  # MISSING
            reasoning = (f.get("reasoning") or "").strip()
            evidence = reasoning if reasoning else "not in this folder"
        lines.append(f"| {day_cell} | {role} | **{display}** | {evidence} |")
    return "\n".join(lines) + "\n"


def render_teacher_packet(project_id: str, unit_id: str, ctx: ReportContext) -> str:
    """Unit-scoped punch list — no course YAG, no other units' systemic tables."""
    import json

    from synthesize import (
        _attention_bullet,
        _component_label,
        _role_label,
        _split_attention_for_champions,
    )

    unit = ctx.manifest["units"].get(unit_id)
    if not unit:
        raise KeyError(f"unit_id {unit_id!r} not in manifest")
    title = unit.get("title") or unit_id
    doc_ids = _unit_doc_ids(ctx.manifest, unit_id)

    rollup = next((u for u in ctx.agg["unit_rollup"] if u["unit_id"] == unit_id), None)
    fulfilled = rollup["fulfilled"] if rollup else 0
    missing = rollup["missing"] if rollup else 0
    duplicate = rollup["duplicate"] if rollup else 0
    match_n = rollup["match"] if rollup else 0
    mismatch_n = rollup["mismatch"] if rollup else 0

    missing_by_role: dict[str, int] = {}
    for f in ctx.findings:
        if f.get("unit_id") == unit_id and f.get("status") == "MISSING":
            role = f.get("role") or "other"
            missing_by_role[role] = missing_by_role.get(role, 0) + 1

    l2_path = ctx.root / "layer2" / "findings.json"
    l2_rows_unit: list[dict] = []
    if l2_path.is_file():
        l2_rows_unit = [
            r for r in json.loads(l2_path.read_text()) if r.get("doc_id") in doc_ids
        ]

    confirmed, worth = _split_attention_for_champions(ctx.agg)

    def _touches(d: dict) -> bool:
        return (
            d.get("doc_id") in doc_ids
            or d.get("parent_unit_id") == unit_id
            or d.get("matched_unit_id") == unit_id
        )

    confirmed_u = [d for d in confirmed if _touches(d)]
    worth_u = [d for d in worth if _touches(d)]

    pacing_u = _pacing_unit_row(project_id, unit_id)
    day_count = None
    cal_rel = unit.get("calendar")
    if cal_rel:
        try:
            day_count = len(load_yaml(ctx.root / cal_rel).get("days") or [])
        except Exception:
            day_count = None

    lines = [
        f"# Teacher packet — {title}",
        "",
        f"**Report id:** `teacher`  ",
        f"**Unit:** `{unit_id}`  ",
        f"**Dataset:** `{project_id}`  ",
        f"**Documents in this unit's folder list:** {len(doc_ids)}",
        "",
        "Punch list for **this unit only**. Course-wide Year-at-a-Glance, other "
        "clusters' gaps, and the full glossary live in the **first-pass** packet "
        "(`output/FIRST-PASS.md`).",
        "",
        "## 1. My unit at a glance",
        "",
        f"- **Title:** {title}",
    ]
    if day_count is not None:
        lines.append(f"- **Days on the unit calendar grid:** {day_count}")
    if pacing_u:
        start, end = pacing_u.get("start_date"), pacing_u.get("end_date")
        days = pacing_u.get("unit_length_days")
        if start or end:
            extra = f" ({days} days)" if days else ""
            lines.append(
                f"- **Dated placement (inferred):** {start or '?'} → {end or '?'}{extra}"
            )
    lines += [
        f"- **Elements confirmed in place:** {match_n}",
        f"- **Filing flags (elements):** {mismatch_n}",
        f"- **Expected materials found:** {fulfilled}  ·  **not in this folder:** {missing}  ·  "
        f"**possible duplicates:** {duplicate}",
    ]

    # Curriculum tier (Weak / Developing / Strong) from Path A + slot counts
    hunter_present = None
    path_a_coherent = None
    lp_json = ctx.root / "output" / "teachers" / unit_id / "LESSON-PLAN.json"
    if lp_json.is_file():
        try:
            lp = json.loads(lp_json.read_text(encoding="utf-8"))
            s = lp.get("summary") or {}
            hunter_present = s.get("hunter_core_present")
            path_a = lp.get("path_a") or {}
            # Coherence from project path_a findings if available
        except Exception:
            pass
    path_a_findings = ctx.root / "path_a" / "findings.json"
    if path_a_findings.is_file():
        try:
            pa = json.loads(path_a_findings.read_text(encoding="utf-8"))
            a3 = (pa.get("steps") or {}).get("A3") or {}
            a5 = (pa.get("steps") or {}).get("A5") or {}
            if hunter_present is None:
                hunter_present = a5.get("hunter_core_present")
            path_a_coherent = a3.get("status") == "COHERENT"
        except Exception:
            pass
    tier = compute_curriculum_tier(
        missing=missing,
        fulfilled=fulfilled,
        hunter_present=hunter_present,
        path_a_coherent=path_a_coherent,
    )
    lines += [
        f"- **Curriculum tier:** **{tier['tier']}** — {tier['blurb']}",
        "",
        "## Files in this unit (open these by name)",
        "",
        "These are the curriculum files listed for this unit. On Google Drive they live in "
        "this unit's folder under `files/` with the same readable names — no hash ids.",
        "",
    ]
    from synthesize import readable_title_from_filename

    unit_docs = unit.get("documents") or unit.get("source_files") or []
    if unit_docs:
        for rel in unit_docs:
            did = doc_id_from_filename(rel)
            human = ctx.title_map.get(did) or readable_title_from_filename(rel)
            lines.append(f"- **{human}**")
    else:
        lines.append("- *(No documents listed for this unit in the manifest.)*")

    lines += [
        "",
        "## 2. Materials I still need",
        "",
        "Compared to what this unit's day grid expects vs what was found in the uploaded files "
        "for **this unit**. Decide: author, pull from another drive, or drop from the S&S.",
        "",
    ]
    if missing_by_role:
        for role, n in sorted(missing_by_role.items(), key=lambda kv: -kv[1]):
            lines.append(
                f"- **{_role_label(role)}** — {n} expected slot(s) not in this folder"
            )
    elif missing == 0:
        lines.append(
            "- None — every expected role slot for this unit has something verified, "
            "or the day grid has no expectations."
        )
    else:
        lines.append(
            f"- **{missing}** expected slot(s) not in this folder "
            "(see `layer1/findings.json` for day/role detail)."
        )
    if duplicate:
        lines.append(
            f"- **Possible duplicates:** {duplicate} "
            "(same role satisfied more than once — check `layer1/findings.json`)."
        )

    lines += [
        "",
        "## 3. My lesson plans — template check",
        "",
        "Core parts: standards/objectives, materials/logistics, direct instruction, "
        "assessment checkpoint. Not a judgment of teaching quality.",
        "",
    ]
    incomplete = [r for r in l2_rows_unit if r.get("status") == "INCOMPLETE"]
    complete = [r for r in l2_rows_unit if r.get("status") == "COMPLETE"]
    if not l2_rows_unit:
        lines.append(
            "- No lesson plans for this unit were checked by Layer 2 yet "
            "(none confirmed as `lesson_plan`, or Layer 2 not run)."
        )
    else:
        lines.append(
            f"**Complete:** {len(complete)}  ·  **Needs template work:** {len(incomplete)}"
        )
        lines.append("")
        for r in incomplete:
            doc_title = ctx.title_map.get(r["doc_id"], r["doc_id"])
            missing_c = ", ".join(
                _component_label(c) for c in (r.get("components_missing") or [])
            )
            has_c = _present_component_labels(r.get("components_present") or [])
            lines.append(
                f"- **{doc_title}** — add: **{missing_c}**. Already has: {has_c}."
            )
        for r in complete:
            doc_title = ctx.title_map.get(r["doc_id"], r["doc_id"])
            lines.append(f"- **{doc_title}** — complete (core parts present).")

    lines += ["", "## 4. Files that may not belong here", ""]
    if not confirmed_u and not worth_u:
        lines.append("- No filing conflicts touching this unit.")
    else:
        if confirmed_u:
            lines += [f"### Confirm these ({len(confirmed_u)})", ""]
            lines += [_attention_bullet(d) for d in confirmed_u]
            lines.append("")
        if worth_u:
            lines += [f"### Worth a look / unconfirmed ({len(worth_u)})", ""]
            lines += [_attention_bullet(d) for d in worth_u]

    lines += [
        "",
        "## 5. What to ignore here",
        "",
        "- Course-wide YAG / pacing and other units → `output/FIRST-PASS.md` (report `first-pass`).",
        "- Overlap pair decisions that span many units → `layer1/REVIEW-QUEUE.md` (report `review-queue`).",
        "",
    ]
    return "\n".join(lines) + "\n"


def _l2_summary_for_unit(unit_id: str, ctx: ReportContext) -> str:
    """Short plain-text Layer 2 status, for feeding the teacher synthesis call —
    not for direct display (render_teacher_packet's own section handles that)."""
    from synthesize import _component_label

    doc_ids = _unit_doc_ids(ctx.manifest, unit_id)
    l2_path = ctx.root / "layer2" / "findings.json"
    if not l2_path.is_file():
        return ""
    import json as _json

    rows = [r for r in _json.loads(l2_path.read_text()) if r.get("doc_id") in doc_ids]
    if not rows:
        return ""
    lines = []
    for r in rows:
        title = ctx.title_map.get(r.get("doc_id") or "", r.get("doc_id"))
        if r.get("status") == "INCOMPLETE":
            missing = ", ".join(
                _component_label(c) for c in (r.get("components_missing") or [])
            )
            lines.append(f"- {title}: INCOMPLETE, missing {missing}")
        else:
            lines.append(f"- {title}: COMPLETE")
    return "\n".join(lines)


def write_teacher(ctx: ReportContext, unit_ids: list[str] | None = None) -> list[Path]:
    """Write TEACHER-PACKET.md for one unit or every unit in the manifest.

    Two-layer design (docs/REPORT-DELIVERY.md binary-evidence doctrine + Bet 0
    — compute is free, spend it where it adds signal):
      1. Deterministic evidence table (render_unit_evidence_table) — the
         inventory of record, sourced directly from Layer 1's own per-slot
         findings. Always present, zero model calls, cannot fail.
      2. ONE tight model call (report_delivery.run_teacher_synthesis) that
         reads THAT table and adds only what a table can't show: priority
         ordering and cross-row root cause. It is forbidden from restating
         rows — the old 3-phase Findings/Patterns/Recommendations chain
         restated the same six facts three times; this replaces that with a
         single synthesis pass over already-correct, already-cited data."""
    from report_delivery import merge_narrative_after_marker, run_teacher_synthesis

    units = unit_ids if unit_ids else sorted(ctx.manifest.get("units") or {})
    if not units:
        log("report teacher: no units in manifest — nothing written")
        return []

    cfg = None
    if ctx.delivery == DELIVERY_MODEL:
        from audit_lib import load_config

        cfg = load_config()

    written: list[Path] = []
    for uid in units:
        validate_slug_id(uid, "unit id")
        if uid not in ctx.manifest["units"]:
            raise KeyError(f"Unknown unit id {uid!r} — not in manifest")
        text = render_teacher_packet(ctx.project_id, uid, ctx)
        evidence_table = render_unit_evidence_table(uid, ctx)
        title = ctx.manifest["units"][uid].get("title") or uid

        synthesis_block = ""
        if ctx.delivery == DELIVERY_MODEL:
            raw_dir = ctx.out_dir / "raw" / "reports" / "teacher" / uid
            raw_dir.mkdir(parents=True, exist_ok=True)
            l2_summary = _l2_summary_for_unit(uid, ctx)
            day_labels = sorted(
                set(re.findall(r"Day \d+", evidence_table)),
                key=lambda s: int(s.split()[1]),
            )
            if "Unit supporting materials" in evidence_table:
                day_labels.append("unit-level supporting materials (no specific day)")
            synthesis, err = run_teacher_synthesis(
                cfg,
                project_id=ctx.project_id,
                unit_id=uid,
                unit_title=title,
                evidence_table_md=evidence_table,
                l2_summary=l2_summary,
                day_labels=day_labels,
                raw_dir=raw_dir,
            )
            if synthesis:
                synthesis_block = f"\n**Priority for this unit:** {synthesis}\n"
            elif err:
                synthesis_block = (
                    f"\n*(Synthesis note skipped: {err}. Table above is unaffected.)*\n"
                )

        narrative = (
            "## What this means for your unit\n\n"
            "Binary status per expected slot, evidence-cited. `PRESENT` cites the "
            "file that fulfills it; `MISSING` cites the model's own reason for "
            "rejecting every candidate it considered.\n\n"
            f"{evidence_table}"
            f"{synthesis_block}\n"
            "*Table is sourced directly from `layer1/findings.json` — every row "
            "traces to a specific finding, not restated prose.*\n"
        )
        text = merge_narrative_after_marker(text, "## 1. My unit at a glance", narrative)

        dest_dir = ctx.out_dir / "teachers" / uid
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Education-space Unit Plan plate (CTAT / NW ISD shape) — macro inventory
        # of what this unit HAS. Blank fields = not found. Separate from the
        # auditor packet written below.
        try:
            from unit_plan_fill import write_unit_plan_for_unit

            write_unit_plan_for_unit(
                ctx.project_id,
                uid,
                manifest=ctx.manifest,
                title_map=ctx.title_map,
                out_dir=dest_dir,
            )
            text += (
                "\n## Unit Plan (education-space inventory)\n\n"
                "A discovery-filled Unit Plan for this unit lives beside this packet "
                "as `UNIT-PLAN.md` / `UNIT-PLAN.pdf` — same CTAT / Northwest ISD "
                "fields curriculum writers use. Blank = not found in uploaded "
                "materials.\n"
            )
        except Exception as e:
            log(f"WARN: unit plan fill skipped for {uid}: {e}")

        # Daily-lesson STRUCTURE plate (test draft) — every core element listed;
        # blank = not found. Companion to UNIT-PLAN.md.
        try:
            from lesson_plan_fill import write_lesson_plan_for_unit

            write_lesson_plan_for_unit(
                ctx.project_id,
                uid,
                manifest=ctx.manifest,
                title_map=ctx.title_map,
                out_dir=dest_dir,
            )
            text += (
                "\n## Lesson Plan structure (test draft)\n\n"
                "A discovery-filled lesson-plan plate (test draft) lives beside this "
                "packet as `LESSON-PLAN.md` / `LESSON-PLAN.pdf`. Structure matrix "
                "first; blank = not found in uploaded materials.\n"
            )
        except Exception as e:
            log(f"WARN: lesson plan fill skipped for {uid}: {e}")

        path = dest_dir / "TEACHER-PACKET.md"
        atomic_write(path, text)
        try:
            from render_pdf import (
                render_lesson_plan_pdf,
                render_teacher_pdf,
                render_unit_plan_pdf,
            )

            render_teacher_pdf(ctx.project_id, uid)
            up_md = dest_dir / "UNIT-PLAN.md"
            if up_md.is_file():
                render_unit_plan_pdf(ctx.project_id, uid)
            lp_md = dest_dir / "LESSON-PLAN.md"
            if lp_md.is_file():
                render_lesson_plan_pdf(ctx.project_id, uid)
        except Exception as e:
            log(f"WARN: teacher PDF skipped for {uid}: {e}")
        written.append(path)
    log(f"report teacher → {len(written)} packet(s) under {ctx.out_dir / 'teachers'}")
    return written


@dataclass
class RegisteredReport:
    spec: ReportSpec
    write: Callable[[ReportContext, list[str] | None], list[Path]]


# Order here = order for --report all
REPORTS: dict[str, RegisteredReport] = {
    "first-pass": RegisteredReport(
        spec=ReportSpec(
            id="first-pass",
            status="implemented",
            summary="Course-level work packet (YAG, gaps, completeness, filing)",
            needs=("layer1", "layer2?", "pacing?"),
        ),
        write=write_first_pass,
    ),
    "dashboard": RegisteredReport(
        spec=ReportSpec(
            id="dashboard",
            status="implemented",
            summary="One-page heatmap for the same first-pass audience",
            needs=("layer1",),
        ),
        write=write_dashboard,
    ),
    "teacher": RegisteredReport(
        spec=ReportSpec(
            id="teacher",
            status="implemented",
            summary="Per-unit teacher punch list under output/teachers/<unit_id>/",
            scope="unit",
            needs=("layer1", "layer2?"),
        ),
        write=write_teacher,
    ),
    "review-queue": RegisteredReport(
        spec=ReportSpec(
            id="review-queue",
            status="implemented",
            summary="Refresh layer1/REVIEW-QUEUE.md overlap calibration queue",
            needs=("layer1",),
        ),
        write=write_review_queue,
    ),
}


def run_reports(
    project_id: str,
    report_ids: list[str],
    unit_ids: list[str] | None = None,
    delivery: str = DELIVERY_MODEL,
) -> Path:
    """Load context once, run each requested implemented report, return output dir."""
    validate_slug_id(project_id, "project id")
    ctx = load_report_context(project_id, delivery=delivery)
    persist_aggregate_stats(ctx)

    for rid in report_ids:
        if rid not in REPORTS:
            raise ValueError(f"report {rid!r} is not implemented")
        entry = REPORTS[rid]
        scope_units = unit_ids if entry.spec.scope == "unit" else None
        entry.write(ctx, scope_units)

    log(f"reports done ({', '.join(report_ids)}; delivery={delivery}) → {ctx.out_dir}")
    return ctx.out_dir


def format_list_reports() -> str:
    lines = [
        "# Crystallize reports",
        "",
        "| Id | Status | Scope | Summary |",
        "|----|--------|-------|---------|",
    ]
    for spec in list_report_specs():
        lines.append(f"| `{spec.id}` | {spec.status} | {spec.scope} | {spec.summary} |")
    lines += [
        "",
        "Implemented reports run with `--report all`. Planned ids are listed only.",
        "",
        "Delivery: `--delivery model` (default) runs hybrid curriculum-audit narrative",
        "for `first-pass` and `teacher`. `--delivery code` is tables-only (fast).",
        "`dashboard` and `review-queue` are always code-only.",
        "",
        "Examples:",
        "```",
        "python3 synthesize.py --project dallas-career-2026 --report first-pass",
        "python3 synthesize.py --project dallas-career-2026 --report teacher --unit engineering",
        "python3 synthesize.py --project dallas-career-2026 --report all --delivery code",
        "```",
        "",
    ]
    return "\n".join(lines)
