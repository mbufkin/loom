"""Shared HAS-PART assembly for the graph spike (Bet 3 code path).

Educational note
----------------
Narrow model steps answer *per document* (role / lessons / assessment). They
must never emit the full organization graph. This module owns:

  1. Loading a **unit slice** from a Loom-style ``manifest.yaml``
     (``units.<id>.documents``) — the same registry production ingest writes.
  2. Merging per-doc lesson lists into a **unit spine** via an explicit policy
     (highest/union wins; sparse Practice must not shrink the module).
  3. ``rebuild_multi`` — turn review-findings into Course → Unit → Lesson →
     Material/Assessment edges.

Curriculum-specific heuristics live in ``SpinePolicy`` knobs, not in hardcoded
PDF name lists. Callers pass ``sources`` from the manifest unit.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml

from graph_inventory import _doc_id, material_id

SpineMode = Literal["contiguous_from_1", "union_only", "explicit_list_only"]

# Roles that may soft-default to the whole unit spine when the model returns [].
FULL_MODULE_ROLES = frozenset({"teacher_edition", "learn_student", "succeed_student"})


@dataclass(frozen=True)
class SpinePolicy:
    """How per-doc lesson numbers become the unit's Lesson node set.

    Best practice: pick a policy per curriculum *family*, not per file.

    - contiguous_from_1: union all numbers; if min==1 and max>=min_module_size,
      expand to 1..max (K–5 module books that cite \"Lesson 1 to 15\").
    - union_only: keep the raw union (holes allowed).
    - explicit_list_only: same as union_only today; reserved for stricter
      future checks that refuse fill without a range citation.
    """

    mode: SpineMode = "contiguous_from_1"
    min_module_size: int = 10


@dataclass(frozen=True)
class UnitSlice:
    """One unit's identity + ordered document list from a manifest."""

    project_id: str
    unit_id: str
    title: str
    documents: list[str]
    manifest_path: Path
    spine_policy: SpinePolicy = SpinePolicy()


def load_unit_slice(
    manifest_path: Path,
    *,
    unit_id: str | None = None,
    spine_policy: SpinePolicy | None = None,
) -> UnitSlice:
    """Load ``units.<unit_id>.documents`` (or legacy ``source_files``).

    If ``unit_id`` is omitted, the first unit key in the manifest is used —
    fine for single-unit spike fixtures; multi-unit projects must pass it.
    """
    path = Path(manifest_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    project = raw.get("project") or {}
    project_id = str(project.get("id") or path.parent.name)
    units = raw.get("units") or {}
    if not isinstance(units, dict) or not units:
        raise ValueError(f"{path}: manifest has no units: map")

    if unit_id is None:
        unit_id = next(iter(units))
    if unit_id not in units:
        raise KeyError(f"{path}: unit_id={unit_id!r} not in {sorted(units)}")

    entry = units[unit_id] or {}
    docs = entry.get("documents") or entry.get("source_files") or []
    documents = [str(Path(d).name) for d in docs]
    if not documents:
        raise ValueError(f"{path}: unit {unit_id!r} has empty documents")

    # Optional per-unit override: units.<id>.spine_policy: {mode, min_module_size}
    policy = spine_policy or SpinePolicy()
    override = entry.get("spine_policy") or raw.get("spine_policy")
    if override and spine_policy is None:
        policy = SpinePolicy(
            mode=str(override.get("mode") or policy.mode),  # type: ignore[arg-type]
            min_module_size=int(override.get("min_module_size") or policy.min_module_size),
        )

    return UnitSlice(
        project_id=project_id,
        unit_id=str(unit_id),
        title=str(entry.get("title") or unit_id),
        documents=documents,
        manifest_path=path,
        spine_policy=policy,
    )


def resolve_unit_spine(
    lesson_nums: Iterable[int],
    policy: SpinePolicy = SpinePolicy(),
) -> set[int]:
    """Turn a bag of lesson numbers into the unit's Lesson-id set.

    Locked rule (2026-08-02): never let one document's shorter list overwrite
    the union. Highest number across the unit wins when the set is module-shaped.
    """
    nums = {int(n) for n in lesson_nums if isinstance(n, int) or str(n).isdigit()}
    nums = {n for n in nums if 1 <= n <= 40}
    if not nums:
        return set()

    if policy.mode == "contiguous_from_1":
        max_n = max(nums)
        min_n = min(nums)
        if max_n >= policy.min_module_size and min_n == 1:
            return set(range(1, max_n + 1))
        return nums

    # union_only / explicit_list_only
    return nums


def merge_narrow_step_findings(
    project_id: str,
    unit_id: str,
    sources: list[str],
    roles: dict[str, dict],
    lessons: dict[str, dict],
    assesses: dict[str, dict],
    *,
    spine_policy: SpinePolicy = SpinePolicy(),
    model_label: str = "narrow-steps",
) -> dict[str, Any]:
    """Code merge of Bet-3 per-doc steps → review-findings for rebuild_multi.

    ``sources`` must be the manifest unit's document list (basename form).
    """
    bag: set[int] = set()
    for sf in sources:
        bag.update((lessons.get(sf) or {}).get("covers_lesson_numbers") or [])
        bag.update((assesses.get(sf) or {}).get("assessment_lesson_numbers") or [])
    all_lesson_nums = resolve_unit_spine(bag, spine_policy)

    lesson_ids = [f"lesson:{unit_id}:l{n}" for n in sorted(all_lesson_nums)]
    id_by_n = {n: f"lesson:{unit_id}:l{n}" for n in sorted(all_lesson_nums)}

    findings: list[dict[str, Any]] = []
    for sf in sources:
        role = (roles.get(sf) or {}).get("role") or "other"
        cover_ns = list((lessons.get(sf) or {}).get("covers_lesson_numbers") or [])
        if not cover_ns and all_lesson_nums and role in FULL_MODULE_ROLES:
            # Soft default: TE/Learn/Succeed without a list still hang on the
            # unit spine — Practice stays sparse and does not invent coverage.
            cover_ns = sorted(all_lesson_nums)
        covers = [id_by_n[n] for n in cover_ns if n in id_by_n]
        home = covers[0] if covers else (lesson_ids[0] if lesson_ids else f"lesson:{unit_id}:l1")

        assess = assesses.get(sf) or {}
        if assess.get("is_assessment_bearing"):
            a_ns = assess.get("assessment_lesson_numbers") or cover_ns
            a_covers = [id_by_n[n] for n in a_ns if n in id_by_n] or covers
            findings.append(
                {
                    "source_file": sf,
                    "action": "attach_assessment",
                    "lesson_id": a_covers[0] if a_covers else home,
                    "role": role,
                    "node_type": "Assessment",
                    "assessment_name": assess.get("assessment_name") or "Practice",
                    "covers_lessons": a_covers,
                    "note": assess.get("notes") or "",
                    "model_steps": {
                        "role": roles.get(sf),
                        "lessons": lessons.get(sf),
                        "assessment": assess,
                    },
                }
            )
        else:
            edge = "describes" if role == "teacher_edition" else "spanIn"
            findings.append(
                {
                    "source_file": sf,
                    "action": "attach_material",
                    "lesson_id": home,
                    "role": role,
                    "node_type": "Material",
                    "edge": edge,
                    "covers_lessons": covers,
                    "note": (lessons.get(sf) or {}).get("notes") or "",
                    "model_steps": {
                        "role": roles.get(sf),
                        "lessons": lessons.get(sf),
                        "assessment": assess,
                    },
                }
            )

    return {
        "project_id": project_id,
        "unit_id": unit_id,
        "create_lessons": [
            {"id": f"lesson:{unit_id}:l{n}", "type": "Lesson", "name": f"Lesson {n}"}
            for n in sorted(all_lesson_nums)
        ],
        "findings": findings,
        "model": model_label,
        "spine_policy": {
            "mode": spine_policy.mode,
            "min_module_size": spine_policy.min_module_size,
        },
        "note": "Narrow steps + code rebuild_multi (Bet 3); spine from unit union.",
    }


def rebuild_multi(provisional: dict, findings: dict) -> dict:
    """Batch rebuild with multiple Lesson nodes (spike rebuild is single-lesson)."""
    graph = deepcopy(provisional)
    graph["stage"] = "rebuilt"
    # Prefer explicit model label from findings; keep a stable assembler method tag.
    if findings.get("model"):
        graph["model"] = findings["model"]
    graph["method"] = "graph-assemble-v0+multi-lesson"
    unit_id = findings["unit_id"]
    unit_node = f"unit:{unit_id}"
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}

    for lesson in findings.get("create_lessons") or []:
        lid = lesson["id"]
        if lid not in nodes_by_id:
            graph["nodes"].append(dict(lesson))
            nodes_by_id[lid] = lesson
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": lid})

    # Drop unit→Material inventory hang; re-hang via lesson edges + inventory keep.
    graph["edges"] = [
        e
        for e in graph["edges"]
        if not (
            e.get("rel") == "hasPart"
            and e.get("from") == unit_node
            and str(e.get("to", "")).startswith("material:")
        )
    ]

    for f in findings.get("findings") or []:
        src = f["source_file"]
        mid = material_id(src)
        mat = nodes_by_id.get(mid)
        if not mat:
            raise ValueError(f"rebuild refuses to invent Material for {src}")
        mat["role"] = f.get("role") or mat.get("role")
        home = f.get("lesson_id")
        covers = f.get("covers_lessons") or ([home] if home else [])

        if f.get("action") == "attach_assessment":
            aid = f"assessment:{_doc_id(src)}:practice"
            if aid not in nodes_by_id:
                anode = {
                    "id": aid,
                    "type": "Assessment",
                    "name": f.get("assessment_name") or "Practice",
                    "source_file": src,
                    "material_id": mid,
                }
                graph["nodes"].append(anode)
                nodes_by_id[aid] = anode
            for lid in covers:
                graph["edges"].append({"rel": "hasPart", "from": lid, "to": aid})
            graph["edges"].append({"rel": "uses", "from": aid, "to": mid})
            graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
        else:
            edge_rel = f.get("edge") or "spanIn"
            if edge_rel == "describes":
                for lid in covers:
                    graph["edges"].append({"rel": "describes", "from": mid, "to": lid})
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})
            else:
                for lid in covers:
                    graph["edges"].append({"rel": "spanIn", "from": lid, "to": mid})
                graph["edges"].append({"rel": "hasPart", "from": unit_node, "to": mid})

    seen: set[tuple] = set()
    uniq = []
    for e in graph["edges"]:
        key = (e.get("rel"), e.get("from"), e.get("to"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    graph["edges"] = uniq
    return graph
