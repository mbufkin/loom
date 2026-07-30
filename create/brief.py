"""Phase 1 — deterministic create briefs (checklists, not finished lessons).

Briefs live under projects/<id>/create/briefs/<gap_id>.md and are explicitly
labeled create_workspace so they never look like district curriculum.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from create.decisions import create_dir

# Role → checklist prompts. Keep short; humans fill the real content.
ROLE_CHECKLISTS: dict[str, list[str]] = {
    "lesson_content": [
        "Learning intention / observable outcome for this day",
        "Hook or engage (2–5 min)",
        "Direct instruction or model (key concepts)",
        "Guided practice with checks for understanding",
        "Independent / applied practice",
        "Closure / summary",
        "Materials & TEKS (or local standards) citations if known",
    ],
    "exit_ticket": [
        "1–3 prompts that check today's learning intention",
        "Expected evidence of mastery (what a strong answer looks like)",
        "Time box (usually 3–5 minutes)",
    ],
    "lesson_plan": [
        "Objectives / success criteria",
        "Standards alignment",
        "Materials & logistics",
        "Lesson sequence (open → teach → practice → close)",
        "Differentiation / supports notes",
        "Assessment plan",
    ],
    "quiz": [
        "Item count and point values",
        "Mix of recall + application items",
        "Answer key linkage (or note that answer_key is a separate gap)",
        "Directions for students",
    ],
    "answer_key": [
        "Correct answers keyed to each item",
        "Partial-credit guidance where needed",
        "Reference to the quiz / assessment it supports",
    ],
    "rubric": [
        "Criteria (rows) with clear descriptors",
        "Performance levels (columns)",
        "What 'proficient' looks like in student work",
    ],
    "worksheet": [
        "Clear student directions",
        "Practice items tied to the day's objective",
        "Space for work / response",
    ],
}


def _checklist_for(label: str, kind: str) -> list[str]:
    if label in ROLE_CHECKLISTS:
        return ROLE_CHECKLISTS[label]
    if kind == "component":
        return [
            f"Locate or author evidence for packet component: {label}",
            "Cite the source file once present",
            "Confirm it matches the declared packet type",
        ]
    if kind == "artifact_required":
        return [
            f"Satisfy artifact requirement: {label}",
            "Add the missing section or criterion evidence",
            "Keep existing artifact identity; do not invent a new unit",
        ]
    return [
        f"Define the missing element: {label}",
        "Align to unit learning intention",
        "Keep scope to this locus only",
        "Mark ready for human review before any promote to sources/",
    ]


def write_brief(project_dir: Path, gap: dict) -> Path:
    create_dir(project_dir)
    gap_id = gap["gap_id"]
    path = project_dir / "create" / "briefs" / f"{gap_id}.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checks = _checklist_for(str(gap.get("label")), str(gap.get("kind")))
    lines = [
        "<!-- create_workspace: brief — NOT district curriculum -->",
        f"# Create brief · `{gap.get('label')}`",
        "",
        f"- **project:** `{gap.get('project_id')}`",
        f"- **unit:** {gap.get('unit_title')} (`{gap.get('unit_id')}`)",
        f"- **kind:** {gap.get('kind')}",
        f"- **locus:** `{gap.get('locus')}`",
        f"- **pattern:** {gap.get('pattern')}",
        f"- **gap_id:** `{gap_id}`",
        f"- **generated:** {now}",
        "",
        "## Why this is open",
        "",
        gap.get("reasoning") or "_No reasoning attached from the auditor._",
        "",
        "## Checklist (human completes)",
        "",
    ]
    for item in checks:
        lines.append(f"- [ ] {item}")
    lines += [
        "",
        "## Neighboring evidence (operator fills)",
        "",
        "_Paste short excerpts or file paths from the audited pack that this "
        "element should align with. Draft assist may only use what you put here._",
        "",
        "## Decision",
        "",
        f"Current: `{gap.get('decision') or 'unset'}` — Author / Pull / Remove",
        "",
        "## Next",
        "",
        "1. Complete checklist or pull the missing file from drive.",
        "2. Optional: request a **DRAFT_UNVERIFIED** assist (Cursor, supervised).",
        "3. Promote to `sources/` only after human accept, then re-audit.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def read_brief(project_dir: Path, gap_id: str) -> str | None:
    path = project_dir / "create" / "briefs" / f"{gap_id}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def save_brief_text(project_dir: Path, gap_id: str, text: str) -> Path:
    """Persist operator edits to an existing (or new) brief file."""
    create_dir(project_dir)
    if not (text or "").strip():
        raise ValueError("brief text is empty")
    path = project_dir / "create" / "briefs" / f"{gap_id}.md"
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path
