"""Normalize audit artifacts into a single GapItem work queue.

Primary source: layer1/findings.json MISSING rows (unit + day + role + reasoning).
Enrichment: aggregate-stats systemic/isolated classification + unit titles from
UNIT-RUNG. Artifact-rung missing_required become kind=artifact_required rows.

Best practice: keep gap_id stable (hash of unit|role|locus) so decisions survive
reloads even when list order changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from create.decisions import load_decisions


def _stable_id(unit_id: str, kind: str, label: str, locus: str) -> str:
    raw = f"{unit_id}|{kind}|{label}|{locus}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def role_gap_id(unit_id: str, role: str, locus: str) -> str:
    """Public stable id for a Layer-1 role slot (matches list_gaps kind=role)."""
    return _stable_id(unit_id, "role", role, locus)


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _role_patterns(stats: dict | None) -> dict[str, str]:
    """role -> systemic | isolated from missing_rollup.roles."""
    out: dict[str, str] = {}
    if not stats:
        return out
    roles = (stats.get("missing_rollup") or {}).get("roles") or []
    if isinstance(roles, dict):
        roles = list(roles.values())
    for row in roles:
        if not isinstance(row, dict):
            continue
        role = row.get("role")
        if not role:
            continue
        cls = (row.get("classification") or "").lower()
        if "systemic" in cls:
            out[role] = "systemic"
        elif "isolated" in cls:
            out[role] = "isolated"
    for row in stats.get("systemic_missing") or []:
        if isinstance(row, dict) and row.get("role"):
            out.setdefault(row["role"], "systemic")
    return out


def _unit_titles(project_dir: Path, stats: dict | None) -> dict[str, str]:
    titles: dict[str, str] = {}
    if stats:
        for u in stats.get("unit_rollup") or []:
            if isinstance(u, dict) and u.get("unit_id"):
                titles[u["unit_id"]] = u.get("title") or u["unit_id"]
    ur = _read_json(project_dir / "layer_unit" / "UNIT-RUNG.json") or {}
    for uid, rec in (ur.get("units") or {}).items():
        if isinstance(rec, dict):
            titles.setdefault(uid, rec.get("title") or uid)
    return titles


def list_gaps(project_id: str, project_dir: Path) -> list[dict]:
    """Build the live gap queue for a project, merging saved decisions."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    patterns = _role_patterns(stats if isinstance(stats, dict) else None)
    titles = _unit_titles(project_dir, stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)

    gaps: list[dict] = []
    seen: set[str] = set()

    findings = _read_json(project_dir / "layer1" / "findings.json")
    if isinstance(findings, list):
        for row in findings:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "").upper() != "MISSING":
                continue
            unit_id = str(row.get("unit_id") or "unknown")
            role = str(row.get("role") or "unknown")
            locus = str(row.get("day_id") or "unit")
            gap_id = _stable_id(unit_id, "role", role, locus)
            if gap_id in seen:
                continue
            seen.add(gap_id)
            dec = decisions.get(gap_id) or {}
            gaps.append(
                {
                    "gap_id": gap_id,
                    "project_id": project_id,
                    "unit_id": unit_id,
                    "unit_title": titles.get(unit_id, unit_id),
                    "kind": "role",
                    "label": role,
                    "locus": locus,
                    "pattern": patterns.get(role, "isolated"),
                    "evidence_refs": [],
                    "reasoning": (row.get("reasoning") or "").strip(),
                    "decision": dec.get("decision"),
                    "decision_note": dec.get("note") or "",
                    "updated_at": dec.get("updated_at"),
                    "has_brief": (
                        project_dir / "create" / "briefs" / f"{gap_id}.md"
                    ).is_file(),
                    "has_draft": (
                        project_dir / "create" / "drafts" / f"{gap_id}.md"
                    ).is_file(),
                }
            )

    # Completeness / component gaps from unit rung (packet checklist).
    ur = _read_json(project_dir / "layer_unit" / "UNIT-RUNG.json") or {}
    for unit_id, rec in (ur.get("units") or {}).items():
        if not isinstance(rec, dict):
            continue
        missing = (rec.get("completeness") or {}).get("missing") or []
        for label in missing:
            locus = "packet"
            kind = "component"
            gap_id = _stable_id(unit_id, kind, str(label), locus)
            if gap_id in seen:
                continue
            seen.add(gap_id)
            dec = decisions.get(gap_id) or {}
            gaps.append(
                {
                    "gap_id": gap_id,
                    "project_id": project_id,
                    "unit_id": unit_id,
                    "unit_title": titles.get(unit_id, rec.get("title") or unit_id),
                    "kind": kind,
                    "label": str(label),
                    "locus": locus,
                    "pattern": "isolated",
                    "evidence_refs": [],
                    "reasoning": "Declared packet component missing from unit evidence.",
                    "decision": dec.get("decision"),
                    "decision_note": dec.get("note") or "",
                    "updated_at": dec.get("updated_at"),
                    "has_brief": (
                        project_dir / "create" / "briefs" / f"{gap_id}.md"
                    ).is_file(),
                    "has_draft": (
                        project_dir / "create" / "drafts" / f"{gap_id}.md"
                    ).is_file(),
                }
            )

    # Artifact rung: documents with missing_required criteria.
    ar = _read_json(project_dir / "layer_artifact" / "ARTIFACT-RUNG.json") or {}
    for art in ar.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        missing_req = (art.get("presence") or {}).get("missing_required") or []
        if not missing_req:
            continue
        unit_id = str(art.get("unit_id") or "unknown")
        doc_id = str(art.get("doc_id") or "doc")
        for req in missing_req:
            label = str(req)
            gap_id = _stable_id(unit_id, "artifact_required", label, doc_id)
            if gap_id in seen:
                continue
            seen.add(gap_id)
            dec = decisions.get(gap_id) or {}
            gaps.append(
                {
                    "gap_id": gap_id,
                    "project_id": project_id,
                    "unit_id": unit_id,
                    "unit_title": titles.get(unit_id, unit_id),
                    "kind": "artifact_required",
                    "label": label,
                    "locus": doc_id,
                    "pattern": "isolated",
                    "evidence_refs": [art.get("source_file") or ""],
                    "reasoning": f"Artifact {art.get('title') or doc_id} missing required: {label}",
                    "decision": dec.get("decision"),
                    "decision_note": dec.get("note") or "",
                    "updated_at": dec.get("updated_at"),
                    "has_brief": (
                        project_dir / "create" / "briefs" / f"{gap_id}.md"
                    ).is_file(),
                    "has_draft": (
                        project_dir / "create" / "drafts" / f"{gap_id}.md"
                    ).is_file(),
                }
            )

    # Systemic first, then unit title, then label — stable operator scan order.
    rank = {"systemic": 0, "isolated": 1}

    def sort_key(g: dict) -> tuple:
        return (
            rank.get(g.get("pattern") or "", 9),
            g.get("unit_title") or "",
            g.get("label") or "",
            g.get("locus") or "",
        )

    gaps.sort(key=sort_key)
    return gaps


def get_gap(project_id: str, project_dir: Path, gap_id: str) -> dict | None:
    for g in list_gaps(project_id, project_dir):
        if g["gap_id"] == gap_id:
            return g
    return None
