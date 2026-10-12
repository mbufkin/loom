#!/usr/bin/env python3
"""Choosing the Brev GPU or NVIDIA's API for a run.

Every run probes the operator's Brev NIM once, at its start: ready AND serving
the pinned model means the whole run uses Brev through a per-run config;
anything else means the pinned config, exactly as before. These tests stand up
fake NIM servers on loopback -- no network, no model calls.

The security property tested hardest is that NVIDIA_API_KEY never reaches the
Brev host: not on the probe, not on a model call, not in the run's environment.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "ui"))

import yaml  # noqa: E402

import server  # noqa: E402
from test_setup_api import (  # noqa: E402
    _Fixture,
    _project_with_a_document,
    _wait_for_run,
)

MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
PINNED = {
    "models": {
        "analyst_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "verifier_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "analyst_model": MODEL,
        "verifier_model": MODEL,
        "enable_thinking": False,
        "timeout_seconds": 600,
    },
    "paths": {"base_dir": "."},
    "policy": {"auditor_only": True},
}
FAKE_NVIDIA_KEY = "nvapi-test-key-must-never-reach-brev"


class FakeNim:
    """A NIM-shaped server. `health`, `models` and `delay` set its behaviour;
    every request's Authorization header is recorded."""

    def __init__(
        self,
        health: int = 200,
        models: list[str] | None = None,
        delay: float = 0,
        reply: str = "ok",
    ):
        self.health, self.delay, self.reply = health, delay, reply
        self.models = [MODEL] if models is None else models
        self.auth_seen: list[str | None] = []
        self.chat_bodies: list[dict] = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.auth_seen.append(self.headers.get("Authorization"))
                if fake.delay:
                    time.sleep(fake.delay)
                if self.path == "/v1/health/ready":
                    return self._send(fake.health, {"status": "ok"})
                if self.path == "/v1/models":
                    return self._send(200, {"data": [{"id": m} for m in fake.models]})
                return self._send(404, {})

            def do_POST(self):
                fake.auth_seen.append(self.headers.get("Authorization"))
                n = int(self.headers.get("Content-Length") or 0)
                fake.chat_bodies.append(json.loads(self.rfile.read(n) or b"{}"))
                return self._send(200, {
                    "model": MODEL,
                    "choices": [{"message": {"content": fake.reply}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                })

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _closed_port_url() -> str:
    """A loopback URL nothing listens on: connection refused at once."""
    s = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = s.server_address[1]
    s.server_close()
    return f"http://127.0.0.1:{port}"


class _Env:
    """Pinned config on disk, RUNS_DIR in a temp dir, env patched."""

    def __init__(self, brev_url: str | None) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="loom-brev-"))
        self.config = self.tmp / "config.yaml"
        self.config.write_text(yaml.safe_dump(PINNED), encoding="utf-8")
        env = {"LOOM_CONFIG": str(self.config), "NVIDIA_API_KEY": FAKE_NVIDIA_KEY}
        if brev_url is not None:
            env["LOOM_BREV_URL"] = brev_url
        self._patch = mock.patch.dict(os.environ, env)
        self._patch.start()
        if brev_url is None:
            os.environ.pop("LOOM_BREV_URL", None)
        self._saved_runs = server.RUNS_DIR
        server.RUNS_DIR = self.tmp / "runs"

    def close(self) -> None:
        server.RUNS_DIR = self._saved_runs
        self._patch.stop()


def test_a_healthy_brev_is_chosen_with_a_per_run_config() -> None:
    nim = FakeNim()
    env = _Env(nim.base + "/v1/")  # pasted with /v1/ -- normalised
    try:
        choice = server._choose_backend("run1")
        assert choice["backend"] == "brev", choice
        assert choice["line"].startswith("Model: Lightning on Brev GPU (127.0.0.1:")

        cfg = yaml.safe_load(Path(choice["config"]).read_text(encoding="utf-8"))
        assert Path(choice["config"]).parent == server.RUNS_DIR
        m, pinned = cfg["models"], PINNED["models"]
        assert m["analyst_url"] == m["verifier_url"] == f"{nim.base}/v1/chat/completions"
        # Everything else exactly as pinned.
        for k in ("analyst_model", "verifier_model", "enable_thinking", "timeout_seconds"):
            assert m[k] == pinned[k], k
        assert m["nim"] is True
        assert cfg["paths"] == PINNED["paths"] and cfg["policy"] == PINNED["policy"]
        # The pinned file itself is untouched.
        assert yaml.safe_load(env.config.read_text()) == PINNED
    finally:
        env.close()
        nim.stop()


def test_a_legacy_api_key_in_the_pinned_config_is_not_copied_for_brev() -> None:
    nim = FakeNim()
    env = _Env(nim.base)
    try:
        with_key = json.loads(json.dumps(PINNED))
        with_key["models"]["api_key"] = "legacy-plaintext"
        env.config.write_text(yaml.safe_dump(with_key), encoding="utf-8")
        cfg = yaml.safe_load(Path(server._choose_backend("r")["config"]).read_text())
        assert "api_key" not in cfg["models"]
    finally:
        env.close()
        nim.stop()


def _expect_api(brev_url: str | None, reason: str, nim: FakeNim | None = None) -> None:
    env = _Env(brev_url)
    try:
        choice = server._choose_backend("r")
        assert choice["backend"] == "nvidia-api", choice
        assert choice["config"] is None
        assert choice["line"].startswith("Model: Lightning on NVIDIA API ("), choice["line"]
        assert reason in choice["line"], choice["line"]
        assert not list(server.RUNS_DIR.glob("*.config.yaml")) if server.RUNS_DIR.exists() else True
    finally:
        env.close()
        if nim:
            nim.stop()


def test_unset_brev_means_the_api_and_no_probe() -> None:
    _expect_api(None, "Brev not configured")
    _expect_api("   ", "Brev not configured")


def test_unreachable_brev_means_the_api() -> None:
    _expect_api(_closed_port_url(), "Brev not reachable")


def test_a_brev_that_is_not_ready_means_the_api() -> None:
    nim = FakeNim(health=503)
    _expect_api(nim.base, "health check returned 503", nim)


def test_a_brev_serving_another_model_means_the_api() -> None:
    nim = FakeNim(models=["meta/llama-3.1-8b-instruct"])
    _expect_api(nim.base, "not nvidia/nemotron-3.5-lightning-30b-a3b", nim)


def test_the_probe_gives_up_within_its_time_budget() -> None:
    """A Brev that accepts the connection and then hangs must not hold the
    run's start for longer than the probe's budget."""
    nim = FakeNim(delay=30)
    try:
        t0 = time.monotonic()
        ok, why = server._probe_brev(nim.base, MODEL)
        elapsed = time.monotonic() - t0
        assert not ok and "timed out" in why, why
        assert elapsed < server.BREV_TOTAL_TIMEOUT + 1.5, elapsed
    finally:
        nim.stop()


def test_the_nvidia_key_never_reaches_brev() -> None:
    """Probe, run environment, and a real model_chat call against the per-run
    config -- with NVIDIA_API_KEY set the whole time."""
    import audit_lib
    import loom_keys

    nim = FakeNim()
    env = _Env(nim.base)
    try:
        choice = server._choose_backend("r")
        cfg = yaml.safe_load(Path(choice["config"]).read_text())
        url = cfg["models"]["analyst_url"]

        assert loom_keys.auth_headers(url, cfg) == {}
        # Sanity: the same lookup for NVIDIA's host does find the key, so the
        # assertion above is about scoping, not about a missing key.
        assert loom_keys.auth_headers(PINNED["models"]["analyst_url"], PINNED)

        run_env = server._run_env(dict(os.environ), choice)
        assert run_env["LOOM_CONFIG"] == choice["config"]
        assert "NVIDIA_API_KEY" not in run_env and "LOOM_API_KEY" not in run_env

        audit_lib.model_chat(
            cfg, "analyst", [{"role": "user", "content": "hi"}], "brev-test",
            max_tokens=16, enable_thinking=False,
        )
        assert nim.auth_seen and all(a is None for a in nim.auth_seen), nim.auth_seen
        body = nim.chat_bodies[-1]
        assert body["model"] == MODEL
        # Treated as the NIM it is: no llama.cpp-only field (NIM rejects it),
        # thinking off as on the hosted path.
        assert "repeat_penalty" not in body
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
    finally:
        env.close()
        nim.stop()


def test_the_api_path_environment_is_unchanged() -> None:
    env = _Env(None)
    try:
        choice = server._choose_backend("r")
        base_env = dict(os.environ)
        assert server._run_env(base_env, choice) == base_env
    finally:
        env.close()


_GRAPH_CALL = r'''
import sys
sys.path.insert(0, sys.argv[1])
import audit_lib, graph_phase
out = graph_phase.chat_json(audit_lib.load_config(), "graph-role-test", "Which role?")
print("graph got role=" + out["role"], flush=True)
'''


def test_the_graph_phase_uses_the_per_run_config_and_is_metered() -> None:
    # The graph phase runs as a grandchild of the server (server -> run_project
    # -> graph_phase). Neither hop passes an env, so the per-run LOOM_CONFIG
    # must survive inheritance and graph_phase must read it via load_config().
    # Proven here with the real graph_phase.chat_json against a fake NIM.
    nim = FakeNim(reply='{"role": "teacher_edition"}')
    env = _Env(nim.base)
    home = env.tmp / "home"
    try:
        choice = server._choose_backend("graph-run")
        assert choice["backend"] == "brev", choice
        child_env = server._run_env(server._audit_env(), choice)
        child_env.update(
            LOOM_HOME=str(home), LOOM_USAGE_PROJECT="p", LOOM_E2E_RUN="r1", LOOM_HOSTED="0"
        )
        script = env.tmp / "graph_call.py"
        script.write_text(_GRAPH_CALL, encoding="utf-8")
        import subprocess

        done = subprocess.run(
            [sys.executable, str(script), str(BASE)],
            env=child_env, capture_output=True, text=True, timeout=60,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "graph got role=teacher_edition" in done.stdout

        # The call went to Brev, with the pinned model, thinking off, no key.
        assert len(nim.chat_bodies) == 1, nim.chat_bodies
        body = nim.chat_bodies[0]
        assert body["model"] == MODEL
        assert FAKE_NVIDIA_KEY not in json.dumps(body)
        assert all(FAKE_NVIDIA_KEY not in (a or "") for a in nim.auth_seen)

        # And it was metered into this run's usage log.
        usage = home / "projects" / "p" / "e2e" / "runs" / "r1" / "usage.jsonl"
        rows = [json.loads(l) for l in usage.read_text().splitlines() if l.strip()]
        assert len(rows) == 1, rows
    finally:
        env.close()
        nim.stop()


# --- through the HTTP API, with fake pipeline steps --------------------------

_FAKE_STEP = r'''
import os, sys
print("child LOOM_CONFIG=" + os.environ.get("LOOM_CONFIG", ""), flush=True)
print("child has NVIDIA key=" + str("NVIDIA_API_KEY" in os.environ), flush=True)
sys.exit(int(sys.argv[1]))
'''


def _fake_steps(fx: _Fixture, ingest_exit: int):
    script = fx.tmp / "fake_step.py"
    script.write_text(_FAKE_STEP, encoding="utf-8")
    saved = (server._organise_argv, server._audit_argv)
    server._organise_argv = lambda pid: [sys.executable, str(script), str(ingest_exit)]
    server._audit_argv = lambda pid, flags: [sys.executable, str(script), "0"]

    def restore() -> None:
        server._organise_argv, server._audit_argv = saved

    return restore


def test_status_and_log_report_brev_and_every_step_gets_the_per_run_config() -> None:
    nim = FakeNim()
    env = _Env(nim.base)
    fx = _Fixture()
    restore = _fake_steps(fx, 0)
    try:
        _project_with_a_document(fx, "on-brev")
        # Organise-and-run cannot pass validation with the fake ingest, so the
        # per-step check uses the legacy endpoints, which share the code path.
        code, body = fx.request("POST", "/api/projects/on-brev/organise", {})
        assert code == 200, body
        status = _wait_for_run(fx, body["runId"])
        assert status["backend"] == "brev" and status["brev_configured"] is True
        lines = status["log"].splitlines()
        assert lines[0].startswith("Model: Lightning on Brev GPU"), lines[0]
        assert any(l.endswith(".config.yaml") and "child LOOM_CONFIG=" in l for l in lines)
        assert "child has NVIDIA key=False" in lines

        code, body = fx.request("POST", "/api/projects/on-brev/run", {"flags": []})
        status = _wait_for_run(fx, body["runId"])
        assert status["backend"] == "brev"
        assert "child has NVIDIA key=False" in status["log"]
    finally:
        restore()
        fx.close()
        env.close()
        nim.stop()


def test_status_and_log_report_the_api_when_brev_is_off() -> None:
    env = _Env(_closed_port_url())
    fx = _Fixture()
    restore = _fake_steps(fx, 0)
    try:
        _project_with_a_document(fx, "on-api")
        code, body = fx.request("POST", "/api/projects/on-api/organise-and-run", {})
        assert code == 200, body
        status = _wait_for_run(fx, body["runId"])
        assert status["backend"] == "nvidia-api" and status["brev_configured"] is True
        first = status["log"].splitlines()[0]
        assert first.startswith("Model: Lightning on NVIDIA API (Brev not reachable"), first
        assert f"child LOOM_CONFIG={env.config}" in status["log"]
        assert "child has NVIDIA key=True" in status["log"]
    finally:
        restore()
        fx.close()
        env.close()


def test_brev_going_away_mid_run_fails_with_a_clear_message() -> None:
    nim = FakeNim()
    env = _Env(nim.base)
    fx = _Fixture()
    restore = _fake_steps(fx, 1)
    try:
        _project_with_a_document(fx, "brev-drop")
        # Brev is up when the run starts; the step then fails and Brev is gone
        # by the time the run ends.
        saved_argv = server._organise_argv

        def argv_and_stop(pid):
            nim.stop()
            return saved_argv(pid)

        server._organise_argv = argv_and_stop
        code, body = fx.request("POST", "/api/projects/brev-drop/organise-and-run", {})
        status = _wait_for_run(fx, body["runId"])
        assert status["status"] == "error" and status["backend"] == "brev"
        assert "Brev GPU stopped answering" in status["error"], status["error"]
        assert "will use NVIDIA's API if Brev is still off" in status["error"]
        assert "Brev GPU stopped answering" in status["log"]
    finally:
        restore()
        fx.close()
        env.close()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
