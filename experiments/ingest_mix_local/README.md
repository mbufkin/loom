# Local ingest auto-improve (Ag + Arts mix)

Hypothesis: G10 local **Nemotron-3-Nano-30B** can separate a mixed pile if it gets
more text + stricter instructions than stock `ingest.py` (200-char excerpts).

```bash
LOOM_CONFIG=config.yaml .venv/bin/python experiments/ingest_mix_local/run_improve.py
```

## Result (2026-07-31)

**PASS by iter 3** (with mechanical normalize):

| Change vs stock ingest | Effect |
|------------------------|--------|
| Richer catalog (800→… chars / file) + allowlist | Placement recovered |
| Repair loop with validator + gold critique | Fixed drops/dupes by iter 3 |
| Code normalize: `sources/` strip, float→int days, `_`→`-` in `unit_id` | Unblocked schema (model used underscores) |

File split: **2 Ag + 8 Arts**, clean. Artifact: `results/SUCCESS/organize.json`.

Stock local ingest (thin catalog) had previously **misfiled** the Arts lesson plan into Ag. This run shows the bet holds: **time + text + instructions** (plus tiny schema normalize) — not “local can’t sort.”
