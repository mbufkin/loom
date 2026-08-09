#!/usr/bin/env python3
"""Compare Dallas E2E route/path findings between two run trees.

Educational note: use this after a new A–H presence run to show routing
redistribution (especially C→B/D/E/H) and stub→presence depth upgrades.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _summarize(run_dir: Path) -> dict:
    out: dict = {"run_dir": str(run_dir), "exists": run_dir.is_dir()}
    rm = run_dir / "layer0" / "route-map.json"
    if rm.is_file():
        data = json.loads(rm.read_text(encoding="utf-8"))
        routes = data.get("routes") or []
        out["generated_at"] = data.get("generated_at")
        out["route_total"] = len(routes)
        out["path_counts"] = dict(
            sorted(Counter(r.get("path") for r in routes).items())
        )
        out["workflow_counts"] = dict(
            sorted(Counter(r.get("workflow_id") for r in routes).items())
        )
        # sample exit tickets / syllabi if any
        out["exit_ticket_docs"] = sum(
            1 for r in routes if r.get("workflow_id") == "exit_ticket"
        )
        out["syllabus_docs"] = sum(
            1 for r in routes if r.get("workflow_id") == "syllabus"
        )
    paths: dict = {}
    for letter in "abcdefgh":
        pf = run_dir / f"path_{letter}" / "findings.json"
        if not pf.is_file():
            paths[letter] = None
            continue
        d = json.loads(pf.read_text(encoding="utf-8"))
        step_status: dict[str, Counter] = defaultdict(Counter)
        for row in d.get("inventory") or []:
            for k, v in row.items():
                if (
                    isinstance(v, dict)
                    and "status" in v
                    and len(k) >= 2
                    and k[0].isalpha()
                    and k[1].isdigit()
                ):
                    step_status[k][v.get("status")] += 1
        for _did, steps in (d.get("steps_by_doc") or {}).items():
            for sk, sv in steps.items():
                if isinstance(sv, dict) and "status" in sv:
                    step_status[sk][sv.get("status")] += 1
        paths[letter] = {
            "status": d.get("status"),
            "doc_count": len(d.get("doc_ids") or []),
            "checklist": d.get("checklist"),
            "has_steps_by_doc": bool(d.get("steps_by_doc")),
            "step_status": {k: dict(v) for k, v in sorted(step_status.items())},
        }
    out["paths"] = paths
    return out


def _md_table(old: dict, new: dict) -> str:
    letters = list("ABCDEFGH")
    lines = [
        "# Dallas E2E path comparison",
        "",
        f"- **Old:** `{old.get('run_dir')}` ({old.get('generated_at') or 'n/a'})",
        f"- **New:** `{new.get('run_dir')}` ({new.get('generated_at') or 'n/a'})",
        "",
        "## Route distribution",
        "",
        "| Path | Old | New | Δ |",
        "|------|----:|----:|--:|",
    ]
    oc = old.get("path_counts") or {}
    nc = new.get("path_counts") or {}
    for L in letters:
        a, b = int(oc.get(L, 0)), int(nc.get(L, 0))
        delta = b - a
        sign = f"+{delta}" if delta > 0 else str(delta)
        lines.append(f"| {L} | {a} | {b} | {sign} |")
    lines += [
        f"| **Total** | {old.get('route_total', 0)} | {new.get('route_total', 0)} | |",
        "",
        "## Path findings depth",
        "",
        "| Path | Old status / docs | New status / docs | Notes |",
        "|------|-------------------|-------------------|-------|",
    ]
    for L in letters:
        o = (old.get("paths") or {}).get(L.lower())
        n = (new.get("paths") or {}).get(L.lower())
        o_s = "MISSING" if o is None else f"{o.get('status')}/{o.get('doc_count')}"
        n_s = "MISSING" if n is None else f"{n.get('status')}/{n.get('doc_count')}"
        note = []
        if o is None and n is not None:
            note.append("new lens artifacts")
        if n and n.get("checklist"):
            note.append("checklist")
        if n and n.get("has_steps_by_doc"):
            note.append("steps_by_doc")
        if o and o.get("status") == "stub" and n and n.get("status") in {"ok", None}:
            note.append("stub→presence")
        lines.append(f"| {L} | {o_s} | {n_s} | {', '.join(note) or '—'} |")
    lines += [
        "",
        f"- Exit tickets routed (new): **{new.get('exit_ticket_docs', 0)}**",
        f"- Syllabi routed (new): **{new.get('syllabus_docs', 0)}**",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--old",
        type=Path,
        default=Path("projects/dallas-career-2026/e2e/runs/grok-4.5"),
    )
    ap.add_argument(
        "--new",
        type=Path,
        required=True,
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(
            "projects/dallas-career-2026/e2e/comparisons/latest-ah-vs-old.md"
        ),
    )
    args = ap.parse_args()
    old = _summarize(args.old)
    new = _summarize(args.new)
    md = _md_table(old, new)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    json_out = args.out.with_suffix(".json")
    json_out.write_text(
        json.dumps({"old": old, "new": new}, indent=2), encoding="utf-8"
    )
    print(md)
    print(f"\nWrote {args.out} and {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
