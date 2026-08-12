# Pathway A–H verification

Raw evidence behind [`docs/PATHWAY-ROLLOUT-REVIEW.md`](../../docs/PATHWAY-ROLLOUT-REVIEW.md).
Start with the review doc — this folder is the backing data, not the conclusion.

## Corpus strategy

No single ingested project contains all eight document types, so coverage is
assembled across four corpora:

| Corpus | Covers | Notes |
| --- | --- | --- |
| `dallas-career-2026` (`e2e/runs/grok-4.5-ah-20260805`) | A, B, C, D, E, H | Post-rollout reference; F/G correctly `skipped` |
| `dallas-career-2026` (`e2e/runs/grok-4.5`) | A, B, C only | Pre-rollout baseline — the before/after comparison |
| `bluebonnet-math-2026` (`e2e/runs/grok-4.5`) | **F** | 12 YAG / scope-and-sequence docs at `status: ok` |
| `lab-culinary-syllabus` | **G** | Seeded lab, 2 syllabi — no ingested project had any |
| `lab-*-path-{b,c,d,e,f,h}` | one path each | Isolation labs: prove one `ok` + the rest `skipped` |

A single mixed corpus that exercises all of A–H in one E2E is still the
coverage gap (see rollout review §6).

## Files

- [`RESULTS.json`](RESULTS.json) — route histograms, findings status, and per-step
  status rollups for every corpus above, plus the regression summary.

Regenerate the corpus survey after a re-run:

```bash
npm test    # then re-run the survey block in docs/PATHWAY-ROLLOUT-REVIEW.md §5
```

## Reading `RESULTS.json`

`corpora.<name>.paths.<LETTER>.steps` holds the actionable signal — a per-checklist-step
count of `PRESENT` / `PARTIAL` / `MISSING` / `NOT_APPLICABLE` / `STUB`. `MISSING` counts
are the gaps a reviewer should act on; `STUB` marks emit steps that are intentionally
not implemented yet.
