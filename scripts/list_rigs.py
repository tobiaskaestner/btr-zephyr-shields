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
# This is shared code between the build system's rig resolution (rig.cmake)
# and any future 'west rigs' extension command. If you change it, make sure
# both consumers still work.
#
# (Imports PyYAML like list_shields.py does — the same Zephyr venv dependency.)

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader

RIG_YML = 'rig.yml'


@dataclass(frozen=True)
class Rig:
    name: str
    dir: Path
    board: str | None = None


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
        ret.append(Rig(name=name, dir=maybe_rig,
                       board=rig_data.get('board')))

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
            json.dumps([{'dir': rig.dir.as_posix(), 'name': rig.name,
                         'board': rig.board} for rig in rigs])
        )
    else:
        for rig in rigs:
            print(f'  {rig.name}')


if __name__ == '__main__':
    args = parse_args()
    dump_rigs(find_rigs(args), args)
