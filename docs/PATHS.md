# Review paths — eight lenses (A–H)

**Product contract:** Loom does **not** invent one review path per filename.
It uses a **small set of review lenses** (paths). Filename types, Layer 0
regex priors, and graph material roles are **routing signals** that feed the
router — they are not paths themselves.

Research anchors (keep the set small):

| Source | Pattern |
|--------|---------|
| [LRMI Learning Resource Type](https://www.dublincore.org/specifications/lrmi/concept_schemes/learningResourceType/) | Broad types (lesson plan, assessment, educator curriculum guide, …); finer types `broadMatch` up |
| Learning Commons / Oak curriculum ontology | Few entities: Course → LessonGrouping → Lesson → Activity / Assessment / Material |
| UbD (Wiggins & McTighe) | Three design stages; review = alignment, not artifact sprawl |
| EdReports | 2–3 gateways of criteria, not hundreds of file-type checklists |

## The eight lenses

| Path | Lens | `workflow_id` | Reviews | Primary signals |
|------|------|---------------|---------|-----------------|
| **A** | Lesson | `lesson_plan` | One instructional episode (Hunter / UbD Stage 3) | Filename `lesson_plan`; **intended:** graph `Lesson` nodes (lesson-level) |
| **B** | Assessment | `quiz` | Quiz ↔ answer key (paired), rubric when assessment-bearing | Filename quiz / answer_key; graph `Assessment`; rubrics fold here |
| **C** | General feedback | `general` | Catch-all + growth queue | Weak/unknown types → `_loom_feedback.yaml` |
| **D** | Teacher support | `teacher_support` | Teacher edition / implementation / educator guide | Graph role `teacher_edition`; filename Teacher_Edition / implementation guide |
| **E** | Student practice | `student_practice` | Learn / practice / succeed / worksheet | Graph roles `learn_student`, `practice_student`; student edition / worksheet names |
| **F** | Standards & pacing | `standards_pacing` | Scope/sequence, pacing, YAG, standards overviews | Filename / program docs (scope, pacing, yag, TEKS/ELPS summary, …) |
| **G** | Syllabus | `syllabus` | Course syllabus / student-facing course contract | Filename / `doc_type` contains `syllabus` (typo alias `sylibuis`) |
| **H** | Exit ticket | `exit_ticket` | Standalone formative end-of-lesson check | Filename / `doc_type` `exit_ticket` |

Path letters stay stable for UI and `route-map.json`. Deeper checklists live
*inside* a lens (A1–A8, B1–…, G1–…, H1–…), not as new top-level paths —
**except** when a lens truly has a different review job (Path H split from B
because quiz↔key ≠ exit-ticket formative).

## Router (assign-path step)

`route.py` writes `layer0/route-map.json`. Downstream Path runners and Layer 1
**only** consume that map — they do not re-guess types.

### Intended assigner (cascade)

1. **Filename / regex prior** — cheap, non-authoritative (`classify_doc_type`, Layer 0 `regex_doc_type_prior`)
2. **Graph override** — when `--with-graph` has run, Material roles and Assessment / Lesson links win over “other” (exit-ticket filenames still force Path H)
3. **Model classify (planned)** — docs historically claimed a model router (full-doc); production code was filename-only. Restore as the tip of the cascade when still uncertain (`general` / low confidence)

Doctrine (Bet 0 / Bet 2): the model (or graph) reading **content** is authoritative; filename is a prior. Disagreement is itself a finding.

### Pipeline slot

```text
layer0 → graph (opt-in) → route.py → workflows/run_paths.py → layer1 …
```

Graph runs **before** route so belonging can help the router. Graph does **not**
replace `route-map.json`; it feeds it.

## Depth vs stub

| Path | Status |
|------|--------|
| A | Deep (A1–A8) — see [PATH-A-LESSON-PLAN.md](PATH-A-LESSON-PLAN.md) |
| B | Presence (B1–B6) — quiz↔key — see [PATH-B-QUIZ.md](PATH-B-QUIZ.md) |
| C | Presence nursery (C1–C5) — see [PATH-C-GENERAL.md](PATH-C-GENERAL.md) |
| D | Presence (D1–D5) — see [PATH-D-TEACHER-SUPPORT.md](PATH-D-TEACHER-SUPPORT.md) |
| E | Presence (E1–E5) — see [PATH-E-STUDENT-PRACTICE.md](PATH-E-STUDENT-PRACTICE.md) |
| F | Presence (F1–F5) — see [PATH-F-STANDARDS-PACING.md](PATH-F-STANDARDS-PACING.md) |
| G | Spec locked (G1–G9) — see [PATH-G-SYLLABUS.md](PATH-G-SYLLABUS.md); presence extractors landing |
| H | Presence (H1–H5) — see [PATH-H-EXIT-TICKET.md](PATH-H-EXIT-TICKET.md) |

## Feedback loop

Unknown or weak routing still appends `_loom_feedback.yaml`. Read that file
when deciding whether a recurring pattern deserves a **checklist inside** an
existing lens — not a new top-level path by default (Path G syllabus and
Path H exit ticket are the intentional lens additions).

## Bluebonnet vs Dallas (why A–H)

- **Dallas** often has discrete `*Lesson_Plan*` files → Path A by filename works.
- **Bluebonnet** ships TE / SE / practice modules with **no** `Lesson_Plan` in
  the name → filename-only routing dumped everything to C. Graph already emits
  `Lesson` nodes and `teacher_edition` / `learn_student` roles; the router must
  use those signals so D/E (and later lesson-level A) receive real reviews.
- **Syllabus** filenames / `doc_type=syllabus` route to Path G (G1–G9).
- **Exit tickets** route to Path H; quizzes and keys stay on Path B.

## Related

- Pipeline stage list: [PIPELINE.md](PIPELINE.md)
- Graph belonging: [GRAPH-PHASE.md](GRAPH-PHASE.md)
- E2E review tree: [E2E.md](E2E.md)
