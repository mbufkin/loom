---
type: research
blocked_by: []
claimed_by: cursor
claimed_at: 2026-08-05T14:45:00Z
resolved_at: 2026-08-05T14:52:55Z
assets:
  - ../assets/02-offline-corpus-inventory-stub-labs.md
---

# Offline corpus inventory for stub-path labs

## Question

What **offline, already-local** quiz, answer-key, exit-ticket, pacing/YAG, teacher-edition, and student-practice samples exist under Loom projects / Desktop / fixtures that can seed strong·mixed·weak lab fixtures for Paths B, H, F, D, and E — without requiring new partner downloads?

## Answer

Full inventory: [02-offline-corpus-inventory-stub-labs asset](../assets/02-offline-corpus-inventory-stub-labs.md).

**Gist / counts (unique primary seeds):**

| Path | Count | Strong / mixed / weak seedability |
|------|------:|-----------------------------------|
| **B** | 4 Dallas quiz↔key pairs (+1 worksheet↔key); 22 OK quizzes + 3 unit test/keys | Dallas pairs **strong**; OK quizzes **mixed** (no per-quiz keys in `sources/`); no Bluebonnet quiz/key |
| **H** | 21 Dallas + 1 synthetic mini | Fully seedable from Dallas (Engineering **strong** → one-prompt / ledger-mini **weak**) |
| **F** | 8 Alg1 pacing/YAG/S&S/TEKS PDFs in `_corpus` | Pacing/S&S **strong**; YAG/summaries **mixed**; prefer `_corpus` over stub `full-grok/sources` |
| **D** | 14 BB TE/impl in `_corpus` + 7 OpenSciEd TE (1 stub) | Module TEs / large OpenSciEd **strong**; `6.4-te.pdf` / name stubs **weak** |
| **E** | 18 G5 Learn/Practice/Succeed + Alg1 Skills/SE + 5 Dallas worksheets + 2 OK worksheets | Learn/Succeed **strong**; many `*_Practice_*` tiny (**weak**); Dallas worksheets **mixed** |

**Caveat:** `bluebonnet-full-grok/sources` and `bluebonnet-g5-m1-graph-test/sources` are filename stubs — real Bluebonnet bytes live in `projects/bluebonnet-math-2026/_corpus/`. Desktop culinary has Path G syllabi only, not B–E seeds.
