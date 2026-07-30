"""Persist Author / Pull / Remove decisions under projects/<id>/create/.

Stored as YAML list so humans can edit/diff. Best practice: write atomically
(temp + rename) so a crash mid-save never corrupts the queue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

DECISIONS_NAME = "decisions.yaml"
ALLOWED = {"author", "pull", "remove", None}


def create_dir(project_dir: Path) -> Path:
    d = project_dir / "create"
    d.mkdir(parents=True, exist_ok=True)
    (d / "briefs").mkdir(exist_ok=True)
    (d / "drafts").mkdir(exist_ok=True)
    (d / "logs").mkdir(exist_ok=True)
    return d


def _path(project_dir: Path) -> Path:
    return create_dir(project_dir) / DECISIONS_NAME


def load_decisions(project_dir: Path) -> dict[str, dict]:
    """Return {gap_id: {decision, note, actor, updated_at}}."""
    path = project_dir / "create" / DECISIONS_NAME
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    items = data.get("decisions") if isinstance(data, dict) else data
    out: dict[str, dict] = {}
    if isinstance(items, list):
        for row in items:
            if isinstance(row, dict) and row.get("gap_id"):
                out[str(row["gap_id"])] = row
    elif isinstance(items, dict):
        out = {str(k): v for k, v in items.items() if isinstance(v, dict)}
    return out


def save_decision(
    project_dir: Path,
    gap_id: str,
    decision: str | None,
    note: str = "",
    actor: str = "operator",
) -> dict[str, Any]:
    if decision is not None and decision not in ("author", "pull", "remove"):
        raise ValueError("decision must be author | pull | remove | null")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_dec = load_decisions(project_dir)
    row = {
        "gap_id": gap_id,
        "decision": decision,
        "note": note or "",
        "actor": actor,
        "updated_at": now,
    }
    all_dec[gap_id] = row

    payload = {
        "version": 1,
        "updated_at": now,
        "decisions": sorted(all_dec.values(), key=lambda r: r.get("gap_id") or ""),
    }
    path = _path(project_dir)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    return row
