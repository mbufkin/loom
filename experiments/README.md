# Experiments

Code here is **not wired** into `run_project.py`. Used for stress tests and research.

| Folder | Project | Scripts |
|--------|---------|---------|
| `openscied/` | `projects/openscied-6` | `decompose.py`, `classify.py`, `organize.py` |
| `apcsp/` | `projects/ap-csp-2026` | `apcsp_check.py`, `apcsp_detail.py` |
| `lesson_preserve/` | `projects/dallas-career-2026` | `run_spike.py`, `test_spike.py` — find/count/preserve LPs, Path A last |

Run from repo root, e.g.:

```bash
python3 experiments/openscied/decompose.py --project openscied-6 --unit 6.2-thermal-energy
python3 experiments/lesson_preserve/run_spike.py --project dallas-career-2026
python3 experiments/lesson_preserve/test_spike.py
```

Requires extracted sources under `projects/<id>/sources/` (and Layer 0 if you need element ledgers).
