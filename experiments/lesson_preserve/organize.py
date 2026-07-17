#!/usr/bin/env python3
"""
organize.py — Pre-path organization: inventory docs, collect LP group, defer Path A.

Simulates mid-flight discovery: non-LP docs are ordered first; any LP found while
scanning still lands in the LP group for end-of-unit Path A.
"""

from __future__ import annotations

from typing import Any

from experiments.lesson_preserve.detect import detect_unit_lesson_plans


def organize_unit(
    project_id: str,
    unit_id: str,
    *,
    title: str,
    documents: list[str],
    title_map: dict[str, str],
) -> dict[str, Any]:
    """
    Build organization record for one unit.

    path_order: non-LP docs first (by manifest order), then LP group (Path A last).
    """
    from audit_lib import doc_id_from_filename

    lp_recs = detect_unit_lesson_plans(
        project_id, unit_id, documents, title_map=title_map
    )
    lp_ids = {r["doc_id"] for r in lp_recs}

    inventory: list[dict] = []
    non_lp_order: list[str] = []
    midflight_appends: list[str] = []

    for rel in documents:
        did = doc_id_from_filename(rel)
        is_lp = did in lp_ids
        inventory.append(
            {
                "doc_id": did,
                "source_rel": rel,
                "title": title_map.get(did) or rel,
                "in_lp_group": is_lp,
            }
        )
        if is_lp:
            # Pretend we discovered it while walking other docs — still defer to end
            midflight_appends.append(did)
        else:
            non_lp_order.append(did)

    path_a_mode: str
    if len(lp_recs) == 0:
        path_a_mode = "pending_signal"  # resolved later: synthesize_missing | none
    elif len(lp_recs) == 1:
        path_a_mode = "single_lp"
    else:
        path_a_mode = "lp_block"

    return {
        "unit_id": unit_id,
        "title": title,
        "doc_count": len(documents),
        "lesson_plan_count": len(lp_recs),
        "lesson_plans": lp_recs,
        "inventory": inventory,
        "path_order": {
            "non_lp_first": non_lp_order,
            "lp_group_last": [r["doc_id"] for r in lp_recs],
            "note": (
                "Non-LP document paths run first; LP group runs Path A last. "
                "Mid-flight LP finds append to lp_group_last."
            ),
            "midflight_lp_appends": midflight_appends,
        },
        "path_a_mode": path_a_mode,
    }
