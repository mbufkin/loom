#!/usr/bin/env python3
"""
Score a cascade result JSON against a prior baseline on doc_id → final_lp.

Best practice: treat the baseline as a regression gate (not ground truth).
Print TP/FP/FN relative to baseline final_lp, plus escalation/source tallies.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _index(rows: list[dict]) -> dict[str, dict]:
    return {r["doc_id"]: r for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="Diff cascade final_lp vs baseline")
    ap.add_argument("--pred", required=True, help="new cascade JSON")
    ap.add_argument("--baseline", required=True, help="prior baseline JSON")
    args = ap.parse_args()

    pred = json.loads(Path(args.pred).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    pi, bi = _index(pred), _index(base)

    shared = sorted(set(pi) & set(bi))
    only_pred = sorted(set(pi) - set(bi))
    only_base = sorted(set(bi) - set(pi))

    tp = fp = fn = tn = 0
    mismatches: list[str] = []
    for did in shared:
        p = bool(pi[did].get("final_lp"))
        b = bool(bi[did].get("final_lp"))
        if p and b:
            tp += 1
        elif p and not b:
            fp += 1
            mismatches.append(f"FP  {pi[did]['unit_id']}: {pi[did]['filename']}")
        elif not p and b:
            fn += 1
            mismatches.append(f"FN  {pi[did]['unit_id']}: {pi[did]['filename']}")
        else:
            tn += 1

    src = Counter(r.get("decision_source") for r in pred)
    esc = sum(1 for r in pred if r.get("escalated"))
    final = sum(1 for r in pred if r.get("final_lp"))
    promoted = sum(1 for r in pred if r.get("promoted"))

    print(f"pred={args.pred}")
    print(f"baseline={args.baseline}")
    print(f"docs pred={len(pred)} baseline={len(base)} shared={len(shared)}")
    if only_pred:
        print(f"only_pred={len(only_pred)}")
    if only_base:
        print(f"only_base={len(only_base)}")
    print(f"final_lp={final} promoted={promoted} escalated={esc}")
    print(f"sources={dict(src)}")
    print(f"vs_baseline TP={tp} FP={fp} FN={fn} TN={tn}")
    if mismatches:
        print("mismatches:")
        for line in mismatches:
            print(f"  {line}")
    else:
        print("mismatches: none (exact final_lp match on shared docs)")

    # Gate: zero FN/FP on shared focus set is the expected regression pass.
    if fp or fn:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
