# lab-student-practice-path-e — Path E smoke (student practice)

Harness: `.plan/stub-path-presence-depth/tickets/01-shared-path-lab-harness.md`

## Seeds (local text copies; gitignored)

| Tier | File | Source |
|------|------|--------|
| strong | `doc_estrong_…_Learn_…_Student_Edition.txt` | evidence JSON flatten of G5 M1 Learn SE |
| mixed | `doc_emixed_…_Succeed_…_Student_Edition.txt` | evidence JSON flatten of G5 M1 Succeed SE |
| weak | `doc_eweak_…_Practice_…_Student_Edition.txt` | evidence JSON flatten of G5 M1 Practice SE (thin) |

## Smoke

```bash
python3 ingest.py --project lab-student-practice-path-e --skip-models
python3 route.py --project lab-student-practice-path-e
python3 workflows/run_paths.py --project lab-student-practice-path-e --no-model
# review path_e/findings.json
```

Path E falls back to source text when the ledger is empty, so route → run_paths
still smokes without Layer 0.
