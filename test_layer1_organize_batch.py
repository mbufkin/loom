#!/usr/bin/env python3
"""Offline tests for Layer 1 ORGANIZE element-batching (roadmap §13)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from layer1 import (  # noqa: E402
    ORGANIZE_BATCH_SIZE,
    _organize_element_batches,
    organize_document,
)


def _el(i: int) -> dict:
    return {
        "element_id": f"doc-e{i}",
        "element_type": "lesson_content",
        "excerpt": f"Excerpt number {i} about place value.",
    }


def test_batch_split_ninety_elements_three_batches():
    elements = [_el(i) for i in range(1, 91)]
    batches = _organize_element_batches(elements, batch_size=40)
    assert len(batches) == 3
    assert [len(b) for b in batches] == [40, 40, 10]
    assert batches[0][0]["element_id"] == "doc-e1"
    assert batches[2][-1]["element_id"] == "doc-e90"


def test_small_doc_single_batch():
    elements = [_el(i) for i in range(1, 11)]
    batches = _organize_element_batches(elements, batch_size=ORGANIZE_BATCH_SIZE)
    assert len(batches) == 1
    assert len(batches[0]) == 10


def test_organize_document_merges_batches_and_isolates_failure(tmp_path: Path | None = None):
    """90 els → 3 model calls; batch 2 fails; batches 1+3 still merge."""
    raw_dir = Path(tmp_path) if tmp_path is not None else BASE / ".tmp-layer1-test-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    elements = [_el(i) for i in range(1, 91)]
    unit_vocab = [{"unit_id": "g5-mod-1", "title": "Module 1"}]
    day_vocab = [
        {"unit_id": "g5-mod-1", "day_id": "d1", "day_label": "Day 1"},
    ]

    calls: list[str] = []

    def fake_call_and_parse(cfg, role, prompt, step, **kwargs):
        calls.append(step)
        # Fail the middle batch only.
        if "batch2of3" in step:
            raise ValueError("simulated truncated JSON")
        # Return one placement per ELEMENT line in the prompt.
        eids = [
            line.split()[1]
            for line in prompt.splitlines()
            if line.startswith("ELEMENT ")
        ]
        return {
            "placements": [
                {
                    "element_id": eid,
                    "self_identifies_with_a_unit": True,
                    "matched_unit_id": "g5-mod-1",
                    "matched_day_id": "d1",
                    "supporting_quote": "place value",
                    "reasoning": "topic match",
                }
                for eid in eids
            ]
        }

    with patch("layer1.call_and_parse_with_retry", side_effect=fake_call_and_parse):
        by_id = organize_document(
            {},
            "Learn_SE",
            elements,
            unit_vocab,
            day_vocab,
            raw_dir,
            batch_size=40,
        )

    assert len(calls) == 3
    assert "batch1of3" in calls[0]
    assert "batch2of3" in calls[1]
    assert "batch3of3" in calls[2]
    # Batches 1 (1-40) and 3 (81-90) present; batch 2 (41-80) absent.
    assert len(by_id) == 50
    assert "doc-e1" in by_id and "doc-e40" in by_id
    assert "doc-e41" not in by_id and "doc-e80" not in by_id
    assert "doc-e81" in by_id and "doc-e90" in by_id
    assert by_id["doc-e1"]["matched_unit_id"] == "g5-mod-1"


def test_organize_document_small_doc_one_call(tmp_path: Path | None = None):
    raw_dir = Path(tmp_path) if tmp_path is not None else BASE / ".tmp-layer1-test-raw2"
    raw_dir.mkdir(parents=True, exist_ok=True)
    elements = [_el(i) for i in range(1, 6)]
    unit_vocab = [{"unit_id": "u1", "title": "Unit 1"}]
    day_vocab = [{"unit_id": "u1", "day_id": "d1", "day_label": "Day 1"}]
    calls: list[str] = []

    def fake_call_and_parse(cfg, role, prompt, step, **kwargs):
        calls.append(step)
        return {
            "placements": [
                {
                    "element_id": el["element_id"],
                    "self_identifies_with_a_unit": False,
                    "matched_unit_id": None,
                    "matched_day_id": None,
                    "supporting_quote": None,
                    "reasoning": None,
                }
                for el in elements
            ]
        }

    with patch("layer1.call_and_parse_with_retry", side_effect=fake_call_and_parse):
        by_id = organize_document(
            {}, "small-doc", elements, unit_vocab, day_vocab, raw_dir
        )

    assert len(calls) == 1
    assert calls[0] == "layer1-organize-small-doc"
    assert "batch" not in calls[0]
    assert len(by_id) == 5


if __name__ == "__main__":
    test_batch_split_ninety_elements_three_batches()
    test_small_doc_single_batch()
    test_organize_document_merges_batches_and_isolates_failure()
    test_organize_document_small_doc_one_call()
    print("test_layer1_organize_batch: OK")
