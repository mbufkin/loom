#!/usr/bin/env python3
"""
zen_smoke.py — one-call connectivity smoke test for a hosted model backend.

Proves the plumbing (endpoint + bearer auth + payload shape + JSON parse) works
BEFORE spending a full pipeline run on it. Backend is chosen entirely by config, so
this same script smoke-tests the local server or OpenCode Zen depending on LOOM_CONFIG.

Usage (OpenCode Zen / Big Pickle):
    export OPENCODE_API_KEY=sk-...
    LOOM_CONFIG=config.zen.yaml python3 experiments/zen_smoke.py

Usage (local llama-server, the default):
    python3 experiments/zen_smoke.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_lib import load_config, model_chat, parse_model_json  # noqa: E402


def main() -> int:
    cfg = load_config()
    m = cfg.get("models", {})
    url = m.get("analyst_url", "?")
    model = m.get("analyst_model", "?")
    key_env = m.get("api_key_env")

    provider = str(m.get("provider") or "").strip() or "(openai-compatible)"
    print(f"Backend under test:")
    print(f"  config     : {os.environ.get('LOOM_CONFIG', 'config.yaml')}")
    print(f"  provider   : {provider}")
    print(f"  url        : {url}")
    print(f"  model      : {model}")
    if m.get("model_params"):
        print(f"  params     : {m.get('model_params')}")
    print(f"  auth       : {'Bearer $' + key_env if key_env else '(none — local)'}")
    print(f"  repeat_pen : {m.get('send_repeat_penalty', True)}")
    # Cursor SDK can also resolve ~/.pi/agent/auth.json when the env var is empty.
    if key_env and not os.environ.get(key_env) and provider not in ("cursor_sdk", "cursor"):
        print(f"\n✗ {key_env} is not set. Run:  export {key_env}=sk-...")
        return 2

    # A deliberately trivial structured-output ask — enough to confirm the model
    # answers, honors "JSON only", and that we can parse it (the pipeline's contract).
    messages = [
        {"role": "system", "content": "You reply with strict JSON and nothing else."},
        {
            "role": "user",
            "content": 'Return exactly this JSON with your own model name filled in: '
            '{"ok": true, "model": "<name>", "can_do_json": true}',
        },
    ]

    print("\n→ sending one chat completion…")
    t0 = time.time()
    try:
        resp = model_chat(cfg, "analyst", messages, step="zen-smoke", max_tokens=200)
    except Exception as e:  # noqa: BLE001 — this is the whole point of a smoke test
        print(f"✗ call failed after {time.time() - t0:.1f}s: {e}")
        return 1
    dt = time.time() - t0

    content = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    print(f"✓ responded in {dt:.1f}s  (usage: {usage or 'n/a'})")
    print(f"\nRaw content:\n{content}\n")

    try:
        parsed = parse_model_json(content, context="zen-smoke")
        print(f"✓ JSON parsed OK: {parsed}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"⚠ model answered but JSON did not parse ({e}) — usable but noisy.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
