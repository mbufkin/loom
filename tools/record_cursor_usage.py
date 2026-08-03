#!/usr/bin/env python3
"""CLI bridge: Cursor SDK tools append one usage row (same schema as model_chat).

Usage:
  python3 tools/record_cursor_usage.py \\
    --project bluebonnet-full-grok \\
    --step unit:g5-m1 \\
    --model grok-4.5 \\
    --run-id run-… \\
    --elapsed-ms 12345 \\
    --usage-json '{"inputTokens":1,"outputTokens":2,"totalTokens":3}' \\
    [--finalize]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from usage_lib import (  # noqa: E402
    record_cursor_run_usage,
    set_usage_project,
    write_usage_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    # Not required for --finalize-only (summary rewrite with no new row).
    ap.add_argument("--step", default="cursor-agent")
    ap.add_argument("--model", default="unknown")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--elapsed-ms", type=float, default=0.0)
    ap.add_argument("--usage-json", default="")
    ap.add_argument("--ok", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--error", default=None)
    ap.add_argument(
        "--finalize",
        action="store_true",
        help="Rewrite projects/<id>/USAGE-SUMMARY.json (with or without a new row)",
    )
    ap.add_argument(
        "--finalize-only",
        action="store_true",
        help="Only rewrite USAGE-SUMMARY.json; do not append a usage row",
    )
    ap.add_argument(
        "--extra-json",
        default="",
        help="Optional JSON object merged into row.extra",
    )
    args = ap.parse_args()

    set_usage_project(args.project)
    if not args.finalize_only:
        if args.step == "cursor-agent" and args.model == "unknown":
            ap.error("--step and --model are required unless --finalize-only")
        usage = None
        if args.usage_json.strip():
            usage = json.loads(args.usage_json)
        extra = json.loads(args.extra_json) if args.extra_json.strip() else None

        row = record_cursor_run_usage(
            project_id=args.project,
            step=args.step,
            model=args.model,
            run_id=args.run_id,
            usage=usage,
            elapsed_ms=args.elapsed_ms,
            ok=args.ok,
            error=args.error,
            extra=extra,
        )
        print(
            json.dumps(
                {
                    "recorded": bool(row),
                    "source": row.get("source"),
                    "total_tokens": row.get("total_tokens"),
                }
            )
        )
    if args.finalize or args.finalize_only:
        summary = write_usage_summary(args.project)
        print(json.dumps({"summary_totals": summary.get("totals")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
