import json
from pathlib import Path

out = Path("projects/ap-csp-2026/output")

print(f"{'Unit':30s} {'Cal_Corr':10s} {'Missing':10s} {'Unplaced':10s} {'Placed':10s}")
print("-" * 70)

for unit_dir in sorted(out.glob("*/")):
    unit = unit_dir.name
    gap_file = unit_dir / "02-gap-report.json"
    if not gap_file.exists():
        print(f"{unit:30s} NO FILE")
        continue
    with open(gap_file) as f:
        d = json.load(f)
    cal_corr = len(
        d.get("calendar_corrections", d.get("tier_a_calendar_corrections", []))
    )
    missing = len(d.get("missing_slots", []))
    unplaced = len(d.get("unplaced_documents", []))
    placed = d.get("placement_count", 0)
    print(
        f"{unit:30s} {str(cal_corr):10s} {str(missing):10s} {str(unplaced):10s} {str(placed):10s}"
    )
