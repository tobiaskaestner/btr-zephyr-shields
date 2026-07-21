#!/usr/bin/env python3
# Copyright (c) 2026
# SPDX-License-Identifier: Apache-2.0

# Mirrors zephyr/scripts/list_shields.py, adapted to the rig folder model:
# a rig is a folder `boards/rigs/<name>/rig.yml` (the folder basename is the
# rig's identity, used as -DRIG=<name>). Unlike shields, a rig has no YAML
# schema to validate here — the rig file's *content* is the expander's job;
# this script only needs to know where each rig lives.
#
# This is shared code between the build system's rig resolution (rig.cmake)
# and any future 'west rigs' extension command. If you change it, make sure
# both consumers still work.
#
# (Kept stdlib-only, like list_shields.py's design intent, so it can run
# without a west/venv environment.)

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

RIG_YML = 'rig.yml'


@dataclass(frozen=True)
class Rig:
    name: str
    dir: Path


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
        if rig_yml.is_file():
            ret.append(Rig(name=maybe_rig.name, dir=maybe_rig))

    return sorted(ret, key=rig_key)


def parse_args():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    add_args(parser)
    add_args_formatting(parser)
    return parser.parse_args()


def add_args(parser):
    parser.add_argument("--board-root", dest='board_roots', default=[],
                         type=Path, action='append',
                         help='add a board root, may be given more than once')


def add_args_formatting(parser):
    parser.add_argument("--json", action='store_true',
                         help='''output list of rigs in JSON format''')


def dump_rigs(rigs, args):
    if args.json:
        print(
            json.dumps([{'dir': rig.dir.as_posix(), 'name': rig.name} for rig in rigs])
        )
    else:
        for rig in rigs:
            print(f'  {rig.name}')


if __name__ == '__main__':
    args = parse_args()
    dump_rigs(find_rigs(args), args)
