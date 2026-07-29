"""rigc CLI -- the frozen front door.

The argv surface is fixed by the frozen suite itself (rigc-mission-brief.md
Sec 2): `expand <rig_yml>` with --shield-dir* --board-dts --build-info
--bindings-dir* --include-dir* --connector-dir* --revision --variant
--out-dir (* = repeatable). Every option is PARSED here from day one;
an option whose subsystem rigc has not built yet is accepted and inert
(conformance is observable bytes, and the covered rejects' bytes do not
depend on it) -- as of R3, that is --board-dts/--build-info/
--bindings-dir (the analyzer/board-DT slices still own those); --shield-
dir/--include-dir/--connector-dir/--revision/--variant are now LIVE (the
shield library, registry, and axis resolution all consume them). main(argv)
-> int is callable in-process, so the argv contract has subprocess-free
unit tests.

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

from . import loader
from .diag import LoadError, has_errors, render
from .registry import load_types
from .unimplemented import Unimplemented


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

    # Resolved ONCE here and threaded down (T0b's shape) -- replaces what
    # would otherwise be a re-glob/re-parse per caller.
    types, _deps = load_types(connector_dirs=connector_dirs,
                              header_dirs=header_dirs)

    workdir = tempfile.mkdtemp(prefix="rigexp-")
    try:
        _rig, diags = loader.load(
            rig_path, workdir, shield_dirs=shield_dirs,
            revision=args.revision, variant=args.variant,
            types=types, include_dirs=header_dirs)
    except LoadError as e:
        # Backstop only (the registry load above): loader.load() converts
        # its own LoadErrors to the normal return shape, priors included.
        diags = list(e.diags)
        print(render(diags), file=sys.stderr)
        return 1
    if has_errors(diags):
        print(render(diags), file=sys.stderr)
        return 1
    raise Unimplemented("expand: the accept path (analyzer/emitter)")


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
