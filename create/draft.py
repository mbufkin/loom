"""Phase 2 — supervised draft assist via Cursor SDK (Pi API key for now).

Doctrine: drafts are DRAFT_UNVERIFIED, written only under create/drafts/, never
auto-promoted into sources/. Human must accept.

Best practice: pass api_key explicitly, use one-shot Agent.prompt so disposal
is automatic, and log run metadata under create/logs/ for traceability.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from create.auth import cursor_api_key, key_source
from create.brief import read_brief, write_brief
from create.decisions import create_dir

DEFAULT_MODEL = "composer-2.5"
MAX_CONTEXT_CHARS = 12_000


def _log(project_dir: Path, gap_id: str, payload: dict) -> None:
    create_dir(project_dir)
    path = project_dir / "create" / "logs" / f"{gap_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_prompt(gap: dict, brief_md: str, context: str) -> str:
    ctx = (context or "").strip()
    if not ctx:
        ctx = "(none provided — draft a minimal scaffold only; mark unknowns)"
    return f"""You are helping a curriculum operator fill ONE missing element.
This is a supervised draft for a local create workspace — NOT published curriculum.

Rules:
- Output ONLY markdown for the missing element.
- First line must be exactly: <!-- DRAFT_UNVERIFIED -->
- Do not edit files. Do not call tools. Do not invent TEKS codes you cannot justify.
- Stay scoped to this gap only.
- If evidence is thin, write a clear scaffold with TODO markers.

Gap:
- unit: {gap.get('unit_title')} ({gap.get('unit_id')})
- kind: {gap.get('kind')}
- label: {gap.get('label')}
- locus: {gap.get('locus')}
- pattern: {gap.get('pattern')}
- auditor reasoning: {gap.get('reasoning') or 'n/a'}

Brief / checklist:
---
{brief_md[:MAX_CONTEXT_CHARS]}
---

Allowed context excerpts (operator-supplied; do not assume more):
---
{ctx[:MAX_CONTEXT_CHARS]}
---
"""


def draft_gap(
    project_dir: Path,
    gap: dict,
    *,
    context: str = "",
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run Cursor Agent.prompt and write create/drafts/<gap_id>.md."""
    create_dir(project_dir)
    gap_id = gap["gap_id"]

    # Brief is required context for a useful draft; generate if missing.
    brief_md = read_brief(project_dir, gap_id)
    if not brief_md:
        write_brief(project_dir, gap)
        brief_md = read_brief(project_dir, gap_id) or ""

    # Refuse empty auditor gap identity — prevents blank "invent a unit" prompts.
    if not gap.get("label") or not gap.get("unit_id"):
        raise ValueError("gap missing label/unit_id — refuse draft")

    api_key = cursor_api_key()
    prompt = _build_prompt(gap, brief_md, context)

    try:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions
    except ImportError as e:
        raise RuntimeError(
            "cursor-sdk not installed — use .venv/bin/python ui/server.py "
            "after `pip install cursor-sdk`"
        ) from e

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cwd = str(project_dir / "create")

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=cwd),
            ),
        )
    except CursorAgentError as err:
        _log(
            project_dir,
            gap_id,
            {
                "at": started,
                "event": "draft_startup_error",
                "message": getattr(err, "message", str(err)),
                "retryable": getattr(err, "is_retryable", None),
                "key_source": key_source(),
                "model": model,
            },
        )
        raise RuntimeError(
            f"Cursor draft failed to start: {getattr(err, 'message', err)}"
        ) from err

    status = getattr(result, "status", None)
    text = getattr(result, "result", None) or ""
    run_id = getattr(result, "id", None)

    if status == "error" or not str(text).strip():
        _log(
            project_dir,
            gap_id,
            {
                "at": started,
                "event": "draft_run_error",
                "status": status,
                "run_id": run_id,
                "key_source": key_source(),
                "model": model,
            },
        )
        raise RuntimeError(f"Cursor draft run failed (status={status}, run={run_id})")

    body = str(text).strip()
    # Strip accidental fenced wrappers if the model wraps the whole reply.
    fence = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", body)
    if fence:
        body = fence.group(1).strip()
    if not body.startswith("<!-- DRAFT_UNVERIFIED"):
        body = "<!-- DRAFT_UNVERIFIED -->\n\n" + body

    header = (
        f"<!-- create_workspace draft · gap_id={gap_id} · model={model} "
        f"· at={started} · run={run_id} -->\n"
    )
    out_path = project_dir / "create" / "drafts" / f"{gap_id}.md"
    out_path.write_text(header + body + "\n", encoding="utf-8")

    _log(
        project_dir,
        gap_id,
        {
            "at": started,
            "event": "draft_ok",
            "status": status,
            "run_id": run_id,
            "key_source": key_source(),
            "model": model,
            "chars": len(body),
            "path": str(out_path.relative_to(project_dir)),
        },
    )
    return {
        "gap_id": gap_id,
        "path": f"create/drafts/{gap_id}.md",
        "model": model,
        "run_id": run_id,
        "key_source": key_source(),
        "chars": len(body),
        "text": body,
    }


def read_draft(project_dir: Path, gap_id: str) -> str | None:
    path = project_dir / "create" / "drafts" / f"{gap_id}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def save_draft_text(project_dir: Path, gap_id: str, text: str) -> Path:
    """Persist operator edits. Keeps DRAFT_UNVERIFIED watermark if stripped."""
    create_dir(project_dir)
    body = (text or "").strip()
    if not body:
        raise ValueError("draft text is empty")
    if "DRAFT_UNVERIFIED" not in body.split("\n", 1)[0]:
        body = "<!-- DRAFT_UNVERIFIED -->\n\n" + body
    path = project_dir / "create" / "drafts" / f"{gap_id}.md"
    path.write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")
    _log(
        project_dir,
        gap_id,
        {
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "draft_saved",
            "chars": len(body),
            "path": f"create/drafts/{gap_id}.md",
        },
    )
    return path
