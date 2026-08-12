#!/usr/bin/env python3
"""Queue Dallas (or any) graph runs for every free NVIDIA NIM model.

Uses the local rate-limited proxy (nvidia-nim-proxy on :8787) which already
enforces ~20 RPM / heavy ~4 RPM against integrate.api.nvidia.com.

Each model writes under the canonical E2E root (not bare graph/runs/):
  projects/<id>/e2e/runs/<slug>/graph/runs/<slug>/

Usage:
  python3 tools/queue_nvidia_free_graph_runs.py --project dallas-career-2026
  python3 tools/queue_nvidia_free_graph_runs.py --project dallas-career-2026 --probe-only
  python3 tools/queue_nvidia_free_graph_runs.py --project dallas-career-2026 --models nvidia/nemotron-3-nano-30b-a3b

Best practice: one model at a time (shared API key RPM). Soft-skips docs with
no ledger evidence. Resumable — skips units that already have HAS-PART.json.
Graph-only under E2E symlinks curriculum layer0/ for the ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = os.environ.get("NVIDIA_NIM_PROXY", "http://127.0.0.1:8787")
CONFIG_DIR = Path(os.environ.get("LOOM_NIM_CONFIG_DIR", "/tmp/loom-nim-configs"))
LOG_DIR = Path(os.environ.get("LOOM_NIM_QUEUE_LOG_DIR", "/tmp/loom-nim-queue"))

# Candidates known from prior bakeoffs + NIM catalog probes on this box.
CANDIDATES = [
    "nvidia/nemotron-3-nano-30b-a3b",
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "mistralai/mistral-nemotron",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-4-maverick-17b-128e-instruct",
    "qwen/qwen3.5-122b-a10b",
    "google/gemma-3-27b-it",
]


def slugify(model: str) -> str:
    s = model.strip().replace("/", "-")
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in s)[:80]


def probe_model(model: str, *, timeout: float = 45.0) -> str:
    """Return free|paid|blocked|rate_limited|error."""
    data = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 3,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        f"{PROXY.rstrip('/')}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return "free"
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        low = body.lower()
        if e.code in (429, 503, 529) or "request limit" in low:
            return "rate_limited"  # treat as free-tier capacity
        if e.code == 402 or "payment" in low or "insufficient" in low:
            return "paid"
        if e.code == 403 or "forbidden" in low:
            return "blocked"
        return f"error:{e.code}"
    except Exception as ex:  # noqa: BLE001
        return f"error:{type(ex).__name__}"


def probe_free(candidates: list[str], *, gap_s: float = 3.2) -> list[str]:
    free: list[str] = []
    report: dict[str, str] = {}
    for m in candidates:
        status = probe_model(m)
        report[m] = status
        print(f"[{status}] {m}", flush=True)
        if status in ("free", "rate_limited"):
            free.append(m)
        time.sleep(gap_s)
    out = LOG_DIR / "nvidia_free_probe.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"proxy": PROXY, "report": report, "free": free}, indent=2) + "\n")
    print(f"probe wrote {out} ({len(free)} free)", flush=True)
    return free


def write_nim_config(model: str, *, timeout: int = 600) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{slugify(model)}.yaml"
    # Proxy injects auth + RPM; Loom just needs OpenAI-compatible URL + model id.
    text = f"""# Auto-generated NIM config for graph A/B — do not commit secrets here.
models:
  analyst_url: "{PROXY.rstrip('/')}/v1/chat/completions"
  verifier_url: "{PROXY.rstrip('/')}/v1/chat/completions"
  analyst_model: "{model}"
  verifier_model: "{model}"
  timeout_seconds: {timeout}

paths:
  base_dir: "{ROOT}"
  default_sources_dir: "{ROOT}/data/career-curriculum/osint"

policy:
  auditor_only: true
"""
    path.write_text(text, encoding="utf-8")
    return path


def run_model_graph(project: str, model: str, *, force: bool = False) -> int:
    cfg = write_nim_config(model)
    run_id = slugify(model)
    log_path = LOG_DIR / f"{run_id}.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # E2E-only: LOOM_E2E_RUN isolates writes under e2e/runs/<slug>/ (run_project
    # also auto-ensures this; set here so logs/state stay explicit).
    env = os.environ.copy()
    env["LOOM_CONFIG"] = str(cfg)
    env["LOOM_USAGE_PROJECT"] = project
    env["LOOM_E2E_RUN"] = run_id
    env.pop("LOOM_ALLOW_LIVE_ROOT", None)
    cmd = [
        sys.executable,
        str(ROOT / "run_project.py"),
        "--project",
        project,
        "--graph-only",
        "--with-graph",
        "--graph-backend",
        "local",
        "--graph-run",
        run_id,
    ]
    if force:
        cmd.append("--force")
    print(
        f"\n=== QUEUE model={model} e2e_run={run_id} "
        f"out=projects/{project}/e2e/runs/{run_id}/ log={log_path} ===",
        flush=True,
    )
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n# start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {model}\n")
        logf.write(f"# LOOM_E2E_RUN={run_id}\n")
        logf.flush()
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT)
    print(f"=== DONE model={model} exit={proc.returncode} ===", flush=True)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="dallas-career-2026")
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument(
        "--models",
        nargs="*",
        help="Explicit model ids (skip probe). Default: probe CANDIDATES for free.",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--gap-between-models-s",
        type=float,
        default=15.0,
        help="Pause between models so RPM windows drain (default 15s)",
    )
    args = ap.parse_args()

    # Proxy health
    try:
        with urllib.request.urlopen(f"{PROXY.rstrip('/')}/health", timeout=10) as r:
            health = json.loads(r.read())
        print("proxy health:", health.get("ok"), "max_rpm=", health.get("max_rpm"), flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: nvidia-nim-proxy not reachable at {PROXY}: {e}", flush=True)
        return 2

    if args.models:
        models = list(args.models)
        print(f"using explicit models ({len(models)})", flush=True)
    else:
        models = probe_free(CANDIDATES)

    if args.probe_only:
        print(json.dumps(models, indent=2))
        return 0 if models else 1

    if not models:
        print("ERROR: no free NVIDIA models found", flush=True)
        return 1

    queue_state = {
        "project": args.project,
        "models": models,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": [],
    }
    state_path = LOG_DIR / f"queue-{args.project}.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for i, model in enumerate(models):
        rc = run_model_graph(args.project, model, force=args.force)
        queue_state["results"].append(
            {
                "model": model,
                "run_id": slugify(model),
                "exit": rc,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        state_path.write_text(json.dumps(queue_state, indent=2) + "\n")
        if i + 1 < len(models) and args.gap_between_models_s > 0:
            print(f"cooling {args.gap_between_models_s}s before next model…", flush=True)
            time.sleep(args.gap_between_models_s)

    failed = [r for r in queue_state["results"] if r["exit"] != 0]
    print(
        f"\nQUEUE COMPLETE: {len(models)} models, {len(failed)} failed. State: {state_path}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
