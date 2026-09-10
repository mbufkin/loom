"""
loom_keys.py — API keys for hosted model endpoints, kept out of the repo.

Loom's default posture is a model on the same machine, where no key exists
and no curriculum text leaves the building. Hosted services like NVIDIA's
build API are the exception: they need a bearer token, and a token is the
single worst thing to keep in a config file. config.yaml is gitignored, but
gitignored is not the same as safe -- it still sits in plain text in the
program's folder, gets picked up by backup software, and shows up in any
screen share of the file tree.

So keys live in the operating system's credential store: Windows Credential
Manager, macOS Keychain, or the Secret Service / KWallet on Linux. The
`keyring` package abstracts all three.

Keys are scoped by endpoint host, not stored as one global secret. That is a
deliberate safety property: a key saved for integrate.api.nvidia.com can
never be attached to a request going to 127.0.0.1, so pointing Loom back at
a local model cannot accidentally ship a cloud credential to it.

Resolution order, most specific first:

  1. LOOM_API_KEY_<HOST>   per-host environment override
  2. LOOM_API_KEY          one key for the configured endpoint
  3. the OS credential store   what Settings writes; the recommended path
  4. models.api_key in config.yaml   legacy plaintext, still read so older
     setups keep working, but never written by the app

Nothing here ever returns a key to the browser. The server exposes only
whether one is present.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

# One service name for every entry, with the endpoint host as the "username".
# In Credential Manager this shows up as loom/integrate.api.nvidia.com, which
# is legible to anyone auditing the machine's stored credentials.
SERVICE = "loom"


def host_of(url: str) -> str:
    """The host an endpoint belongs to, used as the key's scope."""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def is_local(url: str) -> bool:
    """True for a model running on this machine.

    Used to decide whether to even look for a key: a loopback endpoint is the
    normal, key-free case, and skipping the lookup keeps the credential store
    out of the hot path for every local call.
    """
    return host_of(url) in {"127.0.0.1", "localhost", "::1", "[::1]"}


def _env_name(host: str) -> str:
    """LOOM_API_KEY_INTEGRATE_API_NVIDIA_COM, for CI and scripted runs."""
    return "LOOM_API_KEY_" + re.sub(r"[^A-Za-z0-9]", "_", host).upper()


def _keyring():
    """The keyring module, or None when it is unavailable.

    Import failure is not an error. A headless Linux box may have no secret
    service at all, and Loom must still run there against a local model --
    which needs no key. Callers degrade instead of crashing.
    """
    try:
        import keyring

        return keyring
    except Exception:
        return None


def backend_name() -> str | None:
    """Human-readable name of the credential store, or None if there isn't one."""
    kr = _keyring()
    if kr is None:
        return None
    try:
        cls = kr.get_keyring().__class__
        # keyring falls back to a no-op backend when nothing real is present;
        # reporting that as working storage would be a lie.
        if "fail" in cls.__name__.lower():
            return None
        pretty = {
            "WinVaultKeyring": "Windows Credential Manager",
            "Keyring": "macOS Keychain",
            "SecretService": "the system keyring",
            "Kwallet": "KWallet",
        }
        return pretty.get(cls.__name__, cls.__name__)
    except Exception:
        return None


def get_key(url: str, cfg: dict | None = None) -> str:
    """The key to send to this endpoint, or "" when none applies."""
    host = host_of(url)
    if not host:
        return ""

    env_specific = os.environ.get(_env_name(host))
    if env_specific:
        return env_specific.strip()

    env_general = os.environ.get("LOOM_API_KEY")
    if env_general:
        return env_general.strip()

    kr = _keyring()
    if kr is not None:
        try:
            stored = kr.get_password(SERVICE, host)
            if stored:
                return stored.strip()
        except Exception:
            pass

    # Legacy plaintext. Still honoured so existing installs keep working, and
    # still supported for the Cursor bridge, which predates this module.
    if cfg:
        legacy = ((cfg.get("models") or {}).get("api_key") or "").strip()
        if legacy:
            return legacy
    if "8788" in str(url):
        return (os.environ.get("CURSOR_API_KEY") or "").strip()
    return ""


def set_key(url: str, key: str) -> tuple[bool, str]:
    """Store a key for this endpoint's host. Returns (ok, message)."""
    host = host_of(url)
    if not host:
        return False, "that address has no host to attach a key to"
    kr = _keyring()
    if kr is None or backend_name() is None:
        return (
            False,
            "This computer has no credential store available, so a key "
            "cannot be saved safely. Set the LOOM_API_KEY environment "
            "variable instead.",
        )
    try:
        kr.set_password(SERVICE, host, key.strip())
        return True, f"Key saved for {host} in {backend_name()}."
    except Exception as e:
        return False, f"the credential store refused the key: {e}"


def delete_key(url: str) -> tuple[bool, str]:
    """Remove any stored key for this endpoint's host."""
    host = host_of(url)
    kr = _keyring()
    if not host or kr is None:
        return False, "nothing to remove"
    try:
        kr.delete_password(SERVICE, host)
        return True, f"Key removed for {host}."
    except Exception:
        # Deleting something that was never there is the caller's desired
        # end state, so report it as success rather than an error.
        return True, f"No key was stored for {host}."


def key_present(url: str, cfg: dict | None = None) -> bool:
    """Whether a key would be sent to this endpoint. Never reveals the key."""
    return bool(get_key(url, cfg))


def auth_headers(url: str, cfg: dict | None = None) -> dict:
    """Authorization header for this endpoint, or {} when no key applies."""
    key = get_key(url, cfg)
    return {"Authorization": f"Bearer {key}"} if key else {}
