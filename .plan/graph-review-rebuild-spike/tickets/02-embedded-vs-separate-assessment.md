---
type: research
blocked_by: []
claimed_by:
claimed_at:
assets:
  - ../assets/02-embedded-vs-separate-assessment.md
---

# Embedded vs separate assessment attachment

## Question

How do Learning Commons, IMS/SCORM/Common Cartridge, QTI, IEEE LOM, and related academic work treat **assessments embedded inside a lesson document** versus **separate assessment files**, and what flexible attachment rules keep belonging (Assessment ↔ Lesson) without forcing one physical form?

## Answer

Standards keep **organization/belonging** separate from **file packaging**. Learning Commons models `Assessment` as a curriculum entity associated with course / lesson grouping / lesson (via graph relations and API filters), without requiring a single physical form. IMS Content Packaging and Common Cartridge put assessments in the organization tree as items that `identifierref` resources—often QTI Learning Application Objects in their own directories—while also allowing ordinary webcontent; folder placement is usage, not forced co-file containment. QTI’s native interchange form is separate item/test resources in a content package; SCORM allows assessment interactions inside a SCO or as a separate SCO. IEEE LOM classifies educational role (`exercise` / `exam` / `self assessment`, etc.) and part-of relations (`haspart` / `ispartof` / `references`) independently of aggregation level or storage. Wiley’s learning-object literature treats this as a **granularity/combination** choice, not a mandatory layout.

**Loom provisional-graph rule-of-thumb:** embedded span **or** separate assessment file are both OK **if a Lesson↔Assessment belonging link exists**; do not force one physical form. Full citations and attachment rules: [../assets/02-embedded-vs-separate-assessment.md](../assets/02-embedded-vs-separate-assessment.md).
