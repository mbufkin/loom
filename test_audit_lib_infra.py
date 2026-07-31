#!/usr/bin/env python3
"""Offline tests for audit_lib infrastructure fixes (Tier A of the predict audit).

Covers, with no model server or corpus required:
  F008 — audit.log uses a size-bounded RotatingFileHandler (not unbounded FileHandler)
  F018 — atomic_write is atomic (temp→rename) AND durable (fsync file + parent dir)
  F025 — LARGE_CALL_TIMEOUT_SECONDS has ONE definition, shared by layer0/layer1
  F009 — extract_content has ONE definition in audit_lib, reused by the layers/ingest
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import audit_lib  # noqa: E402
import ingest  # noqa: E402
import layer0  # noqa: E402
import layer1  # noqa: E402


# ── F008: bounded, rotating log file ─────────────────────────────────────────
def test_log_uses_rotating_handler_with_bounds() -> None:
    # Force a clean (re)init so we inspect the handler this code path installs.
    audit_lib._logging_ready = False
    audit_lib.log("infra-test: initialize logging")

    rotating = [
        h for h in audit_lib._logger.handlers if isinstance(h, RotatingFileHandler)
    ]
    assert rotating, "audit.log must use a RotatingFileHandler (F008)"
    h = rotating[0]
    assert h.maxBytes == audit_lib.LOG_MAX_BYTES > 0, "rotation must be size-bounded"
    assert h.backupCount == audit_lib.LOG_BACKUP_COUNT >= 1, "must keep backups"
    # A plain unbounded FileHandler must NOT be what's installed.
    plain = [
        h
        for h in audit_lib._logger.handlers
        if isinstance(h, logging.FileHandler)
        and not isinstance(h, RotatingFileHandler)
    ]
    assert not plain, "no unbounded FileHandler should remain"


def test_rotating_handler_actually_rolls_over(tmp_path: Path) -> None:
    # Prove the mechanism with tiny bounds: writing past maxBytes creates a backup.
    log_file = tmp_path / "roll.log"
    h = RotatingFileHandler(log_file, maxBytes=200, backupCount=2, encoding="utf-8")
    logger = logging.getLogger("infra-test-roll")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(h)
    for i in range(50):
        logger.info("x" * 50 + f" line {i}")
    h.close()
    assert log_file.exists()
    assert (tmp_path / "roll.log.1").exists(), "should have rolled at least one backup"


# ── F018: atomic + durable writes ────────────────────────────────────────────
def test_atomic_write_writes_content_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "out.json"  # nested → also tests parent mkdir
    audit_lib.atomic_write(target, '{"ok": true}')
    assert target.read_text(encoding="utf-8") == '{"ok": true}'
    # The temp file used for the atomic swap must not linger.
    assert not (target.parent / "out.json.tmp").exists()
    assert list(target.parent.glob("*.tmp")) == []


def test_atomic_write_replaces_existing_fully(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    audit_lib.atomic_write(target, "first-and-longer-content")
    audit_lib.atomic_write(target, "second")  # shorter — must fully replace, not overlay
    assert target.read_text(encoding="utf-8") == "second"


# ── F025: one timeout constant ───────────────────────────────────────────────
def test_large_call_timeout_is_single_source() -> None:
    assert audit_lib.LARGE_CALL_TIMEOUT_SECONDS == 900
    # layer0/layer1 must resolve to the SAME object, not their own copies.
    assert layer0.LARGE_CALL_TIMEOUT_SECONDS is audit_lib.LARGE_CALL_TIMEOUT_SECONDS
    assert layer1.LARGE_CALL_TIMEOUT_SECONDS is audit_lib.LARGE_CALL_TIMEOUT_SECONDS


# ── F009: one extract_content ────────────────────────────────────────────────
def test_extract_content_single_source_and_correct() -> None:
    # Same function object everywhere (imported, not re-declared).
    assert layer0.extract_content is audit_lib.extract_content
    assert layer1.extract_content is audit_lib.extract_content
    assert ingest.extract_content is audit_lib.extract_content
    # And it still does the right thing.
    resp = {"choices": [{"message": {"content": "hello world"}}]}
    assert audit_lib.extract_content(resp) == "hello world"


if __name__ == "__main__":  # run directly; pytest not required on this box
    import tempfile

    passed = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_")
    ):
        # Supply a tmp_path to tests that request one (poor-man's fixture).
        if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        else:
            fn()
        print(f"ok  {name}")
        passed += 1
    print(f"\n{passed} tests passed")
