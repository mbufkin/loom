import json
from pathlib import Path

out = Path("projects/dallas-career-2026/output")

# Check gap reports for all units — which have old format vs new format
print(
    f"{'Unit':35s} {'Old/New':10s} {'Calendar_corr':15s} {'Missing':10s} {'Unplaced':10s} {'Placed':10s}"
)
print("-" * 90)

for unit_dir in sorted(out.glob("*/")):
    unit = unit_dir.name
    gap_file = unit_dir / "02-gap-report.json"
    if not gap_file.exists():
        print(f"{unit:35s} {'NO FILE':10s}")
        continue

    with open(gap_file) as f:
        d = json.load(f)

    # Detect format
    has_cal_corr = "calendar_corrections" in d or "tier_a_calendar_corrections" in d
    has_extra_slots = "extra_slots_used" in d
    missing = len(d.get("missing_slots", d.get("missing", [])))
    unplaced = len(d.get("unplaced_documents", d.get("unplaced", [])))
    placed = d.get("placement_count", len(d.get("placements", d.get("placed", []))))

    fmt = "NEW" if (has_cal_corr or has_extra_slots) else "OLD"
    cal_corr = len(
        d.get("calendar_corrections", d.get("tier_a_calendar_corrections", []))
    )

    print(
        f"{unit:35s} {fmt:10s} {str(cal_corr):15s} {str(missing):10s} {str(unplaced):10s} {str(placed):10s}"
    )
