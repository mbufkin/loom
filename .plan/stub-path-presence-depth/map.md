---
label: wayfinder:map
status: closed
closed_at: 2026-08-05T18:25:00Z
---

# Stub-path presence depth (B → H → F → D → E → C)

## Destination

Locked **G-style presence depth** for every stub lens — presence extractors, offline tests, and named lab fixtures — in build order **B → H → F → D → E → C**, after a shared lab harness is decided. Map is done when the harness plus each stub path’s presence checklist and fixture set are locked so implementers can build path-by-path without further product decisions. **A/G stay on [World-class path reviews](../world-class-path-reviews/map.md); no A/G polish in this effort.**

**Status: Destination met (2026-08-05).** Harness + plates + runners + labs shipped for B, H, F, D, E, C. Way is clear — no open frontier tickets remain on this map.

## Notes

- Domain: Loom review lenses (`docs/PATHS.md`).
- Standing decisions from charting (2026-08-05):
  - Full depth here = **presence + offline tests + lab fixtures** (not quality calls / one-pagers).
  - Order: **B → H → F → D → E → C**.
  - **New map**, separate from World-class path reviews (A quality bar).
  - **Shared lab harness + offline test template first**, then path plates.
  - Done = harness + each stub path has locked presence checklist + named fixtures.
  - A/G polish: **none** in this map.
  - In-map implement after each plate lock (override of plan-first handoff).
- Skills: wayfinder; **wayfinding-research** (research → recommend → ask on every material choice).
- Tracker: local markdown under `.plan/stub-path-presence-depth/`.

## Decisions so far

- [Offline corpus inventory for stub-path labs](./tickets/02-offline-corpus-inventory-stub-labs.md) — B/H seed from Dallas (4 quiz↔key pairs, 21 exit tickets); F/D/E from `bluebonnet-math-2026/_corpus` (+ OpenSciEd TE); full-grok/g5-m1 sources are stubs; Desktop culinary adds no B–E.
- [Shared path-lab harness contract](./tickets/01-shared-path-lab-harness.md) — `lab-<lens>-path-<letter>/`; CI = `tests/fixtures/path_X/` synthetics + temp integration; labs manual smoke via ingest→layer0→route→run_paths `--no-model`; culinary commit contract; copy named seeds (no corpus symlinks).
- [Path B presence plate and fixtures](./tickets/03-path-b-presence-plate-and-fixtures.md) — B1–B6; two-doc stem pairing; CI synthetics + `lab-assessment-path-b` Dallas seeds; runner shipped.
- [Path H presence plate and fixtures](./tickets/04-path-h-presence-plate-and-fixtures.md) — H1–H5 formative-only; light H4 cues; CI synthetics + `lab-exit-ticket-path-h` Dallas seeds; runner shipped.
- [Path F presence plate and fixtures](./tickets/05-path-f-presence-plate-and-fixtures.md) — F1–F5; YAG router fix; CI synthetics + `lab-standards-path-f` evidence text seeds; runner shipped.
- [Path D presence plate and fixtures](./tickets/06-path-d-presence-plate-and-fixtures.md) — D1–D5; F/D boundary unchanged; CI synthetics + `lab-teacher-support-path-d` evidence text seeds; runner shipped.
- [Path E presence plate and fixtures](./tickets/07-path-e-presence-plate-and-fixtures.md) — E1–E5; no key/LPS pairing; CI synthetics + `lab-student-practice-path-e` G5 Learn/Succeed/Practice seeds; runner shipped.
- [Path C presence plate and fixtures](./tickets/08-path-c-presence-plate-and-fixtures.md) — nursery C1–C5 (identity · feedback log · optional growth bucket); CI synthetics + `lab-general-path-c`; runner shipped.

## Not yet specified

<!-- empty — Destination met; remaining themes sit beyond this map -->

## Out of scope

- Path A / Path G depth or polish (owned by World-class path reviews / existing G work).
- World-class quality calls, trust scorecards, and shared one-pagers for B–H (later effort).
- Deeper TEKS/target matching beyond optional keyword cues (later quality effort).
- New top-level path letters I…Z.
- Inventing lesson/quiz/exit content (auditor-only stays).
- Full multi-module Bluebonnet overnight runs as a requirement of this map.
