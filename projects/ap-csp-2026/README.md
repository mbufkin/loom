# Dataset: ap-csp-2026

| | |
|--|--|
| **Tier** | Stress |
| **Program** | Crystallize at repo root — this folder is **data only** |
| **Shape** | One large AP CSP Course and Exam Description (CED) PDF, mapped to 5 conceptual units |
| **Run** | `./run-audit ap-csp-2026` |

## What this corpus is for

Stress **Layer 0** (and Layer 0-B) on a huge framework-style PDF: chunked map-reduce
extract, wide-span splits, citation fidelity. That path works.

## Known limit (MVP — do not chase for launch)

**Layer 1 ORGANIZE / FULFILL do not fit this document in the current 65k context.**

Live failure (2026-07-10): Phase 1 sent ~**113k** prompt tokens for
`ap-csp-ced.pdf` (~507 ledger elements) against a **65,536**-token context → HTTP 400
`exceed_context_size_error`. All elements left **UNVERIFIED**. Phase 3 hit the same
wall on at least one fulfill call. Layer 2 judged 0 lesson plans. Hybrid
`--report all --delivery model` still wrote plates, but they are **not** a trustworthy
curriculum review — mise en place never placed.

| Stage | Status on this dataset |
|-------|------------------------|
| Layer 0 / 0-B | OK (stress success) |
| Layer 1 | **Blocked** — single-doc organize too large |
| Layer 2 / hybrid reports | Ran, but on empty placement — ignore for demo |

**MVP implication:** Crystallize’s champion path is multi-document course packs
(Dallas-shaped). One giant standards/framework PDF is a **documented stress case**,
not a supported end-to-end product shape until Layer 1 gets document chunking
(same idea Layer 0 already has). Tracked in [`docs/roadmap.md`](../../docs/roadmap.md)
(“Layer 1: chunk ORGANIZE for oversized single documents — DEFERRED”).
