---
type: grilling
blocked_by: []
claimed_by: cursor
claimed_at: 2026-08-05T14:55:00Z
resolved_at: 2026-08-05T15:05:00Z
assets: []
---

# Shared path-lab harness contract

## Question

What is the **shared lab harness** every stub path must use — project layout, offline test template, ingest→Layer 0→route→path command shape, and what is committed vs gitignored — so B–H–F–D–E–C labs stay comparable and Path G’s culinary lab is the pattern, not a one-off?

## Answer

**Shared harness (locked):**

| Concern | Contract |
|---------|----------|
| **Lab project** | One persistent project per path: `projects/lab-<lens>-path-<letter>/` (e.g. `lab-assessment-path-b`), mirroring `lab-culinary-syllabus` layout (`manifest.yaml`, `sources/.gitkeep`, `school-calendar.yaml`, `units/`, `README.md`, `path_*/`). |
| **Offline CI tests** | Per path: (1) pure presence tests on tiny **synthetic** excerpts under `tests/fixtures/path_<letter>/`; (2) one **temp** `projects/_tmp_*` integration that writes `path_<letter>/findings.json`. Lab projects are **manual smoke**, not CI-required. |
| **Commit vs ignore** | Culinary contract: commit README, manifest, calendar/units skeleton, `layer0/route-map.json`, `path_<letter>/findings.json` (other empty path stubs OK). **Never** commit `sources/**` bytes (keep `.gitkeep`) or Layer 0 ledger/REPORT. |
| **Smoke pipeline** | `ingest → layer0 → route → workflows/run_paths.py --no-model` — no `LOOM_E2E_RUN` tree required. Review `path_<letter>/findings.json`. |
| **Lab seeds** | Copy a **small named** strong·mixed·weak set from the offline inventory into lab `sources/` (local only). Synthetics stay in `tests/fixtures/`. No symlinks into full partner/`_corpus` trees. |

Path G culinary remains the reference implementation of this contract; stub paths copy the shape, not the syllabus checklist.
