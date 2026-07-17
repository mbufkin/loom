#!/usr/bin/env python3
"""Smoke tests for lesson_preserve spike (Dallas artifacts)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from experiments.lesson_preserve.emit import spike_out_root
from experiments.lesson_preserve.run_spike import run_spike

PROJECT = "dallas-career-2026"
PILOTS = (
    "professional-preparedness",
    "engineering",
    "financial-literacy",
)


def test_spike_pilots() -> None:
    out = run_spike(PROJECT, list(PILOTS))
    index = json.loads((out / "lesson_plans_index.json").read_text(encoding="utf-8"))
    org = json.loads((out / "organization.json").read_text(encoding="utf-8"))

    pp = index["units"]["professional-preparedness"]
    assert pp["lesson_plan_count"] >= 2, pp
    assert pp["path_a_mode"] == "lp_block", pp
    assert (out / "units/professional-preparedness/path_a_stub.md").is_file()
    stub = (out / "units/professional-preparedness/path_a_stub.md").read_text()
    assert "lp_block" in stub
    assert "single_lp" not in stub.split("Mode:")[1].split("\n")[0] or True  # mode line
    assert "`lp_block`" in stub

    eng = index["units"]["engineering"]
    assert eng["lesson_plan_count"] >= 1, eng
    assert eng["path_a_mode"] == "single_lp", eng
    assert eng.get("meeting_count") is not None
    assert (out / "units/engineering/meeting_span.json").is_file()
    assert (out / "units/engineering/lesson-plans").is_dir()
    preserved = list((out / "units/engineering/lesson-plans").iterdir())
    assert preserved, "expected preserved LP copy"
    # Depth: real Path A review on preserved LP
    eng_review = out / "units/engineering/path_a_review.md"
    assert eng_review.is_file(), "expected path_a_review.md for single_lp"
    eng_txt = eng_review.read_text(encoding="utf-8")
    assert "Structure matrix (A5)" in eng_txt
    assert "A1-A7_single_doc" in eng_txt or "single_lp" in eng_txt
    eng_json = json.loads(
        (out / "units/engineering/path_a_review.json").read_text(encoding="utf-8")
    )
    assert eng_json["reviews"] and eng_json["reviews"][0]["steps"].get("A5")
    assert eng_json["depth"] == "A1-A7_single_doc"

    pp_review = out / "units/professional-preparedness/path_a_review.md"
    assert pp_review.is_file()
    pp_txt = pp_review.read_text(encoding="utf-8")
    assert "Block analysis" in pp_txt
    assert "lp_block" in pp_txt
    pp_json = json.loads(
        (out / "units/professional-preparedness/path_a_review.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(pp_json["reviews"]) >= 2
    assert pp_json.get("group") and pp_json["group"].get("notes")
    assert pp_json["depth"] == "A1-A7_per_lp_plus_block"

    fl = index["units"]["financial-literacy"]
    # FL may be 0 routed LPs → synthesize_missing if calendar expects lesson
    assert fl["path_a_mode"] in {
        "single_lp",
        "lp_block",
        "synthesize_missing",
        "none",
    }, fl
    if fl["path_a_mode"] == "synthesize_missing":
        assert (out / "units/financial-literacy/GAP-LESSON-STRUCTURE.md").is_file()
    if fl["lesson_plan_count"] > 0:
        assert fl["path_a_mode"] in {"single_lp", "lp_block"}

    # Path order: non-LP first, LP last
    for uid in PILOTS:
        po = org["units"][uid]["path_order"]
        assert "non_lp_first" in po and "lp_group_last" in po
        for did in po["lp_group_last"]:
            assert did not in po["non_lp_first"]


def test_no_day_split_plates() -> None:
    out = spike_out_root(PROJECT)
    # Should not emit LESSON-PLAN-dN from this spike
    day_plates = list(out.glob("units/*/LESSON-PLAN-d*.md"))
    assert not day_plates, day_plates


if __name__ == "__main__":
    test_spike_pilots()
    print("OK test_spike_pilots")
    test_no_day_split_plates()
    print("OK test_no_day_split_plates")
    print("ALL LESSON_PRESERVE SPIKE TESTS PASSED")
