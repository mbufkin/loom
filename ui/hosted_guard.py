"""The door in front of ui/server.py when it runs as a hosted service.

On a desktop the server binds to 127.0.0.1 and the only client is the window
on the same machine, so it trusts every request. Hosted, it sits behind a
tunnel on the public internet, and the only legitimate client is the Vercel
forwarder, which has already checked a Google sign-in. Two rules follow:

  1. Every request must carry ``X-Loom-Proxy-Secret`` equal to the
     ``LOOM_PROXY_SECRET`` env var. Anything else is a stranger who found the
     tunnel hostname: 401, before any routing happens.
  2. Endpoints that only make sense on the operator's own machine — choosing a
     model, storing an API key, pip-installing packages, probing model servers
     — are refused with 403 even with the secret. The model is pinned in the
     container's config; letting a signed-in user repoint it would let them
     send district documents anywhere, or run pip as the service.

Hosted mode is switched on by the presence of ``LOOM_PROXY_SECRET``. Without
it this module allows everything, so the desktop app behaves exactly as before.

Keep the BLOCKED list in step with hosted/lib/loom-proxy.ts, which refuses the
same routes one hop earlier. Two layers on purpose: a bug in either one alone
does not open the door.

Standard library only, like the server it guards.
"""

from __future__ import annotations

import hmac
import os
from typing import Mapping

SECRET_ENV = "LOOM_PROXY_SECRET"
SECRET_HEADER = "X-Loom-Proxy-Secret"

#: Path prefixes refused in hosted mode, matched on whole path segments so
#: "/api/models" blocks "/api/models/key" but not a future "/api/modelsets".
BLOCKED_PREFIXES: tuple[str, ...] = (
    "/api/install-deps",
    # discover / providers / remote / key / select. GETs included: `remote`
    # and `discover` make outbound requests to a caller-supplied URL (an SSRF
    # primitive), and key status is nobody's business but the operator's.
    "/api/models",
)


def configured_secret(env: Mapping[str, str] | None = None) -> str:
    """The shared secret, or "" when this server is not in hosted mode."""
    return ((env if env is not None else os.environ).get(SECRET_ENV) or "").strip()


def is_hosted(env: Mapping[str, str] | None = None) -> bool:
    return bool(configured_secret(env))


def is_blocked(path: str) -> bool:
    """True for a desktop-only endpoint. ``path`` is the URL path, no query."""
    # Normalise the cheap tricks ("//api//models", trailing slash) the same way
    # the server's own router does: it splits on "/" and drops empty parts.
    norm = "/" + "/".join(p for p in path.split("/") if p)
    return any(norm == p or norm.startswith(p + "/") for p in BLOCKED_PREFIXES)


def check(path: str, headers: Mapping[str, str], env: Mapping[str, str] | None = None):
    """Decide whether a request may proceed.

    Returns None to allow, or ``(status, message)`` to refuse. The message is
    deliberately generic: a stranger learns nothing about what would work.
    """
    secret = configured_secret(env)
    if not secret:
        return None  # desktop mode: unchanged behaviour
    supplied = (headers.get(SECRET_HEADER) or "").strip()
    # compare_digest takes the same time whether the first or last byte
    # differs, so the secret cannot be recovered by timing many guesses.
    if not supplied or not hmac.compare_digest(
        supplied.encode("utf-8"), secret.encode("utf-8")
    ):
        return 401, "unauthorized"
    if is_blocked(path):
        return 403, "not available in the hosted app"
    return None
