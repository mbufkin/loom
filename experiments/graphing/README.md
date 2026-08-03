# Graphing experiments (P1 × D)

Code-first Day-header proposal + optional local model repair, scored against
hand-built gold in `projects/lab-*/graph/HAS-PART.json`.

**Loom merge handoff (opt-in graph phase):** [docs/GRAPH-PHASE.md](../../docs/GRAPH-PHASE.md).

## Spike: provisional → review → rebuild (`ledger-mini`)

Handoff: [SPIKE.md](SPIKE.md). Runner (no LLM):

```bash
python3 experiments/graphing/spike_loop.py
python3 experiments/graphing/test_spike_loop.py -v
```

Writes `projects/_fixtures/ledger-mini/graph/` (HAS-PART provisional + rebuilt,
review findings, per-source flat `.raw/*.json` with before/after choices).

```bash
# propose only (no model)
LOOM_CONFIG=config.yaml .venv/bin/python experiments/graphing/run_pd.py \
  --project lab-dallas-ag --gold projects/lab-dallas-ag/graph/HAS-PART.json \
  --project lab-arts-av --gold projects/lab-arts-av/graph/HAS-PART.json \
  --skip-model

# full P1×D with local repair
LOOM_CONFIG=config.yaml .venv/bin/python experiments/graphing/run_pd.py \
  --project lab-dallas-ag --gold projects/lab-dallas-ag/graph/HAS-PART.json \
  --project lab-arts-av --gold projects/lab-arts-av/graph/HAS-PART.json
```

Provisional pass: material_coverage=1.0, lesson_mean_iou≥0.5, assessment_attach≥0.67,
lesson count matches gold.
