#!/usr/bin/env python3
"""Offline tests for Layer 0 mid-chunk resume cache."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from layer0 import _load_chunk_resume, _save_chunk_resume  # noqa: E402


def test_roundtrip_and_hash_mismatch():
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td)
        rows = [
            {
                "element_id": "doc-chunk1of2-e1",
                "excerpt": "hello",
                "cited": True,
            }
        ]
        _save_chunk_resume(
            raw,
            "doc-chunk1of2",
            "abc123",
            "chunk1of2",
            rows,
            pass_used=1,
            rechecked=False,
            errors=[],
        )
        hit = _load_chunk_resume(raw, "doc-chunk1of2", "abc123", "chunk1of2")
        assert hit is not None
        loaded_rows, pass_used, rechecked, errors = hit
        assert loaded_rows == rows
        assert pass_used == 1 and rechecked is False and errors == []

        miss_hash = _load_chunk_resume(raw, "doc-chunk1of2", "other", "chunk1of2")
        assert miss_hash is None
        miss_chunk = _load_chunk_resume(raw, "doc-chunk1of2", "abc123", "chunk2of2")
        assert miss_chunk is None


if __name__ == "__main__":
    test_roundtrip_and_hash_mismatch()
    print("test_layer0_chunk_resume: OK")
