"""rigc CLI -- the frozen front door.

The argv surface is fixed by the frozen suite itself (rigc-mission-brief.md
Sec 2): `expand <rig_yml>` with --shield-dir* --board --board-dts
--build-info --bindings-dir* --include-dir* --connector-dir* --revision
--variant --out-dir (* = repeatable). Every option is PARSED here from day
one; as of R4 (rigc-r4-brief.md) every one of them is LIVE -- --board-dts/
--build-info/--bindings-dir feed the board reader (boarddt/board_edt/
edt_build), the same way --shield-dir/--include-dir/--connector-dir/
--revision/--variant feed the loader (R2/R3). --board
(board-coordinate-s1-brief.md Sec 4) feeds the loader too, and is now
the ONLY source of `rig.board` (board-coordinate-s6-brief.md Sec 11
retired rig.yml's own `board:` grammar entirely): omitted, `rig.board`
is simply "" -- legal through the loader, and a diagnostic only once
this file is about to read a real board devicetree (see the board-empty
check right before boarddt.load_board, below). As of R5
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

`--promote`'s value may also be a `;`-separated LIST of shield targets
(multi-plug-list-brief.md): `promote.promote_shield_list` synthesizes
the N-instance pair instead, and `--revision` plays no part (each
element carries its own `@rev` inline in the list text, since one
scalar flag cannot carry N per-element revisions).

Exit vocabulary (rigc-r1-brief.md Sec 1): 0 accept, 1 rejected input,
2 usage error (argparse's own), 3 not implemented (see unimplemented.py).

**The workdir lives inside `--out-dir`, as `<out-dir>/rigc-generated`**,
never in /tmp: a build directory already has an owner and a lifetime, and
the workdir inherits both, so `west build -p`, `rm -rf build/` and
pytest's own tmp_path retention each reap it for free. The name is
DETERMINISTIC (no mkdtemp suffix) and the directory is wiped on entry --
a random suffix inside a long-lived build dir would accumulate one more
directory per configure, which is the pile this shape exists to end.

**The workdir NAME is NOT cosmetic**: the frozen `conftest.py`'s own
`normalize()` strips a path ending in `rigc-generated` (`_WORKDIR_RE`,
hardcoded -- never parameterized on `RIG_EXPAND_COMPILE`) to a stable
placeholder before comparing rendered stderr against a golden. A
cpp-preprocess-failure detail (e.g. `param-missing-header`) embeds this
path verbatim inside gcc's own stderr text, and the leading part of it is
now a per-run build directory, so the trailing component MUST stay
literally `rigc-generated` or the comparison sees an un-normalized
absolute path and byte-mismatches a golden that has nothing else wrong
with it. Recorded here because it is exactly the kind of "confusing
session" trap R0's own CMAKE_CONFIGURE_DEPENDS finding warned about.

**The workdir is KEPT, on every exit** (workdir-retention-ruling.md,
2026-08-19; supersedes cutover-decisions.md D10's accept-path deletion,
post-cutover-backlog.md group A item 1). What it holds is the only record
of what this run actually fed its own parsers -- a promoted shield's
synthesized rig.yml/content pair, each shield's `.dts`, and the
cpp-preprocessed `.pre` of each, the board's included -- and an ACCEPTED
run is exactly the run whose emitted overlay someone later questions, so
deleting the intermediates on success threw away the evidence for the one
verdict that produces an artifact to doubt. D10's deletion answered an
ACCUMULATION problem (7001 directories / 787MB in one session) that the
move out of /tmp had already solved on its own: the name is deterministic
and the directory is wiped on entry, so one --out-dir can hold exactly
ONE of these (~80KB, dominated by the preprocessed board .dts), and it
dies with the build directory that owns it. There is no knob --
`RIGC_KEEP_WORKDIR` is RETIRED rather than left as a no-op that reads as
if it still decided something, and `west build -p` / `rm -rf build/`
already reap the space."""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
from typing import List, Optional, Tuple

from . import analyzer, boarddt, loader, promote
from .deps import union as deps_union
from .diag import Diagnostic, LoadError, error as diag_error, has_errors, render
from .edt_build import BuildRecipe, recipe_from_build_info
from .emitter import context, emit, write_artifacts
from .registry import load_types
from .unimplemented import Unimplemented

log = logging.getLogger(__name__)

#: The workdir's name inside --out-dir. Load-bearing, not cosmetic: the
#: test harness's own normalizer (tests/integration/conftest.py
#: _WORKDIR_RE) strips a path ending in this to a stable placeholder
#: before comparing rendered stderr against a byte-exact golden. See this
#: module's docstring.
WORKDIR_NAME = "rigc-generated"

#: Marks a handler `_configure_logging` itself installed, so a repeated
#: `main()` call (every in-process unit test makes one) never accumulates
#: a second stderr handler -- each call starts from a clean slate and
#: re-derives the CURRENT environment's answer.
_OWN_HANDLER = "_rigc_cli_handler"

#: One element of a `;`-split `--promote` LIST value (multi-plug-list-
#: brief.md): `<shield>[@rev][:opts]`, no `/variant` (every element must
#: be a shield, which has no variant axis to select -- list_rigs.py's/
#: west_commands/rigs.py's own namespace resolution already refused one
#: before this ever runs, `check_promotable`'s own gate). Package-local
#: rather than importing `list_rigs.py`'s own `_RIG_TARGET_RE`: that
#: module is a standalone script outside this package, already importing
#: `rigc.promote` the other way, so importing it back here would cycle.
_LIST_ELEMENT_RE = re.compile(r"^([^@:]+)(@[^@:]+)?(:(.+))?$")


def _split_list_element(element: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Parse one list-promotion element into (name, revision, opt_text).
    A malformed element (the regex fails to match at all -- practically
    unreachable via the west/cmake front doors, which already validated
    every element before ever forwarding this value, but this CLI is
    also directly invocable on its own) falls back to treating the
    WHOLE text as the name: `promote.resolve_for_promotion`'s own
    failure to resolve it, surfaced once the synthesized `shield:`
    reference reaches the loader, is what a caller sees -- the same
    "trust the upstream namespace validation" boundary the single-
    element `--promote` branch below already keeps."""
    m = _LIST_ELEMENT_RE.match(element)
    if not m:
        return element, None, None
    name = m.group(1)
    revision = m.group(2)[1:] if m.group(2) else None
    opt_text = m.group(4)
    return name, revision, opt_text


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
        "--promote", default=None, metavar="TARGET",
        help="a promotion TARGET to expand in place of a real rig.yml: "
        "<shield>[@rev][:<key>=<value>...], or a `;`-separated list of "
        "those -- synthesizes promote.promote_shield's own rig.yml/"
        "content pair into this run's workdir and loads that. Mutually "
        "exclusive with the positional rig",
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
        help="the board to build against, in Zephyr's own "
        "<board>/<soc>/<variant> spelling -- the ONLY source of a rig's "
        "board (no rig file declares one). Omitted, the rig loads with "
        "an empty board, which every stage but the board reader accepts",
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
    # lookup, every .shield template's own translation unit, a shield
    # device's own shield,param-includes/per-instance-parameter
    # resolution) -- one list, one ratified plumbing shape (rigexp/cli.py's
    # own docstring).
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

    # The workdir lives INSIDE --out-dir, never in /tmp: a build directory
    # already has an owner and a lifetime, and the workdir now inherits
    # both. `west build -p`, `rm -rf build/` and pytest's own tmp_path
    # retention each reap it for free, which is what /tmp never did -- and
    # it is what makes "keep it on EVERY exit" (this module's docstring,
    # workdir-retention-ruling.md) affordable at all: under /tmp the keeps
    # were permanent and unowned, 292 of them counted in one session.
    #
    # DETERMINISTIC, not mkdtemp: a random suffix inside a long-lived
    # build directory would just move the pile rather than end it (one
    # more directory per configure). One name per out-dir, wiped on entry
    # so a previous run's intermediates can never be mistaken for this
    # run's -- which is ALSO what bounds the retention above to one
    # directory per --out-dir rather than one per configure.
    #
    # The entry wipe is the one deletion this module still does, and it is
    # a different question from the retention: keeping a PREVIOUS run's
    # files would hand a debugging session a `.pre` that no longer
    # corresponds to the overlay next to it, which is worse than having
    # none.
    out_dir = os.path.abspath(args.out_dir)
    log.info("out-dir: %s", out_dir)
    workdir = os.path.join(out_dir, WORKDIR_NAME)
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)
    log.info("workdir: %s", workdir)
    # --promote materializes promote.promote_shield's own two
    # documents into THIS run's workdir and loads them by path --
    # everything past this point (loader, deps, diagnostics, emitter)
    # runs on a real rig.yml on a real path, exactly as for an
    # authored one. The workdir is kept on every exit, so a promoted
    # shield always leaves the synthesized pair on disk -- the evidence a
    # user needs to look at, at a path inside the workdir the rendered
    # diagnostic itself names, whether the run rejected or accepted.
    revision = args.revision
    if args.promote is not None:
        # --promote's value is the promotion TARGET, not a bare
        # shield name: `<shield>[@rev][:<key>=<value>...]`, or (multi-
        # plug-list-brief.md) a `;`-separated LIST of such targets.
        # cmake forwards list_rigs' `{PROMOTED}` here opaquely and
        # never parses it, so this is the one parser for the option
        # grammar no matter how many options -- or elements -- it
        # grows.
        if ";" in args.promote:
            # A list target carries EACH element's own `@rev` inline
            # (unlike the single-target branch below): there is no
            # single scalar `--revision` flag that could carry N
            # separate per-element revisions, so a list's `--promote`
            # value is never revision-stripped the way a single
            # target's is (list_rigs.PromotedListTarget's own
            # docstring). check_promotable/the rig-in-a-list/
            # duplicate refusals are deliberately NOT re-checked
            # here, mirroring the single-element branch's own "trust
            # the upstream namespace validation" boundary --
            # list_rigs.py/west_commands/rigs.py already ran them
            # before ever forwarding a target this far.
            elements = []
            for element in args.promote.split(";"):
                shield_name, elem_revision, opt_text = _split_list_element(element)
                resolved = promote.resolve_for_promotion(shield_name, shield_dirs)
                opts = promote.parse_promotion_opts(opt_text, element, resolved)
                if isinstance(opts, str):
                    return _reject([diag_error("lang-promote-opts", opts)])
                elements.append((shield_name, elem_revision, opts))
            dup_err = promote.check_list_no_duplicate_elements(
                [name for name, _rev, _opts in elements], args.promote)
            if dup_err is not None:
                return _reject([diag_error("lang-promote-opts", dup_err)])
            promoted = promote.promote_shield_list(elements)
        else:
            shield_name, _, opt_text = args.promote.partition(":")
            # Resolved here, ahead of parse_promotion_opts's own
            # slot-validation grammar (multi-plug-promotion-brief.md Sec
            # 2: a bare socket= on a plural shield, a socket.<slot>= on
            # a single-plug one, an unknown slot) -- this cmake-seam
            # caller was missing from the brief's own predicted call-site
            # list (verified by grep, multi-plug-promotion-brief.md Sec
            # 3's own recorded lesson: run every caller, do not trust a
            # brief's list). check_promotable is deliberately NOT called
            # here: list_rigs.py/west_commands/rigs.py already validated
            # promotability before ever forwarding a target this far
            # (list_rigs.PromotedTarget.promotion_target, cli.py's own
            # module docstring), and this is the one entry point every
            # OTHER caller's --promote value already passed through --
            # duplicating the check here would be a second authority for
            # the same fact.
            resolved = promote.resolve_for_promotion(shield_name, shield_dirs)
            opts = promote.parse_promotion_opts(
                opt_text or None, args.promote, resolved)
            if isinstance(opts, str):
                # No SourceRef: the offending text is argv, not a file,
                # and the message already quotes the target verbatim.
                return _reject([diag_error("lang-promote-opts", opts)])
            promoted = promote.promote_shield(
                shield_name, args.revision, socket=opts.fixed.get("socket"),
                sockets=opts.sockets or None, config=opts.config or None,
                params=opts.params or None)
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
    # rig.board is "" whenever this run injected none (board-
    # coordinate-s6-brief.md Sec 11: the loader itself never requires
    # one any more, since a rig's TOPOLOGY never needed a board to
    # assemble). This is the one place that still does -- passing ""
    # straight to boarddt.load_board would search for a board literally
    # named "" and report the confusing "unknown board ''" rather than
    # the honest fact that none was given, so it is caught here first,
    # before boarddt ever runs. Unlike a `lang-*` loader finding, this
    # has no rig.yml line to blame (there is no longer a `board:` key
    # to point at) -- phys-board, no refs, matching every other
    # board-reading diagnostic's own unanchored shape.
    if not rig.board:
        return _reject(diags + [diag_error(
            "phys-board",
            f"rig '{rig.name}': no board given -- a rig has no board "
            "of its own any more (board: left rig.yml's grammar "
            "entirely); pass --board <name>")])
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
    artifacts = emit(rig, solved, types, workdir, include_dirs=header_dirs)
    artifacts["context.cmake"] = context.render(rig, all_deps)
    write_artifacts(out_dir, artifacts)

    log.info("verdict: accepted, exit 0")
    if diags:  # warnings only -- errors would have exited above
        print(render(diags), file=sys.stderr)
    return 0


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
