import json
from pathlib import Path

out = Path("projects/dallas-career-2026/output")
state = json.loads((out / "batch_state.json").read_text())

print("Batch state run_id:", state.get("run_id"))
print()
print(f"{'Unit':35s} {'Status':10s} {'Finished':25s}")
print("-" * 70)
for uid, info in state["units"].items():
    print(f"{uid:35s} {info.get('status','?'):10s} {info.get('finished_at','?'):25s}")
