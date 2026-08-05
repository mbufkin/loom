# lab-general-path-c — Path C smoke (general feedback nursery)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local text copies; gitignored)

| Tier | File | Source |
|------|------|--------|
| strong | `doc_cstrong_Secondary_Mathematics_Coach_Lesson_Internalization_Protocol.txt` | evidence JSON flatten of coach protocol |
| mixed | `doc_cmixed_CTSO_Presentation.txt` | Dallas CTSO Presentation |
| weak | `doc_cweak_Other_Handout_Stub.txt` | synthetic other stub (no growth keywords) |

## Smoke

```bash
python3 ingest.py --project lab-general-path-c --skip-models
python3 route.py --project lab-general-path-c
python3 workflows/run_paths.py --project lab-general-path-c --no-model
# review path_c/findings.json (+ _loom_feedback.yaml from route)
```

Path C falls back to source text when the ledger is empty. C3 uses
`route.feedback` and/or `_loom_feedback.yaml`.
