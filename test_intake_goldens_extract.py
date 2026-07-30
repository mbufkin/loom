#!/usr/bin/env python3
"""Extract/catalog accountability for intake golden packs (wayfinder #6 / #7 / #12).

Offline: real scrub/extract, no models. Materializes office binaries via
tests/fixtures/intake-goldens/generate.py into a temp sources/ tree.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

ACCOUNT_PATH = BASE / "tests" / "fixtures" / "intake-goldens" / "account.py"


def _load_account():
    spec = importlib.util.spec_from_file_location("intake_goldens_account", ACCOUNT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_all_packs_extract_accountability() -> None:
    account = _load_account()
    packs = account.discover_packs()
    assert packs, "expected at least one pack under tests/fixtures/intake-goldens/packs/"
    for pack_dir in packs:
        cfg = account.load_pack(pack_dir)
        if "extract" not in (cfg.get("stages") or []):
            continue
        with tempfile.TemporaryDirectory(prefix=f"intake-{cfg['id']}-") as td:
            sources = Path(td) / "sources"
            account.materialize_sources(pack_dir, sources)
            account.assert_extract_accountability(pack_dir, sources)


def test_pack_many_little_has_volume() -> None:
    """Many-little pack must keep several seed files (shape intent)."""
    account = _load_account()
    pack = BASE / "tests/fixtures/intake-goldens/packs/pack-many-little"
    seeds = list((pack / "seeds").rglob("*"))
    seed_files = [p for p in seeds if p.is_file()]
    assert len(seed_files) >= 4


if __name__ == "__main__":
    test_pack_many_little_has_volume()
    print("ok  test_pack_many_little_has_volume")
    test_all_packs_extract_accountability()
    print("ok  test_all_packs_extract_accountability")
    print("ALL intake golden extract TESTS PASSED")
