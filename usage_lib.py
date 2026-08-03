"""Per-project LLM token metering for Loom.

Educational note — how llama.cpp research stacks usually meter:
  The OpenAI-compatible `/v1/chat/completions` response already includes
  `usage: {prompt_tokens, completion_tokens, total_tokens}` (and often
  `timings`). Capture that object at the HTTP client choke point; do not
  re-tokenize locally unless `usage` is missing. Char/4 estimates are a
  fallback only, and must be labeled so rollups stay honest.

Artifacts (per project):
  projects/<id>/usage.jsonl          — one JSON object per model call
  projects/<id>/USAGE-SUMMARY.json   — rolled-up totals by step/role/source
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep this module free of audit_lib imports at load time (model_chat imports us).
BASE_DIR = Path(__file__).resolve().parent

# Rough English/code average used only when the server omits usage.
CHARS_PER_TOKEN = 4


def project_dir(project_id: str) -> Path:
    """Match audit_lib: honor LOOM_E2E_RUN so usage.jsonl stays with that A/B tree."""
    base = BASE_DIR / "projects" / project_id
    run = (os.environ.get("LOOM_E2E_RUN") or "").strip()
    if run:
        import re

        safe = re.sub(r"[^\w.\-]+", "-", run).strip("-._")[:80]
        if safe:
            return base / "e2e" / "runs" / safe
    return base

_project_id: ContextVar[str | None] = ContextVar("loom_usage_project", default=None)
_argv_scanned = False
_lock = threading.Lock()


def set_usage_project(project_id: str | None) -> None:
    """Bind subsequent model_chat calls to a projects/<id> usage log."""
    _project_id.set(project_id)
    if project_id:
        os.environ["LOOM_USAGE_PROJECT"] = project_id
    elif "LOOM_USAGE_PROJECT" in os.environ:
        del os.environ["LOOM_USAGE_PROJECT"]


def get_usage_project() -> str | None:
    """Resolve project id: context → env → `--project` on argv (lazy)."""
    pid = _project_id.get()
    if pid:
        return pid
    env = os.environ.get("LOOM_USAGE_PROJECT")
    if env:
        return env
    _scan_argv_for_project()
    return _project_id.get() or os.environ.get("LOOM_USAGE_PROJECT")


def _scan_argv_for_project() -> None:
    """Best-effort: scripts almost always expose `--project <id>`."""
    global _argv_scanned
    if _argv_scanned:
        return
    _argv_scanned = True
    argv = sys.argv
    try:
        i = argv.index("--project")
    except ValueError:
        return
    if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
        set_usage_project(argv[i + 1])


def usage_log_path(project_id: str | None = None) -> Path:
    pid = project_id or get_usage_project()
    if pid:
        return project_dir(pid) / "usage.jsonl"
    return BASE_DIR / "logs" / "usage-unscoped.jsonl"


def usage_summary_path(project_id: str | None = None) -> Path:
    pid = project_id or get_usage_project()
    if not pid:
        return BASE_DIR / "logs" / "USAGE-SUMMARY-unscoped.json"
    return project_dir(pid) / "USAGE-SUMMARY.json"


def approx_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def approx_tokens_from_messages(messages: list) -> int:
    total = 0
    for m in messages or []:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            # multimodal / content parts
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += len(part["text"])
                else:
                    total += len(str(part))
        elif content is not None:
            total += len(str(content))
    return approx_tokens_from_text("x" * total) if total else 0


def extract_openai_usage(resp: dict) -> tuple[dict[str, int | None], str]:
    """Return (usage_fields, source) from an OpenAI-compatible response body.

    Prefer server `usage`. Fall back to llama.cpp `timings.prompt_n` /
    `timings.predicted_n` when present. Otherwise caller should estimate.
    """
    usage = resp.get("usage") if isinstance(resp, dict) else None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        if prompt is not None or completion is not None or total is not None:
            p = int(prompt or 0)
            c = int(completion or 0)
            t = int(total) if total is not None else p + c
            cached = None
            details = usage.get("prompt_tokens_details")
            if isinstance(details, dict) and details.get("cached_tokens") is not None:
                cached = int(details["cached_tokens"])
            return (
                {
                    "prompt_tokens": p,
                    "completion_tokens": c,
                    "total_tokens": t,
                    "cached_tokens": cached,
                },
                "api",
            )

    timings = resp.get("timings") if isinstance(resp, dict) else None
    if isinstance(timings, dict):
        # llama.cpp server: prompt_n / predicted_n are token counts.
        pn = timings.get("prompt_n")
        pred = timings.get("predicted_n")
        if pn is not None or pred is not None:
            p = int(pn or 0)
            c = int(pred or 0)
            return (
                {
                    "prompt_tokens": p,
                    "completion_tokens": c,
                    "total_tokens": p + c,
                    "cached_tokens": int(timings["cache_n"])
                    if timings.get("cache_n") is not None
                    else None,
                },
                "timings",
            )

    return (
        {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
        },
        "missing",
    )


def extract_completion_text(resp: dict) -> str:
    try:
        choices = resp.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        parts = [msg.get("content") or ""]
        # Reasoning models may put tokens in reasoning_content (still generated).
        rc = msg.get("reasoning_content")
        if isinstance(rc, str) and rc:
            parts.append(rc)
        return "".join(parts)
    except (AttributeError, IndexError, TypeError):
        return ""


def record_model_call(
    *,
    role: str,
    step: str,
    model: str,
    messages: list,
    resp: dict | None,
    elapsed_ms: float,
    ok: bool = True,
    error: str | None = None,
    project_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict:
    """Append one usage row. Safe to call from any thread; never raises to callers."""
    try:
        pid = project_id or get_usage_project()
        usage_fields, source = (
            extract_openai_usage(resp) if isinstance(resp, dict) else (
                {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "cached_tokens": None,
                },
                "missing",
            )
        )
        if source == "missing":
            prompt_est = approx_tokens_from_messages(messages)
            completion_est = approx_tokens_from_text(
                extract_completion_text(resp) if isinstance(resp, dict) else ""
            )
            usage_fields = {
                "prompt_tokens": prompt_est,
                "completion_tokens": completion_est,
                "total_tokens": prompt_est + completion_est,
                "cached_tokens": None,
            }
            source = "estimate"

        timings = None
        if isinstance(resp, dict) and isinstance(resp.get("timings"), dict):
            t = resp["timings"]
            timings = {
                k: t.get(k)
                for k in (
                    "prompt_ms",
                    "predicted_ms",
                    "prompt_per_second",
                    "predicted_per_second",
                    "cache_n",
                )
                if k in t
            }

        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "project": pid or "_unscoped",
            "role": role,
            "step": step,
            "model": model,
            "ok": ok,
            "error": error,
            "elapsed_ms": round(elapsed_ms, 1),
            "source": source,
            "prompt_tokens": usage_fields["prompt_tokens"],
            "completion_tokens": usage_fields["completion_tokens"],
            "total_tokens": usage_fields["total_tokens"],
            "cached_tokens": usage_fields["cached_tokens"],
            "timings": timings,
        }
        if extra:
            row["extra"] = extra

        path = usage_log_path(pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        return row
    except Exception as e:  # noqa: BLE001 — metering must never break audits
        try:
            from audit_lib import log

            log(f"WARN: usage metering failed: {e}")
        except Exception:
            pass
        return {}


def record_cursor_run_usage(
    *,
    project_id: str | None,
    step: str,
    model: str,
    run_id: str | None,
    usage: dict | None,
    elapsed_ms: float,
    ok: bool = True,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict:
    """Record Cursor SDK RunResult.usage (inputTokens/outputTokens/...)."""
    try:
        pid = project_id or get_usage_project()
        source = "cursor_sdk"
        prompt = completion = total = cached = reasoning = None
        if isinstance(usage, dict) and usage:
            # SDK TokenUsage shape
            prompt = usage.get("inputTokens", usage.get("prompt_tokens"))
            completion = usage.get("outputTokens", usage.get("completion_tokens"))
            total = usage.get("totalTokens", usage.get("total_tokens"))
            cached = usage.get("cacheReadTokens", usage.get("cached_tokens"))
            reasoning = usage.get("reasoningTokens")
            if prompt is not None:
                prompt = int(prompt)
            if completion is not None:
                completion = int(completion)
            if total is not None:
                total = int(total)
            elif prompt is not None or completion is not None:
                total = int(prompt or 0) + int(completion or 0)
            if cached is not None:
                cached = int(cached)
            if reasoning is not None:
                reasoning = int(reasoning)
        else:
            source = "missing"
            prompt = completion = total = 0

        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "project": pid or "_unscoped",
            "role": "cursor_agent",
            "step": step,
            "model": model,
            "ok": ok,
            "error": error,
            "elapsed_ms": round(elapsed_ms, 1),
            "source": source,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "cached_tokens": cached,
            "reasoning_tokens": reasoning,
            "run_id": run_id,
            "timings": None,
        }
        if extra:
            row["extra"] = extra

        path = usage_log_path(pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row
    except Exception as e:  # noqa: BLE001
        try:
            from audit_lib import log

            log(f"WARN: cursor usage metering failed: {e}")
        except Exception:
            pass
        return {}


def read_usage_rows(project_id: str | None = None) -> list[dict]:
    path = usage_log_path(project_id)
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write_usage_summary(project_id: str | None = None) -> dict:
    """Roll usage.jsonl into USAGE-SUMMARY.json. Returns the summary dict."""
    pid = project_id or get_usage_project() or "_unscoped"
    rows = read_usage_rows(project_id or (None if pid == "_unscoped" else pid))
    by_step: dict[str, dict[str, int]] = {}
    by_role: dict[str, dict[str, int]] = {}
    by_source: dict[str, int] = {}
    totals = {
        "n_calls": 0,
        "n_ok": 0,
        "n_error": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "elapsed_ms": 0.0,
    }

    def _bump(bucket: dict[str, dict[str, int]], key: str, row: dict) -> None:
        slot = bucket.setdefault(
            key,
            {
                "n_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        slot["n_calls"] += 1
        slot["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        slot["completion_tokens"] += int(row.get("completion_tokens") or 0)
        slot["total_tokens"] += int(row.get("total_tokens") or 0)

    for row in rows:
        totals["n_calls"] += 1
        if row.get("ok", True):
            totals["n_ok"] += 1
        else:
            totals["n_error"] += 1
        totals["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(row.get("completion_tokens") or 0)
        totals["total_tokens"] += int(row.get("total_tokens") or 0)
        totals["cached_tokens"] += int(row.get("cached_tokens") or 0)
        totals["reasoning_tokens"] += int(row.get("reasoning_tokens") or 0)
        totals["elapsed_ms"] += float(row.get("elapsed_ms") or 0)
        _bump(by_step, str(row.get("step") or "unknown"), row)
        _bump(by_role, str(row.get("role") or "unknown"), row)
        src = str(row.get("source") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    summary = {
        "project": pid,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "usage_log": str(usage_log_path(None if pid == "_unscoped" else pid)),
        "totals": totals,
        "by_source": by_source,
        "by_role": by_role,
        "by_step": by_step,
    }
    out = usage_summary_path(None if pid == "_unscoped" else pid)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


# Kept for timing helpers used by model_chat.
def monotonic_ms() -> float:
    return time.monotonic() * 1000.0
