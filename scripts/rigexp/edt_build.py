# SPDX-License-Identifier: BSD-3-Clause
"""Standalone edtlib.EDT construction over a single real devicetree file.

This is a generic reader layer: it knows nothing about rigs, sockets, or any
other rigexp product concept -- only devicetree/edtlib mechanics plus the
one piece of Zephyr CMake convention (a build_info.yml's cmake.devicetree
section) needed to recover the include/bindings directories a real west
build used. It is the candidate for upstreaming into python-devicetree
itself, so it must never import a rigexp product module (model / analyzer /
emitter / diag) -- only the standard library, PyYAML, and devicetree.edtlib.

Recipe (mirrors cmake/modules/dts.cmake + scripts/dts/gen_defines.py): cpp
the board .dts with -nostdinc plus one -isystem per include dir and
-D__DTS__ (no other defines -- linemarkers stay intact, so dtlib/edtlib
source references point at the ORIGINAL board files, not the preprocessed
temp file), then hand the preprocessed file plus the bindings dirs to
edtlib.EDT.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

import yaml

_ZEPHYR_BASE = os.environ.get("ZEPHYR_BASE")
if not _ZEPHYR_BASE:
    raise RuntimeError(
        "edt_build: $ZEPHYR_BASE is not set -- it is required to locate "
        "zephyr's devicetree library (scripts/dts/python-devicetree/src). "
        "Export it (the zephyr-rigs tree) before importing this module.")
_DT_SRC = os.path.join(_ZEPHYR_BASE, "scripts", "dts", "python-devicetree", "src")
if _DT_SRC not in sys.path:
    sys.path.insert(0, _DT_SRC)

from devicetree import edtlib  # noqa: E402


@dataclass(frozen=True)
class BuildRecipe:
    """The two directory lists a real Zephyr configure step feeds to the
    devicetree preprocessor and to edtlib.

    include_dirs:
      -isystem search directories for the C preprocessor pass.

    bindings_dirs:
      Directories edtlib recursively globs for .yaml binding files.
    """
    include_dirs: List[str]
    bindings_dirs: List[str]


def recipe_from_build_info(build_info_path: str) -> BuildRecipe:
    """Recover the recipe a real west build used from its
    <build-dir>/build_info.yml.

    dts.cmake's dts_build_info_output() records the exact directories
    passed to the board-DTS preprocessor and to edtlib under
    cmake.devicetree.include-dirs / cmake.devicetree.bindings-dirs -- this
    is a read of that record, not a re-derivation, so it stays correct
    across Zephyr versions without mirroring pre_dt.cmake.

    Also appends cmake.board.path (written by boards.cmake:
    build_info(board path PATH ${BOARD_DIRECTORIES}) -- every board
    directory the configure resolved, base board first, then any hwmv2
    board-EXTENSION directories registered against it). Plain boards get
    exactly one entry here (their own dir, already implied by
    include-dirs' subpaths); an extension variant's own dts lives in a
    DIFFERENT directory than the base board it #includes, so its base
    directory must be on the cpp search path too for that quoted include
    to resolve -- this is the standalone-read analog of cmake/dts.cmake
    appending the same BOARD_DIRECTORIES list to the expander's
    --include-dir args for the in-build path.
    """
    with open(build_info_path) as f:
        doc = yaml.safe_load(f)
    devicetree = doc["cmake"]["devicetree"]
    board_paths = doc["cmake"].get("board", {}).get("path", [])
    if isinstance(board_paths, str):
        board_paths = [board_paths]
    return BuildRecipe(
        include_dirs=list(devicetree["include-dirs"]) + list(board_paths),
        bindings_dirs=list(devicetree["bindings-dirs"]))


def preprocess(dts_path: str, include_dirs: List[str], out_path: str) -> None:
    """cpp dts_path, exactly as a real board-DTS preprocess does: no
    standard include path, one -isystem per include_dirs entry, and
    -D__DTS__ (the sole macro Zephyr's own board-DTS cpp step defines)."""
    cmd = ["gcc", "-E", "-x", "assembler-with-cpp", "-nostdinc"]
    for include_dir in include_dirs:
        cmd += ["-isystem", include_dir]
    cmd += ["-D__DTS__", dts_path, "-o", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cpp failed on {dts_path}:\n{result.stderr}")


def build_edt(dts_path: str, recipe: BuildRecipe, workdir: str) -> edtlib.EDT:
    """Build a standalone edtlib.EDT over one .dts file -- no app, no
    overlay: this pass reads only the board's own devicetree, never app or
    overlay context.

    infer_binding_for_paths covers the two paths a real build always
    carries without a dedicated binding (/zephyr,user, /cpus), matching
    what a normal Zephyr configure does for the same board.
    """
    os.makedirs(workdir, exist_ok=True)
    pre = os.path.join(workdir, os.path.basename(dts_path) + ".pre")
    preprocess(dts_path, recipe.include_dirs, pre)
    return edtlib.EDT(
        pre, recipe.bindings_dirs,
        default_prop_types=True,
        infer_binding_for_paths=["/zephyr,user", "/cpus"])
