# Loom data flow — type split

Visual: [`DATA-FLOW.png`](DATA-FLOW.png). Plan: [`../PLAN.md`](../PLAN.md).

## Locked order

Graphing **solves the content router**. Filename is a prior (hard-wins for explicit lesson/quiz/exit/syllabus/pacing names). HAS-PART Material roles and Assessment links assign Paths D/E/B when the filename is silent — the Bluebonnet failure mode (TE/SE dumped to Path C) is closed. `route.py` still writes `layer0/route-map.json`; path runners do not re-read the graph.

```mermaid
flowchart TB
  sources[sources] --> extract[extract]
  extract --> L0[Layer0_decompose]
  L0 --> graph[Graph_HAS_PART]
  graph --> router[Loom_router]
  router --> pathA[PathA_lesson]
  router --> pathB[PathB_assessment]
  router --> pathC[PathC_general]
  router --> pathD[PathD_teacher]
  router --> pathE[PathE_practice]
  router --> pathF[PathF_pacing]
  router --> pathG[PathG_syllabus]
  router --> pathH[PathH_exit]
  pathA --> place[Place_into_units]
  pathB --> place
  pathC --> place
  pathD --> place
  pathE --> place
  pathF --> place
  pathG --> place
  pathH --> place
  place --> assemble[Unit_assemble]
  assemble --> cal[Model_calendars_year]
  cal --> plates[Plates_and_packet]
  plates --> drive[Drive]
```

## Hard rules

- Nothing goes into a unit until it has passed the Loom router (`route-map.json`).
- Graph runs **before** route (`--with-graph`) so belonging can assign D/E/B; it does not replace the route-map.
- Calendars/year are built **after** unit assemble (model), not early rollup-as-authority.
- Templates = checkboxes; blank = missing signal; never invent content.

## Paths

| Path | How it gets assigned | Doc |
|------|----------------------|-----|
| A | Filename `lesson_plan` (hard-win); graph `Lesson` is the intended lesson-level lens | [PATH-A-LESSON-PLAN.md](PATH-A-LESSON-PLAN.md) |
| B | Filename quiz/key **or** graph Assessment link | [PATH-B-QUIZ.md](PATH-B-QUIZ.md) |
| C | Nursery only — weak/unknown after filename + graph | [PATH-C-GENERAL.md](PATH-C-GENERAL.md) |
| D | Graph `teacher_edition` (TE without `Lesson_Plan` in the name) | — |
| E | Graph `learn_student` / `practice_student` | — |
| F | Filename/pacing/YAG/standards names (beats a graph TE mis-tag) | — |
| G | Filename / `doc_type` syllabus | — |
| H | Filename exit ticket (beats graph Assessment) | — |

## Handoffs

JSON Schema under [`../workflows/handoffs/`](../workflows/handoffs/).
