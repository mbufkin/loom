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

- Default CI: real extract/catalog; mocked ingest / Layer 0 / Layer 1
- Optional `@slow` live smoke — not default CI
- `data/cs-loops-unit/` is an authoring template / optional smoke only — not a pack here
