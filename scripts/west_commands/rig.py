# SPDX-License-Identifier: Apache-2.0
#
# `west build-rig --rig <name> <app>` — a thin subclass of Zephyr's own `build`
# command that adds a single flag, `--rig`. <name> is a rig's `rig.name` field
# (NOT its folder basename — same convention as boards/shields). With --rig it
# forwards -DRIG=<name> to cmake; every other `west build` option works
# unchanged because we inherit Build's full parser and do_run. The application
# source dir is required and always supplied by the user (positional or -s) —
# this command never defaults it.
#
# ZERO rig knowledge here (ratified 2026-07-24, design rule 2,
# claude/rigs/cmake-alone-rig-entry-brief.md): this command is a pure wrapper
# around the cmake invocation. It does NOT scan boards/rigs/*/rig.yml or infer
# a board — cmake's own boards.cmake fork resolves -DRIG to a board target
# itself (the cmake-alone rig entry slice), the same way a bare
# `cmake -DRIG=<name>` (west absent) would. `args.board`/`args.shields` are
# left completely untouched by this command: it forwards `-DRIG=...` and
# nothing else of its own, and whatever the user ALSO passed (`-b`/`--board`,
# `--shield`) rides along through Zephyr's own Build machinery exactly as
# for a plain `west build` (`-DBOARD=...`/`-DSHIELD=...` alongside our
# `-DRIG=...`) — this command adds no board/shield opinion, first or last
# word. BOARD is now an independent coordinate with a per-rig default
# (board-coordinate-s1-brief.md): a given `-DBOARD` wins in cmake's
# boards.cmake fork, absent it is inferred from the rig exactly as before.
# SHIELD keeps its own, separate exclusion (design rule 4, amended/added
# 2026-07-24, unchanged by the board coordinate change): cmake's
# shields.cmake fork still FATALs on `-DSHIELD` alongside `-DRIG`
# unconditionally, since the rig's own instances are the sole source of
# SHIELD_AS_LIST for a rig build.
#
# EMPIRICAL (recorded in the cmake-alone-rig-entry-brief.md handoff): a fresh
# `west build` build dir with no -b/--board given does NOT refuse to run
# cmake — Zephyr's own Build._run_cmake only WARNS ("This looks like a fresh
# build and BOARD is unknown") and still invokes cmake with whatever
# cmake_opts it has (zephyr/scripts/west_commands/build.py, _run_cmake). So
# there is no west-side gate to bypass here: this command's only remaining
# job is UX sugar (resolve the rig BY NAME once via -DRIG=<name>, so the user
# need not remember `-- -DRIG=<name>` themselves) — never board inference.
#
# We deliberately DO NOT shadow `build` (west forbids it) nor monkey-patch it;
# this is a separate, additive command that reuses Build by subclassing.
#
# Coupling note: this imports Zephyr's Build by path (from the zephyr tree
# resolved by _resolve_zephyr_base). That couples us to Zephyr's west_commands
# layout — accepted per design decision; if Zephyr moves build.py, update
# _resolve_zephyr_base.

import os
import sys
from pathlib import Path

from west import log

# This command lives at btr-shields/scripts/west_commands/rig.py, so it can
# locate the west workspace topdir purely by walking up — no hardcoded
# directory names.
_TOPDIR = Path(__file__).resolve().parents[3]         # the west workspace


def _abs_under_topdir(value):
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else _TOPDIR / p


def _resolve_zephyr_base(explicit=None, configured=None):
    """Locate the zephyr tree to build against — WITHOUT hardcoding its name.
    Priority: --zephyr-base > west config `zephyr.base` > a checkout discovered
    under the workspace. This project's `.west/config` sets `zephyr.base =
    zephyr-rigs` (the rig-enabled worktree), so that config IS the source of the
    name — no literal here beyond the last-resort discovery heuristic below.

    The ambient $ZEPHYR_BASE is deliberately NOT trusted: a shell profile
    commonly exports the plain manifest `zephyr`, which is the WRONG tree for
    rig builds — overriding that (via the explicit env we set in do_run) is the
    whole reason this resolution exists."""
    for cand in (_abs_under_topdir(explicit), _abs_under_topdir(configured)):
        if cand and (cand / 'scripts' / 'west_commands' / 'build.py').is_file():
            return cand
    for name in ('zephyr-rigs', 'zephyr'):
        cand = _TOPDIR / name
        if (cand / 'scripts' / 'west_commands' / 'build.py').is_file():
            return cand
    return None


# build.py imports sibling modules (build_helpers, zcmake, zephyr_ext_common),
# so its directory must be on sys.path before we import it. (The specific tree
# used for a given build is (re)resolved in do_run, honoring --zephyr-base.)
_ZEPHYR_BASE = _resolve_zephyr_base()
if _ZEPHYR_BASE is None:
    raise ImportError('could not locate a zephyr build.py — set $ZEPHYR_BASE '
                      f'or keep a zephyr-rigs/zephyr checkout under {_TOPDIR}')
_BUILD_WC = _ZEPHYR_BASE / 'scripts' / 'west_commands'
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
            help='rig to build (by rig.yml `rig.name`): forwarded verbatim '
                 'as -DRIG=<NAME>. The board defaults to the rig\'s own '
                 '(cmake\'s boards.cmake fork resolves it), or pass '
                 '-b/--board yourself to override it -- given wins, '
                 'whatever the rig declares. --shield keeps its own '
                 'exclusion: do NOT pass --shield here, cmake FATALs on '
                 'that combination (the rig\'s own instances are the sole '
                 'source of shields for a rig build). The app source dir '
                 'is still required (positional or -s).')
        parser.add_argument(
            '--zephyr-base', metavar='DIR',
            help='zephyr tree to build against (default: $ZEPHYR_BASE, else a '
                 'zephyr-rigs/ or zephyr/ checkout under the workspace)')
        return parser

    def do_run(self, args, remainder):
        rig = getattr(args, 'rig', None)
        if rig:
            # Zero rig knowledge: no rig.yml scan, no board inference (see the
            # module docstring above). The app is required and must come from
            # the user — via -s/--source-dir (args.source_dir) or as the
            # first positional, which Build parses out of `remainder` later
            # (in _parse_remainder). We never default it: application
            # locations don't belong in this command.
            positional_app = bool(remainder) and remainder[0] != '--'
            app = args.source_dir or (remainder[0] if positional_app else None)
            if not app:
                log.die(f"--rig {rig}: no application given.\n"
                        f"  usage: west build-rig --rig {rig} <app-source-dir>")
            args.cmake_opts = list(args.cmake_opts or []) + [f'-DRIG={rig}']
            log.inf(f'build-rig: rig={rig} app={app}')
        # Pin ZEPHYR_BASE explicitly for the build. A shell profile or the
        # manifest can leave the ambient ZEPHYR_BASE pointing at the plain
        # `zephyr` tree, so we overwrite it with the resolved rig tree (from
        # --zephyr-base or west config `zephyr.base`). An explicit env var wins
        # over west's own manifest resolution. The worktree name lives in
        # config, not in this code.
        zb = _resolve_zephyr_base(getattr(args, 'zephyr_base', None),
                                  self.config.get('zephyr.base')) or _ZEPHYR_BASE
        os.environ['ZEPHYR_BASE'] = str(zb)
        return super().do_run(args, remainder)
