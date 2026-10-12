"""Hosted-mode door in front of ui/server.py (ui/hosted_guard.py).

Fully offline: a locally generated RSA key signs the tokens, and a tiny local
HTTP server plays Cloudflare's /cdn-cgi/access/certs endpoint for the real
PyJWKClient. Needs requirements-hosted.txt (run inside the hosted image):

    docker run --rm --entrypoint python loom-app:latest test_hosted_guard.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "ui"))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

import hosted_guard  # noqa: E402

ISSUER = "https://test-team.cloudflareaccess.com"
AUD = "test-aud-0123456789abcdef"
EMAIL = "admin@example.org"


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private_key, kid: str) -> dict:
    d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    d.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return d


class FakeCerts:
    """Serves {"keys": [...]} like Cloudflare's certs endpoint; keys are mutable."""

    def __init__(self):
        self.keys: list[dict] = []
        self.hits = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits += 1
                body = json.dumps({"keys": outer.keys}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/cdn-cgi/access/certs"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


KEY = _new_key()
OTHER_KEY = _new_key()
CERTS = FakeCerts()
CERTS.keys = [_jwk(KEY, "kid-1")]


def make_token(key=KEY, kid="kid-1", **overrides) -> str:
    now = int(time.time())
    claims = {
        "aud": [AUD],
        "iss": ISSUER,
        "email": EMAIL,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
        "sub": "user-1",
        "type": "app",
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def make_guard(**kw) -> hosted_guard.AccessGuard:
    return hosted_guard.AccessGuard(
        issuer=ISSUER,
        audience=AUD,
        jwks_client=jwt.PyJWKClient(CERTS.url, cache_keys=True),
        **kw,
    )


def hdr(token: str) -> dict:
    return {hosted_guard.TOKEN_HEADER: token}


class TokenRules(unittest.TestCase):
    def setUp(self):
        self.g = make_guard()

    def test_valid_header_token_passes(self):
        self.assertIsNone(self.g.check("/api/projects", hdr(make_token())))

    def test_valid_cookie_token_passes(self):
        cookie = {"Cookie": f"other=1; {hosted_guard.TOKEN_COOKIE}={make_token()}"}
        self.assertIsNone(self.g.check("/", cookie))

    def test_ui_files_need_a_token_too(self):
        self.assertEqual(self.g.check("/", {})[0], 401)
        self.assertEqual(self.g.check("/assets/index.js", {})[0], 401)

    def test_missing_token_is_401(self):
        self.assertEqual(self.g.check("/api/version", {})[0], 401)

    def test_wrong_audience_is_403(self):
        t = make_token(aud=["some-other-app"])
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_wrong_issuer_is_403(self):
        t = make_token(iss="https://evil.cloudflareaccess.com")
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_expired_is_403(self):
        now = int(time.time())
        t = make_token(iat=now - 7200, nbf=now - 7200, exp=now - 3600)
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_small_clock_skew_is_tolerated(self):
        now = int(time.time())
        t = make_token(exp=now - 5)
        self.assertIsNone(self.g.check("/api/version", hdr(t)))

    def test_not_yet_valid_is_403(self):
        now = int(time.time())
        t = make_token(nbf=now + 3600, iat=now)
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_missing_exp_is_403(self):
        t = make_token(exp=None)
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_bad_signature_is_403(self):
        # Right kid, wrong key: the classic forged token.
        t = make_token(key=OTHER_KEY, kid="kid-1")
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_tampered_payload_is_403(self):
        head, _, sig = make_token().split(".")
        forged = jwt.utils.base64url_encode(
            json.dumps({"aud": [AUD], "iss": ISSUER, "exp": 9999999999, "iat": 1}).encode()
        ).decode()
        self.assertEqual(self.g.check("/api/version", hdr(f"{head}.{forged}.{sig}"))[0], 403)

    def test_hs256_and_none_algorithms_are_refused(self):
        now = int(time.time())
        claims = {"aud": [AUD], "iss": ISSUER, "iat": now, "exp": now + 600}
        hs = jwt.encode(claims, "guessable", algorithm="HS256", headers={"kid": "kid-1"})
        none = jwt.encode(claims, None, algorithm="none", headers={"kid": "kid-1"})
        self.assertEqual(self.g.check("/api/version", hdr(hs))[0], 403)
        self.assertEqual(self.g.check("/api/version", hdr(none))[0], 403)

    def test_garbage_token_is_403(self):
        self.assertEqual(self.g.check("/api/version", hdr("not-a-jwt"))[0], 403)

    def test_unknown_kid_is_403(self):
        t = make_token(key=OTHER_KEY, kid="kid-nobody-published")
        self.assertEqual(self.g.check("/api/version", hdr(t))[0], 403)

    def test_rotated_key_is_picked_up_by_refetch(self):
        new_key = _new_key()
        g = make_guard()
        self.assertIsNone(g.check("/api/version", hdr(make_token())))  # caches kid-1
        CERTS.keys = [_jwk(KEY, "kid-1"), _jwk(new_key, "kid-2")]
        try:
            self.assertIsNone(g.check("/api/version", hdr(make_token(key=new_key, kid="kid-2"))))
        finally:
            CERTS.keys = [_jwk(KEY, "kid-1")]

    def test_email_allowlist(self):
        g = make_guard(allowed_emails=frozenset({"admin@example.org"}))
        self.assertIsNone(g.check("/api/version", hdr(make_token(email="Admin@Example.org"))))
        self.assertEqual(g.check("/api/version", hdr(make_token(email="x@example.org")))[0], 403)
        self.assertEqual(g.check("/api/version", hdr(make_token(email=None)))[0], 403)

    def test_desktop_only_routes_are_403_with_a_valid_token(self):
        t = make_token()
        for path in (
            "/api/install-deps",
            "/api/models/key",
            "/api/models/select",
            "/api/models/discover",
            "/api/models/remote",
            "/api/models/providers",
            "//api//models/select/",
        ):
            self.assertEqual(self.g.check(path, hdr(t))[0], 403, path)

    def test_healthz_only_without_token_from_inside_the_container(self):
        self.assertIsNone(self.g.check("/healthz", {}, "127.0.0.1"))
        self.assertEqual(self.g.check("/healthz", {}, "172.18.0.1")[0], 401)


class Config(unittest.TestCase):
    def test_desktop_mode_allows_everything(self):
        g = hosted_guard.build({})
        self.assertIsNone(g.check("/api/install-deps", {}))
        self.assertIsNone(g.check("/api/models/key", {}))

    def test_hosted_mode_fails_closed_without_settings(self):
        for env in (
            {"LOOM_HOSTED": "1"},
            {"LOOM_HOSTED": "1", "LOOM_ACCESS_AUD": AUD},
            {"LOOM_HOSTED": "1", "LOOM_ACCESS_TEAM_DOMAIN": "test-team"},
        ):
            with self.assertRaises(hosted_guard.ConfigError, msg=str(env)):
                hosted_guard.build(env)

    def test_from_env_builds_the_certs_url_from_the_team(self):
        seen = []
        g = hosted_guard.AccessGuard.from_env(
            {"LOOM_ACCESS_TEAM_DOMAIN": "loomaudit", "LOOM_ACCESS_AUD": AUD},
            jwks_factory=lambda url: seen.append(url) or object(),
        )
        self.assertEqual(g.issuer, "https://loomaudit.cloudflareaccess.com")
        self.assertEqual(seen, ["https://loomaudit.cloudflareaccess.com/cdn-cgi/access/certs"])

    def test_team_domain_forms(self):
        n = hosted_guard.normalise_team_domain
        self.assertEqual(n("loomaudit"), "https://loomaudit.cloudflareaccess.com")
        self.assertEqual(n("loomaudit.cloudflareaccess.com"), "https://loomaudit.cloudflareaccess.com")
        self.assertEqual(n("https://loomaudit.cloudflareaccess.com/"), "https://loomaudit.cloudflareaccess.com")


class NvidiaKeyFallback(unittest.TestCase):
    """The container has no keyring; NVIDIA_API_KEY must work, for NIM only."""

    def setUp(self):
        import loom_keys

        self.lk = loom_keys
        names = ("NVIDIA_API_KEY", "LOOM_API_KEY", loom_keys._env_name(loom_keys.NVIDIA_HOST))
        self._saved = {k: os.environ.pop(k, None) for k in names}
        os.environ["NVIDIA_API_KEY"] = "nvapi-test-not-real"

    def tearDown(self):
        os.environ.pop("NVIDIA_API_KEY", None)
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_used_for_nim(self):
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.assertEqual(self.lk.get_key(url), "nvapi-test-not-real")

    def test_never_sent_elsewhere(self):
        self.assertNotEqual(
            self.lk.get_key("https://example.com/v1/chat/completions"),
            "nvapi-test-not-real",
        )


class LiveServer(unittest.TestCase):
    """The real Handler in hosted mode answers before routing."""

    @classmethod
    def setUpClass(cls):
        cls._env = mock.patch.dict(os.environ, {"LOOM_HOSTED": "1"})
        cls._env.start()
        import server

        cls.server = server
        cls._saved_guard = server.GUARD
        server.GUARD = make_guard()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.server.GUARD = cls._saved_guard
        cls._env.stop()

    def _req(self, path, method="GET", headers=None, body=None):
        req = urllib.request.Request(
            self.base + path, method=method, headers=headers or {}, data=body
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, dict(res.headers)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers)

    def test_version_needs_a_valid_token(self):
        self.assertEqual(self._req("/api/version")[0], 401)
        self.assertEqual(self._req("/api/version", headers=hdr("junk"))[0], 403)
        status, headers = self._req("/api/version", headers=hdr(make_token()))
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_ui_root_needs_a_token(self):
        self.assertEqual(self._req("/")[0], 401)

    def test_post_without_token_is_refused_before_routing(self):
        self.assertEqual(self._req("/api/projects", "POST", body=b"{}")[0], 401)

    def test_settings_routes_are_forbidden(self):
        t = hdr(make_token())
        self.assertEqual(self._req("/api/install-deps", "POST", t, b"")[0], 403)
        self.assertEqual(self._req("/api/models/select", "POST", t, b"{}")[0], 403)
        self.assertEqual(self._req("/api/models/key", "POST", t, b"{}")[0], 403)
        self.assertEqual(self._req("/api/models/providers", headers=t)[0], 403)

    def test_organise_and_run_needs_a_token_and_is_not_desktop_only(self):
        path = "/api/projects/no-such-curriculum/organise-and-run"
        self.assertEqual(self._req(path, "POST", body=b"{}")[0], 401)
        self.assertEqual(self._req(path, "POST", hdr("junk"), b"{}")[0], 403)
        # With a valid token it reaches the router: 404 for a curriculum that
        # does not exist, not the guard's 403. Nothing is spawned.
        self.assertEqual(self._req(path, "POST", hdr(make_token()), b"{}")[0], 404)

    def test_healthz_from_localhost(self):
        self.assertEqual(self._req("/healthz")[0], 200)

    def test_main_refuses_to_start_without_access_settings(self):
        saved = self.server.GUARD
        self.server.GUARD = None
        try:
            with mock.patch.object(sys, "argv", ["server.py", "--port", "0"]):
                self.assertEqual(self.server.main(), 78)
        finally:
            self.server.GUARD = saved


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        CERTS.close()
