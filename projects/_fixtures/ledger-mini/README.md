# ledger-mini — fast offline pipeline fixture

A tiny, self-contained curriculum corpus (3 hand-written source docs) used by
`test_layer0_ledger_complete.py` to exercise the **real** Layer 0 code path with a
**fake model**, in milliseconds.

## Why it exists

The Layer 0 `ledger.json` truncation bug (2026-07-21) shipped because the only test
that touched Layer 0 end-to-end required the real, private Dallas corpus **and** a
live local model — so nobody ran it in the inner dev loop, and the bug was only
found by watching a multi-hour production run. That is the wrong place to catch a
deterministic plumbing bug.

This fixture follows standard test-pyramid practice:

- **Tiny, checked-in, hand-verified data** (known paragraph counts → known element
  counts under the fake model).
- **The expensive, non-deterministic dependency (the model) is mocked** behind the
  existing `_decompose_text_with_retry` seam, exactly like `test_layer1_organize_batch.py`
  fakes `call_and_parse_with_retry`.
- **Hermetic**: the test patches `layer0.project_dir` to a temp directory, so no
  artifacts are ever written into the repo.

## Contents

| File | Paragraphs (blank-line separated) |
|------|-----------------------------------|
| `sources/doc_aaaa01_Mini_Lesson_Plan.txt` | 4 |
| `sources/doc_aaaa02_Mini_Slides.txt`      | 3 |
| `sources/doc_aaaa03_Mini_Exit_Ticket.txt` | 2 |

The fake model emits one element per paragraph, so a clean full run yields a
9-element ledger. Keep these docs small and their paragraph counts stable; the test
asserts against them.
