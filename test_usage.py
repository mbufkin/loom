#!/usr/bin/env python3
"""Unit tests for usage_lib metering (no live model required)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import usage_lib as ul  # noqa: E402


def _isolated_project(tmp: Path, name: str = "usage-test") -> str:
    """Point usage_lib at a temp projects/<id> tree."""
    ul.BASE_DIR = tmp
    (tmp / "projects" / name).mkdir(parents=True)
    ul.set_usage_project(name)
    # Reset argv scan so tests don't inherit the pytest/unittest argv.
    ul._argv_scanned = True  # noqa: SLF001 — intentional for isolation
    return name


def test_extract_openai_usage_api() -> None:
    fields, source = ul.extract_openai_usage(
        {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 2},
            }
        }
    )
    assert source == "api"
    assert fields["prompt_tokens"] == 10
    assert fields["completion_tokens"] == 5
    assert fields["total_tokens"] == 15
    assert fields["cached_tokens"] == 2


def test_extract_openai_usage_timings_fallback() -> None:
    fields, source = ul.extract_openai_usage(
        {"timings": {"prompt_n": 17, "predicted_n": 8, "cache_n": 6}}
    )
    assert source == "timings"
    assert fields["prompt_tokens"] == 17
    assert fields["completion_tokens"] == 8
    assert fields["total_tokens"] == 25
    assert fields["cached_tokens"] == 6


def test_extract_openai_usage_missing() -> None:
    fields, source = ul.extract_openai_usage({"choices": []})
    assert source == "missing"
    assert fields["total_tokens"] is None


def test_record_and_summary_estimate() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pid = _isolated_project(tmp)
        row = ul.record_model_call(
            role="analyst",
            step="unit-test-estimate",
            model="fake",
            messages=[{"role": "user", "content": "abcd" * 10}],  # 40 chars → 10 tok
            resp={"choices": [{"message": {"content": "xy" * 8}}]},  # 16 chars → 4
            elapsed_ms=12.5,
            ok=True,
        )
        assert row["source"] == "estimate"
        assert row["prompt_tokens"] == 10
        assert row["completion_tokens"] == 4
        assert row["total_tokens"] == 14

        log_path = tmp / "projects" / pid / "usage.jsonl"
        assert log_path.is_file()
        lines = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

        summary = ul.write_usage_summary(pid)
        assert summary["totals"]["n_calls"] == 1
        assert summary["totals"]["total_tokens"] == 14
        assert summary["by_source"]["estimate"] == 1
        assert (tmp / "projects" / pid / "USAGE-SUMMARY.json").is_file()


def test_record_api_usage() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pid = _isolated_project(tmp)
        row = ul.record_model_call(
            role="verifier",
            step="unit-test-api",
            model="nemotron",
            messages=[{"role": "user", "content": "hi"}],
            resp={
                "model": "nemotron",
                "usage": {
                    "prompt_tokens": 23,
                    "completion_tokens": 8,
                    "total_tokens": 31,
                },
                "choices": [{"message": {"content": "hello"}}],
            },
            elapsed_ms=100.0,
        )
        assert row["source"] == "api"
        assert row["total_tokens"] == 31
        summary = ul.write_usage_summary(pid)
        assert summary["by_role"]["verifier"]["total_tokens"] == 31


def test_record_cursor_run_usage() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pid = _isolated_project(tmp)
        row = ul.record_cursor_run_usage(
            project_id=pid,
            step="grok-unit:g5-m1",
            model="grok-4.5",
            run_id="run-test",
            usage={
                "inputTokens": 1000,
                "outputTokens": 200,
                "totalTokens": 1200,
                "cacheReadTokens": 50,
            },
            elapsed_ms=5000,
        )
        assert row["source"] == "cursor_sdk"
        assert row["prompt_tokens"] == 1000
        assert row["completion_tokens"] == 200
        assert row["total_tokens"] == 1200
        assert row["cached_tokens"] == 50


def main() -> int:
    test_extract_openai_usage_api()
    test_extract_openai_usage_timings_fallback()
    test_extract_openai_usage_missing()
    test_record_and_summary_estimate()
    test_record_api_usage()
    test_record_cursor_run_usage()
    print("test_usage.py: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
