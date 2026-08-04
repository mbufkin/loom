# Review paths — six lenses (A–F)

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

## The six lenses

| Path | Lens | `workflow_id` | Reviews | Primary signals |
|------|------|---------------|---------|-----------------|
| **A** | Lesson | `lesson_plan` | One instructional episode (Hunter / UbD Stage 3) | Filename `lesson_plan`; **intended:** graph `Lesson` nodes (lesson-level) |
| **B** | Assessment | `quiz` | Quiz, exit ticket, answer key, summative / performance evidence | Filename quiz / exit_ticket / answer_key; graph `Assessment`; rubrics fold here when assessment-bearing |
| **C** | General feedback | `general` | Catch-all + growth queue | Weak/unknown types → `_loom_feedback.yaml` |
| **D** | Teacher support | `teacher_support` | Teacher edition / implementation / educator guide | Graph role `teacher_edition`; filename Teacher_Edition / implementation guide |
| **E** | Student practice | `student_practice` | Learn / practice / succeed / worksheet | Graph roles `learn_student`, `practice_student`; student edition / worksheet names |
| **F** | Standards & pacing | `standards_pacing` | Scope/sequence, pacing, standards overviews | Filename / program docs (scope, pacing, TEKS/ELPS summary, …) |

Path letters stay stable for UI and `route-map.json`. Deeper checklists live
*inside* a lens (A1–A8, B1–…), not as new top-level paths.

## Router (assign-path step)

`route.py` writes `layer0/route-map.json`. Downstream Path runners and Layer 1
**only** consume that map — they do not re-guess types.

### Intended assigner (cascade)

1. **Filename / regex prior** — cheap, non-authoritative (`classify_doc_type`, Layer 0 `regex_doc_type_prior`)
2. **Graph override** — when `--with-graph` has run, Material roles and Assessment / Lesson links win over “other”
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
| B | Light stub today — see [PATH-B-QUIZ.md](PATH-B-QUIZ.md); lens name is **Assessment** |
| C | Stub + feedback log — see [PATH-C-GENERAL.md](PATH-C-GENERAL.md) |
| D / E / F | Stub inventory + feedback hooks — grow checklists without adding Path G…Z |

## Feedback loop

Unknown or weak routing still appends `_loom_feedback.yaml`. Read that file
when deciding whether a recurring pattern deserves a **checklist inside** an
existing lens — not a seventh top-level path by default.

## Bluebonnet vs Dallas (why six)

- **Dallas** often has discrete `*Lesson_Plan*` files → Path A by filename works.
- **Bluebonnet** ships TE / SE / practice modules with **no** `Lesson_Plan` in
  the name → filename-only routing dumped everything to C. Graph already emits
  `Lesson` nodes and `teacher_edition` / `learn_student` roles; the router must
  use those signals so D/E (and later lesson-level A) receive real reviews.

## Related

- Pipeline stage list: [PIPELINE.md](PIPELINE.md)
- Graph belonging: [GRAPH-PHASE.md](GRAPH-PHASE.md)
- E2E review tree: [E2E.md](E2E.md)
