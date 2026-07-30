# Intake goldens

Synthetic packs that prove Loom’s early pipeline does **not** silently drop
curriculum source files. Decisions live on
[Map: Document intake golden suite](https://github.com/mbufkin/loom/issues/6).

## Layout

```text
packs/<pack-id>/
  pack.yaml          # id, shape, formats, stages, mock_plan_ref
  seeds/             # committed .md/.txt/.html (and nested paths for mixed-tree)
  expected/          # stage sidecars (candidates + extract/…)
  mock_plan.yaml     # mocked ingest organize plan (when stages include ingest+)
generate.py          # builds docx/pptx/xlsx/pdf into a temp sources/ tree
```

Pytest materializes `sources/` in a temp dir (seeds + generators). Office
binaries are not committed.

## v1 packs

| Pack | Shape |
|------|--------|
| `pack-long-singular` | One long document |
| `pack-many-little` | Many short files |
| `pack-mixed-tree` | Nested folders under sources/ |

## Harness (v1)

- Default CI: real extract/scrub; mocked ingest organize (`validate_coverage` +
  mock plan); synthetic L0 / route / L1 ledgers asserted via `expected/*.json`
- Optional `@slow` live smoke — not default CI
- `data/cs-loops-unit/` is an authoring template / optional smoke only — not a pack here

### Expected sidecars

| File | Stage |
|------|--------|
| `candidates.json` | Inventory of curriculum candidates |
| `extract.json` | S1 extract status |
| `ingest-coverage.json` | S2 assigned / labeled_not_in_manifest |
| `l0-docs.json` | S3 doc terminal status |
| `route.json` | S5 routed / not_in_ledger |
| `l1-placement.json` | S6 placed / not_in_scope |
