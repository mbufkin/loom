#!/usr/bin/env python3
"""
Auto-improve local ingest-organize on lab-ag-arts-mix.

Hypothesis: local Nemotron-3-Nano-30B can cleanly separate Ag vs Arts AV if it
gets (a) more document text than the stock 200-char catalog and (b) tight
instructions + repair loops on concrete failures.

Does NOT modify production ingest.py. Writes under experiments/ingest_mix_local/.

Usage:
  LOOM_CONFIG=config.yaml .venv/bin/python experiments/ingest_mix_local/run_improve.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit_lib import (  # noqa: E402
    extract_content,
    load_config,
    log,
    model_chat,
    parse_model_json,
)
from ingest import build_catalog, validate_coverage  # noqa: E402
from schema_validate import validate_ingest_plan  # noqa: E402

PROJECT = "lab-ag-arts-mix"
SOURCES = ROOT / "projects" / PROJECT / "sources"
OUT = Path(__file__).resolve().parent / "results"
MAX_ITERS = 8

# Gold separation for this experiment (known correct piles).
GOLD = {
    "agriculture-plant-science": {
        "doc_b5e36486805a_Agriculture-_Plant_Science.txt",
        "doc_e9e6ac00ce09_Agriculture-_Plant_Science_Alternate_Lesson_Plan_Template.txt",
    },
    "arts-av-technology-communication": {
        "doc_0a62e0b9729e_Arts_A_V_Student_Notes.txt",
        "doc_0cbd06c7c769_Arts_AV_Technology___Communication_Flyer_Project_Rubric.txt",
        "doc_314d7d0905ca_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_1.txt",
        "doc_761e6495bc24_Arts_A_V_Tech__Lesson_Plan_.txt",
        "doc_89430d6aae63_Arts_AV_Technology___Communication_-_Slides.txt",
        "doc_af9cf3b04474_Arts_AV_Technology___Communication_Commercial_Project_Rubric.txt",
        "doc_e2c12c61bc5f_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_3.txt",
        "doc_ff5cd4c0712e_Arts_AV_Technology___Communication_-__Exit_Ticket_Day_2.txt",
    },
}

SCHEMA = """
Respond with ONLY valid JSON (no markdown fences):
{
  "school_calendar_hint": {
    "school_year": null,
    "notes": null,
    "grading_periods": []
  },
  "units": [
    {
      "unit_id": "slug",
      "title": "Human Title",
      "source_files": ["exact-filename-from-allowlist.txt"],
      "calendar": {
        "unit_length_days": 3,
        "days": [
          {"id": "d1", "label": "Day 1", "expected": ["lesson_content"]}
        ],
        "unit_supporting": ["lesson_plan"]
      }
    }
  ]
}
"""


def norm_name(p: str) -> str:
    p = str(p).strip().lstrip("./")
    if p.startswith("sources/"):
        p = p[len("sources/") :]
    return Path(p).name


def normalize_plan(plan: dict, allow: set[str]) -> dict:
    """Code repair for brittle formatting — strip path prefixes, int days, slug hyphens.

    Educational note: keep model judgment for *which files go where*; normalize only
    mechanical contract fields the weaker model repeatedly flubs (path prefix, float
    day counts, underscores in slugs). Do not silently drop/reassign files here.
    """
    if not isinstance(plan, dict):
        return plan
    units = []
    for u in plan.get("units") or []:
        if not isinstance(u, dict):
            continue
        files = [norm_name(f) for f in (u.get("source_files") or [])]
        cal = dict(u.get("calendar") or {})
        uld = cal.get("unit_length_days")
        if isinstance(uld, float):
            cal["unit_length_days"] = max(1, int(round(uld)))
        elif isinstance(uld, str) and uld.replace(".", "", 1).isdigit():
            cal["unit_length_days"] = max(1, int(round(float(uld))))
        days = cal.get("days") or []
        if cal.get("unit_length_days") is not None and days:
            try:
                if int(cal["unit_length_days"]) != len(days):
                    cal["unit_length_days"] = len(days)
            except (TypeError, ValueError):
                cal["unit_length_days"] = len(days) or 1
        uid = u.get("unit_id")
        if isinstance(uid, str):
            # Loom slugs are hyphenated: agri_plant_science → agri-plant-science
            uid = re.sub(r"_+", "-", uid.strip().lower())
        units.append(
            {
                **u,
                "unit_id": uid,
                "source_files": files,
                "calendar": cal,
            }
        )
    out = dict(plan)
    out["units"] = units
    return out


def rich_catalog_block(records: list[dict], *, max_chars: int) -> str:
    """More text than stock ingest (200 chars). Small files → full clean text."""
    lines = [
        "FILE ALLOWLIST (copy these strings EXACTLY into source_files — no sources/ prefix, no renaming):",
    ]
    for r in records:
        lines.append(f"  - {r['source_file']}")
    lines.append("")
    lines.append(f"DOCUMENT CATALOG ({len(records)} files, up to {max_chars} chars each):")
    for r in records:
        body = (r.get("content_clean") or r.get("excerpt_head") or "")[:max_chars]
        lines.append(
            f"\n### FILE: {r['source_file']}\n"
            f"fmt={r.get('source_format')} prior_type={r.get('doc_type')} "
            f"day_hints={r.get('day_hints')} len_hint={r.get('unit_length_days_hint')} "
            f"title={r.get('title')!r} chars={r.get('char_count_clean')}\n"
            f"TEXT:\n{body}\n"
        )
    return "\n".join(lines)


def base_rules(allow: list[str]) -> str:
    return f"""
You are a curriculum document organizer. READ-ONLY. Local-model mode: be literal.

GOAL: Put every file into exactly one unit. This pile mixes TWO subjects
(Agriculture / Plant Science vs Arts A/V Technology). Do not merge them.

HARD RULES:
1. source_files entries MUST be copied EXACTLY from the allowlist. Character-for-character.
2. NEVER invent, rename, merge, or prefix filenames (no "sources/", no new hashes).
3. Every allowlist file appears in exactly one unit. No leftovers. No duplicates.
4. unit_length_days MUST be a positive INTEGER (not 2.5). Prefer matching the number of Day N headings / Estimated Day(s).
5. day ids are d1, d2, ... consecutive.
6. Group by subject evidence in the TEXT (career cluster names, TEKS, titles) — not by guessing from a single shared word.
7. Rubrics and exit tickets belong with their cluster's lesson plan/slides, not alone and not in the other cluster.
8. If unsure, keep Agriculture files with Agriculture titles; Arts/A/V/Communication files with Arts.

ALLOWLIST ({len(allow)}):
{chr(10).join('  - ' + a for a in allow)}
"""


def score_gold(plan: dict) -> tuple[bool, list[str], dict]:
    """Return (perfect, notes, detail). Unit ids may differ; match by best Jaccard to gold sets."""
    notes: list[str] = []
    unit_docs: dict[str, set[str]] = {}
    for u in plan.get("units") or []:
        uid = u.get("unit_id") or "?"
        unit_docs[uid] = {norm_name(f) for f in (u.get("source_files") or [])}

    detail = {"units": {k: sorted(v) for k, v in unit_docs.items()}}
    used: set[str] = set()
    perfect = True
    for gname, gset in GOLD.items():
        best_uid, best_j = None, -1.0
        for uid, dset in unit_docs.items():
            if uid in used:
                continue
            union = dset | gset
            j = (len(dset & gset) / len(union)) if union else 0.0
            if j > best_j:
                best_j, best_uid = j, uid
        if best_uid is None:
            perfect = False
            notes.append(f"{gname}: no predicted unit")
            continue
        used.add(best_uid)
        dset = unit_docs[best_uid]
        fp = sorted(dset - gset)
        fn = sorted(gset - dset)
        detail[gname] = {"matched_unit": best_uid, "jaccard": best_j, "fp": fp, "fn": fn}
        if fp or fn:
            perfect = False
            if fp:
                notes.append(f"{gname} via {best_uid}: false positives {fp}")
            if fn:
                notes.append(f"{gname} via {best_uid}: missing {fn}")
        else:
            notes.append(f"{gname} ↔ {best_uid}: PASS jaccard=1.0")

    # extras / wrong unit count
    if len(unit_docs) != 2:
        perfect = False
        notes.append(f"expected 2 units, got {len(unit_docs)}: {list(unit_docs)}")
    return perfect, notes, detail


def gold_repair_feedback(detail: dict, allow: set[str]) -> str:
    lines = [
        "GOLD CRITIQUE (experiment oracle — fix these concrete errors):",
        "Target shape: exactly 2 units — one Agriculture/Plant Science (2 files), one Arts A/V (8 files).",
    ]
    for gname in GOLD:
        d = detail.get(gname) or {}
        if d.get("fp"):
            lines.append(f"- Remove from the unit matched to {gname}: {d['fp']}")
        if d.get("fn"):
            lines.append(f"- Add into the {gname} unit: {d['fn']}")
    # any allow files not in any unit already covered by fn
    lines.append("Re-emit the FULL corrected JSON plan. Keep exact allowlist filenames.")
    lines.append(f"Allowlist again: {sorted(allow)}")
    return "\n".join(lines)


def call_organize(cfg: dict, prompt: str, step: str) -> dict:
    resp = model_chat(
        cfg,
        "analyst",
        [{"role": "user", "content": prompt}],
        step,
        temperature=0.1,
    )
    return parse_model_json(extract_content(resp), context=step)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    models = cfg.get("models") or {}
    log(
        f"local improve: model={models.get('analyst_model')} "
        f"url={models.get('analyst_url')}"
    )

    records, _ = build_catalog(SOURCES)
    allow = sorted(r["source_file"] for r in records)
    allow_set = set(allow)

    # Escalating text budgets across iterations if still failing.
    char_budgets = [800, 2000, 6000, 12000, 12000, 20000, 20000, 50000]

    results_path = OUT / "RESULTS.md"
    results_path.write_text(
        "# lab-ag-arts-mix local auto-improve\n\n"
        f"Model: `{models.get('analyst_model')}` via `{models.get('analyst_url')}`\n"
        f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n",
        encoding="utf-8",
    )

    last_plan: dict | None = None
    stuck_same = 0
    prev_sig = ""

    for i in range(1, MAX_ITERS + 1):
        budget = char_budgets[min(i - 1, len(char_budgets) - 1)]
        catalog = rich_catalog_block(records, max_chars=budget)
        step = f"mix-local-iter{i}"

        if i == 1 or last_plan is None:
            prompt = f"{base_rules(allow)}\n\n{catalog}\n\n{SCHEMA}\n"
            mode = "fresh"
        else:
            # repair from last attempt
            cov = validate_coverage(records, last_plan)
            sch = validate_ingest_plan(last_plan)
            ok_gold, gold_notes, detail = score_gold(last_plan)
            critique = []
            if cov or sch:
                critique.append("VALIDATOR ERRORS:")
                critique.extend(f"  - {e}" for e in cov + sch)
            if not ok_gold:
                critique.append(gold_repair_feedback(detail, allow_set))
            prompt = (
                f"{base_rules(allow)}\n\n"
                f"Your previous JSON failed. Fix it.\n\n"
                + "\n".join(critique)
                + f"\n\nPREVIOUS_JSON:\n{json.dumps(last_plan, indent=2)}\n\n"
                f"{catalog}\n\n{SCHEMA}\n"
            )
            mode = "repair"

        log(f"=== iter {i}/{MAX_ITERS} mode={mode} budget={budget} ===")
        t0 = time.time()
        try:
            raw_plan = call_organize(cfg, prompt, step)
        except Exception as e:
            log(f"iter {i} model/parse ERROR: {e}")
            with results_path.open("a") as f:
                f.write(f"## Iter {i} — ERROR\n\n`{e}`\n\n")
            stuck_same += 1
            if stuck_same >= 3:
                log("stuck: repeated model/parse failures")
                break
            continue

        plan = normalize_plan(raw_plan, allow_set)
        (OUT / f"iter{i}-raw.json").write_text(json.dumps(raw_plan, indent=2), encoding="utf-8")
        (OUT / f"iter{i}-normalized.json").write_text(
            json.dumps(plan, indent=2), encoding="utf-8"
        )
        (OUT / f"iter{i}-prompt.txt").write_text(prompt, encoding="utf-8")

        cov = validate_coverage(records, plan)
        sch = validate_ingest_plan(plan)
        ok_gold, gold_notes, detail = score_gold(plan)
        elapsed = time.time() - t0

        sig = json.dumps(
            {u.get("unit_id"): sorted(u.get("source_files") or []) for u in plan.get("units") or []},
            sort_keys=True,
        )
        if sig == prev_sig:
            stuck_same += 1
        else:
            stuck_same = 0
            prev_sig = sig
        last_plan = plan

        status = "PASS" if (ok_gold and not cov and not sch) else "FAIL"
        log(f"iter {i} {status} ({elapsed:.1f}s) gold={ok_gold} cov={cov} sch={sch}")
        for n in gold_notes:
            log(f"  {n}")

        with results_path.open("a") as f:
            f.write(f"## Iter {i} — {status} ({elapsed:.1f}s, budget={budget}, mode={mode})\n\n")
            f.write(f"- coverage errors: {cov or 'none'}\n")
            f.write(f"- schema errors: {sch or 'none'}\n")
            f.write(f"- gold: {'; '.join(gold_notes)}\n")
            f.write(f"- detail: `{json.dumps(detail)[:500]}`\n\n")

        if status == "PASS":
            # write side-by-side success artifact; do not clobber grok manifest unless asked
            success_dir = OUT / "SUCCESS"
            success_dir.mkdir(exist_ok=True)
            (success_dir / "organize.json").write_text(
                json.dumps(plan, indent=2), encoding="utf-8"
            )
            (success_dir / "detail.json").write_text(
                json.dumps(detail, indent=2), encoding="utf-8"
            )
            log(f"SUCCESS on iter {i} → {success_dir}")
            with results_path.open("a") as f:
                f.write(f"**SUCCESS on iter {i}.**\n")
            return 0

        if stuck_same >= 3:
            log("stuck: same assignment 3 times — stopping")
            with results_path.open("a") as f:
                f.write("**STUCK** — identical assignments repeated.\n")
            return 2

    log("exhausted iterations without PASS")
    with results_path.open("a") as f:
        f.write("**EXHAUSTED** — no PASS within max iters.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
