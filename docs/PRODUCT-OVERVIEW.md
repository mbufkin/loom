# Product Overview — Loom

## What this is

**Loom** is one read-only **curriculum auditor** program. Curricula are data under `projects/<id>/` — feed any corpus, get a solid report.

Schools and providers rarely ship a complete documentation stack. The system:

1. Accepts **any amount** of curriculum material (PDF, Word, slides, text, …)
2. **Reads each document in full** with local models (chunk + reassemble if oversized) to infer its structure and timing
3. **Audits conformance and gaps** — is each piece where it claims to be; what is present, missing, or misplaced
4. Delivers **director-ready reports** (PDF + markdown)

> Design doctrine: [BETS.md](BETS.md).

## What the system does

| Capability | Status |
|------------|--------|
| Multi-format document ingest | Yes |
| Full-document model reading, element-level, verbatim citations (Layer 0, map-reduce chunking for oversized docs) | Yes — validated on 3 corpora |
| Model-assisted organization into units | Yes |
| Unit calendar inference | Yes |
| Element-level placement conformance auditing (Layer 1: MATCH/MISMATCH/CROSS_REFERENCE/EXPECTED_OVERLAP/ORPHAN/UNVERIFIED + FULFILLED/MISSING/DUPLICATE) | Yes — headline goal; validated on multi-doc corpora (Dallas). **Not** yet for one giant framework PDF (AP CSP CED exceeds context — roadmap §13, deferred) |
| Human-in-the-loop calibration for cross-discipline overlap (`layer1/REVIEW-QUEUE.md`) | Yes |
| Gap / misplaced artifact reports | Yes |
| Year-at-a-glance pacing rollup (inferred, rough scaffold) | Yes — demoted |
| Global PDF + first-pass work packet (`FIRST-PASS.md` / `GLOBAL-AUDIT.md` alias) + `DASHBOARD.md` | Yes |
| Unattended resumable batch queue | Yes (Layer 0/1: checkpointed, retries on parse failure, resumable) |
| Lesson structural completeness inside role-fulfilling docs (Layer 2; code-only) | Yes — on default `./run-audit` path |
| One-command pipeline (`./run-audit` / `run_project.py`) | Yes — Layer 0 → 1 → 2 → hybrid synthesize |

## Explicitly out of scope (by charter, not by tier)

The system audits structure. It **never authors content** — no lesson, assessment,
or rubric generation, ever. That boundary is the product's identity, not a
limitation to grow out of. See [STRUCTURAL-FILL.md](STRUCTURAL-FILL.md).

## Core principle: structural fill, not content fill

| We **do** infer | We **never** create |
|-----------------|---------------------|
| Unit calendars from documents | Missing lesson plans |
| Projected pacing / year map | Assessments or rubrics |
| Placement on timeline | Instructional content |
| Gap and coverage reports | “Fixed” curriculum |

Every inferred artifact is labeled **`inferred_from_documents`** and carries a disclaimer: not official district curriculum.

## Who it is for

- **Curriculum directors** evaluating provider completeness
- **CTO / data teams** running local LLM audit workflows
- **Partners** who need conformance and coverage reporting on curriculum

## Sample output

See [OUTPUTS.md](OUTPUTS.md) and the `projects/dallas-career-2026/` sample (calendars + inferred pacing — source documents not redistributed in this repo).
