# Layer 0 Report

**Status:** SUCCESS
**Project:** lab-dallas-ag
**Documents scanned:** 2
**Documents extracted OK:** 2
**Documents failed extraction (skipped):** 0
**Elements in ledger:** 26
**Second-pass rechecks:** 0
**Documents with schema/model errors:** 0
**Uncited excerpts (flagged, not dropped):** 0

## Extraction failures
- None

## Artifacts
- `ledger.json` — the shared evidence ledger (one row per element)
- `ledger.md` — human-readable ledger + per-document notes
- `.raw/<doc_id>-tier1.json`, `.raw/<doc_id>-tier2.json` — raw model responses
- `.raw/<doc_id>-chunk<N>of<M>-tier1.json`, `-tier2.json` — for oversized documents,
  one pair per chunk (real map/reduce — see docs/roadmap.md "Large single-document
  chunking")
