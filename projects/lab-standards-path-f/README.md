# lab-standards-path-f — Path F smoke (standards & pacing)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local text copies; gitignored)

| Tier | File | Source |
|------|------|--------|
| strong | `doc_fstrong_Algebra_I_Math_150-day_Topic_Pacing_Guides.txt` | evidence JSON flatten of Alg1 pacing guide |
| mixed | `doc_fmixed_Algebra_I_Math_YAG_150-day.txt` | evidence JSON flatten of Alg1 YAG 150-day |
| weak | `doc_fweak_Activity_Sequence_Pacing_Stub.txt` | pathful sequence flowchart (renamed so router hits F) |

## Smoke

```bash
python3 ingest.py --project lab-standards-path-f --skip-models
python3 route.py --project lab-standards-path-f
python3 workflows/run_paths.py --project lab-standards-path-f --no-model
# review path_f/findings.json
```

Path F falls back to source text when the ledger is empty, so route → run_paths
still smokes without Layer 0.
