#!/usr/bin/env python3
"""Tests for the ledger-mini graph→review→rebuild spike (SPIKE.md)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from spike_loop import (  # noqa: E402
    build_provisional,
    gate_a,
    list_sources,
    materials_needing_queue,
    rebuild,
    default_review_findings,
    run_spike,
)

FIXTURE = ROOT / "projects" / "_fixtures" / "ledger-mini"


class TestSpikeLoop(unittest.TestCase):
    def test_gate_a_passes_when_all_sources_are_materials(self):
        sources = list_sources(FIXTURE / "sources")
        g = build_provisional("ledger-mini", "plants", sources)
        r = gate_a(g, sources)
        self.assertTrue(r.ok, r.message)
        self.assertEqual(r.missing_materials, [])

    def test_gate_a_fails_on_orphan_source(self):
        sources = list_sources(FIXTURE / "sources")
        g = build_provisional("ledger-mini", "plants", sources)
        # Drop one Material node → missing inventory
        g["nodes"] = [n for n in g["nodes"] if n.get("source_file") != sources[0]]
        r = gate_a(g, sources)
        self.assertFalse(r.ok)
        self.assertIn(sources[0], r.missing_materials)

    def test_soft_queue_when_no_lessons(self):
        sources = list_sources(FIXTURE / "sources")
        g = build_provisional("ledger-mini", "plants", sources)
        q = materials_needing_queue(g)
        self.assertEqual(sorted(q), sorted(sources))

    def test_rebuild_attaches_assessment_via_haspart(self):
        sources = list_sources(FIXTURE / "sources")
        prov = build_provisional("ledger-mini", "plants", sources)
        findings = default_review_findings("ledger-mini", "plants", sources)
        out = rebuild(prov, findings)
        lessons = [n for n in out["nodes"] if n["type"] == "Lesson"]
        assessments = [n for n in out["nodes"] if n["type"] == "Assessment"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(len(assessments), 1)
        lesson_id = lessons[0]["id"]
        aid = assessments[0]["id"]
        self.assertIn(
            {"rel": "hasPart", "from": lesson_id, "to": aid},
            out["edges"],
        )
        # Material inventory preserved (one Material per source)
        mats = [n for n in out["nodes"] if n["type"] == "Material"]
        self.assertEqual({m["source_file"] for m in mats}, set(sources))

    def test_run_spike_writes_raw_before_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ledger-mini"
            shutil.copytree(FIXTURE, root)
            # Don't copy a pre-existing graph/ if any
            gdir = root / "graph"
            if gdir.exists():
                shutil.rmtree(gdir)
            summary = run_spike(root)
            self.assertEqual(summary["gate_a"], "Gate A pass")
            self.assertTrue(summary["soft_queue"])
            raw = root / "graph" / ".raw"
            files = sorted(raw.glob("*.json"))
            self.assertEqual(len(files), 3)
            for path in files:
                rec = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("provisional_choice", rec)
                self.assertIn("rebuild_choice", rec)
                self.assertIsNotNone(rec["rebuild_choice"])
                # Provisional: no Lesson yet → queued
                self.assertTrue(rec["provisional_choice"].get("queued"))
                # Rebuild: exit ticket becomes Assessment under Lesson
                if "Exit_Ticket" in rec["source_file"]:
                    self.assertEqual(rec["rebuild_choice"]["node_type"], "Assessment")
                    self.assertIsNotNone(rec["rebuild_choice"]["lesson_id"])


if __name__ == "__main__":
    unittest.main()
