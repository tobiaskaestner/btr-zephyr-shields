#!/usr/bin/env python3
# Copyright (c) 2026
# SPDX-License-Identifier: Apache-2.0

# Mirrors zephyr/scripts/list_shields.py, adapted to the rig folder model:
# a rig is a folder `boards/rigs/<dir>/rig.yml`. Following the same convention
# as boards (board.yml) and shields (shield.yml), the rig's IDENTITY is the
# `rig.name` field inside rig.yml — NOT the folder basename. The folder name is
# conventionally the same as the rig name but is not authoritative (exactly as
# list_shields.py takes the name from shield.yml's `name:`, not the folder).
# Beyond the name, the rig file's *content* is the expander's job.
#
# This is shared code between the build system's rig resolution
# (cmake/boards.cmake's fork, `-DRIG=<target>` -> board; cmake/dts.cmake's
# fork, `-DRIG=<target>` -> rig folder) and any future 'west rigs' extension
# command. If you change it, make sure all consumers still work.
#
# (Imports PyYAML like list_shields.py does — the same Zephyr venv dependency.)

import argparse
import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader

RIG_YML = 'rig.yml'

# hwmv2-exact rig target grammar (`name[@rev][/variant]`, ratified in
# rig-variants-revisions.md — the SAME three-way split
# `parse_board_components` (zephyr's cmake/modules/boards.cmake) applies to a
# board target, mirrored here for a rig's identity string per ontology.md
# section 7 ("the board->rig lift"): a rig target is symmetric with a board
# target, so its grammar and its parser are too.
_RIG_TARGET_RE = re.compile(r'^([^@/]+)(@[^@/]+)?(/(.+))?$')


@dataclass(frozen=True)
class Rig:
    name: str
    dir: Path
    board: str | None = None
    # DECLARED qualifier axes (rig.yml revisions:/variants:, V1a), each
    # {'default': str|None, 'list': [str, ...]} or None if undeclared.
    revisions: dict | None = None
    variants: dict | None = None
    # SELECTED axis values, filled in only by resolve_rig_target (never by
    # find_rigs_in, which just enumerates declarations) -- None until then.
    revision: str | None = None
    variant: str | None = None


def rig_key(rig):
    return rig.name


def find_rigs(args):
    ret = []

    for root in args.board_roots:
        for rig in find_rigs_in(root):
            ret.append(rig)

    return sorted(ret, key=rig_key)


def find_rigs_in(root):
    rigs_dir = root / 'boards' / 'rigs'
    ret = []

    if not rigs_dir.exists():
        return ret

    for maybe_rig in rigs_dir.iterdir():
        if not maybe_rig.is_dir():
            continue

        rig_yml = maybe_rig / RIG_YML
        if not rig_yml.is_file():
            continue

        data = yaml.load(rig_yml.read_text(), Loader=SafeLoader) or {}
        rig_data = data.get('rig') or {}
        name = rig_data.get('name')
        if not name:
            sys.exit(f'ERROR: rig has no rig.name: {rig_yml.as_posix()}')
        # Declared axes: read here (not validated for shape -- that is the
        # rigexp loader's job, the canonical rig.yml content parser; this
        # is enough to resolve a bare target's default for filename
        # construction, per resolve_rig_target below).
        ret.append(Rig(name=name, dir=maybe_rig,
                       board=rig_data.get('board'),
                       revisions=rig_data.get('revisions'),
                       variants=rig_data.get('variants')))

    return sorted(ret, key=rig_key)


def parse_rig_target(target):
    """Split a `-DRIG=<target>` value into `(name, revision, variant)`, per
    the grammar above. `revision`/`variant` are `None` when absent (never an
    empty string), so a caller can tell "bare name" apart from a stray empty
    match cleanly.
    """
    m = _RIG_TARGET_RE.match(target)
    if not m:
        sys.exit(f"ERROR: invalid rig target syntax: {target!r} "
                  f"(expected name[@rev][/variant])")
    name = m.group(1)
    revision = m.group(2)[1:] if m.group(2) else None
    variant = m.group(4)
    return name, revision, variant


def _resolve_axis(rig_name, axis_kind, decl_key, declared, selected):
    """Resolve one qualifier axis (revision or variant) against its rig.yml
    declaration: an explicitly selected value must be a declared member; a
    bare (unselected) axis takes the declared default, erroring if there is
    none. Mirrors rigexp.loader_yml._resolve_axis (rules 1-3) -- this
    lightweight copy exists so cmake can construct fragment filenames
    BEFORE ever invoking the expander; the loader is still the canonical
    validator once `rigexp expand` itself runs (every real build reaches
    it). Returns the resolved value, or None if the axis is undeclared and
    nothing was selected."""
    if selected is not None:
        if declared is None:
            sys.exit(f"ERROR: rig '{rig_name}' names a {axis_kind} "
                      f"({selected!r}), but this rig declares no "
                      f"{decl_key}: at all.")
        values = [str(v) for v in (declared.get('list') or [])]
        if selected not in values:
            sys.exit(f"ERROR: rig '{rig_name}': {axis_kind} '{selected}' is "
                      f"not declared -- known {axis_kind}s: "
                      f"{', '.join(values) or '(none)'}")
        return selected
    if declared is None:
        return None
    default = declared.get('default')
    if default is not None:
        return str(default)
    values = [str(v) for v in (declared.get('list') or [])]
    sys.exit(f"ERROR: rig '{rig_name}' names no {axis_kind}, and this rig "
              f"declares no default {axis_kind} -- choose one of: "
              f"{', '.join(values) or '(none)'}")


def resolve_rig_target(target, args):
    """Resolve a FULL `-DRIG=<target>` string to the ONE rig it names — the
    cmake-facing seam for cmake/boards.cmake's fork (rig->board inference +
    the `-DBOARD`/`-DRIG` mismatch check, cmake-alone-rig-entry-brief.md) and
    cmake/dts.cmake's fork (rig->folder resolution), plus any future
    `west rigs --rig <target>` use.

    Design rule 1 (ratified 2026-07-24): cmake never parses rig CONTENT — it
    hands this function the target VERBATIM; resolution semantics live here,
    never reimplemented in cmake. `@rev`/`/variant` resolve fully as of V1a:
    the selected value is validated against the rig's OWN declared
    revisions:/variants: (or defaulted, for a bare target) and returned
    alongside NAME/DIR/BOARD, so cmake can construct the per-axis fragment
    filenames (`<name>_<variant>.overlay` etc.) without parsing rig.yml
    itself. `rigexp expand`, invoked later in the SAME configure, is the
    canonical validator (lang-rev/lang-variant diagnostics) -- this
    resolution exists so cmake has concrete axis strings to build filenames
    from, not to duplicate that diagnostic quality.

    Exits (via `sys.exit`, mirroring `find_rigs_in`'s existing error
    convention in this module) rather than raising, so a cmake
    `execute_process` caller sees a clean nonzero exit + stderr message with
    no Python traceback.
    """
    name, revision, variant = parse_rig_target(target)
    rigs = find_rigs(args)
    for rig in rigs:
        if rig.name == name:
            if not rig.board:
                sys.exit(
                    f"ERROR: rig '{name}' ({(rig.dir / RIG_YML).as_posix()}) "
                    "has no rig.board -- cannot resolve a board target.")
            resolved_revision = _resolve_axis(
                rig.name, 'revision', 'revisions', rig.revisions, revision)
            resolved_variant = _resolve_axis(
                rig.name, 'variant', 'variants', rig.variants, variant)
            return replace(rig, revision=resolved_revision,
                           variant=resolved_variant)
    available = ', '.join(r.name for r in rigs) or '(none)'
    sys.exit(f"ERROR: -DRIG={target} does not resolve to a rig.\n"
              f"  available rigs: {available}")


def parse_args():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    add_args(parser)
    add_args_formatting(parser)
    return parser.parse_args()


def add_args(parser):
    parser.add_argument("--board-root", dest='board_roots', default=[],
                         type=Path, action='append',
                         help='add a board root, may be given more than once')
    parser.add_argument("--rig", dest='rig', default=None,
                         help='resolve a single rig target '
                              '(name[@rev][/variant]) instead of listing '
                              'every rig; prints via --cmakeformat if given, '
                              'else just the resolved name')


def add_args_formatting(parser):
    parser.add_argument("--json", action='store_true',
                         help='''output list of rigs in JSON format''')
    parser.add_argument("--cmakeformat", default=None,
                         help='CMake format string for --rig (mirrors '
                              "list_boards.py's --board query mode); "
                              'available keys: {NAME}, {DIR}, {BOARD}, '
                              '{REVISION}, {VARIANT}')


def dump_rigs(rigs, args):
    if args.json:
        print(
            json.dumps([{'dir': rig.dir.as_posix(), 'name': rig.name,
                         'board': rig.board, 'revisions': rig.revisions,
                         'variants': rig.variants} for rig in rigs])
        )
    else:
        for rig in rigs:
            print(f'  {rig.name}')


def dump_rig_target(rig, args):
    if args.cmakeformat is not None:
        def notfound(x):
            return x or 'NOTFOUND'
        info = args.cmakeformat.format(
            NAME='NAME;' + rig.name,
            DIR='DIR;' + rig.dir.as_posix(),
            BOARD='BOARD;' + notfound(rig.board),
            REVISION='REVISION;' + notfound(rig.revision),
            VARIANT='VARIANT;' + notfound(rig.variant),
        )
        print(info)
    else:
        print(rig.name)


if __name__ == '__main__':
    args = parse_args()
    if args.rig is not None:
        dump_rig_target(resolve_rig_target(args.rig, args), args)
    else:
        dump_rigs(find_rigs(args), args)
