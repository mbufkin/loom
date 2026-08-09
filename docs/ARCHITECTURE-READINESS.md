# Architecture Readiness — are we done building, or still building?

**Assessed:** 2026-08-09 · **Updated:** 2026-08-09 (phases 1–3 landed) ·
**Branch:** `feature/lesson-quality-ui-wiring` · **Scope:** Paths A–H structure, not model quality

The question this answers: *is the structure set, so that everything left is tuning
how the model rates documents?*

**Answer: yes. All ten checks in §3 pass. The structure is frozen and tuning is safe.**

The pipeline fails loudly on a broken stage and on a silent one. Every non-lesson
document is scored by exactly one system. Findings validate against a schema at write
time, all eight paths share one shape, and ratings are golden-pinned so a checklist
change produces a reviewable diff instead of an invisible shift.

The remaining work is tuning: how the model rates documents, not how the data moves.

| Check | Status |
| --- | --- |
| 1 single scorer · 2 findings schema · 3 Path A conforms · 5 route-map schema | **Pass** |
| 6 handoffs enforced · 7 determinism · 8 Path A tests · 9 golden pins · 10 stage integrity | **Pass** |
| 4 one path per document | Holds on every corpus; the only one still unasserted in CI |

**All 12 projects are pinned.** The four that lacked a route map were re-routed and
re-scored offline in under ten seconds total — Layer 0 was already on disk for each, and
routing plus presence scoring are deterministic and need no model. Nothing required a
full pipeline run.

| Lens | Documents pinned | Real corpora |
| --- | --- | --- |
| A lesson plan | 38 | dallas |
| B assessment | 50 | dallas |
| C general | 75 | ap-csp, bluebonnet, dallas, pathful |
| D teacher support | 26 | bluebonnet, dallas |
| E student practice | 72 | bluebonnet, dallas |
| F standards & pacing | 15 | bluebonnet |
| G syllabus | 2 | waxahachie culinary |
| H exit ticket | 45 | dallas |

**Path G was recorded here as fixture-only. That was wrong**, and the error is worth
keeping visible: `lab-culinary-syllabus` holds two genuine Waxahachie ISD documents
(Culinary I and Culinary Practicum), so the lens had real input all along and nobody
had read what it said about them. Its thin corpus was mistaken for a synthetic one.

Reading them is what surfaced the defect described in §11: presence was matched as a
plain substring, so `PPE` matched "Cli**ppe**rs" and the lens reported lab safety
rules on a syllabus that had none. Path G is now checked against those two documents
field by field, and its ratings are pinned at field level.

Two documents is still a thin corpus, and both come from one teacher, so the
checklist is tuned to one author's phrasing. The next syllabus from a different
district should be expected to move ratings again.

What was already solid is listed in §5.

---

> **Visual walkthrough:** [`ARCHITECTURE-READINESS.html`](ARCHITECTURE-READINESS.html)
> — same findings with pipeline diagrams. Open it in a browser.

## 0. The blocker, stated correctly: two stages silently do not run — RESOLVED 2026-08-09

> **Resolved.** Both stages import and run; the artifact rung is now a rollup over
> Paths B–H rather than a separate scorer; and `run_step` raises `StageBrokenError`
> on a child import/syntax failure instead of warning past it. Evidence and the
> resulting numbers are in §0.1. The diagnosis below is kept because it is the
> reason the design changed.

I first framed §1 below as a design choice between two competing scorers. That was
wrong in a way that changes the conclusion, so it is corrected here.

**Two of the ten pipeline stages crash on import**, and both sit inside a
`try/except` band in `run_project.py` that logs a warning and lets the run report
success:

```
artifact_rung   ModuleNotFoundError: No module named 'artifact_scorers'
unit_rung       ImportError: cannot import name 'load_expectations' from 'synthesize'
```

`artifact_scorers.py` was committed in `a13d3a3` and is **not in HEAD**, with no
commit recording its deletion — only a stale `.pyc` dated 2026-07-23 remains. There
is no `ARTIFACT-RUNG.json` anywhere in the repository.

**The consequence.** `unit_rung.unit_band()` gates "Strong" on
`not metrics.get("has_artifact_gap")`. That flag comes from `_unit_artifacts()`,
which is explicitly written to return a gap-free block when the artifact rung is
absent. With the rung dead the flag is permanently `False`, so **the non-lesson
quality gate is inert** — a unit can be rated Strong while containing 25 quizzes
with no answer key.

So §1 is not a choice between two working designs. It is **one working scorer with
no consumer (Paths B–H) and one consumer whose scorer is gone (the artifact rung).**
That collapses the decision: make Paths B–H the single non-lesson scorer and have
`artifact_rung.py` roll their findings up into the `ARTIFACT-RUNG.json` shape that
`unit_rung.py` already expects.

The deeper problem is not the bug but that **nothing asserts a stage produced
anything** — see check 10 in §3.

## 0.1 What was built (2026-08-09)

Three changes, in the order they landed.

**Stages fail loudly.** `run_project.run_step` now tees the child's stderr and
raises `StageBrokenError` when it sees `ModuleNotFoundError`, `ImportError`, or
`SyntaxError`. The best-effort `try/except` band re-raises that class and keeps
warning on everything else, so a model being offline still degrades gracefully
while a packaging bug stops the run. `test_pipeline_stages.py` import-checks every
pipeline module in CI — this is check 10, and it is the thing that would have
caught the dead rungs a month earlier.

**`unit_rung` runs again.** `synthesize.load_expectations` was restored from
`957fa80`. The history rewrite had removed more than that one symbol: it also took
`aggregate_missing`, `_pick_exemplars`, the `EXEMPLAR_CAP` / systemic-absence
constants, and `aggregate_layer1`'s `expectations` parameter and `missing_rollup`
return. Restoring only the imported name would have import-cleanly then raised
`TypeError` at runtime, so the whole consumer path came back together. The other
two `aggregate_layer1` callers are unaffected — the new parameter defaults to
`None`.

**The artifact rung is a rollup, not a scorer.** `artifact_rung.py` no longer
scores anything. It reads `path_b` … `path_h` findings, maps each document to its
unit through the manifest, and emits the same `ARTIFACT-RUNG.json` contract
`unit_rung` already consumed. `artifact_scorers.py` was not restored. Two rules
matter and are pinned by `test_artifact_rung.py`:

- Documents whose type is in `lesson_bakeoff.LESSON_DOC_TYPES` are skipped, because
  `lesson_rung` already grades them. Both rungs now partition the corpus from one
  shared definition instead of two lists that can drift.
- A `MISSING` on a step whose fields are *all* optional is advisory, not a gap. A
  step with any required field still gates. See §2.5 — the root cause lives
  upstream and is not fixed yet.

**Dallas, after the change:** 78 artifacts across 17 units, 12 passing the presence
gate (15.4%), 16 units carrying a deterministic gap. Zero overlap with the 33
documents `lesson_rung` grades. The largest remaining gaps are real: 25 assessments
with no answer-key signal, 17 exit tickets with no next-day formative signal, 16
with no item stems.

**Unit bands did not move** — still 15 Weak, 3 Unrated. That is correct, not a
no-op. `unit_band()` consults `has_artifact_gap` only inside the Strong branch, so
the gate can demote Strong to Developing but never manufacture Weak. Dallas has no
Strong candidates today because systemic role gaps already drive every unit down.
The gate is live and load-bearing; this corpus simply gives it nothing to act on.
A corpus with clean lesson coverage and broken artifacts is where it will first
show, and that is exactly the case it exists to catch.

## 1. Background: two spec formats for the same job

Loom carries **two presence-scoring spec formats over the same non-lesson
documents**. Per §0 only one of the two is executable today, but both are still in
the tree, which is what makes the resolution above necessary.

| | System 1 — Paths B–H | System 2 — Artifact rung |
| --- | --- | --- |
| Spec source | `workflows/checklists/*.yaml` | `workflows/rubrics/artifacts/*.yaml` |
| Driver | `workflows/run_paths.py` | `artifact_rung.py` |
| Reads | `layer0/route-map.json` + ledger | `layer0/ledger.json` directly |
| Writes | `path_<letter>/findings.json` | `layer_artifact/ARTIFACT-RUNG.json` |
| Consumed by | **The UI, and nothing else** | `unit_rung.py` → dashboard → reports → PDF |

They overlap on quizzes, exit tickets, worksheets, answer keys, rubrics,
presentations, and project work — and they disagree about what matters. For a quiz:

```
System 1  workflows/checklists/assessment.yaml    (v1-assessment-quiz-key)
  B2 Item stems               numbered_items, choice_stems
  B3 Answer key signal        answer_key_header, keyed_answers
  B4 Learning targets         objective_or_teks
  B5 quiz <-> key pairing     (code, not checklist)

System 2  workflows/rubrics/artifacts/quiz.yaml   (v1-quiz-2026-07)
  has_items                   Assessment items present
  has_instructions            Directions / instructions
```

System 1 is the richer, newer lens — it is the one that found *25 of 26 Dallas
assessments have no answer key* and *9 orphaned quizzes*. System 2 has two criteria,
no pairing concept, and (per §0) does not run at all.

### Why this is structural and not cosmetic

Tuning means changing how documents get rated. Two spec formats for one job means
tuning twice and still disagreeing, so the reported number and the reviewable number
drift apart. This has to be settled before tuning starts, because it determines
*which file you tune*.

Options, with §0 taken into account:

1. **Artifact rung consumes path findings — recommended.** Paths B–H become the
   single scorer; `artifact_rung.py` stops re-deriving presence and rolls up
   `path_*/findings.json` into `ARTIFACT-RUNG.json`. One spec format, one number,
   B–H stop dead-ending, and the dead scorer is not resurrected.
2. **Restore `artifact_scorers.py` from `a13d3a3`.** Recoverable and it would light
   the dashboard back up, but it reinstates the weaker scorer and locks in two spec
   formats permanently.
3. **Point `unit_rung.py` straight at path findings.** Slightly less code than the
   shim, but it couples the reporting layer directly to the findings format, making
   check 2 urgent rather than merely important.
4. **Keep both with a documented boundary.** Defensible if both worked; one doesn't.

---

## 2. Contract gaps

These are smaller, but each one is a place where "data flows consistently" is
currently a convention rather than something the system enforces.

### 2.1 Paths B–H dead-end — RESOLVED 2026-08-09

Was: no root-level Python module read `path_b` … `path_h` findings, so six of the
eight lenses produced artifacts only the UI panel could see.

`artifact_rung.py` now reads all of them and rolls them into `ARTIFACT-RUNG.json`,
which `unit_rung.py` consumes for the unit verdict, which `synthesize.py` renders
into the dashboard. The loop from a path finding to a director-facing report is
closed for the first time (§0.1).

**Still dead:** `layer0/workflow-handoff.json` is written by `run_paths.py` and read
by nothing at all. Either wire it or delete it; leaving a written-but-unread artifact
is how the last one rotted unnoticed.

### 2.2 Path A does not honor the findings contract — RESOLVED 2026-08-09

> **Resolved.** Path A now carries `lens`, `status`, `checklist`, `inventory`, and
> `steps_by_doc` alongside its existing `steps`, `a6_fields`, and `emit_paths`. The
> addition is purely additive, which matters: `reports.py` reads `A5.hunter_core_present`
> and `A3.status` to compute the curriculum tier, and a replacement would have shifted
> unit ratings silently. Verified unchanged — hunter 8, A3 `COHERENT`, zero unit tier
> changes.
>
> Path-level status is now `ok`/`skipped` like B–H. `ready` is gone from the handoff
> schema, and `_paths_summary()` no longer infers a status for A. `lesson_plan.yaml`,
> `daily_lesson_plan.yaml`, and `syllabus.yaml` gained the `path:`/`workflow_id:`
> headers the other six always had, so Paths A and G are now derivable from the
> checklists and the test workaround that recovered them is gone. `test_path_a_lesson_plan.py`
> gives A the offline coverage B–H already had (check 8).
>
> **Correction to the finding below:** Path A never wrote `status` to disk at all. It set
> `ready` on the in-memory return value *after* writing, so `ready` only ever appeared in
> the handoff — the on-disk file simply had no status.

The original finding, kept for context:

Same directory, same filename, different shape:

| Key | Path A | Paths B–H |
| --- | --- | --- |
| `status` | **absent** | `ok` / `skipped` |
| `lens` | **absent** | present |
| `checklist` | **absent** | present |
| `inventory` | **absent** | present |
| `steps_by_doc` | **absent** | present |
| `steps` | present (A1–A8) | absent |
| `a6_fields`, `emit_paths` | present | absent |

Every consumer has to special-case A. The UI already does — `_paths_summary()`
infers a status for A because the file does not carry one. That inference is a
workaround for a contract gap, and it will spread to the next consumer too.

Two related gaps surfaced while fixing §2.4, both belonging to this work:

- **A reports a different status word.** The handoff records `status: "ready"` for
  Path A where B–H record `"ok"` for the same state. One vocabulary, or consumers
  keep branching.
- **Two checklists do not declare their own identity.** Six checklist YAMLs carry
  `path:` and `workflow_id:` headers; `lesson_plan.yaml` and `syllabus.yaml` do not,
  so Paths A and G exist only in `run_paths.py`. Anything deriving the live path set
  from the checklists silently misses them — which the §2.4 test had to work around.
  Adding the two headers is a two-line fix and removes the workaround.

### 2.3 Nothing validates a findings file — RESOLVED 2026-08-09

> **Resolved.** `schema_validate.py` gained `validate_path_findings()` and
> `validate_route_map()` (check 5), hand-rolled in the module's existing style rather
> than pulling in a `jsonschema` dependency. Both are called at write time — findings
> through a shared `workflows/findings_io.py` helper that validates then atomically
> writes, so all eight paths go through one door instead of seven bolted-on calls.
>
> Confirmed rejecting an unknown step status, a missing required key, and the retired
> `ready` status, while all eight real Dallas findings pass.

The original finding, kept for context:

`schema_validate.py` covers the ingest plan, manifest, unit calendars, placements,
and the Layer 0 / Layer 1 model responses. It does **not** cover
`path_*/findings.json`, `layer0/route-map.json`, or the checklist YAMLs.

Readers are trust-based: `json.loads` plus `.get()`. A path that writes a malformed
or half-written findings file produces a quietly wrong panel, not an error.

### 2.4 The handoff contracts are stale and unenforced — RESOLVED 2026-08-09

> **Resolved.** Both enums now cover all eight paths and workflow ids, and
> `test_loom_pipeline.py` validates a **real emitted** `workflow-handoff.json`
> against `workflow_to_place.json` rather than only asserting the schema parses.
> A second test derives the live path set from the checklist YAMLs plus the emitted
> handoff, so adding a Path I updates the test by adding the lens rather than by
> remembering to edit a literal list. Both were confirmed to fail on the exact
> drift they exist to catch before being accepted.
>
> **Found while fixing it:** Path A reports `status: "ready"` in the handoff where
> B–H report `"ok"` for the same state. The schema accepts both for now, with a
> comment pointing at §2.2, because unifying them means changing Path A's runner —
> that belongs with the Path A contract work, not here.

The original finding, kept for context:

`workflows/handoffs/router_to_workflow.json` is a JSON Schema that still describes
a six-path world:

```json
"workflow_id": { "enum": ["lesson_plan","quiz","general","teacher_support","student_practice","standards_pacing"] },
"path":        { "enum": ["A","B","C","D","E","F"] }
```

`syllabus` and `exit_ticket` are missing; the path enum stops at F.
`workflow_to_place.json` is worse — paths A–C only. These files are never fed to a
schema validator; the only test asserts they exist and parse.

### 2.5 `MISSING` means two different things, and one path disagrees — RESOLVED 2026-08-09

> **Resolved.** All seven modules now emit `OPTIONAL_ABSENT` for an all-optional step
> with no hit, replacing both the six `MISSING` results and `syllabus.py`'s `SKIPPED`.
> The status is in `STEP_STATUSES`, the `PathStepStatus` union, and the Paths panel,
> styled as a neutral signal rather than a failure. `SKIPPED` no longer appears
> anywhere in the tree.
>
> On Dallas, **63 cells moved from `MISSING` to `OPTIONAL_ABSENT`** (B4 20, C4 1, D4 3,
> E4 23, H3 16); no other status changed. `MISSING` now means one thing: 167 → 104.
>
> The gate workaround in `artifact_rung.py` is gone — it treats `OPTIONAL_ABSENT` as
> advisory exactly as it does `PARTIAL`, and no longer infers required-field counts.
> Artifact numbers are byte-identical to the workaround's (78 artifacts, 12 passing,
> 16 of 17 units with gaps), which is the point: the rule was replaced, not loosened.
>
> My "~59" estimate was low. C4 and D4 also qualified.

The original finding, kept for context:

Found while wiring the artifact gate (§0.1). Scoring does not live in `run_paths.py`;
each lens has its own module (`workflows/quiz.py`, `general.py`, …), and **every one of
the seven reads the field-level `optional` flag.** The flag is honored. The problem is
what they do with it.

Each module has a `required == 0` branch for steps whose fields are all optional. Six
resolve "no optional signal found" to `MISSING`; `syllabus.py` resolves the identical
case to `SKIPPED`:

| Module | All-optional, nothing found |
| --- | --- |
| `quiz`, `general`, `teacher_support`, `student_practice`, `standards_pacing`, `exit_ticket` | `MISSING` |
| `syllabus` | `SKIPPED` |

**Two defects follow.**

*One:* `MISSING` is overloaded. It means both "a required element is absent" (a real
finding) and "a nice-to-have signal was not found" (not a finding). Nothing downstream
can tell them apart, which is precisely what misled the artifact gate and still misleads
a human reading the Paths panel.

*Two:* `SKIPPED` is not in the shared vocabulary — `STEP_STATUSES` is
`PRESENT, PARTIAL, MISSING, NOT_APPLICABLE, STUB`. It appears in no findings file today
only because Path G is skipped on every current corpus, so the branch has never fired.
The first real syllabus corpus will emit a status the UI silently drops from its tallies.
A latent bug with a fuse on it.

Six steps define only optional fields and report `MISSING` when the signal is absent:

| Step | Lens | MISSING on Dallas |
| --- | --- | --- |
| `E4` | Student practice — learning target cue | 23 |
| `B4` | Assessment — learning targets / standards | 20 |
| `H3` | Exit ticket — learning target cue | 16 |
| `C4`, `D4`, `F4` | General / teacher support / standards pacing | — |

Three of those are among the top six drivers of gate failure on Dallas, and nine
documents failed purely on them before the workaround.

`artifact_rung.py` currently exempts these at the gate, which keeps the unit verdict
honest. **That is a patch, not the fix.** The Paths panel still renders an absent
optional signal as a red `MISSING`, so a human reviewer is misled exactly the way the
gate was.

**The fix:** give the case its own status, adopted by all seven modules, and add it to
`STEP_STATUSES` so the UI can render it as the neutral signal it is. That retires
`SKIPPED` before it ever reaches a findings file and lets `MISSING` mean one thing again.

Deliberately deferred rather than done inline, because it changes the status vocabulary
in `findings.json` and therefore belongs with the schema work in §2.3 and the golden pins
in check 9 — landing it before those exist would mean re-pinning immediately. Once fixed,
drop the exemption in `artifact_rung.py` and let the gate read the status directly.

### 2.6 Two checklist steps have no human label — RESOLVED 2026-08-09

`B5` and `C1` rendered as bare step ids while every other step resolved to a readable
label. Both are now declared in their checklist `sections` — `B5 Quiz ↔ key pairing`
and `C1 Inventory` — as label-only entries carrying `label` and `step` but no `fields`,
since both are scored in code rather than by field matching. Verified that adding the
sections did not reroute either step through the field rollup: `B5` holds its 9
`MISSING` and `C1` its 1, and the 63 cells that moved are exactly B4, C4, D4, E4, and H3.

---

## 3. The checks that define "structure is frozen"

Concrete and runnable. Each is a gate, not a task — when all nine pass in CI, the
structure is set and tuning is safe.

| # | Check | How to verify | Status |
| --- | --- | --- | --- |
| 1 | One scorer owns non-lesson presence | No document is graded by both `workflows/checklists/` and `workflows/rubrics/artifacts/`, or the boundary is documented and asserted | **Passes** — §0.1; Paths B–H are the sole scorer, lesson/artifact split asserted by `test_artifact_rung.py` |
| 2 | Every path's findings validate against a schema | `validate_path_findings()` exists, all eight conform, called at write time | **Passes** — §2.3; one shared write path in `workflows/findings_io.py` |
| 3 | Path A honors the same contract | A carries `status`, `lens`, `checklist`; consumers stop special-casing | **Passes** — §2.2; additive, curriculum tier verified unchanged |
| 4 | Every routed document lands in exactly one path | Sum of per-path `n_docs` equals `total_routed`; no doc in two findings files | **Passes** on Dallas (111 = 111), unasserted |
| 5 | Route map validates against a schema | `validate_route_map()`, covers the `path` enum A–H | **Passes** — §2.3; called at write time in `route.py` |
| 6 | Handoff schemas match reality and are enforced | Enums include all eight paths; a test validates a real route-map against them | **Passes** — §2.4; two tests in `test_loom_pipeline.py`, both verified to fail on drift |
| 7 | Re-running is deterministic | Two consecutive runs differ only in `generated_at` | **Passes** — verified below |
| 8 | Path A has offline tests like B–H | `test_path_a_lesson_plan.py` with synthetic fixtures | **Passes** — 4 tests, in CI |
| 9 | Findings are golden-pinned | A snapshot test catches unintended rating changes during tuning | **Passes** — `snapshot_findings.py --check --paths` in CI, exits 1 on drift; 8 of 12 projects pinned (see intro) |
| 10 | Every stage imports, and a run asserts its outputs | A CI test imports all ten pipeline modules; a run fails if a declared artifact is missing | **Passes** — §0.1; `StageBrokenError` for the loud half, `StageOutputError` for the quiet half. All 14 stages declare their artifacts; verified the original dead-rung bug is now caught |

### On check 7 (determinism)

I re-ran `route.py` and `workflows/run_paths.py --no-model` against
`lab-assessment-path-b` and diffed. `path_b/findings.json` was **byte-identical**
(`bfd4997…` before and after). The route map differed **only** in its
`generated_at` timestamp. So the presence pipeline is deterministic — but you
cannot diff two runs without normalizing that timestamp first, which is exactly
what check 9 needs to do.

### On check 9 (why it matters most for tuning)

This is the one that makes tuning *safe* rather than just possible. Once findings
are golden-pinned, changing a keyword in `assessment.yaml` produces a reviewable
diff — "23 documents changed from MISSING to PARTIAL" — instead of an invisible
shift. `tools/snapshot_findings.py` already does this for Layer 1 and is not in CI;
the pattern exists and needs extending to paths.

---

## 4. Documentation drift — RESOLVED 2026-08-09

> **Resolved.** Every item below is fixed, plus eight more files the original sweep
> missed (`PROJECT_INDEX.md`, `docs/README.md`, `docs/GRAPH-PHASE.md`, `README.md`,
> `README-crystallize.md`, `PLAN.md`, `TESTING_STRATEGY.md`, and a lab README).
> `doc_type_to_workflow()` is deleted. Three references survive on purpose because they
> describe history accurately: `PLAN.md`'s phase table, this repository's rollout review
> of an older A/B/C-only run, and a pre-rollout baseline in `experiments/`.

The original list, kept for context:

- `run_project.py:16` still describes the path stage as "A/B/C".
- `docs/PIPELINE.md`, `docs/ARCHITECTURE.md`, `docs/E2E.md`, `docs/STRUCTURAL-FILL.md`
  describe A–C or A–G. The code runs A–H.
- `PROJECT_STRUCTURE.md:187` describes the router as "Unit → Path A/B/C".
- ~~The UI labels `layer_artifact/ARTIFACT-RUNG.md` as "Artifact rung — Paths B/C"~~ —
  **fixed 2026-08-09**; it now reads "Paths B–H", which as of §0.1 is also accurate
  rather than merely better-worded.
- `route.py:104` `doc_type_to_workflow()` is dead code — never called. Real routing
  is `resolve_workflow()` at line 244.

---

## 5. What is already solid

Stated plainly so the gaps above are read in proportion. This is the majority of
the system and I found nothing wrong with it:

- **All eight paths run in production.** `run_project.py` always invokes
  `workflows/run_paths.py`, which calls A–H unconditionally. No path is
  test-only or standalone-only.
- **The router cascade is coherent and precedence is explicit.**
  `resolve_workflow()` has a documented order: doc_type hard wins, then filename
  priors, then graph roles, then fallback to C. Fourteen tests pin it, including
  the precedence cases (`test_syllabus_filename_beats_graph_te`).
- **Absent doc types degrade correctly.** A corpus with no syllabi writes
  `status: skipped`, not an error. Verified across six workspaces.
- **Paths B–H share one artifact shape.** All six emit the same nine top-level
  keys. The contract exists in practice; it just is not written down or enforced.
- **Presence scoring is deterministic** (check 7).
- **Path A's emit is real.** A8 writes `path_a/findings.json` plus one file per
  document, and feeds `output/teachers/<unit>/LESSON-PLAN.*`. It is the model
  the other paths' emit steps should follow.
- **The workspace abstraction holds.** Live tree and `e2e/runs/<id>/` snapshots
  resolve through one code path; every API endpoint takes the same `e2e_run`
  parameter.
- **The offline suite is green and now gated.** 15 tests, 84 assertions, in CI.

---

## 6. Recommended order

- [x] **0. Add the import check** (check 10). Landed — `test_pipeline_stages.py` plus
      `StageBrokenError`. Catches both dead stages and stops the class recurring.
- [x] **1. Decide §0/§1.** Decided and built: Paths B–H are the single non-lesson
      scorer, the artifact rung rolls them up (§0.1).
- [x] **2. Freeze the findings contract** (checks 2, 3, 5). Done — schema, Path A
      conformance, and write-time validation through one shared helper. §2.5 and §2.6
      landed first, as planned, so the vocabulary was settled before anything was pinned.
- [x] **3. Golden-pin findings** (check 9), `generated_at` normalized. Verified by
      simulating a rating regression: the diff names the path, the step, the document
      count, and the direction, and `--check` exits 1 so CI fails.
- [x] **4. Assert stage outputs** — done. `STAGE_EXPECTED_OUTPUTS` declares an artifact
      for all 14 stages; `StageOutputError` fails the run when one is absent after the
      stage ran. A stage that never ran, or that legitimately writes `status: skipped`,
      still passes.
- [x] **5. Fix the handoff schemas** (check 6). Done — enums cover A–H and a real
      emitted handoff is validated against them. Check 5 (a `validate_route_map()`
      in `schema_validate.py`) is still open and belongs with step 2's schema work.
      `workflow-handoff.json` now has a consumer in the test suite, which settles
      §2.1's wire-or-delete question in favour of keeping it.
- [x] **6. Add `test_path_a_lesson_plan.py`** (check 8) — done, 4 tests in CI.

**All ten checks pass. The structure is frozen; the next change should be a tuning
change.** The one piece of follow-up work is coverage rather than correctness: re-run
`ap-csp-2026`, `bluebonnet-math-2026`, `lab-dallas-career`, and
`pathful-planning-guides-2026` through the router so their findings can be regenerated
and pinned like the other eight.
- [x] **7. Sweep the docs** (§4) — done, including eight files beyond the original list.

Steps 2 and 3 are still the ones that convert "we think data flows consistently" into
"CI fails if it does not." Step 2 is now the critical path: §2.5 is a live correctness
bug that a patch is currently masking.

## 11. Presence was matched as a substring — PARTIALLY RESOLVED 2026-08-09

The first thing found by actually reading a lens's output against its documents.
Every path tested checklist keywords with `keyword in text.lower()`. A substring
match ignores word edges, so on the two culinary syllabi:

| keyword | matched | reported |
| --- | --- | --- |
| `PPE` | Cli**ppe**rs, ha**ppe**n, dro**ppe**d | lab safety rules present |
| `credit` | extra credit | course credit stated |
| `cover` | recipe **cover** to protect from food | TEKS coverage claim |
| `sequence` | Con**sequence**s | scope and sequence present |
| `cte` | expe**cte**d, prote**cte**d | document is CTE-shaped |

The last one disabled a feature outright: `_doc_has_cte_signals` decides whether the
optional safety/WBL/acknowledgment fields are required, and because almost every
document contains "expected", the soft gate never once softened anything.

These are all false *positives*, which is the dangerous direction. A false MISSING
is noise a teacher ignores; a false PRESENT is a gap the audit never reports, and
presence feeds the rung rollups, so it becomes a passing grade nobody questions.

Fixed for Path G by `workflows/keyword_match.py`: boundary-anchored matching, an
optional trailing plural, punctuation-shaped keywords matched literally, whitespace
inside a phrase allowed to stretch (extraction splits runs — "A bsences"), and an
`exclude:` list for the residue, since "extra credit" contains "credit" at a clean
boundary. Citations now quote the matched sentence rather than the head of the
excerpt, which is what makes a rating reviewable at all.

Path G also now reads the source document for G2–G7 instead of the Layer 0 ledger.
Layer 0 excerpting is tuned for lesson plates and samples a syllabus rather than
covering it; the practicum syllabus lost its whole header block, so instructor,
email, phone and room read MISSING on a document that states all four on line
three. G1 still reports the ledger, because G1 is a claim about Layer 0 coverage.
`evidence_base` in the findings records which text was read.

**Still open for the other seven paths.** 60 keywords across all eight checklists
currently fire only as substrings on the real corpora — `teach` inside "teacher",
`unit` inside "opport**unit**y", `ELPS` inside "h**elps**", `how` inside "s**how**",
`rate` inside "accu**rate**". This is not a mechanical switch, which is why it was
not done here: some of those keywords are deliberate stems (`facilitat`, `vocab`,
`scaffold`) that a boundary would break, and telling the two apart needs a per-
keyword reading of each checklist against its corpus. Doing it path by path also
keeps each ratings shift reviewable on its own.

Field-level golden pinning landed alongside this, and was prompted by it: the Path G
correction turned two false PRESENTs into MISSING and one false MISSING into PRESENT,
yet the step rolled up to PARTIAL either way and the pin showed a single changed cell.
Tuning happens at the field, so the pin records the field.
