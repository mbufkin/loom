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

`<model>` is the run id (`--graph-run` or a slug of the configured analyst model).
`run_project` auto-sets `LOOM_E2E_RUN` and prepares the tree via
`tools/e2e_run_lib.py`.

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
