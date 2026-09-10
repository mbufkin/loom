"""Loom Run Review — native desktop window.

One command opens the review UI in an OS-native window: no browser, no tab, no
URL to paste. It starts the two dev processes the app needs, waits for them to
answer, shows the window, and shuts them down again when the window closes.

    ./run-ui                                  # repo root, POSIX
    run-ui.cmd                                # repo root, Windows
    python ui/window.py                       # equivalent

Useful flags:

    --project disd-aas-icev-smoke   open straight to one curriculum
    --view overview                 open a deck instead of the review console
    --prod                          ship mode: one origin, no Vite, no Node
    --no-spawn                      attach to servers you started yourself
    --api-port 8899                 move the API off its default port (--prod)
    --debug                         enable webview devtools (F12)

Two modes, and the difference matters:

  default  Vite on 5173 serves the app and proxies /api to the Python API on
           8770. Hot-module reload works *inside* the native window, so editing
           a `.tsx` updates what you are looking at. This is the mode to use
           while changing the UI.

  --prod   The Python API serves the built ui/dist itself on a single
           OS-assigned port. No Vite, no Node, no proxy, no CORS — one process
           behind the window, which is what you want on a delivered machine.

Why Vite is launched through `node` instead of `npm run dev`: on Windows `npm`
is a PowerShell/cmd shim that cannot be spawned without a shell, and it would
add a process layer between us and the real server — killing the shim can
orphan Vite and leave the port bound. Calling `node node_modules/vite/bin/
vite.js` gives one process we can start and stop cleanly on every platform.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import webview
from webview.menu import Menu, MenuAction, MenuSeparator

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent
VITE_BIN = UI_DIR / "node_modules" / "vite" / "bin" / "vite.js"
DIST = UI_DIR / "dist"
# Built from assets/pdf/mark.png. .NET's Icon() constructor needs a real .ico,
# so a PNG cannot be handed to pywebview directly.
ICON = ROOT / "assets" / "loom.ico"

HOST = "127.0.0.1"
DEFAULT_API_PORT = 8770
# vite.config.ts sets `strictPort: true` on 5173, so Vite will refuse to drift
# to another port. That is deliberate: a silent port change would leave the
# window pointing at nothing. We check the port up front and say so plainly.
VITE_PORT = 5173

WINDOW_TITLE = "Loom Run Review"

# Route clicks that mean "leave this window" out to the OS instead of letting
# WebView2 open a chromeless popup it cannot navigate. Covers both external
# https links inside curriculum markdown and the `target="_blank"` artifact
# links (PDF / HTML) that should open in the system's default viewer.
_EXTERNAL_LINK_SHIM = """
(function () {
  if (window.__loomExternalLinks) return;
  window.__loomExternalLinks = true;
  document.addEventListener(
    'click',
    function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('a') : null;
      if (!a) return;
      var href = a.getAttribute('href') || '';
      if (!href || href.charAt(0) === '#') return;
      var newWindow = a.target === '_blank';
      var external = /^https?:\\/\\//i.test(href);
      if (!newWindow && !external) return;
      ev.preventDefault();
      // a.href is the resolved absolute form of the attribute.
      window.pywebview.api.open_external(a.href);
    },
    true
  );
})();
"""


def _log(message: str) -> None:
    """Print a startup line that actually reaches the terminal.

    Python block-buffers stdout whenever it is redirected (a pipe, a log file,
    a launcher script), so plain print() can swallow these lines for the whole
    run — including the port-conflict errors that explain a failure. Flushing
    each line keeps the startup readable wherever it is run from.
    """
    print(message, flush=True)


def open_external(url: str) -> None:
    """Hand a URL to the OS. Exposed to the page as pywebview.api.open_external.

    Also the answer to in-window PDFs: WebView2 renders them inline but
    WebKitGTK on Linux does not, so the explicit "open" links defer to whatever
    the operating system already uses for that file type.
    """
    webbrowser.open(url)


def _port_in_use(port: int) -> bool:
    """True when something is already listening on HOST:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, port)) == 0


def _free_port() -> int:
    """Ask the OS for an unused port.

    Production mode has no fixed port to defend: nothing proxies to it and no
    bookmark points at it, so binding 0 and reading the result avoids ever
    colliding with another tool. We pick it here rather than passing
    `--port 0` to the server so the URL is known before the child starts.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _wait_until_answering(url: str, timeout_s: float) -> bool:
    """Poll a URL until it produces any HTTP response, or time out.

    An HTTPError still means the server is up and talking, so it counts as
    ready — we only care that the socket is serving HTTP, not what it returns.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop a child and anything it spawned.

    Vite starts helper processes (esbuild), so a bare terminate() can leave
    strays holding the port. On Windows `taskkill /T` walks the tree; elsewhere
    terminate() then kill() on the child is enough because we spawn the real
    binary directly rather than a wrapper script.
    """
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _spawn_api(api_port: int) -> subprocess.Popen:
    """Start the stdlib JSON API.

    `sys.executable` is used rather than the string "python3": the repo's npm
    scripts assume a POSIX box, but this launcher has to work on Windows too,
    and sys.executable is always the interpreter that is running us.
    """
    return subprocess.Popen(
        [sys.executable, str(UI_DIR / "server.py"), "--port", str(api_port)],
        cwd=str(ROOT),
    )


def _require_vite() -> None:
    if not VITE_BIN.is_file():
        raise SystemExit(f"Vite is not installed. Run:\n    cd {UI_DIR} && npm ci")


def _spawn_vite() -> subprocess.Popen:
    """Start the Vite dev server as a single, directly-killable process."""
    _require_vite()
    return subprocess.Popen(["node", str(VITE_BIN)], cwd=str(UI_DIR))


def _build_dist() -> None:
    """Produce ui/dist so the API can serve the app on one origin.

    A convenience build for first run in --prod; `npm run ui:build` remains the
    canonical one because it also runs `tsc -b`. This deliberately skips the
    typecheck so launching is not gated on unrelated type errors.
    """
    _require_vite()
    _log("[loom-ui] no bundle at ui/dist — building it (first --prod run only)")
    result = subprocess.run(["node", str(VITE_BIN), "build"], cwd=str(UI_DIR))
    if result.returncode != 0 or not (DIST / "index.html").is_file():
        raise SystemExit(
            "vite build failed. Run `npm run ui:build` in ui/ to see the error."
        )


def _build_menu(window: webview.Window) -> list[Menu]:
    """A minimal menu bar covering what a browser would otherwise provide.

    A native window has no address bar or reload button, so without this there
    is no way to recover from a failed load, and no way to escape to a real
    browser when you want one.
    """
    return [
        Menu(
            "View",
            [
                # location.reload() re-runs the SPA at its current URL, which
                # keeps the selected curriculum and run in place.
                MenuAction("Reload", lambda: window.run_js("location.reload()")),
                MenuSeparator(),
                MenuAction(
                    "Open in browser",
                    lambda: open_external(window.get_current_url() or ""),
                ),
            ],
        )
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Loom Run Review desktop window")
    ap.add_argument(
        "--project",
        default=None,
        help="curriculum id to open on start, e.g. disd-aas-icev-smoke",
    )
    ap.add_argument(
        "--view",
        choices=("review", "overview", "next"),
        default=None,
        help="open straight to a deck instead of the review console",
    )
    ap.add_argument(
        "--prod",
        action="store_true",
        help="single-origin mode: serve the built ui/dist from the API, no Vite",
    )
    ap.add_argument(
        "--no-spawn",
        action="store_true",
        help="do not start the servers; attach to ones already running",
    )
    ap.add_argument(
        "--api-port",
        type=int,
        default=None,
        help=f"default {DEFAULT_API_PORT} in dev; an OS-assigned port in --prod",
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="enable webview devtools (F12) and verbose pywebview logging",
    )
    args = ap.parse_args()

    if args.prod:
        # Nothing proxies to this port, so let the OS choose and never clash.
        api_port = args.api_port or _free_port()
        origin = f"http://{HOST}:{api_port}/"
    else:
        # In dev the port is fixed by vite.config.ts, whose /api proxy targets
        # 8770. Moving the API without editing that config would leave every
        # /api call falling through to the SPA index — fail instead of guessing.
        if args.api_port not in (None, DEFAULT_API_PORT):
            raise SystemExit(
                f"--api-port {args.api_port} cannot work in dev: the Vite proxy in "
                f"vite.config.ts targets {DEFAULT_API_PORT}.\n"
                f"Use --prod for a custom port, or edit vite.config.ts."
            )
        api_port = DEFAULT_API_PORT
        origin = f"http://{HOST}:{VITE_PORT}/"

    # The app reads these off the query string, so the launcher only has to
    # build a URL — no IPC into the page and nothing to keep in sync.
    query = {k: v for k, v in (("project", args.project), ("view", args.view)) if v}
    url = origin + ("?" + urllib.parse.urlencode(query) if query else "")

    # Name the loaded curriculum in the title bar: with several windows open,
    # alt-tab is the only way to tell them apart.
    title = f"{WINDOW_TITLE} — {args.project}" if args.project else WINDOW_TITLE

    children: list[subprocess.Popen] = []
    try:
        if args.no_spawn:
            expected = api_port if args.prod else VITE_PORT
            if not _port_in_use(expected):
                hint = (
                    f"python {UI_DIR / 'server.py'} --port {expected}"
                    if args.prod
                    else f"cd {UI_DIR} && npm run dev"
                )
                raise SystemExit(
                    f"--no-spawn given but nothing is listening on {HOST}:{expected}.\n"
                    f"Start it with: {hint}"
                )
        else:
            # Fail before spawning anything, so we never half-start and leave
            # a stray server behind.
            if not args.prod and _port_in_use(VITE_PORT):
                raise SystemExit(
                    f"Port {VITE_PORT} is already in use and vite.config.ts pins it "
                    f"(strictPort).\nStop the other dev server, or attach to it with "
                    f"--no-spawn."
                )
            if _port_in_use(api_port):
                raise SystemExit(
                    f"Port {api_port} is already in use.\n"
                    f"Stop the other API, or pick another with --api-port."
                )
            if args.prod and not (DIST / "index.html").is_file():
                _build_dist()

            _log(f"[loom-ui] starting API on {HOST}:{api_port}")
            children.append(_spawn_api(api_port))
            if not args.prod:
                _log(f"[loom-ui] starting vite on {HOST}:{VITE_PORT}")
                children.append(_spawn_vite())

            if not _wait_until_answering(
                f"http://{HOST}:{api_port}/api/projects", timeout_s=30
            ):
                raise SystemExit("API did not come up within 30s.")
            if not _wait_until_answering(url, timeout_s=60):
                raise SystemExit(
                    "The app did not come up within 60s."
                    if args.prod
                    else "Vite did not come up within 60s."
                )

        _log(f"[loom-ui] opening window at {url}")
        window = webview.create_window(
            title,
            url,
            width=1600,
            height=1000,
            # Below roughly this the three-column review layout starts to
            # collide, so stop the drag rather than render something broken.
            min_size=(1100, 700),
            # pywebview disables both by default. A reviewer has to be able to
            # quote an excerpt and to zoom into a dense findings table.
            text_select=True,
            zoomable=True,
        )
        window.expose(open_external)
        # `loaded` fires on every navigation; the shim guards against
        # double-binding so a reload does not stack listeners.
        window.events.loaded += lambda: window.run_js(_EXTERNAL_LINK_SHIM)

        start_kwargs = {"debug": args.debug, "menu": _build_menu(window)}
        if ICON.is_file():
            start_kwargs["icon"] = str(ICON)
        # start() takes the main thread for the platform UI loop and returns
        # when the window closes. On Windows the renderer is the Edge WebView2
        # runtime that ships with the OS, so no browser engine is bundled here.
        webview.start(**start_kwargs)
        return 0
    finally:
        # Always reached: normal close, Ctrl+C, or a startup failure above.
        for proc in reversed(children):
            _kill_tree(proc)
        if children:
            _log("[loom-ui] servers stopped")


if __name__ == "__main__":
    raise SystemExit(main())
