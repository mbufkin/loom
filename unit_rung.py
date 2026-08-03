#!/usr/bin/env python3
"""
unit_rung.py — the deterministic UNIT rung of the curriculum waterfall.

One level up from lesson_rung.py. It does NOT re-read documents or call a model;
it composes signals other stages already computed deterministically into ONE
per-unit verdict, and every number cites the artifact it came from:

  - lesson roll-up   <- layer_lesson/LESSON-RUNG.json  (gate-pass rate, coverage)
  - role fulfillment <- synthesize.aggregate_layer1()   (fulfilled/missing + the
                        noise-reduced missing_rollup: systemic vs isolated gaps)
  - pacing fit       <- pacing-plan.yaml vs INFERRED-CALENDARS.json (planned days
                        vs days that actually have evidence)
  - internal parts   <- layer2/findings.json            (lessons missing core parts)

It emits layer_unit/UNIT-RUNG.json (+ .md), whose per-unit bands + summary are the
stable hand-off the future CURRICULUM rung will consume — exactly as the lesson
rung's per-unit rollup fed this one.

Deliberately NOT judged here (no infrastructure to back it, so we don't fake it):
standards/TEKS coverage matrix, Introduced/Practiced/Assessed progression, and
rigor/DOK. See docs/UNIT-RUNG.md for why each is deferred.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from audit_lib import (
    atomic_write,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)
from lesson_rung import GATE_SCORER
from synthesize import (
    aggregate_layer1,
    load_expectations,
    load_layer1_data,
    load_layer2_data,
)

# --- Band tuning (documented + tunable, mirroring synthesize.py's constant style) ---
# A unit's band is a deterministic function of signals we can defend with evidence.
# Thresholds are intentionally forgiving on the low end (a director wants the truly
# thin units surfaced, not every unit dinged) and demanding on the high end (Strong
# should mean "I'd hand this to a teacher as-is").
WEAK_GATE_RATE = 0.34  # <1/3 of lessons clear the completeness gate -> thin unit
STRONG_GATE_RATE = 0.67  # >=2/3 clear the gate ...
STRONG_COVERAGE = 0.70  # ... AND lessons are on average well-covered -> Strong
# Pacing: evidence days below this fraction of planned days reads as an under-built
# unit (e.g. 6 days of evidence for a 10-day module -> 0.6 < 0.8 -> UNDER_COVERED).
PACING_UNDER_RATIO = 0.8
INTERNAL_TOP_N = 3  # most common missing lesson-parts to name per unit
ISOLATED_GAP_CAP = 5  # localized gaps shown per unit before we defer to findings.json


def unit_pacing_fit(pacing_unit: dict | None, inferred_unit: dict | None) -> dict:
    """Planned instructional days (pacing-plan.yaml) vs days that actually carry
    evidence (INFERRED-CALENDARS.json HAS_EVIDENCE). Pure. Flags an under-built unit
    without a model — the calendar already knows where the blanks are."""
    planned = (pacing_unit or {}).get("unit_length_days")
    days = (inferred_unit or {}).get("days") or []
    evidence_days = sum(1 for d in days if d.get("status") == "HAS_EVIDENCE")
    if not planned:
        return {
            "planned_days": planned,
            "evidence_days": evidence_days,
            "ratio": None,
            "flag": "UNKNOWN",
        }
    ratio = round(evidence_days / planned, 3)
    if ratio < PACING_UNDER_RATIO:
        flag = "UNDER_COVERED"
    elif evidence_days > planned:
        flag = "OVER_COVERED"
    else:
        flag = "OK"
    return {
        "planned_days": planned,
        "evidence_days": evidence_days,
        "ratio": ratio,
        "flag": flag,
    }


def unit_internal_gaps(layer2_rows: list[dict], unit_doc_ids: set[str]) -> dict:
    """How many of the unit's judged lessons are internally incomplete, and which
    core parts they most commonly lack (from Layer 2). Pure."""
    rows = [r for r in layer2_rows if r.get("doc_id") in unit_doc_ids]
    incomplete = [r for r in rows if r.get("status") == "INCOMPLETE"]
    comp = Counter()
    for r in incomplete:
        for c in r.get("components_missing") or []:
            comp[c] += 1
    return {
        "docs_judged": len(rows),
        "docs_incomplete": len(incomplete),
        "top_missing_components": [c for c, _ in comp.most_common(INTERNAL_TOP_N)],
    }


def _unit_artifacts(artifact_unit: dict | None) -> dict:
    """Shape the artifact rung's per-unit block for the unit record. Pure. Separates
    the DETERMINISTIC signal that gates (presence gaps) from the ADVISORY alignment
    (which is carried for display only). Absent artifact rung -> an empty,
    gap-free block so unit_band is unaffected on an older run."""
    au = artifact_unit or {}
    gaps = au.get("deterministic_gaps") or []
    return {
        "count": au.get("artifact_count", 0),
        "gate_pass": au.get("gate_pass_count", 0),
        "gate_pass_rate": au.get("gate_pass_rate", 0.0),
        "roles": au.get("roles", {}),
        # Gating signal: at least one artifact is structurally incomplete.
        "has_gap": bool(gaps),
        "deterministic_gaps": gaps,
        # Advisory: how many artifacts could not be aligned (lesson lacked an anchor).
        "cannot_assess_alignment": au.get("cannot_assess_alignment", 0),
    }


def unit_band(metrics: dict) -> str:
    """Deterministic Strong/Developing/Weak (or Unrated) from the assembled metrics.
    Pure and total — the single place the verdict is decided, so it is trivially
    testable and auditable.

    Unrated is honest, not a cop-out: a unit with no lessons found has no lesson
    evidence to grade, so calling it "Weak" would be a fabricated judgment. Its
    thinness is still surfaced via the pacing flag instead."""
    if not metrics.get("lesson_count"):
        return "Unrated"
    gpr = metrics.get("gate_pass_rate") or 0.0
    cov = metrics.get("gate_coverage")
    if gpr < WEAK_GATE_RATE or metrics.get("has_systemic_gap"):
        return "Weak"
    if (
        gpr >= STRONG_GATE_RATE
        and cov is not None
        and cov >= STRONG_COVERAGE
        and metrics.get("pacing_flag") != "UNDER_COVERED"
        # A structurally-incomplete non-lesson artifact (a quiz with no items, an
        # answer key with no answers) is a deterministic gap: the unit is not
        # "hand it to a teacher as-is" Strong. This can only DROP Strong->Developing;
        # it never fabricates Weak (lesson thinness + systemic role gaps drive Weak).
        and not metrics.get("has_artifact_gap")
    ):
        return "Strong"
    return "Developing"


def _unit_ids(units_manifest: dict, *extra_sources: dict) -> list[str]:
    """Manifest key order first (the authored sequence), then any unit id that only
    shows up in the data (e.g. an unlinked bucket), so nothing is silently dropped."""
    ordered = [uid for uid in units_manifest]
    seen = set(ordered)
    tail = set()
    for src in extra_sources:
        tail |= {uid for uid in src if uid and uid not in seen}
    return ordered + sorted(tail)


def build_unit_rung(project_id: str) -> Path:
    """Assemble the per-unit verdicts and write UNIT-RUNG.json (+ .md). Returns path."""
    root = project_dir(project_id)
    manifest = load_yaml(root / "manifest.yaml")
    units_manifest = manifest.get("units") or {}

    # Layer 1 aggregates (same deterministic path synthesize/reports use).
    bucket_rows, findings = load_layer1_data(project_id)
    expectations = load_expectations(project_id)
    agg = aggregate_layer1(bucket_rows, findings, manifest, expectations)
    unit_rollup = {u["unit_id"]: u for u in agg.get("unit_rollup", [])}
    missing_rollup = agg.get("missing_rollup") or {}
    systemic_roles = {r["role"] for r in missing_rollup.get("systemic_absent", [])}
    silenced_roles = {r["role"] for r in missing_rollup.get("silenced", [])}

    # Lesson rung (may be absent on an older run — degrade, don't crash).
    lr_path = root / "layer_lesson" / "LESSON-RUNG.json"
    lesson_units: dict = {}
    if lr_path.is_file():
        lesson_units = (json.loads(lr_path.read_text()) or {}).get("units", {})

    # Artifact rung (Paths B/C non-lesson review). Also optional — degrade, don't
    # crash — so unit_rung still works on a project that has only run the lesson rung.
    ar_path = root / "layer_artifact" / "ARTIFACT-RUNG.json"
    artifact_units: dict = {}
    if ar_path.is_file():
        artifact_units = (json.loads(ar_path.read_text()) or {}).get("units", {})

    # Pacing + inferred calendars.
    pacing = load_yaml(root / "pacing-plan.yaml") if (
        root / "pacing-plan.yaml"
    ).is_file() else {}
    pacing_units = {u["unit_id"]: u for u in (pacing.get("units") or [])}
    inf_path = root / "calendars_inferred" / "INFERRED-CALENDARS.json"
    inferred_units: dict = {}
    if inf_path.is_file():
        inferred_units = (json.loads(inf_path.read_text()) or {}).get("units", {})

    # Layer 2 rows + doc->unit map (via manifest, same key Layer 2 writes).
    l2_rows = load_layer2_data(project_id)
    doc_unit: dict[str, str] = {}
    for uid, u in units_manifest.items():
        for rel in u.get("documents") or u.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)
    unit_doc_ids: dict[str, set[str]] = defaultdict(set)
    for did, uid in doc_unit.items():
        unit_doc_ids[uid].add(did)

    # Findings grouped per unit, for isolated-vs-systemic gap classification.
    findings_by_unit: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        findings_by_unit[f["unit_id"]].append(f)

    units_out: dict[str, dict] = {}
    for uid in _unit_ids(units_manifest, unit_rollup, lesson_units, artifact_units):
        title = (
            (units_manifest.get(uid) or {}).get("title")
            or unit_rollup.get(uid, {}).get("title")
            or uid
        )

        lr = lesson_units.get(uid) or {}
        lesson_count = lr.get("lesson_count", 0)
        gate_pass = lr.get("gate_pass_count", 0)
        gate_rate = lr.get("gate_pass_rate", 0.0)
        mean_cov = lr.get("mean_coverage") or {}
        gate_cov = mean_cov.get(GATE_SCORER)

        # Role gaps for THIS unit: which missing roles are project-wide systemic
        # (one expectation call, inhibited) vs isolated (a real localized gap).
        uf = findings_by_unit.get(uid, [])
        unit_missing_roles = {f["role"] for f in uf if f.get("status") == "MISSING"}
        unit_systemic = sorted(unit_missing_roles & systemic_roles)
        isolated = [
            {"role": f["role"], "day_id": f.get("day_id")}
            for f in uf
            if f.get("status") == "MISSING"
            and f["role"] not in systemic_roles
            and f["role"] not in silenced_roles
        ]
        roll = unit_rollup.get(uid, {})

        pacing_fit = unit_pacing_fit(pacing_units.get(uid), inferred_units.get(uid))
        internal = unit_internal_gaps(l2_rows, unit_doc_ids.get(uid, set()))
        artifacts = _unit_artifacts(artifact_units.get(uid))

        band = unit_band(
            {
                "lesson_count": lesson_count,
                "gate_pass_rate": gate_rate,
                "gate_coverage": gate_cov,
                "has_systemic_gap": bool(unit_systemic),
                "pacing_flag": pacing_fit["flag"],
                # Deterministic artifact gaps GATE (block Strong); alignment advises.
                "has_artifact_gap": artifacts["has_gap"],
            }
        )

        units_out[uid] = {
            "title": title,
            "band": band,
            "lessons": {
                "count": lesson_count,
                "gate_pass": gate_pass,
                "gate_pass_rate": gate_rate,
                "mean_coverage": mean_cov,
            },
            "roles": {
                "fulfilled": roll.get("fulfilled", 0),
                "missing": roll.get("missing", 0),
                "systemic_absent": unit_systemic,
                "isolated_gaps": isolated[:ISOLATED_GAP_CAP],
                "isolated_gap_total": len(isolated),
            },
            "pacing": pacing_fit,
            "internal": internal,
            "artifacts": artifacts,
            "cites": {
                "lesson_rung": "layer_lesson/LESSON-RUNG.json",
                "artifact_rung": "layer_artifact/ARTIFACT-RUNG.json",
                "layer1_findings": "layer1/findings.json",
                "unit_id": uid,
            },
        }

    band_counts = Counter(u["band"] for u in units_out.values())
    artifact = {
        "project_id": project_id,
        "gate_scorer": GATE_SCORER,
        "summary": {
            "unit_count": len(units_out),
            "band_counts": dict(band_counts),
        },
        "units": units_out,
    }

    out_dir = root / "layer_unit"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "UNIT-RUNG.json"
    atomic_write(dest, json.dumps(artifact, indent=2))
    atomic_write(out_dir / "UNIT-RUNG.md", _render_md(project_id, artifact))
    log(
        f"unit-rung → {dest} ({len(units_out)} units; "
        f"{dict(band_counts)})"
    )
    return dest


def _render_md(project_id: str, artifact: dict) -> str:
    bands = artifact["summary"]["band_counts"]
    band_line = "  ·  ".join(f"{k}: {v}" for k, v in bands.items()) or "(none)"
    md = [
        "# Unit rung (deterministic roll-up)",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Units:** {artifact['summary']['unit_count']}  ·  {band_line}",
        "",
        "Deterministic composition of the lesson rung, Layer 1 role fulfillment, "
        "pacing, and Layer 2 completeness. Per-unit detail (with citations) is in "
        "`UNIT-RUNG.json`. Standards coverage, skill progression, and rigor are "
        "deliberately out of scope (see `docs/UNIT-RUNG.md`).",
        "",
        "| Unit | Band | Lessons (gate) | Gate cov | Pacing | Internal gaps | Artifacts (gate) |",
        "|---|---|---|---|---|---|---|",
    ]
    for uid, u in artifact["units"].items():
        les = u["lessons"]
        cov = les["mean_coverage"].get(artifact["gate_scorer"])
        cov_s = f"{cov:.2f}" if cov is not None else "—"
        pac = u["pacing"]
        pac_s = (
            f"{pac['evidence_days']}/{pac['planned_days']} ({pac['flag']})"
            if pac["planned_days"]
            else pac["flag"]
        )
        intern = u["internal"]
        intern_s = (
            f"{intern['docs_incomplete']}/{intern['docs_judged']} incomplete"
            if intern["docs_judged"]
            else "—"
        )
        art = u.get("artifacts", {})
        art_s = (
            f"{art['gate_pass']}/{art['count']}"
            + ("  ⚠gap" if art.get("has_gap") else "")
            if art.get("count")
            else "—"
        )
        md.append(
            f"| {uid} | {u['band']} | "
            f"{les['gate_pass']}/{les['count']} | {cov_s} | {pac_s} | {intern_s} | {art_s} |"
        )
    return "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic unit rung (rolls up the lesson rung; feeds the curriculum rung)"
    )
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    validate_slug_id(args.project, "project id")
    try:
        build_unit_rung(args.project)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
