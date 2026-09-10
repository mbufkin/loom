"""Loom Run Review — native desktop window.

One command opens the review UI in an OS-native window: no browser, no tab, no
URL to paste. It starts the two dev processes the app needs, waits for them to
answer, shows the window, and shuts them down again when the window closes.

    ./run-ui                      # repo root, POSIX
    run-ui.cmd                    # repo root, Windows
    python ui/window.py           # equivalent

Useful flags:

    --project disd-aas-icev-smoke   open straight to one curriculum
    --no-spawn                      attach to servers you started yourself
    --api-port 8899                 move the API off its default port

Why the window loads the Vite dev server rather than a built bundle: hot-module
reload keeps working *inside* the native window, so editing a `.tsx` updates
what you are looking at. A bundle would have to be rebuilt on every edit.

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
from pathlib import Path

import webview

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent

HOST = "127.0.0.1"
DEFAULT_API_PORT = 8770
# vite.config.ts sets `strictPort: true` on 5173, so Vite will refuse to drift
# to another port. That is deliberate: a silent port change would leave the
# window pointing at nothing. We check the port up front and say so plainly.
VITE_PORT = 5173

WINDOW_TITLE = "Loom Run Review"


def _log(message: str) -> None:
    """Print a startup line that actually reaches the terminal.

    Python block-buffers stdout whenever it is redirected (a pipe, a log file,
    a launcher script), so plain print() can swallow these lines for the whole
    run — including the port-conflict errors that explain a failure. Flushing
    each line keeps the startup readable wherever it is run from.
    """
    print(message, flush=True)


def _port_in_use(port: int) -> bool:
    """True when something is already listening on HOST:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, port)) == 0


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


def _spawn_vite() -> subprocess.Popen:
    """Start the Vite dev server as a single, directly-killable process."""
    vite_bin = UI_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_bin.is_file():
        raise SystemExit(
            f"Vite is not installed. Run:\n    cd {UI_DIR} && npm ci"
        )
    return subprocess.Popen(["node", str(vite_bin)], cwd=str(UI_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(description="Loom Run Review desktop window")
    ap.add_argument(
        "--project",
        default=None,
        help="curriculum id to open on start, e.g. disd-aas-icev-smoke",
    )
    ap.add_argument(
        "--no-spawn",
        action="store_true",
        help="do not start the servers; attach to ones already running",
    )
    ap.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    args = ap.parse_args()

    url = f"http://{HOST}:{VITE_PORT}/"
    if args.project:
        url += "?" + urllib.parse.urlencode({"project": args.project})

    children: list[subprocess.Popen] = []
    try:
        if args.no_spawn:
            if not _port_in_use(VITE_PORT):
                raise SystemExit(
                    f"--no-spawn given but nothing is listening on {HOST}:{VITE_PORT}.\n"
                    f"Start it with: cd {UI_DIR} && npm run dev"
                )
        else:
            # Fail before spawning anything, so we never half-start and leave
            # a stray server behind.
            if _port_in_use(VITE_PORT):
                raise SystemExit(
                    f"Port {VITE_PORT} is already in use and vite.config.ts pins it "
                    f"(strictPort).\nStop the other dev server, or attach to it with "
                    f"--no-spawn."
                )
            if _port_in_use(args.api_port):
                raise SystemExit(
                    f"Port {args.api_port} is already in use.\n"
                    f"Stop the other API, or pick another with --api-port."
                )

            _log(f"[loom-ui] starting API on {HOST}:{args.api_port}")
            children.append(_spawn_api(args.api_port))
            _log(f"[loom-ui] starting vite on {HOST}:{VITE_PORT}")
            children.append(_spawn_vite())

            if not _wait_until_answering(
                f"http://{HOST}:{args.api_port}/api/projects", timeout_s=30
            ):
                raise SystemExit("API did not come up within 30s.")
            if not _wait_until_answering(url, timeout_s=60):
                raise SystemExit("Vite did not come up within 60s.")

        _log(f"[loom-ui] opening window at {url}")
        webview.create_window(WINDOW_TITLE, url, width=1600, height=1000)
        # start() takes the main thread for the platform UI loop and returns
        # when the window closes. On Windows the renderer is the Edge WebView2
        # runtime that ships with the OS, so no browser engine is bundled here.
        webview.start()
        return 0
    finally:
        # Always reached: normal close, Ctrl+C, or a startup failure above.
        for proc in reversed(children):
            _kill_tree(proc)
        if children:
            _log("[loom-ui] servers stopped")


if __name__ == "__main__":
    raise SystemExit(main())
