"""Create tree aggregators — doctrine: unit matrix + UbD stages.

Primary: unit completeness matrix (Stage 1→2→3).
Secondary: by-element systemic patterns (list_roles).
Legacy: list_units / list_unit_slots still available.

See docs/CREATE-WORKFLOW.md.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from create.decisions import load_decisions
from create.gaps import _read_json, _role_patterns, _unit_titles, role_gap_id

# Human labels for the create tree (Review uses a similar map in UnitDetail).
ROLE_LABELS: dict[str, str] = {
    "exit_ticket": "Exit ticket",
    "quiz": "Quiz",
    "answer_key": "Answer key",
    "rubric": "Rubric",
    "worksheet": "Worksheet",
    "project_work": "Project",
    "presentation": "Slides",
    "game_activity": "Activity",
    "lab_activity": "Lab",
    "flex_day": "Flex day",
    "lesson_content": "Lesson content",
    "lesson_plan": "Lesson plan",
    "other": "Other",
}

# UbD-ordered bands (docs/CREATE-WORKFLOW.md). Unknown roles → Stage 3.
UBD_STAGES: list[dict[str, Any]] = [
    {
        "id": 1,
        "key": "goals",
        "label": "Stage 1 · Goals / plan",
        "roles": ("lesson_plan",),
    },
    {
        "id": 2,
        "key": "evidence",
        "label": "Stage 2 · Evidence",
        "roles": ("quiz", "rubric", "answer_key", "exit_ticket"),
    },
    {
        "id": 3,
        "key": "learning",
        "label": "Stage 3 · Learning",
        "roles": (
            "lesson_content",
            "worksheet",
            "presentation",
            "project_work",
            "game_activity",
            "lab_activity",
            "flex_day",
            "other",
        ),
    },
]

_ROLE_TO_STAGE: dict[str, int] = {}
for _st in UBD_STAGES:
    for _r in _st["roles"]:
        _ROLE_TO_STAGE[_r] = int(_st["id"])


def role_label(role: str) -> str:
    if role in ROLE_LABELS:
        return ROLE_LABELS[role]
    return role.replace("_", " ").title()


def stage_for_role(role: str) -> int:
    """1 / 2 / 3 — unknown roles default to learning (Stage 3)."""
    return _ROLE_TO_STAGE.get(role, 3)


def _findings(project_dir: Path) -> list[dict]:
    data = _read_json(project_dir / "layer1" / "findings.json")
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def _slot_from_finding(
    row: dict,
    *,
    titles: dict[str, str],
    decisions: dict[str, dict],
    project_dir: Path,
) -> dict[str, Any] | None:
    status = str(row.get("status") or "").upper()
    role = str(row.get("role") or "")
    if not role or status not in ("MISSING", "FULFILLED"):
        return None
    unit_id = str(row.get("unit_id") or "unknown")
    locus = str(row.get("day_id") or "unit")
    gap_id = role_gap_id(unit_id, role, locus) if status == "MISSING" else None
    dec = decisions.get(gap_id) if gap_id else None
    has_brief = bool(
        gap_id and (project_dir / "create" / "briefs" / f"{gap_id}.md").is_file()
    )
    has_draft = bool(
        gap_id and (project_dir / "create" / "drafts" / f"{gap_id}.md").is_file()
    )
    return {
        "unit_id": unit_id,
        "unit_title": titles.get(unit_id, unit_id),
        "status": status,
        "locus": locus,
        "role": role,
        "role_label": role_label(role),
        "reasoning": (row.get("reasoning") or "").strip(),
        "fulfilled_by": list(row.get("fulfilled_by") or []),
        "gap_id": gap_id,
        "decision": (dec or {}).get("decision"),
        "decision_note": (dec or {}).get("note") or "",
        "has_brief": has_brief,
        "has_draft": has_draft,
    }


def _sort_slots(slots: list[dict]) -> list[dict]:
    rank = {"MISSING": 0, "FULFILLED": 1}
    slots.sort(
        key=lambda s: (
            rank.get(s["status"], 9),
            s.get("role_label") or s.get("role") or "",
            s.get("unit_title") or "",
            s.get("locus") or "",
        )
    )
    return slots


def list_roles(project_id: str, project_dir: Path) -> dict[str, Any]:
    """L1 — element types sorted by missing count (largest first)."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    patterns = _role_patterns(stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)
    findings = _findings(project_dir)

    by_role: dict[str, dict[str, int]] = defaultdict(
        lambda: {"missing": 0, "fulfilled": 0, "pending_decisions": 0}
    )
    for row in findings:
        status = str(row.get("status") or "").upper()
        role = str(row.get("role") or "")
        if not role or status not in ("MISSING", "FULFILLED"):
            continue
        if status == "MISSING":
            by_role[role]["missing"] += 1
            unit_id = str(row.get("unit_id") or "unknown")
            locus = str(row.get("day_id") or "unit")
            gid = role_gap_id(unit_id, role, locus)
            if not (decisions.get(gid) or {}).get("decision"):
                by_role[role]["pending_decisions"] += 1
        else:
            by_role[role]["fulfilled"] += 1

    roles = []
    for role, counts in by_role.items():
        roles.append(
            {
                "role": role,
                "label": role_label(role),
                "missing": counts["missing"],
                "fulfilled": counts["fulfilled"],
                "pattern": patterns.get(role, "isolated"),
                "pending_decisions": counts["pending_decisions"],
            }
        )
    roles.sort(key=lambda r: (-r["missing"], -r["fulfilled"], r["label"]))
    return {"project_id": project_id, "roles": roles}


def list_role_units(project_id: str, project_dir: Path, role: str) -> dict[str, Any]:
    """By-element L2 — unit inventory for one role: missing + present slots."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    titles = _unit_titles(project_dir, stats if isinstance(stats, dict) else None)
    patterns = _role_patterns(stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)
    findings = _findings(project_dir)

    slots: list[dict] = []
    for row in findings:
        if str(row.get("role") or "") != role:
            continue
        slot = _slot_from_finding(
            row, titles=titles, decisions=decisions, project_dir=project_dir
        )
        if slot:
            slots.append(slot)

    _sort_slots(slots)
    # For role→unit view, prefer unit title over role in secondary sort.
    slots.sort(
        key=lambda s: (
            0 if s["status"] == "MISSING" else 1,
            s.get("unit_title") or "",
            s.get("locus") or "",
        )
    )
    missing = sum(1 for s in slots if s["status"] == "MISSING")
    fulfilled = sum(1 for s in slots if s["status"] == "FULFILLED")
    return {
        "project_id": project_id,
        "role": role,
        "label": role_label(role),
        "pattern": patterns.get(role, "isolated"),
        "missing": missing,
        "fulfilled": fulfilled,
        "slots": slots,
    }


def list_units(project_id: str, project_dir: Path) -> dict[str, Any]:
    """By-unit L1 — units sorted by missing count (largest holes first)."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    titles = _unit_titles(project_dir, stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)
    findings = _findings(project_dir)

    by_unit: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "missing": 0,
            "fulfilled": 0,
            "pending_decisions": 0,
            "missing_roles": set(),
        }
    )
    for row in findings:
        status = str(row.get("status") or "").upper()
        role = str(row.get("role") or "")
        unit_id = str(row.get("unit_id") or "")
        if not unit_id or not role or status not in ("MISSING", "FULFILLED"):
            continue
        bucket = by_unit[unit_id]
        if status == "MISSING":
            bucket["missing"] += 1
            bucket["missing_roles"].add(role)
            locus = str(row.get("day_id") or "unit")
            gid = role_gap_id(unit_id, role, locus)
            if not (decisions.get(gid) or {}).get("decision"):
                bucket["pending_decisions"] += 1
        else:
            bucket["fulfilled"] += 1

    units = []
    for unit_id, counts in by_unit.items():
        missing_roles = sorted(counts["missing_roles"], key=role_label)
        units.append(
            {
                "unit_id": unit_id,
                "title": titles.get(unit_id, unit_id),
                "missing": counts["missing"],
                "fulfilled": counts["fulfilled"],
                "pending_decisions": counts["pending_decisions"],
                "missing_role_labels": [role_label(r) for r in missing_roles[:6]],
                "missing_role_count": len(missing_roles),
            }
        )
    units.sort(key=lambda u: (-u["missing"], -u["fulfilled"], u["title"]))
    return {"project_id": project_id, "units": units}


def _empty_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": st["id"],
            "key": st["key"],
            "label": st["label"],
            "missing": 0,
            "fulfilled": 0,
            "pending_decisions": 0,
            "slots": [],
        }
        for st in UBD_STAGES
    ]


def _assign_stages(slots: list[dict]) -> list[dict[str, Any]]:
    """Bucket slots into UbD stages; sort missing first within each stage."""
    stages = _empty_stages()
    by_id = {s["id"]: s for s in stages}
    for slot in slots:
        sid = stage_for_role(str(slot.get("role") or ""))
        bucket = by_id[sid]
        enriched = {**slot, "stage": sid}
        bucket["slots"].append(enriched)
        if slot["status"] == "MISSING":
            bucket["missing"] += 1
            if not slot.get("decision"):
                bucket["pending_decisions"] += 1
        else:
            bucket["fulfilled"] += 1
    for bucket in stages:
        bucket["slots"].sort(
            key=lambda s: (
                0 if s["status"] == "MISSING" else 1,
                s.get("role_label") or "",
                s.get("locus") or "",
            )
        )
    return stages


def list_unit_slots(project_id: str, project_dir: Path, unit_id: str) -> dict[str, Any]:
    """By-unit detail — flat slots + UbD stage buckets."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    titles = _unit_titles(project_dir, stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)
    findings = _findings(project_dir)

    slots: list[dict] = []
    for row in findings:
        if str(row.get("unit_id") or "") != unit_id:
            continue
        slot = _slot_from_finding(
            row, titles=titles, decisions=decisions, project_dir=project_dir
        )
        if slot:
            slots.append(slot)

    for s in slots:
        s["stage"] = stage_for_role(str(s.get("role") or ""))
    _sort_slots(slots)
    stages = _assign_stages(slots)
    missing = sum(1 for s in slots if s["status"] == "MISSING")
    fulfilled = sum(1 for s in slots if s["status"] == "FULFILLED")
    # Soft-gate signal: undecided Stage 1 holes still open.
    stage1 = stages[0]
    return {
        "project_id": project_id,
        "unit_id": unit_id,
        "title": titles.get(unit_id, unit_id),
        "missing": missing,
        "fulfilled": fulfilled,
        "slots": slots,
        "stages": stages,
        "stage1_open": stage1["pending_decisions"],
    }


def list_matrix(project_id: str, project_dir: Path) -> dict[str, Any]:
    """Primary Create home — units with UbD stage rollups, largest holes first."""
    stats = _read_json(project_dir / "output" / "aggregate-stats.json")
    titles = _unit_titles(project_dir, stats if isinstance(stats, dict) else None)
    decisions = load_decisions(project_dir)
    findings = _findings(project_dir)

    by_unit: dict[str, list[dict]] = defaultdict(list)
    for row in findings:
        slot = _slot_from_finding(
            row, titles=titles, decisions=decisions, project_dir=project_dir
        )
        if slot:
            by_unit[slot["unit_id"]].append(slot)

    units_out: list[dict] = []
    for unit_id, slots in by_unit.items():
        stages = _assign_stages(slots)
        missing = sum(1 for s in slots if s["status"] == "MISSING")
        fulfilled = sum(1 for s in slots if s["status"] == "FULFILLED")
        pending = sum(
            1
            for s in slots
            if s["status"] == "MISSING" and not s.get("decision")
        )
        units_out.append(
            {
                "unit_id": unit_id,
                "title": titles.get(unit_id, unit_id),
                "missing": missing,
                "fulfilled": fulfilled,
                "pending_decisions": pending,
                "stage1_open": stages[0]["pending_decisions"],
                "stages": [
                    {
                        "id": st["id"],
                        "key": st["key"],
                        "label": st["label"],
                        "missing": st["missing"],
                        "fulfilled": st["fulfilled"],
                        "pending_decisions": st["pending_decisions"],
                    }
                    for st in stages
                ],
            }
        )
    units_out.sort(key=lambda u: (-u["missing"], -u["fulfilled"], u["title"]))
    return {
        "project_id": project_id,
        "doctrine": "CREATE-WORKFLOW.md",
        "stage_defs": [
            {"id": s["id"], "key": s["key"], "label": s["label"]} for s in UBD_STAGES
        ],
        "units": units_out,
    }
