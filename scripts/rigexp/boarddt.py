"""Board DT reader — expander-side input (Conv. 4: 'the expander reads the
board DT to find socket nodes by compatible'). THE FLIP (Bridge-A rewrite,
saferails 2/6/8): this module used to parse a bundled `common-dts` scaffold
standalone with dtlib; it now delegates entirely to `board_edt`/`edt_build`'s
real `edtlib.EDT` reader over the board's OWN devicetree — the shadow
dual-read (`tests/test_board_read.py`, formerly `test_board_dualread.py`)
proved this produces the SAME `model.Board` the scaffold did, on every axis,
for all four board clones.

This module keeps two responsibilities of its own, both about board
RESOLUTION rather than DT mechanics (those live in `board_edt`/`edt_build`):

  * board NAME -> `.dts` path, explicit (the in-build path: rig.cmake already
    resolved BOARD_DIR via boards.cmake, so it passes `--board-dts` directly)
    or discovered (the standalone/CLI fallback, via zephyr's own
    `list_boards.py` — consumed, not forked, mirroring how `list_shields.py`
    is consumed elsewhere in this tree).

  * the two board-level diagnostics that keep `phys-board` physically
    meaningful: a board that does not exist at all (discovery finds no such
    directory) vs. a board that exists but never opted in (its devicetree
    declares no `socket,*` node — Conv. 4's opt-in mechanism).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from . import board_edt
from .diag import Diagnostics
from .dtsio import MODULE_ROOT
from .edt_build import BuildRecipe
from .model import Board


def load_board(name: str, workdir: str, diags: Diagnostics,
               board_dts: Optional[str] = None,
               recipe: Optional[BuildRecipe] = None) -> Optional[Board]:
    """Resolve board `name` to a `model.Board`, or None (+ a `phys-board`
    Diagnostic) if it can't be read at all.

    `board_dts` / `recipe` are the two inputs `board_edt.load_board` needs
    (see `edt_build.BuildRecipe`). The IN-BUILD path (rig.cmake) always
    passes both explicitly — BOARD_DIR is already resolved by boards.cmake
    long before the expander runs, and rig.cmake computes the recipe itself
    (saferail 13). Leaving `board_dts` None triggers the standalone/CLI
    discovery fallback below; leaving `recipe` None (whether or not
    `board_dts` was given) is a caller-configuration gap, reported the same
    way as any other board-resolution failure — see the `recipe is None`
    branch.
    """
    if board_dts is None:
        board_dts = _discover_board_dts(name, diags)
        if board_dts is None:
            return None
    elif not os.path.isfile(board_dts):
        diags.error(
            "phys-board",
            f"board '{name}': no such devicetree file\n  {board_dts}")
        return None

    if recipe is None:
        diags.error(
            "phys-board",
            f"board '{name}': no devicetree-reading recipe available "
            f"({board_dts})\n"
            "pass --include-dir/--bindings-dir (repeatable), or --build-info "
            "<build_info.yml> from a real build, to read its devicetree — a "
            "rig build (rig.cmake) supplies this automatically")
        return None

    board = board_edt.load_board(name, board_dts, recipe, workdir)
    if not board.sockets:
        diags.error(
            "phys-board",
            f"board '{name}' has a devicetree ({os.path.relpath(board_dts)}) "
            "but declares no socket,* nodes — it exists, but is not "
            "rig-enabled (Conv. 4: a board opts in with a typed socket node)")
        return None
    return board


def _discover_board_dts(name: str, diags: Diagnostics) -> Optional[str]:
    """Standalone/CLI fallback: resolve a board NAME to its own `.dts` by
    CONSUMING zephyr's own `scripts/list_boards.py` (not forking it — the
    same choice `list_shields.py` gets elsewhere in this tree; list_boards.py
    has no `--json` mode to subprocess+parse the way list_shields.py does, so
    a direct import is the cleaner half of that pattern here). Searches only
    this module's OWN board root (`MODULE_ROOT`) — every board this rig
    tooling can ever reference is one of its own clones."""
    zephyr_base = os.environ["ZEPHYR_BASE"]
    scripts_dir = os.path.join(zephyr_base, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import list_boards  # noqa: E402  (zephyr script, consumed not forked)

    args = argparse.Namespace(
        board_roots=[Path(MODULE_ROOT)], soc_roots=[Path(zephyr_base)],
        board=None, board_dir=[])
    boards = list_boards.find_v2_boards(args)
    if name not in boards:
        diags.error(
            "phys-board",
            f"unknown board '{name}'\n"
            f"no such board directory under {os.path.relpath(MODULE_ROOT)}/boards\n"
            f"known boards: {', '.join(sorted(boards)) or '(none)'}")
        return None
    return str(boards[name].dir / f"{name}.dts")
