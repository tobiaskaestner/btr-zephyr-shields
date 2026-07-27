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

from conftest import REPO_ROOT, zephyr_base
from rigexp.ctypes_registry import BINDINGS, load_types
from rigexp.edt_build import ensure_devicetree_on_path

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
    types = load_types()

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
