"""Loom Run Review — native desktop window (dev shell).

Opens the existing React app in an OS-native window instead of a browser tab.
Nothing about the app or the API changes: the window simply loads the Vite dev
server, which keeps hot-module-reload working *inside* the native window. Edit
a `.tsx` and this window updates, exactly as a browser tab would.

Why the dev server and not a built bundle: a bundle would have to be rebuilt on
every edit, which is the opposite of what you want while changing the UI. The
production single-origin path (server.py serving ui/dist) comes later.

Run, with the two dev processes already up:

    python ui/server.py          # stdlib API on :8770
    cd ui && npm run dev         # Vite on :5173
    python ui/window.py          # this window
"""

from __future__ import annotations

import webview

# Vite pins 127.0.0.1:5173 (`strictPort: true` in vite.config.ts) and proxies
# /api -> :8770, so this one URL covers both the app and its API in dev.
DEV_URL = "http://127.0.0.1:5173/"


def main() -> int:
    webview.create_window(
        "Loom Run Review",
        DEV_URL,
        width=1600,
        height=1000,
    )
    # start() takes over the main thread with the platform UI loop and returns
    # once the window is closed. On Windows the renderer is the Edge WebView2
    # runtime, which ships with Win10/11 — so no browser engine is bundled here.
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
