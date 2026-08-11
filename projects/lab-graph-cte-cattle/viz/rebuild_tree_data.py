#!/usr/bin/env python3
"""Rebuild src/treeData.json from the latest multi-unit spike HAS-PART.

Shared materials are duplicated under every Class they describe/span —
tidy trees cannot share a child node, so copies keep the PNG honest.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
LATEST = (LAB / "graph" / "LATEST").read_text().strip()
HAS = LAB / "graph" / LATEST / "HAS-PART.json"
OUT = Path(__file__).resolve().parent / "src" / "treeData.json"

REL_ORDER = {"describes": 0, "spanIn": 1, "hasPart": 2}

UNIT_TITLES = {
    "breeds-of-livestock-cattle": "Unit · Breeds of Livestock — Cattle",
    "external-anatomy-of-livestock-terms-terminology": (
        "Unit · External Anatomy of Livestock"
    ),
}


def short_file(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if "__" in base:
        base = base.split("__", 1)[1]
    return base


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s)


def unit_key(unit_id: str) -> str:
    if unit_id.startswith("breeds"):
        return "cattle"
    if unit_id.startswith("external"):
        return "anatomy"
    return slug(unit_id)[:24]


def main() -> None:
    g = json.loads(HAS.read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    edges = g["edges"]

    course = next(n for n in g["nodes"] if n["type"] == "Course")
    units = [n for n in g["nodes"] if n["type"] == "LessonGrouping"]
    units.sort(key=lambda n: n["id"])

    lesson_kids: dict[str, list[tuple[str, str]]] = defaultdict(list)
    uses: dict[str, str] = {}
    for e in edges:
        rel, frm, to = e.get("rel"), e["from"], e["to"]
        if rel == "uses" and frm.startswith("assessment:") and to.startswith("material:"):
            uses[frm] = to
        if frm.startswith("lesson:") and rel in ("describes", "spanIn", "hasPart"):
            if to.startswith("material:") or to.startswith("assessment:"):
                lesson_kids[frm].append((rel, to))

    rows: list[dict[str, str]] = [
        {
            "path": "course",
            "kind": "course",
            "label": f"Course · {course.get('name') or course['id']}",
        },
    ]

    for unit in units:
        uid = unit["id"].split(":", 1)[1]
        uk = unit_key(uid)
        upath = f"course/{uk}"
        rows.append(
            {
                "path": upath,
                "kind": "unit",
                "label": UNIT_TITLES.get(uid, f"Unit · {uid}"),
            }
        )

        lessons = sorted(
            [
                n
                for n in g["nodes"]
                if n.get("type") == "Lesson"
                and (n.get("unit_id") == uid or n["id"].startswith(f"lesson:{uid}:"))
            ],
            key=lambda n: n.get("lesson_n") or 0,
        )
        for les in lessons:
            n = les["lesson_n"]
            lpath = f"{upath}/l{n}"
            rows.append({"path": lpath, "kind": "lesson", "label": les["name"]})

            kids = sorted(
                lesson_kids.get(les["id"], []),
                key=lambda t: (REL_ORDER.get(t[0], 9), nodes[t[1]].get("name") or t[1]),
            )
            for rel, tid in kids:
                node = nodes[tid]
                if tid.startswith("assessment:"):
                    apath = f"{lpath}/assessment_{slug(tid)}"
                    rows.append(
                        {
                            "path": apath,
                            "kind": "assessment",
                            "label": f"ASSESS {node.get('name') or tid}",
                        }
                    )
                    mid = uses.get(tid)
                    if mid and mid in nodes:
                        m = nodes[mid]
                        mfile = short_file(m.get("source_file") or m.get("name") or mid)
                        rows.append(
                            {
                                "path": f"{apath}/uses_{slug(mid)}",
                                "kind": "uses",
                                "label": f"uses {mfile}",
                            }
                        )
                else:
                    kind = node.get("artifact_kind") or "other"
                    mfile = short_file(node.get("source_file") or node.get("name") or tid)
                    rows.append(
                        {
                            "path": f"{lpath}/{rel}_{slug(tid)}",
                            "kind": "material",
                            "label": f"{rel} · {mfile} [{kind}]",
                        }
                    )

    OUT.write_text(json.dumps(rows, indent=2) + "\n")
    counts: Counter[str] = Counter()
    for r in rows:
        parts = r["path"].split("/")
        if len(parts) >= 3 and parts[1] in {"cattle", "anatomy"} and parts[2].startswith("l"):
            if len(parts) == 3:
                counts[f"{parts[1]}/{parts[2]}"] += 0
            else:
                counts[f"{parts[1]}/{parts[2]}"] += 1
    print(f"wrote {OUT} rows={len(rows)}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v} children")


if __name__ == "__main__":
    main()
