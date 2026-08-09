# Layer 1 Report

**Status:** SUCCESS
**Project:** lab-dallas-ag
**Scope:** all units
**Elements judged:** 26
**MATCH:** 0
**MISMATCH:** 0
  - corroborated (3+ elements of the same document agree): 0 — high-confidence, likely real misfiles
  - single/low-corroboration: 0 — needs individual review, not yet strong enough to act on alone
**CROSS_REFERENCE (hub/overview unit's own element names another unit — expected, not a misfile):** 0
**EXPECTED_OVERLAP (human-confirmed legitimate overlap pair, see manifest.yaml known_overlaps — not a misfile):** 0
**ORPHAN:** 0
**UNVERIFIED (no self-declaration, parent-link only, or a discounted hub-unit self-declaration):** 26
**MISSING role findings:** 8
**DUPLICATE role findings:** 1
**CHECK_FAILED role findings (Phase 3 model call failed — NOT a real finding, needs re-run):** 0

## Artifacts
- `bucket-ledger.json` — one row per Layer 0 element, with Phase 1-2 placement judgment
  (plus `fulfills_role`/`fulfillment_confidence` backfilled from Phase 3, if any)
- `findings.json` — one row per (unit, day, expected role), with Phase 3 fulfillment judgment
- `REVIEW-QUEUE.md` — remaining MISMATCH findings grouped by unit-pair, for a human to
  confirm as either a genuine error or an expected overlap (see manifest.yaml known_overlaps)
- `.raw/<doc_id>-phase1.json` — raw Phase 1 model responses
- `.raw/<unit_id>-<day_id>-phase3.json` — raw Phase 3 model responses

## MISMATCH detail (sorted by corroboration strength)
(none)
