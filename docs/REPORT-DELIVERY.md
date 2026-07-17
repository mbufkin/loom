# Report delivery — hybrid curriculum-audit narrative

Mise en place (Layer 0→2) fills ledgers. **Report delivery** is a separate phase:
code locks inventories; the local Analyst writes audit-style narrative grounded in
those facts.

## What this is / is not

| Is | Is not |
|----|--------|
| Curriculum **audit** narrative (findings → patterns → recommendations) | Teacher evaluation / SET reports |
| Written expectations (day grid / S&S / calendar) vs **folder artifacts** | Classroom observation or coaching |
| Revision **options** (author / relocate / drop / expected overlap) | Authored lessons, assessments, or rewrites |

## Presentation rules (curriculum-review literature)

Drawn from Fenwick English / CMSi curriculum management audits, written–taught–
assessed quality control (here: written vs materials on disk), curriculum mapping
coherence work, district YAG/pacing review cycles, and CTE program self-study —
**not** instructional coaching or teaching-eval UX research.

1. Lead with **findings against standards** (match vs discrepancy), evidence first.
2. Cite ledger ids (`element_id`, `doc_id`, unit/role); keep code tables as the
   inventory of record.
3. Separate **finding** (existing state) from **recommendation** (revision options).
4. Prefer **systemic patterns** (same gap across units); full lists stay in tables.
5. Label inferred YAG as **draft**; frame MISSING as calendar/S&S vs folder, not
   teacher performance.

## CLI

```bash
# Default: hybrid model delivery for first-pass + teacher
python3 synthesize.py --project dallas-career-2026 --report all

# Fast regen (tables only)
python3 synthesize.py --project dallas-career-2026 --report all --delivery code

# One unit
python3 synthesize.py --project dallas-career-2026 --report teacher --unit engineering
```

`dashboard` and `review-queue` are always code-only. Raw phase JSON lives under
`output/raw/reports/<report_id>/<scope>/`.

## Phases

1. **Findings** — existing state vs expectations (no advice)
2. **Patterns** — coherence (gaps / redundancies / misfiles)
3. **Recommendations** — work-session revision options only

Implementation: [`report_delivery.py`](../report_delivery.py). Registry: [`reports.py`](../reports.py).
