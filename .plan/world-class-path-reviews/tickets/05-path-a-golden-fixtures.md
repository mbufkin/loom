---
type: grilling
blocked_by: []
claimed_by: cursor
claimed_at: 2026-08-04T00:18:47Z
resolved_at: 2026-08-04T00:20:07Z
assets:
  - ../assets/05-path-a-golden-fixtures.md
---

# Path A golden fixtures for usefulness tests

## Question

Which **fixed documents / units** (Dallas golden, and optionally a small Bluebonnet slice) are the proving set for “a human trusts this Path A output,” and what makes a fixture in or out of that set?

## Answer

**Dallas-only trio** (no Bluebonnet): see [05-path-a-golden-fixtures](../assets/05-path-a-golden-fixtures.md).

| Role | Unit |
|------|------|
| Strong | `engineering` |
| Mixed | `teaching-and-training` |
| Weak | `family-community` |

**IN:** fixed Dallas unit plate (`output/teachers/<unit>/LESSON-PLAN.*`) + Path A one-pager scored by **all** hard gates (C1–C4 + X5–X7 + G8).

**OUT:** Bluebonnet; project-level `findings.json` alone; full 18-unit corpus; units outside the trio; observation rubrics; invented lesson drafts.

**Note:** today’s `path_a/findings.json` is project-scoped — usefulness fixtures pin **unit plates**, not that JSON blob as the human trust artifact.
