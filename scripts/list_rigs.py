#!/usr/bin/env python3
# Copyright (c) 2026
# SPDX-License-Identifier: Apache-2.0

# Mirrors zephyr/scripts/list_shields.py, adapted to the rig folder model:
# a rig is a folder `boards/rigs/<dir>/rig.yml`. Following the same convention
# as boards (board.yml) and shields (shield.yml), the rig's IDENTITY is the
# `rig.name` field inside rig.yml — NOT the folder basename. The folder name is
# conventionally the same as the rig name but is not authoritative (exactly as
# list_shields.py takes the name from shield.yml's `name:`, not the folder).
#
# rig.yml holds ONLY metadata (name/board/revisions/variants) — never a
# hardware description. The assembled topology (instances/wires/dt-includes)
# lives in a separate, required content file, `<rigname>.yml`, which this
# module never opens: everything past the four keys read below is the
# rigc loader's job, the canonical content parser.
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


def variant_boards(variants):
    """Every DECLARED per-variant board, keyed by variant name -- the raw
    variants: dict's list: entries that are mappings ({name:, board:,
    sockets:}) rather than bare names. Empty for a rig using the
    degenerate single top-level board: shape, or one with no variants:
    axis at all."""
    boards = {}
    for item in (variants or {}).get('list') or []:
        if isinstance(item, dict):
            name = item.get('name')
            board = item.get('board')
            if name is not None and board is not None:
                boards[str(name)] = str(board)
    return boards


def _revision_axis_shape(rig_data):
    """rig.yml's `revision:` block (hwmv2-revision-semantics-brief.md
    shape: `format:`/`default:`/`exact:`/a plural `revisions:` list of
    `{name:}` mappings), reshaped into the `{'default':, 'list': [...]}`
    this module's OWN `_resolve_axis`/`variant_names` already expect --
    kept in that shape rather than teaching those two hwmv2's own keys,
    since this module predicts cmake-side fragment filenames for the
    plain case (a bare target, or one naming a revision declared
    verbatim) ONLY. It does not implement `rigc.loader.axes`'s
    per-format validation, zero-append or nearest-lower match -- an
    undeclared-but-nearest-lower-eligible revision is rejected HERE,
    before `rigc expand` (the canonical validator, which DOES resolve
    it) ever runs; a known gap, not this rename's job to close.
    None when rig.yml declares no `revision:` block at all."""
    block = rig_data.get('revision')
    if not isinstance(block, dict):
        return None
    names = [str(item['name']) for item in (block.get('revisions') or [])
             if isinstance(item, dict) and item.get('name') is not None]
    return {'default': block.get('default'), 'list': names}


def variant_names(variants):
    """Bare variant-axis values, whichever shape variants: list: entries
    take -- a scalar, or a {name:, board:, sockets:} mapping in the
    per-variant-board shape. Display/reporting code that only wants the
    declared NAMES (west rigs' own variants= column) uses this rather
    than assuming every entry is already a bare string."""
    return [item.get('name') if isinstance(item, dict) else item
            for item in (variants or {}).get('list') or []]


def default_board(rig):
    """The board to show for a rig that has not gone through
    resolve_rig_target -- --list/--json below, and west rigs' own listing
    text: the degenerate top-level board:, or -- for a per-variant rig --
    the DECLARED DEFAULT variant's board, since showing nothing at all
    would read as a broken entry rather than as "this rig has no single
    board". None if even that cannot be answered (a malformed rig with
    neither shape, or a per-variant rig declaring no default variant)."""
    per_variant = variant_boards(rig.variants)
    if not per_variant:
        return rig.board
    default = (rig.variants or {}).get('default')
    return per_variant.get(str(default)) if default is not None else None


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
        # Declared axes: read here (not validated for shape -- rig.yml
        # carries only metadata, and this is enough to resolve a bare
        # target's default for filename construction, per
        # resolve_rig_target below; shape validation, and the separate
        # content file's own existence, are the rigc loader's job).
        ret.append(Rig(name=name, dir=maybe_rig,
                       board=rig_data.get('board'),
                       revisions=_revision_axis_shape(rig_data),
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
    none. Mirrors rigc.loader.axes's own axis-resolution rules -- this
    lightweight copy exists so cmake can construct fragment filenames
    BEFORE ever invoking the expander; the loader is still the canonical
    validator once `rigc expand` itself runs (every real build reaches
    it). Returns the resolved value, or None if the axis is undeclared and
    nothing was selected.

    Membership is checked against variant_names(declared), never the raw
    list: entries directly -- a rig's variants: axis may declare its list
    as {name:, board:, sockets:} mappings (the per-variant-board shape),
    and comparing a selected bare name against a stringified MAPPING would
    never match. revisions: never takes that shape, so this is a no-op
    there."""
    if selected is not None:
        if declared is None:
            sys.exit(f"ERROR: rig '{rig_name}' names a {axis_kind} "
                      f"({selected!r}), but this rig declares no "
                      f"{decl_key}: at all.")
        values = [str(v) for v in variant_names(declared)]
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
    values = [str(v) for v in variant_names(declared)]
    sys.exit(f"ERROR: rig '{rig_name}' names no {axis_kind}, and this rig "
              f"declares no default {axis_kind} -- choose one of: "
              f"{', '.join(values) or '(none)'}")


def _resolve_board(rig, resolved_variant):
    """The board a resolved rig target actually builds: the per-variant
    board declared beside the SELECTED variant, or the rig's own
    top-level board: in the degenerate single-board shape. Mirrors
    rigc.loader.binding's own two-shape mixing rule closely
    enough that cmake never constructs a fragment filename from a board
    that rule would have rejected -- the loader stays the canonical
    validator with the fuller diagnostic (naming every offending variant,
    not just the one selected here)."""
    per_variant = variant_boards(rig.variants)
    if per_variant:
        if rig.board is not None:
            sys.exit(
                f"ERROR: rig '{rig.name}' declares a top-level board: "
                "while its variants also declare their own -- a rig may "
                "declare a board per variant or once at the top level, "
                "never both.")
        if resolved_variant not in per_variant:
            sys.exit(
                f"ERROR: rig '{rig.name}': variant '{resolved_variant}' "
                "declares no board:, but at least one other variant does "
                "-- every variant must declare a board, or none should.")
        return per_variant[resolved_variant]
    if rig.board is None:
        sys.exit(
            f"ERROR: rig '{rig.name}' ({(rig.dir / RIG_YML).as_posix()}) "
            "declares no board -- neither a top-level board: nor one for "
            "every declared variant.")
    return rig.board


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
    itself. `rigc expand`, invoked later in the SAME configure, is the
    canonical validator (lang-rev/lang-variant diagnostics) -- this
    resolution exists so cmake has concrete axis strings to build filenames
    from, not to duplicate that diagnostic quality.

    The board is resolved LAST, after both axes, in the per-variant-board
    shape it depends on which variant was actually selected -- see
    _resolve_board.

    Exits (via `sys.exit`, mirroring `find_rigs_in`'s existing error
    convention in this module) rather than raising, so a cmake
    `execute_process` caller sees a clean nonzero exit + stderr message with
    no Python traceback.
    """
    name, revision, variant = parse_rig_target(target)
    rigs = find_rigs(args)
    for rig in rigs:
        if rig.name == name:
            resolved_revision = _resolve_axis(
                rig.name, 'revision', 'revision', rig.revisions, revision)
            resolved_variant = _resolve_axis(
                rig.name, 'variant', 'variants', rig.variants, variant)
            resolved_board = _resolve_board(rig, resolved_variant)
            return replace(rig, board=resolved_board, revision=resolved_revision,
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
    """--list / --json never resolves a target axis, so a per-variant rig
    has no single selected board to report -- default_board falls back to
    the DECLARED DEFAULT variant's, so this listing never prints a
    board of None for a rig that legitimately has one per variant."""
    if args.json:
        print(
            json.dumps([{'dir': rig.dir.as_posix(), 'name': rig.name,
                         'board': default_board(rig), 'revisions': rig.revisions,
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
