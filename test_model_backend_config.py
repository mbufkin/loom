#!/usr/bin/env python3
"""Offline tests for the pluggable model-backend config (Zen experiment plumbing).

No network: requests.post is mocked. These lock the backward-compatible contract so
pointing Loom at a hosted OpenAI-compatible API (OpenCode Zen) can't silently break
the local-server default:
  - LOOM_CONFIG selects an alternate config file
  - api_key_env → Authorization: Bearer header (key from env, never from config)
  - missing key raises a helpful error
  - repeat_penalty is sent by default (local) but omitted when disabled (strict gateway)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import audit_lib  # noqa: E402


class _FakeResp:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


def _cfg(**model_over) -> dict:
    models = {
        "analyst_url": "https://example.test/v1/chat/completions",
        "analyst_model": "big-pickle",
        "verifier_url": "https://example.test/v1/chat/completions",
        "verifier_model": "big-pickle",
        "timeout_seconds": 30,
    }
    models.update(model_over)
    return {"models": models}


def _call(cfg: dict):
    """Run one mocked model_chat and return the captured requests.post kwargs."""
    fake = MagicMock(return_value=_FakeResp({"choices": [{"message": {"content": "{}"}}]}))
    with patch.object(audit_lib.requests, "post", fake):
        audit_lib.model_chat(cfg, "analyst", [{"role": "user", "content": "hi"}], "t")
    return fake.call_args


# ── LOOM_CONFIG override ─────────────────────────────────────────────────────
def test_loom_config_env_selects_alternate_file(tmp_path: Path) -> None:
    alt = tmp_path / "alt.yaml"
    alt.write_text("models:\n  analyst_url: 'http://alt'\n", encoding="utf-8")
    old = os.environ.get("LOOM_CONFIG")
    try:
        os.environ["LOOM_CONFIG"] = str(alt)
        cfg = audit_lib.load_config()
        assert cfg["models"]["analyst_url"] == "http://alt"
    finally:
        if old is None:
            os.environ.pop("LOOM_CONFIG", None)
        else:
            os.environ["LOOM_CONFIG"] = old


# ── bearer auth ──────────────────────────────────────────────────────────────
def test_auth_header_present_when_key_env_set() -> None:
    os.environ["ZEN_TEST_KEY"] = "sk-secret-123"
    try:
        args = _call(_cfg(api_key_env="ZEN_TEST_KEY", send_repeat_penalty=False))
    finally:
        os.environ.pop("ZEN_TEST_KEY", None)
    headers = args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-secret-123"


def test_missing_key_raises_helpful_error() -> None:
    os.environ.pop("ZEN_MISSING_KEY", None)
    try:
        _call(_cfg(api_key_env="ZEN_MISSING_KEY"))
        assert False, "expected RuntimeError for missing key env"
    except RuntimeError as e:
        assert "ZEN_MISSING_KEY" in str(e)


def test_no_auth_header_for_local_default() -> None:
    # No api_key_env → local server → no Authorization header at all.
    args = _call(_cfg())
    assert "Authorization" not in args.kwargs["headers"]


def test_custom_auth_header_and_raw_key_scheme() -> None:
    # Azure-style: raw key in an `api-key` header, no "Bearer " prefix.
    os.environ["AZURE_TEST_KEY"] = "azkey-999"
    try:
        args = _call(
            _cfg(
                api_key_env="AZURE_TEST_KEY",
                auth_header="api-key",
                auth_scheme="",
                send_repeat_penalty=False,
            )
        )
    finally:
        os.environ.pop("AZURE_TEST_KEY", None)
    headers = args.kwargs["headers"]
    assert headers["api-key"] == "azkey-999"  # raw, no scheme prefix
    assert "Authorization" not in headers


def test_extra_headers_are_sent() -> None:
    # OpenRouter-style static headers ride alongside auth.
    os.environ["OR_TEST_KEY"] = "or-1"
    try:
        args = _call(
            _cfg(
                api_key_env="OR_TEST_KEY",
                extra_headers={"HTTP-Referer": "https://x.test", "X-Title": "Loom"},
                send_repeat_penalty=False,
            )
        )
    finally:
        os.environ.pop("OR_TEST_KEY", None)
    headers = args.kwargs["headers"]
    assert headers["HTTP-Referer"] == "https://x.test"
    assert headers["X-Title"] == "Loom"
    assert headers["Authorization"] == "Bearer or-1"  # default scheme still applies


# ── repeat_penalty gating ────────────────────────────────────────────────────
def test_repeat_penalty_sent_by_default() -> None:
    args = _call(_cfg())  # no flag → default True (local llama needs it)
    assert args.kwargs["json"]["repeat_penalty"] == 1.15


def test_repeat_penalty_omitted_when_disabled() -> None:
    args = _call(_cfg(send_repeat_penalty=False))
    assert "repeat_penalty" not in args.kwargs["json"]


def test_cursor_model_selection_from_yaml_knobs() -> None:
    """Model id + effort/fast stay in YAML so operators can swap without code edits."""
    from audit_lib import resolve_cursor_model_selection

    sel = resolve_cursor_model_selection(
        {
            "analyst_model": "grok-4.5",
            "model_params": {"effort": "high", "fast": True},
        },
        "analyst",
    )
    assert sel["id"] == "grok-4.5"
    assert {"id": "effort", "value": "high"} in sel["params"]
    assert {"id": "fast", "value": "true"} in sel["params"]

    # Inline dict form + per-role override.
    sel2 = resolve_cursor_model_selection(
        {
            "analyst_model": {
                "id": "composer-2.5",
                "params": {"effort": "medium"},
            },
            "model_params": {"fast": False},
            "analyst_model_params": {"effort": "high"},
        },
        "analyst",
    )
    assert sel2["id"] == "composer-2.5"
    params = {p["id"]: p["value"] for p in sel2["params"]}
    assert params["effort"] == "high"
    assert params["fast"] == "false"


def test_cursor_provider_bypasses_http_and_keeps_openai_envelope() -> None:
    """provider=cursor_sdk must not POST; layers still see choices[0].message.content."""
    import types

    from audit_lib import extract_content, model_chat

    fake_result = MagicMock()
    fake_result.status = "finished"
    fake_result.result = '{"ok": true}'
    fake_result.id = "run_test_1"

    fake_mod = types.ModuleType("cursor_sdk")
    fake_mod.Agent = MagicMock(prompt=MagicMock(return_value=fake_result))
    fake_mod.AgentOptions = MagicMock(side_effect=lambda **kw: kw)
    fake_mod.LocalAgentOptions = MagicMock(side_effect=lambda **kw: kw)
    fake_mod.CursorAgentError = type("CursorAgentError", (Exception,), {})

    cfg = {
        "models": {
            "provider": "cursor_sdk",
            "analyst_model": "grok-4.5",
            "verifier_model": "grok-4.5",
            "model_params": {"effort": "high", "fast": True},
            "timeout_seconds": 60,
            "api_key_env": "CURSOR_API_KEY",
        }
    }
    os.environ["CURSOR_API_KEY"] = "test-cursor-key-not-real"
    try:
        with patch("requests.post") as post, patch.dict(sys.modules, {"cursor_sdk": fake_mod}):
            resp = model_chat(
                cfg,
                "analyst",
                [{"role": "user", "content": "ping"}],
                "test-cursor",
            )
        assert post.call_count == 0
        assert extract_content(resp) == '{"ok": true}'
        assert resp["model"]["id"] == "grok-4.5"
        # Layers' message content is what was sent (flattened), not rewritten.
        sent_prompt = fake_mod.Agent.prompt.call_args[0][0]
        assert "[user]\nping" in sent_prompt
        opts = fake_mod.Agent.prompt.call_args[0][1]
        assert opts["model"]["id"] == "grok-4.5"
        assert opts["mode"] == "plan"
    finally:
        os.environ.pop("CURSOR_API_KEY", None)


if __name__ == "__main__":  # pytest-free runner
    import tempfile

    n = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        if fn.__code__.co_argcount and "tmp_path" in fn.__code__.co_varnames[:1]:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        else:
            fn()
        print(f"ok  {name}")
        n += 1
    print(f"\n{n} tests passed")
