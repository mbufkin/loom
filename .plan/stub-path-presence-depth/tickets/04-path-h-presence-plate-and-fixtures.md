---
type: grilling
blocked_by:
  - 01-shared-path-lab-harness
  - 03-path-b-presence-plate-and-fixtures
claimed_by: cursor
claimed_at: 2026-08-05T15:15:00Z
resolved_at: 2026-08-05T15:25:00Z
assets:
  - ../../docs/PATH-H-EXIT-TICKET.md
  - ../../workflows/checklists/exit_ticket.yaml
---

# Path H presence plate and fixtures

## Question

For Path H (exit ticket), what are the **presence steps (H1–Hn)** that stay formative-only (no key requirement), and which **named strong·mixed·weak fixtures** lock the offline tests and lab — learning from Path B’s plate without copying quiz↔key assumptions?

## Answer

**Plate (shipped):** H1 inventory · H2 formative prompt/stems · H3 optional target cue · H4 light next-day signal keywords · H5 stub emit. No key/pairing. Checklist: `workflows/checklists/exit_ticket.yaml`.

**CI fixtures** (`tests/fixtures/path_h/`): `strong_exit.txt` / `mixed_exit.txt` / `weak_exit.txt` via `test_path_h_exit_ticket.py`.

**Lab** (`projects/lab-exit-ticket-path-h/`): Dallas Engineering (strong), Arts AV Day 1 (mixed), Professional Preparedness Day 2 (weak). Smoke: ingest → route → `run_paths --no-model`.
