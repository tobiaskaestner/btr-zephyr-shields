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
import os
import re
import shutil
import sys
import tempfile
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
            - revisions: declared revision axis values (rig-variants-
              revisions.md V1a), comma-separated, empty if undeclared
            - variants: declared variant axis values, comma-separated,
              empty if undeclared
            '''))

        # Remember to update west-commands.yml help if you add or remove flags.
        parser.add_argument('-f', '--format', default=default_fmt,
                            help='''Format string to use to list each rig;
                                    see FORMAT STRINGS below.''')
        parser.add_argument('-n', '--name', dest='name_re',
                            help='''a regular expression; only rigs whose names
                            match NAME_RE will be listed''')
        parser.add_argument(
            '--boards-for', metavar='RIG_TARGET', default=None,
            help='''instead of listing rigs, print the boards whose typed
                 sockets satisfy RIG_TARGET (name[@rev][/variant]): mating,
                 bus-subset exposure, alias-aware reference resolution and
                 stackability, censused from board rig-extension SOURCES
                 (no cmake configure). This is NOT a promise the rig
                 actually builds on a listed board -- GPIO position
                 routing, CS-pool allocation, address domains and net
                 analysis need the board's real devicetree, which this
                 census cannot see. Short-circuits the listing: -f/-n do
                 not apply.''')
        parser.add_argument(
            '--explain', metavar='TARGET', default=None,
            help='''instead of listing rigs, print the rig.yml and content
                 file TARGET (name[@rev][/variant]) stands for: verbatim
                 from disk for a persisted rig, or the synthesized pair a
                 shield name desugars to when TARGET names a discoverable
                 shield instead (board-as-coordinate-brief.md Sec 9.2/9.3)
                 -- printed AS AUTHORED, with no axis resolved into the
                 text (a variant's fragment folded in, a revision
                 selected). A name that is both a rig folder and a shield
                 is an error naming both paths; a promoted shield takes
                 only "@rev" (the shield's own revision) -- "/variant"
                 on one is refused, since a promoted shield has no
                 variant axis. Short-circuits the listing like
                 --boards-for: -f/-n do not apply.''')
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

        if args.boards_for is not None:
            self._boards_for(args)
            return

        if args.explain is not None:
            self._explain(args)
            return

        for rig in list_rigs.find_rigs(args):
            if name_re is not None and not name_re.search(rig.name):
                continue
            # board: default_board falls back to the DECLARED DEFAULT
            # variant's board for a per-variant rig (rig.board itself is
            # None there) -- printing nothing would read as a broken
            # entry. variants: variant_names extracts the bare NAME out of
            # each list: entry, which may be a {name:, board:, sockets:}
            # mapping rather than a scalar in that same shape.
            board = list_rigs.default_board(rig)
            self.inf(args.format.format(
                name=rig.name,
                dir=rig.dir,
                board=board if board is not None else '',
                revisions=', '.join(str(v) for v in rig.revisions['list'])
                if rig.revisions else '',
                variants=', '.join(str(v) for v in
                                   list_rigs.variant_names(rig.variants))
                if rig.variants else '',
            ))

    def _boards_for(self, args):
        """`--boards-for`'s implementation: resolve RIG_TARGET exactly as
        the cmake seam does (list_rigs.resolve_rig_target, which itself
        sys.exit()s with its own message on an unresolved target -- never
        re-derived here), load it standalone (no --board, no
        --include-dir: rigc.loader.load runs this way unassisted, and the
        connector-type registry finds its own bindings by default), then
        run board_census.boards_for against every censused board rig-
        extension. Prints one conforming target per line, sorted;
        nothing at all, exit 0, when none conform -- an empty answer is a
        fact, not an error. A rig that fails to LOAD renders its own
        diagnostics to stderr and exits 1, same convention rigc's own CLI
        uses."""
        # rigc reads $ZEPHYR_BASE at call time (its own header/index
        # parsing needs zephyr's include dir); pin it to west's OWN
        # resolution rather than trust the ambient shell, exactly as
        # build-rig (rig.py) already does for the same reason.
        os.environ['ZEPHYR_BASE'] = str(ZEPHYR_BASE)

        # rigc lives beside list_rigs under _SCRIPTS, already on sys.path
        # (module top, above) for that import -- nothing further to add.
        from rigc import board_census, loader
        from rigc.diag import has_errors, render
        from rigc.registry import load_types

        rig_target = list_rigs.resolve_rig_target(args.boards_for, args)
        rig_yml = rig_target.dir / list_rigs.RIG_YML

        types, _types_deps = load_types()
        workdir = tempfile.mkdtemp(prefix='rigs-boards-for-')
        try:
            rig, diags, _rig_deps = loader.load(
                str(rig_yml), workdir, types=types,
                revision=rig_target.revision, variant=rig_target.variant)
        finally:
            # D10's rule: this command never leaves a workdir behind,
            # accept or reject alike -- unlike rigc's own CLI, a query has
            # no reject-path evidence worth keeping.
            shutil.rmtree(workdir, ignore_errors=True)

        if rig is None or has_errors(diags):
            print(render(diags), file=sys.stderr)
            sys.exit(1)

        boards = board_census.census_boards(
            [str(root) for root in args.board_roots])
        for verdict in sorted(board_census.boards_for(rig, types, boards),
                              key=lambda v: v.target):
            if verdict.conforms:
                self.inf(verdict.target)

    def _explain(self, args):
        """`--explain`'s implementation (board-coordinate-s3-brief.md Sec
        6): resolve TARGET against BOTH namespaces -- a persisted rig
        (list_rigs.find_rigs, keyed by rig.yml's own name:) and a
        discoverable shield (rigc.promote.discover_shields, the SAME
        scan loader/library.py's own resolve() uses) -- per the Sec 5
        namespace rule: a rig folder wins, a shield name is the
        fallback, a name that is BOTH is an error naming both paths.
        "Neither" is never a message of this method's own: it falls
        through to list_rigs.resolve_rig_target, reusing its existing
        "does not resolve" exit rather than inventing a second one.

        No cmake, no cpp, no board here: a promoted shield's two
        documents are pure text (promote.promote_shield never touches a
        filesystem); a persisted rig's are read verbatim off disk.
        --explain never applies a fragment or resolves an axis into the
        printed text (Sec 6's own scope line) -- unlike --boards-for,
        this needs no $ZEPHYR_BASE pin and no workdir at all."""
        from rigc import promote
        from rigc.loader.documents import content_file_name

        name, revision, variant = list_rigs.parse_rig_target(args.explain)
        rigs = list_rigs.find_rigs(args)
        rig = next((r for r in rigs if r.name == name), None)
        # BOTH namespaces at the SAME breadth. find_rigs walks every module
        # board root (do_run appends them above), so the shield scan must
        # too -- discover_shields' own default is the vendored library
        # alone, and using it here would make a shield in another module
        # invisible to --explain AND silently uncollidable, which is the
        # namespace rule failing open rather than erroring.
        shields = promote.discover_shields(
            [str(Path(root) / 'boards' / 'shields') for root in args.board_roots])

        if rig is not None and name in shields:
            sys.exit(f'ERROR: {promote.both_paths_error(name, rig.dir, shields[name].dir)}')

        if name in shields:
            err = promote.check_promotable(name, shields[name], variant)
            if err is not None:
                sys.exit(f'ERROR: {err}')
            promoted = promote.promote_shield(name, revision)
            self._print_pair(('rig.yml', promoted.rig_yml),
                             (promoted.content_name, promoted.content))
            return

        # Not a shield name at all: an ordinary rig target, including the
        # "does not resolve" exit list_rigs.resolve_rig_target already
        # owns -- reused verbatim rather than a second message. Axes
        # given in TARGET are validated (the rig's own declared
        # revisions:/variants:) but never applied to the printed text --
        # --explain prints the base rig.yml/content file AS AUTHORED
        # (Sec 6's out-of-scope line), regardless of which axis value
        # was resolved.
        rig_target = list_rigs.resolve_rig_target(args.explain, args)
        rig_yml_path = rig_target.dir / list_rigs.RIG_YML
        content_path = rig_target.dir / content_file_name(rig_target.name)
        self._print_pair(('rig.yml', rig_yml_path.read_text()),
                         (content_path.name, content_path.read_text()))

    def _print_pair(self, first, second):
        """One --explain answer: two (filename, text) pairs, each headed
        by its own bare filename -- never a full path -- so a promoted
        shield's output and a persisted rig's are diffable line for line
        (Sec 6's property 1: the singleton law checkable at this level).
        Separated by one blank line; neither text needs its own trailing
        newline duplicated by self.inf's own."""
        pairs = (first, second)
        for i, (name, text) in enumerate(pairs):
            self.inf(f'# {name}')
            self.inf(text.rstrip('\n'))
            if i < len(pairs) - 1:
                self.inf('')
