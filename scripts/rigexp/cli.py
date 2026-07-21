"""rigexp CLI — the real, vendored command-line front-end (P2/T1).

Mirrors `frontend-trial/scripts/run_trials.py:run_one` / `investigate`:

  rig    = loader_yml.load(path, workdir, diags, shields_dir)
  solved = analyzer.analyze(rig, workdir, diags)
  outputs = emitter.emit(solved)     # strong contract: cannot fail here

`expand` writes every file the emitter returns (overlay, config-sheet.md,
expectations.yml, and any future `.conf`) into --out-dir. On rejection
(diagnostics carry an error, or a stage returns None) it prints
`diags.render()` to stderr and exits non-zero — same reject path as
`investigate`. Exit 0 on success.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

from .diag import Diagnostics, LoadError
from . import analyzer, emitter, loader_yml


def _expand(rig_path: str, shield_dir: str, out_dir: str) -> int:
    # Resolve to absolute paths up front: the loader parses each shield in a
    # temp workdir and cpp-includes it by the glob'd path, so a relative
    # --shield-dir yields a relative #include that cpp cannot find from the
    # temp dir. The cmake seam runs this CLI from the build dir, so all inputs
    # must be cwd-independent.
    rig_path = os.path.abspath(rig_path)
    shield_dir = os.path.abspath(shield_dir)
    out_dir = os.path.abspath(out_dir)

    diags = Diagnostics()
    workdir = tempfile.mkdtemp(prefix="rigexp-")

    try:
        rig = loader_yml.load(rig_path, workdir, diags, shields_dir=shield_dir)
    except LoadError as e:
        diags.append(e.diag)
        print(diags.render(), file=sys.stderr)
        return 1

    if rig is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    solved = analyzer.analyze(rig, workdir, diags)
    if solved is None or diags.errors:
        print(diags.render(), file=sys.stderr)
        return 1

    outputs = emitter.emit(solved)   # strong contract: cannot fail here

    os.makedirs(out_dir, exist_ok=True)
    for fname, content in outputs.items():
        with open(os.path.join(out_dir, fname), "w") as f:
            f.write(content)

    if diags:   # warnings only (errors would have exited above) — surfaced,
        print(diags.render(), file=sys.stderr)   # not fatal
    return 0


def _add_expand(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "expand",
        help="run one rig through load -> analyze -> emit and write the "
             "outputs to --out-dir")
    p.add_argument("rig", help="path to the <rig>.rig.yml file")
    p.add_argument("--shield-dir", required=True,
                    help="directory of .shield templates (the shield library)")
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
        return _expand(args.rig, args.shield_dir, args.out_dir)
    ap.error(f"unknown command {args.command!r}")
    return 2   # unreachable; ap.error() exits


if __name__ == "__main__":
    sys.exit(main())
