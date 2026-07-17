import json
from pathlib import Path

proj = "projects/dallas-career-2026"
units = sorted(Path(proj).glob("output/*/"))

for unit_dir in units:
    unit_name = unit_dir.name
    ev_dir = unit_dir / "evidence"
    if not ev_dir.exists():
        print(f"\n{'='*60}\n{unit_name}: No evidence directory\n{'='*60}")
        continue

    ev_files = sorted(ev_dir.glob("*.json"))
    print(f"\n{'='*60}\n{unit_name}: {len(ev_files)} evidence files\n{'='*60}")

    for f in ev_files:
        with open(f) as fh:
            d = json.load(fh)

        doc_type = d.get("doc_type", "?")
        ma = d.get("model_analysis")
        has_ma = isinstance(ma, dict) and "placement_rationale" in ma
        content_len = len(d.get("content_clean", ""))
        model_call = d.get("model_call_count", d.get("_model_calls", "?"))
        print(
            f"  {f.stem[:40]:40s} type={doc_type[:15]:15s} ma={int(has_ma)} c_len={content_len:5d} calls={model_call}"
        )
