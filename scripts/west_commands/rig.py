# SPDX-License-Identifier: Apache-2.0
#
# `west build-rig --rig <name> <app>` — a thin subclass of Zephyr's own `build`
# command that adds a single flag, `--rig`. <name> is a rig's `rig.name` field
# (NOT its folder basename — same convention as boards/shields). With --rig it
# looks up the rig by name among boards/rigs/*/rig.yml, infers the target board
# from it, and injects -DRIG=<name>;
# every other `west build` option works unchanged because we inherit Build's full
# parser and do_run. The application source dir is required and always supplied by
# the user (positional or -s) — this command never defaults it.
#
# We deliberately DO NOT shadow `build` (west forbids it) nor monkey-patch it;
# this is a separate, additive command that reuses Build by subclassing.
#
# Coupling note: this imports Zephyr's Build by path (from the zephyr-rigs tree
# west is configured against). That couples us to Zephyr's west_commands layout
# — accepted per design decision; if Zephyr moves build.py, update _find_build.

import os
import sys
from pathlib import Path

import yaml
from west import log

# btr-shields/scripts/west_commands/rig.py -> workspace topdir is 3 parents up.
_TOPDIR = Path(__file__).resolve().parents[3]


def _find_build_dir():
    # Prefer the tree west builds against (zephyr-rigs per .west/config base).
    for cand in (_TOPDIR / 'zephyr-rigs', _TOPDIR / 'zephyr'):
        wc = cand / 'scripts' / 'west_commands'
        if (wc / 'build.py').is_file():
            return wc
    raise ImportError('could not locate zephyr build.py under '
                      f'{_TOPDIR}/(zephyr-rigs|zephyr)/scripts/west_commands')


# build.py imports sibling modules (build_helpers, zcmake, zephyr_ext_common),
# so its directory must be on sys.path before we import it.
_BUILD_WC = _find_build_dir()
if str(_BUILD_WC) not in sys.path:
    sys.path.insert(0, str(_BUILD_WC))

from build import Build  # noqa: E402  (resolved via sys.path above)


class BuildRig(Build):
    def __init__(self):
        super().__init__()               # registers as 'build'; retarget below
        self.name = 'build-rig'
        # Keep in sync with west-commands.yml.
        self.help = ('build a rig by name (--rig) — full `west build` plus '
                     'rig expansion')

    def do_add_parser(self, parser_adder):
        # Inherit the entire `west build` parser, then add our one flag.
        parser = super().do_add_parser(parser_adder)
        # Build hardcodes usage=BUILD_USAGE ("west build ..."); retarget the prog.
        if parser.usage:
            parser.usage = parser.usage.replace('west build', 'west build-rig')
        parser.add_argument(
            '--rig', metavar='NAME',
            help='rig to build (btr-shields/boards/rigs/<NAME>/rig.yml): infers '
                 '-b <board> and the rig-runner app, then runs the expander '
                 'seam via -DRIG=<NAME>')
        return parser

    def do_run(self, args, remainder):
        rig = getattr(args, 'rig', None)
        if rig:
            root = _TOPDIR / 'btr-shields'
            # A rig's identity is its `rig.name` field, NOT its folder basename
            # — the same convention boards/shields follow (board.yml/shield.yml
            # `name:`). Resolve --rig by scanning rig.yml names, mirroring how
            # rig.cmake resolves -DRIG via list_rigs.py's `name`.
            by_name = {}
            for rig_yml in sorted((root / 'boards' / 'rigs').glob('*/rig.yml')):
                rdata = (yaml.safe_load(rig_yml.read_text()) or {}).get('rig') or {}
                name = rdata.get('name')
                if name:
                    by_name[name] = (rig_yml, rdata)
            if rig not in by_name:
                log.die(f"--rig {rig}: no such rig.\n"
                        f"  available: {', '.join(sorted(by_name)) or '(none)'}")
            rig_file, rdata = by_name[rig]
            board = rdata.get('board')
            if not board:
                log.die(f"--rig {rig}: rig.board missing in {rig_file}")

            # Infer the board only if the user didn't pass one explicitly.
            if not getattr(args, 'board', None):
                args.board = board
            # The app is required and must come from the user — via -s/--source-dir
            # (args.source_dir) or as the first positional, which Build parses out
            # of `remainder` later (in _parse_remainder). We never default it:
            # application locations don't belong in this command.
            positional_app = bool(remainder) and remainder[0] != '--'
            app = args.source_dir or (remainder[0] if positional_app else None)
            if not app:
                log.die(f"--rig {rig}: no application given.\n"
                        f"  usage: west build-rig --rig {rig} <app-source-dir>")
            args.cmake_opts = list(args.cmake_opts or []) + [f'-DRIG={rig}']
            log.inf(f'build-rig: rig={rig} board={args.board} app={app}')
        # Force the project's zephyr-rigs tree. .west/config `zephyr.base` alone
        # does NOT stick here: the manifest's `zephyr` project resolves to path
        # `zephyr`, so without this the build would use the wrong tree. An
        # explicit ZEPHYR_BASE env wins over the manifest resolution.
        os.environ['ZEPHYR_BASE'] = str(_TOPDIR / 'zephyr-rigs')
        return super().do_run(args, remainder)
