# Model decisions — Pass 1 type (why this kind?)

Grok run: `spike-20260811T171256Z`
Local run: `spike-20260811T182012Z`

Each Pass 1 call is fresh context. Path is Python (`kind→letter`), not the model.

## Diffs (local ≠ grok)

### `023-breeds-of-livestock-cattle__action-plan.html`

| | kind→Path | citation | notes |
|---|---|---|---|
| **Grok** | `lesson_plan→A` | `023-breeds-of-livestock-cattle__action-plan.html-e1` | Multi-class plan with objectives, EQs, and sequenced steps across 7 classes. |
| **Local** | `other→C` | `023-breeds-of-livestock-cattle__action-plan.html-e1` | teacher-facing lesson overview |

- Grok excerpt_head: Lesson Plan Breeds of Livestock: Cattle  Lesson Overview Objectives: 1. To identify breeds of cattle.
- Local excerpt_head: Lesson Plan: Identify cattle breeds and their characteristics across multiple classes.

- Local: `kind_fallback=true` (invalid kind string normalized to `other`)

### `023-breeds-of-livestock-cattle__key-concepts.html`

| | kind→Path | citation | notes |
|---|---|---|---|
| **Grok** | `student_practice→E` | `023-breeds-of-livestock-cattle__key-concepts.html-e1` | Fill-in-the-blank key-concepts guided notes for students, not a teacher lesson plan. |
| **Local** | `teacher_support→D` | `023-breeds-of-livestock-cattle__key-concepts.html-e1` | lesson plan content |

- Grok excerpt_head: Key Concepts Breeds of Livestock: Cattle Key Concepts  Dairy Breeds Essential Questions 1.
- Local excerpt_head: Overview of cattle breeds, their origins, traits, and uses as key concepts for instruction.

### `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html`

| | kind→Path | citation | notes |
|---|---|---|---|
| **Grok** | `student_practice→E` | `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html-e1` | Student project sheet: group presentation directions, peer eval form, and scoring rubric. |
| **Local** | `other→C` | `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html-e1` | short |

- Grok excerpt_head: Project Livestock Instructor  Project Overview: You will create a presentation to teach
- Local excerpt_head: Project Overview: Create presentation on external anatomy of assigned livestock animal

- Local: `kind_fallback=true` (invalid kind string normalized to `other`)

## All Pass 1 decisions (local)

| source_file | kind→Path | notes | excerpt_head |
|---|---|---|---|
| `023-breeds-of-livestock-cattle__action-plan.html` | `other→C` ⚠fallback | teacher-facing lesson overview | Lesson Plan: Identify cattle breeds and their characteristics across multiple classes. |
| `023-breeds-of-livestock-cattle__activity-career-connections.html` | `student_practice→E` | short | Career interview questions for students to answer after watching videos. |
| `023-breeds-of-livestock-cattle__activity-cattle-breeds-flashcards.html` | `student_practice→E` | student activity | Create flashcards for cattle breeds, including name, sketch, origin, traits, uses; then quiz peers. |
| `023-breeds-of-livestock-cattle__check-for-understanding-1-dairy-breeds.html` | `assessment→B` | short | Check for Understanding Dairy Breeds Directions: Answer the following questions. |
| `023-breeds-of-livestock-cattle__final-assessment-answer-key.html` | `assessment→B` | short | Match the following breeds to their physical descriptions. |
| `023-breeds-of-livestock-cattle__final-assessment.html` | `assessment→B` | short | Final Assessment Breeds of Livestock: Cattle Final Assessment Directions: Answer the following questions. |
| `023-breeds-of-livestock-cattle__horizontal-alignments.html` | `standards_pacing→F` | short | Breeds of Livestock: Cattle Horizontal Alignments – Core-Subject Areas and Foundations |
| `023-breeds-of-livestock-cattle__key-concepts.html` | `teacher_support→D` | lesson plan content | Overview of cattle breeds, their origins, traits, and uses as key concepts for instruction. |
| `023-breeds-of-livestock-cattle__project-build-a-breed.html` | `student_practice→E` | short | Project Build a Breed: Create your own cattle breed suited to local climate and geography. |
| `023-breeds-of-livestock-cattle__view-lesson-plan.html` | `lesson_plan→A` | comprehensive multi‑class lesson plan covering cattle breed analysis and project work | Lesson Overview: Cattle Breeds – Objectives & Class Structure |
| `023-breeds-of-livestock-cattle__vocabulary-handout.html` | `student_practice→E` | short | Vocabulary terms for cattle breeds and related concepts. |
| `027-external-anatomy-of-livestock-terms-terminology__action-plan.html` | `lesson_plan→A` | short | Action Plan for External Anatomy Terminology Lesson |
| `027-external-anatomy-of-livestock-terms-terminology__activity-career-connections.html` | `student_practice→E` | short | Career interview worksheet with guided questions for students. |
| `027-external-anatomy-of-livestock-terms-terminology__activity-labeling-a-boar.html` | `student_practice→E` | short | Label the external anatomy of a boar using the given terms. |
| `027-external-anatomy-of-livestock-terms-terminology__assessment-answer-key.html` | `assessment→B` | short | Final Assessment External Anatomy of Livestock: Terms & Terminology Assessment Answer Key Directions: Answer the followi |
| `027-external-anatomy-of-livestock-terms-terminology__assessment.html` | `assessment→B` | final quiz on livestock anatomy terms | Final Assessment External Anatomy of Livestock: Terms & Terminology Assessment |
| `027-external-anatomy-of-livestock-terms-terminology__horizontal-alignments.html` | `standards_pacing→F` | short | Horizontal Alignments External Anatomy of Livestock: Terms & Terminology |
| `027-external-anatomy-of-livestock-terms-terminology__key-concepts.html` | `student_practice→E` | short | Key Concepts External Anatomy of Livestock: Terms & Terminology |
| `027-external-anatomy-of-livestock-terms-terminology__ngss-correlation.html` | `standards_pacing→F` | short | Common Core Standards Alignments External Anatomy of Livestock: Terms & Terminology NGSS Correlations |
| `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html` | `other→C` ⚠fallback | short | Project Overview: Create presentation on external anatomy of assigned livestock animal |
| `027-external-anatomy-of-livestock-terms-terminology__view-lesson-plan.html` | `lesson_plan→A` | comprehensive lesson with multiple class activities and assessment | Lesson Plan: External Anatomy of Livestock – objectives to identify and analyze animal parts. |
| `027-external-anatomy-of-livestock-terms-terminology__vocabulary-handout.html` | `student_practice→E` | short | Vocabulary External Anatomy of Livestock Terms & Terminology Handout |

## All Pass 1 decisions (grok)

| source_file | kind→Path | notes | excerpt_head |
|---|---|---|---|
| `023-breeds-of-livestock-cattle__action-plan.html` | `lesson_plan→A` | Multi-class plan with objectives, EQs, and sequenced steps across 7 classes. | Lesson Plan Breeds of Livestock: Cattle  Lesson Overview Objectives: 1. To identify breeds of cattle. |
| `023-breeds-of-livestock-cattle__activity-career-connections.html` | `student_practice→E` | Student handout: watch career interviews and answer guided questions; independent practice, not a lesson plan. | Career Connections Directions: view the required number of interviews and answer the questions. |
| `023-breeds-of-livestock-cattle__activity-cattle-breeds-flashcards.html` | `student_practice→E` | Student-facing flashcard activity with directions, peer quiz, and short reflection/submit. | Cattle Breeds Flashcards Activity Overview: You will develop a set of flashcards |
| `023-breeds-of-livestock-cattle__check-for-understanding-1-dairy-breeds.html` | `assessment→B` | Formative CFU quiz: MC, T/F, matching on dairy breeds; not a lesson plan. | Check for Understanding Dairy Breeds Check for Understanding Directions: Answer the following questions. |
| `023-breeds-of-livestock-cattle__final-assessment-answer-key.html` | `assessment→B` | Final assessment answer key with scored quiz items (match, T/F, MC). | Final Assessment Breeds of Livestock: Cattle Final Assessment Answer Key |
| `023-breeds-of-livestock-cattle__final-assessment.html` | `assessment→B` | Final test: matching, T/F, MC, select-all; not a lesson plan. | Final Assessment Breeds of Livestock: Cattle Final Assessment |
| `023-breeds-of-livestock-cattle__horizontal-alignments.html` | `standards_pacing→F` | Title and body are cross-curricular horizontal alignments (LA/SS/Science), not a lesson. | Breeds of Livestock: Cattle Horizontal Alignments Core-Subject Area: Language Arts |
| `023-breeds-of-livestock-cattle__key-concepts.html` | `student_practice→E` | Fill-in-the-blank key-concepts guided notes for students, not a teacher lesson plan. | Key Concepts Breeds of Livestock: Cattle Key Concepts  Dairy Breeds Essential Questions 1. |
| `023-breeds-of-livestock-cattle__project-build-a-breed.html` | `student_practice→E` | Student project sheet: directions, deliverables, gallery walk, and scoring rubric—not a teacher lesson plan. | Project Build a Breed  Project Overview: You will create your own crossbred or composite cattle breed |
| `023-breeds-of-livestock-cattle__view-lesson-plan.html` | `lesson_plan→A` | Teacher-facing multi-class plan with goals, objectives, sequenced steps, hooks, and CFUs. | Lesson Plan Breeds of Livestock: Cattle  Lesson Overview Media: Microsoft ® PowerPoint ® |
| `023-breeds-of-livestock-cattle__vocabulary-handout.html` | `student_practice→E` | Student vocab handout: cattle breed terms with definitions; not a lesson plan or assessment. | Vocabulary Breeds of Livestock: Cattle Vocabulary Handout |
| `027-external-anatomy-of-livestock-terms-terminology__action-plan.html` | `lesson_plan→A` | Multi-class Action Plan with objectives, EQs, and Class 1–6 instructional sequence. | Action Plan External Anatomy of Livestock: Terms & Terminology Lesson Overview Objectives |
| `027-external-anatomy-of-livestock-terms-terminology__activity-career-connections.html` | `student_practice→E` | Student activity handout: watch career interviews and answer prompt questions; independent practice, not a lesson plan. | Career Connections Directions: view the required number of interviews and answer the questions. |
| `027-external-anatomy-of-livestock-terms-terminology__activity-labeling-a-boar.html` | `student_practice→E` | Student labeling activity with word bank; independent practice handout, not a lesson plan or test. | Activity Labeling a Boar — practice locating external anatomical features; word bank labels |
| `027-external-anatomy-of-livestock-terms-terminology__assessment-answer-key.html` | `assessment→B` | Final assessment MCQs labeled Assessment Answer Key; quiz/test artifact. | Final Assessment External Anatomy of Livestock: Terms & Terminology Assessment Answer Key |
| `027-external-anatomy-of-livestock-terms-terminology__assessment.html` | `assessment→B` | Labeled final assessment; 10 MCQs with directions to answer. | Final Assessment External Anatomy of Livestock: Terms & Terminology Assessment |
| `027-external-anatomy-of-livestock-terms-terminology__horizontal-alignments.html` | `standards_pacing→F` | Title and body are core-subject horizontal alignments (Math/ELA/Science), not a lesson. | Horizontal Alignments External Anatomy of Livestock: Terms & Terminology |
| `027-external-anatomy-of-livestock-terms-terminology__key-concepts.html` | `student_practice→E` | Guided key-concepts notes with blanks/EQs; student vocab handout, not a lesson plan or quiz. | Key Concepts External Anatomy of Livestock: Terms & Terminology Key Concepts |
| `027-external-anatomy-of-livestock-terms-terminology__ngss-correlation.html` | `standards_pacing→F` | NGSS correlation/alignment map only; lists HS-LS strands and PEs, not a lesson. | Common Core Standards Alignments External Anatomy of Livestock: Terms & Terminology NGSS Correlations |
| `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html` | `student_practice→E` | Student project sheet: group presentation directions, peer eval form, and scoring rubric. | Project Livestock Instructor  Project Overview: You will create a presentation to teach |
| `027-external-anatomy-of-livestock-terms-terminology__view-lesson-plan.html` | `lesson_plan→A` | View Lesson Plan: 6-class sequence with objectives, bell ringers, steps, exit tickets. | Lesson Plan External Anatomy of Livestock: Terms & Terminology |
| `027-external-anatomy-of-livestock-terms-terminology__vocabulary-handout.html` | `student_practice→E` | Student vocab handout: livestock anatomy terms with definitions; not a lesson or assessment. | Vocabulary External Anatomy of Livestock: Terms & Terminology Vocabulary Handout |

## Pass 2 connect (diff docs only)

### `023-breeds-of-livestock-cattle__action-plan.html`

- Grok covers: `[1, 2, 3, 4, 5, 6, 7]` — Action Plan spans Classes 1–7 with per-class steps, EQs, and activities across the full cattle breeds pack.
- Local covers: `[1]` — short

### `023-breeds-of-livestock-cattle__key-concepts.html`

- Grok covers: `[1, 2, 3, 4, 5]` — Fill-in key concepts span dairy, Asian/African, British, continental, and American breed sections matching Classes 1–5; no Build a Breed or final-assessment content.
- Local covers: `[1, 2, 3, 4, 5]` — reference for lessons 1‑5

### `027-external-anatomy-of-livestock-terms-terminology__project-livestock-instructor.html`

- Grok covers: `[4, 5, 6]` — Multi-day Livestock Instructor group presentation project; spine labels explicitly place it in Classes 4–6. Includes peer eval/rubric but is practice/project work, not the unit assessment artifacts.
- Local covers: `[4]` — short

