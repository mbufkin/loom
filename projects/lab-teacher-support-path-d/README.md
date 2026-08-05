# lab-teacher-support-path-d — Path D smoke (teacher support / TE)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local text copies; gitignored)

| Tier | File | Source |
|------|------|--------|
| strong | `doc_dstrong_K-5_Math_Grade_5_Module_1_Place_Value_and_Decimals_Teacher_Edition.txt` | evidence JSON flatten of G5 M1 TE |
| mixed | `doc_dmixed_Algebra_I_Math_Teacher_Edition_Course_and_Implementation_Guide.txt` | evidence JSON flatten of Alg1 Course+Impl |
| weak | `doc_dweak_Module_Placeholder_Teacher_Edition_Stub.txt` | tiny TE-named stub (no facilitation) |

## Smoke

```bash
python3 ingest.py --project lab-teacher-support-path-d --skip-models
python3 route.py --project lab-teacher-support-path-d
python3 workflows/run_paths.py --project lab-teacher-support-path-d --no-model
# review path_d/findings.json
```

Path D falls back to source text when the ledger is empty, so route → run_paths
still smokes without Layer 0.
