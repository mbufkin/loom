# CTE spike — Path score (gold expectations)

**Overall:** FAIL
**Gold docs:** 22 · PASS 18 · FAIL 4 · missing obs 0

Path = thin `kind → Path` table after Pass 1 (not a second model sort).

| Status | source_file | expected | got |
|--------|-------------|----------|-----|
| FAIL | `023-breeds-of-livestock-cattle__action-plan.html` | `student_practice→E` | `other→C` |
| PASS | `023-breeds-of-livestock-cattle__activity-career-connections.html` | `student_practice→E` | `student_practice→E` |
| PASS | `023-breeds-of-livestock-cattle__activity-cattle-breeds-flashcards.html` | `student_practice→E` | `student_practice→E` |
| PASS | `023-breeds-of-livestock-cattle__check-for-understanding-1-dairy-breeds.html` | `assessment→B` | `assessment→B` |
| PASS | `023-breeds-of-livestock-cattle__final-assessment-answer-key.html` | `assessment→B` | `assessment→B` |
| PASS | `023-breeds-of-livestock-cattle__final-assessment.html` | `assessment→B` | `assessment→B` |
| PASS | `023-breeds-of-livestock-cattle__horizontal-alignments.html` | `standards_pacing→F` | `standards_pacing→F` |
| FAIL | `023-breeds-of-livestock-cattle__key-concepts.html` | `student_practice→E` | `teacher_support→D` |
| PASS | `023-breeds-of-livestock-cattle__project-build-a-breed.html` | `student_practice→E` | `student_practice→E` |
| PASS | `023-breeds-of-livestock-cattle__view-lesson-plan.html` | `lesson_plan→A` | `lesson_plan→A` |
| PASS | `023-breeds-of-livestock-cattle__vocabulary-handout.html` | `student_practice→E` | `student_practice→E` |
| FAIL | `027-external-anatomy-of-livestock-terms-terminology__action-plan.html` | `student_practice→E` | `lesson_plan→A` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__activity-career-connections.html` | `student_practice→E` | `student_practice→E` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__activity-labeling-a-boar.html` | `student_practice→E` | `student_practice→E` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__assessment-answer-key.html` | `assessment→B` | `assessment→B` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__assessment.html` | `assessment→B` | `assessment→B` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__horizontal-alignments.html` | `standards_pacing→F` | `standards_pacing→F` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__key-concepts.html` | `student_practice→E` | `student_practice→E` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__ngss-correlation.html` | `standards_pacing→F` | `standards_pacing→F` |
| FAIL | `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html` | `student_practice→E` | `other→C` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__view-lesson-plan.html` | `lesson_plan→A` | `lesson_plan→A` |
| PASS | `027-external-anatomy-of-livestock-terms-terminology__vocabulary-handout.html` | `student_practice→E` | `student_practice→E` |

## Failures

### `023-breeds-of-livestock-cattle__action-plan.html`

- Expected: `student_practice` → Path **E**
- Got: `other` → Path **C**
- Rationale: iCEV Action Plan = student task checklist, not the lesson plan

### `023-breeds-of-livestock-cattle__key-concepts.html`

- Expected: `student_practice` → Path **E**
- Got: `teacher_support` → Path **D**
- Rationale: Student note-taking outline

### `027-external-anatomy-of-livestock-terms-terminology__action-plan.html`

- Expected: `student_practice` → Path **E**
- Got: `lesson_plan` → Path **A**
- Rationale: iCEV Action Plan = student task checklist, not the lesson plan

### `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html`

- Expected: `student_practice` → Path **E**
- Got: `other` → Path **C**
- Rationale: Student project sheet

