# Arts AV — T1 gold hasPart graph

Hand-built for graphing experiments (`docs/GRAPHING.md` tier T1).

```mermaid
flowchart TB
  Unit["LessonGrouping: arts-av-technology"]
  L1["Lesson d1"]
  L2["Lesson d2"]
  L3["Lesson d3"]
  Plan["Material: lesson_plan"]
  Slides["Material: slides"]
  Notes["Material: student notes"]
  R1["Material: flyer rubric"]
  R2["Material: commercial rubric"]
  E1["Assessment: exit d1"]
  E2["Assessment: exit d2"]
  E3["Assessment: exit d3"]

  Unit --> L1
  Unit --> L2
  Unit --> L3
  Unit --> Plan
  Unit --> Slides
  Plan -.->|describes| L1
  Plan -.->|describes| L2
  Plan -.->|describes| L3
  L1 -->|spanIn| Slides
  L2 -->|spanIn| Slides
  L3 -->|spanIn| Slides
  L1 --> E1
  L2 --> E2
  L3 --> E3
  L1 --> Notes
  L2 --> R1
  L2 --> R2
```

## Placement rules encoded

| Resource | Graph role |
|----------|------------|
| Lesson plan `761e…` | Spine Material; `describes` d1–d3 |
| Slides `8943…` | Multi-day Material; Lessons `spanIn` by Day headers |
| Exit tickets (3 files) | `Assessment` `hasPart` of matching Lesson |
| Rubrics (2 files) | Materials `uses`d by d2 create activity |
| Student notes | Material used mainly on d1 |
| Flyer/commercial examples | `referenced_missing` |

## Tension to remember

Lab `calendar.yaml` still says **2** days; gold uses **3** Lessons because slides/plan mark Day 1/2/3. Graphing should surface that calendar/material disagreement rather than silently trust the thin calendar.

See `HAS-PART.json`.
