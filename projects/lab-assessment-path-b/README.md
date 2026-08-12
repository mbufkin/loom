# lab-assessment-path-b — Path B smoke (quiz ↔ answer key)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local copies; gitignored)

| Tier | Files |
|------|--------|
| strong | Engineering Quizizz + Answer key |
| strong | Architecture Quizizz + Answer key |
| mixed | Manufacturing Quizizz (no key sibling) |
| weak | Blank quiz placeholder |

## Smoke

```bash
python3 ingest.py --project lab-assessment-path-b --skip-models
python3 layer0.py --project lab-assessment-path-b --only Quiz  # or full if model up
python3 route.py --project lab-assessment-path-b
python3 workflows/run_paths.py --project lab-assessment-path-b --no-model
# review path_b/findings.json
```

Path B falls back to source text when the ledger is empty, so route → run_paths still smokes without Layer 0.
