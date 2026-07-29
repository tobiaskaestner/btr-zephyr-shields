"""rigc CLI -- the frozen front door.

The argv surface is fixed by the frozen suite itself (rigc-mission-brief.md
Sec 2): `expand <rig_yml>` with --shield-dir* --board-dts --build-info
--bindings-dir* --include-dir* --connector-dir* --revision --variant
--out-dir (* = repeatable). Every option is PARSED here from day one; as
of R4 (rigc-r4-brief.md) every one of them is LIVE -- --board-dts/
--build-info/--bindings-dir now feed the board reader (boarddt/board_edt/
edt_build), the same way --shield-dir/--include-dir/--connector-dir/
--revision/--variant already feed the loader (R2/R3). Only the emitter's
own artifacts (rig-gen.overlay, context.cmake, config-sheet.md) remain
unbuilt -- a clean analysis still ends in a loud exit-3 refusal.
main(argv) -> int is callable in-process, so the argv contract has
subprocess-free unit tests.

Exit vocabulary (rigc-r1-brief.md Sec 1): 0 accept, 1 rejected input,
2 usage error (argparse's own), 3 not implemented (see unimplemented.py).

**The workdir prefix is NOT cosmetic**: the frozen `conftest.py`'s own
`normalize()` strips exactly `/tmp/rigexp-<...>` (`_WORKDIR_RE`, hardcoded
-- never parameterized on `RIG_EXPAND_COMPILE`) to a stable placeholder
before comparing rendered stderr against a golden. A cpp-preprocess-
failure detail (e.g. `param-missing-header`) embeds this path verbatim
inside gcc's own stderr text, so rigc's workdir MUST share that literal
prefix or the differential comparison sees an un-normalized path and
byte-mismatches a golden that has nothing else wrong with it. Recorded
here because it is exactly the kind of "confusing session" trap R0's own
CMAKE_CONFIGURE_DEPENDS finding warned about."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import List, Optional

from . import analyzer, boarddt, loader
from .diag import LoadError, has_errors, render
from .edt_build import BuildRecipe, recipe_from_build_info
from .registry import load_types
from .unimplemented import Unimplemented


def _resolve_recipe(include_dirs: Optional[List[str]],
                    bindings_dirs: Optional[List[str]],
                    build_info: Optional[str]) -> Optional[BuildRecipe]:
    """--build-info wins if given (one path, no per-dir bookkeeping); else
    an explicit --include-dir/--bindings-dir pair, if either was given;
    else None -- the caller (boarddt.load_board) turns a still-None recipe
    into a clear diagnostic once/if it is actually needed, rather than
    this function guessing at "nothing usable" (ported from rigexp/
    cli.py's own `_resolve_recipe`, rigc-r4-brief.md Sec 1)."""
    if build_info is not None:
        return recipe_from_build_info(os.path.abspath(build_info))
    if include_dirs or bindings_dirs:
        return BuildRecipe(
            include_dirs=[os.path.abspath(d) for d in (include_dirs or [])],
            bindings_dirs=[os.path.abspath(d) for d in (bindings_dirs or [])])
    return None


def build_parser() -> argparse.ArgumentParser:
    """The frozen argv surface. Public so the argv contract gets unit
    tests without a subprocess."""
    ap = argparse.ArgumentParser(
        prog="rigc",
        description="Compile a rig file: reject invalid input or emit the "
                    "devicetree overlay + build artifacts.")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("expand", help="run one rig through the pipeline "
                                      "and write the outputs to --out-dir")
    p.add_argument("rig", help="path to the rig's metadata file, rig.yml")
    p.add_argument("--shield-dir", dest="shield_dirs", action="append",
                   metavar="DIR", default=None,
                   help="a shield-library root; repeatable")
    p.add_argument("--board-dts", default=None,
                   help="the rig's board's own .dts")
    p.add_argument("--include-dir", dest="include_dirs", action="append",
                   metavar="DIR", default=None,
                   help="a cpp -I directory; repeatable")
    p.add_argument("--bindings-dir", dest="bindings_dirs", action="append",
                   metavar="DIR", default=None,
                   help="an edtlib bindings directory; repeatable")
    p.add_argument("--connector-dir", dest="connector_dirs", action="append",
                   metavar="DIR", default=None,
                   help="a connector-type root; repeatable")
    p.add_argument("--build-info", default=None, metavar="PATH",
                   help="recover the cpp/bindings recipe from a real "
                        "build's build_info.yml")
    p.add_argument("--revision", default=None, metavar="REV",
                   help="the selected revision axis value")
    p.add_argument("--variant", default=None, metavar="NAME",
                   help="the selected variant axis value")
    p.add_argument("--out-dir", required=True,
                   help="directory to write the emitted artifacts into")
    return ap


def _expand(args: argparse.Namespace) -> int:
    # Absolute up front, like the whole pipeline expects: the cmake seam
    # runs this CLI from the build dir, so inputs must be cwd-independent
    # -- and the diagnostics' message paths are spec'd absolute.
    rig_path = os.path.abspath(args.rig)
    shield_dirs = ([os.path.abspath(d) for d in args.shield_dirs]
                  if args.shield_dirs else None)
    connector_dirs = ([os.path.abspath(d) for d in args.connector_dirs]
                      if args.connector_dirs else None)
    # header_dirs is the RAW --include-dir list, threaded to every cpp
    # invocation this run makes (the connector-type registry's <type>.h
    # lookup, every .shield template's own translation unit, the rig's
    # dt-includes:/per-instance-parameter resolution) -- one list, one
    # ratified plumbing shape (rigexp/cli.py's own docstring).
    header_dirs = ([os.path.abspath(d) for d in args.include_dirs]
                  if args.include_dirs else None)
    board_dts = os.path.abspath(args.board_dts) if args.board_dts else None

    # Resolved ONCE here and threaded down (T0b's shape) -- replaces what
    # would otherwise be a re-glob/re-parse per caller.
    types, _deps = load_types(connector_dirs=connector_dirs,
                              header_dirs=header_dirs)

    workdir = tempfile.mkdtemp(prefix="rigexp-")
    try:
        rig, diags = loader.load(
            rig_path, workdir, shield_dirs=shield_dirs,
            revision=args.revision, variant=args.variant,
            types=types, include_dirs=header_dirs)
    except LoadError as e:
        # Backstop only (the registry load above): loader.load() converts
        # its own LoadErrors to the normal return shape, priors included.
        diags = list(e.diags)
        print(render(diags), file=sys.stderr)
        return 1
    if rig is None or has_errors(diags):
        print(render(diags), file=sys.stderr)
        return 1

    # Pass 1: board reading (rigc-r4-brief.md Sec 1). The recipe is
    # resolved HERE, not up front alongside the other inputs: it opens a
    # real file (--build-info) eagerly, and doing that before the loader
    # even runs would turn a caller's typo'd --build-info path into an
    # unhandled crash on a rig that was going to be rejected anyway (never
    # a traceback, the reject convention) -- resolving it only once the
    # loader has already accepted is what board.load_board's own
    # "no usable recipe" diagnostic exists to report cleanly instead.
    #
    # board.load_board's own diagnostics carry no `rig`-side src ref (a
    # "phys-board" finding is never anchored to a rig.yml line), so they
    # simply extend the diags list gathered so far, matching the
    # blueprint's continuation shape (rigc-r2-brief.md Sec 6): a
    # rejection here is never a reason to drop the loader's own (empty,
    # since has_errors already returned above) findings.
    recipe = _resolve_recipe(args.include_dirs, args.bindings_dirs,
                             args.build_info)
    board, board_diags, _bdeps = boarddt.load_board(
        rig.board, workdir, board_dts=board_dts, recipe=recipe)
    diags += board_diags
    if board is None:
        print(render(diags), file=sys.stderr)
        return 1

    # Pass 2: the analyzer (rigc-r4-brief.md Sec 2) -- mating/socket
    # resolution, nets, addresses, CS, wires, labels.
    _solved, analyzer_diags = analyzer.analyze(rig, board, types)
    diags += analyzer_diags
    if has_errors(diags):
        print(render(diags), file=sys.stderr)
        return 1

    # A clean analysis still ends in a loud exit-3 refusal: the emitter
    # (rig-gen.overlay/context.cmake/config-sheet.md) is R5's job.
    raise Unimplemented("expand: the accept path (emitter)")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "expand":
            return _expand(args)
        raise Unimplemented(f"command '{args.command}'")   # unreachable:
        # add_subparsers(required=True) already usage-errors on anything else
    except Unimplemented as e:
        print(f"rigc: not implemented: {e.what}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
