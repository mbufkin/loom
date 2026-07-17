import json

with open("projects/dallas-career-2026/output/career-cluster/02-gap-report.json") as f:
    d = json.load(f)

print("Top-level keys:", list(d.keys()))
print()

if "tier_a_calendar_corrections" in d:
    print("=== TIER A ===")
    for corr in d["tier_a_calendar_corrections"]:
        print(json.dumps(corr, indent=2)[:600])
        print()
elif "calendar_corrections" in d:
    print("=== calendar_corrections ===")
    print(json.dumps(d["calendar_corrections"], indent=2)[:600])

# Check placements
if "placements" in d:
    print("=== PLACEMENTS ===")
    print(f"Placement count: {len(d['placements'])}")
    for p in d["placements"][:5]:
        print(
            f"  {p.get('doc_id','?'):30s} day={p.get('day','?')} slot={p.get('slot','?')}"
        )
elif "placed" in d:
    print("=== PLACED ===")
    print(json.dumps(d["placed"], indent=2)[:600])
else:
    # print all keys with short values
    for k, v in d.items():
        if isinstance(v, (str, int, float, bool)):
            print(f"  {k}: {v}")
        elif isinstance(v, list):
            print(f"  {k}: [{len(v)} items]")
        elif isinstance(v, dict):
            print(f"  {k}: [{len(v)} keys]")

# Check for model output
print()
print("=== Looking for model traces ===")
s = json.dumps(d)
for keyword in [
    "model",
    "analyst",
    "verifier",
    "calendar_corrections",
    "rationale",
    "tier",
]:
    if keyword in s.lower():
        print(f"  '{keyword}' found in report")
