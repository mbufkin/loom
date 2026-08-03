#!/usr/bin/env python3
"""Tests for shared unit-spine merge + manifest-driven assemble."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE))  # score_haspart, spike_loop
sys.path.insert(0, str(_ROOT))  # promoted graph_assemble / graph_inventory

from graph_assemble import (  # noqa: E402
    SpinePolicy,
    load_unit_slice,
    merge_narrow_step_findings,
    rebuild_multi,
    resolve_unit_spine,
)
from score_haspart import score  # noqa: E402
from spike_loop import build_provisional  # noqa: E402

HERE = Path(__file__).resolve().parent
SLICE = HERE / "results" / "bluebonnet-g5-m1-grok"
MANIFEST = SLICE / "manifest.yaml"
GOLD = SLICE / "graph" / "HAS-PART.json"
# Completed 16k run that exposed the TE-cap bug (12 lessons before fix).
PRIOR_RUN = HERE / "results" / "P1xD_bluebonnet-g5-m1-slice_1785686678"


class TestSpinePolicy(unittest.TestCase):
    def test_highest_union_fills_to_max_not_te_cap(self):
        """Regression: TE 1–12 must not overwrite Learn/Succeed 1–15."""
        bag = set(range(1, 13)) | set(range(1, 16)) | {1, 4, 6, 8, 11, 12}
        spine = resolve_unit_spine(bag, SpinePolicy(mode="contiguous_from_1"))
        self.assertEqual(spine, set(range(1, 16)))

    def test_sparse_alone_does_not_invent_module(self):
        spine = resolve_unit_spine({1, 4, 6, 8}, SpinePolicy())
        self.assertEqual(spine, {1, 4, 6, 8})

    def test_union_only_keeps_holes(self):
        spine = resolve_unit_spine({1, 2, 15}, SpinePolicy(mode="union_only"))
        self.assertEqual(spine, {1, 2, 15})


class TestManifestUnit(unittest.TestCase):
    def test_load_bluebonnet_g5_m1_slice(self):
        slice_ = load_unit_slice(MANIFEST, unit_id="place-value-decimals")
        self.assertEqual(slice_.project_id, "bluebonnet-g5-m1-slice")
        self.assertEqual(slice_.unit_id, "place-value-decimals")
        self.assertEqual(len(slice_.documents), 4)
        self.assertEqual(slice_.spine_policy.mode, "contiguous_from_1")
        self.assertTrue(any("Teacher_Edition" in d for d in slice_.documents))
        self.assertTrue(any("Practice" in d for d in slice_.documents))


class TestMergeReplay(unittest.TestCase):
    @unittest.skipUnless(PRIOR_RUN.is_dir(), "prior 16k run artifacts missing")
    def test_replay_prior_steps_pass_15_of_15(self):
        """Same model answers as the 12/15 bug run → merge fix → 15/15 pass."""
        slice_ = load_unit_slice(MANIFEST, unit_id="place-value-decimals")
        roles, lessons, assesses = {}, {}, {}
        for sf in slice_.documents:
            stem = Path(sf).stem
            roles[sf] = json.loads((PRIOR_RUN / ".raw" / f"01-role-{stem}.json").read_text())
            lessons[sf] = json.loads(
                (PRIOR_RUN / ".raw" / f"02-lessons-{stem}.json").read_text()
            )
            assesses[sf] = json.loads(
                (PRIOR_RUN / ".raw" / f"03-assess-{stem}.json").read_text()
            )

        findings = merge_narrow_step_findings(
            slice_.project_id,
            slice_.unit_id,
            slice_.documents,
            roles,
            lessons,
            assesses,
            spine_policy=slice_.spine_policy,
        )
        names = [x["name"] for x in findings["create_lessons"]]
        self.assertEqual(len(names), 15, names)
        self.assertEqual(names[-1], "Lesson 15")

        provisional = build_provisional(
            slice_.project_id, slice_.unit_id, slice_.documents
        )
        final = rebuild_multi(provisional, findings)
        out = PRIOR_RUN / "final_graph_assemble_replay.json"
        out.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
        sc = score(out, GOLD, SLICE / "sources")
        self.assertEqual(sc["n_pred_lessons"], 15)
        self.assertEqual(sc["n_gold_lessons"], 15)
        self.assertTrue(sc["pass_provisional"], sc)


if __name__ == "__main__":
    unittest.main()
