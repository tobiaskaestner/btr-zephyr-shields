"""rigexp CLI — the real, vendored command-line front-end.

The three-stage pipeline:

  rig    = loader_yml.load(path, workdir, diags, shield_dirs)
  solved = analyzer.analyze(rig, workdir, diags, board_dts, recipe)
  outputs = emitter.emit(solved)     # strong contract: cannot fail here

expand writes every file the emitter returns (overlay, config-sheet.md,
expectations.yml, and any future .conf) into --out-dir. On rejection
(diagnostics carry an error, or a stage returns None) it prints
diags.render() to stderr and exits non-zero. Exit 0 on success.

Board-reading recipe: pass 1 reads the real board devicetree via edtlib
(boarddt / board_edt / edt_build), which needs the board's own .dts path
plus a BuildRecipe (cpp include dirs + edtlib bindings dirs). --board-dts
names the file directly — omit it to let boarddt discover it from the
rig's board name via zephyr's own list_boards.py (the standalone/CLI
fallback; the in-build path, dts.cmake, always passes it explicitly, since
BOARD_DIR is already resolved by boards.cmake long before the expander
runs). The recipe comes from either --include-dir/--bindings-dir
(repeatable — the explicit form dts.cmake uses, having computed them
itself) or --build-info <path> (a real build's build_info.yml, recovered
via edt_build.recipe_from_build_info — a standalone/dev convenience: reuse
a build you already have rather than re-deriving dts.cmake's own dir
mirror by hand). Omitting all recipe inputs is not fatal by itself — an
unknown board is still reported as such, since board resolution never
needs a recipe — but a named, existing board with no usable recipe is its
own "phys-board" diagnostic (see boarddt.load_board), not a crash.

--revision/--variant carry the SELECTED qualifier axis values (rig-
variants-revisions.md V1a) -- the resolved counterpart of a target's
@rev/variant, which cmake/dts.cmake's fork already worked out via
list_rigs.py before invoking this CLI. Omit either for a bare target;
loader_yml.load applies the rig's declared default, if any.

Connector-type registry: --connector-dir names the type-YAML root(s)
(ctypes_registry.load_types); each type's <type>.h header is looked up
against --include-dir, first match wins, MODULE_INC tried last -- the same
list already threaded for the board .dts cpp preprocess, not a second knob.
Resolved exactly ONCE here (never re-derived by loader_yml/analyzer/
emitter) and threaded down as the types parameter both stages take.
Omitting --connector-dir/--include-dir reproduces today's single real
directory unchanged.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import List, Optional

from .ctypes_registry import load_types
from .diag import Depends, Diagnostics, LoadError
from .edt_build import BuildRecipe, recipe_from_build_info
from . import analyzer, emitter, loader_yml


def _cmake_list_escape(value: str) -> str:
    """Escape one string for embedding as ONE element of a ;-joined CMake
    list literal inside a double-quoted set(... "a;b;c") — CMake unescapes
    \\;/\\"/\\\\ when the string is later read back (e.g. by
    set_property(... APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ...) in
    dts.cmake), so a path containing a literal ;, ", or \\ survives the
    round-trip as a single element instead of being mis-split or corrupting
    the quoting. Real-world paths essentially never contain these, but
    RIG_DEPENDS is provenance data cmake.cmake trusts verbatim — worth doing
    correctly once here rather than assuming."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace(";", "\\;")


def _resolve_recipe(include_dirs: Optional[List[str]],
                    bindings_dirs: Optional[List[str]],
                    build_info: Optional[str]) -> Optional[BuildRecipe]:
    """--build-info wins if given (one path, no per-dir bookkeeping); else
    an explicit --include-dir/--bindings-dir pair, if either was given;
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
           build_info: Optional[str],
           revision: Optional[str] = None,
           variant: Optional[str] = None,
           connector_dirs: Optional[List[str]] = None) -> int:
    # Resolve to absolute paths up front: the loader parses each shield in a
    # temp workdir and cpp-includes it by the glob'd path, so a relative
    # --shield-dir yields a relative #include that cpp cannot find from the
    # temp dir. The cmake seam runs this CLI from the build dir, so all inputs
    # must be cwd-independent — --board-dts/--include-dir/--bindings-dir/
    # --build-info/--connector-dir too (see _resolve_recipe).
    rig_path = os.path.abspath(rig_path)
    if shield_dirs is not None:
        shield_dirs = [os.path.abspath(d) for d in shield_dirs]
    out_dir = os.path.abspath(out_dir)
    if board_dts is not None:
        board_dts = os.path.abspath(board_dts)
    recipe = _resolve_recipe(include_dirs, bindings_dirs, build_info)
    resolved_connector_dirs = ([os.path.abspath(d) for d in connector_dirs]
                               if connector_dirs else None)
    # header_dirs is the RAW --include-dir list (not recipe.include_dirs,
    # which may instead come from --build-info's recovered board
    # directories) — threaded to every cpp invocation this run makes
    # OTHER than the board .dts preprocess (which already has its own
    # recipe): the connector-type registry's <type>.h lookup
    # (ctypes_registry.load_types), every .shield template's own
    # translation unit (dtsio.run_cpp, via loader_yml), and the rig's
    # dt-includes:/per-instance-parameter resolution (dtsio.check_include/
    # resolve_token, via loader_yml and the emitter's config sheet). One
    # list, one ratified plumbing shape (first match wins, ZEPHYR_INC/
    # MODULE_INC tried last) — mirroring how cpp itself would resolve the
    # same #include wherever it appears.
    header_dirs = ([os.path.abspath(d) for d in include_dirs]
                   if include_dirs else None)

    diags = Diagnostics()
    workdir = tempfile.mkdtemp(prefix="rigexp-")
    # Every real source-tree file this run opens (rig.yml, its <rigname>.yml
    # content file, .shield templates + their cpp includes, connector
    # bindings, index headers, the board .dts) — the dependency-tracking
    # handoff (RIG_DEPENDS, below), so cmake/dts.cmake can retrigger
    # configure when any of them changes.
    deps = Depends()

    # Resolved ONCE here and threaded down to both the loader (shield plug
    # checks) and the analyzer (board socket type facts) — replaces what
    # used to be six independent load_types() calls (loader_yml once,
    # analyzer once, emitter four times per run), each re-globbing and
    # re-parsing the whole connector tree. connector_dirs is None absent
    # --connector-dir (today's single real directory, unchanged); header_dirs
    # is None absent --include-dir (MODULE_INC alone, unchanged) — a caller
    # supplying neither sees exactly the pre-existing behavior.
    types = load_types(connector_dirs=resolved_connector_dirs,
                       header_dirs=header_dirs, deps=deps)

    try:
        rig = loader_yml.load(rig_path, workdir, diags, shield_dirs=shield_dirs,
                              deps=deps, revision=revision, variant=variant,
                              types=types, include_dirs=header_dirs)
    except LoadError as e:
        diags.append(e.diag)
        print(diags.render(), file=sys.stderr)
        return 1

    if rig is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    solved = analyzer.analyze(rig, workdir, diags, board_dts, recipe, deps,
                              types=types)
    if solved is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    # strong contract: cannot fail here
    outputs = emitter.emit(solved, workdir, include_dirs=header_dirs)

    os.makedirs(out_dir, exist_ok=True)
    for fname, content in outputs.items():
        with open(os.path.join(out_dir, fname), "w") as f:
            f.write(content)

    # Build-glue handoff: a cmake fragment the rig build module (dts.cmake)
    # include()s to learn what the rig instantiated — board + the DISTINCT set of
    # shields (rig order). The expander is the single authority on the rig->shields
    # mapping; dts.cmake resolves each shield to its folder + drives the Kconfig /
    # bookkeeping. Kept out of emitter.emit() (which stays rig-artifacts-only).
    shields = []
    shield_revisions = []
    for inst in rig.instances:
        if inst.shield.name not in shields:
            shields.append(inst.shield.name)
        # The RESOLVED revision of every shield that DECLARES a revisions:
        # axis, default selections included — symmetric with RIG_REVISION /
        # RIG_VARIANT below, which likewise appear whenever the rig declares
        # the axis rather than only when a non-default value was chosen.
        # Suppressing a defaulted revision would leave provenance unable to
        # answer which revision of a shield a given build actually used
        # (silence would mean both "revision 1" and "this shield has no
        # revisions"), which is the question build provenance exists for; a
        # value with a raw and a resolved form is always recorded in its
        # RESOLVED form.
        shield = inst.shield
        if shield.revision is not None and shield.revisions is not None:
            pair = f"{shield.name}@{shield.revision}"
            if pair not in shield_revisions:
                shield_revisions.append(pair)
    # RIG_DEPENDS: the dependency-tracking handoff. The expander is the sole
    # authority on what pass 1 actually read — cmake/dts.cmake appends this
    # (sorted, absolute) to CMAKE_CONFIGURE_DEPENDS, on top of its own static
    # registrations (rig.yml / its <name>.yml content file / the rig's own
    # <name>_defconfig/<name>.overlay / rigexp sources / list_rigs.py),
    # which cover the pre-expansion trigger set. One-configure lag: this
    # list is only as fresh as the LAST successful expand, so a
    # brand-new dependency (e.g. a rig naming a shield for the first time)
    # needs one configure to register before edits to IT retrigger — the
    # static set is what guarantees that first configure happens at all.
    deps_list = ";".join(_cmake_list_escape(p) for p in sorted(deps))
    with open(os.path.join(out_dir, "context.cmake"), "w") as f:
        f.write("# generated by rigexp — consumed by btr-shields/cmake/dts.cmake\n")
        f.write(f'set(RIG_NAME "{rig.name}")\n')
        f.write(f'set(RIG_BOARD "{rig.board}")\n')
        f.write(f'set(RIG_SHIELDS "{";".join(shields)}")\n')
        # RIG_SHIELD_REVISIONS: "<name>@<rev>" per DISTINCT shield revision
        # resolved — written only when non-empty, the same "no declaration,
        # no artifact" precedent as RIG_REVISION/RIG_VARIANT below, so a
        # shield with no revisions: axis costs every rig naming it NOTHING.
        if shield_revisions:
            f.write(f'set(RIG_SHIELD_REVISIONS "{";".join(shield_revisions)}")\n')
        # RIG_REVISION/RIG_VARIANT: written only when this rig actually
        # declares the corresponding axis (rig.revision/rig.variant is
        # None otherwise) — same "no declaration, no artifact, zero
        # churn" precedent as rig-gen-includes.dtsi for dt-includes:, so
        # the 13 axis-less corpus rigs' context.cmake stays byte-identical.
        if rig.revision is not None:
            f.write(f'set(RIG_REVISION "{rig.revision}")\n')
        if rig.variant is not None:
            f.write(f'set(RIG_VARIANT "{rig.variant}")\n')
        f.write(f'set(RIG_DEPENDS "{deps_list}")\n')

    if diags:   # warnings only (errors would have exited above) — surfaced,
        print(diags.render(), file=sys.stderr)   # not fatal
    return 0


def _add_expand(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "expand",
        help="run one rig through load -> analyze -> emit and write the "
             "outputs to --out-dir")
    p.add_argument("rig", help="path to the rig's metadata file, rig.yml "
                    "(the content file, <rigname>.yml, is derived from its "
                    "own name: and read alongside it)")
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
                         "dts.cmake uses. Omit to discover it from the rig's "
                         "board name via zephyr's list_boards.py (standalone/"
                         "CLI fallback).")
    p.add_argument("--include-dir", dest="include_dirs", action="append",
                    metavar="DIR", default=None,
                    help="a cpp -I directory for the board .dts preprocess; "
                         "repeatable. With --bindings-dir, the explicit "
                         "recipe form dts.cmake passes (it computes these "
                         "itself). Also the search list a connector type's "
                         "dt-bindings/connector/<type>.h resolves against, "
                         "first match wins, MODULE_INC tried last.")
    p.add_argument("--bindings-dir", dest="bindings_dirs", action="append",
                    metavar="DIR", default=None,
                    help="an edtlib bindings directory (globbed for "
                         "*.yaml); repeatable.")
    p.add_argument("--connector-dir", dest="connector_dirs", action="append",
                    metavar="DIR", default=None,
                    help="a connector-type root (globbed for *.yaml unified "
                         "socket+plug bindings, ctypes_registry.py); "
                         "repeatable. Omit to use the vendored default "
                         "(dts/bindings/connectors, direct/API use only). "
                         "Each type's <type>.h header is looked up in "
                         "--include-dir, not here.")
    p.add_argument("--build-info", default=None, metavar="PATH",
                    help="recover the cpp/bindings recipe from a real "
                         "build's build_info.yml instead of --include-dir/"
                         "--bindings-dir — standalone/dev convenience "
                         "(edt_build.recipe_from_build_info); wins over "
                         "--include-dir/--bindings-dir if both are given.")
    p.add_argument("--revision", default=None, metavar="REV",
                    help="the selected revision axis value (the @rev half "
                         "of a qualified -DRIG=name@rev/variant target); "
                         "omit for a bare target, which takes the rig's "
                         "declared default revision, if any.")
    p.add_argument("--variant", default=None, metavar="NAME",
                    help="the selected variant axis value (the /variant "
                         "half of a qualified target); omit for a bare "
                         "target, which takes the rig's declared default "
                         "variant, if any.")
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
                       args.build_info, args.revision, args.variant,
                       args.connector_dirs)
    ap.error(f"unknown command {args.command!r}")
    return 2   # unreachable; ap.error() exits


if __name__ == "__main__":
    sys.exit(main())
