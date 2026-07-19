#!/usr/bin/env python3
"""Stage Bluebonnet corpus into sources/ and write module-oriented unit YAML.

Stages:
  d1  — Grade 5 Module 1 pack + G5 program guides
  d2  — Full Grade 5 course
  d3  — Algebra I modules + program (no binders; corpus already excludes them)
  d4  — Grade 5 + Algebra I combined

Usage:
  python3 tools/stage_bluebonnet_units.py --stage d1
  python3 tools/stage_bluebonnet_units.py --stage d4
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

PROJECT = "bluebonnet-math-2026"
ROOT = BASE / "projects" / PROJECT
CORPUS = ROOT / "_corpus"
SOURCES = ROOT / "sources"


def days(n: int) -> list[dict]:
    return [
        {
            "id": f"d{i}",
            "label": f"Day {i}",
            "expected": ["exit_ticket"] if i == n else ["lesson_content"],
        }
        for i in range(1, n + 1)
    ]


SUPPORTING = ["lesson_plan", "quiz", "worksheet", "answer_key"]


def classify_g5(name: str) -> str | None:
    """Return unit_id for a Grade 5 filename, or None if skip."""
    if re.search(r"Module[_\s]+(\d+)", name, re.I):
        m = re.search(r"Module[_\s]+(\d+)", name, re.I)
        assert m
        return f"g5-mod-{int(m.group(1))}"
    # Program / family / navigation / course guides
    if any(
        k in name
        for k in (
            "Course_Guide",
            "Course Guide",
            "Family_Guide",
            "Family Guide",
            "Component_Navigation",
            "Component Navigation",
            "Year-at",
            "Year_at",
            "Scope",
            "Pacing",
            "ADSY",
        )
    ):
        return "g5-program"
    return "g5-program"


def classify_alg1(name: str) -> str | None:
    if re.search(r"Module[_\s]+(\d+)", name, re.I):
        m = re.search(r"Module[_\s]+(\d+)", name, re.I)
        assert m
        return f"alg1-mod-{int(m.group(1))}"
    return "alg1-program"


def module_length(unit_id: str) -> int:
    # TEA modules vary; use sensible scaffolds until pacing ingest replaces them.
    if unit_id.startswith("g5-mod-"):
        return 13
    if unit_id.startswith("alg1-mod-"):
        return 10
    if unit_id.endswith("-program"):
        return 5
    return 5


def title_for(unit_id: str) -> str:
    if unit_id == "g5-program":
        return "Grade 5 Math — program guides"
    if unit_id == "alg1-program":
        return "Algebra I — program guides"
    if unit_id.startswith("g5-mod-"):
        return f"Grade 5 Math — Module {unit_id.split('-')[-1]}"
    if unit_id.startswith("alg1-mod-"):
        return f"Algebra I — Module {unit_id.split('-')[-1]}"
    return unit_id


def collect_stage_files(stage: str) -> list[tuple[str, Path]]:
    """Return list of (rel_under_sources, absolute path in corpus)."""
    out: list[tuple[str, Path]] = []
    g5 = sorted((CORPUS / "grade-5").glob("*.pdf")) if (CORPUS / "grade-5").is_dir() else []
    a1 = (
        sorted((CORPUS / "algebra-1").glob("*.pdf"))
        if (CORPUS / "algebra-1").is_dir()
        else []
    )

    # D1 core program guides only — exclude huge ADSY TE / kits (those belong in d2).
    D1_PROGRAM_ALLOW = re.compile(
        r"Component_Navigation|Component Navigation|"
        r"Family_Guide|Family Guide|"
        r"Course_Guide|Course Guide|"
        r"Program_and_Implementation|Program and Implementation",
        re.I,
    )

    def g5_d1(p: Path) -> bool:
        # Module 1 only (not Module 10+); underscore after 1 is fine.
        if re.search(r"Module[_\s]*1(?!\d)", p.name, re.I):
            return True
        return bool(D1_PROGRAM_ALLOW.search(p.name))

    if stage == "d1":
        for p in g5:
            if g5_d1(p):
                out.append((f"grade-5/{p.name}", p))
    elif stage == "d2":
        for p in g5:
            out.append((f"grade-5/{p.name}", p))
    elif stage == "d3":
        for p in a1:
            out.append((f"algebra-1/{p.name}", p))
    elif stage == "d4":
        for p in g5:
            out.append((f"grade-5/{p.name}", p))
        for p in a1:
            out.append((f"algebra-1/{p.name}", p))
    else:
        raise ValueError(f"unknown stage {stage}")
    return out


def sync_sources(files: list[tuple[str, Path]]) -> None:
    if SOURCES.exists():
        for child in SOURCES.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    SOURCES.mkdir(parents=True, exist_ok=True)
    for rel, src in files:
        dest = SOURCES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(src.resolve())


def write_units(files: list[tuple[str, Path]]) -> None:
    by_unit: dict[str, list[str]] = {}
    for rel, _src in files:
        name = Path(rel).name
        if rel.startswith("grade-5/"):
            uid = classify_g5(name) or "g5-program"
        else:
            uid = classify_alg1(name) or "alg1-program"
        by_unit.setdefault(uid, []).append(rel)

    # Preserve school-calendar DISD spine.
    school_cal_path = ROOT / "school-calendar.yaml"
    school_bak = school_cal_path.read_text(encoding="utf-8") if school_cal_path.is_file() else None

    units_dir = ROOT / "units"
    if units_dir.exists():
        shutil.rmtree(units_dir)
    units_dir.mkdir(parents=True, exist_ok=True)

    manifest_units: dict = {}
    for uid in sorted(by_unit.keys()):
        n = module_length(uid)
        cal = {
            "unit_id": uid,
            "title": title_for(uid),
            "unit_length_days": n,
            "days": days(n),
            "unit_supporting": list(SUPPORTING),
        }
        cal_path = units_dir / uid / "calendar.yaml"
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cal_path, "w", encoding="utf-8") as f:
            yaml.dump(cal, f, default_flow_style=False, sort_keys=False)
        manifest_units[uid] = {
            "title": title_for(uid),
            "calendar": f"units/{uid}/calendar.yaml",
            "documents": sorted(by_unit[uid]),
        }

    manifest = {
        "project": {
            "id": PROJECT,
            "name": "TEA Bluebonnet Math — Grade 5 + Algebra I validation",
        },
        "sources_dir": str(SOURCES.resolve()),
        "units": manifest_units,
        "generated_by": "tools/stage_bluebonnet_units.py",
    }
    with open(ROOT / "manifest.yaml", "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    if school_bak is not None:
        school_cal_path.write_text(school_bak, encoding="utf-8")

    print(f"units: {len(manifest_units)}")
    for uid, meta in sorted(manifest_units.items()):
        print(f"  {uid}: {len(meta['documents'])} docs, {module_length(uid)} days")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stage",
        required=True,
        choices=["d1", "d2", "d3", "d4"],
        help="Validation ladder stage",
    )
    args = ap.parse_args()
    if not CORPUS.is_dir():
        print(f"ERROR: corpus missing at {CORPUS}", file=sys.stderr)
        print("Run: python3 tools/download_bluebonnet_math.py", file=sys.stderr)
        return 2
    files = collect_stage_files(args.stage)
    if not files:
        print("ERROR: no files selected for stage", file=sys.stderr)
        return 2
    sync_sources(files)
    write_units(files)
    print(f"staged {args.stage}: {len(files)} files -> {SOURCES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
