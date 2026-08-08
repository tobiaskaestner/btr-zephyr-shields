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

# `--boards-for` (Rigs._boards_for, below) needs SOME board to satisfy
# loader.load's schema now that no rig declares one (board-coordinate-
# s6-brief.md Sec 3) -- inert by construction (see _boards_for's own
# docstring for why its exact spelling never matters), so it is spelled
# to read as a placeholder rather than a real hwmv2 target if it ever
# does leak into a diagnostic somehow.
_BOARDS_FOR_PLACEHOLDER_BOARD = '(boards-for census: no board selected)'


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
            - dir: directory that contains the rig definition
            - revisions: declared revision axis values (rig-variants-
              revisions.md V1a), comma-separated, empty if undeclared
            - variants: declared variant axis values, comma-separated,
              empty if undeclared

            No `board` column (board-coordinate-s6-brief.md Sec 8
            criterion 6): a rig no longer declares one, so this listing
            has nothing of its own to print -- use --boards-for to ask
            which real boards a rig's typed sockets are satisfiable on.
            '''))

        # Remember to update west-commands.yml help if you add or remove flags.
        parser.add_argument('-f', '--format', default=default_fmt,
                            help='''Format string to use to list each rig;
                                    see FORMAT STRINGS below.''')
        parser.add_argument('-n', '--name', dest='name_re',
                            help='''a regular expression; only rigs whose names
                            match NAME_RE will be listed''')
        parser.add_argument(
            '--boards-for', metavar='TARGET', default=None,
            help='''instead of listing rigs, print the boards whose typed
                 sockets satisfy TARGET (name[@rev][/variant]): mating,
                 bus-subset exposure, alias-aware reference resolution and
                 stackability, censused from board rig-extension SOURCES
                 (no cmake configure). TARGET is resolved against BOTH
                 namespaces, exactly as --explain resolves it: a persisted
                 rig, or a discoverable shield promoted to one -- so
                 "which boards can host this shield?" is askable without a
                 rig existing for it. This is NOT a promise the rig
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
            # No board column any more (Sec 8 criterion 6): a rig no
            # longer declares one, so this listing has nothing of its own
            # to print for it -- --boards-for is the enumeration answer.
            # variants: variant_names extracts the bare NAME out of each
            # list: entry, which may be a {name:, board:, sockets:}
            # mapping rather than a scalar in that same shape.
            self.inf(args.format.format(
                name=rig.name,
                dir=rig.dir,
                revisions=', '.join(str(v) for v in rig.revisions['list'])
                if rig.revisions else '',
                variants=', '.join(str(v) for v in
                                   list_rigs.variant_names(rig.variants))
                if rig.variants else '',
            ))

    def _shield_dirs(self, args):
        """The shield namespace at the SAME breadth as the rig namespace:
        `<root>/boards/shields` for every board root do_run resolved,
        never `discover_shields`' own vendored-library default. That
        default was the S3a defect (a cross-module shield invisible to
        --explain and therefore silently uncollidable), so both callers
        below pass this explicitly. A root with no `boards/shields`
        contributes nothing."""
        return [str(Path(root) / 'boards' / 'shields')
                for root in args.board_roots]

    def _resolve_both_namespaces(self, args, target):
        """The board-coordinate-s3-brief.md Sec 5 namespace rule, shared
        by --explain and --boards-for: a rig FOLDER wins, a shield name is
        the fallback, a name that is BOTH is an error naming both paths.
        Returns (name, revision, variant, shield_info-or-None); a None
        shield means the caller should fall through to
        list_rigs.resolve_rig_target, which owns the "neither" exit.

        Shared rather than written twice on purpose. Sec 5's rule is a
        property of the TARGET GRAMMAR, not of either flag, so two copies
        could disagree about which namespace wins or whether a collision
        is an error -- and `west rigs --explain X` succeeding while
        `--boards-for X` reported "does not resolve to a rig" was exactly
        the divergence this method was extracted to end.

        Exits non-zero (never returns) on a collision or on a shield that
        cannot be promoted -- `check_promotable` is what refuses
        "/variant" on a shield, which has no variant axis to select."""
        from rigc import promote

        name, revision, variant = list_rigs.parse_rig_target(target)
        rig = next((r for r in list_rigs.find_rigs(args) if r.name == name),
                   None)
        shields = promote.discover_shields(self._shield_dirs(args))

        if rig is not None and name in shields:
            sys.exit('ERROR: ' + promote.both_paths_error(
                name, rig.dir, shields[name].dir))

        if name in shields:
            err = promote.check_promotable(name, shields[name], variant)
            if err is not None:
                sys.exit(f'ERROR: {err}')
            return name, revision, variant, shields[name]

        return name, revision, variant, None

    def _boards_for(self, args):
        """`--boards-for`'s implementation: resolve TARGET against
        BOTH namespaces (_resolve_both_namespaces, the same Sec 5 rule
        --explain applies), load it standalone (no --include-dir: rigc.
        loader.load runs this way unassisted, and the connector-type
        registry finds its own bindings by default), then run board_
        census.boards_for against every censused board rig-extension.
        Prints one conforming target per line, sorted; nothing at all,
        exit 0, when none conform -- an empty answer is a fact, not an
        error. A rig that fails to LOAD renders its own diagnostics to
        stderr and exits 1, same convention rigc's own CLI uses.

        A PROMOTED SHIELD is materialized the way `rigc expand --promote`
        materializes it (cli.py): promote.promote_shield's two synthesized
        documents are written into this run's workdir and loaded by path,
        so everything downstream runs on a real rig.yml at a real path and
        the census cannot tell the two namespaces apart. The shield's own
        revision is baked into the content's `shield:` reference there, so
        it is never ALSO passed to loader.load as a rig-level selection --
        a promoted rig declares no revisions: axis of its own.

        Answering a promoted shield is the point of the flag, not an
        extra: a shield is exactly the case where "which boards can host
        this?" has no other way to be asked. Until this landed, every
        shield name exited 1 with list_rigs' "does not resolve to a rig",
        which read as "no such thing" rather than "wrong namespace".

        board IS injected, as of S6 (board-coordinate-s6-brief.md Sec 3):
        no corpus rig declares one any more, so loader.load would
        otherwise hit binding.resolve_board's "declares no board:"
        rejection for every target this command is asked about -- the
        opposite of "an empty answer is a fact, not an error" above. The
        injected value is _BOARDS_FOR_PLACEHOLDER_BOARD, an inert
        constant: this command's own claim is bounded to socket
        conformance against EVERY censused board (board_census.boards_for
        iterates cb.board for each CensusBoard, never rig.board), so which
        placeholder string satisfies the loader's schema is immaterial --
        it is never rendered (no emitter call on this path at all) and
        never reaches boarddt (no --board-dts either, so pass-1 board
        reading never runs here)."""
        # rigc reads $ZEPHYR_BASE at call time (its own header/index
        # parsing needs zephyr's include dir); pin it to west's OWN
        # resolution rather than trust the ambient shell, exactly as
        # build-rig (rig.py) already does for the same reason.
        os.environ['ZEPHYR_BASE'] = str(ZEPHYR_BASE)

        # rigc lives beside list_rigs under _SCRIPTS, already on sys.path
        # (module top, above) for that import -- nothing further to add.
        from rigc import board_census, loader, promote
        from rigc.diag import has_errors, render
        from rigc.registry import load_types

        name, revision, variant, shield = self._resolve_both_namespaces(
            args, args.boards_for)

        types, _types_deps = load_types()
        workdir = tempfile.mkdtemp(prefix='rigs-boards-for-')
        try:
            if shield is not None:
                promoted = promote.promote_shield(name, revision)
                rig_yml = os.path.join(workdir, list_rigs.RIG_YML)
                with open(rig_yml, 'w') as f:
                    f.write(promoted.rig_yml)
                with open(os.path.join(workdir, promoted.content_name),
                          'w') as f:
                    f.write(promoted.content)
                revision = None
            else:
                # Not a shield name at all: an ordinary rig target,
                # including the "does not resolve" exit
                # list_rigs.resolve_rig_target already owns -- reused
                # verbatim rather than a second message.
                rig_target = list_rigs.resolve_rig_target(args.boards_for, args)
                rig_yml = str(rig_target.dir / list_rigs.RIG_YML)
                revision, variant = rig_target.revision, rig_target.variant

            rig, diags, _rig_deps = loader.load(
                rig_yml, workdir, types=types,
                shield_dirs=self._shield_dirs(args),
                revision=revision, variant=variant,
                board=_BOARDS_FOR_PLACEHOLDER_BOARD)
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
        6): resolve TARGET against BOTH namespaces via
        _resolve_both_namespaces (the Sec 5 rule, shared with
        --boards-for). "Neither" is never a message of this method's own:
        it falls through to list_rigs.resolve_rig_target, reusing its
        existing "does not resolve" exit rather than inventing a second
        one.

        No cmake, no cpp, no board here: a promoted shield's two
        documents are pure text (promote.promote_shield never touches a
        filesystem); a persisted rig's are read verbatim off disk.
        --explain never applies a fragment or resolves an axis into the
        printed text (Sec 6's own scope line) -- unlike --boards-for,
        this needs no $ZEPHYR_BASE pin and no workdir at all."""
        from rigc import promote
        from rigc.loader.documents import content_file_name

        name, revision, _variant, shield = self._resolve_both_namespaces(
            args, args.explain)

        if shield is not None:
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
