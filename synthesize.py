#!/usr/bin/env python3
"""
synthesize.py — cross-unit synthesis for a curriculum-reviser / champion work
packet, sourced from Layer 1's bucket-ledger.json + findings.json (and Layer 2
completeness + rollup pacing when present).

Reads layer1 (+ layer2 + pacing-plan) -> GLOBAL-AUDIT.md + DASHBOARD.md.
Auditor-only: findings and patterns, no curriculum fixes. The report is framed
around teacher deliverables (YAG, pacing, S&S gaps, lesson-plan completeness,
filing/alignment) — see docs/CHAMPION-REVIEW-MAP.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

from audit_lib import (
    atomic_write,
    doc_id_from_filename,
    is_corroborated,
    load_config,
    load_yaml,
    log,
    project_dir,
)

AUDITOR_RULES = """
You are a curriculum audit synthesizer. READ-ONLY.
- Report cross-unit patterns, systemic gaps, prioritized findings (max 20).
- NEVER suggest lesson content, assessments, or rewrites.
- Plain language for curriculum directors.
"""

# Plain-language definitions for every status this pipeline can produce — written
# directly into GLOBAL-AUDIT.md so a curriculum director can interpret the report
# without an agent/engineer explaining it to them each time (the gap this file was
# rewritten to close — see docs/roadmap.md "Full-corpus run + MISMATCH signal
# refinement" and docs/BETS.md Bet 12).
STATUS_GLOSSARY = [
    (
        "MATCH",
        "This content's own words agree with where it's filed. No action needed.",
    ),
    (
        "MISMATCH",
        "This content's own words name a DIFFERENT unit than where it's filed. "
        "The real signal this whole system exists to produce — but check the "
        "corroboration count and excerpt before acting; see 'Needs your attention' below.",
    ),
    (
        "CROSS_REFERENCE",
        "An overview/hub document (e.g. a district-wide career-cluster survey) mentions "
        "another unit by name — that's the hub doing its job, not a misfile.",
    ),
    (
        "EXPECTED_OVERLAP",
        "A human reviewer already confirmed this unit-pair legitimately, expectedly "
        "overlaps (e.g. an Architecture & Construction lesson teaching engineering "
        "design methodologies). Not a filing error — see manifest.yaml known_overlaps.",
    ),
    ("ORPHAN", "This document isn't linked from any unit in the manifest at all."),
    (
        "UNVERIFIED",
        "This content doesn't restate its own unit/day in its own words, so placement "
        "is trusted from the manifest only, not independently confirmed. This is normal "
        "and expected for most body content — not a red flag on its own.",
    ),
    (
        "MISSING",
        "An expected artifact for a specific day (e.g. a lesson plan, worksheet, rubric) was not found anywhere in the corpus.",
    ),
    (
        "DUPLICATE",
        "Two or more near-identical claims independently satisfy the same day/role — "
        "likely the same content counted twice, not two distinct pieces of evidence.",
    ),
    (
        "FULFILLED",
        "An expected day-level artifact was found and verified to actually function as that role, not just labeled as one.",
    ),
]


def readable_title_from_filename(name: str) -> str:
    """A curriculum document's stored name is a machine artifact — either
    `doc_<12-hex-hash>_Career_Cluster_-_Lesson_Plan.txt` (Dallas: hash prefix +
    sanitized title) or `unit-2-pathways-careers.txt` (Region10: slugged path).
    A director reading the report needs the human title, not either of those.

    Recover it by mirroring how Layer 0/1 derive doc_id (audit_lib.doc_id_from_filename):
    drop the extension, drop the `doc_<hash>_` prefix if present, and turn the
    underscores the sanitizer inserted back into spaces. This is display-only — the
    stable doc_id hash still travels alongside as a secondary reference so a finding
    is always traceable back to the exact file on disk."""
    base = os.path.basename(name)
    base = re.sub(r"\.[A-Za-z0-9]+$", "", base)  # strip extension
    base = re.sub(r"^doc_[a-f0-9]+_", "", base)  # strip doc_<hash>_ prefix
    base = re.sub(r"_+", " ", base).strip()  # underscores -> spaces
    base = re.sub(r"\s{2,}", " ", base)  # collapse runs
    return base or os.path.basename(name)


def build_doc_title_map(manifest: dict) -> dict[str, str]:
    """doc_id -> human-readable document title, built from manifest.yaml the same
    way layer1.build_parent_link_map() builds doc_id -> unit_id. One shared source
    of truth for turning hashes into names, reused by the PDF renderer.

    Disambiguates same-unit title collisions (e.g. two source files both named
    "Financial Literacy") with a " (version N)" suffix in manifest order — without
    this, a teacher reading two different findings that both cite "Financial
    Literacy" cannot tell which physical file is which (see docs/BETS.md citation
    fidelity discussion; a citation that cannot be told apart from another is not
    a real citation)."""
    mapping: dict[str, str] = {}
    for unit in manifest.get("units", {}).values():
        raw_titles: dict[str, str] = {}
        order: list[str] = []
        for doc_path in unit.get("documents", unit.get("source_files", [])):
            did = doc_id_from_filename(doc_path)
            raw_titles[did] = readable_title_from_filename(doc_path)
            order.append(did)
        counts: dict[str, int] = {}
        for did in order:
            counts[raw_titles[did]] = counts.get(raw_titles[did], 0) + 1
        seen: dict[str, int] = {}
        for did in order:
            title = raw_titles[did]
            if counts[title] > 1:
                seen[title] = seen.get(title, 0) + 1
                mapping[did] = f"{title} (version {seen[title]})"
            else:
                mapping[did] = title
    return mapping


def load_layer1_data(project_id: str) -> tuple[list[dict], list[dict]]:
    root = project_dir(project_id)
    l1_dir = root / "layer1"
    bucket_path = l1_dir / "bucket-ledger.json"
    findings_path = l1_dir / "findings.json"
    if not bucket_path.is_file():
        raise FileNotFoundError(
            f"No Layer 1 output at {bucket_path} — run `python3 layer1.py --project {project_id}` first."
        )
    bucket_rows = json.loads(bucket_path.read_text())
    findings = json.loads(findings_path.read_text()) if findings_path.is_file() else []
    return bucket_rows, findings


def _group_mismatches_by_document(
    mismatch_rows: list[dict], title_map: dict[str, str], unit_titles: dict[str, str]
) -> list[dict]:
    """Collapse per-element MISMATCH rows into one finding per document — the unit
    of a director's actual decision. A single misfiled lesson plan decomposed into
    10 instructional elements was surfacing as 10 near-identical alarming rows
    (e82d217defad-e1..e10, all "Career Cluster filed, Hospitality reads"); a director
    needs to see "this ONE document looks misfiled," once, named plainly.

    For each document we keep the dominant self-declared target, the strongest
    corroboration count seen among its elements, one representative excerpt, and
    whether ANY element cleared the corroboration bar (that promotes the whole
    document to high-confidence — the conflict is real somewhere in it)."""
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in mismatch_rows:
        by_doc[r["doc_id"]].append(r)

    docs = []
    for doc_id, grp in by_doc.items():
        # Dominant target unit across this document's disagreeing elements.
        target = Counter(r["matched_unit_id"] for r in grp).most_common(1)[0][0]
        target_rows = [r for r in grp if r["matched_unit_id"] == target]
        rep = max(
            target_rows,
            key=lambda r: (r.get("mismatch_corroboration") or {}).get(
                "same_target_count", 0
            ),
        )
        corr = rep.get("mismatch_corroboration") or {}
        excerpt = next(
            (r["excerpt"] for r in target_rows if (r.get("excerpt") or "").strip()),
            (rep.get("excerpt") or ""),
        )
        # The model's one-sentence "why this reads as the target unit" (Phase 1
        # reasoning). Prefer the representative element's, else the first target row
        # that has one; may be absent on ledgers built before reasoning was added.
        reasoning = next(
            (
                r.get("reasoning")
                for r in [rep, *target_rows]
                if (r.get("reasoning") or "").strip()
            ),
            "",
        )
        parent = rep["parent_link_unit_id"]
        docs.append(
            {
                "doc_id": doc_id,
                "title": title_map.get(doc_id, doc_id),
                "parent_unit_id": parent,
                "parent_title": unit_titles.get(parent, parent),
                "matched_unit_id": target,
                "matched_title": unit_titles.get(target, target),
                "element_count": len(grp),
                "same_target_count": corr.get("same_target_count", 0),
                "total_self_declarations_in_doc": corr.get(
                    "total_self_declarations_in_doc", 0
                ),
                "excerpt": (excerpt or "")[:220].strip().replace("\n", " "),
                "reasoning": (reasoning or "").strip().replace("\n", " "),
                "high_confidence": any(is_corroborated(r) for r in grp),
                # True if an independent recheck ran on any of this doc's MISMATCH
                # elements and did NOT reproduce the finding — surfaced so the reader
                # knows the two passes disagreed (Bet 5), not hidden.
                "recheck_disagreed": any(
                    r.get("recheck_performed") and r.get("recheck_agreed") is False
                    for r in grp
                ),
            }
        )
    # Strongest signal first: high-confidence docs, then by agreement strength.
    docs.sort(
        key=lambda d: (not d["high_confidence"], -d["same_target_count"], d["title"])
    )
    return docs


def aggregate_layer1(
    bucket_rows: list[dict], findings: list[dict], manifest: dict
) -> dict:
    """Build structured stats without models — same deterministic-first discipline
    as the doc-level version this replaces (model enrichment, if used, only rewrites
    the executive-summary prose afterward; every number/citation here is pure code)."""
    status_counts = Counter(r["match_status"] for r in bucket_rows)
    documents_judged = len({r["doc_id"] for r in bucket_rows})
    unit_titles = {uid: u.get("title", uid) for uid, u in manifest["units"].items()}
    title_map = build_doc_title_map(manifest)

    mismatch_rows = [r for r in bucket_rows if r["match_status"] == "MISMATCH"]
    # Document-level (not element-level) attention findings — see _group_mismatches_by_document.
    mismatch_docs = _group_mismatches_by_document(mismatch_rows, title_map, unit_titles)
    mismatch_docs_high = [d for d in mismatch_docs if d["high_confidence"]]
    mismatch_docs_low = [d for d in mismatch_docs if not d["high_confidence"]]

    # Pending human-in-the-loop calibration (docs/BETS.md Bet 12) — distinct
    # unit-pairs still awaiting a known_overlaps decision, same pair grouping
    # layer1.py's build_review_queue_md() uses, kept in sync deliberately: a
    # pair counted as pending here should be a pair that also shows up in
    # layer1/REVIEW-QUEUE.md, never silently double-counted or missed.
    review_pairs = {
        frozenset((r["parent_link_unit_id"], r["matched_unit_id"]))
        for r in mismatch_rows
    }

    finding_status_counts = Counter(f["status"] for f in findings)
    by_unit_bucket: dict[str, Counter] = defaultdict(Counter)
    for r in bucket_rows:
        by_unit_bucket[r.get("final_unit_id") or "(unlinked)"][r["match_status"]] += 1
    by_unit_findings: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        by_unit_findings[f["unit_id"]][f["status"]] += 1

    unit_rollup = []
    for uid in sorted(set(by_unit_bucket) | set(by_unit_findings)):
        bc, fc = by_unit_bucket.get(uid, Counter()), by_unit_findings.get(
            uid, Counter()
        )
        unit_rollup.append(
            {
                "unit_id": uid,
                "title": unit_titles.get(uid, uid),
                "match": bc.get("MATCH", 0),
                "mismatch": bc.get("MISMATCH", 0),
                "fulfilled": fc.get("FULFILLED", 0),
                "missing": fc.get("MISSING", 0),
                "duplicate": fc.get("DUPLICATE", 0),
            }
        )

    # Systemic: a role missing in 3+ DISTINCT units (not 3+ findings — a role
    # missing on every day of one unit must not count as "systemic" on its own).
    missing_units_by_role: dict[str, set[str]] = defaultdict(set)
    for f in findings:
        if f["status"] == "MISSING":
            missing_units_by_role[f["role"]].add(f["unit_id"])
    systemic = sorted(
        (
            {"role": role, "unit_count": len(units)}
            for role, units in missing_units_by_role.items()
            if len(units) >= 3
        ),
        key=lambda x: -x["unit_count"],
    )

    return {
        "elements_judged": len(bucket_rows),
        "documents_judged": documents_judged,
        "status_counts": dict(status_counts),
        # Document-level attention findings (one entry per misfiled document, not
        # per element) — see _group_mismatches_by_document. These are small,
        # JSON-serializable dicts, so unlike the old raw-row lists they are safe to
        # persist into aggregate-stats.json / the regression golden.
        "mismatch_docs_high": mismatch_docs_high,
        "mismatch_docs_low": mismatch_docs_low,
        "mismatch_element_count": status_counts.get("MISMATCH", 0),
        "review_queue_pending_pairs": len(review_pairs),
        "finding_status_counts": dict(finding_status_counts),
        "systemic_missing": systemic[:10],
        "unit_rollup": unit_rollup,
    }


def load_layer2_data(project_id: str) -> list[dict]:
    """Layer 2 findings, or [] if Layer 2 hasn't run yet (older project output, or
    a --skip-layer01 run). Synthesize must degrade gracefully here, not crash —
    Layer 2 is a strictly additive enrichment on top of Layer 1's report, never
    a hard dependency (see docs/BETS.md note under Bet 10/11)."""
    path = project_dir(project_id) / "layer2" / "findings.json"
    return json.loads(path.read_text()) if path.is_file() else []


def aggregate_layer2(rows: list[dict], title_map: dict[str, str]) -> dict:
    """Structured stats for the 'Lesson structural completeness' section — same
    deterministic-first, JSON-serializable discipline as aggregate_layer1(every
    field here is safe to persist into aggregate-stats.json / a regression
    golden)."""
    documents_judged = len(rows)
    incomplete = [r for r in rows if r["status"] == "INCOMPLETE"]
    complete_count = documents_judged - len(incomplete)

    incomplete_docs = sorted(
        (
            {
                "doc_id": r["doc_id"],
                "title": title_map.get(r["doc_id"], r["doc_id"]),
                "role": r["role"],
                "components_missing": r["components_missing"],
                "components_present": [c["component"] for c in r["components_present"]],
                # One representative citation from whatever IS present, so an
                # absence finding still anchors to real, quoted evidence rather
                # than a bare claim (Bet 5: auditor-only, never invent).
                "sample_excerpt": next(
                    (
                        c["excerpt"]
                        for c in r["components_present"]
                        if (c.get("excerpt") or "").strip()
                    ),
                    "",
                )[:220]
                .strip()
                .replace("\n", " "),
            }
            for r in incomplete
        ),
        key=lambda d: (d["title"], d["role"]),
    )

    # Systemic: a component missing across 3+ DISTINCT documents (mirrors Layer 1's
    # missing_units_by_role threshold in aggregate_layer1) — a scope-and-sequence
    # pattern worth reviewing once, not one document's isolated problem.
    missing_docs_by_component: dict[str, set[str]] = defaultdict(set)
    for r in incomplete:
        for component in r["components_missing"]:
            missing_docs_by_component[component].add(r["doc_id"])
    systemic = sorted(
        (
            {"component": c, "doc_count": len(docs)}
            for c, docs in missing_docs_by_component.items()
            if len(docs) >= 3
        ),
        key=lambda x: -x["doc_count"],
    )

    return {
        "documents_judged": documents_judged,
        "complete_count": complete_count,
        "incomplete_count": len(incomplete),
        "incomplete_docs": incomplete_docs,
        "systemic_missing_components": systemic,
    }


def render_glossary_md() -> str:
    lines = ["| Status | What it means |", "|---|---|"]
    lines += [f"| **{status}** | {meaning} |" for status, meaning in STATUS_GLOSSARY]
    return "\n".join(lines)


def render_dashboard(project_id: str, agg: dict, agg2: dict | None = None) -> str:
    confirmed, worth = _split_attention_for_champions(agg)
    lines = [
        "# Curriculum Review Dashboard",
        "",
        f"**Dataset:** {project_id}",
        "",
        "## At a glance (work-session)",
        "",
        "| Focus | Count |",
        "|-------|-------|",
        f"| Documents in folder | {agg['documents_judged']} |",
        f"| Filing conflicts to confirm | {len(confirmed)} |",
        f"| Filing flags (weaker / unconfirmed) | {len(worth)} |",
        f"| Expected materials not in this folder | {agg['finding_status_counts'].get('MISSING', 0)} |",
        f"| Possible duplicate materials | {agg['finding_status_counts'].get('DUPLICATE', 0)} |",
        f"| Overlap pairs awaiting your decision | {agg['review_queue_pending_pairs']} |",
    ]
    if agg2 and agg2["documents_judged"]:
        lines.append(
            f"| Lesson plans needing template work | {agg2['incomplete_count']} of {agg2['documents_judged']} |"
        )
    lines += [
        "",
        "## Unit heatmap",
        "",
        "| Unit | Confirmed | Misfiled | Found | Not in folder | Duplicates |",
        "|------|-----------|----------|-------|---------------|------------|",
    ]
    for u in sorted(
        agg["unit_rollup"],
        key=lambda x: (-x["mismatch"], -x["duplicate"], -x["missing"]),
    ):
        bar = "🔴" if u["mismatch"] > 0 else ("🟡" if u["duplicate"] > 0 else "🟢")
        lines.append(
            f"| {bar} {u['title']} | {u['match']} | {u['mismatch']} | {u['fulfilled']} | {u['missing']} | {u['duplicate']} |"
        )

    lines.extend(["", "## Scope gaps across 3+ units", ""])
    if agg["systemic_missing"]:
        for i, p in enumerate(agg["systemic_missing"][:5], 1):
            lines.append(
                f"{i}. **{_role_label(p['role'])}** — missing in **{p['unit_count']}** units"
            )
    else:
        lines.append("- No pattern reached the 3+ unit threshold.")

    return "\n".join(lines) + "\n"


def _verdict_sentence(agg: dict) -> str:
    """One plain-English sentence a director can read in isolation and act on."""
    n_docs = agg["documents_judged"]
    n_misfiled = len(agg["mismatch_docs_high"]) + len(agg["mismatch_docs_low"])
    n_missing = agg["finding_status_counts"].get("MISSING", 0)
    if n_misfiled == 0 and n_missing == 0:
        return (
            f"All {n_docs} documents audited appear to be filed where they belong, and no "
            "expected materials are missing. No action needed."
        )
    parts = []
    if n_misfiled:
        hi = len(agg["mismatch_docs_high"])
        parts.append(
            f"**{n_misfiled} of {n_docs} documents look misfiled** "
            f"({hi} strongly, worth checking first)"
        )
    else:
        parts.append(f"all {n_docs} documents appear correctly filed")
    if n_missing:
        parts.append(
            f"**{n_missing} expected materials appear to be missing** across the units"
        )
    return "Bottom line: " + ", and ".join(parts) + ". Details below."


def _attention_bullet(d: dict) -> str:
    """One misfiled DOCUMENT, plain language, real title, one representative quote."""
    agree = ""
    same, tot = d["same_target_count"], d["total_self_declarations_in_doc"]
    if tot:
        count_phrase = "all " + str(tot) if same == tot else f"{same} of {tot}"
        agree = f" ({count_phrase} of its self-describing parts point to {d['matched_title']})"
    why = f"\n  - Why it reads that way: {d['reasoning']}" if d.get("reasoning") else ""
    excerpt = d["excerpt"]
    quote = f'\n  - Evidence (its own words): "{excerpt}"' if excerpt else ""
    recheck = (
        "\n  - Note: an independent second read did not reproduce this — treat as unconfirmed."
        if d.get("recheck_disagreed")
        else ""
    )
    return (
        f"- **{d['title']}** — filed under **{d['parent_title']}**, but its own wording "
        f"reads as **{d['matched_title']}**{agree}. "
        f"Suggested check: confirm whether this document belongs in {d['matched_title']}. "
        f"(id `{d['doc_id']}`, {d['element_count']} element(s)){why}{quote}{recheck}"
    )


def _layer2_bullet(d: dict) -> str:
    """One document Layer 1 confirmed anchors a role, but Layer 0's own elements
    show it's missing an expected internal part — e.g. a lesson plan with no
    standards/objectives section anywhere in it."""
    present = (
        f" Has: {', '.join(d['components_present'])}."
        if d["components_present"]
        else ""
    )
    quote = (
        f'\n  - Evidence of what IS present (its own words): "{d["sample_excerpt"]}"'
        if d["sample_excerpt"]
        else ""
    )
    return (
        f"- **{d['title']}** (functioning as `{d['role']}`) is missing "
        f"**{', '.join(d['components_missing'])}**.{present} "
        f"(id `{d['doc_id']}`){quote}"
    )


def _split_attention_for_champions(agg: dict) -> tuple[list[dict], list[dict]]:
    """Trust-first split for teacher-facing packets: a high-confidence MISMATCH the
    independent recheck did NOT reproduce is demoted to 'worth a look' so champions
    don't burn a work session on an unconfirmed flag (Carrasco-style cases)."""
    confirmed = [d for d in agg["mismatch_docs_high"] if not d.get("recheck_disagreed")]
    worth = list(agg["mismatch_docs_low"]) + [
        d for d in agg["mismatch_docs_high"] if d.get("recheck_disagreed")
    ]
    return confirmed, worth


def _load_pacing_brief(project_id: str) -> dict | None:
    """Dated YAG / pacing summary for the champion 'Year-at-a-Glance' section.
    Returns None when rollup hasn't run or there is no school-calendar spine."""
    path = project_dir(project_id) / "pacing-plan.yaml"
    if not path.is_file():
        return None
    pacing = load_yaml(path)
    summary = pacing.get("summary") or {}
    yag = pacing.get("year_at_a_glance") or {}
    columns = yag.get("grading_period_columns") or []
    return {
        "school_year": pacing.get("school_year") or "",
        "district": pacing.get("district") or "",
        "mode": pacing.get("mode") or "sequential",
        "disclaimer": (pacing.get("disclaimer") or "").strip(),
        "units_placed": summary.get("units_placed", 0),
        "units_total": summary.get("units_total", 0),
        "days_used": summary.get("instructional_days_consumed", 0),
        "days_available": summary.get("instructional_days_available", 0),
        "days_remaining": summary.get("instructional_days_remaining", 0),
        "grading_periods": [
            {
                "label": c.get("label") or c.get("id"),
                "begin": c.get("begin"),
                "end": c.get("end"),
                "unit_count": len(c.get("unit_ids") or []),
            }
            for c in columns
        ],
        "has_school_calendar": (
            project_dir(project_id) / "school-calendar.yaml"
        ).is_file(),
    }


def _role_label(role: str) -> str:
    """Champion-facing names for artifact roles (still the same closed enum)."""
    return {
        "lesson_plan": "Lesson plans",
        "lesson_content": "Lesson content / slides",
        "exit_ticket": "Exit tickets",
        "quiz": "Quizzes",
        "answer_key": "Answer keys",
        "rubric": "Rubrics",
        "worksheet": "Worksheets",
        "project_work": "Projects",
        "presentation": "Presentations",
        "game_activity": "Games / activities",
        "lab_activity": "Labs",
        "flex_day": "Flex days",
        "other": "Other materials",
    }.get(role, role.replace("_", " ").title())


def _component_label(component: str) -> str:
    return {
        "standards_objectives": "standards / objectives (TEKS language)",
        "logistics_materials": "materials / logistics",
        "direct_instruction": "direct instruction / explain",
        "assessment_checkpoint": "assessment / check for understanding",
        "hook_engagement": "hook / engage",
        "guided_practice": "guided practice",
        "independent_practice": "independent practice",
        "reflection_closure": "reflection / closure",
    }.get(component, component.replace("_", " "))


def render_global_audit_deterministic(
    project_id: str,
    agg: dict,
    agg2: dict | None = None,
    pacing: dict | None = None,
) -> str:
    """Champion / curriculum-reviser work packet — same underlying findings as the
    old engineer-facing audit, reorganized around the deliverables teachers are
    actually asked to produce (YAG, pacing, gap lists, lesson-plan completeness,
    filing/alignment). See docs/CHAMPION-REVIEW-MAP.md."""
    agg2 = agg2 or {
        "documents_judged": 0,
        "complete_count": 0,
        "incomplete_count": 0,
        "incomplete_docs": [],
        "systemic_missing_components": [],
    }
    confirmed, worth = _split_attention_for_champions(agg)
    n_missing = agg["finding_status_counts"].get("MISSING", 0)
    n_fulfilled = agg["finding_status_counts"].get("FULFILLED", 0)
    n_dup = agg["finding_status_counts"].get("DUPLICATE", 0)

    lines = [
        "# Curriculum Review Work Packet",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Documents in the shared folder:** {agg['documents_judged']}  ",
        f"**Units in scope:** {len(agg['unit_rollup'])}",
        "",
        "This is a **read-only structure check** of what is already in the curriculum "
        "folder, compared to the district instructional calendar and each unit's day "
        "grid. It does **not** write lessons, syllabi, or assessments — those stay with "
        "you. Use it to prep a work session: what to bless as a YAG/pacing draft, what "
        "materials the calendar expects but the folder lacks, which lesson plans are "
        "missing core parts, and which files may be misfiled.",
        "",
        "## 1. Work-session agenda (start here)",
        "",
    ]

    agenda: list[str] = []
    if pacing and pacing.get("mode") == "dated":
        agenda.append(
            f"**Year-at-a-Glance / pacing draft** — review the dated map "
            f"({pacing['days_used']} of {pacing['days_available']} instructional days used). "
            "Bless, adjust unit lengths, or note where the official S&S should differ."
        )
    elif pacing:
        agenda.append(
            "**Year-at-a-Glance / pacing** — no district school calendar was found, so "
            "dates are sequential only. Add `school-calendar.yaml` (DISD spine is in "
            "`shared/disd-school-calendar/`) and re-run rollup for a dated YAG."
        )
    else:
        agenda.append(
            "**Year-at-a-Glance / pacing** — run rollup first "
            "(`python3 rollup.py --project … --force`) so a draft map appears here."
        )
    if n_missing:
        agenda.append(
            f"**Scope & sequence gaps** — {n_missing} expected material slot(s) have nothing "
            "in the folder yet (calendar/S&S expectation vs. what was uploaded). Decide "
            "what to author, what to drop from the day grid, or what still lives elsewhere."
        )
    if agg2["incomplete_count"]:
        agenda.append(
            f"**Lesson plan templates** — {agg2['incomplete_count']} lesson plan(s) are "
            "missing one or more core parts (standards, materials, instruction, assessment). "
            "Use section 4 as a punch list for template refinement."
        )
    if confirmed:
        agenda.append(
            f"**Filing / cross-course alignment** — {len(confirmed)} document(s) look "
            "strongly misfiled (own words disagree with where they're stored). Confirm "
            "moves or mark as expected overlap."
        )
    if worth:
        agenda.append(
            f"**Quick scan** — {len(worth)} weaker or unconfirmed filing flag(s); don't "
            "block the session on these unless something jumps out."
        )
    if agg["review_queue_pending_pairs"]:
        agenda.append(
            f"**Overlap decisions** — {agg['review_queue_pending_pairs']} subject-pair(s) "
            "waiting on a one-time human call (`layer1/REVIEW-QUEUE.md`)."
        )
    if not agenda:
        agenda.append(
            "No structural blockers — use the session for content refinement."
        )
    lines += [f"{i}. {item}" for i, item in enumerate(agenda, 1)]

    # --- Deliverable: YAG / pacing ---
    lines += ["", "## 2. Year-at-a-Glance & pacing guide (draft)", ""]
    if pacing and pacing.get("mode") == "dated":
        lines += [
            f"**District spine:** {pacing.get('district') or 'district calendar'} · "
            f"school year **{pacing.get('school_year') or '—'}**  ",
            f"**Status:** inferred draft from unit day grids + `school-calendar.yaml` — "
            "**not** the official YAG until your team blesses it.",
            "",
            f"- Units placed on the calendar: **{pacing['units_placed']}** / {pacing['units_total']}",
            f"- Instructional days used: **{pacing['days_used']}** / {pacing['days_available']} "
            f"({pacing['days_remaining']} remaining)",
            "",
            "| Grading period | Dates | Units starting in this window |",
            "|----------------|-------|-------------------------------|",
        ]
        for gp in pacing["grading_periods"]:
            lines.append(
                f"| {gp['label']} | {gp['begin']} → {gp['end']} | {gp['unit_count']} |"
            )
        lines += [
            "",
            "Full day-by-day unit timeline: `output/03-year-calendar-map.md`.",
        ]
        if pacing.get("disclaimer"):
            lines += ["", f"> {pacing['disclaimer']}"]
    elif pacing:
        lines.append(
            "Pacing exists but is **sequential** (no dated district spine). Copy the DISD "
            "calendar from `shared/disd-school-calendar/` into this project and re-run rollup."
        )
    else:
        lines.append(
            "No `pacing-plan.yaml` yet — rollup has not been run for this dataset."
        )

    # --- Deliverable: gaps / S&S ---
    lines += [
        "",
        "## 3. Scope & sequence gaps (calendar expectation vs. folder)",
        "",
        "These counts compare **what each unit's day grid says should exist** "
        "(lesson plan, exit ticket, rubric, …) with **what was found in the uploaded "
        "files**. A high number usually means the calendar is ambitious relative to "
        "this folder — not that teachers failed. Decide per gap: author it, pull it "
        "from another drive, or remove it from the official S&S/day grid.",
        "",
        f"**Found & verified:** {n_fulfilled}  ·  **Not in this folder:** {n_missing}  ·  "
        f"**Possible duplicates:** {n_dup}",
        "",
    ]
    if agg["systemic_missing"]:
        lines += [
            "**Patterns across 3+ units** (fix the S&S once, not unit-by-unit):",
            "",
        ]
        for i, p in enumerate(agg["systemic_missing"], 1):
            lines.append(
                f"{i}. **{_role_label(p['role'])}** — missing in **{p['unit_count']}** units"
            )
        lines.append("")
    lines += [
        "| Unit | Materials found | Not in folder | Possible duplicates |",
        "|------|-----------------|---------------|---------------------|",
    ]
    for u in sorted(agg["unit_rollup"], key=lambda x: (-x["missing"], x["title"])):
        lines.append(
            f"| {u['title']} | {u['fulfilled']} | {u['missing']} | {u['duplicate']} |"
        )

    # --- Deliverable: lesson plan template completeness ---
    lines += [
        "",
        "## 4. Lesson plan template completeness",
        "",
        "For documents already confirmed as lesson plans, this checks whether core "
        "**parts** are present in the file itself: standards/objectives, materials, "
        "direct instruction, and an assessment checkpoint. It does **not** score "
        "whether the lesson is engaging or pedagogically strong.",
        "",
    ]
    if agg2["documents_judged"] == 0:
        lines.append(
            "No lesson plans were confirmed for completeness yet (Layer 2 empty or no "
            "`lesson_plan` fulfillments)."
        )
    else:
        lines += [
            f"**Complete:** {agg2['complete_count']}  ·  **Needs template work:** "
            f"{agg2['incomplete_count']}  (of {agg2['documents_judged']} checked)",
            "",
        ]
        if agg2["incomplete_docs"]:
            for d in agg2["incomplete_docs"]:
                missing = ", ".join(
                    _component_label(c) for c in d["components_missing"]
                )
                has = (
                    ", ".join(_component_label(c) for c in d["components_present"])
                    or "none of the core four"
                )
                lines.append(
                    f"- **{d['title']}** — add: **{missing}**. Already has: {has}."
                )
        else:
            lines.append("- Every checked lesson plan has the core parts.")

    # --- Deliverable: alignment / filing ---
    lines += [
        "",
        "## 5. Filing & cross-course alignment",
        "",
        "Documents whose **own wording** names a different unit than the folder they "
        "live in. Strongest cases first — often a reused template or a file saved in "
        "the wrong cluster folder.",
        "",
    ]
    if not confirmed and not worth:
        lines.append("No filing conflicts detected.")
    else:
        if confirmed:
            lines += [
                f"### Confirm these ({len(confirmed)})",
                "",
            ]
            lines += [_attention_bullet(d) for d in confirmed]
            lines.append("")
        if worth:
            lines += [
                f"### Worth a look / unconfirmed ({len(worth)})",
                "",
                "Weaker agreement, or an independent second read did not reproduce the flag.",
                "",
            ]
            lines += [_attention_bullet(d) for d in worth]
            lines.append("")
        if agg["review_queue_pending_pairs"]:
            lines += [
                f"### Expected overlap decisions ({agg['review_queue_pending_pairs']} pairs)",
                "",
                "Some conflicts may be legitimate cross-discipline overlap. See "
                "`layer1/REVIEW-QUEUE.md` — one decision per subject-pair covers future files.",
            ]

    # --- Explicit non-goals ---
    lines += [
        "",
        "## 6. What this packet does **not** do",
        "",
        "- Write or rewrite lesson plans, assessments, rubrics, or syllabi",
        "- Insert videos or partner curriculum modules for you",
        "- Judge TEKS / CCMR / industry alignment as pass/fail (it can only show when "
        "standards language is present in a file)",
        "- Replace collaborative work sessions, PD, or compensation tracking",
        "",
        "Your team still owns content quality and the official YAG, syllabus, and S&S.",
        "",
        "## Appendix — status glossary",
        "",
        render_glossary_md(),
        "",
        "## Appendix — how this was produced",
        "",
        "Every document was read in full and broken into cited instructional elements; "
        "placement was checked against the manifest and day grid without showing the "
        "model the filing answer key; expected materials were verified by function; "
        "lesson plans were checked for core parts with no extra model calls. "
        "Details: `docs/CHAMPION-REVIEW-MAP.md`, `docs/BETS.md`.",
    ]
    return "\n".join(lines) + "\n"


def model_enrich_global(cfg: dict, agg: dict) -> str | None:
    """Optional Analyst pass to rewrite ONLY the executive-summary prose in plain
    language — the glossary, citations, and per-unit table are always code-rendered
    and never passed through the model, so a finding's wording can never drift from
    what Layer 0/1 actually cited (Bet 5: auditor-only, no invented content)."""
    summary_input = json.dumps(
        {
            "documents_judged": agg["documents_judged"],
            "status_counts": agg["status_counts"],
            "finding_status_counts": agg["finding_status_counts"],
            "systemic_missing": agg["systemic_missing"],
            "misfiled_documents_sample": [
                {k: d[k] for k in ("title", "parent_title", "matched_title", "excerpt")}
                for d in agg["mismatch_docs_high"][:15]
            ],
        },
        indent=2,
    )
    prompt = f"""{AUDITOR_RULES}

Synthesize this cross-unit conformance data into an EXECUTIVE SUMMARY for a curriculum
director (max 300 words, plain language). This replaces ONLY the summary paragraph —
do not restate the raw data as a list, write connected prose. No lesson fixes.

DATA:
{summary_input}
"""
    url = cfg["models"]["analyst_url"]
    model = cfg["models"]["analyst_model"]
    timeout = cfg["models"]["timeout_seconds"]
    try:
        resp = requests.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"WARN: model synthesis skipped: {e}")
        return None


def synthesize(
    project_id: str,
    delivery: str = "model",
    report: str = "all",
    unit_ids: list[str] | None = None,
    use_model: bool | None = None,
) -> Path:
    """Plate Layer 1/2 ledgers into registered reports.

    delivery='model' (default): hybrid curriculum-audit narrative for first-pass
    and teacher. delivery='code': deterministic tables only.
    use_model is a deprecated alias: True→model, False→code when delivery omitted
    via older callers.
    """
    from reports import DELIVERY_CODE, DELIVERY_MODEL, resolve_report_ids, run_reports

    if use_model is not None:
        delivery = DELIVERY_MODEL if use_model else DELIVERY_CODE
    if delivery not in (DELIVERY_MODEL, DELIVERY_CODE):
        raise ValueError(f"delivery must be '{DELIVERY_MODEL}' or '{DELIVERY_CODE}'")
    return run_reports(
        project_id,
        resolve_report_ids(report),
        unit_ids=unit_ids,
        delivery=delivery,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plate Layer 1/2 ledgers into modular reports (first-pass, teacher, …). "
            "Default --delivery model runs hybrid curriculum-audit narrative for "
            "first-pass and teacher. See --list-reports and docs/REPORT-DELIVERY.md."
        )
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--report",
        default="all",
        help="Report id, comma-separated ids, or 'all' (default: all implemented)",
    )
    parser.add_argument(
        "--unit",
        help="Comma-separated unit id(s) for teacher report (default: every unit in manifest)",
    )
    parser.add_argument(
        "--list-reports",
        action="store_true",
        help="Print registered report ids (implemented + planned) and exit",
    )
    parser.add_argument(
        "--delivery",
        choices=["model", "code"],
        default="model",
        help="model=hybrid narrative (default); code=tables only (fast regen)",
    )
    parser.add_argument(
        "--model",
        action="store_true",
        help="Deprecated alias for --delivery model (kept for older scripts)",
    )
    args = parser.parse_args()
    try:
        if args.list_reports:
            from reports import format_list_reports

            print(format_list_reports())
            return 0
        unit_ids = None
        if args.unit:
            unit_ids = [u.strip() for u in args.unit.split(",") if u.strip()]
            for u in unit_ids:
                from audit_lib import validate_slug_id

                validate_slug_id(u, "unit id")
        delivery = "model" if args.model else args.delivery
        synthesize(
            args.project,
            delivery=delivery,
            report=args.report,
            unit_ids=unit_ids,
        )
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
