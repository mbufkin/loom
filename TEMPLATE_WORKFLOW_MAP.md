# Template → Workflow Placement

Checklists under `workflows/checklists/` encode a practical bar for "complete curriculum"
in Texas CTE (unit-plan structure, accommodations, CTE essentials). Partner/district
template packs are kept local and are **not** redistributed in this repository.

## Where each template lands in the Loom workflow

### Primary: Type-specific analysis templates

| Template | Loom workflow stage | What it checks |
|---|---|---|
| `unit-plan-template.txt` | **Lesson plan workflow → Layer 2 (content)** | TEKS alignment, learning target (higher-order), rationale, vocabulary, launch/intro, activities (DI/guided/independent + IEP), closure |
| `unit-plan-template.txt` (assessments section) | **Lesson plan workflow → Layer 2 (assessment)** | Summatives (up to 3) + formatives that lead to each. Checks if assessment path exists, not just if *an* assessment exists |
| `unit-plan-template.txt` (required components) | **Lesson plan workflow → Layer 2 (accommodations)** | ELPS strategies, SpEd modifications, 504 accommodations, GT extensions |
| `unit-plan-template.txt` (CTE essentials) | **Lesson plan workflow → Layer 2 (CTE-specific)** | Career development, portfolio checks, PSPR, certification prep |

### Secondary: Staff role templates (workflow context)

These define who does what in the curriculum process. Not analysis targets but workflow *metadata* — they tell Loom which role should be reviewing which output.

| Template | Loom use |
|---|---|
| `cte-coordinators.txt` | Coordinator role: "facilitate creation of common curriculum" — Loom's *router output* goes here |
| `cte-instructional-coach.txt` | Coach role: classroom observation, feedback, TEKS integration into lesson plans — Loom's *Layer 3 (gaps)* maps to what a coach would catch |
| `ccr-compliance-specialist.txt` | Compliance role: hard gate for legal/regulatory requirements |
| `cte-data-ibc-coordinator.txt` | Data role: certification tracking, IBC data — Loom's *certification prep checks* feed here |

### Tertiary: Reference / manual templates

Good to have, less directly actionable in the current workflow. Referenced but not yet automated.

| Template | Notes |
|---|---|
| `cte-advisor-manual.txt` | CTSO advisor handbook — could feed into a "club/competition" document type workflow |
| `cte-travel-binder.txt` | Travel compliance — separate domain, not curriculum auditing |
| `cte-ard-representatives.txt` | SpEd ARD support — overlaps with the accommodations section of unit-plan-template |
| `cte-academy-facilitator.txt` | Academy-level coordination |
| `cte-ag-maintenance-facilitator.txt` | Facilities — out of scope |
| `program-access-marketing-specialist.txt` | Recruitment/equity — out of scope for current Loom |

## How templates change the workflow

Currently Crystallize checks: *does a document exist in this folder slot?*

| Current Crystallize question | Loom question (with unit-plan-template) |
|---|---|
| "Does the lesson plan have TEKS listed?" | "Do the listed TEKS align with the stated learning objectives?" (direct from template) |
| "Are there assessments?" | "Is there a summative + formative path? Up to 3 summatives? Do formatives flow into summatives?" |
| "Are accommodations listed?" | "Are ELPS strategies aligned with lesson activities? SpEd / 504 / GT each addressed?" |
| "Is there career development content?" | "Career tree? Speakers? Portfolio checks? PSPR self-assessment? Certification prep planned?" |

The template doesn't just add more questions — it changes the *kind* of question. From existence checks to coherence checks.

## Next step for implementation

The `unit-plan-template.txt` sections should be parsed into structured checklists (YAML or JSON) that the route-specific workflow loads for each document type. This is Phase 2 on the roadmap — after the router exists (Phase 1) and can say "this is a lesson plan, load the lesson plan checklist."

Template → checklist conversion format:

```yaml
lesson_plan:
  unit_overview:
    - program_of_study
    - course_name
    - teks: { must_align_with_objectives: true }
  lesson_instruction:
    - learning_target: { higher_order_skills: true }
    - rationale: { real_world_connection: true }
    - duration
    - prerequisite_knowledge
    - key_vocabulary
    - launch_intro
    - instructional_activities: { di: true, guided: true, independent: true, iep_accommodations: true }
    - closure
  assessments:
    summatives: { min: 1, max: 3 }
    formatives_per_summative: { min: 1 }
  accommodations:
    - elps_strategies: { aligned_with_activities: true }
    - special_education: { modifications: true }
    - section_504: { accommodations: true }
    - gt: { extensions: true }
  cte_essentials:
    - student_career_development: { career_tree: true, speakers: true }
    - portfolio_checks
    - pspr: { self_assessment: true }
    - certification_prep
```
