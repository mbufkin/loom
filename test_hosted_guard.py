"""Hosted-mode door in front of ui/server.py (ui/hosted_guard.py).

The pure checks cover the rule table; the live test proves the server applies
it before routing, which is the part a refactor of do_GET/do_POST could lose.
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "ui"))

import hosted_guard  # noqa: E402

SECRET = "test-secret-not-real"
ENV = {hosted_guard.SECRET_ENV: SECRET}
OK = {hosted_guard.SECRET_HEADER: SECRET}


class GuardRules(unittest.TestCase):
    def test_desktop_mode_allows_everything(self):
        self.assertIsNone(hosted_guard.check("/api/install-deps", {}, env={}))
        self.assertIsNone(hosted_guard.check("/api/models/key", {}, env={}))

    def test_missing_or_wrong_secret_is_401(self):
        self.assertEqual(hosted_guard.check("/api/version", {}, env=ENV)[0], 401)
        bad = {hosted_guard.SECRET_HEADER: SECRET + "x"}
        self.assertEqual(hosted_guard.check("/api/version", bad, env=ENV)[0], 401)

    def test_right_secret_allows_normal_routes(self):
        for path in ("/api/version", "/api/projects", "/api/projects/x/documents"):
            self.assertIsNone(hosted_guard.check(path, OK, env=ENV), path)

    def test_desktop_only_routes_are_403_even_with_secret(self):
        for path in (
            "/api/install-deps",
            "/api/models/key",
            "/api/models/select",
            "/api/models/discover",
            "/api/models/remote",
            "//api//models/select/",
        ):
            self.assertEqual(hosted_guard.check(path, OK, env=ENV)[0], 403, path)

    def test_prefix_match_is_on_whole_segments(self):
        self.assertFalse(hosted_guard.is_blocked("/api/modelsets"))
        self.assertTrue(hosted_guard.is_blocked("/api/models"))


class NvidiaKeyFallback(unittest.TestCase):
    """The container has no keyring; NVIDIA_API_KEY must work, for NIM only."""

    def setUp(self):
        import loom_keys

        self.lk = loom_keys
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ("NVIDIA_API_KEY", "LOOM_API_KEY", loom_keys._env_name(loom_keys.NVIDIA_HOST))
        }
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
    """The real Handler, with hosted mode on, answers before routing."""

    @classmethod
    def setUpClass(cls):
        cls._saved_env = os.environ.get(hosted_guard.SECRET_ENV)
        os.environ[hosted_guard.SECRET_ENV] = SECRET
        import server

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._saved_env is None:
            os.environ.pop(hosted_guard.SECRET_ENV, None)
        else:
            os.environ[hosted_guard.SECRET_ENV] = cls._saved_env

    def _status(self, path, method="GET", headers=None, body=None):
        req = urllib.request.Request(
            self.base + path, method=method, headers=headers or {}, data=body
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_version_needs_the_secret(self):
        self.assertEqual(self._status("/api/version"), 401)
        self.assertEqual(self._status("/api/version", headers=OK), 200)

    def test_post_without_secret_is_refused_before_routing(self):
        self.assertEqual(self._status("/api/projects", "POST", body=b"{}"), 401)

    def test_install_and_model_writes_are_forbidden(self):
        self.assertEqual(self._status("/api/install-deps", "POST", OK, b""), 403)
        self.assertEqual(self._status("/api/models/select", "POST", OK, b"{}"), 403)
        self.assertEqual(self._status("/api/models/providers", headers=OK), 403)


if __name__ == "__main__":
    unittest.main()
