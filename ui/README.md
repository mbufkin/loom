# Loom Run Review (local-only)

A tiny local browser for reviewing the artifacts a completed Loom run wrote under
`projects/<id>/` — course plates, stage reports, a unit heatmap, and PDFs — with
an optional button to kick off a local `./run-audit`. Local-only by design: the
API binds to `127.0.0.1`, has no auth, and confines every file read to the
requested project directory.

## Run it (one command, native window)

No browser, no tab, no URL to paste. `run-ui` starts the API and the dev
server, opens an OS-native window, and stops both when you close it.

```bash
cd ui && npm ci                       # first time only
pip install -r ui/requirements.txt    # first time only (pywebview)

./run-ui                              # POSIX, from repo root
run-ui.cmd                            # Windows, from repo root
./run-ui --project disd-aas-icev-smoke --view overview
```

The window renders in the OS webview — Edge WebView2 on Windows, WebKitGTK on
Linux, Cocoa/WebKit on macOS — so no browser engine is bundled.

| Flag | Effect |
|------|--------|
| `--project <id>` | open straight to one curriculum |
| `--view review\|overview\|next` | open a deck instead of the review console |
| `--prod` | single-origin: the API serves built `ui/dist`, no Vite, no Node |
| `--no-spawn` | attach to servers you started yourself |
| `--api-port N` | move the API off its default port (`--prod` only) |
| `--debug` | enable webview devtools (F12) |

Default mode runs Vite, so **hot-module reload works inside the native window**:
edit a `.tsx` and the window updates. Use `--prod` on a delivered machine —
one Python process behind the window, no proxy and no CORS.

The `View` menu has `Reload` and `Open in browser`, because a native window has
no address bar. External links and `target="_blank"` artifact links (PDF, HTML)
are handed to the OS rather than opened in a chromeless popup.

## Run it in a browser instead (two terminals)

```bash
# 1) API (stdlib Python, no deps) — serves files + launches runs
npm run ui:api          # from repo root  ->  http://127.0.0.1:8770

# 2) UI (Vite dev server, proxies /api -> :8770)
cd ui && npm install    # first time only
npm run ui:dev          # from repo root  ->  http://localhost:5173
```

Open http://localhost:5173. Default project is `dallas-career-2026`; append
`?project=<id>` to open another, including non-STATUS trees.

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

## Surfaces that stay dark without their data

Several panels are gated on artifacts a given run may not have written. They
are not broken — there is simply nothing to draw — so check for the input
before debugging the component.

| Surface | Needs | Symptom when missing |
|---------|-------|----------------------|
| Review console (all of it) | `e2e/runs/<id>/REVIEW-READY.json` | "No completed review run yet." Only completed E2E snapshots are listed; older live-root plates stay off this surface by design. |
| `GraphViz`, `GraphBelongingPanel` | `graph/runs/*` | Model-run picker reads "No model runs"; `Curriculum graph` greyed with a `none` badge |
| Unit heatmap bands | `layer_unit/UNIT-RUNG.json` | Bands fall back to a Layer 1 role-fulfillment estimate; review slip shows `UNKNOWN` |
| `CreateStudio`, `GapQueue` (Next Steps) | the `create/` package, which is `.gitignore`d | `500` from `/api/projects/<id>/create/matrix` |
| PDF viewer | `output/*.pdf` | `outputs.pdfs` is empty, so no PDF entries appear |

To review an older run that predates the `e2e/runs/<model>/` layout, copy its
plates into `projects/<id>/e2e/runs/<name>/` (same relative paths — the API
treats an E2E folder as a self-contained project mirror) and add a
`REVIEW-READY.json` beside them.

## Scope (v1)

In: browse/read run outputs, unit heatmap, local run + log stream, read-only
config summary. Out: remote hosting, config editor, editing curriculum content,
live model-token streaming.
