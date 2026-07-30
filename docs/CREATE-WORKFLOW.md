# Create workflow — research-backed doctrine

**Status:** operator doctrine for Create Studio (G10)  
**Related:** [NEXT-STEPS-BUILD-SPEC.md](NEXT-STEPS-BUILD-SPEC.md), [PRODUCT-OVERVIEW.md](PRODUCT-OVERVIEW.md), [STRUCTURAL-FILL.md](STRUCTURAL-FILL.md)

---

## 1. Problem this solves

Auditing tells you what is missing. Creating without a **map** turns into pin-the-tail: picking random missing exit tickets with no sense of unit, design order, or what is already present.

Professional practice does not work that way. This doc freezes Loom’s create-after-audit loop to match curriculum-mapping and UbD practice — then the UI must follow it.

---

## 2. Research anchors (what we steal)

| Source | Practice |
|--------|----------|
| **Heidi Hayes Jacobs — curriculum mapping review** | Collect map data → read for gaps/redundancies → decide **immediate** vs **needs research** → revise → next cycle. Work is **map-based**, not slot roulette. |
| **District curriculum cycles** | Needs / gap analysis → design maps → materials → implement → evaluate. Creation comes *after* the map says what is missing. |
| **UbD (Wiggins / McTighe)** | The design unit is the **unit**. Backward stages: **(1) Desired results → (2) Assessment evidence → (3) Learning plan**. Fill in that order; keep stages aligned. |
| **Map review templates** (e.g. NYSED-style) | Completeness against a fixed grid: each cell present or missing against an expected template. |

Jacobs-style triage maps to Loom’s existing decisions:

| Professional move | Loom decision |
|-------------------|---------------|
| Create / write what is missing | **Author** |
| Locate existing material (drive, vendor, prior pack) | **Pull** |
| Drop from scope / S&S for this pack | **Remove** |

---

## 3. Loom mapping

```text
Audit (today) → Unit completeness matrix → Triage (Author|Pull|Remove)
    → Fill inside unit in UbD order (Stage 1 → 2 → 3)
    → Brief → supervised draft → human save
    → (later) Promote + re-audit QA
```

### Primary workspace: unit map

Same grain as the Review heatmap and UbD. Rank units by hole size (missing count). Enter one unit; see **present and missing** together.

### Secondary lens: systemic patterns

Cross-unit role absences (e.g. exit tickets missing in 18/18 units). Use for prioritization and partner conversation — **not** the default create surface.

### Inside a unit: UbD stage bands

| Stage | Label | Loom roles (Dallas-shaped) | Why this order |
|-------|--------|----------------------------|----------------|
| **1** | Goals / plan | `lesson_plan` (+ packet completeness components when shown) | Without the plan, day materials have no design target |
| **2** | Evidence | `quiz`, `rubric`, `answer_key`, `exit_ticket` | Assess what Stage 1 claims |
| **3** | Learning | `lesson_content`, `worksheet`, `presentation`, `project_work`, `game_activity`, `lab_activity`, … | Instruction that serves Stage 1/2 |

Unknown roles land in Stage 3. Each cell is **PRESENT** (cite / `fulfilled_by`) or **MISSING** (`gap_id` for create).

### Soft gate (stage order)

Prefer Author / draft on Stage 1 holes before Stage 3. UI warns if Stage 1 still has undecided MISSING slots when opening a Stage 3 Author draft; operator may override with an explicit note. Not a hard block — directors sometimes have vendor plans already “in flight.”

---

## 4. Operator script (freeze)

1. Open project → **Units** matrix (largest holes first).  
2. Enter one unit → Stage 1 → 2 → 3 with present + missing.  
3. Triage: Author / Pull / Remove.  
4. For Author cells: brief → supervised draft → save under `projects/<id>/create/`.  
5. Later: promote to sources + re-audit (Phase 3 — not required for this doctrine UI).

Success criterion: in under a minute answer — *Which unit am I repairing? What’s already there? What’s the next design-stage hole?*

---

## 5. Non-goals

- Silent curriculum invention inside Layer 0–2  
- Equal “by element” and “by unit” as dual primaries  
- Promote / re-audit automation before the matrix UX is stable  
- Replacing Review’s unit heatmap (Create consumes audit outputs; it does not replace the auditor)

---

## 6. API surface (implementation)

| Endpoint | Role |
|----------|------|
| `GET /api/projects/{id}/create/matrix` | Unit matrix + UbD stage buckets |
| `GET /api/projects/{id}/create/tree` | Systemic patterns (roles) — secondary |
| Existing gaps / brief / draft | Unchanged create actions |

Doctrine boundary unchanged: auditor reports; create is human-supervised under `create/`.
