# When instructional structure should be revised after review

**Ticket:** `tickets/03-graph-revision-after-review.md`  
**Question:** What do UbD, evidence-centered design, content-packaging practice, and educational KG literature say about **when** structure (lesson membership, assessment attach, material roles) should be revised **after** humans or review passes inspect documents — vs locking the org tree up front?

---

## Verdict

Across these traditions, **document/resource inventory can be provisionally assembled early, but organizational structure is not locked until after inspection against purpose, evidence, and role**. Lesson membership, assessment attach, and material roles are exactly the kind of edges that review is meant to invalidate and rebuild. What may stabilize early is the **resource set / atoms** (files, spans, claims about desired results)—not the HAS-PART / attach / role graph that places them.

---

## 1. Understanding by Design (UbD)

### What the sources say

Wiggins & McTighe’s UbD framework uses three-stage **backward design**: (1) Desired Results, (2) Assessment Evidence, (3) Learning Plan. Alignment is definitional: Stage 1 content/understandings must be what is assessed in Stage 2 and taught in Stage 3 ([ASCD UbD White Paper, 2012](https://files.ascd.org/staticfiles/ascd/pdf/siteASCD/publications/UbD_WhitePaper0312.pdf)).

Key practice points from that white paper and companion materials:

- **Regular review against design standards** is an explicit UbD habit: “Regularly reviewing units and curriculum against design standards enhances curricular quality and effectiveness” (same white paper; also [UbD in a Nutshell](https://jaymctighe.com/wp-content/uploads/2011/04/UbD-in-a-Nutshell.pdf)).
- UbD is framed as **continuous improvement**: student/performance results and design reviews inform adjustments—not a one-pass freeze of the unit tree.
- Stage 2 review questions ask whether assessments cover Stage 1 goals or whether important goals are “slipping through the cracks” (white paper Stage 2 alignment check)—i.e., **assessment attach is an after-draft revision target**.
- Stage 3 asks whether learning events align with Stage 1 goals and Stage 2 assessments, and how the unit is sequenced—i.e., **lesson membership / learning-plan structure is revised for alignment**, not authored once and sealed.
- The published [UbD Design Standards 2.0](https://jaymctighe.com/downloads/UbD-Design-Standards-2.0.pdf) are peer-review criteria spanning Stage 1–3 plus overall coherence (standards 8–14 specifically cover valid assessment evidence, sufficiency of opportunities to show achievement, learning events for acquire/meaning/transfer, WHERETO, and three-stage alignment). Peer review → revise is the intended loop.

### Timing implication

| Stabilize earlier | Revise after review |
|-------------------|---------------------|
| Desired results / unit priorities (Stage 1 “north star”) | Assessment evidence placement under goals (Stage 2) |
| | Learning events, sequence, and which lessons carry which activities (Stage 3) |
| | Cross-stage coherence when peer review finds misalignment |

UbD does **not** endorse locking the learning-plan org tree before Stage 2/3 and design-standards review. It does endorse locking *intent* (what success looks like) before finalizing *structure of evidence and instruction*.

---

## 2. Evidence-Centered Design (ECD)

### What the sources say

Mislevy and colleagues organize assessment design into layers—commonly: domain analysis → domain modeling → conceptual assessment framework (CAF: Student / Evidence / Task models) → implementation → delivery ([Mislevy & Riconscente, PADI TR9](https://padi.sri.com/downloads/TR9_ECD.pdf); [Riconscente, Mislevy & Corrigan overview](https://doi.org/10.1016/j.pse.2014.11.003)).

Authoritative timing claims:

- “Although the layers might suggest a sequence in the design process, **good practice typically is characterized by cycles of iteration and refinement both within and across layers**” (PADI TR9).
- “It is **less costly to make changes in the early layers** (Domain Analysis and Modeling)… than… after incurring the expense of item acquisition” — yet “**Problems encountered in a later layer may force a return to an earlier layer**” (Riconscente et al., *Psicología Educativa* ECD introduction).
- Concrete reverse-flow example: failed task development to obtain required evidence can force revision of claims/constraints—not stubborn adherence to the first CAF wiring.
- Applied ECD pipelines (e.g., Shute et al. on game-based assessment) treat evaluation/debugging phases as loops that revisit earlier model decisions when later steps reveal problems ([IJT paper](https://myweb.fsu.edu/vshute/pdf/IJT.pdf)).

### Timing implication

| Stabilize earlier (cheaper) | Revise after inspection / tryout |
|----------------------------|----------------------------------|
| Domain analysis inventory of materials & KSAs | Evidence-model wiring: which observables update which claims |
| Narrative design patterns (broad) | Task–evidence–proficiency attach when tasks fail to elicit needed evidence |
| | Student-model grain when scoring/implementation shows mismatch |

ECD treats **assessment attach and task membership as revisable blueprints**. Locking CAF structure before materials/tasks have been inspected (or before implementation feedback) is anti-pattern; provisional models are expected.

---

## 3. Content-packaging practice (IMS CP / SCORM / Common Cartridge)

### What the sources say

IMS Content Packaging separates:

- **Resources** — “A collection of references to resources. **There is no assumption of order or hierarchy**” ([IMS CP v1.1.4 Information Model](https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_infov1p1p4.html)).
- **Organizations** — zero, one, or **multiple** hierarchical views over those resources; “Different views or organizational paths through the content can be described using multiple instances of organization.”

Best-practice text states organizations exist “so that resources within the Package can be moved to create one or multiple organizations of content (such as course outlines)” ([IMS CP Best Practice](https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_bestv1p1p4.html)). SCORM packaging practice likewise treats the organization tree as a hierarchical arrangement of items over leaf resources; the same resource can sit under different items ([SCORM.com content packaging](https://scorm.com/scorm-explained/technical-scorm/content-packaging/)).

Common Cartridge profiles that organization as the navigation/folder tree used on import, while resources remain separately declared ([IMS CC 1.2 Implementation](https://www.imsglobal.org/cc/ccv1p2/imscc_profilev1p2-Implementation.html)). Field workflows (export → audit → modify TOC/content → re-audit → re-import) treat the org tree as editable after human inspection of package contents (e.g., Blackboard CXP modify/re-import practice).

### Timing implication

| Stabilize earlier | Revise after review |
|-------------------|---------------------|
| Resource inventory (files, assessments as assets) | Organization tree (lesson folders, item nesting, which item points at which resource) |
| Resource identity / identifiers | Roles implied by placement in the TOC (quiz under Day 2 vs free-floating) |
| | Alternate organizations over the same resources |

Packaging standards **encode** the lesson loom already steals: org ≠ files. They imply you may inventory resources first and **rewrite membership/roles later** without re-authoring binaries.

---

## 4. Educational knowledge-graph literature

### What the sources say

Recent EduKG construction work converges on **provisional automated structure → human/expert refinement → then publish**:

- CourseMapper (Abu-Rasheed et al., Springer AIED 2025 companion): bottom-up extraction from learning materials outperformed top-down; still, accuracy remained low enough that authors add **Human-in-the-Loop** so course creators “review and refine the EduKG **before publication**”—edit/remove/add concepts and **link them to relevant slides**, then publish the verified graph ([chapter abstract / full text](https://link.springer.com/chapter/10.1007/978-3-032-00056-9_11)).
- LLM-assisted curriculum KG work describes a four-step strategy: ontology definition → automated topic extraction → **human–AI validation** → KG construction, with teachers validating sampled semantic relations and feeding corrections back into extraction ([arXiv:2501.12300](https://arxiv.org/abs/2501.12300)).
- Adaptive curriculum-graph construction describes **iterative expert validation and refinement** of prerequisite (and related) edges after automated candidate generation ([AISE 2024](https://doi.org/10.6914/aiese.010402)).
- Curriculum KG pipelines that extract from syllabi/materials commonly recommend interactive user-in-the-loop correction of false positives/negatives before treating taxonomy membership as authoritative (e.g., KeyBERT curriculum KG discussion of refinement loops, [Information 2025](https://www.mdpi.com/2078-2489/16/7/580)).

A systematic review notes educational KGs often lack a universal locked schema and are built from heterogeneous sources (textbooks, LMS, etc.), so structure emerges under validation pressure rather than a single upfront tree ([Heliyon SLR](https://www.sciencedirect.com/science/article/pii/S2405844024014142)).

### Timing implication

| Stabilize earlier | Revise after expert/HITL review |
|-------------------|----------------------------------|
| Base ontology / node types (schema) | Membership edges (concept↔slide, lesson↔material) |
| Candidate extractions from documents | Part-whole / prerequisite / role relations |
| | Publish-ready graph only after human refine |

EduKG practice explicitly **rejects locking the org before document-informed human review**.

---

## 5. Cross-tradition synthesis

```text
                LOCK EARLY                          REVISE AFTER REVIEW
  ┌─────────────────────────────┐     ┌──────────────────────────────────┐
  │ Resource / atom inventory   │     │ Lesson membership (hasPart)      │
  │ Unit / claim priorities     │ --> │ Assessment attach under lessons  │
  │ Schema / node types         │     │ Material roles (spine, content,  │
  │                             │     │   missing, describes/uses)       │
  └─────────────────────────────┘     └──────────────────────────────────┘
         provisional assemble              review / peer / ECD tryout
                                              |
                                              v
                                         rebuild org graph
```

**Shared rule:** treat the first organization as a **hypothesis**. Inspection of documents (and of how review lanes classify them) is the evidentiary event that authorizes structural revision. Freezing the org tree at first assemble freezes the very errors these traditions exist to catch (misaligned evidence, wrong lesson nesting, wrong material roles).

---

## 6. Explicit implications for Path A / B / C–style document review

Loom today routes peer documents as Path A (`lesson_plan`), Path B (quiz/assessment), Path C (general)—see `docs/GRAPHING.md`. The spike stance is provisional HAS-PART → document review → rebuild. Literature maps cleanly onto that loop:

### Rebuild triggers after Path A (lesson / plan review)

Review discoveries that should **invalidate provisional structure** and trigger rebuild:

- One “lesson plan” file **describes** multiple days/lessons → split Lesson nodes; keep one Material with spans (`describes` edges), do not leave a single Lesson membership.
- Plan is spine, not peer content → material **role** change (`describes` / spine vs `lesson_content`).
- Activities or assessments named inside the plan but attached elsewhere (or orphaned) → **assessment/activity attach** rewrite under the correct Lesson.

Path A output is not just conformance commentary; findings about **which lessons exist and what hangs under them** are structural evidence.

### Rebuild triggers after Path B (assessment / quiz review)

- Standalone quiz that actually **belongs under** a specific lesson/day → assessment attach edge (not peer Path-B job forever).
- “Quiz” that is formative exit ticket embedded in a deck → role + membership change (embedded Assessment under Lesson; possibly Path B on a span, not a free-floating file).
- Assessment that fails Stage-2-style alignment (measures the wrong claim / wrong lesson) → re-attach or re-parent; ECD analog of revising Evidence↔Task wiring.

### Rebuild triggers after Path C (general / other review)

- Path C `other` that review retypes as lesson content, handout, game, or assessment → **material role** and often lesson membership change (classic Ag failure mode in GRAPHING.md).
- Multi-lesson deck typed as a single peer doc → break into Lesson memberships over one resource (IMS org ≠ resource).
- Referenced-but-missing materials discovered in review → add Material nodes / `uses` / `referenced_missing` without locking prior incomplete tree.

### What must *not* be frozen by first Path A/B/C dispatch

- Lesson membership, assessment attach, and material roles derived from first-pass `doc_type` routing.
- Treating Path labels as permanent peers equal to Lessons.

### What may stay stable across rebuild

- Layer-0 atoms / file identities (IMS resources).
- Unit calendars / desired-results spine once Stage-1-like priorities are agreed (UbD).
- Schema of node types (EduKG ontology), while instance edges rewrite.

### Contract sketch for ticket 06

1. Run provisional assemble (coverage-first).
2. Dispatch Path A/B/C (or node-aware successors) as **review lanes over provisional nodes**.
3. Collect structured findings: `{node_id, proposed_role, proposed_parent_lesson, evidence_spans, retype}`.
4. **Rebuild** org edges from L0 + calendars + review findings; do not patch roles only inside the router.
5. Re-gate completeness; optionally re-review only nodes whose membership/role changed.

---

## Sources (retrieved; not invented)

1. Wiggins, G., & McTighe, J. — *Understanding by Design Framework* white paper (ASCD, 2012): https://files.ascd.org/staticfiles/ascd/pdf/siteASCD/publications/UbD_WhitePaper0312.pdf  
2. McTighe — *UbD in a Nutshell*: https://jaymctighe.com/wp-content/uploads/2011/04/UbD-in-a-Nutshell.pdf  
3. McTighe — *UbD Design Standards 2.0*: https://jaymctighe.com/downloads/UbD-Design-Standards-2.0.pdf  
4. Mislevy, R. J., & Riconscente, M. — *Evidence-Centered Assessment Design: Layers, Structures, and Terminology* (PADI TR9): https://padi.sri.com/downloads/TR9_ECD.pdf  
5. Riconscente, M. M., Mislevy, R. J., & Corrigan, S. — “An introduction to the use of evidence-centered design in test development,” *Psicología Educativa* (2014): https://doi.org/10.1016/j.pse.2014.11.003  
6. Mislevy, R. J., et al. — Implications of ECD for educational testing (PADI TR17): https://padi.sri.com/downloads/TR17_EMIP.pdf  
7. IMS Global — Content Packaging v1.1.4 Information Model: https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_infov1p1p4.html  
8. IMS Global — Content Packaging Best Practice Guide: https://www.imsglobal.org/content/packaging/cpv1p1p4/imscp_bestv1p1p4.html  
9. SCORM.com — Content packaging overview: https://scorm.com/scorm-explained/technical-scorm/content-packaging/  
10. Abu-Rasheed et al. — Top-Down vs. Bottom-Up EduKG construction in CourseMapper (Springer, 2025): https://link.springer.com/chapter/10.1007/978-3-032-00056-9_11  
11. Ain et al. — LLM-Assisted KG Completion for Curriculum… (arXiv:2501.12300): https://arxiv.org/abs/2501.12300  
12. Adaptive curriculum graphs / iterative expert validation: https://doi.org/10.6914/aiese.010402  
13. Loom in-repo framing for Path A/B/C + org≠resource: `docs/GRAPHING.md`
