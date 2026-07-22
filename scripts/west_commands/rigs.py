# SPDX-License-Identifier: Apache-2.0
#
# `west rigs` — display the list of available rigs, mirroring Zephyr's own
# `west shields` / `west boards`. A rig's identity is its rig.yml `rig.name`
# field (see list_rigs.py); this lists those names, with the same `-f/--format`
# and `-n/--name` flags shields/boards support, plus `--board-root`.
#
# Root discovery follows shields.py: every Zephyr module that declares a
# build.settings.board_root is scanned (btr-shields itself does), so rigs are
# found wherever a module puts boards/rigs — no path needed for the common case.

import argparse
import re
import sys
import textwrap
from pathlib import Path

from west.commands import WestCommand

# btr-shields/scripts/west_commands/rigs.py -> scripts/ is the parent dir
# (where list_rigs lives); workspace topdir is 3 parents up (mirrors rig.py).
_SCRIPTS = Path(__file__).resolve().parent.parent
_TOPDIR = Path(__file__).resolve().parents[3]

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import list_rigs  # noqa: E402  (resolved via sys.path above)


def _add_zephyr_scripts():
    # zephyr_ext_common / zephyr_module live in the zephyr tree; add its script
    # dirs so module-root discovery works exactly as it does inside `west
    # shields`. For a listing command the specific tree is immaterial (the
    # module code is identical across checkouts), so we just discover one —
    # the 'zephyr-rigs'/'zephyr' names are a heuristic, not a requirement. We
    # do NOT trust the ambient $ZEPHYR_BASE (a shell profile often points it at
    # the plain tree), consistent with build-rig's resolution.
    for cand in (_TOPDIR / 'zephyr-rigs', _TOPDIR / 'zephyr'):
        wc = cand / 'scripts' / 'west_commands'
        if (wc / 'zephyr_ext_common.py').is_file():
            for p in (wc, cand / 'scripts'):
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
            return
    raise ImportError('could not locate zephyr scripts under '
                      f'{_TOPDIR}/(zephyr-rigs|zephyr)/scripts')


_add_zephyr_scripts()

from zephyr_ext_common import ZEPHYR_BASE  # noqa: E402
import zephyr_module  # noqa: E402


class Rigs(WestCommand):

    def __init__(self):
        super().__init__(
            'rigs',
            'display list of available rigs',
            description='Display list of available rigs',
            accepts_unknown_args=False)

    def do_add_parser(self, parser_adder):
        default_fmt = '{name}'
        parser = parser_adder.add_parser(
            self.name,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=self.description,
            epilog=textwrap.dedent(f'''\
            FORMAT STRINGS
            --------------

            Rigs are listed using a Python 3 format string. Arguments to the
            format string are accessed by name.

            The default format string is:

            "{default_fmt}"

            The following arguments are available:

            - name: rig name (the rig.yml `rig.name` field, the rig's identity)
            - board: the board the rig targets
            - dir: directory that contains the rig definition
            '''))

        # Remember to update west-commands.yml help if you add or remove flags.
        parser.add_argument('-f', '--format', default=default_fmt,
                            help='''Format string to use to list each rig;
                                    see FORMAT STRINGS below.''')
        parser.add_argument('-n', '--name', dest='name_re',
                            help='''a regular expression; only rigs whose names
                            match NAME_RE will be listed''')
        list_rigs.add_args(parser)

        return parser

    def do_run(self, args, _):
        if args.name_re is not None:
            name_re = re.compile(args.name_re)
        else:
            name_re = None

        modules_board_roots = [ZEPHYR_BASE]

        for module in zephyr_module.parse_modules(ZEPHYR_BASE, self.manifest):
            board_root = module.meta.get('build', {}).get('settings', {}).get('board_root')
            if board_root is not None:
                modules_board_roots.append(Path(module.project) / board_root)

        args.board_roots += modules_board_roots

        for rig in list_rigs.find_rigs(args):
            if name_re is not None and not name_re.search(rig.name):
                continue
            self.inf(args.format.format(
                name=rig.name,
                dir=rig.dir,
                board=rig.board if rig.board is not None else '',
            ))
