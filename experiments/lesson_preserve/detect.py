#!/usr/bin/env python3
"""
detect.py — Find lesson-plan documents for a unit (preserve identity, don't remake).

Sources of truth (v1):
  1. layer0/route-map.json workflow_id == lesson_plan
  2. Filename / title cues (Lesson_Plan, Lesson Plan, …)
  3. Layer 0 regex_doc_type_prior == lesson_plan
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from audit_lib import doc_id_from_filename, project_dir

LP_NAME_RE = re.compile(
    r"lesson[_\s-]*plan|daily[_\s-]*lesson",
    re.I,
)


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return {} if path.suffix == ".json" else []
    return json.loads(path.read_text(encoding="utf-8"))


def load_route_workflow_by_doc(project_id: str) -> dict[str, str]:
    root = project_dir(project_id)
    rm = _load_json(root / "layer0" / "route-map.json")
    out: dict[str, str] = {}
    for r in rm.get("routes") or []:
        did = r.get("doc_id")
        if did:
            out[str(did)] = str(r.get("workflow_id") or "")
    return out


def load_doc_type_priors(project_id: str) -> dict[str, str]:
    """doc_id → first regex_doc_type_prior seen in ledger."""
    root = project_dir(project_id)
    ledger = _load_json(root / "layer0" / "ledger.json")
    if not isinstance(ledger, list):
        return {}
    priors: dict[str, str] = {}
    for e in ledger:
        did = e.get("doc_id")
        prior = e.get("regex_doc_type_prior")
        if did and prior and did not in priors:
            priors[str(did)] = str(prior)
    return priors


def is_lesson_plan_doc(
    *,
    doc_id: str,
    source_file: str,
    title: str,
    route_workflow: str | None,
    doc_type_prior: str | None,
) -> tuple[bool, list[str]]:
    """Return (is_lp, reasons)."""
    reasons: list[str] = []
    if route_workflow == "lesson_plan":
        reasons.append("route_map:lesson_plan")
    if (doc_type_prior or "").lower() == "lesson_plan":
        reasons.append("ledger_prior:lesson_plan")
    blob = f"{source_file} {title}"
    if LP_NAME_RE.search(blob):
        reasons.append("filename_or_title_cue")
    return (bool(reasons), reasons)


def detect_unit_lesson_plans(
    project_id: str,
    unit_id: str,
    documents: list[str],
    *,
    title_map: dict[str, str] | None = None,
) -> list[dict]:
    """Build preserved LP records for one unit (order = manifest order)."""
    title_map = title_map or {}
    routes = load_route_workflow_by_doc(project_id)
    priors = load_doc_type_priors(project_id)
    found: list[dict] = []
    for rel in documents:
        did = doc_id_from_filename(rel)
        src = Path(rel).name
        title = title_map.get(did) or src
        wf = routes.get(did)
        prior = priors.get(did)
        ok, reasons = is_lesson_plan_doc(
            doc_id=did,
            source_file=src,
            title=title,
            route_workflow=wf,
            doc_type_prior=prior,
        )
        if not ok:
            continue
        found.append(
            {
                "doc_id": did,
                "source_file": src,
                "source_rel": rel,
                "title": title,
                "route_workflow": wf or None,
                "detect_reasons": reasons,
            }
        )
    return found
