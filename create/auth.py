"""Load Cursor API credentials for supervised draft assist.

Priority (first wins):
1. CURSOR_API_KEY environment variable
2. ~/.pi/agent/auth.json  →  { "cursor": { "type": "api_key", "key": "..." } }

Best practice: never hardcode keys; prefer env in production, Pi auth is fine
for local G10 demos so operators don't paste secrets into config.yaml.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def cursor_api_key() -> str:
    env = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if env:
        return env

    auth_path = Path.home() / ".pi" / "agent" / "auth.json"
    if not auth_path.is_file():
        raise FileNotFoundError(
            "No CURSOR_API_KEY and no ~/.pi/agent/auth.json — "
            "set the env var or configure Pi cursor auth."
        )
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"unreadable Pi auth.json: {e}") from e

    cursor = data.get("cursor") or {}
    key = (cursor.get("key") or "").strip()
    if not key:
        raise RuntimeError("Pi auth.json has no cursor.key")
    return key


def key_source() -> str:
    """Where the active key came from (for UI status — never the key itself)."""
    if (os.environ.get("CURSOR_API_KEY") or "").strip():
        return "env:CURSOR_API_KEY"
    if (Path.home() / ".pi" / "agent" / "auth.json").is_file():
        return "pi:~/.pi/agent/auth.json"
    return "none"
