"""rigc CLI -- the frozen front door.

The argv surface is fixed by the frozen suite itself (rigc-mission-brief.md
Sec 2): `expand <rig_yml>` with --shield-dir* --board --board-dts
--build-info --bindings-dir* --include-dir* --connector-dir* --revision
--variant --out-dir (* = repeatable). Every option is PARSED here from day
one; as of R4 (rigc-r4-brief.md) every one of them is LIVE -- --board-dts/
--build-info/--bindings-dir feed the board reader (boarddt/board_edt/
edt_build), the same way --shield-dir/--include-dir/--connector-dir/
--revision/--variant feed the loader (R2/R3). --board
(board-coordinate-s1-brief.md Sec 4) feeds the loader too: given, it wins
over whatever rig.yml (or the selected variant) declares as the rig's
board, unconditionally; absent, the loader resolves the board exactly as
before --board existed. As of R5
(rigc-r5-brief.md) the accept path is complete: a clean analysis emits
the rig artifacts (`emitter.emit`) plus the build-glue handoff
(`emitter.context.render`) through the one writer (`emitter.write_
artifacts`) and returns 0 -- `unimplemented.py`'s Unimplemented no
longer fires on any input the frozen corpus contains.
main(argv) -> int is callable in-process, so the argv contract has
subprocess-free unit tests.

The positional `rig` and `--promote <shield-name>` are mutually exclusive
alternatives for the SAME slot (board-coordinate-s3b-brief.md Sec 5): a
promoted shield has no rig.yml on disk, so `--promote` makes `_expand`
synthesize `promote.promote_shield`'s own pair straight into this run's
workdir and load THAT by path -- the loader, deps, diagnostics and
emitter never learn the difference. `--revision` alongside `--promote`
means the SHIELD's own revision (baked into the synthesized content
file), never a rig-level axis -- a promoted rig declares no revisions:
of its own, so it is never forwarded to `loader.load`.

Exit vocabulary (rigc-r1-brief.md Sec 1): 0 accept, 1 rejected input,
2 usage error (argparse's own), 3 not implemented (see unimplemented.py).

**The workdir prefix is NOT cosmetic**: the frozen `conftest.py`'s own
`normalize()` strips exactly `/tmp/rigc-<...>` (`_WORKDIR_RE`, hardcoded
-- never parameterized on `RIG_EXPAND_COMPILE`) to a stable placeholder
before comparing rendered stderr against a golden. A cpp-preprocess-
failure detail (e.g. `param-missing-header`) embeds this path verbatim
inside gcc's own stderr text, so rigc's workdir MUST share that literal
prefix or the comparison sees an un-normalized path and byte-mismatches a
golden that has nothing else wrong with it. Recorded here because it is
exactly the kind of "confusing session" trap R0's own
CMAKE_CONFIGURE_DEPENDS finding warned about.

**The workdir is removed on a clean accept, KEPT on any non-zero exit**
(cutover-decisions.md D10, post-cutover-backlog.md group A item 1): a cpp
failure embeds the workdir path in its rendered diagnostic, which is
exactly why the harness carries the `_WORKDIR_RE` normalization above, so
deleting it unconditionally would destroy the evidence a reject is
pointing at. `RIGC_KEEP_WORKDIR` (any non-empty value) overrides the
accept-path deletion too, for inspecting a run that succeeded."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from typing import List, Optional

from . import analyzer, boarddt, loader, promote
from .deps import union as deps_union
from .diag import Diagnostic, LoadError, has_errors, render
from .edt_build import BuildRecipe, recipe_from_build_info
from .emitter import context, emit, write_artifacts
from .registry import load_types
from .unimplemented import Unimplemented

log = logging.getLogger(__name__)

#: Marks a handler `_configure_logging` itself installed, so a repeated
#: `main()` call (every in-process unit test makes one) never accumulates
#: a second stderr handler -- each call starts from a clean slate and
#: re-derives the CURRENT environment's answer.
_OWN_HANDLER = "_rigc_cli_handler"


def _configure_logging(verbosity: int = 0) -> None:
    """Attach a real stderr handler to the `rigc` logger tree ONLY when
    asked to, either via `-v`/`-vv` on the command line (`verbosity` 1 or
    2+, INFO or DEBUG respectively) or, when neither flag was given, via
    `RIGC_LOG=<level>` in the environment -- otherwise the package root's
    `NullHandler` (rigc/__init__.py) is the only handler and nothing
    reaches stderr, Python's own `lastResort` notwithstanding. The CLI
    flag wins over the environment when both are present, since it is the
    more explicit, per-invocation request.

    Enabling this during a golden-comparing run BREAKS the comparison BY
    DESIGN: every enabled record lands on the exact same stderr stream the
    renderer's own bytes are compared against (rigc-r45-brief.md Part B).
    Called from `main()` after argv is parsed, so an in-process unit test
    can pass a verbosity or monkeypatch the environment and observe the
    effect without a subprocess."""
    root = logging.getLogger("rigc")
    for h in list(root.handlers):
        if getattr(h, _OWN_HANDLER, False):
            root.removeHandler(h)
    level_name: Optional[str]
    if verbosity >= 2:
        level_name = "DEBUG"
    elif verbosity == 1:
        level_name = "INFO"
    else:
        level_name = os.environ.get("RIGC_LOG")
    if level_name is None:
        return
    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _OWN_HANDLER, True)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s:%(funcName)s: %(message)s"
        )
    )
    root.addHandler(handler)
    root.setLevel(level_name.upper())


def _resolve_recipe(
    include_dirs: Optional[List[str]],
    bindings_dirs: Optional[List[str]],
    build_info: Optional[str],
) -> Optional[BuildRecipe]:
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
            bindings_dirs=[os.path.abspath(d) for d in (bindings_dirs or [])],
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    """The frozen argv surface. Public so the argv contract gets unit
    tests without a subprocess."""
    ap = argparse.ArgumentParser(
        prog="rigc",
        description="Compile a rig file: reject invalid input or emit the "
        "devicetree overlay + build artifacts.",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser(
        "expand",
        help="run one rig through the pipeline and write the outputs to --out-dir",
    )
    rig_or_promote = p.add_mutually_exclusive_group(required=True)
    rig_or_promote.add_argument(
        "rig", nargs="?", default=None,
        help="path to the rig's metadata file, rig.yml",
    )
    rig_or_promote.add_argument(
        "--promote", default=None, metavar="SHIELD",
        help="a shield name to promote in place of a real rig.yml: "
        "synthesizes promote.promote_shield's own rig.yml/content pair "
        "into this run's workdir and loads that -- mutually exclusive "
        "with the positional rig",
    )
    p.add_argument(
        "--shield-dir",
        dest="shield_dirs",
        action="append",
        metavar="DIR",
        default=None,
        help="a shield-library root; repeatable",
    )
    p.add_argument(
        "--board", default=None, metavar="NAME",
        help="the board to build against, overriding rig.yml's board: "
        "(or the selected variant's) unconditionally; omit to resolve "
        "the board from the rig exactly as without this option",
    )
    p.add_argument("--board-dts", default=None, help="the rig's board's own .dts")
    p.add_argument(
        "--include-dir",
        dest="include_dirs",
        action="append",
        metavar="DIR",
        default=None,
        help="a cpp -I directory; repeatable",
    )
    p.add_argument(
        "--bindings-dir",
        dest="bindings_dirs",
        action="append",
        metavar="DIR",
        default=None,
        help="an edtlib bindings directory; repeatable",
    )
    p.add_argument(
        "--connector-dir",
        dest="connector_dirs",
        action="append",
        metavar="DIR",
        default=None,
        help="a connector-type root; repeatable",
    )
    p.add_argument(
        "--build-info",
        default=None,
        metavar="PATH",
        help="recover the cpp/bindings recipe from a real build's build_info.yml",
    )
    p.add_argument(
        "--revision",
        default=None,
        metavar="REV",
        help="the selected revision axis value",
    )
    p.add_argument(
        "--variant",
        default=None,
        metavar="NAME",
        help="the selected variant axis value",
    )
    p.add_argument(
        "--out-dir", required=True, help="directory to write the emitted artifacts into"
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v for INFO logging on stderr, -vv for DEBUG; "
        "overrides RIGC_LOG when given",
    )
    return ap


def _reject(diags: List[Diagnostic]) -> int:
    """Render diags to stderr and return the reject exit code -- the ONE
    place every `_expand()` rejection funnels through, so the verdict log
    line and the exit code can never drift apart."""
    log.info("verdict: rejected, exit 1")
    print(render(diags), file=sys.stderr)
    return 1


def _expand(args: argparse.Namespace) -> int:
    # Absolute up front, like the whole pipeline expects: the cmake seam
    # runs this CLI from the build dir, so inputs must be cwd-independent
    # -- and the diagnostics' message paths are spec'd absolute. A
    # --promote target has no path yet (it is materialized into the
    # workdir below, once one exists), so this stays None until then.
    # breakpoint()
    rig_path = os.path.abspath(args.rig) if args.rig is not None else None
    shield_dirs = (
        [os.path.abspath(d) for d in args.shield_dirs] if args.shield_dirs else None
    )
    connector_dirs = (
        [os.path.abspath(d) for d in args.connector_dirs]
        if args.connector_dirs
        else None
    )
    # header_dirs is the RAW --include-dir list, threaded to every cpp
    # invocation this run makes (the connector-type registry's <type>.h
    # lookup, every .shield template's own translation unit, the rig's
    # dt-includes:/per-instance-parameter resolution) -- one list, one
    # ratified plumbing shape (rigexp/cli.py's own docstring).
    header_dirs = (
        [os.path.abspath(d) for d in args.include_dirs] if args.include_dirs else None
    )
    board_dts = os.path.abspath(args.board_dts) if args.board_dts else None

    # Resolved ONCE here and threaded down (T0b's shape) -- replaces what
    # would otherwise be a re-glob/re-parse per caller. types_deps rides
    # RIG_DEPENDS below (every connector-type YAML and index header this
    # run's registry actually read).
    types, types_deps = load_types(
        connector_dirs=connector_dirs, header_dirs=header_dirs
    )

    workdir = tempfile.mkdtemp(prefix="rigc-")
    log.info("workdir: %s", workdir)
    accepted = False
    try:
        # --promote materializes promote.promote_shield's own two
        # documents into THIS run's workdir and loads them by path --
        # everything past this point (loader, deps, diagnostics, emitter)
        # runs on a real rig.yml on a real path, exactly as for an
        # authored one. D10 keeps the workdir on a reject, so a rejected
        # promoted shield leaves the synthesized pair on disk: the
        # evidence a user needs to look at, at a path inside the workdir
        # the rendered diagnostic itself names.
        revision = args.revision
        if args.promote is not None:
            promoted = promote.promote_shield(args.promote, args.revision)
            rig_path = os.path.join(workdir, "rig.yml")
            with open(rig_path, "w") as f:
                f.write(promoted.rig_yml)
            with open(os.path.join(workdir, promoted.content_name), "w") as f:
                f.write(promoted.content)
            # The SHIELD's own revision is already baked into
            # promoted.content's `shield:` reference above; a promoted
            # rig declares no revisions: axis of its own, so this is
            # never also passed to loader.load as a rig-level selection.
            revision = None
        assert rig_path is not None  # argparse's mutually exclusive group guarantees one of rig/--promote

        try:
            rig, diags, rig_deps = loader.load(
                rig_path,
                workdir,
                shield_dirs=shield_dirs,
                revision=revision,
                variant=args.variant,
                board=args.board,
                types=types,
                include_dirs=header_dirs,
            )
        except LoadError as e:
            # Backstop only (the registry load above): loader.load()
            # converts its own LoadErrors to the normal return shape,
            # priors included.
            return _reject(list(e.diags))
        if rig is None or has_errors(diags):
            return _reject(diags)

        # Pass 1: board reading (rigc-r4-brief.md Sec 1). The recipe is
        # resolved HERE, not up front alongside the other inputs: it opens
        # a real file (--build-info) eagerly, and doing that before the
        # loader even runs would turn a caller's typo'd --build-info path
        # into an unhandled crash on a rig that was going to be rejected
        # anyway (never a traceback, the reject convention) -- resolving
        # it only once the loader has already accepted is what
        # board.load_board's own "no usable recipe" diagnostic exists to
        # report cleanly instead.
        #
        # board.load_board's own diagnostics carry no `rig`-side src ref
        # (a "phys-board" finding is never anchored to a rig.yml line), so
        # they simply extend the diags list gathered so far, matching the
        # blueprint's continuation shape (rigc-r2-brief.md Sec 6): a
        # rejection here is never a reason to drop the loader's own
        # (empty, since has_errors already returned above) findings.
        recipe = _resolve_recipe(args.include_dirs, args.bindings_dirs, args.build_info)
        board, board_diags, board_deps = boarddt.load_board(
            rig.board, workdir, board_dts=board_dts, recipe=recipe
        )
        diags += board_diags
        if board is None:
            return _reject(diags)

        # Pass 2: the analyzer (rigc-r4-brief.md Sec 2) -- mating/socket
        # resolution, nets, addresses, CS, wires, labels.
        solved, analyzer_diags = analyzer.analyze(rig, board, types)
        diags += analyzer_diags
        if has_errors(diags):
            return _reject(diags)

        # Accept: emit the rig artifacts (emitter.emit -- strong contract,
        # cannot fail here) plus the build-glue handoff (context.render,
        # rigc-r5-brief.md Sec 2 -- kept a SEPARATE value function so
        # cli.py never builds context.cmake's text itself), then ONE
        # writer for everything. RIG_DEPENDS is every real source-tree
        # file this run actually touched: the connector-type registry,
        # the loader's own closure (rig.yml, its content file, qualifier
        # delta fragments, every shield resolution across all three
        # topology stages -- eager scan breadth and resolution history
        # alike, see loader.load's own docstring), and the board's .dts.
        all_deps = deps_union(types_deps, rig_deps, board_deps)
        out_dir = os.path.abspath(args.out_dir)
        log.info("out-dir: %s", out_dir)
        artifacts = emit(rig, solved, types, workdir, include_dirs=header_dirs)
        artifacts["context.cmake"] = context.render(rig, all_deps)
        write_artifacts(out_dir, artifacts)

        log.info("verdict: accepted, exit 0")
        if diags:  # warnings only -- errors would have exited above
            print(render(diags), file=sys.stderr)
        accepted = True
        return 0
    finally:
        # D10 (cutover-decisions.md; post-cutover-backlog.md group A item
        # 1): every invocation used to leak this directory -- 7001/787MB
        # measured in one session, and dts.cmake runs the expander once
        # per real configure too. A reject keeps it (the evidence a cpp
        # failure's own rendered diagnostic points at, e.g.
        # param-missing-header); RIGC_KEEP_WORKDIR overrides the
        # accept-path deletion for inspecting a run that succeeded.
        if accepted and not os.environ.get("RIGC_KEEP_WORKDIR"):
            log.debug("workdir: removing %s (accepted)", workdir)
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            log.debug("workdir: keeping %s", workdir)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(getattr(args, "verbose", 0))
    log.info("argv: %s", vars(args))
    try:
        if args.command == "expand":
            return _expand(args)
        raise Unimplemented(f"command '{args.command}'")  # unreachable:
        # add_subparsers(required=True) already usage-errors on anything else
    except Unimplemented as e:
        log.info("verdict: refusal (%s), exit 3", e.what)
        print(f"rigc: not implemented: {e.what}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
