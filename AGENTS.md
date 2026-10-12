# AGENTS.md — notes for AI coding agents

Start with [CONTRIBUTING.md](CONTRIBUTING.md): it is written for humans and
agents alike and its rules apply here.

## Models read whole documents

Never truncate, cap or sample document text sent to a model to save context or
cost. Large documents are split with Layer 0's thresholds (100K-char
threshold, 60K-char parts) and the answers merged; lists of elements are
batched by size and merged. Truncation for display, logs and output plates is
fine. `test_no_document_caps.py` enforces this, and every model stage logs a
`Full-text check:` line and fails if it sent less than the full text.

Details: `.cursor/rules/full-documents.mdc`, docs/BETS.md (Bet 1), and
docs/roadmap.md ("Large single-document chunking").
