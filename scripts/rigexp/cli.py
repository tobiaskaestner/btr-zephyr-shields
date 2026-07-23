"""rigexp CLI — the real, vendored command-line front-end (P2/T1).

Mirrors `frontend-trial/scripts/run_trials.py:run_one` / `investigate`:

  rig    = loader_yml.load(path, workdir, diags, shield_dirs)
  solved = analyzer.analyze(rig, workdir, diags, board_dts, recipe)
  outputs = emitter.emit(solved)     # strong contract: cannot fail here

`expand` writes every file the emitter returns (overlay, config-sheet.md,
expectations.yml, and any future `.conf`) into --out-dir. On rejection
(diagnostics carry an error, or a stage returns None) it prints
`diags.render()` to stderr and exits non-zero — same reject path as
`investigate`. Exit 0 on success.

Board-reading recipe (Bridge-A rewrite, THE FLIP): pass 1 now reads the REAL
board devicetree via edtlib (`boarddt` / `board_edt` / `edt_build`), which
needs the board's own `.dts` path plus a `BuildRecipe` (cpp include dirs +
edtlib bindings dirs). `--board-dts` names the file directly — omit it to let
`boarddt` discover it from the rig's board name via zephyr's own
`list_boards.py` (the standalone/CLI fallback; the in-build path, rig.cmake,
always passes it explicitly, since BOARD_DIR is already resolved by
boards.cmake long before the expander runs). The recipe comes from EITHER
`--include-dir`/`--bindings-dir` (repeatable — the explicit form rig.cmake
uses, having computed them itself, saferail 13) OR `--build-info <path>` (a
real build's `build_info.yml`, recovered via
`edt_build.recipe_from_build_info` — a standalone/dev convenience: reuse a
build you already have rather than re-deriving rig.cmake's own dir mirror by
hand). Omitting all recipe inputs is not fatal by itself — an unknown board
is still reported as such, since board resolution never needs a recipe — but
a NAMED, EXISTING board with no usable recipe is its own `phys-board`
diagnostic (see `boarddt.load_board`), not a crash.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import List, Optional

from .diag import Diagnostics, LoadError
from .edt_build import BuildRecipe, recipe_from_build_info
from . import analyzer, emitter, loader_yml


def _resolve_recipe(include_dirs: Optional[List[str]],
                    bindings_dirs: Optional[List[str]],
                    build_info: Optional[str]) -> Optional[BuildRecipe]:
    """`--build-info` wins if given (one path, no per-dir bookkeeping); else
    an explicit `--include-dir`/`--bindings-dir` pair, if either was given;
    else None — the caller (boarddt.load_board, via analyzer.analyze) turns
    a still-None recipe into a clear diagnostic once/if it is actually
    needed, rather than this function guessing at "nothing usable"."""
    if build_info is not None:
        return recipe_from_build_info(os.path.abspath(build_info))
    if include_dirs or bindings_dirs:
        return BuildRecipe(
            include_dirs=[os.path.abspath(d) for d in (include_dirs or [])],
            bindings_dirs=[os.path.abspath(d) for d in (bindings_dirs or [])])
    return None


def _expand(rig_path: str, shield_dirs: Optional[List[str]], out_dir: str,
           board_dts: Optional[str], include_dirs: Optional[List[str]],
           bindings_dirs: Optional[List[str]],
           build_info: Optional[str]) -> int:
    # Resolve to absolute paths up front: the loader parses each shield in a
    # temp workdir and cpp-includes it by the glob'd path, so a relative
    # --shield-dir yields a relative #include that cpp cannot find from the
    # temp dir. The cmake seam runs this CLI from the build dir, so all inputs
    # must be cwd-independent — --board-dts/--include-dir/--bindings-dir/
    # --build-info too (see _resolve_recipe).
    rig_path = os.path.abspath(rig_path)
    if shield_dirs is not None:
        shield_dirs = [os.path.abspath(d) for d in shield_dirs]
    out_dir = os.path.abspath(out_dir)
    if board_dts is not None:
        board_dts = os.path.abspath(board_dts)
    recipe = _resolve_recipe(include_dirs, bindings_dirs, build_info)

    diags = Diagnostics()
    workdir = tempfile.mkdtemp(prefix="rigexp-")

    try:
        rig = loader_yml.load(rig_path, workdir, diags, shield_dirs=shield_dirs)
    except LoadError as e:
        diags.append(e.diag)
        print(diags.render(), file=sys.stderr)
        return 1

    if rig is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    solved = analyzer.analyze(rig, workdir, diags, board_dts, recipe)
    if solved is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    outputs = emitter.emit(solved)   # strong contract: cannot fail here

    os.makedirs(out_dir, exist_ok=True)
    for fname, content in outputs.items():
        with open(os.path.join(out_dir, fname), "w") as f:
            f.write(content)

    # Build-glue handoff: a cmake fragment the rig build module (rig.cmake)
    # include()s to learn what the rig instantiated — board + the DISTINCT set of
    # shields (rig order). The expander is the single authority on the rig->shields
    # mapping; rig.cmake resolves each shield to its folder + drives the Kconfig /
    # bookkeeping. Kept out of emitter.emit() (which stays rig-artifacts-only).
    shields = []
    for inst in rig.instances:
        if inst.shield.name not in shields:
            shields.append(inst.shield.name)
    with open(os.path.join(out_dir, "context.cmake"), "w") as f:
        f.write("# generated by rigexp — consumed by btr-shields/cmake/rig.cmake\n")
        f.write(f'set(RIG_NAME "{rig.name}")\n')
        f.write(f'set(RIG_BOARD "{rig.board}")\n')
        f.write(f'set(RIG_SHIELDS "{";".join(shields)}")\n')

    if diags:   # warnings only (errors would have exited above) — surfaced,
        print(diags.render(), file=sys.stderr)   # not fatal
    return 0


def _add_expand(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "expand",
        help="run one rig through load -> analyze -> emit and write the "
             "outputs to --out-dir")
    p.add_argument("rig", help="path to the <rig>.rig.yml file")
    p.add_argument("--shield-dir", dest="shield_dirs", action="append",
                    metavar="DIR", default=None,
                    help="a shield-library root (a boards/shields directory); "
                         "may be given more than once. Templates are unioned "
                         "across all of them — shields may live in any "
                         "board_root of any Zephyr module. Omit to use the "
                         "vendored default (direct/API use only).")
    p.add_argument("--board-dts", default=None,
                    help="the rig's board's own .dts (Conv. 4's typed socket "
                         "node lives there) — the explicit in-build form "
                         "rig.cmake uses. Omit to discover it from the rig's "
                         "board name via zephyr's list_boards.py (standalone/"
                         "CLI fallback).")
    p.add_argument("--include-dir", dest="include_dirs", action="append",
                    metavar="DIR", default=None,
                    help="a cpp -I directory for the board .dts preprocess; "
                         "repeatable. With --bindings-dir, the explicit "
                         "recipe form rig.cmake passes (it computes these "
                         "itself — saferail 13).")
    p.add_argument("--bindings-dir", dest="bindings_dirs", action="append",
                    metavar="DIR", default=None,
                    help="an edtlib bindings directory (globbed for "
                         "*.yaml); repeatable.")
    p.add_argument("--build-info", default=None, metavar="PATH",
                    help="recover the cpp/bindings recipe from a real "
                         "build's build_info.yml instead of --include-dir/"
                         "--bindings-dir — standalone/dev convenience "
                         "(edt_build.recipe_from_build_info); wins over "
                         "--include-dir/--bindings-dir if both are given.")
    p.add_argument("--out-dir", required=True,
                    help="directory to write overlay / config-sheet.md / "
                         "expectations.yml into")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="rigexp", description="Expand a rig file into a devicetree "
        "overlay + config sheet + expectations stub.")
    sub = ap.add_subparsers(dest="command", required=True)
    _add_expand(sub)

    args = ap.parse_args(argv)
    if args.command == "expand":
        return _expand(args.rig, args.shield_dirs, args.out_dir,
                       args.board_dts, args.include_dirs, args.bindings_dirs,
                       args.build_info)
    ap.error(f"unknown command {args.command!r}")
    return 2   # unreachable; ap.error() exits


if __name__ == "__main__":
    sys.exit(main())
