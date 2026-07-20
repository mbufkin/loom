# Bluebonnet Grade 5 + Algebra I — validation log

Major Loom validation corpus (TEA Learn Canvas courses `9543` + `9546`).
Full Volume 1/2 binders excluded.

## Pipeline accommodations

| Fix | Where |
|-----|--------|
| Layer 1 ORGANIZE batches (40 els) | `layer1.py` `ORGANIZE_BATCH_SIZE` |
| Layer 0 mid-chunk resume | `.raw/*-resolved-rows.json` |
| 900s decompose timeout | `LARGE_CALL_TIMEOUT_SECONDS` |
| Smaller chunks (30k / threshold 40k) | `layer0.py` — stops mid-JSON truncation on TE/Learn |
| Forced chunk fallback | simple-path parse fail → chunked path |
| Ladder runner + pass checks | `tools/run_bluebonnet_ladder.py` |

## Ladder

| Stage | Corpus | Status | Notes |
|-------|--------|--------|-------|
| D1 | G5 Module 1 pack + core program guides (8 PDFs) | **Pass** (2026-07-17) | Batched ORGANIZE unblocked 195-el Learn SE |
| D2 | Full Grade 5 (30 PDFs) | in progress | Prior overnight run died mid-Mod5; rechunk + resume |
| D3 | Algebra I modules + program | pending | |
| D4 | G5 + Alg I combined | pending | |

## D1 results (2026-07-17)

- Wall-clock: ~2.2 h
- Layer 0: **289** elements / **6** docs (Practice/Succeed timed out at 300s before timeout fix)
- Learn SE ORGANIZE: **5 batches**; TE ORGANIZE: **2 batches**
- Layer 1: MATCH 17 · MISMATCH 7 · UNVERIFIED 265
- Route: Path C × 6
- Report: `output/GLOBAL-AUDIT-REPORT.pdf`

Pass criteria met for D1: batched ORGANIZE unblocked Learn/TE; report not mass-UNVERIFIED from ORGANIZE collapse.
## D2 results (2026-07-20 02:10 UTC)

- Result: **PASS**
- Wall-clock: 33.02 h
- Sources: 30 PDFs
- Ledger docs: 28
- Layer 0 coverage: 28/30 docs (93%); missing=['K-5_Math_Grade_5_Module_5_Learn_Addition_and_Multiplication_with_Volume_and_Area_Student_Edition.pdf', 'K-5_Math_Grade_5_Module_6_Succeed_Problem_Solving_with_the_Coordinate_Plane_and_Data_Student_Edition.pdf']
- report ok (104091 bytes)
- Layer 1 match_status: {'UNVERIFIED': 1598, 'MISMATCH': 90, 'MATCH': 459}
- ORGANIZE batch artifact files: 62
- PASS

