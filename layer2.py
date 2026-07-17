#!/usr/bin/env python3
"""
layer2.py — Layer 2: Lesson Structural Completeness.

See docs/BETS.md Bet 14 and docs/roadmap.md for the design context. Reads
Layer 0's already-cited element ledger and Layer 1's already-
computed role-fulfillment findings, and answers one further question with ZERO
new model calls: for a document Layer 1 already confirmed IS fulfilling role X
(e.g. `lesson_plan`), does that document itself contain the internal
instructional-function components (Bet 10's `element_type` taxonomy) a
complete role-X document should have?

This is deliberately narrower and more mechanical than Layer 1 Phase 3's "does
this element function as role X" judgment — Bet 11 correctly kept THAT as a
per-case model call, not a static element_type -> ARTIFACT_ROLES lookup table,
because that mapping problem is about ROUTING one candidate element to the
right cross-document slot, a judgment call a table gets wrong on real corpora.
Layer 2's question is narrower: "given we already know this ONE document
anchors role X, what internal parts does a well-formed role-X document have"
— a checklist against a document already selected, not a routing decision —
so a static ROLE_EXPECTED_COMPONENTS table is a defensible, cheap, code-only
check here (Bet 0: don't spend a model call when the deterministic answer is
already computable from data Layer 0/1 already produced).

Scope, deliberately narrow for v1 (see docs/STRUCTURAL-FILL.md): this checks
whether expected PARTS of a lesson are PRESENT, never whether the lesson is
well-designed, engaging, or pedagogically effective, and never whether those
parts are internally consistent with each other (e.g. does the assessment
actually test the stated objective — a harder, separate question, explicitly
deferred). Missing content is reported, never authored or fixed.

Auditor-only: reports which internal parts are present/missing, with a
citation for each present one; never writes or fixes lesson content.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from audit_lib import (
    atomic_write,
    doc_id_from_filename,
    load_manifest,
    log,
    project_dir,
    validate_slug_id,
)

# v1-hypothesis, same versioning discipline as schema_validate.LAYER0_TAXONOMY_VERSION
# (Bet 10) — a future retaxonomy or expanded role list is a traceable re-run, not a
# silent redefinition.
LAYER2_TAXONOMY_VERSION = "v2-ctat-unit-plan"

# Which element_type(s) (Layer 0's universal instructional-function taxonomy, see
# schema_validate.ELEMENT_TYPES) a complete document fulfilling this ARTIFACT_ROLE
# should contain SOMEWHERE among its own elements. Loaded from the CTAT /
# Northwest ISD lesson-plan checklist (workflows/checklists/lesson_plan.yaml) so
# Layer 2 tracks the same education-space bar as the Unit Plan discovery plate
# (unit_plan_fill.py). Falls back to the original four-part set if the checklist
# file is missing.
def _load_role_expected_components() -> dict[str, frozenset[str]]:
    fallback = frozenset(
        {
            "standards_objectives",
            "logistics_materials",
            "direct_instruction",
            "assessment_checkpoint",
        }
    )
    try:
        from unit_plan_fill import layer2_expected_element_types

        return {"lesson_plan": layer2_expected_element_types()}
    except Exception:
        return {"lesson_plan": fallback}


ROLE_EXPECTED_COMPONENTS: dict[str, frozenset[str]] = _load_role_expected_components()


def load_ledger(project_id: str) -> list[dict]:
    path = project_dir(project_id) / "layer0" / "ledger.json"
    if not path.is_file():
        raise FileNotFoundError(f"No Layer 0 ledger at {path} — run layer0.py first")
    return json.loads(path.read_text())


def load_layer1_findings(project_id: str) -> list[dict]:
    path = project_dir(project_id) / "layer1" / "findings.json"
    if not path.is_file():
        raise FileNotFoundError(f"No Layer 1 findings at {path} — run layer1.py first")
    return json.loads(path.read_text())


def _element_types(el: dict) -> set[str]:
    """Split an element's element_type into its member token(s).

    Should almost always be a single-item set. It's a set, not a `.get()`, as a
    defensive backward-compat shim: a since-fixed Layer 0-B bug (see layer0.py
    coerce_element_type — the split-review path wrote whatever the model
    returned straight into the ledger with no enum check, so a model that
    echoed the pipe-delimited enum LIST from the prompt back as a value instead
    of picking one member landed rows like "hook_engagement|direct_instruction"
    in already-produced ledgers) means real, already-committed ledgers can
    contain a "|"-joined compound value. Splitting it here means those legacy
    rows are still judged fairly (every token they contain counts as present)
    instead of silently never matching any expected component and producing a
    false INCOMPLETE. A clean single value splits into a one-item set, so this
    is a no-op for any ledger produced after the Layer 0 fix.
    """
    raw = el.get("element_type") or ""
    return {t for t in raw.split("|") if t}


def compute_completeness(
    findings: list[dict],
    ledger_by_id: dict[str, dict],
    elements_by_doc: dict[str, list[dict]],
) -> list[dict]:
    """One row per (doc_id, role) — deduped so a document anchoring multiple
    unit/day slots for the same role is judged once, not once per slot. Each row
    lists which of ROLE_EXPECTED_COMPONENTS[role] element_types are present
    ANYWHERE in that document's own Layer 0 elements — not just the specific
    element(s) Phase 3 happened to route into THIS slot. A lesson plan's
    assessment_checkpoint element may have been independently routed to fulfill
    a separate exit_ticket slot; the lesson plan document still HAS an
    assessment part, so judging only the routed subset would be unfair to it."""
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []

    for f in findings:
        role = f.get("role")
        if f.get("status") != "FULFILLED" or role not in ROLE_EXPECTED_COMPONENTS:
            continue
        doc_ids = sorted(
            {
                ledger_by_id[eid]["doc_id"]
                for eid in f.get("fulfilled_by", [])
                if eid in ledger_by_id
            }
        )
        for doc_id in doc_ids:
            key = (doc_id, role)
            if key in seen:
                continue
            seen.add(key)

            doc_elements = elements_by_doc.get(doc_id, [])
            present_types: set[str] = set()
            for e in doc_elements:
                present_types |= _element_types(e)
            expected = ROLE_EXPECTED_COMPONENTS[role]
            present_components = sorted(expected & present_types)
            missing_components = sorted(expected - present_types)

            components_present = []
            for component in present_components:
                # First matching element is the citation — same "one representative
                # citation" convention as synthesize.py's mismatch grouping.
                match = next(
                    (e for e in doc_elements if component in _element_types(e)), None
                )
                components_present.append(
                    {
                        "component": component,
                        "element_id": match["element_id"] if match else None,
                        "excerpt": (match.get("excerpt") or "") if match else "",
                    }
                )

            rows.append(
                {
                    "doc_id": doc_id,
                    "role": role,
                    "taxonomy_version": LAYER2_TAXONOMY_VERSION,
                    "components_expected": sorted(expected),
                    "components_present": components_present,
                    "components_missing": missing_components,
                    "status": "COMPLETE" if not missing_components else "INCOMPLETE",
                }
            )

    rows.sort(key=lambda r: (r["status"] != "INCOMPLETE", r["doc_id"], r["role"]))
    return rows


def build_layer2_report_md(
    project_id: str, rows: list[dict], only_units: list[str] | None
) -> str:
    complete = sum(1 for r in rows if r["status"] == "COMPLETE")
    incomplete = [r for r in rows if r["status"] == "INCOMPLETE"]

    detail = (
        "\n".join(
            f"- [{r['role']}] {r['doc_id']}: missing {', '.join(r['components_missing'])} "
            f"(has {', '.join(c['component'] for c in r['components_present']) or 'none'})"
            for r in incomplete
        )
        or "(none)"
    )

    return f"""# Layer 2 Report

**Status:** SUCCESS
**Project:** {project_id}
**Scope:** {','.join(only_units) if only_units else "all units"}
**Taxonomy version:** {LAYER2_TAXONOMY_VERSION}
**Roles checked:** {', '.join(sorted(ROLE_EXPECTED_COMPONENTS))}
**Documents judged:** {len(rows)}
**COMPLETE:** {complete}
**INCOMPLETE:** {len(incomplete)}

## Artifacts
- `findings.json` — one row per (doc_id, role) that Layer 1 confirmed FULFILLED,
  with which of that role's expected internal components (Bet 10 element_type
  taxonomy) are present/missing, citing the first matching Layer 0 element for
  each present component.

## INCOMPLETE detail
{detail}
"""


def run_layer2(project_id: str, only_units: list[str] | None = None) -> Path:
    root = project_dir(project_id)
    manifest = load_manifest(root / "manifest.yaml")
    ledger = load_ledger(project_id)
    findings = load_layer1_findings(project_id)

    ledger_by_id = {e["element_id"]: e for e in ledger}
    elements_by_doc: dict[str, list[dict]] = defaultdict(list)
    for e in ledger:
        elements_by_doc[e["doc_id"]].append(e)

    if only_units:
        unknown = [u for u in only_units if u not in manifest["units"]]
        if unknown:
            raise KeyError(f"Unknown unit(s) in manifest: {unknown}")
        scoped_findings = [f for f in findings if f.get("unit_id") in only_units]
    else:
        scoped_findings = findings

    scope_label = f" (units={','.join(only_units)})" if only_units else ""
    log(f"Layer 2: {len(scoped_findings)} FULFILLED finding(s) in scope{scope_label}")

    new_rows = compute_completeness(scoped_findings, ledger_by_id, elements_by_doc)

    # Carry forward untouched units' already-computed rows — same discipline as
    # layer1.py's --only-unit carry-forward (a scoped run must ADD/UPDATE units it
    # touches, never silently drop other units' already-good findings). Touched
    # doc_ids = manifest-declared documents of the units in scope, UNION any doc_id
    # that actually produced a row this run (covers cross-unit-cited documents too).
    l2_dir = root / "layer2"
    findings_path = l2_dir / "findings.json"
    carry_forward: list[dict] = []
    if only_units and findings_path.is_file():
        touched_doc_ids = {
            doc_id_from_filename(p)
            for uid in only_units
            for p in manifest["units"][uid].get("documents", [])
        }
        touched_doc_ids |= {r["doc_id"] for r in new_rows}
        existing_rows = json.loads(findings_path.read_text())
        carry_forward = [r for r in existing_rows if r["doc_id"] not in touched_doc_ids]

    all_rows = new_rows + carry_forward

    l2_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(findings_path, json.dumps(all_rows, indent=2))
    atomic_write(
        l2_dir / "REPORT.md", build_layer2_report_md(project_id, all_rows, only_units)
    )

    complete = sum(1 for r in all_rows if r["status"] == "COMPLETE")
    incomplete = sum(1 for r in all_rows if r["status"] == "INCOMPLETE")
    log(
        f"Layer 2 done: {len(all_rows)} document(s) judged ({complete} complete, {incomplete} incomplete) -> {l2_dir}"
    )
    return l2_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 2: check Layer-1-confirmed role-fulfilling documents for expected internal components"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--only-unit",
        help="Restrict this run to one or more units, comma-separated (matches layer1.py --only-unit)",
    )
    args = parser.parse_args()

    try:
        validate_slug_id(args.project, "project id")
        only_units = None
        if args.only_unit:
            only_units = [u.strip() for u in args.only_unit.split(",") if u.strip()]
            for u in only_units:
                validate_slug_id(u, "unit id")
        run_layer2(args.project, only_units=only_units)
    except Exception as e:
        log(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
