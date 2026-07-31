#!/usr/bin/env python3
"""Offline tests for multi-backend bake-off scheduling (no model calls)."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from experiments.multi_backend_bakeoff import _schedule  # noqa: E402


def test_sequential_one_per_wave() -> None:
    backends = {
        "local": {"budget_group": "local"},
        "zen": {"budget_group": "zen"},
        "nvidia": {"budget_group": "nvidia"},
    }
    waves = _schedule(backends, ["local", "zen", "nvidia"], parallel=False)
    assert waves == [["local"], ["zen"], ["nvidia"]]


def test_parallel_different_groups_one_wave() -> None:
    backends = {
        "local": {"budget_group": "local"},
        "zen": {"budget_group": "zen"},
    }
    waves = _schedule(backends, ["local", "zen"], parallel=True)
    # Different budgets → same wave (true parallel).
    assert len(waves) == 1
    assert set(waves[0]) == {"local", "zen"}


def test_parallel_same_group_stays_sequential() -> None:
    # Two NVIDIA models sharing one key / RPM budget.
    backends = {
        "nvidia-a": {"budget_group": "nvidia"},
        "nvidia-b": {"budget_group": "nvidia"},
        "local": {"budget_group": "local"},
    }
    waves = _schedule(backends, ["nvidia-a", "nvidia-b", "local"], parallel=True)
    # Wave 1: one nvidia + local; wave 2: the other nvidia alone.
    assert len(waves) == 2
    assert "local" in waves[0]
    assert len([b for b in waves[0] if b.startswith("nvidia")]) == 1
    assert waves[1] == ["nvidia-b"] or set(waves[1]) == {"nvidia-b"}
    # Never two nvidia backends in the same wave.
    for wave in waves:
        assert sum(1 for b in wave if b.startswith("nvidia")) <= 1


if __name__ == "__main__":
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        fn()
        print(f"ok  {name}")
    print("\n3 tests passed")
