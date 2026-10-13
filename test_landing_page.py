#!/usr/bin/env python3
"""Guards for the public landing page (deploy/hosted-app/landing/index.html).

Why a test for a static page: it is the one public, unauthenticated surface of
Loom. The failure we care about is silent drift: someone pastes an analytics
snippet, a remote font or a hard-coded wrong sign-in URL, and nothing complains.
These checks fail loudly instead. Stdlib only, so it runs on the Pi host.

Run:  python3 test_landing_page.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LANDING = Path(__file__).resolve().parent / "deploy" / "hosted-app" / "landing"
APP_URL = "https://app.loomaudit.com"
# Only these destinations may appear in an href. Everything else is a mistake.
ALLOWED_HREF = re.compile(r"^(#.*|/|mailto:[^\s]+|" + re.escape(APP_URL) + r"/?)$")


def _html() -> str:
    return (LANDING / "index.html").read_text(encoding="utf-8")


def test_no_scripts_or_remote_resources() -> None:
    html = _html()
    assert "<script" not in html.lower(), "landing page must not run JavaScript"
    # Any src/href/url() pointing off-page would be a third-party request.
    remote = re.findall(r"""(?:src|srcset|data-src)\s*=\s*["']\s*https?://""", html, re.I)
    assert not remote, f"remote resources found: {remote}"
    assert not re.findall(r"url\(\s*['\"]?https?://", html, re.I), "remote url() in CSS"
    assert "@import" not in html, "CSS @import would fetch a remote stylesheet"
    assert not re.findall(r"""<link[^>]+rel=["']?(?:stylesheet|preload|preconnect)""", html, re.I)


def test_content_security_policy_blocks_everything_by_default() -> None:
    m = re.search(
        # The policy itself contains single quotes ('none'), so only stop at a double quote.
        r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
        _html(),
        re.I,
    )
    assert m, "missing Content-Security-Policy meta tag"
    csp = m.group(1)
    assert "default-src 'none'" in csp
    assert "script-src" not in csp, "a script-src would re-open scripts"


def test_every_link_goes_to_the_app_mail_or_the_page_itself() -> None:
    hrefs = re.findall(r"""<a\b[^>]*\shref=["']([^"']*)["']""", _html(), re.I)
    assert hrefs, "no links found"
    bad = [h for h in hrefs if not ALLOWED_HREF.match(h)]
    assert not bad, f"unexpected link destinations: {bad}"


def test_sign_in_points_at_the_real_app() -> None:
    html = _html()
    sign_in = re.findall(r"""href=["']([^"']+)["'][^>]*>\s*Sign in\s*<""", html)
    assert sign_in, "no 'Sign in' link"
    assert all(h.rstrip("/") == APP_URL for h in sign_in), sign_in


def test_basics_for_a_public_page() -> None:
    html = _html()
    assert 'lang="en"' in html
    assert re.search(r"<title>[^<]{5,}</title>", html)
    assert 'name="viewport"' in html
    assert 'name="description"' in html
    assert re.search(r"<h1[ >]", html) and len(re.findall(r"<h1[ >]", html)) == 1


def test_no_real_district_or_secret_content() -> None:
    # The repo is public. The page may show an example, never real documents.
    # Strip comments first: developer notes may legitimately say "design tokens".
    html = re.sub(r"<!--.*?-->|/\*.*?\*/", "", _html(), flags=re.S).lower()
    for needle in ("api_key", "apikey", "bearer ", "password", "dallas isd", "carrasco"):
        assert needle not in html, f"unexpected content on public page: {needle!r}"


def test_headers_file_present() -> None:
    headers = (LANDING / "_headers").read_text(encoding="utf-8")
    for h in ("X-Content-Type-Options: nosniff", "X-Frame-Options: DENY", "Referrer-Policy"):
        assert h in headers, f"_headers missing {h}"


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
