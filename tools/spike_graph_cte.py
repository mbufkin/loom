#!/usr/bin/env python3
"""SPIKE ONLY — CTE graph sort (type then connect). Not production graph_phase.

Educational note
----------------
Bluebonnet TE/SE roles are intentionally unused here. This runner proves:

  Layer 0 full evidence
    → Pass 1: artifact_kind (what is it?)  [per unit]
    → Lesson spine from lesson_plan docs  [per unit]
    → Pass 2: connect to Lessons (kind frozen)  [per unit, isolated spine]
    → thin kind→Path preview (no second classifier)
    → anti-mangle checks across units (no cross-unit edges)

Isolated lab: projects/lab-graph-cte-cattle/ (cattle + external anatomy)
Does not import or modify graph_phase.ROLES / step_role.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_lib import load_config, log, model_chat, parse_model_json  # noqa: E402
from graph_inventory import build_provisional, gate_a, material_id  # noqa: E402

LAB_ID = "lab-graph-cte-cattle"

ARTIFACT_KINDS = frozenset(
    {
        "lesson_plan",
        "assessment",
        "student_practice",
        "teacher_support",
        "standards_pacing",
        "other",
    }
)

# Thin Path preview — code table only (not a model).
PATH_BY_KIND = {
    "lesson_plan": "A",
    "assessment": "B",
    "student_practice": "E",
    "teacher_support": "D",
    "standards_pacing": "F",
    "other": "C",
}


def lab_dir() -> Path:
    return ROOT / "projects" / LAB_ID


def load_expected_paths(root: Path | None = None) -> dict:
    path = (root or lab_dir()) / "EXPECTED-PATHS.json"
    return json.loads(path.read_text(encoding="utf-8"))


def score_paths(
    unit_results: list[dict],
    *,
    expected: dict | None = None,
) -> dict:
    """Score Pass-1 kinds against gold Path expectations (no model calls).

    Educational note: Path is not a second classifier — it is PATH_BY_KIND[kind].
    Failures here mean Pass 1 typed the wrong kind for the gold Path.
    """
    gold = expected or load_expected_paths()
    docs = gold.get("documents") or {}
    table = gold.get("path_by_kind") or PATH_BY_KIND

    # Flatten observed kinds from unit runs
    observed: dict[str, dict] = {}
    for u in unit_results:
        for sf, krow in (u.get("kinds") or {}).items():
            observed[sf] = {
                "unit_id": u["unit_id"],
                "kind": (krow or {}).get("artifact_kind") or "other",
            }

    rows = []
    missing_gold = []
    missing_obs = []
    for sf, exp in sorted(docs.items()):
        if sf not in observed:
            missing_obs.append(sf)
            rows.append(
                {
                    "source_file": sf,
                    "status": "MISSING_OBS",
                    "expected_kind": exp.get("expected_kind"),
                    "expected_path": exp.get("expected_path"),
                    "got_kind": None,
                    "got_path": None,
                    "rationale": exp.get("rationale"),
                }
            )
            continue
        got_kind = observed[sf]["kind"]
        got_path = table.get(got_kind) or PATH_BY_KIND.get(got_kind, "?")
        exp_kind = exp.get("expected_kind")
        exp_path = exp.get("expected_path")
        kind_ok = got_kind == exp_kind
        path_ok = got_path == exp_path
        # Table sanity: expected_kind must map to expected_path
        table_ok = table.get(exp_kind) == exp_path
        status = "PASS" if (kind_ok and path_ok and table_ok) else "FAIL"
        rows.append(
            {
                "source_file": sf,
                "unit_id": observed[sf]["unit_id"],
                "status": status,
                "expected_kind": exp_kind,
                "expected_path": exp_path,
                "got_kind": got_kind,
                "got_path": got_path,
                "kind_ok": kind_ok,
                "path_ok": path_ok,
                "table_ok": table_ok,
                "rationale": exp.get("rationale"),
            }
        )

    for sf in sorted(observed):
        if sf not in docs:
            missing_gold.append(sf)

    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_miss = sum(1 for r in rows if r["status"] == "MISSING_OBS")
    return {
        "overall": "PASS" if n_fail == 0 and n_miss == 0 and not missing_gold else "FAIL",
        "n_gold": len(docs),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_missing_obs": n_miss,
        "missing_gold_for_observed": missing_gold,
        "rows": rows,
    }


def write_path_score(out_dir: Path, score: dict) -> Path:
    lines = [
        "# CTE spike — Path score (gold expectations)",
        "",
        f"**Overall:** {score['overall']}",
        f"**Gold docs:** {score['n_gold']} · "
        f"PASS {score['n_pass']} · FAIL {score['n_fail']} · "
        f"missing obs {score['n_missing_obs']}",
        "",
        "Path = thin `kind → Path` table after Pass 1 (not a second model sort).",
        "",
        "| Status | source_file | expected | got |",
        "|--------|-------------|----------|-----|",
    ]
    for r in score["rows"]:
        exp = f"{r.get('expected_kind')}→{r.get('expected_path')}"
        got = f"{r.get('got_kind')}→{r.get('got_path')}"
        lines.append(
            f"| {r['status']} | `{r['source_file']}` | `{exp}` | `{got}` |"
        )

    fails = [r for r in score["rows"] if r["status"] == "FAIL"]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines += [
                f"### `{r['source_file']}`",
                "",
                f"- Expected: `{r['expected_kind']}` → Path **{r['expected_path']}**",
                f"- Got: `{r['got_kind']}` → Path **{r['got_path']}**",
                f"- Rationale: {r.get('rationale') or '—'}",
                "",
            ]

    if score.get("missing_gold_for_observed"):
        lines += [
            "",
            "## Observed docs with no gold row",
            "",
        ]
        for sf in score["missing_gold_for_observed"]:
            lines.append(f"- `{sf}`")

    path = out_dir / "PATH-SCORE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "PATH-SCORE.json").write_text(
        json.dumps(score, indent=2) + "\n", encoding="utf-8"
    )
    return path


def chat_json(cfg: dict, step: str, prompt: str) -> dict:
    resp = model_chat(
        cfg,
        "analyst",
        [{"role": "user", "content": prompt}],
        f"spike-cte-{step}",
        temperature=0.1,
    )
    text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return parse_model_json(text, context=step)


def load_manifest_units(root: Path) -> list[dict]:
    """Return [{unit_id, title, documents}] in manifest order."""
    man = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    out = []
    for unit_id, meta in (man.get("units") or {}).items():
        out.append(
            {
                "unit_id": unit_id,
                "title": meta.get("title") or unit_id,
                "documents": list(meta.get("documents") or []),
            }
        )
    return out


def load_evidence_by_source(ledger_path: Path) -> dict[str, list[dict]]:
    rows = json.loads(ledger_path.read_text(encoding="utf-8"))
    by: dict[str, list[dict]] = {}
    for e in rows:
        sf = e.get("source_file")
        if not sf:
            continue
        by.setdefault(sf, []).append(e)
    return by


def evidence_pack(source_file: str, elements: list[dict]) -> dict:
    """Full Layer 0 text for the model — match production local intent.

    Educational note
    ----------------
    Production ``graph_phase`` local steps dump every ledger row with
    **uncapped** excerpts (no 900-char clip). This spike matches that.

    iCEV Layer 0 sometimes repeats the *same* wide-span excerpt across many
    element_type rows (e.g. 39× identical action-plan text). Sending that
    verbatim matches production bytes but blows the context window and hung
    the Grok bridge. We therefore keep **uncapped** text but collapse
    duplicate excerpt strings, listing every element_id/type that shared it.
    Information content = full document once; not a head-only clip.
    """
    # excerpt text → first slim row + sibling ids/types
    by_text: dict[str, dict] = {}
    order: list[str] = []
    for e in elements:
        ex = e.get("excerpt") or ""
        if ex not in by_text:
            by_text[ex] = {
                "element_id": e.get("element_id"),
                "element_type": e.get("element_type"),
                "excerpt": ex,
                "excerpt_start_paragraph": e.get("excerpt_start_paragraph"),
                "excerpt_end_paragraph": e.get("excerpt_end_paragraph"),
                "also_element_ids": [],
                "also_element_types": [],
            }
            order.append(ex)
        else:
            row = by_text[ex]
            eid = e.get("element_id")
            et = e.get("element_type")
            if eid and eid != row["element_id"]:
                row["also_element_ids"].append(eid)
            if et and et != row["element_type"] and et not in row["also_element_types"]:
                row["also_element_types"].append(et)

    slim = []
    for ex in order:
        row = by_text[ex]
        item = {
            "element_id": row["element_id"],
            "element_type": row["element_type"],
            "excerpt": row["excerpt"],
            "excerpt_start_paragraph": row["excerpt_start_paragraph"],
            "excerpt_end_paragraph": row["excerpt_end_paragraph"],
        }
        if row["also_element_ids"] or row["also_element_types"]:
            item["duplicate_ledger_rows"] = 1 + len(row["also_element_ids"])
            if row["also_element_types"]:
                item["also_element_types"] = row["also_element_types"]
        slim.append(item)

    note = None
    if len(slim) < len(elements):
        note = (
            f"collapsed {len(elements)} ledger rows → {len(slim)} unique "
            f"uncapped excerpts (duplicate wide-span text removed)"
        )
    return {
        "source_file": source_file,
        "n_elements_ledger": len(elements),
        "n_elements": len(slim),
        "truncation_note": note,
        "elements": slim,
    }


def pass1_type(cfg: dict, source_file: str, elements: list[dict], raw_dir: Path) -> dict:
    pack = evidence_pack(source_file, elements)
    # Educational note: artifact_kind is the model's only type decision.
    # Path letter is assigned later in Python. Keep the JSON example as ONE
    # concrete kind (not a pipe-list) — smaller local models echoed the list.
    prompt = f"""You are typing ONE CTE curriculum document for a course graph.

Task: choose exactly one artifact_kind for what this document's primary job is.
Read the Layer 0 evidence. Prefer substance over filename, but use the rules below when names and content conflict.

SOURCE_FILE: {source_file}

Allowed artifact_kind values (pick exactly one token — never a list):
  lesson_plan — the instructional lesson plan itself (View Lesson Plan / class-by-class teaching plan with objectives, hooks, and teacher steps for the pack)
  assessment — quiz, check-for-understanding, final test, or answer key
  student_practice — student-facing work: Action Plan task checklist, worksheets, activities, flashcards, vocab handouts, key-concepts guided notes, student projects
  teacher_support — facilitator/implementation guide that is NOT a lesson plan and NOT student work
  standards_pacing — standards alignments, NGSS/TEKS maps, horizontal alignments (not instruction)
  other — none of the above

Disambiguation (common iCEV packs):
  - Filename/title "View Lesson Plan" or a document whose primary job is the teacher class sequence → lesson_plan.
  - Filename/title "Action Plan" that lists tasks for students to complete → student_practice, even if it also prints objectives or class overviews.
  - "Key Concepts" fill-in / guided notes for students → student_practice (not teacher_support, not lesson_plan).
  - Student project sheets ("you will create…", peer eval, rubric for the student) → student_practice.
  - Answer keys travel with assessments → assessment.

FULL_LAYER0_EVIDENCE_JSON:
{json.dumps(pack, ensure_ascii=False)}

Respond with ONLY one JSON object. artifact_kind must be a single token from the list above.
Example shape (replace fields; do not copy example kind blindly):
{{"source_file":"{source_file}","artifact_kind":"student_practice","citation_element_id":"e1","excerpt_head":"short quote <=120 chars","notes":"why this kind"}}
"""
    data = chat_json(cfg, f"type-{Path(source_file).stem[:48]}", prompt)
    kind = str(data.get("artifact_kind") or "").strip().lower()
    if kind not in ARTIFACT_KINDS:
        log(f"WARN invalid kind {kind!r} → other for {source_file}")
        data["artifact_kind"] = "other"
        data["kind_fallback"] = True
    data["source_file"] = source_file
    (raw_dir / f"01-type-{Path(source_file).stem}.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    return data


def class_nums_from_text(text: str) -> list[int]:
    found = sorted({int(n) for n in re.findall(r"(?i)\bclass\s+(\d+)\b", text or "")})
    return [n for n in found if 1 <= n <= 40]


def build_spine_from_lesson_plans(
    cfg: dict,
    kinds: dict[str, dict],
    evidence: dict[str, list[dict]],
    raw_dir: Path,
    *,
    unit_id: str,
) -> list[dict]:
    """Return [{n, label}] lesson spine for ONE unit only."""
    lp_files = [
        sf for sf, k in kinds.items() if k.get("artifact_kind") == "lesson_plan"
    ]
    if not lp_files:
        return [{"n": 1, "label": "Lesson 1"}]

    primary = sorted(lp_files, key=lambda s: -len(evidence.get(s) or []))[0]
    pack = evidence_pack(primary, evidence[primary])
    prompt = f"""From this CTE lesson plan evidence, list the instructional lessons/classes.

UNIT_ID: {unit_id}
SOURCE_FILE: {primary}
FULL_LAYER0_EVIDENCE_JSON:
{json.dumps(pack, ensure_ascii=False)}

If the plan has Class 1, Class 2, … use those numbers.
If it is a single undivided lesson, return one lesson n=1.
Do NOT invent lessons from other units.

Respond ONLY JSON:
{{"source_file":"{primary}","unit_id":"{unit_id}","lessons":[{{"n":1,"label":"Class 1 — short title"}}],"notes":"short"}}
"""
    data = chat_json(cfg, f"spine-{unit_id[:28]}-{Path(primary).stem[:28]}", prompt)
    (raw_dir / f"01b-spine-{unit_id}.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    lessons_out: list[dict] = []
    for item in data.get("lessons") or []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 40:
            lessons_out.append(
                {"n": n, "label": str(item.get("label") or f"Class {n}").strip()}
            )
    if lessons_out:
        lessons_out.sort(key=lambda x: x["n"])
        return lessons_out

    bag: set[int] = set()
    for sf in lp_files:
        for e in evidence.get(sf) or []:
            bag.update(class_nums_from_text(e.get("excerpt") or ""))
    if bag:
        return [{"n": n, "label": f"Class {n}"} for n in sorted(bag)]
    return [{"n": 1, "label": "Lesson 1"}]


def pass2_connect(
    cfg: dict,
    source_file: str,
    elements: list[dict],
    kind: str,
    spine: list[dict],
    typed_inventory: list[dict],
    raw_dir: Path,
    *,
    unit_id: str,
) -> dict:
    pack = evidence_pack(source_file, elements)
    spine_json = json.dumps(spine, ensure_ascii=False)
    inv_json = json.dumps(typed_inventory, ensure_ascii=False)
    prompt = f"""Connect ONE typed curriculum document to Lessons in a CTE unit graph.

Do NOT change artifact_kind. Kind is already decided: {kind}
Do NOT attach to any other unit. This document belongs ONLY to unit_id={unit_id}.

SOURCE_FILE: {source_file}
UNIT_ID: {unit_id}
ARTIFACT_KIND: {kind}

UNIT_LESSON_SPINE (attach only to these n values — this unit only):
{spine_json}

UNIT_TYPED_INVENTORY (this unit only — context):
{inv_json}

FULL_LAYER0_EVIDENCE_JSON:
{json.dumps(pack, ensure_ascii=False)}

Rules:
- covers_lesson_numbers: subset of spine n values this document supports.
- lesson_plan that spans the whole pack may cover all spine lessons.
- A single CFU for one topic likely covers the matching class only when clear; else best guess with note.
- is_assessment_bearing: true for assessment kind (quiz/key/final/CFU).

Respond ONLY JSON:
{{"source_file":"{source_file}","unit_id":"{unit_id}","artifact_kind":"{kind}","covers_lesson_numbers":[1],"is_assessment_bearing":false,"assessment_name":null,"notes":"short"}}
"""
    data = chat_json(cfg, f"connect-{unit_id[:20]}-{Path(source_file).stem[:40]}", prompt)
    data["artifact_kind"] = kind
    data["source_file"] = source_file
    data["unit_id"] = unit_id
    nums = []
    for x in data.get("covers_lesson_numbers") or []:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if any(s["n"] == n for s in spine):
            nums.append(n)
    data["covers_lesson_numbers"] = sorted(set(nums))
    if not data["covers_lesson_numbers"] and spine:
        data["covers_lesson_numbers"] = [spine[0]["n"]]
        data["connect_defaulted"] = True
    if kind == "assessment":
        data["is_assessment_bearing"] = True
    (raw_dir / f"02-connect-{Path(source_file).stem}.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    return data


def rebuild_cte(
    provisional: dict,
    *,
    unit_id: str,
    spine: list[dict],
    kinds: dict[str, dict],
    connects: dict[str, dict],
    sources: list[str],
) -> dict:
    """Spike-local rebuild — Lesson nodes + artifact_kind (not TE/SE roles)."""
    graph = deepcopy(provisional)
    graph["stage"] = "rebuilt-cte-spike"
    graph["method"] = "spike-graph-cte-v0-multi"
    graph["model"] = "cte-artifact-kind"
    unit_node = f"unit:{unit_id}"
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}

    for lesson in spine:
        n = lesson["n"]
        lid = f"lesson:{unit_id}:l{n}"
        if lid not in nodes_by_id:
            node = {
                "id": lid,
                "type": "Lesson",
                "name": lesson.get("label") or f"Class {n}",
                "lesson_n": n,
                "unit_id": unit_id,
            }
            graph["nodes"].append(node)
            nodes_by_id[lid] = node
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": lid})

    graph["edges"] = [
        e
        for e in graph["edges"]
        if not (
            e.get("rel") == "hasPart"
            and e.get("from") == unit_node
            and str(e.get("to", "")).startswith("material:")
        )
    ]

    id_by_n = {s["n"]: f"lesson:{unit_id}:l{s['n']}" for s in spine}

    for sf in sources:
        mid = material_id(sf)
        mat = nodes_by_id.get(mid)
        if not mat:
            raise ValueError(f"missing Material for {sf}")
        kind = (kinds.get(sf) or {}).get("artifact_kind") or "other"
        mat["artifact_kind"] = kind
        mat["role"] = kind
        mat["unit_id"] = unit_id
        conn = connects.get(sf) or {}
        covers = [
            id_by_n[n]
            for n in (conn.get("covers_lesson_numbers") or [])
            if n in id_by_n
        ]
        home = covers[0] if covers else (f"lesson:{unit_id}:l{spine[0]['n']}" if spine else None)

        if conn.get("is_assessment_bearing") or kind == "assessment":
            aid = f"assessment:{Path(sf).stem}:item"
            if aid not in nodes_by_id:
                anode = {
                    "id": aid,
                    "type": "Assessment",
                    "name": conn.get("assessment_name") or Path(sf).stem,
                    "source_file": sf,
                    "artifact_kind": "assessment",
                    "unit_id": unit_id,
                }
                graph["nodes"].append(anode)
                nodes_by_id[aid] = anode
            for lid in covers or ([home] if home else []):
                graph["edges"].append({"rel": "hasPart", "from": lid, "to": aid})
            graph["edges"].append({"rel": "uses", "from": aid, "to": mid})
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
        else:
            edge = "describes" if kind == "lesson_plan" else "spanIn"
            for lid in covers or ([home] if home else []):
                graph["edges"].append({"rel": edge, "from": lid, "to": mid})
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})

    return graph


def merge_course_graphs(unit_graphs: list[dict], *, project_id: str) -> dict:
    """Merge per-unit HAS-PART graphs into one Course with multiple units."""
    course_id = f"course:{project_id}"
    nodes: list[dict] = [{"id": course_id, "type": "Course", "name": project_id}]
    edges: list[dict] = []
    seen = {course_id}

    for g in unit_graphs:
        unit_id = g["unit_id"]
        unit_node = f"unit:{unit_id}"
        edges.append({"rel": "hasPart", "from": course_id, "to": unit_node})
        for n in g.get("nodes") or []:
            nid = n["id"]
            if nid.startswith("course:"):
                continue
            if nid in seen:
                continue
            seen.add(nid)
            nodes.append(n)
        for e in g.get("edges") or []:
            # drop per-unit course→unit; we re-emit course→unit above
            if e.get("from", "").startswith("course:"):
                continue
            edges.append(e)

    return {
        "project_id": project_id,
        "stage": "rebuilt-cte-spike",
        "method": "spike-graph-cte-v0-multi",
        "model": "cte-artifact-kind",
        "unit_ids": [g["unit_id"] for g in unit_graphs],
        "nodes": nodes,
        "edges": edges,
    }


def resolve_unit(
    node_id: str,
    nodes: dict[str, dict],
    doc_unit: dict[str, str],
) -> str | None:
    """Map any graph node id back to its owning unit_id."""
    if node_id.startswith("course:"):
        return None
    if node_id.startswith("unit:"):
        return node_id.split(":", 1)[1]
    if node_id.startswith("lesson:"):
        parts = node_id.split(":")
        if len(parts) >= 3:
            return parts[1]
    node = nodes.get(node_id) or {}
    if node.get("unit_id"):
        return str(node["unit_id"])
    sf = node.get("source_file")
    if sf in doc_unit:
        return doc_unit[sf]
    # material:{stem} / assessment:{stem}:item
    if node_id.startswith("material:"):
        stem = node_id.split(":", 1)[1]
        for path, uid in doc_unit.items():
            if Path(path).stem == stem:
                return uid
    if node_id.startswith("assessment:"):
        # assessment:{stem}:item
        mid = node_id[len("assessment:") :]
        stem = mid[:-5] if mid.endswith(":item") else mid
        for path, uid in doc_unit.items():
            if Path(path).stem == stem:
                return uid
    return None


def anti_mangle_checks(
    course: dict,
    *,
    unit_results: list[dict],
    doc_unit: dict[str, str],
) -> dict[str, bool]:
    """Contract that two units did not bleed into each other."""
    nodes = {n["id"]: n for n in course.get("nodes") or []}
    edges = course.get("edges") or []
    unit_ids = [u["unit_id"] for u in unit_results]
    checks: dict[str, bool] = {
        "two_units_present": len(unit_ids) >= 2
        and all(f"unit:{u}" in nodes for u in unit_ids),
    }

    for u in unit_results:
        uid = u["unit_id"]
        lp = next(
            (sf for sf in u["sources"] if sf.endswith("__view-lesson-plan.html")),
            None,
        )
        kind = (u["kinds"].get(lp) or {}).get("artifact_kind") if lp else None
        checks[f"{uid}__lesson_nodes_ge_1"] = len(u["spine"]) >= 1
        checks[f"{uid}__view_lesson_plan_is_lesson_plan"] = kind == "lesson_plan"
        checks[f"{uid}__view_lesson_plan_path_A"] = PATH_BY_KIND.get(kind or "") == "A"

    mats = [n for n in nodes.values() if n.get("type") == "Material"]
    checks["no_teacher_edition_role"] = all(
        n.get("role")
        not in {
            "teacher_edition",
            "learn_student",
            "practice_student",
            "succeed_student",
        }
        for n in mats
    )

    lessons = [n for n in nodes.values() if n.get("type") == "Lesson"]
    checks["lesson_ids_namespaced"] = len(lessons) >= 2 and all(
        bool(n.get("unit_id")) and n["id"].startswith(f"lesson:{n['unit_id']}:")
        for n in lessons
    )

    cross = []
    foreign_attach = []
    for e in edges:
        frm, to = e.get("from") or "", e.get("to") or ""
        uf = resolve_unit(frm, nodes, doc_unit)
        ut = resolve_unit(to, nodes, doc_unit)
        if uf and ut and uf != ut:
            cross.append(e)
        if (
            e.get("rel") in {"describes", "spanIn", "hasPart", "uses"}
            and frm.startswith("lesson:")
            and uf
            and ut
            and uf != ut
        ):
            foreign_attach.append(e)

    checks["no_cross_unit_edges"] = len(cross) == 0
    checks["no_foreign_lesson_attachments"] = len(foreign_attach) == 0
    return checks


def write_spike_result(
    out_dir: Path,
    *,
    course: dict,
    unit_results: list[dict],
    checks: dict[str, bool],
) -> Path:
    passed = all(checks.values())
    lessons = [n for n in course.get("nodes") or [] if n.get("type") == "Lesson"]
    mats = [n for n in course.get("nodes") or [] if n.get("type") == "Material"]
    assessments = [n for n in course.get("nodes") or [] if n.get("type") == "Assessment"]

    lines = [
        "# CTE graph sort spike — RESULT (two units)",
        "",
        f"**Overall:** {'PASS' if passed else 'FAIL'}",
        f"**Units:** {', '.join(f'`{u['unit_id']}`' for u in unit_results)}",
        "",
        "## Anti-mangle / contract checks",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ]
    for k, ok in checks.items():
        lines.append(f"| `{k}` | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Course counts",
        "",
        f"- Units: {len(unit_results)}",
        f"- Lesson nodes: {len(lessons)}",
        f"- Materials: {len(mats)}",
        f"- Assessments: {len(assessments)}",
        f"- Edges: {len(course.get('edges') or [])}",
        "",
    ]

    for u in unit_results:
        uid = u["unit_id"]
        lines += [
            f"## Unit `{uid}`",
            "",
            f"**Title:** {u['title']}",
            f"**Spine:** {len(u['spine'])} — {', '.join(s['label'] for s in u['spine'])}",
            "",
            "| source_file | artifact_kind | Path |",
            "|-------------|---------------|------|",
        ]
        for sf in u["sources"]:
            kind = (u["kinds"].get(sf) or {}).get("artifact_kind") or "?"
            lines.append(f"| `{sf}` | `{kind}` | **{PATH_BY_KIND.get(kind, '?')}** |")
        lines += ["", "### Lesson nodes", ""]
        for n in lessons:
            if n.get("unit_id") == uid or n["id"].startswith(f"lesson:{uid}:"):
                lines.append(f"- `{n.get('id')}` — {n.get('name')}")
        lines.append("")

    path = out_dir / "SPIKE-RESULT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_unit(
    cfg: dict,
    *,
    unit: dict,
    evidence_all: dict[str, list[dict]],
    out_dir: Path,
) -> dict:
    """Type → spine → connect → rebuild for one unit (isolated inventory/spine)."""
    unit_id = unit["unit_id"]
    sources = [sf for sf in unit["documents"] if sf in evidence_all]
    missing = [sf for sf in unit["documents"] if sf not in evidence_all]
    if missing:
        raise SystemExit(f"unit {unit_id}: missing ledger rows for {missing}")

    raw_dir = out_dir / ".raw" / unit_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    unit_out = out_dir / "units" / unit_id
    unit_out.mkdir(parents=True, exist_ok=True)

    log(f"=== UNIT {unit_id}: {len(sources)} docs ===")
    kinds: dict[str, dict] = {}
    for sf in sources:
        log(f"[{unit_id}] Pass 1 type: {sf} ({len(evidence_all[sf])} elements)")
        kinds[sf] = pass1_type(cfg, sf, evidence_all[sf], raw_dir)

    typed_inventory = [
        {"source_file": sf, "artifact_kind": kinds[sf].get("artifact_kind")}
        for sf in sources
    ]
    (unit_out / "kinds.json").write_text(
        json.dumps(kinds, indent=2) + "\n", encoding="utf-8"
    )

    log(f"[{unit_id}] Building lesson spine…")
    spine = build_spine_from_lesson_plans(
        cfg, kinds, {sf: evidence_all[sf] for sf in sources}, raw_dir, unit_id=unit_id
    )
    (unit_out / "spine.json").write_text(
        json.dumps(spine, indent=2) + "\n", encoding="utf-8"
    )
    log(f"[{unit_id}] spine: {spine}")

    connects: dict[str, dict] = {}
    for sf in sources:
        kind = kinds[sf].get("artifact_kind") or "other"
        log(f"[{unit_id}] Pass 2 connect: {sf} kind={kind}")
        connects[sf] = pass2_connect(
            cfg,
            sf,
            evidence_all[sf],
            kind,
            spine,
            typed_inventory,
            raw_dir,
            unit_id=unit_id,
        )
    (unit_out / "connects.json").write_text(
        json.dumps(connects, indent=2) + "\n", encoding="utf-8"
    )

    provisional = build_provisional(
        LAB_ID, unit_id, sources, method="spike-cte-provisional"
    )
    (unit_out / "HAS-PART.provisional.json").write_text(
        json.dumps(provisional, indent=2) + "\n", encoding="utf-8"
    )
    gate = gate_a(provisional, sources)
    if not gate.ok:
        raise SystemExit(f"[{unit_id}] {gate.message}")

    graph = rebuild_cte(
        provisional,
        unit_id=unit_id,
        spine=spine,
        kinds=kinds,
        connects=connects,
        sources=sources,
    )
    graph["unit_id"] = unit_id
    (unit_out / "HAS-PART.json").write_text(
        json.dumps(graph, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "unit_id": unit_id,
        "title": unit["title"],
        "sources": sources,
        "kinds": kinds,
        "spine": spine,
        "connects": connects,
        "graph": graph,
    }


def load_unit_results_from_run(out_dir: Path) -> list[dict]:
    """Rebuild unit_results from a finished spike dir (for --score-only)."""
    units_dir = out_dir / "units"
    if not units_dir.is_dir():
        raise SystemExit(f"no units/ under {out_dir}")
    results = []
    for udir in sorted(units_dir.iterdir()):
        if not udir.is_dir():
            continue
        kinds = json.loads((udir / "kinds.json").read_text(encoding="utf-8"))
        spine = json.loads((udir / "spine.json").read_text(encoding="utf-8"))
        results.append(
            {
                "unit_id": udir.name,
                "title": udir.name,
                "sources": sorted(kinds.keys()),
                "kinds": kinds,
                "spine": spine,
            }
        )
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="SPIKE CTE graph sort (multi-unit)")
    ap.add_argument("--lab", default=LAB_ID)
    ap.add_argument(
        "--score-only",
        action="store_true",
        help="Score EXPECTED-PATHS.json against graph/LATEST (no model calls)",
    )
    ap.add_argument(
        "--run",
        default="",
        help="Spike run dir name under graph/ (default: LATEST)",
    )
    args = ap.parse_args()
    if args.lab != LAB_ID:
        log(f"WARN this spike is wired for {LAB_ID}; got {args.lab}")

    root = lab_dir()

    if args.score_only:
        run_name = args.run or (root / "graph" / "LATEST").read_text(encoding="utf-8").strip()
        out_dir = root / "graph" / run_name
        unit_results = load_unit_results_from_run(out_dir)
        score = score_paths(unit_results)
        path = write_path_score(out_dir, score)
        log(f"path score {score['overall']}: {score['n_pass']}/{score['n_gold']} → {path}")
        for r in score["rows"]:
            if r["status"] != "PASS":
                log(
                    f"  {r['status']} {r['source_file']}: "
                    f"expected {r.get('expected_kind')}→{r.get('expected_path')} "
                    f"got {r.get('got_kind')}→{r.get('got_path')}"
                )
        return 0 if score["overall"] == "PASS" else 1

    ledger = root / "layer0" / "ledger.json"
    if not ledger.is_file():
        log(f"ERROR missing {ledger}")
        return 2

    units = load_manifest_units(root)
    if len(units) < 2:
        log("ERROR multi-unit spike requires ≥2 units in manifest.yaml")
        return 2

    cfg = load_config()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = root / "graph" / f"spike-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence_all = load_evidence_by_source(ledger)
    log(
        f"spike-cte multi: {len(units)} units, "
        f"{len(evidence_all)} docs, "
        f"{sum(len(v) for v in evidence_all.values())} elements → {out_dir}"
    )

    unit_results: list[dict] = []
    for unit in units:
        unit_results.append(
            run_unit(cfg, unit=unit, evidence_all=evidence_all, out_dir=out_dir)
        )

    course = merge_course_graphs([u["graph"] for u in unit_results], project_id=LAB_ID)
    (out_dir / "HAS-PART.json").write_text(
        json.dumps(course, indent=2) + "\n", encoding="utf-8"
    )

    doc_unit = {
        sf: u["unit_id"] for u in unit_results for sf in u["sources"]
    }
    checks = anti_mangle_checks(course, unit_results=unit_results, doc_unit=doc_unit)
    (out_dir / "anti-mangle.json").write_text(
        json.dumps(checks, indent=2) + "\n", encoding="utf-8"
    )

    score = score_paths(unit_results)
    path_score = write_path_score(out_dir, score)
    log(f"path score {score['overall']}: {score['n_pass']}/{score['n_gold']} → {path_score}")

    result = write_spike_result(
        out_dir, course=course, unit_results=unit_results, checks=checks
    )
    # Append path-score summary into SPIKE-RESULT
    with result.open("a", encoding="utf-8") as fh:
        fh.write("\n## Path score (gold)\n\n")
        fh.write(
            f"**{score['overall']}** — {score['n_pass']}/{score['n_gold']} "
            f"(see `PATH-SCORE.md`)\n"
        )
        fails = [r for r in score["rows"] if r["status"] != "PASS"]
        if fails:
            fh.write("\n")
            for r in fails:
                fh.write(
                    f"- FAIL `{r['source_file']}`: "
                    f"expected `{r.get('expected_kind')}→{r.get('expected_path')}`, "
                    f"got `{r.get('got_kind')}→{r.get('got_path')}`\n"
                )

    log(f"wrote {result}")
    overall_ok = all(checks.values()) and score["overall"] == "PASS"
    overall = "PASS" if overall_ok else "FAIL"
    log(f"DONE spike multi → {out_dir} overall={overall}")
    (root / "graph" / "LATEST").write_text(out_dir.name + "\n", encoding="utf-8")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
