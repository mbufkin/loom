#!/usr/bin/env python3
"""
packet_types.py — declared curriculum "packet type" + per-unit completeness.

This is the COMPLETENESS half of the unit heatmap's two-axis design (the other
half, QUALITY, lives in unit_rung.unit_band). A packet type is DECLARED by the
human in the project manifest (`packet_type:`), never inferred, and it selects
which checklist a unit's documents are measured against.

Everything here is pure + deterministic + offline (no model): it maps document
roles (from the filename router, audit_lib.classify_doc_type) onto a per-type
checklist of expected components and reports how many slots are filled. That
number is DESCRIPTIVE — it tells a reviewer "this is a Teacher Edition and it
has 2 of its 3 expected pieces", and it must NEVER be turned into a grade.

Design notes / best practices baked in:
  - Single source of truth: the checklists live in workflows/packet_types.yaml,
    so adding a packet type is a config edit, not a code change.
  - Graceful degradation: an unknown/absent declared type falls back to the
    configured default rather than crashing, and a unit with no ledger evidence
    reports `completeness=None` (unknown) instead of a misleading 0/N.
  - Curriculum-agnostic: checklists speak in universal roles (any_of groups),
    not in one curriculum's file names.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from audit_lib import classify_doc_type, doc_id_from_filename, load_yaml, project_dir

# workflows/packet_types.yaml sits next to the other declarative specs.
SPEC_PATH = Path(__file__).resolve().parent / "workflows" / "packet_types.yaml"


@lru_cache(maxsize=1)
def load_packet_types() -> dict:
    """Load + lightly validate the packet-type registry. Cached (pure config)."""
    data = load_yaml(SPEC_PATH) or {}
    types = data.get("types") or {}
    if not types:
        raise ValueError(f"{SPEC_PATH} defines no packet types")
    default = data.get("default")
    if default not in types:
        # A default that doesn't exist is a config bug we want surfaced loudly.
        raise ValueError(f"default packet_type {default!r} not in types {list(types)}")
    for name, spec in types.items():
        comps = spec.get("components") or []
        if not comps:
            raise ValueError(f"packet type {name!r} has no components")
        for c in comps:
            if not c.get("any_of"):
                raise ValueError(f"packet type {name!r} component {c!r} has no any_of")
    return data


def default_packet_type() -> str:
    """The type used when a project doesn't declare one."""
    return load_packet_types()["default"]


def resolve_packet_type(declared: str | None) -> str:
    """Map a (possibly missing/unknown) declared value to a real type id. Declared
    beats clever, but an undeclared/typo'd value degrades to the default rather
    than exploding a whole run."""
    types = load_packet_types()["types"]
    if declared and declared in types:
        return declared
    return default_packet_type()


def packet_type_spec(declared: str | None) -> dict:
    """The resolved spec dict for a declared type, with its resolved id attached
    under `id` for convenience (the UI/report wants both id + label)."""
    tid = resolve_packet_type(declared)
    spec = dict(load_packet_types()["types"][tid])
    spec["id"] = tid
    return spec


def project_packet_type(project_id: str) -> str:
    """Read the DECLARED packet type from a project's manifest, resolved to a real
    id (default when absent). This is the one place manifest -> type happens."""
    manifest = load_yaml(project_dir(project_id) / "manifest.yaml") or {}
    return resolve_packet_type(manifest.get("packet_type"))


def present_roles_by_unit(project_id: str) -> dict[str, set[str]]:
    """For each unit, the set of document ROLES physically present in it.

    Ground truth is the Layer 0 ledger (what actually got decomposed) classified
    by the filename router — so this answers "does this unit HAVE a quiz?" rather
    than "was a quiz expected on the day grid?". Absent ledger -> empty map, so
    callers can report completeness as unknown instead of fabricating zeros."""
    root = project_dir(project_id)
    ledger_path = root / "layer0" / "ledger.json"
    if not ledger_path.is_file():
        return {}

    import json

    ledger = json.loads(ledger_path.read_text())
    manifest = load_yaml(root / "manifest.yaml") or {}

    # doc_id -> unit_id, via the same manifest keys every other stage uses.
    doc_unit: dict[str, str] = {}
    for uid, unit in (manifest.get("units") or {}).items():
        for rel in unit.get("documents") or unit.get("source_files") or []:
            doc_unit.setdefault(doc_id_from_filename(rel), uid)

    # One representative source_file per doc_id (the ledger repeats it per element).
    doc_source: dict[str, str] = {}
    for el in ledger:
        did = el.get("doc_id")
        if did and did not in doc_source:
            doc_source[did] = el.get("source_file", did)

    roles: dict[str, set[str]] = defaultdict(set)
    for did, source in doc_source.items():
        uid = doc_unit.get(did, "(unlinked)")
        roles[uid].add(classify_doc_type(source))
    return roles


def unit_completeness(present: set[str] | None, spec: dict) -> dict | None:
    """Score a unit's present roles against a packet-type spec's checklist.

    Returns a DESCRIPTIVE profile (never a grade):
        {
          "packet_type": "teacher_edition",
          "label": "Teacher Edition",
          "short": "TEACHER ED",
          "present": 2, "expected": 3,
          "components": [ {"label","present": bool,"matched": role|None,"any_of":[...]}, ... ],
          "missing": ["Check / assessment"],
        }
    `present=None` (no ledger evidence for the unit) -> return None (unknown), so
    the UI can render an honest "—" instead of "0/3"."""
    if present is None:
        return None
    comps_out = []
    filled = 0
    missing = []
    for comp in spec.get("components") or []:
        any_of = comp.get("any_of") or []
        hit = next((r for r in any_of if r in present), None)
        is_present = hit is not None
        if is_present:
            filled += 1
        else:
            missing.append(comp["label"])
        comps_out.append(
            {
                "label": comp["label"],
                "present": is_present,
                "matched": hit,
                "any_of": list(any_of),
            }
        )
    return {
        "packet_type": spec.get("id"),
        "label": spec.get("label", spec.get("id")),
        "short": spec.get("short", (spec.get("label") or "").upper()),
        "present": filled,
        "expected": len(comps_out),
        "components": comps_out,
        "missing": missing,
    }
