import json
from pathlib import Path

# Read first unit's gap report
with open("projects/ap-csp-2026/output/creative-development/02-gap-report.json") as f:
    d = json.load(f)

print("=== FULL REPORT (creative-development) ===")
print(json.dumps(d, indent=2))
