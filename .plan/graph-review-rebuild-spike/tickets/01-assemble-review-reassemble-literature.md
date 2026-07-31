---
type: research
blocked_by: []
claimed_by:
claimed_at:
assets: [".plan/graph-review-rebuild-spike/assets/01-assemble-review-reassemble.md"]
---

# Assemble → review → reassemble literature

## Question

What published patterns (standards, peer-reviewed, or widely adopted edtech practice) describe building a **provisional** instructional organization graph, running **document/content review**, then **revising the graph** from what review found — and what do they imply for loom’s spike loop?

## Answer

No single standard brands “provisional HAS-PART → review → rebuild,” but several independent published patterns converge on that loop: **draft an organization over a stable materials inventory, review content/alignment against the map, then revise belonging and structure from findings.** Full source brief: [.plan/graph-review-rebuild-spike/assets/01-assemble-review-reassemble.md](../assets/01-assemble-review-reassemble.md).

The strongest technical warrant is **IMS/1EdTech Content Packaging and SCORM CAM**: organizations (TOC / aggregation trees) are separate from resources (file inventory); multiple organizations may rearrange the same resources without touching physical files. **Learning Commons** supplies the curriculum `hasPart` schema Loom already targets. The review→revise half is mainstream edtech: **Jacobs curriculum mapping** (draft/diary map → multi-step review → immediate vs longer revision), **UbD** (draft unit → design-standards peer review → edit; gap-finding via backward maps), **Quality Matters** (score design → amend course → re-check), and **ADDIE** as an iterative evaluate→redesign cycle (Bates). Harden’s AMEE Guide 21 frames mapping as development infrastructure, not a one-shot inventory.

Relative to `docs/GRAPHING.md`: the doc already cites LC / SCORM / UbD and prefers graphing before the router so peer typing does not freeze bad structure. This research **extends** that one-shot assemble into an explicit CQI loop — provisional organization → Path/document review → rebuilt organization — while keeping Materials inventory stable across rebuilds.

**Implications for the spike**

- Provisional HAS-PART is legitimate practice (draft map / first org); rebuild is expected, not failure.
- Keep Material / L0 inventory stable; rebuild revises organization, spans, and edges (`hasPart`, `describes`, `uses`, etc.).
- Review findings must be allowed to change belonging — not only annotate a frozen Path A/B/C peer map.
- Treat gaps/`unresolved`/`referenced_missing` as first-class; distinguish immediate edge fixes from HITL “needs research” tickets (Jacobs).
- Gate provisional on knownness/inventory; leave pedagogy quality to Path review; merge structural discoveries on rebuild (GRAPHING.md invariant 5 + UbD stages).
