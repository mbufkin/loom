#!/usr/bin/env python3
"""
artifact_rung.py — the NON-lesson artifact rung of the curriculum waterfall.

lesson_rung.py owns lesson atoms (lesson_plan / lesson_content). This rung
reviews everything else by rolling up the Path B–H findings that
workflows/run_paths.py already wrote — quizzes, exit tickets, rubrics,
worksheets, answer keys, projects, slides, syllabi, and catch-all types. It
does NOT re-score documents and does NOT call a model; the Paths lenses are
the presence signal. Path findings files B–H are the input source; lesson-typed
docs that Path E also inventorizes are skipped here so a unit cannot pick up an
artifact gap on a document lesson_rung already judged (the lesson_content
contradiction fix).

Per document, a MISSING checklist step is a deterministic structural gap
(STUB and NOT_APPLICABLE are ignored; PARTIAL and OPTIONAL_ABSENT are advisory
only — the scorers emit OPTIONAL_ABSENT when an all-optional step finds no
signal). Per-unit roll-up lands in layer_artifact/ARTIFACT-RUNG.json (+ .md) —
the stable hand-off unit_rung.py consumes. Alignment scoring is intentionally
absent: the contract keeps the fields so consumers stay stable, with honest
"no alignment ran" values.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from audit_lib import (
    BASE_DIR,
    atomic_write,
    doc_id_from_filename,
    load_yaml,
    log,
    project_dir,
    validate_slug_id,
)
# LESSON_DOC_TYPES is the living set lesson_rung / enumerate_lessons uses. The
# pre-rewrite module called this LESSON_ROLES (plus teacher_edition_multi_lesson);
# that name no longer exists — import the bake-off constant so the two rungs
# cannot drift on what counts as a lesson atom.
from lesson_bakeoff import LESSON_DOC_TYPES
from synthesize import readable_title_from_filename

# Paths B–H are the findings files we read. Lesson atoms inside those files are
# still excluded via LESSON_DOC_TYPES (see collect_path_records).
ARTIFACT_PATHS: tuple[str, ...] = ("b", "c", "d", "e", "f", "g", "h")

# Honest identity for this rollup. Kept as a stable string so ARTIFACT-RUNG.json
# readers can tell path-findings provenance from the deleted presence scorer.
PRESENCE_SCORER = "path_b_h_rollup"

# Step ids in inventory rows look like B3 / H4 — letter matches the path, digit
# is the checklist section. Anything else on the row is metadata (doc_id, …).
_STEP_RE = re.compile(r"^[A-H]\d+$")

# Statuses that never gate and never count as coverage denominators. STUB is the
# unimplemented emit step every path ships; NOT_APPLICABLE means the lens does
# not apply to this doc_type (e.g. rubric↔key pairing).
_IGNORED_STATUSES = frozenset({"STUB", "NOT_APPLICABLE"})


# --- checklist metadata -----------------------------------------------------


def load_checklist(checklist_rel: str | None) -> dict[str, str]:
    """Load step labels from one checklist YAML.

    Labels mirror the Paths panel helper in ui/server.py (B3 -> "Answer key
    signal"). Structural steps (pairing, inventory) live in ``sections`` with a
    label and no fields so this loader and the UI share one source. Returns {}
    when the checklist is missing or unreadable — an older findings file without
    a checklist path still rolls up, just with bare step ids in the gap chips.
    """
    if not checklist_rel:
        return {}
    # Resolve under the repo root and refuse path escape (findings name a relative
    # path like workflows/checklists/assessment.yaml — never trust it blindly).
    spec = (BASE_DIR / checklist_rel).resolve()
    try:
        spec.relative_to(BASE_DIR)
    except ValueError:
        return {}
    if not spec.is_file():
        return {}
    try:
        data = load_yaml(spec)
    except Exception:  # noqa: BLE001 — bad checklist must not kill the rung
        return {}
    labels: dict[str, str] = {}
    for section in (data.get("sections") or {}).values():
        step = section.get("step")
        if not step:
            continue
        sid = str(step)
        label = section.get("label")
        if label:
            # Labels are stored as "B3 Answer key signal"; drop the redundant id.
            labels[sid] = str(label).removeprefix(f"{step} ").strip()
    return labels


def checklist_labels(checklist_rel: str | None) -> dict[str, str]:
    """Step id -> human label. Alias kept for callers that prefer the name."""
    return load_checklist(checklist_rel)


def _gap_label(step: str, labels: dict[str, str]) -> str:
    """Chip-friendly missing-part string: keep the step id so a reviewer can
    jump to the same cell the Paths panel shows."""
    human = labels.get(step) or step
    if human == step:
        return step
    return f"{step} {human}"


# --- enumeration / route metadata -------------------------------------------


def doc_unit_map(project_id: str) -> dict[str, str]:
    """doc_id -> unit_id from the project's manifest. Unmapped docs fall through
    to the caller, which uses the '(unlinked)' bucket — same fallback the
    original ledger enumeration used when a file was outside every unit."""
    root = project_dir(project_id)
    manifest = load_yaml(root / "manifest.yaml")
    doc_unit: dict[str, str] = {}
    for uid, unit in (manifest.get("units") or {}).items():
        for rel in unit.get("documents") or unit.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)
    return doc_unit


def _route_by_doc(project_id: str) -> dict[str, dict]:
    """doc_id -> route-map row (source_file, doc_type, …). Soft-absent: a project
    that has path findings but no route-map still rolls up; titles then degrade
    to the bare doc_id rather than crashing the rung."""
    path = project_dir(project_id) / "layer0" / "route-map.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for row in data.get("routes") or []:
        did = row.get("doc_id")
        if did:
            out[str(did)] = row
    return out


def _load_path_findings(project_id: str, letter: str) -> dict | None:
    """Read path_<letter>/findings.json. None when absent or unreadable — a path
    that has not been run yet contributes nothing (same as status: skipped)."""
    path = project_dir(project_id) / f"path_{letter}" / "findings.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"WARN: ignoring unreadable {path}: {e}")
        return None


# --- per-doc scoring from path inventory ------------------------------------


def _inventory_steps(item: dict) -> list[tuple[str, dict]]:
    """(step_id, step_payload) pairs from one inventory row, sorted for stable
    criteria order. Inventory nests steps as sibling keys alongside doc_id /
    doc_type — we key off the step-id pattern rather than a fixed schema so a
    new B7/H6 does not require a code change here."""
    steps: list[tuple[str, dict]] = []
    for key, val in item.items():
        if not _STEP_RE.match(key):
            continue
        if not isinstance(val, dict):
            continue
        steps.append((key, val))
    steps.sort(key=lambda kv: (kv[0][0], int(kv[0][1:])))
    return steps


def score_inventory_item(
    item: dict,
    labels: dict[str, str],
    *,
    path: str,
    lens: str,
) -> dict:
    """Turn one Path inventory row into a presence block. Pure.

    Gate rule (deliberate, not a soft heuristic): among steps that are neither
    STUB nor NOT_APPLICABLE, MISSING fails the gate. PARTIAL and OPTIONAL_ABSENT
    advise only — the path scorers emit OPTIONAL_ABSENT when every field on the
    step is optional and none hit, so this gate does not re-derive optionality
    from the checklist YAML.

    Coverage counts only PRESENT toward the numerator so PARTIAL /
    OPTIONAL_ABSENT do not inflate the rate.
    """
    criteria: list[dict] = []
    missing_required: list[str] = []
    scored = 0
    present = 0
    for step, payload in _inventory_steps(item):
        status = str(payload.get("status") or "").upper()
        if status in _IGNORED_STATUSES:
            continue
        scored += 1
        label = labels.get(step) or step
        note = str(payload.get("note") or "")
        criteria.append(
            {
                "criterion_id": step,
                "label": label,
                "scoring": "presence",
                "verdict": status,
                "band": None,
                "evidence": [],
                "note": note,
                # Provenance for drill-down: which lens produced this verdict.
                "path": path,
                "lens": lens,
            }
        )
        if status == "PRESENT":
            present += 1
        elif status == "MISSING":
            missing_required.append(_gap_label(step, labels))
        # PARTIAL / OPTIONAL_ABSENT: counted in denominator, not present, not a gap.
    gate_pass = not missing_required
    coverage = round(present / scored, 3) if scored else 0.0
    return {
        "gate_pass": gate_pass,
        "coverage": coverage,
        "missing_required": missing_required,
        "criteria": criteria,
    }


def artifact_record_from_path(
    item: dict,
    *,
    unit_id: str,
    title: str,
    source_file: str | None,
    labels: dict[str, str],
    path: str,
    lens: str,
) -> dict:
    """One artifact's rung record — same outer shape the UI ArtifactDoc type
    expects, filled from a Path inventory row instead of a presence scorer."""
    doc_id = str(item.get("doc_id") or "")
    doc_type = str(item.get("doc_type") or "other")
    presence = score_inventory_item(
        item,
        labels,
        path=path,
        lens=lens,
    )
    return {
        "doc_id": doc_id,
        "unit_id": unit_id,
        "title": title,
        "source_file": source_file,
        "role": doc_type,
        "doc_type": doc_type,
        # Paths B–H are dedicated lenses, not the old generic fallback rubric.
        "is_fallback": False,
        "nursery": False,
        "path": path,
        "lens": lens,
        "presence": presence,
    }


# --- rollup -----------------------------------------------------------------


def collect_path_records(project_id: str) -> list[dict]:
    """Walk Paths B–H findings and emit one record per inventoried document.

    A path with status 'skipped' (or a missing findings.json) contributes
    nothing — the router deliberately writes skipped files when a lens has no
    routed docs, and treating those as empty keeps the rollup honest. The first
    path that claims a doc_id wins if routing ever double-emits (it should not).

    Documents whose doc_type is in LESSON_DOC_TYPES are skipped even when a
    Path B–H inventory lists them (Path E routinely inventorizes lesson_content).
    lesson_rung owns those atoms; double-counting them here would let an artifact
    gap override a lesson already judged on its merits.
    """
    doc_unit = doc_unit_map(project_id)
    routes = _route_by_doc(project_id)
    records: list[dict] = []
    seen: set[str] = set()

    for letter in ARTIFACT_PATHS:
        findings = _load_path_findings(project_id, letter)
        if not findings:
            continue
        if str(findings.get("status") or "").lower() == "skipped":
            continue
        labels = load_checklist(findings.get("checklist"))
        path = str(findings.get("path") or letter.upper())
        lens = str(findings.get("lens") or path)
        for item in findings.get("inventory") or []:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id") or "")
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            route = routes.get(doc_id) or {}
            # Prefer inventory doc_type; fall back to the route-map's classification.
            doc_type = str(item.get("doc_type") or route.get("doc_type") or "other")
            if doc_type in LESSON_DOC_TYPES:
                continue
            if not item.get("doc_type") and route.get("doc_type"):
                item = {**item, "doc_type": route["doc_type"]}
            source = route.get("source_file") or ""
            title = (
                readable_title_from_filename(source)
                if source
                else doc_id
            )
            source_file = f"sources/{source}" if source else None
            records.append(
                artifact_record_from_path(
                    item,
                    unit_id=doc_unit.get(doc_id, "(unlinked)"),
                    title=title,
                    source_file=source_file,
                    labels=labels,
                    path=path,
                    lens=lens,
                )
            )

    records.sort(key=lambda r: (r["unit_id"], r["doc_type"], r["title"], r["doc_id"]))
    return records


def rollup_units(records: list[dict]) -> dict:
    """Compose per-artifact records into a per-unit summary — the hand-off the
    unit rung reads. Pure (no I/O). Deterministic presence gaps GATE; alignment
    fields stay at the honest zero because this rollup never runs a model."""
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_unit[r["unit_id"]].append(r)

    units: dict[str, dict] = {}
    for uid, rows in sorted(by_unit.items()):
        n = len(rows)
        gate_pass = sum(1 for r in rows if r["presence"]["gate_pass"])
        # Structural gaps: every artifact that failed its presence gate, named by
        # role + the checklist steps it lacks. unit_rung gates Strong on a
        # non-empty deterministic_gaps list (via bool(gaps)), not has_artifact_gap.
        gaps = [
            {
                "doc_id": r["doc_id"],
                "role": r["role"],
                "title": r["title"],
                "missing_required": r["presence"]["missing_required"],
            }
            for r in rows
            if not r["presence"]["gate_pass"]
        ]
        role_counts: dict[str, int] = defaultdict(int)
        for r in rows:
            role_counts[r["role"]] += 1
        units[uid] = {
            "artifact_count": n,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / n, 3) if n else 0.0,
            "roles": dict(role_counts),
            "deterministic_gaps": gaps,
            "has_artifact_gap": bool(gaps),
            "cannot_assess_alignment": 0,
            "documents": rows,
        }
    return units


# --- build ------------------------------------------------------------------


def build_artifact_rung(project_id: str, with_model: bool = False) -> Path:
    """Roll up Path B–H findings into ARTIFACT-RUNG.json (+ .md).

    `with_model` is accepted for CLI compatibility with the pre-rewrite stage
    (run_project still passes nothing; operators may pass --with-model). This
    rollup never invokes a model — alignment stays null/zero so the contract
    fields remain honest rather than inventing advisory bands.
    """
    if with_model:
        log(
            "artifact-rung: --with-model accepted but unused "
            "(alignment pass is not part of the path-findings rollup)"
        )

    records = collect_path_records(project_id)
    units = rollup_units(records)
    total = len(records)
    gate_pass = sum(1 for r in records if r["presence"]["gate_pass"])
    role_totals: dict[str, int] = defaultdict(int)
    for r in records:
        role_totals[r["role"]] += 1

    artifact = {
        "project_id": project_id,
        "presence_scorer": PRESENCE_SCORER,
        # Alignment is not implemented on the path-findings rollup; keep the key
        # so consumers that read alignment_scorer / with_model do not KeyError.
        "alignment_scorer": None,
        "with_model": False,
        "summary": {
            "artifact_count": total,
            "gate_pass_count": gate_pass,
            "gate_pass_rate": round(gate_pass / total, 3) if total else 0.0,
            "unit_count": len(units),
            "roles": dict(sorted(role_totals.items())),
            "nursery_count": 0,
        },
        "units": units,
        "artifacts": records,
    }

    out_dir = project_dir(project_id) / "layer_artifact"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "ARTIFACT-RUNG.json"
    atomic_write(dest, json.dumps(artifact, indent=2))
    atomic_write(out_dir / "ARTIFACT-RUNG.md", _render_md(project_id, artifact))
    log(
        f"artifact-rung → {dest} ({total} artifacts, {gate_pass} passed presence "
        f"gate, {len(units)} units)"
    )
    return dest


def _render_md(project_id: str, artifact: dict) -> str:
    s = artifact["summary"]
    roles = "  ·  ".join(f"{k}×{v}" for k, v in s["roles"].items()) or "(none)"
    md = [
        "# Artifact rung (Paths B–H — non-lesson review)",
        "",
        f"**Dataset:** `{project_id}`  ",
        f"**Artifacts:** {s['artifact_count']}  ·  "
        f"**Passed presence gate:** {s['gate_pass_count']} "
        f"({s['gate_pass_rate']:.0%})  ·  **Units:** {s['unit_count']}",
        f"**Roles:** {roles}  ",
        f"**Presence source:** `{artifact['presence_scorer']}` (Path B–H findings rollup)",
        "",
        "Deterministic Path checklist gaps GATE the unit band. Model alignment is "
        "not run by this rollup. Per-doc detail is in `ARTIFACT-RUNG.json`.",
        "",
        "| Unit | Artifacts | Presence gate | Structural gaps | Cannot-assess |",
        "|---|---|---|---|---|",
    ]
    for uid, u in artifact["units"].items():
        gaps = len(u["deterministic_gaps"])
        md.append(
            f"| {uid} | {u['artifact_count']} | "
            f"{u['gate_pass_count']}/{u['artifact_count']} | {gaps} | "
            f"{u['cannot_assess_alignment']} |"
        )
    return "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Artifact rung (Paths B–H findings rollup; feeds the unit rung)"
        )
    )
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--with-model",
        action="store_true",
        help=(
            "accepted for CLI compatibility; alignment is not run by this rollup"
        ),
    )
    args = ap.parse_args()
    validate_slug_id(args.project, "project id")
    try:
        build_artifact_rung(args.project, with_model=args.with_model)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
