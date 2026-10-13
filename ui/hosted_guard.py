"""The door in front of ui/server.py when it runs as a hosted service.

On a desktop the server binds to 127.0.0.1 and the only client is the window
on the same machine, so it trusts every request. Hosted, it is published to
the internet through a Cloudflare tunnel with Cloudflare Access in front:
Access signs people in (one-time PIN to an allowed email) and adds a signed
JWT to every request it lets through. This module refuses anything that does
not carry a valid one, so the app stays closed even if the Access application
is misconfigured, deleted, or bypassed by reaching the origin some other way.

Rules, in order, for every request (UI files and /api alike):

  1. ``/healthz`` from inside the container (127.0.0.1) answers without a
     token, for the Docker healthcheck. Requests through the tunnel arrive
     from the Docker bridge address, never 127.0.0.1, so they cannot use it.
  2. A token must be present: the ``Cf-Access-Jwt-Assertion`` header, or the
     ``CF_Authorization`` cookie as a fallback. Missing -> 401.
  3. It must verify: RS256 signature against the team's published keys
     (https://<team>.cloudflareaccess.com/cdn-cgi/access/certs), ``aud`` equal
     to this application's AUD tag, ``iss`` equal to the team domain, and
     ``exp``/``nbf`` within a small leeway. Anything else -> 403.
  4. Optional defence in depth: if ``LOOM_ALLOWED_EMAILS`` is set, the token's
     ``email`` must be on it. Access already enforces its own policy; this
     keeps a too-broad policy edit in the dashboard from opening the app.
  5. Desktop-only endpoints (model choice, API keys, pip install) -> 403 even
     for a valid user. The model is pinned in the container's config; letting
     a signed-in user repoint it would let them send district documents
     anywhere, or run pip as the service.

Hosted mode is switched on by ``LOOM_HOSTED=1``. In hosted mode a missing
``LOOM_ACCESS_TEAM_DOMAIN`` or ``LOOM_ACCESS_AUD`` is a startup error, never a
quiet fall-back to "allow everyone" (fail closed). Without ``LOOM_HOSTED`` this
module allows everything, so the desktop app behaves exactly as before.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from typing import Any, Callable, Mapping

TOKEN_HEADER = "Cf-Access-Jwt-Assertion"
TOKEN_COOKIE = "CF_Authorization"
HEALTH_PATH = "/healthz"

#: Clock skew tolerated on exp/nbf/iat, in seconds.
LEEWAY_SECONDS = 30

#: Path prefixes refused in hosted mode, matched on whole path segments so
#: "/api/models" blocks "/api/models/key" but not a future "/api/modelsets".
BLOCKED_PREFIXES: tuple[str, ...] = (
    "/api/install-deps",
    # discover / providers / remote / key / select. GETs included: `remote`
    # and `discover` make outbound requests to a caller-supplied URL (an SSRF
    # primitive), and key status is nobody's business but the operator's.
    "/api/models",
)


class ConfigError(RuntimeError):
    """Hosted mode is on but the Access settings are incomplete."""


def is_hosted(env: Mapping[str, str] | None = None) -> bool:
    return ((env if env is not None else os.environ).get("LOOM_HOSTED") or "").strip() == "1"


def is_blocked(path: str) -> bool:
    """True for a desktop-only endpoint. ``path`` is the URL path, no query."""
    # Normalise the cheap tricks ("//api//models", trailing slash) the same way
    # the server's own router does: it splits on "/" and drops empty parts.
    norm = "/" + "/".join(p for p in path.split("/") if p)
    return any(norm == p or norm.startswith(p + "/") for p in BLOCKED_PREFIXES)


def normalise_team_domain(raw: str) -> str:
    """"loomaudit", "loomaudit.cloudflareaccess.com" or the full URL -> the issuer URL."""
    host = raw.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not host:
        return ""
    if "." not in host:
        host = f"{host}.cloudflareaccess.com"
    return f"https://{host}"


def _parse_email_list(raw: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


@dataclass
class AccessGuard:
    """Validates Cloudflare Access tokens for one application.

    ``jwks_client`` is any object with ``get_signing_key_from_jwt(token)``
    (PyJWT's PyJWKClient in production). PyJWKClient caches the team's keys
    and refetches once when a token names a key id it has not seen, which is
    exactly what a Cloudflare key rotation needs.
    """

    issuer: str
    audience: str
    allowed_emails: frozenset[str] = frozenset()
    jwks_client: Any = None
    leeway: int = LEEWAY_SECONDS
    _jwt: Any = field(default=None, repr=False)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        jwks_factory: Callable[[str], Any] | None = None,
    ) -> "AccessGuard":
        env = env if env is not None else os.environ
        issuer = normalise_team_domain(env.get("LOOM_ACCESS_TEAM_DOMAIN") or "")
        audience = (env.get("LOOM_ACCESS_AUD") or "").strip()
        missing = [
            name
            for name, value in (
                ("LOOM_ACCESS_TEAM_DOMAIN", issuer),
                ("LOOM_ACCESS_AUD", audience),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "hosted mode needs " + " and ".join(missing) + "; refusing to start"
            )
        import jwt  # PyJWT, from requirements-hosted.txt

        certs_url = f"{issuer}/cdn-cgi/access/certs"
        factory = jwks_factory or (
            lambda url: jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=10)
        )
        return cls(
            issuer=issuer,
            audience=audience,
            allowed_emails=_parse_email_list(env.get("LOOM_ALLOWED_EMAILS") or ""),
            jwks_client=factory(certs_url),
            _jwt=jwt,
        )

    def token_from(self, headers: Mapping[str, str]) -> str:
        """The Access token from the header, else from the CF_Authorization cookie."""
        token = (headers.get(TOKEN_HEADER) or "").strip()
        if token:
            return token
        raw_cookie = headers.get("Cookie") or ""
        if not raw_cookie:
            return ""
        try:
            jar = SimpleCookie()
            jar.load(raw_cookie)
        except CookieError:
            return ""
        morsel = jar.get(TOKEN_COOKIE)
        return morsel.value.strip() if morsel else ""

    def verify(self, token: str) -> dict:
        """Claims of a valid token. Raises jwt.PyJWTError (or ValueError) otherwise."""
        jwt = self._jwt
        if jwt is None:
            import jwt as _jwt

            jwt = self._jwt = _jwt
        signing_key = self.jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            # Pinned: never let the token's own header choose the algorithm
            # (the "alg: none" / HS256-with-public-key attacks).
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            leeway=self.leeway,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        if self.allowed_emails:
            email = str(claims.get("email") or "").strip().lower()
            if email not in self.allowed_emails:
                raise ValueError("email not on LOOM_ALLOWED_EMAILS")
        return claims

    def email_of(self, headers: Mapping[str, str]) -> str:
        """Email of the signed-in person, or "" when there is no valid token.

        Display only ("Signed in as ..."). It goes through verify(), the same
        signature, audience, issuer and allow-list checks as check(), so an
        unverified or forged token can never put a name on the screen. Never
        use this for authorisation decisions: check() is the door.
        """
        token = self.token_from(headers)
        if not token:
            return ""
        try:
            claims = self.verify(token)
        except Exception:  # noqa: BLE001 - cosmetic lookup: any failure means "unknown"
            return ""
        return str(claims.get("email") or "").strip().lower()

    def check(self, path: str, headers: Mapping[str, str], client_ip: str = ""):
        """None to allow, or ``(status, message)`` to refuse.

        Messages are deliberately generic: a stranger learns nothing about
        which check failed. The reason goes to the server log instead.
        """
        if path == HEALTH_PATH and client_ip in ("127.0.0.1", "::1"):
            return None
        token = self.token_from(headers)
        if not token:
            return 401, "sign in required"
        try:
            self.verify(token)
        except Exception as e:  # noqa: BLE001 - any failure is a refusal
            print(f"[loom-access] refused {path}: {type(e).__name__}: {e}", flush=True)
            return 403, "forbidden"
        if is_blocked(path):
            return 403, "not available in the hosted app"
        return None


class _DesktopGuard:
    """Desktop mode: no door at all."""

    def check(self, path, headers, client_ip=""):  # noqa: ARG002
        return None

    def email_of(self, headers):  # noqa: ARG002
        return ""


def build(env: Mapping[str, str] | None = None):
    """The guard for this process. Raises ConfigError when hosted mode is incomplete."""
    return AccessGuard.from_env(env) if is_hosted(env) else _DesktopGuard()
