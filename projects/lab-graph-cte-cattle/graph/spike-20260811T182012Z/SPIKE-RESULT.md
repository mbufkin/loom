# CTE graph sort spike — RESULT (two units)

**Overall:** PASS
**Units:** `breeds-of-livestock-cattle`, `external-anatomy-of-livestock-terms-terminology`

## Anti-mangle / contract checks

| Check | Result |
|-------|--------|
| `two_units_present` | PASS |
| `breeds-of-livestock-cattle__lesson_nodes_ge_1` | PASS |
| `breeds-of-livestock-cattle__view_lesson_plan_is_lesson_plan` | PASS |
| `breeds-of-livestock-cattle__view_lesson_plan_path_A` | PASS |
| `external-anatomy-of-livestock-terms-terminology__lesson_nodes_ge_1` | PASS |
| `external-anatomy-of-livestock-terms-terminology__view_lesson_plan_is_lesson_plan` | PASS |
| `external-anatomy-of-livestock-terms-terminology__view_lesson_plan_path_A` | PASS |
| `no_teacher_edition_role` | PASS |
| `lesson_ids_namespaced` | PASS |
| `no_cross_unit_edges` | PASS |
| `no_foreign_lesson_attachments` | PASS |

## Course counts

- Units: 2
- Lesson nodes: 13
- Materials: 22
- Assessments: 5
- Edges: 98

## Unit `breeds-of-livestock-cattle`

**Title:** Breeds of Livestock — Cattle
**Spine:** 7 — Class 1 — Dairy Breeds, Class 2 — Asian & African Breeds, Class 3 — British Breeds, Class 4 — Continental Breeds, Class 5 — American Breeds, Class 6 — Build a Breed Project, Class 7 — Final Assessment

| source_file | artifact_kind | Path |
|-------------|---------------|------|
| `023-breeds-of-livestock-cattle__action-plan.html` | `other` | **C** |
| `023-breeds-of-livestock-cattle__activity-career-connections.html` | `student_practice` | **E** |
| `023-breeds-of-livestock-cattle__activity-cattle-breeds-flashcards.html` | `student_practice` | **E** |
| `023-breeds-of-livestock-cattle__check-for-understanding-1-dairy-breeds.html` | `assessment` | **B** |
| `023-breeds-of-livestock-cattle__final-assessment-answer-key.html` | `assessment` | **B** |
| `023-breeds-of-livestock-cattle__final-assessment.html` | `assessment` | **B** |
| `023-breeds-of-livestock-cattle__horizontal-alignments.html` | `standards_pacing` | **F** |
| `023-breeds-of-livestock-cattle__key-concepts.html` | `teacher_support` | **D** |
| `023-breeds-of-livestock-cattle__project-build-a-breed.html` | `student_practice` | **E** |
| `023-breeds-of-livestock-cattle__view-lesson-plan.html` | `lesson_plan` | **A** |
| `023-breeds-of-livestock-cattle__vocabulary-handout.html` | `student_practice` | **E** |

### Lesson nodes

- `lesson:breeds-of-livestock-cattle:l1` — Class 1 — Dairy Breeds
- `lesson:breeds-of-livestock-cattle:l2` — Class 2 — Asian & African Breeds
- `lesson:breeds-of-livestock-cattle:l3` — Class 3 — British Breeds
- `lesson:breeds-of-livestock-cattle:l4` — Class 4 — Continental Breeds
- `lesson:breeds-of-livestock-cattle:l5` — Class 5 — American Breeds
- `lesson:breeds-of-livestock-cattle:l6` — Class 6 — Build a Breed Project
- `lesson:breeds-of-livestock-cattle:l7` — Class 7 — Final Assessment

## Unit `external-anatomy-of-livestock-terms-terminology`

**Title:** External Anatomy of Livestock: Terms & Terminology
**Spine:** 6 — Class 1 — Anatomical Terms of Location, Class 2 — External Components of Livestock, Class 3 — Livestock External Anatomy Diagrams, Class 4 — Labeling Activities & Project Preparation, Class 5 — Continued Labeling & Presentation Work, Class 6 — Assessment & Project Sharing

| source_file | artifact_kind | Path |
|-------------|---------------|------|
| `027-external-anatomy-of-livestock-terms-terminology__action-plan.html` | `lesson_plan` | **A** |
| `027-external-anatomy-of-livestock-terms-terminology__activity-career-connections.html` | `student_practice` | **E** |
| `027-external-anatomy-of-livestock-terms-terminology__activity-labeling-a-boar.html` | `student_practice` | **E** |
| `027-external-anatomy-of-livestock-terms-terminology__assessment-answer-key.html` | `assessment` | **B** |
| `027-external-anatomy-of-livestock-terms-terminology__assessment.html` | `assessment` | **B** |
| `027-external-anatomy-of-livestock-terms-terminology__horizontal-alignments.html` | `standards_pacing` | **F** |
| `027-external-anatomy-of-livestock-terms-terminology__key-concepts.html` | `student_practice` | **E** |
| `027-external-anatomy-of-livestock-terms-terminology__ngss-correlation.html` | `standards_pacing` | **F** |
| `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html` | `other` | **C** |
| `027-external-anatomy-of-livestock-terms-terminology__view-lesson-plan.html` | `lesson_plan` | **A** |
| `027-external-anatomy-of-livestock-terms-terminology__vocabulary-handout.html` | `student_practice` | **E** |

### Lesson nodes

- `lesson:external-anatomy-of-livestock-terms-terminology:l1` — Class 1 — Anatomical Terms of Location
- `lesson:external-anatomy-of-livestock-terms-terminology:l2` — Class 2 — External Components of Livestock
- `lesson:external-anatomy-of-livestock-terms-terminology:l3` — Class 3 — Livestock External Anatomy Diagrams
- `lesson:external-anatomy-of-livestock-terms-terminology:l4` — Class 4 — Labeling Activities & Project Preparation
- `lesson:external-anatomy-of-livestock-terms-terminology:l5` — Class 5 — Continued Labeling & Presentation Work
- `lesson:external-anatomy-of-livestock-terms-terminology:l6` — Class 6 — Assessment & Project Sharing


## Path score (gold)

**FAIL** — 18/22 (see `PATH-SCORE.md`)

- FAIL `023-breeds-of-livestock-cattle__action-plan.html`: expected `student_practice→E`, got `other→C`
- FAIL `023-breeds-of-livestock-cattle__key-concepts.html`: expected `student_practice→E`, got `teacher_support→D`
- FAIL `027-external-anatomy-of-livestock-terms-terminology__action-plan.html`: expected `student_practice→E`, got `lesson_plan→A`
- FAIL `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html`: expected `student_practice→E`, got `other→C`
