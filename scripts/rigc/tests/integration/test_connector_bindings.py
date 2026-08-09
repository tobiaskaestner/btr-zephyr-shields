"""The unified connector-type files (dts/bindings/connectors/<type>.yaml)
are REAL edtlib bindings — socket schema plus the plug contract as plug,*
vendor-namespaced extension keys (opaque to edtlib, preserved in
Binding.raw; zephyr rig-branch commit 1a657124349).

Why edtlib-loading them here matters: edtlib's binding scan is
content-sniffing — pass 2 only ever parses a binding file whose compatible
string appears in the current devicetree. socket,i2c-port never does
(its sockets are shield-synthesized and lowered to plain mux children with
no compatible), so WITHOUT this test that file is validated by nothing:
it could go schema-invalid and no build would notice until the day some
DT carries the compatible. This test is that day, every run.
"""
from __future__ import annotations

import glob
import os
import sys

from conftest import FIXTURES_DIR, REPO_ROOT, zephyr_base

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.registry import BINDINGS, load_types  # noqa: E402
from rigc.edt_build import ensure_devicetree_on_path  # noqa: E402

ensure_devicetree_on_path()
from devicetree import edtlib  # noqa: E402


def _fname2path() -> dict:
    """Basename→path over both bindings roots (zephyr's + ours), enough to
    resolve the include: chains of the connector bindings — the same
    mapping shape edtlib.EDT itself builds over its bindings dirs."""
    mapping: dict = {}
    for root in (os.path.join(zephyr_base(), "dts", "bindings"),
                 os.path.join(str(REPO_ROOT), "dts", "bindings")):
        for path in glob.glob(os.path.join(root, "**", "*.yaml"), recursive=True):
            mapping.setdefault(os.path.basename(path), path)
    return mapping


def test_unified_connector_bindings_are_valid_edtlib_bindings() -> None:
    files = sorted(glob.glob(os.path.join(BINDINGS, "*.yaml")))
    assert files, f"no connector-type bindings found under {BINDINGS}"

    fname2path = _fname2path()
    types, _deps = load_types()

    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        binding = edtlib.Binding(path, fname2path, require_compatible=True)
        # Identity: filename and compatible agree (the loader keys types by
        # filename; pass 2 keys the same file by compatible).
        assert binding.compatible == f"socket,{name}", path
        # The plug contract rides as plug,* extension keys and survives
        # edtlib parsing (Binding.raw round-trip).
        assert "plug,positions" in binding.raw, path
        assert "plug,bus-proxies" in binding.raw, path
        # And the rig loader assembled a ConnectorType from the same file.
        assert name in types, path


def test_fixture_nexus_type_is_registry_visible() -> None:
    """The ceiling T0 hit, lifted: registry.load_types can see the
    fixture connector type when pointed at its directory explicitly, and
    still sees the four real types when it is not — the same function, two
    different roots, proving the default-preserving fallback rather than
    merely asserting it. Moved here (not test_reference_shields.py, where
    it was authored) because the second half asserts directly on
    repo-production connector-type names -- integration by that half's
    purpose, and no module may mix unit and integration tests."""
    fixture_types, _deps = load_types(
        connector_dirs=[str(FIXTURES_DIR / "dts" / "connectors")],
        header_dirs=[str(FIXTURES_DIR / "include")])
    assert set(fixture_types) == {"fixture-nexus"}
    ctype = fixture_types["fixture-nexus"]
    assert set(ctype.positions) == {"D0", "D1", "CS"}
    assert ctype.bus_proxies == ["i2c", "spi"]
    assert ctype.cs_pool == {"spi": [4]}

    real_types, _deps = load_types()
    assert set(real_types) == {"arduino-r3", "grove", "i2c-port", "mikrobus"}
    assert BINDINGS == str(REPO_ROOT / "dts" / "bindings" / "connectors")
