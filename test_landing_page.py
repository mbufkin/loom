#!/usr/bin/env python3
"""Guards for the public pages (deploy/hosted-app/landing/: index, signin, site.css).

Why a test for static pages: they are the one public, unauthenticated surface of
Loom. The failure we care about is silent drift: someone pastes an analytics
snippet, a remote font or a wrong sign-in URL, and nothing complains. These checks
fail loudly instead. Stdlib only, so it runs on the Pi host.

Run:  python3 test_landing_page.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LANDING = Path(__file__).resolve().parent / "deploy" / "hosted-app" / "landing"
APP_URL = "https://app.loomaudit.com"
PAGES = ("index.html", "signin.html")
# Only these destinations may appear in an href. Everything else is a mistake.
ALLOWED_HREF = re.compile(
    r"^(#.*|/|/signin|/site\.css|mailto:[^\s]+|" + re.escape(APP_URL) + r"/?)$"
)


def _read(name: str) -> str:
    return (LANDING / name).read_text(encoding="utf-8")


def test_no_scripts_or_remote_resources() -> None:
    for page in PAGES:
        html = _read(page)
        assert "<script" not in html.lower(), f"{page}: must not run JavaScript"
        remote = re.findall(r"""(?:src|srcset|data-src)\s*=\s*["']\s*https?://""", html, re.I)
        assert not remote, f"{page}: remote resources found: {remote}"
        # The only <link> allowed besides the icon is our own stylesheet.
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            if re.search(r"""rel=["']?(?:stylesheet)""", tag, re.I):
                assert 'href="/site.css"' in tag, f"{page}: unexpected stylesheet {tag}"
            else:
                assert re.search(r"""rel=["']icon["']""", tag, re.I), f"{page}: unexpected <link> {tag}"
        assert "style=" not in html, f"{page}: inline style attributes need unsafe-inline"
        assert "<style" not in html.lower(), f"{page}: inline <style> needs unsafe-inline"


def test_stylesheet_is_self_contained() -> None:
    css = _read("site.css")
    assert "@import" not in css, "CSS @import would fetch a remote stylesheet"
    assert not re.findall(r"url\(\s*['\"]?https?://", css, re.I), "remote url() in CSS"


def test_content_security_policy_blocks_everything_by_default() -> None:
    for page in PAGES:
        m = re.search(
            # The policy itself contains single quotes ('none'), so stop only at a double quote.
            r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
            _read(page),
            re.I,
        )
        assert m, f"{page}: missing Content-Security-Policy meta tag"
        csp = m.group(1)
        assert "default-src 'none'" in csp, page
        assert "style-src 'self'" in csp, page
        assert "unsafe-inline" not in csp, f"{page}: inline styles/scripts must stay blocked"
        assert "script-src" not in csp, f"{page}: a script-src would re-open scripts"


def test_every_link_goes_to_the_app_mail_or_these_pages() -> None:
    for page in PAGES:
        hrefs = re.findall(r"""<a\b[^>]*\shref=["']([^"']*)["']""", _read(page), re.I)
        assert hrefs, f"{page}: no links found"
        bad = [h for h in hrefs if not ALLOWED_HREF.match(h)]
        assert not bad, f"{page}: unexpected link destinations: {bad}"


def test_sign_in_flow_points_where_it_should() -> None:
    # Landing page: every "Sign in" goes to our own sign-in page, never straight at the app.
    landing = _read("index.html")
    to_signin = re.findall(r"""href=["']([^"']+)["'][^>]*>\s*Sign in\s*<""", landing)
    assert to_signin and all(h == "/signin" for h in to_signin), to_signin
    assert APP_URL not in landing, "landing page should link to /signin, not the app directly"
    # Sign-in page: the Google button is the one link to the real app.
    signin = _read("signin.html")
    google = re.findall(r"""class="google-btn"\s+href=["']([^"']+)["']""", signin)
    assert google == [APP_URL], google
    assert "Sign in with Google" in signin


def test_signin_page_is_not_indexed_and_has_help_for_denied_users() -> None:
    signin = _read("signin.html")
    assert re.search(r'name="robots"\s+content="noindex"', signin)
    assert "access denied" in signin.lower(), "denied users need on-page guidance"
    assert "mailto:" in signin, "denied users need a way to request access"


def test_basics_for_public_pages() -> None:
    for page in PAGES:
        html = _read(page)
        assert 'lang="en"' in html, page
        assert re.search(r"<title>[^<]{5,}</title>", html), page
        assert 'name="viewport"' in html, page
        assert 'name="description"' in html, page
        assert len(re.findall(r"<h1[ >]", html)) == 1, f"{page}: exactly one <h1>"


def test_no_real_district_or_secret_content() -> None:
    # The repo is public. Pages may show an example, never real documents or secrets.
    for name in (*PAGES, "site.css"):
        # Strip comments first: developer notes may legitimately say "design tokens".
        text = re.sub(r"<!--.*?-->|/\*.*?\*/", "", _read(name), flags=re.S).lower()
        for needle in ("api_key", "apikey", "bearer ", "password", "dallas isd", "carrasco"):
            assert needle not in text, f"{name}: unexpected content on public page: {needle!r}"


def test_web_server_sets_security_headers_and_clean_urls() -> None:
    conf = (LANDING.parent / "landing.nginx.conf").read_text(encoding="utf-8")
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "server_tokens off"):
        assert h in conf, f"landing.nginx.conf missing {h}"
    assert "try_files $uri $uri/ $uri.html =404" in conf, "/, clean /signin URL or 404 fallback lost"
    assert "autoindex" not in conf, "directory listing must stay off"
    # A location block that adds its own header would silently drop the server-level ones.
    # Strip comments first: prose that mentions "location" must not look like a block.
    code = re.sub(r"(?m)^\s*#.*$", "", conf)
    locations = re.findall(r"location\s[^{;]*\{([^}]*)\}", code)
    assert locations, "expected a location block"
    assert not any("add_header" in body for body in locations), "add_header inside a location"
    assert not (LANDING / "_headers").exists(), "_headers is Pages-only and would be served publicly"


def test_public_pages_service_is_loopback_only_and_read_only() -> None:
    compose = (LANDING.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8791:8080"' in compose, "loom-landing must bind to loopback only"
    assert not re.search(r'"(?:0\.0\.0\.0:)?8791:8080"', compose), "loom-landing exposed on the LAN"
    block = compose[compose.index("loom-landing:"):]
    for needle in ("read_only: true", "cap_drop: [ALL]", "no-new-privileges:true"):
        assert needle in block, f"loom-landing missing {needle}"
    assert "secrets" not in block and "/data" not in block, "public service must not see app data"


def test_tunnel_routes_public_names_to_the_static_service_only() -> None:
    tunnel = (LANDING.parent / "cloudflared" / "loom.yml").read_text(encoding="utf-8")
    assert re.search(r"hostname: app\.loomaudit\.com\s+service: http://127\.0\.0\.1:8790", tunnel)
    for host in ("loomaudit.com", "www.loomaudit.com"):
        assert re.search(
            rf"hostname: {re.escape(host)}\s+service: http://127\.0\.0\.1:8791", tunnel
        ), f"{host} must go to the static service on 8791"


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
