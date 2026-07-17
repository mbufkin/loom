# Sample Project — `dallas-career-2026`

A **structural demo** using career-cluster style unit calendars and a real DISD 2026–2027 school calendar spine.

## What is included in the public repo

| Path | Purpose |
|------|---------|
| `projects/dallas-career-2026/school-calendar.yaml` | District instructional year (from public calendar reference) |
| `projects/dallas-career-2026/reference/README.md` | How the calendar was sourced |
| `projects/dallas-career-2026/units/*/calendar.yaml` | Inferred 18 unit module grids |
| `projects/dallas-career-2026/manifest.yaml` | Unit registry (document list) |
| `projects/dallas-career-2026/pacing-plan.yaml` | Example inferred year-at-a-glance |

## What is **not** included

- Raw curriculum source files (size / redistribution)
- Full `output/` tree (regenerate locally)
- Model raw JSON under `ingest/`

To run a full audit, add your own documents:

```bash
mkdir -p projects/dallas-career-2026/sources
# copy curriculum files here
cp config.example.yaml config.yaml   # single-model URLs OK — see config.example.yaml
./run-audit dallas-career-2026 --ingest --force
# same as: python3 run_project.py --project dallas-career-2026 --ingest --force
```

**What the one command produces (when sources exist):** Layer 0 → 1 → 2 ledgers, then hybrid
`output/FIRST-PASS.md` (+ `GLOBAL-AUDIT.md` alias), teacher packets, dashboard, and
`GLOBAL-AUDIT-REPORT.pdf`. Drive push is on by default (`--skip-drive-push` to keep local).

Smoke one unit: `./run-audit dallas-career-2026 --only engineering --force`.

## Expected results (when documents are present)

- **18 units** placed sequentially on instructional days
- **~39 instructional days** consumed for short modules (most units are 2–3 days)
- **~136 days remaining** on the school calendar — correctly signals modules do not fill a full year
- All units start in **Fall 1** under default manifest order (no manual pacing overrides)

## Interpreting the year grid

The global PDF **Year at a Glance** section shows which units start in each grading period. In this sample, everything clusters early because:

1. Units are short career-cluster modules, not a year-long course spine
2. Rollup uses manifest order with no district pacing overrides

That clustering is a **finding**, not a bug — it shows the gap between provider packs and a full-year scope-and-sequence.
