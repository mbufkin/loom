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
