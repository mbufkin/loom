#!/usr/bin/env python3
"""Offline tests for Layer 0 mid-chunk resume cache."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from layer0 import (  # noqa: E402
    _clamp_span,
    _load_chunk_resume,
    _save_chunk_resume,
    build_flagged_span_text,
)


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


def test_clamp_span_guards_out_of_range():
    """Layer 0-B must not crash when a stored wide-span cites paragraphs beyond
    what its chunk reconstructs to (regression: AP-CSP CED raised IndexError)."""
    # In-range spans pass through untouched.
    assert _clamp_span(1, 3, 3) == (1, 3)
    # End past the last paragraph clamps to what exists.
    assert _clamp_span(2, 99, 3) == (2, 3)
    # A span that starts past the end has no overlap -> nothing to show.
    assert _clamp_span(10, 12, 3) == (0, 0)
    # No paragraphs at all -> nothing to show.
    assert _clamp_span(1, 5, 0) == (0, 0)


def test_build_flagged_span_text_never_indexerrors():
    paras = ["alpha", "beta", "gamma"]
    # Over-long end degrades to the available tail instead of raising.
    out = build_flagged_span_text(paras, 2, 99)
    assert out.startswith("[P2] beta") and "[P3] gamma" in out
    # Out-of-range / empty inputs return an empty string, never an exception.
    assert build_flagged_span_text(paras, 10, 12) == ""
    assert build_flagged_span_text([], 1, 5) == ""


if __name__ == "__main__":
    test_roundtrip_and_hash_mismatch()
    test_clamp_span_guards_out_of_range()
    test_build_flagged_span_text_never_indexerrors()
    print("test_layer0_chunk_resume: OK")
