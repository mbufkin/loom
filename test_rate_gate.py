#!/usr/bin/env python3
"""Offline tests for the RPM rate gate (models.max_rpm) and 429 backoff.

No network. Fake clock + sleeper prove the gate waits until the sliding window
has a free slot; mocked requests prove model_chat retries on HTTP 429.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import audit_lib  # noqa: E402
from audit_lib import RateGate  # noqa: E402


class FakeClock:
    """Monotonic clock we can advance ourselves (no real sleep)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_gate_noop_when_max_rpm_unset() -> None:
    clock = FakeClock()
    slept: list[float] = []
    g = RateGate(clock=clock, sleeper=lambda s: slept.append(s) or clock.advance(s))
    assert g.wait(None, step="t") == 0.0
    assert g.wait(0, step="t") == 0.0
    assert slept == []


def test_gate_allows_up_to_max_then_waits() -> None:
    clock = FakeClock()
    slept: list[float] = []

    def sleeper(s: float) -> None:
        slept.append(s)
        clock.advance(s)

    g = RateGate(clock=clock, sleeper=sleeper)
    # Fill the window to the cap (3 RPM).
    for _ in range(3):
        assert g.wait(3, step="t", window_seconds=60.0) == 0.0
    assert g.recent_count == 3
    # 4th call must wait until the oldest falls out of the 60s window.
    slept_total = g.wait(3, step="t", window_seconds=60.0)
    assert slept_total > 0
    assert slept, "expected at least one sleep"
    # After waiting, the call was recorded.
    assert g.recent_count <= 3


def test_gate_clears_as_window_slides() -> None:
    clock = FakeClock()
    g = RateGate(clock=clock, sleeper=lambda s: clock.advance(s))
    for _ in range(2):
        g.wait(2, step="t", window_seconds=10.0)
    # Jump past the window — history should be pruned on next wait.
    clock.advance(11.0)
    assert g.wait(2, step="t", window_seconds=10.0) == 0.0


def test_model_chat_respects_max_rpm() -> None:
    """model_chat with max_rpm=1 must sleep before a second call in the same window."""
    audit_lib._rate_gate.reset()
    clock = FakeClock()
    slept: list[float] = []
    # Swap the process-wide gate's clock/sleeper for this test.
    audit_lib._rate_gate._clock = clock
    audit_lib._rate_gate._sleeper = lambda s: slept.append(s) or clock.advance(s)

    class R:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

    cfg = {
        "models": {
            "analyst_url": "http://example.test/v1/chat/completions",
            "analyst_model": "m",
            "verifier_url": "http://example.test/v1/chat/completions",
            "verifier_model": "m",
            "timeout_seconds": 5,
            "send_repeat_penalty": False,
            "max_rpm": 1,
        }
    }
    fake = MagicMock(return_value=R())
    try:
        with patch.object(audit_lib.requests, "post", fake):
            audit_lib.model_chat(cfg, "analyst", [{"role": "user", "content": "a"}], "t1")
            audit_lib.model_chat(cfg, "analyst", [{"role": "user", "content": "b"}], "t2")
        assert fake.call_count == 2
        assert slept, "second call should have hit the rate gate"
    finally:
        # Restore real clock so other tests / process aren't stuck on FakeClock.
        audit_lib._rate_gate = RateGate()


def test_model_chat_retries_429() -> None:
    audit_lib._rate_gate.reset()

    class R429:
        status_code = 429
        text = "rate limited"
        headers = {"Retry-After": "0.01"}

        def raise_for_status(self) -> None:
            err = __import__("requests").HTTPError("429")
            err.response = self
            raise err

        def json(self) -> dict:
            return {}

    class ROk:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    cfg = {
        "models": {
            "analyst_url": "http://example.test/v1/chat/completions",
            "analyst_model": "m",
            "verifier_url": "x",
            "verifier_model": "m",
            "timeout_seconds": 5,
            "send_repeat_penalty": False,
        }
    }
    fake = MagicMock(side_effect=[R429(), ROk()])
    with patch.object(audit_lib.requests, "post", fake), patch.object(
        audit_lib.time, "sleep", lambda s: None
    ):
        out = audit_lib.model_chat(
            cfg, "analyst", [{"role": "user", "content": "hi"}], "t", retries=2
        )
    assert out["choices"][0]["message"]["content"]
    assert fake.call_count == 2


def test_gateway_504_uses_longer_backoff() -> None:
    """502/503/504 should cool down longer than 2**attempt (Tail at Scale / NIM)."""
    sleeps: list[float] = []
    cfg = {
        "models": {
            "analyst_url": "http://example.test/v1/chat/completions",
            "analyst_model": "m",
            "verifier_url": "x",
            "verifier_model": "m",
            "timeout_seconds": 5,
            "send_repeat_penalty": False,
        }
    }
    err_resp = MagicMock()
    err_resp.status_code = 504
    err_resp.text = "gateway timeout"
    err_resp.headers = {}

    ok = MagicMock()
    ok.raise_for_status = lambda: None
    ok.json = lambda: {"choices": [{"message": {"content": "{}"}}]}

    def post_side_effect(*_a, **_k):
        if post_side_effect.n == 0:
            post_side_effect.n += 1
            e = audit_lib.requests.HTTPError("504")
            e.response = err_resp
            raise e
        return ok

    post_side_effect.n = 0
    with patch.object(audit_lib.requests, "post", side_effect=post_side_effect), patch.object(
        audit_lib.time, "sleep", lambda s: sleeps.append(s)
    ):
        out = audit_lib.model_chat(
            cfg, "analyst", [{"role": "user", "content": "hi"}], "t", retries=2
        )
    assert out["choices"][0]["message"]["content"] == "{}"
    assert sleeps, "expected a backoff sleep after 504"
    assert sleeps[0] >= 4.0, f"504 backoff too short: {sleeps}"


def test_local_default_no_gate() -> None:
    """config without max_rpm must not sleep (local llama path)."""
    audit_lib._rate_gate = RateGate()  # fresh real gate
    slept: list[float] = []
    audit_lib._rate_gate._sleeper = lambda s: slept.append(s)

    class R:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

    cfg = {
        "models": {
            "analyst_url": "http://localhost:8080/v1/chat/completions",
            "analyst_model": "x",
            "verifier_url": "x",
            "verifier_model": "x",
            "timeout_seconds": 5,
        }
    }
    with patch.object(audit_lib.requests, "post", MagicMock(return_value=R())):
        for _ in range(5):
            audit_lib.model_chat(cfg, "analyst", [{"role": "user", "content": "hi"}], "t")
    assert slept == []
    audit_lib._rate_gate = RateGate()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        fn()
        print(f"ok  {name}")
        n += 1
    print(f"\n{n} tests passed")
