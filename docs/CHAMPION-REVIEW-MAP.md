# Champion-style curriculum review ↔ Crystallize

This maps a typical Dallas ISD CTE “curriculum revisiting / standardization”
teacher packet onto what **Crystallize** can and cannot do. Comp, time codes,
meeting locations, and stipend terms are **human/PD logistics** — out of scope
for the auditor. Course numbers (e.g. 1594 / 1677) and named providers (e.g.
Education is Freedom) are **project-specific inputs**, not hardcoded product
features.

## District spine (always for DISD)

Champions need a Year-at-a-Glance on the **real district calendar**. Crystallize
expects the same:

| Input | Where |
|-------|--------|
| Official Traditional calendar image | `reference/DISD-Academic-Calendar-2026-2027.png` |
| Machine spine | `school-calendar.yaml` |

Shared canonical copies: [`shared/disd-school-calendar/`](../shared/disd-school-calendar/).
Without the YAML, `rollup.py` cannot produce a **dated** pacing / YAG map.

## Deliverables champions produce vs what Crystallize audits

| Champion / CTE deliverable | Crystallize role | Artifact |
|----------------------------|------------------|----------|
| **Year-at-a-Glance (YAG)** | **Path F** presence (F1–F5) on partner YAG/pacing docs; dated map still from unit calendars | `path_f/findings.json` — see [PATH-F-STANDARDS-PACING.md](PATH-F-STANDARDS-PACING.md); also `pacing-plan.yaml`, `output/03-year-calendar-map.md` |
| **Pacing guide / S&S** | **Path F** — same lens as YAG (presence extractors) | `path_f/findings.json` |
| **Scope & sequence / unit frameworks** | Manifest + `units/*/calendar.yaml` (expected day roles) | ingest / human-curated YAML |
| **Course syllabus** | **Path G** — course-level student/family contract audit (G1–G9; presence extractors landing) | `path_g/findings.json` — see [PATH-G-SYLLABUS.md](PATH-G-SYLLABUS.md) |
| **Lesson plan templates** | **Layer 2** — structural completeness of fulfilled `lesson_plan` docs (standards, materials, instruction, assessment) | `layer2/findings.json`, first-pass §4 / teacher §3 |
| **Instructional resources / supports** | Layer 1 role fulfillment (worksheet, rubric, slides, …) + MISSING | `layer1/findings.json` |
| **Quizzes / answer keys** | **Path B** — quiz↔key assessment stub | `path_b/findings.json` — see [PATH-B-QUIZ.md](PATH-B-QUIZ.md) |
| **Exit tickets** | **Path H** — standalone formative check (not quiz↔key) | `path_h/findings.json` — see [PATH-H-EXIT-TICKET.md](PATH-H-EXIT-TICKET.md) |
| **Other assessments / performance tasks** | Layer 1 roles (`rubric`, …) + Path B when assessment-bearing | `layer1/findings.json` |
| **TEKS / industry / CCMR alignment** | Not adjudicated as “aligned”; Layer 0 may tag `standards_objectives` text when present | excerpts in ledger |
| **Vertical / horizontal alignment across two courses** | Cross-unit MISMATCH / EXPECTED_OVERLAP / REVIEW-QUEUE | `FIRST-PASS.md`, `layer1/REVIEW-QUEUE.md` |
| **Identify gaps, redundancies, program improvements** | MISSING, DUPLICATE, INCOMPLETE, MISMATCH | first-pass PDF + teacher packets |
| **Author / rewrite lessons, EIF modules, videos, syllabi** | **Forbidden** (structural fill only) | — |
| **PD facilitation, compensation records** | Not in product | — |

## How to use Crystallize in a summer revisit (conceptually)

1. Drop the course pack into `projects/<course-id>/sources/` (any provider — not only named partners).
2. Keep DISD `school-calendar.yaml` in the project root.
3. Run `./run-audit <course-id>` (overnight OK) — ends with `synthesize.py --report all --delivery model` (hybrid curriculum-audit narrative on first-pass + teacher; see [`REPORT-DELIVERY.md`](REPORT-DELIVERY.md)).
4. Open plates (same ledgers, different audiences):
   - **First-pass (course):** `output/FIRST-PASS.md` / `GLOBAL-AUDIT-REPORT.pdf` — YAG, gaps, completeness, filing + model findings/recommendations.
   - **Teacher (per unit):** `output/teachers/<unit_id>/TEACHER-PACKET.md` — unit punch list + model narrative for that unit.
   - **Dashboard:** `output/DASHBOARD.md` (code-only heatmap)
   - **Review queue:** `layer1/REVIEW-QUEUE.md`
5. Call one plate (model delivery is the default; use `--delivery code` for tables-only regen):
   ```bash
   python3 synthesize.py --project <id> --list-reports
   python3 synthesize.py --project <id> --report first-pass
   python3 synthesize.py --project <id> --report teacher --unit engineering
   python3 synthesize.py --project <id> --report all --delivery code
   ```
6. Humans edit content and official YAG/syllabus; re-run Layer 1/2 only when the folder changes, then `--report all` again (delivery re-reads ledgers — no re-extract unless ledgers are wrong).

Registry: [`reports.py`](../reports.py). Delivery: [`report_delivery.py`](../report_delivery.py). Planned (not in `--report all` yet): `ops`, `document`.

## Framing for teachers (one paragraph you can reuse)

> Crystallize is a **read-only structure check**. It reads what is in the shared
> drive against the Dallas ISD instructional calendar and the unit day grid, and
> reports misfiled documents, missing expected materials, and lesson plans that
> lack core parts (standards, materials, instruction, assessment). It does
> **not** write lessons, score pedagogy, or replace TEKS alignment judgment —
> those stay with CTE and classroom teachers.

## Related doctrine

- `docs/STRUCTURAL-FILL.md` — structural vs content fill  
- `docs/BETS.md` Bet 7 (conformance over calendar synthesis), Bet 8 (auditor forever)  
- `OPERATORS.md` — how to run  
