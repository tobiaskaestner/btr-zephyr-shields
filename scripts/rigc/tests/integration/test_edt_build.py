# SPDX-License-Identifier: BSD-3-Clause
"""Unit tests for edt_build.py, the generic devicetree/edtlib reader layer:
it knows nothing about rigs, sockets, or any other product concept -- only
devicetree/edtlib mechanics plus one piece of Zephyr CMake convention (a
build_info.yml's cmake.devicetree section), so it is the candidate for
upstreaming into python-devicetree itself. Its tests therefore travel with
it, BSD-3, in the test_edtlib.py idiom: module-level test_* functions,
plain asserts, no rigexp product imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import edt_build  # noqa: E402

pytestmark = pytest.mark.unit


def test_recipe_from_build_info(tmp_path: Path) -> None:
    """recipe_from_build_info reads exactly the
    cmake.devicetree.include-dirs / bindings-dirs keys a real
    build_info.yml carries, against a tiny hand-written fixture."""
    build_info = tmp_path / "build_info.yml"
    build_info.write_text(
        "cmake:\n"
        "  devicetree:\n"
        "    include-dirs:\n"
        "      - /a/include\n"
        "      - /b/include\n"
        "    bindings-dirs:\n"
        "      - /a/dts/bindings\n"
        "      - /b/dts/bindings\n")
    recipe = edt_build.recipe_from_build_info(str(build_info))
    assert recipe.include_dirs == ["/a/include", "/b/include"]
    assert recipe.bindings_dirs == ["/a/dts/bindings", "/b/dts/bindings"]
