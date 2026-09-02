"""The corpus of rigs under boards/rigs/, plus a set of synthetic fixtures,
is frozen at two levels, named for the ARTIFACT each freezes rather than
the order the two layers were built:

  emitted (test_emitted_rejects.py, test_emitted_corpus.py) —
  expander-level, every rig: verdict + rendered diagnostics + whatever of
  EMITTED_FILES (harness.py) the run produced. How each is compared is NOT
  uniform, and rigc/tests/compare.py holds the contracts: exit_code and
  stderr.txt byte-exact; context.cmake as a key -> value mapping;
  config-sheet.md as the facts it carries; rig-gen.overlay as only the
  facts a resolved zephyr.dts cannot see (its semantics ride that
  comparison instead), with one declared byte-compared exception;
  rig-gen-includes.dtsi as an ordered header list; rig-gen.conf asserted
  absent. Only the path placeholders in harness.py are normalized first.
  Split in two so no module mixes unit and integration tests:
  test_emitted_rejects.py holds the fixture-only rejects that
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

This module holds the corpus-tethered half of what used to be the single
tests/integration/conftest.py: the corpus table (rig_dir(), BOARD_DTS,
RigCase/ACCEPT_CASES/REJECT_CASES/ALL_CASES/RIG_BOARD), the per-board
extra-cmake-defines rule (board_extra_defines, bridle_root), and the
cached-plain-build machinery (PlainBuild, plain_build_for). It imports the
generic plumbing (path discovery, the expander subprocess runner,
normalization, the freeze/assert primitives) from harness.py rather than
duplicating it. expectations.yml is deliberately never read here — it is
emitted but never gated (see claude/hw-expectations/).
"""

from __future__ import annotations

import dataclasses
import functools
import logging
import os
import shlex
import subprocess
from pathlib import Path

import pytest
from harness import (
    REPO_ROOT,
    RIG_EXPAND_COMPILE,
    WEST_EXE,
    WEST_TOPDIR,
    render_argv,
    subprocess_timeout,
    write_rerun_script,
    zephyr_base,
)
from harness import run_expand as _harness_run_expand

_LOGGER = logging.getLogger(__name__)

SHIELD_DIR = REPO_ROOT / "boards" / "shields"
RIGS_DIR = REPO_ROOT / "boards" / "rigs"


@functools.cache
def rig_dir(name: str) -> Path:
    """The on-disk directory for corpus rig `name`, wherever it actually
    lives under boards/rigs/ -- flat (every rig but five) or one level
    deeper, under boards/rigs/clash/ (the REJECT_CASES that cannot build).
    A rig's folder basename is asserted
    identical to its own rig.yml rig.name by test_corpus_rig_identity, so
    finding the one directory named `name` anywhere under RIGS_DIR is
    exactly as canonical as reading the name back out of rig.yml, and
    needs no import of scripts/list_rigs.py here -- that module stays
    untyped and outside this package's own mypy graph (see
    test_list_rigs_cmakeformat.py's identical reasoning for why it
    duplicates list_rigs._cmake_list_escape rather than importing it).

    Memoized (a fixed corpus, looked up by the same handful of names
    across many parametrized cases in one session) -- callers must not
    mutate the returned Path in place, though Path is immutable in the
    ways this module ever uses it."""
    matches = [d for d in sorted(RIGS_DIR.rglob(name)) if d.is_dir() and (d / "rig.yml").is_file()]
    assert len(matches) == 1, (
        f"expected exactly one rig directory named {name!r} under {RIGS_DIR}, found {matches}"
    )
    return matches[0]


# board name -> its OWN .dts, relative to the repo root (typed
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
BOARD_DTS: dict[str, str] = {
    "nucleo_f401re/stm32f401xe/rig": (
        "boards/extend/st/nucleo_f401re/nucleo_f401re_stm32f401xe_rig.dts"
    ),
    "mikroe_quail/stm32f427xx/rig": "boards/extend/mikroe/quail/mikroe_quail_stm32f427xx_rig.dts",
    "frdm_k64f/mk64f12/rig": "boards/extend/nxp/frdm_k64f/frdm_k64f_mk64f12_rig.dts",
    "seeeduino_lotus/samd21g18a/rig": (
        "boards/extend/seeed/seeeduino_lotus/seeeduino_lotus_samd21g18a_rig.dts"
    ),
    "m5stack_nanoc6/esp32c6/hpcore/rig": (
        "boards/extend/m5stack/m5stack_nanoc6/m5stack_nanoc6_esp32c6_hpcore_rig.dts"
    ),
}
BOARDS: list[str] = list(BOARD_DTS)

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
            f"checkout missing from this workspace?"
        )
    return root


def board_extra_defines(board: str) -> list[str]:
    """Per-board extra -D cmake defines every build path (plain build,
    the resolved-corpus `west build --cmake-only -- -DRIG=`, cmake-alone)
    must thread through identically.

    -DRIG_EXPAND_COMPILE=<value> (the differential-harness module knob)
    is threaded UNCONDITIONALLY, for every
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


@dataclasses.dataclass(frozen=True)
class RigCase:
    """One corpus rig, identified by its rig.yml rig.name — also its
    folder name under boards/rigs/ (rigs are named underscored, board/
    shield-symmetric: a rig's folder and its rig.name are the same
    string) — the board the HARNESS supplies for it, and the expected
    verdict.

    `board` is this table's own answer to "what does this rig build
    against", not rig.yml's: no corpus rig.yml declares a board at all,
    so nothing here reads one back out of rig.yml — this field is the
    injected value every corpus build (run_expand's --board,
    test_resolved_corpus.py's own `west build`'s -b) uses, the harness
    acting as the invocation supplies it. RIG_BOARD must come back
    byte-unchanged in every golden."""

    name: str
    board: str
    accept: bool
    category: str | None = None  # expected phys-* code, reject rigs only


# The full corpus of rigs this suite freezes goldens for, with the board
# each one builds against and the verdict each one is expected to produce.
ACCEPT_CASES: list[RigCase] = [
    RigCase("nucleo_datalogger", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("quail_temp_farm", "mikroe_quail/stm32f427xx/rig", True),
    RigCase("quail_sockets", "mikroe_quail/stm32f427xx/rig", True),
    # can_span_click plugs two of quail's own mikroBUS sockets at once
    # (test_multiplug_shield.py's own ad-hoc rig exercises the same
    # shield/board pair already; this is that same pairing carried into
    # the permanent corpus, so the emitted/resolved golden machinery
    # protects it too).
    RigCase("quail_can_span", "mikroe_quail/stm32f427xx/rig", True),
    # mikrobus_span_adapter re-exports ONE mixed-parent socket,mikrobus
    # from two of quail's own mikroBUS sockets, with the EXISTING
    # eth_click plugged on it (test_multiplug_carrier.py's own ad-hoc rig
    # exercises the same shield/board pair already; this is that same
    # pairing carried into the permanent corpus).
    RigCase("quail_eth_span", "mikroe_quail/stm32f427xx/rig", True),
    RigCase("nucleo_wifi_logger_ok", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("frdm_eth_nest", "frdm_k64f/mk64f12/rig", True),
    RigCase("nucleo_mux_farm", "nucleo_f401re/stm32f401xe/rig", True),
    RigCase("lotus_pwm", "seeeduino_lotus/samd21g18a/rig", True),
    # The pwm-shaped counterpart of lotus_buttons' gpio-leds collection:
    # two grove_pwm_led entries aggregated into one pwm-leds node, each
    # keeping its own resolved channel (tcc0 ch0 / ch1). The only corpus
    # user of shield,collect on a NON-gpio function.
    RigCase("lotus_pwm_led", "seeeduino_lotus/samd21g18a/rig", True),
    RigCase("lotus_buttons", "seeeduino_lotus/samd21g18a/rig", True),
    # Pilot rig family: this entry alone
    # exercises the BARE target (declared defaults revision=1/variant=
    # variant_a) through the standard emitted/resolved machinery; the other
    # three qualifier combinations get their own dedicated tests below,
    # since a single corpus folder now resolves to more than one tuple.
    RigCase("pilot_variants", "nucleo_f401re/stm32f401xe/rig", True),
    # Shield revisions accept pilot: shield: i2c_sensor@2 is an
    # ordinary instance-level string, needing no rig-level qualifier at
    # all, so it rides the standard corpus machinery directly rather than
    # a dedicated test function like the rig-axis pilot above.
    RigCase("shield_rev_pilot", "nucleo_f401re/stm32f401xe/rig", True),
    # The two revision axes composing: this entry covers the BARE
    # target, whose default revision 1 must resolve the sensor to the
    # shield's revision 1; revision 2, where the rig's own delta moves it
    # to the shield's revision 2, gets its own tests since one folder
    # again resolves to more than one tuple.
    RigCase("shield_rev_family", "nucleo_f401re/stm32f401xe/rig", True),
    # Dual-host rig: this entry rides the BARE target on its PRIMARY
    # board (nucleo) -- the declared default variant. The second board
    # (frdm) gets its own dedicated emitted/resolved tests below via
    # ARD_DATALOGGER_FRDM_BOARD, since one RigCase carries exactly one
    # board and this is the corpus's only rig genuinely built on two.
    RigCase("ard_datalogger", "nucleo_f401re/stm32f401xe/rig", True),
    # grove_sens (the first real corpus shield behind the Grove socket's
    # I2C bus proxy, dts/bindings/connectors/grove.yaml's socket,i2c):
    # config: pins the address strap to its NON-DEFAULT domain state
    # (0x77), a real user of the label-resolution config: path
    # with an AUTHORED address, distinct from the silent/allocated half
    # the singleton-law census already exercises for this same shield.
    RigCase("grove_sens_pinned", "m5stack_nanoc6/esp32c6/hpcore/rig", True),
    # The first NESTED carrier promotion in the permanent corpus -- a
    # Grove Base Shield V2 on the Nucleo Arduino header re-exports typed
    # Grove sockets, and one I2C shield (grove_sens_bme280) plus one
    # digital shield (grove_btn) plug straight into two of those EXPOSED
    # sockets, exactly nucleo_mux_farm's own carrier-then-instance shape
    # but through a passive carrier instead of an active mux.
    RigCase("nucleo_grove_farm", "nucleo_f401re/stm32f401xe/rig", True),
]

REJECT_CASES: list[RigCase] = [
    RigCase("nucleo_wifi_logger", "nucleo_f401re/stm32f401xe/rig", False, "phys-net"),
    RigCase("quail_dup_th", "mikroe_quail/stm32f427xx/rig", False, "phys-addr"),
    RigCase("frdm_cs_clash", "frdm_k64f/mk64f12/rig", False, "phys-cs"),
    RigCase("nucleo_mux_clash", "nucleo_f401re/stm32f401xe/rig", False, "phys-addr"),
    RigCase("lotus_pwm_clash", "seeeduino_lotus/samd21g18a/rig", False, "phys-channel"),
]

ALL_CASES: list[RigCase] = ACCEPT_CASES + REJECT_CASES

# Convenience lookup for the handful of call sites that need a corpus rig's
# board OUTSIDE a parametrized RigCase (a case object already carries its
# own .board directly) -- e.g. the pilot/shield-revision family's shared
# helpers below, which build against a fixed board regardless of which
# qualifier tuple is under test.
RIG_BOARD: dict[str, str] = {c.name: c.board for c in ALL_CASES}

# ard_datalogger's SECOND board -- deliberately NOT in RIG_BOARD/RigCase,
# which carry exactly one board per rig; this is the one rig actually
# built on two, so its second board is its own named constant, mirroring
# how the shield-uart-subset fixture pair already names its two boards as
# literals rather than inventing a second-board slot in the corpus table.
ARD_DATALOGGER_FRDM_BOARD = "frdm_k64f/mk64f12/rig"

# No corpus rig.yml declares a board: RIG_BOARD / RigCase.board /
# ARD_DATALOGGER_FRDM_BOARD above are the harness's own answer -- the test
# corpus table names each rig's board, the invocation (run_expand's
# --board, test_resolved_corpus.py's own `west build`'s -b) supplies it,
# and nothing reads it back out of the rig's own metadata.


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

_plain_build_cache: dict[str, PlainBuild] = {}


def _run_plain_build(board: str, build_dir: Path) -> subprocess.CompletedProcess[str]:
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
    cmd = [
        WEST_EXE,
        "build",
        "--cmake-only",
        "-b",
        board,
        _PLAIN_BUILD_APP,
        "-p",
        "always",
        "-d",
        str(build_dir),
    ]
    extra = board_extra_defines(board)
    if extra:
        cmd += ["--", *extra]
    _LOGGER.info("plain build argv: %s", shlex.join(cmd))
    write_rerun_script(build_dir, WEST_TOPDIR, cmd, env)
    return subprocess.run(
        cmd,
        cwd=str(WEST_TOPDIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=subprocess_timeout(600),
    )


def plain_build_for(board: str, tmp_path_factory: pytest.TempPathFactory) -> PlainBuild:
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
            f"{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        _plain_build_cache[board] = PlainBuild(board=board, build_dir=build_dir)
    return _plain_build_cache[board]


def run_expand(
    rig_yml: Path,
    out_dir: Path,
    shield_dirs: list[Path] | None = None,
    board: str | None = None,
    board_dts: Path | None = None,
    build_info: Path | None = None,
    bindings_dirs: list[Path] | None = None,
    include_dirs: list[Path] | None = None,
    revision: str | None = None,
    variant: str | None = None,
    connector_dirs: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    """harness.run_expand, with the repo-shield tether restored: when
    shield_dirs is None this defaults to [SHIELD_DIR] rather than harness's
    own no-default -- this default IS the corpus tether that keeps every
    caller relying on it (test_emitted_corpus.py, test_resolved_corpus.py,
    and the rest of this directory's corpus-facing modules) on the stay
    side: they resolve real shields under boards/shields/, which is
    exactly the content this directory exists to keep with the hardware
    definitions rather than travelling with the mechanics."""
    dirs = shield_dirs if shield_dirs is not None else [SHIELD_DIR]
    return _harness_run_expand(
        rig_yml,
        out_dir,
        shield_dirs=dirs,
        board=board,
        board_dts=board_dts,
        build_info=build_info,
        bindings_dirs=bindings_dirs,
        include_dirs=include_dirs,
        revision=revision,
        variant=variant,
        connector_dirs=connector_dirs,
    )
