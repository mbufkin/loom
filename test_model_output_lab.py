#!/usr/bin/env python3
"""Offline tests for Model Output Lab wiring (no network, no model)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

LAB = BASE / "experiments" / "model-output-lab"
RUNNER = LAB / "run_serial_compare.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("model_output_lab_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_lab_layout_exists() -> None:
    assert (LAB / "README.md").is_file()
    assert (LAB / "backends.yaml").is_file()
    assert (LAB / "run_serial_compare.py").is_file()
    assert (LAB / "configs" / "zen.yaml").is_file()
    assert (LAB / "configs" / "nvidia.example.yaml").is_file()
    assert (LAB / "results").is_dir()


def test_backends_resolve_configs() -> None:
    mod = _load_runner()
    backends = mod._load_backends()
    assert "local" in backends and "zen" in backends
    local_cfg = mod._config_path_for("local", backends["local"])
    assert local_cfg.name == "config.yaml"
    assert local_cfg.is_file()
    zen_cfg = mod._config_path_for("zen", backends["zen"])
    assert zen_cfg.name == "zen.yaml"
    assert zen_cfg.is_file()


def test_nvidia_missing_config_gives_clear_error() -> None:
    mod = _load_runner()
    backends = mod._load_backends()
    # nvidia.yaml may not exist yet — runner should return a clear error, not crash.
    r = mod._run_job(
        "nvidia",
        backends["nvidia"],
        job="smoke",
        project="bluebonnet-math-2026",
        lesson="Module_5.pdf__L2",
    )
    assert r["ok"] is False
    assert "config missing" in (r.get("error") or "") or "NVIDIA_API_KEY" in (
        r.get("error") or ""
    )


if __name__ == "__main__":
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        fn()
        print(f"ok  {name}")
    print("\n3 tests passed")
