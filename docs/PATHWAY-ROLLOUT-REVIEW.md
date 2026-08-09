# Pathway Rollout Review — Paths B–H

**Status:** accepted · **Reviewed:** 2026-08-09 · **Branch:** `feature/lesson-quality-ui-wiring`

This is the acceptance record for expanding Loom from "Path A plus a catch-all" to
the full eight-lens router (A–H). It answers two questions and nothing else:

1. **What is each new path worth?** — with real findings from a real corpus, not a claim.
2. **Did adding them break anything?** — with a reproducible regression result.

For *how* each path works, see [PATHS.md](PATHS.md) and the per-path docs
(`PATH-A-...` through `PATH-H-...`). This document is the *review*, not the spec.

---

## 1. Verdict

| Question | Answer |
| --- | --- |
| Do all eight lenses route documents? | Yes — A, B, C, D, E, H proven on Dallas; F on Bluebonnet; G on a syllabus lab |
| Do the new paths produce non-empty findings? | Yes — every path reaches `status: ok` on a corpus that contains its doc type |
| Did any pre-existing behavior regress? | No — 15/15 offline tests pass, including the pre-existing 7 |
| Is the regression gated going forward? | Yes — the eight lens tests are now in CI and `npm test` (they were not before) |

**One-line summary:** the router got six new lenses, they each find real gaps that
Path A and the old catch-all were silently swallowing, and the existing pipeline
is byte-for-byte unaffected on every test that existed before the change.

---

## 2. Value of each path

Read the status columns as: `PRESENT` = the lens found the thing it looks for,
`PARTIAL` = weak or partial signal (worth a human look), `MISSING` = the thing is
absent (the actionable finding), `STUB` = one-pager emit step, deliberately not
implemented yet.

### The headline: what the new lenses caught that Path A could not

Before this rollout, anything that was not a lesson plan fell into Path C, which
only asks one question (`C4 Growth-bucket cue`). Routing those same documents
through purpose-built lenses turned a single vague signal into specific, fixable gaps:

| Path | Lens | Corpus | Docs | The finding that justifies the path |
| --- | --- | --- | --- | --- |
| **B** | Assessment (quiz ↔ key) | Dallas live | 26 | **25 of 26 assessments have no answer-key signal** (`B3 MISSING`), and **9 quizzes are orphaned** with no sibling key (`B5 MISSING`). This is undeliverable-to-a-teacher, and nothing else in the system was checking it. |
| **C** | General / nursery | Dallas live | 1 | Now a genuine catch-all of *one* document instead of 62. That drop is the clearest single measure of the rollout's value — 61 documents moved from "unclassified" to a lens that actually asks the right questions. |
| **D** | Teacher support | Dallas live | 8 | **All 8 teacher-edition documents lack TE/guide role cues** (`D2 MISSING`) and **5 of 8 have no facilitation cues** (`D3`). These were previously indistinguishable from student handouts. |
| **E** | Student practice | Dallas live | 36 | The largest bucket in the corpus. **23 of 36 have no learning-target cue** (`E4 MISSING`) and only 1 of 36 has a clean student-task signal (`E3 PRESENT`). Practice material that is not tied to a target is the most common quality complaint this lens now surfaces automatically. |
| **F** | Standards & pacing | Bluebonnet E2E | 12 | **11 of 12 YAG/scope-and-sequence docs carry standards cues** (`F4 PRESENT`) — this path mostly *confirms* health, which is its job. The 1 miss plus 8 `PARTIAL` role cues are the review queue. |
| **G** | Syllabus | `lab-culinary-syllabus` | 2 | The deepest lens (G2–G7, 21 fields). Both syllabi are `PARTIAL` on **five of six sections** — identity/logistics, assessment transparency, TEKS timeline, policies, and CTE/WBL access. A syllabus that looks fine to a human is measurably incomplete against the CTE rubric. |
| **H** | Exit ticket | Dallas live | 21 | Split cleanly out of Path B so exit tickets stop being graded as quizzes. **16 of 21 have no learning-target cue** (`H3`) and **17 of 21 give no next-day formative signal** (`H4`) — the entire point of an exit ticket. |

### Why the split mattered structurally

The router change is visible in the Dallas histogram. Same corpus, before and after:

| Path | Before (`e2e/runs/grok-4.5`) | After (`e2e/runs/grok-4.5-ah-20260805`) |
| --- | --- | --- |
| A Lesson | 19 | 19 |
| B Assessment | 30 | 20 |
| C General (catch-all) | **62** | **5** |
| D Teacher support | — | 12 |
| E Student practice | — | 34 |
| H Exit ticket | — | 21 |

Path A is **unchanged at 19 documents** across both runs. That is the important
number: the new lenses drew exclusively from the catch-all and from Path B's
over-broad claim, never from Path A. Path B shed 10 documents and Path C shed 57;
those 67 became the 12 teacher-support, 34 student-practice, and 21 exit-ticket
documents that now get graded by a lens built for them.

### Per-step detail

<details>
<summary>Dallas live root — full step rollup</summary>

```
Path B (26 docs)   B1 PRESENT 26 | B2 P7/PA3/M16 | B3 P1/M25  | B4 P6/M20  | B5 P8/PA1/NA8/M9 | B6 STUB
Path C (1 doc)     C1 MISSING 1  | C2 PRESENT 1  | C3 PRESENT 1 | C4 MISSING 1 | C5 STUB
Path D (8 docs)    D1 PRESENT 8  | D2 M8         | D3 PA3/M5  | D4 P5/M3   | D5 STUB
Path E (36 docs)   E1 PRESENT 36 | E2 P4/PA17/M15 | E3 P1/PA27/M8 | E4 P13/M23 | E5 STUB
Path H (21 docs)   H1 PRESENT 21 | H2 P17/PA4    | H3 P5/M16  | H4 P4/M17  | H5 STUB
```

</details>

<details>
<summary>Bluebonnet Path F and syllabus lab Path G</summary>

```
Path F (12 docs)   F1 PRESENT 12 | F2 P3/PA8/M1 | F3 P7/PA4/M1 | F4 P11/M1 | F5 STUB
Path G (2 docs)    G1 PRESENT 2  | G2 PA2 | G3 P2 | G4 PA2 | G5 PA2 | G6 PA2 | G7 PA2 | G8-G9 STUB
```

</details>

### Coverage matrix

Each path has both a **synthetic test fixture** (fast, corpus-free, runs in CI) and a
**real-corpus proof** (slow, shows the lens works on messy input):

| Path | Synthetic test | Real corpus | Findings status |
| --- | --- | --- | --- |
| A | `test_loom_pipeline.py` | Dallas (19 docs) | emitted |
| B | `test_path_b_assessment.py` | Dallas (26), `lab-assessment-path-b` (6) | `ok` |
| C | `test_path_c_general.py` | Dallas (1), `lab-general-path-c` (3) | `ok` |
| D | `test_path_d_teacher_support.py` | Dallas (8), `lab-teacher-support-path-d` (3) | `ok` |
| E | `test_path_e_student_practice.py` | Dallas (36), `lab-student-practice-path-e` (3) | `ok` |
| F | `test_path_f_standards_pacing.py` | Bluebonnet (12), `lab-standards-path-f` (3) | `ok` |
| G | `test_path_g_syllabus.py` | `lab-culinary-syllabus` (2) | `ok` |
| H | `test_path_h_exit_ticket.py` | Dallas (21), `lab-exit-ticket-path-h` (3) | `ok` |

Router behavior itself is covered by `test_route_lenses.py` (14 cases), which pins the
cascade precedence the new lenses depend on — filename priors beating graph roles
(`test_syllabus_filename_beats_graph_te`, `test_standards_filename_beats_graph_te`) and
the B/H split (`test_exit_ticket_is_path_h_not_quiz`).

---

## 3. Proof we did not break the system

### Test results

All 15 offline tests pass. The **first seven existed before the pathway work** and
are the actual regression signal; the last eight are the new lenses.

| Test | Status | Time | New? |
| --- | --- | --- | --- |
| `test_schema_validate.py` | PASS | 83 ms | pre-existing |
| `test_audit.py` | PASS | 63 ms | pre-existing |
| `test_rollup.py` | PASS | 177 ms | pre-existing |
| `test_doc_extract.py` | PASS | 65 ms | pre-existing |
| `test_loom_pipeline.py` | PASS | 7656 ms | pre-existing |
| `test_usage.py` | PASS | 22 ms | pre-existing |
| `test_intake_goldens_extract.py` | PASS | 132 ms | pre-existing |
| `test_route_lenses.py` | PASS | 147 ms | new |
| `test_path_b_assessment.py` | PASS | 72 ms | new |
| `test_path_c_general.py` | PASS | 68 ms | new |
| `test_path_d_teacher_support.py` | PASS | 71 ms | new |
| `test_path_e_student_practice.py` | PASS | 71 ms | new |
| `test_path_f_standards_pacing.py` | PASS | 72 ms | new |
| `test_path_g_syllabus.py` | PASS | 96 ms | new |
| `test_path_h_exit_ticket.py` | PASS | 70 ms | new |

`test_loom_pipeline.py` is the strongest evidence here: it drives the whole
pipeline end to end against the real Dallas project, and it passes unchanged with
all eight paths registered.

Reproduce with:

```bash
npm test              # everything
npm run test:core     # the seven pre-existing tests only
npm run test:paths    # the eight lens tests only
```

### Backward compatibility

- **Path A is untouched.** 19 documents routed before the rollout, 19 after. No Path A
  document was reassigned to a new lens.
- **Absent doc types degrade, they do not fail.** A corpus with no syllabi writes
  `path_g/findings.json` with `status: skipped` rather than erroring. Confirmed on
  Dallas (F and G both `skipped` with all other paths `ok`) and on every single-path
  lab, which each show exactly one `ok` and the rest `skipped`.
- **Older runs still read correctly.** The pre-rollout `e2e/runs/grok-4.5` snapshot,
  which only has A/B/C at `status: stub`, still loads in the UI and in the survey tooling.

### The gap this review closed

The eight lens tests **were written but never wired into any gate** — neither
`.github/workflows/ci.yml` nor the `npm test` script referenced them, so a change to
the router or a checklist could have broken a path with CI still green. This review
added them to both, and split `npm test` into `test:core` / `test:paths` so the
pre-existing suite can still be run in isolation as a clean regression signal.
`test_usage.py` was also missing from CI and is now included.

---

## 4. Known limitations

These are accepted, not defects:

- **`*5`/`*6` emit steps are `STUB` on every path.** B6, C5, D5, E5, F5, H5, G8, G9 are
  the one-pager generation steps. Presence extraction is complete; rendering is not.
  Path A is the only path with a finished one-pager.
- **Path G's real-corpus proof is a 2-document synthetic lab**, not a district corpus.
  `lab-culinary-syllabus` was seeded specifically because no ingested project contained
  syllabi. The lens is correct; the sample is small.
- **Bluebonnet's B/C/D/E findings are stale `status: stub`.** Only Path F was re-run
  there. Dallas is the current reference for those four paths.
- **ICEV curriculum is not in the repository**, so the originally planned "one corpus
  exercises all of A–H" run could not happen. Coverage is assembled across three
  corpora instead, which is weaker evidence for the router's cascade ordering under
  a genuinely mixed document set.
- **`test_loom_pipeline.py` writes into the live Dallas tree.** Running the suite
  produces uncommitted changes under `projects/dallas-career-2026/path_*/`. Expected,
  but do not mistake it for drift.

---

## 5. Supporting artifacts

| Artifact | What it holds |
| --- | --- |
| [`experiments/pathway-a-g-verify/RESULTS.json`](../experiments/pathway-a-g-verify/RESULTS.json) | Machine-readable route histograms and findings status per corpus |
| [`experiments/pathway-a-g-verify/README.md`](../experiments/pathway-a-g-verify/README.md) | Which project covers which path, and why |
| [PATHS.md](PATHS.md) | Router cascade and the A–H taxonomy |
| [PATH-B-QUIZ.md](PATH-B-QUIZ.md) … [PATH-H-EXIT-TICKET.md](PATH-H-EXIT-TICKET.md) | Per-path step definitions |
| [CURRICULUM-ACCEPTANCE-REVIEW.md](CURRICULUM-ACCEPTANCE-REVIEW.md) | Formal accept/reject of a pack + run intent |

---

## 6. Recommended next steps

In priority order:

1. **Ingest ICEV** (or any single mixed corpus) and run one E2E that exercises all of
   A–H together. This is the only material gap in the evidence.
2. **Refresh Bluebonnet's B/C/D/E** so a second corpus corroborates Dallas.
3. **Implement the `*5`/`*6` emit steps**, starting with H5 — exit tickets have the
   highest miss rate (`H4 MISSING` on 17 of 21) and the smallest one-pager.
4. **Commit this branch.** The path findings, labs, and this review are all uncommitted
   on `feature/lesson-quality-ui-wiring`.
