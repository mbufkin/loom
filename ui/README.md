# Loom Run Review (local-only)

A tiny local browser for reviewing the artifacts a completed Loom run wrote under
`projects/<id>/` — course plates, stage reports, a unit heatmap, and PDFs — with
an optional button to kick off a local `./run-audit`. Local-only by design: the
API binds to `127.0.0.1`, has no auth, and confines every file read to the
requested project directory.

## Run it (two terminals)

```bash
# 1) API (stdlib Python, no deps) — serves files + launches runs
npm run ui:api          # from repo root  ->  http://127.0.0.1:8770

# 2) UI (Vite dev server, proxies /api -> :8770)
cd ui && npm install    # first time only
npm run ui:dev          # from repo root  ->  http://localhost:5173
```

Open http://localhost:5173. Default project is `dallas-career-2026`.

## Getting review content onto this machine

The review artifacts (`output/`, `layer0|1|2/`) are `.gitignore`d (they quote
copyrighted curriculum), so a plain `git pull` does NOT include them. Copy them
from the box that produced the run, e.g.:

```bash
rsync -av --prune-empty-dirs \
  --include='*/' \
  --include='output/***' --include='layer_unit/***' \
  --include='layer0/REPORT.md' --include='layer1/***' --include='layer2/***' \
  --include='manifest.yaml' --include='pacing-plan.yaml' \
  --exclude='*' \
  <user>@<gb10-host>:~/g10-control-center-loom/projects/dallas-career-2026/ \
  ./projects/dallas-career-2026/
```

## What it reads

| Surface | File(s) |
|---------|---------|
| Course plates | `output/DASHBOARD.md`, `FIRST-PASS.md`, `SUMMARY.md`, `REVIEW-QUEUE.md`, `GLOBAL-AUDIT.md` |
| Machine stats / heatmap | `output/aggregate-stats.json` (`unit_rollup`) |
| Stage reports | `layer0/REPORT.md`, `layer1/REPORT.md` + `REVIEW-QUEUE.md`, `layer2/REPORT.md`, `layer_unit/UNIT-RUNG.md` |
| Per-unit | `output/<unit>/REPORT.md`, gap reports, `output/teachers/<unit>/*` |
| PDF | `output/GLOBAL-AUDIT-REPORT.pdf`, unit `AUDIT-REPORT.pdf` |

Unit heatmap bands use the real `layer_unit/UNIT-RUNG.json` bands when present, and
otherwise derive a band from Layer 1 role fulfillment.

## Scope (v1)

In: browse/read run outputs, unit heatmap, local run + log stream, read-only
config summary. Out: remote hosting, config editor, editing curriculum content,
live model-token streaming.
