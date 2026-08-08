"""Shared fixtures and helpers for the rig-expander golden tests.

The corpus of rigs under boards/rigs/, plus a set of synthetic fixtures,
is frozen at two levels, named for the ARTIFACT each freezes rather than
the order the two layers were built:

  emitted (test_emitted_rejects.py, test_emitted_corpus.py) —
  expander-level, every rig: verdict + rendered diagnostics + whatever of
  EMITTED_FILES (below) the run produced. How each is compared is NOT
  uniform, and rigc/tests/compare.py holds the contracts: exit_code and
  stderr.txt byte-exact; context.cmake as a key -> value mapping;
  config-sheet.md as the facts it carries; rig-gen.overlay as only the
  facts a resolved zephyr.dts cannot see (its semantics ride that
  comparison instead), with one declared byte-compared exception;
  rig-gen-includes.dtsi as an ordered header list; rig-gen.conf asserted
  absent. Only the path placeholders below are normalized first.
  Split in two so no module mixes unit and integration tests (Tobi,
  2026-07-27): test_emitted_rejects.py holds the fixture-only rejects that
  need no Zephyr DATA at all; test_emitted_corpus.py holds the real corpus
  sweep plus the handful of synthetic fixtures whose own behavior still
  depends on real repo content (board discovery, real Zephyr bindings).

  resolved (test_resolved_corpus.py, @pytest.mark.build) — the real pass-2
  zephyr.dts, compared STRUCTURALLY (via dts_equiv.py), not byte-for-byte
  — labels/phandle numbers/ordering may legitimately differ between the
  expander's overlay text and the golden, so only the resolved tree is the
  invariant a change to HOW the overlay is worded must preserve; an
  emitted golden is refrozen whenever such a change legitimately alters
  the emitted text, using the resolved tree as the oracle that nothing
  else moved.

This module holds only the plumbing all three share: the corpus table, path
discovery (self-locating — no workspace-name literals), the expander
subprocess runner, normalization, and the freeze/assert primitives.
expectations.yml is deliberately never read here — it is emitted but never
gated (see claude/hw-expectations/).
"""
from __future__ import annotations

import dataclasses
import difflib
import logging
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

import pytest
import yaml

_LOGGER = logging.getLogger(__name__)

# This file lives in tests/integration/ (moved here at cutover, alongside
# the frozen suite's other own modules); TESTS_DIR is tests/ itself, one
# level up, where fixtures/ and goldens/ actually sit (siblings of
# integration/, not children of it -- fixtures/ in particular must land at
# exactly this depth for diag.anchor_path()'s "scripts/<module>/"-relative
# rendering to reproduce every frozen anchor line byte-for-byte).
TESTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TESTS_DIR.parents[2]   # scripts/rigc/tests -> btr-shields
GOLDENS_DIR = TESTS_DIR / "goldens"
FIXTURES_DIR = TESTS_DIR / "fixtures"
SHIELD_DIR = REPO_ROOT / "boards" / "shields"
RIGS_DIR = REPO_ROOT / "boards" / "rigs"

# This directory carries no __init__.py (the frozen suite's own modules
# import each other as plain top-level names, e.g. "from conftest import
# ..."), so it is never part of the rigc package chain pytest walks to put
# scripts/ on sys.path by itself -- every integration module that needs an
# in-process rigc import inserts scripts/ explicitly (test_board_read.py,
# test_reference_shields.py, etc.); this is that same idiom, for the
# comparators context.cmake and config-sheet.md need structurally rather
# than byte-for-byte.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.tests.compare import (  # noqa: E402
    compare_config_sheet, compare_context_cmake, compare_includes_dtsi,
    compare_overlay, overlay_is_byte_compared)


def assert_fixture_local(paths: List[Union[Path, str]]) -> None:
    """Structural proof of hermeticity for a test that claims to need no
    real Zephyr tree and no repo-production devicetree content: every
    path it hands to board_edt/edtlib as a --board-dts/--bindings-dir/
    --include-dir resolves under FIXTURES_DIR, never under $ZEPHYR_BASE
    or REPO_ROOT/dts or REPO_ROOT/include.

    $ZEPHYR_BASE may still be SET for such a test (it locates the
    devicetree package itself, which this workspace's zephyr branch
    patches -- edt_build.ensure_devicetree_on_path -- so it is not
    something a test can or should route around); what this asserts is
    that none of its DATA leaks in. Checking the caller's own recipe
    inputs (rather than, say, the ABSENCE of $ZEPHYR_BASE) is what makes
    "hermetic" a property of what the test actually reads, not an
    accident of how it was invoked."""
    for p in paths:
        resolved = Path(p).resolve()
        assert str(resolved) == str(FIXTURES_DIR) or str(resolved).startswith(
            str(FIXTURES_DIR) + os.sep), (
            f"{resolved} is outside {FIXTURES_DIR} -- a test asserting "
            "hermeticity must reference only its own fixture-tree paths")
DTS_EQUIV = REPO_ROOT / "scripts" / "dts_equiv.py"

# board name -> its OWN .dts, relative to the repo root (Conv. 4: typed
# socket nodes live in the board's own devicetree). Shared by
# test_emitted_corpus.py (--board-dts per rig) and test_board_read.py (the
# plain-build / edt.pickle-cross-check corpus).
#
# Every board here is an hwmv2 board EXTENSION: board: in rig.yml is the
# FULL qualified target, read verbatim (no expander-side sugar), and each
# one's .dts lives under boards/extend/, layered on top of the REAL upstream
# board via #include. seeeduino_lotus is the one CROSS-MODULE case: its
# base .dts lives in the bridle Zephyr module, which the west manifest does
# NOT carry -- every build path naming this board must thread
# -DEXTRA_ZEPHYR_MODULES=<bridle_root()> (see board_extra_defines
# below), or the board does not exist at all.
BOARD_DTS: Dict[str, str] = {
    "nucleo_f401re/stm32f401xe/rig":
        "boards/extend/st/nucleo_f401re/nucleo_f401re_stm32f401xe_rig.dts",
    "mikroe_quail/stm32f427xx/rig":
        "boards/extend/mikroe/quail/mikroe_quail_stm32f427xx_rig.dts",
    "frdm_k64f/mk64f12/rig":
        "boards/extend/nxp/frdm_k64f/frdm_k64f_mk64f12_rig.dts",
    "seeeduino_lotus/samd21g18a/rig":
        "boards/extend/seeed/seeeduino_lotus/seeeduino_lotus_samd21g18a_rig.dts",
}
BOARDS: List[str] = list(BOARD_DTS)

# The one board needing bridle threaded onto EXTRA_ZEPHYR_MODULES -- a
# case-level mechanism, not a global flag: every OTHER board's goldens must
# stay byte-identical (no cross-board flavor leak).
_BRIDLE_MODULE_BOARD = "seeeduino_lotus/samd21g18a/rig"


def bridle_root() -> Path:
    """The bridle Zephyr module root, SELF-LOCATED as WEST_TOPDIR / "bridle"
    (no /wrk literal) -- bridle deliberately stays OUT of the west
    manifest, so every build targeting seeeduino_lotus/samd21g18a/rig must
    pass it via -DEXTRA_ZEPHYR_MODULES=<this path> explicitly. Fails
    loudly if the checkout is missing, exactly like zephyr_base() does for
    $ZEPHYR_BASE."""
    root = WEST_TOPDIR / "bridle"
    if not root.is_dir():
        pytest.fail(
            f"bridle module not found at {root} -- lotus rig builds need "
            f"-DEXTRA_ZEPHYR_MODULES=<west-topdir>/bridle; is the bridle "
            f"checkout missing from this workspace?")
    return root


def board_extra_defines(board: str) -> List[str]:
    """Per-board extra -D cmake defines every build path (plain build,
    the resolved-corpus west build-rig, cmake-alone) must thread through
    identically.

    -DRIG_EXPAND_COMPILE=<value> (the differential-harness module knob,
    rigc-mission-brief.md Sec 3) is threaded UNCONDITIONALLY, for every
    board -- not a case-level mechanism like the bridle define below, since
    the module under test is a property of the whole differential run, not
    of any one board. Passed even when RIG_EXPAND_COMPILE already holds
    the default: dts.cmake's own cache variable derives the same value, so
    this is a provable no-op on the default path -- simpler than
    conditioning the define on non-default, and it makes
    every build's actual argv/rerun-expand.sh honest about which module
    dts.cmake resolved to, rather than leaving it to the cache default and
    an ambient $RIG_EXPAND_COMPILE the caller may or may not have exported.

    -DEXTRA_ZEPHYR_MODULES=<bridle_root> remains the one case-level extra:
    only the lotus board needs it, so non-lotus boards get it omitted and
    their goldens stay byte-identical."""
    extra = [f"-DRIG_EXPAND_COMPILE={RIG_EXPAND_COMPILE}"]
    if board == _BRIDLE_MODULE_BOARD:
        extra.append(f"-DEXTRA_ZEPHYR_MODULES={bridle_root()}")
    return extra


def _find_west_topdir(start: Path) -> Path:
    """Walk upward from start to the west workspace root (the directory
    holding .west/) — self-locating, no hardcoded workspace-name literal."""
    for candidate in (start, *start.parents):
        if (candidate / ".west").is_dir():
            return candidate
    raise RuntimeError(f"no .west/ found above {start} — is this a west workspace?")


WEST_TOPDIR = _find_west_topdir(REPO_ROOT)
_VENV_WEST = WEST_TOPDIR / ".venv" / "bin" / "west"
WEST_EXE = str(_VENV_WEST) if _VENV_WEST.is_file() else "west"

# RIGC_REFREEZE=1 rewrites goldens instead of asserting against them (both
# emitted and resolved). Always inspect git diff tests/goldens after a
# refreeze — it must reflect an INTENTIONAL, understood behavior change,
# never silent drift.
REFREEZE = bool(os.environ.get("RIGC_REFREEZE"))

# RIG_EXPAND_COMPILE: the module knob (rigc-mission-brief.md Sec 3) -- the
# Python module name of the expander CLI under test, read ONCE here from the
# environment (same name as cmake/dts.cmake's own cache variable of the same
# name, deliberately: most subprocesses this suite launches inherit this
# process's environment wholesale, e.g. via env=dict(os.environ), so that
# cache variable's own environment fallback picks up the SAME value without
# every call site needing to thread an explicit -D). rigc is the tool
# (cutover C1/C3); the knob survives cutover as cheap insurance for any
# future re-implementation (cutover-brief.md Sec 8.4), but scripts/rigexp/
# is gone from disk (C3) -- RIG_EXPAND_COMPILE=rigexp no longer runs an
# original tool to differential against; it fails outright (no such
# module), not merely expected-red.
RIG_EXPAND_COMPILE = os.environ.get("RIG_EXPAND_COMPILE", "rigc")

# rigc's workdir is `<--out-dir>/rigc-generated` (cli.WORKDIR_NAME), so
# the leading part varies per run -- a pytest tmp_path here, a real build
# directory under cmake. Match the whole absolute path up to and including
# the fixed trailing component: anchoring on `rigc-generated` alone would
# leave the run-specific prefix in the text, and matching a bare
# `/generated` would collide with zephyr's own include/generated. The
# workdir used to be `/tmp/rigc-<mkdtemp suffix>`, which is why the
# trailing component still carries the `rigc-` marker.
_WORKDIR_RE = re.compile(r"/[^\s]*rigc-generated")

# A resolved zephyr.dts's own DT provenance comments (/* in PATH:LINE */,
# /* node 'X' defined in PATH:LINE */) render PATH relative to the build's
# cwd (WEST_TOPDIR) — e.g. ../../../tmp/pytest-of-<user>/pytest-52/
# test_resolved_accept_zephyr_dt0/build/rig/rig-gen.overlay:25 — which embeds
# pytest's OWN per-session tmp dir (tmp_path, a fresh directory every test
# run: test_resolved_corpus._run_build builds into tmp_path / "build").
# Byte-freezing that raw text would make every refreeze session rewrite
# every resolved golden on this fragment alone, with no content change at
# all. (?:\.\./)+ (not a fixed count) tolerates whatever depth WEST_TOPDIR
# sits at under the filesystem root on a given machine.
_DTS_BUILD_PROVENANCE_RE = re.compile(
    r"(?:\.\./)+tmp/pytest-of-[^/\s]+/pytest-\d+/[^/\s]+/build/(rig/[^:\s*]+):(\d+)")


def normalize_dts_provenance(text: str) -> str:
    """Replace a resolved zephyr.dts's pytest-tmp-dir-dependent provenance
    comment paths with a stable placeholder, keeping the meaningful
    generated-file-relative part (rig/<file>:<line>) intact — comments
    only, so dts_equiv.py's structural comparison (which ignores comments)
    is unaffected either way; this exists purely so a refreeze's diff shows
    real content changes, not tmp-path churn."""
    return _DTS_BUILD_PROVENANCE_RE.sub(r"<RIGC_BUILD>/\1:\2", text)


def zephyr_base() -> str:
    """The zephyr tree the expander / dts_equiv.py need, from $ZEPHYR_BASE."""
    value = os.environ.get("ZEPHYR_BASE")
    if not value:
        pytest.fail(
            "ZEPHYR_BASE is not set — export it (the zephyr-rigs tree), the "
            "same way scripts/check.sh requires.")
    return value


def normalize(text: str, zb: Optional[str]) -> str:
    """Replace machine-/run-specific absolute paths with stable placeholders
    before freezing/comparing: the expander's own temp workdir,
    $ZEPHYR_BASE, and the repo root (in that order — repo root and zephyr
    base can each be a prefix of the other under a shared workspace topdir, so
    the more specific substitutions must land first). This function only
    replaces machine-specific paths; WHETHER what is left compares
    byte-exact or by contract is freeze_or_assert's decision, per artifact.

    zb is None for a golden-comparing test that needs no real Zephyr tree at
    all (a hermetic fixture) -- that one substitution is skipped rather than
    forcing every such caller through zephyr_base()'s hard failure just to
    normalize output that never contained a $ZEPHYR_BASE path to begin
    with. Every other substitution still applies unconditionally."""
    text = _WORKDIR_RE.sub("<RIGC_WORKDIR>", text)
    if zb is not None:
        text = text.replace(zb, "<ZEPHYR_BASE>")
    text = text.replace(str(REPO_ROOT), "<REPO_ROOT>")
    text = text.replace(str(WEST_TOPDIR), "<WEST_TOPDIR>")
    return text


def render_argv(result: "subprocess.CompletedProcess[str]") -> str:
    """Shell-quoted rendering of a completed subprocess's own argv, for a
    failure assertion to interpolate alongside stdout/stderr -- .args is
    exactly what subprocess.run was given, so this needs no extra plumbing
    at any call site: -s cannot show a captured subprocess's command (only
    the test process's own stdout), and no assertion in this suite named
    the command that produced a failure until this existed."""
    return shlex.join(str(part) for part in result.args)


def write_rerun_script(script_dir: Path, cwd: Path, cmd: List[str],
                       env: Dict[str, str]) -> Path:
    """Write an executable rerun.sh into script_dir: a standalone re-run of
    this exact subprocess invocation, mirroring cmake/dts.cmake's own
    rerun-expand.sh (shebang, set -e, the env-then-argv shape) -- written
    BEFORE the subprocess runs, so it survives even a failing invocation,
    exactly like the cmake precedent keeps its script after a FAILED
    configure. Composes with pytest's tmp_path_retention_policy (default
    failed): a failing test's tmp dir, and therefore this script, is kept
    without any extra flag; -o tmp_path_retention_policy=all keeps a
    passing one's too.

    cwd is recorded as an explicit cd line rather than left to whatever
    directory the script happens to be run from: a diagnostic that renders
    a process-cwd-relative path would otherwise reproduce DIFFERENTLY than
    the original failure, defeating the point of a reproduction script.

    Only the env entries this invocation's caller added on top of the
    inherited environment are exported -- recording every inherited
    variable would bury the ones that actually distinguish this
    invocation, and would embed values (e.g. a caller's current PATH) that
    have nothing to do with reproducing it."""
    lines = [
        "#!/bin/sh",
        "# regenerate: rewritten on every test run -- edits here do not persist.",
        "# Standalone re-run of this test's own subprocess invocation, e.g. under",
        f"# a debugger: copy the env + argv below into "
        f"'python3 -m pdb -m {RIG_EXPAND_COMPILE} ...'.",
        "set -e",
        f"cd {shlex.quote(str(cwd))}",
    ]
    for key, value in env.items():
        if os.environ.get(key) != value:
            lines.append(f"export {key}={shlex.quote(value)}")
    lines.append("exec " + " ".join(shlex.quote(str(c)) for c in cmd) + ' "$@"')
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / "rerun.sh"
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script


@dataclasses.dataclass(frozen=True)
class RigCase:
    """One corpus rig, identified by its rig.yml rig.name — also its
    folder name under boards/rigs/ (rigs are named underscored, board/
    shield-symmetric: a rig's folder and its rig.name are the same
    string) — the board the HARNESS supplies for it, and the expected
    verdict.

    `board` is this table's own answer to "what does this rig build
    against", not rig.yml's (board-coordinate-s6-brief.md Sec 3, RULED):
    since S6, no corpus rig.yml declares a board at all, so nothing here
    reads one back out of rig.yml — this field is the injected value
    every corpus build (run_expand's --board, west build-rig's -b) uses,
    the harness acting as the invocation strict symmetry says supplies
    it. It is the value each rig was frozen against BEFORE S6 too (S6's
    own acceptance criterion 2: RIG_BOARD must come back byte-unchanged),
    never a new choice."""

    name: str
    board: str
    accept: bool
    category: Optional[str] = None   # expected phys-* code, reject rigs only


# The full corpus of rigs this suite freezes goldens for, with the board
# each one builds against and the verdict each one is expected to produce.
ACCEPT_CASES: List[RigCase] = [
    RigCase("nucleo_datalogger", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("quail_temp_farm", "mikroe_quail/stm32f427xx/rig", True),
    RigCase("quail_sockets", "mikroe_quail/stm32f427xx/rig", True),
    RigCase("nucleo_wifi_logger_ok", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("frdm_eth_nest", "frdm_k64f/mk64f12/rig", True),
    RigCase("nucleo_mux_farm", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("lotus_pwm", "seeeduino_lotus/samd21g18a/rig", True),
    RigCase("lotus_buttons", "seeeduino_lotus/samd21g18a/rig", True),
    # Pilot rig family (rig-variants-revisions.md V1a): this entry alone
    # exercises the BARE target (declared defaults revision=1/variant=
    # variant_a) through the standard emitted/resolved machinery; the other
    # three qualifier combinations get their own dedicated tests below,
    # since a single corpus folder now resolves to more than one tuple.
    RigCase("pilot_variants", "nucleo_f401re/stm32f401xe/rig", True),
    # Shield revisions accept pilot (V1c): shield: i2c_sensor@2 is an
    # ordinary instance-level string, needing no rig-level qualifier at
    # all, so it rides the standard corpus machinery directly rather than
    # a dedicated test function like the rig-axis pilot above.
    RigCase("shield_rev_pilot", "nucleo_f401re/stm32f401xe/rig", True),
    # The two revision axes composing (V1c): this entry covers the BARE
    # target, whose default revision 1 must resolve the sensor to the
    # shield's revision 1; revision 2, where the rig's own delta moves it
    # to the shield's revision 2, gets its own tests since one folder
    # again resolves to more than one tuple.
    RigCase("shield_rev_family", "nucleo_f401re/stm32f401xe/rig", True),
    # Dual-host rig (S6's collapse, board-coordinate-s6-brief.md Sec 5):
    # this entry rides the BARE target on its PRIMARY board (nucleo) --
    # the same one it was frozen against before the collapse, when it was
    # still the declared default variant. The second board (frdm) gets
    # its own dedicated emitted/resolved tests below via
    # ARD_DATALOGGER_FRDM_BOARD, since one RigCase carries exactly one
    # board and this is the corpus's only rig genuinely built on two.
    RigCase("ard_datalogger", "nucleo_f401re/stm32f401xe/rig", True),
]

REJECT_CASES: List[RigCase] = [
    RigCase("nucleo_wifi_logger", "nucleo_f401re/stm32f401xe/rig", False, "phys-net"),
    RigCase("quail_dup_th", "mikroe_quail/stm32f427xx/rig", False, "phys-addr"),
    RigCase("frdm_cs_clash", "frdm_k64f/mk64f12/rig", False, "phys-cs"),
    RigCase("nucleo_mux_clash", "nucleo_f401re/stm32f401xe/rig", False, "phys-addr"),
    RigCase("lotus_pwm_clash", "seeeduino_lotus/samd21g18a/rig", False, "phys-channel"),
]

ALL_CASES: List[RigCase] = ACCEPT_CASES + REJECT_CASES

# Convenience lookup for the handful of call sites that need a corpus rig's
# board OUTSIDE a parametrized RigCase (a case object already carries its
# own .board directly) -- e.g. the pilot/shield-revision family's shared
# helpers below, which build against a fixed board regardless of which
# qualifier tuple is under test.
RIG_BOARD: Dict[str, str] = {c.name: c.board for c in ALL_CASES}

# ard_datalogger's SECOND board (S6's dual-host collapse, board-coordinate-
# s6-brief.md Sec 5) -- deliberately NOT in RIG_BOARD/RigCase, which carry
# exactly one board per rig; this is the one rig actually built on two, so
# its second board is its own named constant, mirroring how the
# shield-uart-subset fixture pair already names its two boards as literals
# rather than inventing a second-board slot in the corpus table.
ARD_DATALOGGER_FRDM_BOARD = "frdm_k64f/mk64f12/rig"

# The artifact filenames the emitter may produce, shared by
# test_emitted_rejects.py and test_emitted_corpus.py. Order is stable so a
# refreeze's git diff stays readable. rig-gen-includes.dtsi is emitted only
# when a rig declares dt-includes: (today, only lotus_buttons) --
# assert_absent_or_refreeze covers the "correctly absent" case for every
# other corpus rig, the same way it already does for rig-gen.conf.
EMITTED_FILES = ("rig-gen.overlay", "rig-gen-includes.dtsi", "context.cmake",
                 "config-sheet.md", "rig-gen.conf")


# rig_board_name (which read rig.yml's own rig.board back out) is RETIRED
# as of S6 (board-coordinate-s6-brief.md Sec 3, RULED): no corpus rig.yml
# declares a board any more, so there is nothing left for it to read.
# RIG_BOARD / RigCase.board / ARD_DATALOGGER_FRDM_BOARD above are the
# harness's own answer now -- the test corpus table names each rig's
# board, the invocation (run_expand's --board, west build-rig's -b)
# supplies it, and nothing reads it back out of the rig's own metadata.


# ---------------------------------------------------------------- cached plain builds


@dataclasses.dataclass(frozen=True)
class PlainBuild:
    """One board's plain (no shield, no rig) west build --cmake-only — the
    "cached-plain-build pattern": the real recipe (cpp include dirs + edtlib
    bindings dirs) a Zephyr configure computed for this board, recovered
    from its own build_info.yml rather than re-deriving
    cmake/dts.cmake's pre_dt.cmake mirror a second time in Python.
    Session-memoized by board (see plain_build_for) — every rig naming the
    same board reuses ONE configure."""
    board: str
    build_dir: Path

    @property
    def build_info(self) -> Path:
        return self.build_dir / "build_info.yml"

    @property
    def edt_pickle(self) -> Path:
        return self.build_dir / "zephyr" / "edt.pickle"


# Any app works for a cmake-only PLAIN configure; hello_world is the corpus's
# own reference app (see test_resolved_corpus.py).
_PLAIN_BUILD_APP = "zephyr/samples/hello_world"

_plain_build_cache: Dict[str, PlainBuild] = {}


def subprocess_timeout(default: int) -> Optional[int]:
    """The default for every long-running subprocess.run() timeout across
    the integration tests, overridable via RIGC_SUBPROCESS_TIMEOUT (seconds;
    0 disables the timeout). subprocess.run's timeout clock runs in the
    pytest process and is oblivious to a debugger paused inside the child --
    past the timeout it kills that child regardless, ending the debug
    session out from under you. Set RIGC_SUBPROCESS_TIMEOUT=0 (e.g. via a
    project-local .env picked up by nvim-dap-python) while debugging into a
    subprocess.run child. Not applied to the short dts_equiv.py comparisons,
    which carry no timeout of their own."""
    raw = os.environ.get("RIGC_SUBPROCESS_TIMEOUT")
    if not raw:
        return default
    value = int(raw)
    return value if value > 0 else None


def _run_plain_build(board: str, build_dir: Path) -> "subprocess.CompletedProcess[str]":
    """west build --cmake-only -b <board> of hello_world — deliberately
    PLAIN: no --shield, no -DRIG, so this exercises the legacy/plain
    board path a rig-enabling board change must never break. Threads
    board_extra_defines(board) after -- always carries -DRIG_EXPAND_COMPILE
    (a no-op here regardless of value: a plain build never sets -DRIG, so
    dts.cmake's fork returns before ever reading that variable), plus
    -DEXTRA_ZEPHYR_MODULES for the lotus extension only — the same
    mechanism plain_build_for's callers (test_emitted_corpus.py,
    test_board_read.py) get for free, since they never build the cmake
    argv themselves."""
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    cmd = [WEST_EXE, "build", "--cmake-only", "-b", board, _PLAIN_BUILD_APP,
           "-p", "always", "-d", str(build_dir)]
    extra = board_extra_defines(board)
    if extra:
        cmd += ["--", *extra]
    _LOGGER.info("plain build argv: %s", shlex.join(cmd))
    write_rerun_script(build_dir, WEST_TOPDIR, cmd, env)
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                           capture_output=True, text=True,
                           timeout=subprocess_timeout(600))


def plain_build_for(board: str, tmp_path_factory: "pytest.TempPathFactory") -> PlainBuild:
    """The cached-plain-build pattern: build board once per test session
    (memoized across every test in every file that asks for it — a plain
    function rather than a @pytest.fixture(params=...), so a rig case can
    request the ONE board it names without pytest cross-producting every rig
    case against every board)."""
    if board not in _plain_build_cache:
        # A qualified hwmv2 target (e.g. "nucleo_f401re/stm32f401xe/rig")
        # carries "/" -- sanitize for the tmp-dir BASENAME only; board
        # itself is passed to -b unchanged just below.
        build_dir = tmp_path_factory.mktemp(f"plain-{board.replace('/', '_')}")
        result = _run_plain_build(board, build_dir)
        assert result.returncode == 0, (
            f"{board}: plain `west build --cmake-only` (no shield, no rig) "
            f"must configure clean\n--- argv ---\n{render_argv(result)}\n"
            f"--- stdout ---\n"
            f"{result.stdout}\n--- stderr ---\n{result.stderr}")
        _plain_build_cache[board] = PlainBuild(board=board, build_dir=build_dir)
    return _plain_build_cache[board]


def run_expand(rig_yml: Path, out_dir: Path,
               shield_dirs: Optional[List[Path]] = None,
               board: Optional[str] = None,
               board_dts: Optional[Path] = None,
               build_info: Optional[Path] = None,
               bindings_dirs: Optional[List[Path]] = None,
               include_dirs: Optional[List[Path]] = None,
               revision: Optional[str] = None,
               variant: Optional[str] = None,
               connector_dirs: Optional[List[Path]] = None,
               ) -> "subprocess.CompletedProcess[str]":
    """Run python -m <RIG_EXPAND_COMPILE> expand exactly as dts.cmake does
    (modulo the recipe form: dts.cmake passes --include-dir/--bindings-dir
    explicitly;
    this harness reuses a cached plain build's --build-info instead, per the
    cached-plain-build pattern — see plain_build_for) — a real subprocess,
    cwd pinned to the repo root so any process-cwd-relative path a
    diagnostic renders is reproducible regardless of the caller's cwd.

    include_dirs is the cpp -I side of the explicit recipe (cli.py
    --include-dir); a hermetic fixture board whose .dts #includes its own
    fixture-local header needs this alongside bindings_dirs -- board_dts/
    build_info were the only two forms the harness needed until a fixture
    board required an #include of its own, so this was never plumbed
    through until now.

    board_dts/build_info are both None for the unknown-board fixture —
    deliberately, so the CLI exercises boarddt's own name->dts DISCOVERY
    (list_boards.py) and its "board not found" diagnostic, exactly as a bare
    standalone invocation would.

    board threads cli.py's own --board (board-coordinate-s1-brief.md Sec
    4/board-coordinate-s6-brief.md Sec 3): the board the INVOCATION
    supplies, winning over whatever the rig declares (nothing, since S6)
    unconditionally. Omitted (None) means no injection at all -- the rig
    must declare its own board, or the loader rejects it exactly as an
    ordinary `rigc expand` with no -DBOARD would. Every corpus rig call
    site passes this now (RigCase.board), since S6 removed the
    declaration this used to fall back to; a caller wanting the
    un-injected diagnostic path itself (no-board-declared) leaves it
    unset on purpose.

    revision/variant carry the SELECTED qualifier axis values (rig-variants-
    revisions.md V1a) — the harness's stand-in for what cmake/dts.cmake's
    fork would resolve via list_rigs.py before invoking this same CLI.
    Omitted (None) means a bare target: the loader applies the rig's own
    declared default, if any.

    connector_dirs is cli.py's --connector-dir (repeatable): a fixture rig
    that must MATE a shield against a synthetic connector type needs this,
    since ctypes_registry's default is the real dts/bindings/connectors
    directory alone. Each type's header still resolves through
    include_dirs, not a separate list — see cli.py's own docstring."""
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")
    dirs = shield_dirs if shield_dirs is not None else [SHIELD_DIR]
    cmd = [sys.executable, "-m", RIG_EXPAND_COMPILE, "expand", str(rig_yml)]
    for d in dirs:
        cmd += ["--shield-dir", str(d)]
    if board is not None:
        cmd += ["--board", board]
    if board_dts is not None:
        cmd += ["--board-dts", str(board_dts)]
    if build_info is not None:
        cmd += ["--build-info", str(build_info)]
    for b in bindings_dirs or []:
        cmd += ["--bindings-dir", str(b)]
    for i in include_dirs or []:
        cmd += ["--include-dir", str(i)]
    for c in connector_dirs or []:
        cmd += ["--connector-dir", str(c)]
    if revision is not None:
        cmd += ["--revision", revision]
    if variant is not None:
        cmd += ["--variant", variant]
    cmd += ["--out-dir", str(out_dir)]
    _LOGGER.info("expand argv: %s", shlex.join(cmd))
    write_rerun_script(out_dir, REPO_ROOT, cmd, env)
    return subprocess.run(cmd, env=env, cwd=str(REPO_ROOT),
                           capture_output=True, text=True,
                           timeout=subprocess_timeout(120))


def freeze_or_assert(golden_path: Path, content: str) -> None:
    """Write content as the golden (RIGC_REFREEZE=1) or assert it matches
    the committed fixture, with a readable failure message on mismatch.

    context.cmake, config-sheet.md, and rig-gen-includes.dtsi
    (golden_path.name, not a directory check -- this is the single seam
    every EMITTED_FILES artifact passes through) compare STRUCTURALLY:
    context.cmake as a key -> value mapping, with RIG_DEPENDS as a set;
    config-sheet.md as the facts it carries (instance/socket/address/
    index/... -- see compare.py), never its prose rendering;
    rig-gen-includes.dtsi as the ORDERED header list dt-includes:
    declared. rig-gen.overlay compares through compare_overlay (targeted
    assertions only -- its semantics ride the zephyr.dts + dts_equiv.py
    comparison instead) EXCEPT for golden_path.parent.name (the rig's own
    golden directory) satisfying overlay_is_byte_compared -- the one rig
    with no zephyr.dts, which stays byte-compared so it keeps SOME check
    on this artifact.

    What remains byte-compared is exit_code and stderr.txt, and those two
    stay that way PERMANENTLY -- not pending a comparator. The reject
    corpus's rendered diagnostic wording is a user-facing product surface
    (a rig author reads it), which is the whole reason those goldens
    exist. Loosening them is not a later slice; it is out of scope by
    ruling."""
    if REFREEZE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(content)
        return
    if not golden_path.is_file():
        pytest.fail(
            f"golden missing: {golden_path}\n"
            f"(run with RIGC_REFREEZE=1 to create it, then inspect + "
            f"commit deliberately)")
    expected = golden_path.read_text()
    if golden_path.name == "context.cmake":
        mismatch = compare_context_cmake(expected, content)
        if mismatch is not None:
            pytest.fail(f"golden mismatch: {golden_path}\n{mismatch}")
        return
    if golden_path.name == "config-sheet.md":
        mismatch = compare_config_sheet(expected, content)
        if mismatch is not None:
            pytest.fail(f"golden mismatch: {golden_path}\n{mismatch}")
        return
    if golden_path.name == "rig-gen-includes.dtsi":
        mismatch = compare_includes_dtsi(expected, content)
        if mismatch is not None:
            pytest.fail(f"golden mismatch: {golden_path}\n{mismatch}")
        return
    if (golden_path.name == "rig-gen.overlay"
            and not overlay_is_byte_compared(golden_path.parent.name)):
        mismatch = compare_overlay(expected, content)
        if mismatch is not None:
            pytest.fail(f"golden mismatch: {golden_path}\n{mismatch}")
        return
    if expected != content:
        diff = "\n".join(difflib.unified_diff(
            expected.splitlines(), content.splitlines(),
            fromfile=str(golden_path), tofile="<observed>", lineterm=""))
        pytest.fail(f"golden mismatch: {golden_path}\n{diff}")


def assert_absent_or_refreeze(golden_path: Path) -> None:
    """The counterpart of freeze_or_assert for an artifact the current run did
    NOT produce: under refreeze, drop a now-stale golden; otherwise assert
    none is committed — a golden for a file the expander no longer emits is
    itself a drift worth catching, not something to pass silently."""
    if REFREEZE:
        if golden_path.is_file():
            golden_path.unlink()
        return
    assert not golden_path.is_file(), (
        f"golden {golden_path} exists but this run produced no such file")


# `build` is the only marker on this tree, so no marker-census hook is
# needed: `pytest --collect-only -m build` answers which tests carry it,
# and tests/unit/test_layer_discipline.py asserts statically that every
# test reaching a west/cmake launch carries it.
