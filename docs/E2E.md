# E2E — one program, common review folder

**Product contract:** there is one end-to-end program. Every normal run writes
into a **common review tree** keyed by **curriculum** and **model**.

## Program

| Entry | What it is |
|-------|------------|
| `./run-audit <curriculum> […]` | Preferred CLI (thin wrapper) |
| `python3 run_project.py --project <curriculum> […]` | Same program |

Do not add parallel “spike” or experiment runners for production review.

## Output layout (canonical)

```text
projects/<curriculum>/e2e/runs/<model>/
  RUN.json                 # model + backend + timestamps
  layer0/ layer1/ layer2/  # pipeline stages
  path_a/ path_b/ path_c/
  graph/runs/<model>/      # belonging (HAS-PART) when --with-graph
  output/                  # dashboards, teacher packets, quality plates
  USAGE-SUMMARY.json
```

Examples on this box:

- `projects/dallas-career-2026/e2e/runs/grok-4.5/`
- `projects/dallas-career-2026/e2e/runs/nemotron3-nano-30b/`
- `projects/bluebonnet-math-2026/e2e/runs/grok-4.5/`

`<model>` is the run id (`--graph-run` or a slug of the configured analyst model).
`run_project` auto-sets `LOOM_E2E_RUN` and prepares the tree via
`tools/e2e_run_lib.py`.

## Run cost notes (Grok)

E2E trees often stay **local** (ledgers quote curriculum). Cost math is documented
here from `USAGE-SUMMARY.json` + xAI list rates — not as a commit of the corpus.

### Bluebonnet · `grok-4.5` (finished 2026-08-03T18:49Z)

| Meter | Value |
|-------|--------|
| Path | `projects/bluebonnet-math-2026/e2e/runs/grok-4.5/` |
| Calls | 446 ok / 0 error (~4.0 h wall) |
| Metered tokens | 2,711,287 prompt · 2,353,792 cached · 60,975 completion |
| Token coverage | **6** Cursor SDK graph calls only; **440** bridge `:8788` API calls logged `0` tokens |

**xAI Grok 4.5 list rates** (per 1M tokens): under 200k prompt → $2 input / $0.30 cached / $6 output; at or above 200k prompt → $4 / $0.60 / $12 for the whole request.

| Piece | Estimate |
|-------|----------|
| Graph SDK (metered; all six calls ≥200k prompt) | **$3.57** |
| Layer 0 + Layer 1 + synth (unmetered; reconstructed from docs/steps) | ~$9–$22 |
| **Full-run list-price equivalent** | **~$13–$25 (mid ~$16)** |

**Caveats:** this run used the Cursor OpenAI-compatible bridge (`:8788`), so real
spend may be **Cursor plan quota**, not a direct xAI invoice. Treat **$3.57** as
the hard metered floor; **~$16** as the best full-run reconstruction until bridge
API calls record usage.

### Dallas · `grok-4.5` (finished 2026-08-03T12:51Z)

| Meter | Value |
|-------|--------|
| Path | `projects/dallas-career-2026/e2e/runs/grok-4.5/` |
| Calls | 1,022 ok |
| Metered tokens | 799,076 prompt · 680,512 cached · 21,043 completion (2 SDK calls only) |

Same metering gap (most `:8788` API rows untokened). Do not treat
`USAGE-SUMMARY.json` totals alone as full-run spend.

## Review UI

1. Pick **curriculum** (project id)
2. Pick **E2E · \<model\>** (defaults to a run with quality plates when present)
3. Nested graph/quality plates resolve under that same folder

API: `GET /api/projects/{id}/e2e/runs` then scoped `?e2e_run=<model>`.

## Escape hatch (not for review A/B)

`--allow-live-root` (or `LOOM_ALLOW_LIVE_ROOT=1`) writes the golden
`projects/<curriculum>/` tree — overnight / golden refresh only.

## Related

- Pipeline stages: [GRAPH-PHASE.md](GRAPH-PHASE.md), [PIPELINE.md](PIPELINE.md)
- Operator flags: [../OPERATORS.md](../OPERATORS.md)
