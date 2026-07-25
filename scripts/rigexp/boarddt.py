"""Board DT reader — expander-side input (Conv. 4: 'the expander reads the
board DT to find socket nodes by compatible'). Delegates entirely to
`board_edt`/`edt_build`'s `edtlib.EDT` reader over the board's OWN
devicetree; `tests/test_board_read.py` guards that this production path
agrees with a direct `board_edt` call and with pass 2's own `edt.pickle`.

This module keeps two responsibilities of its own, both about board
RESOLUTION rather than DT mechanics (those live in `board_edt`/`edt_build`):

  * board NAME -> `.dts` path, explicit (the in-build path: dts.cmake already
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
from .diag import Depends, Diagnostics
from .dtsio import MODULE_ROOT
from .edt_build import BuildRecipe
from .model import Board


def load_board(name: str, workdir: str, diags: Diagnostics,
               board_dts: Optional[str] = None,
               recipe: Optional[BuildRecipe] = None,
               deps: Optional[Depends] = None) -> Optional[Board]:
    """Resolve board `name` to a `model.Board`, or None (+ a `phys-board`
    Diagnostic) if it can't be read at all.

    `board_dts` / `recipe` are the two inputs `board_edt.load_board` needs
    (see `edt_build.BuildRecipe`). The IN-BUILD path (dts.cmake) always
    passes both explicitly — BOARD_DIR is already resolved by boards.cmake
    long before the expander runs, and dts.cmake computes the recipe itself.
    Leaving `board_dts` None triggers the standalone/CLI
    discovery fallback below; leaving `recipe` None (whether or not
    `board_dts` was given) is a caller-configuration gap, reported the same
    way as any other board-resolution failure — see the `recipe is None`
    branch.

    `deps`, if given, records the board's own `.dts` (not its cpp-included
    files — those are the board's own concern, covered elsewhere; a rig
    build's dependency tracking cares about the ONE file naming the board,
    matching what `--board-dts` itself takes as a single path).
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
            "rig build (dts.cmake) supplies this automatically")
        return None

    if deps is not None:
        deps.see(board_dts)
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
    this module's OWN board root (`MODULE_ROOT`) — a narrower catalog than a
    real build sees.

    `name` may carry hwmv2 qualifiers (`<board>/<qualifiers...>`, e.g. an
    extension variant `nucleo_f401re/stm32f401xe/rig` —
    boards/extend/st/nucleo_f401re/): the qualifiers select a
    `<board>_<qualifiers>[.dts]` file (full form, falling back to the
    single-SoC SHORT form that drops the leading SoC segment — the same
    two candidates `dts.cmake`'s own `dts_configuration_files()` tries),
    never a bespoke naming rule.

    KNOWN GAP: every board this tooling can build today is an hwmv2
    EXTENSION whose BASE lives OUTSIDE `MODULE_ROOT` (a real upstream board
    in `$ZEPHYR_BASE`, or another Zephyr module) —
    `list_boards.find_v2_boards()` only attaches a `board.yml` `extend:`
    entry to a base it can already see, so a MODULE_ROOT-only scan never
    learns of any of them, and this fallback's own board catalog is
    consequently always empty. The in-build path (dts.cmake) never hits
    this: BOARD_DIR/BOARD_DIRECTORIES are already resolved by boards.cmake
    (which scans every real BOARD_ROOT) long before the expander runs, so
    `--board-dts` is always passed explicitly for a real build. Widening
    this fallback's own board root to include `$ZEPHYR_BASE` would populate
    the catalog, but pulls the ENTIRE upstream board list into an "unknown
    board" diagnostic that has nothing to do with the rig actually named —
    so the diagnostic below reports the gap honestly instead (no local
    catalog to print) and points at the wider tool that has one.
    """
    zephyr_base = os.environ["ZEPHYR_BASE"]
    scripts_dir = os.path.join(zephyr_base, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import list_boards  # noqa: E402  (zephyr script, consumed not forked)

    board_name, _, qualifiers = name.partition("/")
    args = argparse.Namespace(
        board_roots=[Path(MODULE_ROOT)], soc_roots=[Path(zephyr_base)],
        board=None, board_dir=[])
    boards = list_boards.find_v2_boards(args)
    if board_name not in boards:
        diags.error(
            "phys-board",
            f"unknown board '{name}'\n"
            f"no such board directory under {os.path.relpath(MODULE_ROOT)}/boards\n"
            "this standalone lookup only searches that one root; every "
            "board this tooling can build today extends a base that lives "
            "elsewhere (a real Zephyr board, or another Zephyr module), so "
            "it is never listed here either way -- run `west boards` for "
            "the full catalog, or pass --board-dts directly")
        return None

    board = boards[board_name]
    directories = (board.directories if isinstance(board.directories, list)
                   else [board.directories])
    if not qualifiers:
        candidates = [board_name]
    else:
        segments = qualifiers.split("/")
        candidates = ["_".join([board_name] + segments)]
        socs = len(board.socs) if board.socs else 0
        if socs == 1 and len(segments) > 1:
            candidates.append("_".join([board_name] + segments[1:]))

    # Later directories win on a naming collision, matching dts.cmake's own
    # (no-break, last-match-overwrites) BOARD_DIRECTORIES search loop.
    for directory in reversed(directories):
        for candidate in candidates:
            path = directory / f"{candidate}.dts"
            if path.is_file():
                return str(path)

    diags.error(
        "phys-board",
        f"unknown board '{name}'\n"
        f"no '{candidates[0]}.dts' (or short form) found in any of: "
        f"{', '.join(str(d) for d in directories)}")
    return None
