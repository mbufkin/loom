"""Where the program lives, versus where the user's data lives.

Until now these were the same directory: ``BASE_DIR`` pointed at the checkout,
and ``config.yaml``, ``logs/`` and every curriculum hung off it. That is fine
for a repo you run from source and wrong for software you hand to somebody
else, because it means:

  * shipping the program ships whatever curricula happen to be in the tree;
  * a district's own work lands inside a git working tree, so updating the
    program and managing their data become the same risky operation;
  * there is nowhere to put per-machine settings that survives a reinstall.

So this module draws the line every desktop application draws:

  INSTALL_DIR  the code, pipeline scripts, checklists, the built UI bundle.
               Read-only in normal use. Replaced wholesale on upgrade.

  DATA_DIR     curricula, config.yaml, credentials, logs. Owned by the user,
               never touched by an upgrade.

Kept to the standard library on purpose. ``usage_lib`` cannot import
``audit_lib`` at load time (``audit_lib.model_chat`` imports ``usage_lib``, so
it would be circular), and both need this seam, so it has to live somewhere
neither of them owns.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Where this program is installed — the directory holding the pipeline
#: scripts. Never write user data here.
INSTALL_DIR = Path(__file__).resolve().parent


def default_data_dir() -> Path:
    """The conventional per-user data location for this OS.

    These are the directories each platform's users already expect an
    application to use, which matters because people back these up, sync
    them, and know where to look when something goes wrong.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "Loom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Loom"
    # Linux and the BSDs: the XDG base directory spec.
    xdg = (os.environ.get("XDG_DATA_HOME") or "").strip()
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "loom"


def resolve_data_dir() -> Path:
    """Decide where user data lives, in order of decreasing explicitness.

    1. ``LOOM_HOME`` — an explicit choice always wins, which is what makes
       this testable and lets one machine keep several separate data sets.
    2. A ``projects/`` directory inside the checkout — this is a developer
       working tree, so leave it exactly where it is. Without this rule,
       introducing the split would make every existing curriculum vanish
       from the UI on the machines that have them.
    3. Otherwise the per-OS user data directory: the case that matters for
       anyone who installs the program rather than cloning it.
    """
    env = (os.environ.get("LOOM_HOME") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if (INSTALL_DIR / "projects").is_dir():
        return INSTALL_DIR
    return default_data_dir()


#: Resolved once at import. Tests override the *importing* module's copy of
#: this name (e.g. ``audit_lib.DATA_DIR = tmp``) rather than reassigning here.
DATA_DIR = resolve_data_dir()


def is_legacy_in_repo() -> bool:
    """True when data is sharing the install directory (a developer tree)."""
    return DATA_DIR == INSTALL_DIR


def ensure_data_dirs(data_dir: Path | None = None) -> Path:
    """Create the data directory skeleton, returning the root.

    Safe to call repeatedly. Only invoked from entry points, never at import
    time, so importing a module never has the side effect of writing to disk.
    """
    root = data_dir or DATA_DIR
    (root / "projects").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    return root
