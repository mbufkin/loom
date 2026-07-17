# Outputs — Crystallize

Primary plates for `./run-audit` / `synthesize.py --report all --delivery model`.
Operator table (always keep in sync): [OPERATORS.md](../OPERATORS.md) § Outputs.
List report ids: `python3 synthesize.py --list-reports`.

## Project level (default deliverables)

| File | Description |
|------|-------------|
| `output/FIRST-PASS.md` | Course-level Curriculum Review Work Packet (report `first-pass`) |
| `output/GLOBAL-AUDIT.md` | **Alias** of first-pass (compat name) |
| `output/GLOBAL-AUDIT-REPORT.pdf` | PDF rendered from first-pass markdown |
| `output/DASHBOARD.md` | Skimmable heatmap (report `dashboard`; code delivery) |
| `output/SUMMARY.md` | Compact pass / review / gap table per unit |
| `output/aggregate-stats.json` | Machine-readable aggregate stats |
| `output/teachers/<unit>/TEACHER-PACKET.md` | Per-unit punch list (report `teacher`) |
| `pacing-plan.yaml` | Inferred projected map — unit days → instructional dates |
| `output/03-year-calendar-map.md` / `.json` | Human / machine year timeline |
| `layer0/ledger.json` | Element ledger with citations |
| `layer1/bucket-ledger.json` / `findings.json` | Placement conformance source of truth |
| `layer1/REVIEW-QUEUE.md` | Overlap HITL queue (report `review-queue`) |
| `layer2/findings.json` / `REPORT.md` | Lesson structural completeness (code-only Layer 2) |

`FIRST-PASS.md` / teacher packets need a real Layer 1 ledger (and Layer 2 findings when present).
Run without `--skip-layer01`, or synthesize raises a clear error. Status vocabulary is
embedded in the first-pass plate for directors.

Hybrid narrative details: [REPORT-DELIVERY.md](REPORT-DELIVERY.md).

## Archived per-unit artifacts (not produced by `./run-audit`)

Older doc-level scrub→place runs may still leave files under `output/<unit>/`
(`02-gap-report.*`, `evidence/`, `AUDIT-REPORT.pdf`). Those are **not** regenerated
by the product path. See [archive/legacy-unit-audit/README.md](../archive/legacy-unit-audit/README.md).

## What outputs are **not**

- Not lesson plans or assessments
- Not an official district adoption packet
- Not auto-remediation — findings only
