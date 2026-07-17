# Curriculum dataset status

Each row is **data** for the Loom program (`./run-audit <id>`).  
Maturity = how complete generated artifacts are — not a separate code path.

| Dataset id | Tier | Layer 0 | Layer 1 | Notes |
|------------|------|---------|---------|-------|
| `dallas-career-2026` | **Golden** | Yes | Yes | 18 CTE units; acceptance / demo / MVP |
| `oklahoma-ag-orientation-2026` | Active | — | — | Public OK CareerTech Orientation to Ag (6 units); sequential calendar |
| `region10-career-college-2026` | Active | Yes | Yes | Region 10 career/college |
| `ap-csp-2026` | Stress | Yes | **Blocked** | Layer 0 OK; Layer 1 ORGANIZE exceeds 65k ctx on single CED (~113k) — see dataset README; deferred roadmap |
| `openscied-6` | Experiment | — | — | Pairs with `experiments/openscied/` |
| `_fixtures/ingest-pilot` | Fixture | — | — | Ingest smoke only |
| `_fixtures/ingest-test` | Fixture | — | — | Ingest smoke only |
| `_template` | Template | — | — | Copy to start a new dataset |

**Tiers:** Golden = regression bar · Active = real work · Stress = hard inputs · Experiment = alternate code · Fixture = CI/smoke · Template = blank shelf slot.

**MVP scope:** multi-document course packs (golden Dallas). Huge single-framework PDFs are Layer 0 stress only until Layer 1 chunking ships (`docs/roadmap.md`).
