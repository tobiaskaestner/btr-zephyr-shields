"""Shared fixtures and helpers for the rig-expander golden tests.

The corpus of rigs under boards/rigs/, plus a set of synthetic fixtures,
is frozen at two levels, named for the ARTIFACT each freezes rather than
the order the two layers were built:

  emitted (test_emitted_rejects.py, test_emitted_corpus.py) —
  expander-level, every rig: verdict + rendered diagnostics + whatever of
  rig-gen.overlay/context.cmake/config-sheet.md/rig-gen.conf the run
  produced (EMITTED_FILES, below), frozen byte-exact after normalization.
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
from typing import Dict, FrozenSet, List, Optional, Tuple, Union

import pytest
import yaml

_LOGGER = logging.getLogger(__name__)

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]   # scripts/rigexp/tests -> btr-shields
GOLDENS_DIR = TESTS_DIR / "goldens"
FIXTURES_DIR = TESTS_DIR / "fixtures"
SHIELD_DIR = REPO_ROOT / "boards" / "shields"
RIGS_DIR = REPO_ROOT / "boards" / "rigs"


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
    identically --
    a case-level mechanism keyed on the board string, not a global flag, so
    non-lotus boards get an empty list and their goldens stay byte-identical."""
    if board == _BRIDLE_MODULE_BOARD:
        return [f"-DEXTRA_ZEPHYR_MODULES={bridle_root()}"]
    return []


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

# RIGEXP_REFREEZE=1 rewrites goldens instead of asserting against them (both
# emitted and resolved). Always inspect git diff tests/goldens after a
# refreeze — it must reflect an INTENTIONAL, understood behavior change,
# never silent drift.
REFREEZE = bool(os.environ.get("RIGEXP_REFREEZE"))

_WORKDIR_RE = re.compile(r"/tmp/rigexp-[^/\s]+")

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
    return _DTS_BUILD_PROVENANCE_RE.sub(r"<RIGEXP_BUILD>/\1:\2", text)


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
    the more specific substitutions must land first). Everything else must
    match byte-exact.

    zb is None for a golden-comparing test that needs no real Zephyr tree at
    all (a hermetic fixture) -- that one substitution is skipped rather than
    forcing every such caller through zephyr_base()'s hard failure just to
    normalize output that never contained a $ZEPHYR_BASE path to begin
    with. Every other substitution still applies unconditionally."""
    text = _WORKDIR_RE.sub("<RIGEXP_WORKDIR>", text)
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
    a process-cwd-relative path (e.g. boarddt.py's unknown-board message,
    a bare os.path.relpath) would otherwise reproduce DIFFERENTLY than the
    original failure, defeating the point of a reproduction script.

    Only the env entries this invocation's caller added on top of the
    inherited environment are exported -- recording every inherited
    variable would bury the ones that actually distinguish this
    invocation, and would embed values (e.g. a caller's current PATH) that
    have nothing to do with reproducing it."""
    lines = [
        "#!/bin/sh",
        "# regenerate: rewritten on every test run -- edits here do not persist.",
        "# Standalone re-run of this test's own subprocess invocation, e.g. under",
        "# a debugger: copy the env + argv below into 'python3 -m pdb -m rigexp ...'.",
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
    string), and the expected verdict."""

    name: str
    accept: bool
    category: Optional[str] = None   # expected phys-* code, reject rigs only


# The full corpus of rigs this suite freezes goldens for, with the verdict
# each one is expected to produce.
ACCEPT_CASES: List[RigCase] = [
    RigCase("nucleo_datalogger", True),
    RigCase("quail_temp_farm", True),
    RigCase("quail_sockets", True),
    RigCase("nucleo_wifi_logger_ok", True),
    RigCase("frdm_eth_nest", True),
    RigCase("nucleo_mux_farm", True),
    RigCase("lotus_pwm", True),
    RigCase("lotus_buttons", True),
    # Pilot rig family (rig-variants-revisions.md V1a): this entry alone
    # exercises the BARE target (declared defaults revision=1/variant=
    # variant_a) through the standard emitted/resolved machinery; the other
    # three qualifier combinations get their own dedicated tests below,
    # since a single corpus folder now resolves to more than one tuple.
    RigCase("pilot_variants", True),
    # Shield revisions accept pilot (V1c): shield: i2c_sensor@2 is an
    # ordinary instance-level string, needing no rig-level qualifier at
    # all, so it rides the standard corpus machinery directly rather than
    # a dedicated test function like the rig-axis pilot above.
    RigCase("shield_rev_pilot", True),
    # The two revision axes composing (V1c): this entry covers the BARE
    # target, whose default revision 1 must resolve the sensor to the
    # shield's revision 1; revision 2, where the rig's own delta moves it
    # to the shield's revision 2, gets its own tests since one folder
    # again resolves to more than one tuple.
    RigCase("shield_rev_family", True),
    # Dual-host rig (the metadata/content split, board per variant): this
    # entry rides the BARE target, whose declared default variant (nucleo)
    # resolves to nucleo_f401re/stm32f401xe/rig via rig_board_name's own
    # per-variant fallback above. The frdm variant gets its own dedicated
    # emitted/resolved tests below, since one folder again resolves to more
    # than one tuple, and it is the tuple that carries NO fragment at all.
    RigCase("ard_datalogger", True),
]

REJECT_CASES: List[RigCase] = [
    RigCase("nucleo_wifi_logger", False, "phys-net"),
    RigCase("quail_dup_th", False, "phys-addr"),
    RigCase("frdm_cs_clash", False, "phys-cs"),
    RigCase("nucleo_mux_clash", False, "phys-addr"),
    RigCase("lotus_pwm_clash", False, "phys-channel"),
]

ALL_CASES: List[RigCase] = ACCEPT_CASES + REJECT_CASES

# The artifact filenames the emitter may produce, shared by
# test_emitted_rejects.py and test_emitted_corpus.py. Order is stable so a
# refreeze's git diff stays readable. rig-gen-includes.dtsi is emitted only
# when a rig declares dt-includes: (today, only lotus_buttons) --
# assert_absent_or_refreeze covers the "correctly absent" case for every
# other corpus rig, the same way it already does for rig-gen.conf.
EMITTED_FILES = ("rig-gen.overlay", "rig-gen-includes.dtsi", "context.cmake",
                 "config-sheet.md", "rig-gen.conf")


def rig_board_name(folder: str, variant: Optional[str] = None) -> str:
    """The rig.yml rig.board for a corpus folder — which of BOARDS this
    rig needs a plain build (and --board-dts) for.

    A rig using the per-variant-board shape (no top-level rig.board:, one
    board: per variants: list: entry — ard_datalogger) has no single
    answer, so `variant` picks which one; omitted, it falls back to the
    declared default variant, matching a bare (unqualified) target's own
    resolution."""
    with open(RIGS_DIR / folder / "rig.yml") as f:
        doc = yaml.safe_load(f)
    rig = doc["rig"]
    if "board" in rig:
        return str(rig["board"])
    variants = rig.get("variants") or {}
    selected = variant or variants.get("default")
    for item in variants.get("list") or []:
        if isinstance(item, dict) and item.get("name") == selected:
            return str(item["board"])
    raise KeyError(
        f"rig '{folder}': no board declared for variant {selected!r} "
        f"(neither a top-level rig.board: nor a per-variant one)")


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


def _run_plain_build(board: str, build_dir: Path) -> "subprocess.CompletedProcess[str]":
    """west build --cmake-only -b <board> of hello_world — deliberately
    PLAIN: no --shield, no -DRIG, so this exercises the legacy/plain
    board path a rig-enabling board change must never break. Threads
    board_extra_defines(board) after -- (empty for every board except
    the lotus extension) — the same mechanism plain_build_for's callers
    (test_emitted_corpus.py, test_board_read.py) get for free, since they
    never build the cmake argv themselves."""
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
                           capture_output=True, text=True, timeout=600)


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
               board_dts: Optional[Path] = None,
               build_info: Optional[Path] = None,
               bindings_dirs: Optional[List[Path]] = None,
               include_dirs: Optional[List[Path]] = None,
               revision: Optional[str] = None,
               variant: Optional[str] = None,
               connector_dirs: Optional[List[Path]] = None,
               ) -> "subprocess.CompletedProcess[str]":
    """Run python -m rigexp expand exactly as dts.cmake does (modulo the
    recipe form: dts.cmake passes --include-dir/--bindings-dir explicitly;
    this harness reuses a cached plain build's --build-info instead, per the
    cached-plain-build pattern — see plain_build_for) — a real subprocess,
    cwd pinned to the repo root so any process-cwd-relative path a
    diagnostic renders (e.g. boarddt.py's unknown-board message, which uses a
    bare os.path.relpath) is reproducible regardless of the caller's cwd.

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
    cmd = [sys.executable, "-m", "rigexp", "expand", str(rig_yml)]
    for d in dirs:
        cmd += ["--shield-dir", str(d)]
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
                           capture_output=True, text=True, timeout=120)


def freeze_or_assert(golden_path: Path, content: str) -> None:
    """Write content as the golden (RIGEXP_REFREEZE=1) or assert it matches
    the committed fixture exactly, with a readable unified diff on mismatch."""
    if REFREEZE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(content)
        return
    if not golden_path.is_file():
        pytest.fail(
            f"golden missing: {golden_path}\n"
            f"(run with RIGEXP_REFREEZE=1 to create it, then inspect + "
            f"commit deliberately)")
    expected = golden_path.read_text()
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


# node id -> (module name, the unit/integration markers it carries).
MarkerCensus = Dict[str, Tuple[str, FrozenSet[str]]]

# The markers scripts/markers.sh reports on, in display order -- the same
# three pyproject.toml declares. Deliberately NOT every marker on an item
# (iter_markers() also yields pytest's own parametrize marker, which is
# noise for this report).
_REPORTED_MARKERS = ("unit", "integration", "build")


def pytest_addoption(parser: "pytest.Parser") -> None:
    """--markers-report (scripts/markers.sh): one collection, not three/four
    separate `-m <expr>` collections, and it cannot miss an unmarked test by
    construction -- it walks the FULL collected item list itself rather than
    inferring "unmarked" from what three positive -m passes failed to
    select."""
    parser.addoption(
        "--markers-report", action="store_true", default=False,
        help="print every collected test's node id and its "
             "unit/integration/build markers, then exit without running "
             "anything -- see scripts/markers.sh")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: "pytest.Config",
                                  items: "List[pytest.Item]") -> None:
    """Stash the unit/integration markers of every COLLECTED test, before
    any -m/-k deselection can narrow items down -- tryfirst=True so this
    runs ahead of pytest's own markexpr/keyword filters, which mutate items
    in place. test_marker_discipline.py reads config's stashed census
    rather than request.session.items, since a run invoked as
    pytest -m unit would otherwise only see the unit-selected subset by
    the time a test body executes, making both enforcement checks pass
    vacuously.

    This census is deliberately the ONLY consumer of the pre-deselection
    item list. --markers-report is a SEPARATE consumer
    (pytest_collection_finish, below) reading the post-deselection list --
    filtering this stash instead would silently defeat
    test_marker_discipline's own enforcement under pytest -m unit, which
    is the one property most at risk from making the report filter-aware."""
    census: MarkerCensus = {}
    for item in items:
        markers = frozenset(m.name for m in item.iter_markers()
                            if m.name in ("unit", "integration"))
        # The file portion of the node id (before "::") IS the module --
        # simpler and just as precise as item.module.__name__, and it
        # sidesteps that attribute existing only on pytest.Function, not
        # the base pytest.Item type every collected item is typed as here.
        module = item.nodeid.split("::", 1)[0]
        census[item.nodeid] = (module, markers)
    config._rigexp_marker_census = census  # type: ignore[attr-defined]


def pytest_collection_finish(session: "pytest.Session") -> None:
    """--markers-report (scripts/markers.sh): emitted here, AFTER collection
    (and therefore after every pytest_collection_modifyitems hook,
    including pytest's own -k/-m deselection, has already run) so
    session.items is the POST-deselection list -- -k/-m must actually scope
    this report, unlike the pre-deselection census above. Path scoping
    (a file/directory/node id argument) already worked before this existed,
    since a path narrows what pytest COLLECTS in the first place, upstream
    of both modifyitems and this hook.

    Still walks the item list directly rather than inferring "unmarked"
    from separate -m <expr> passes -- classification (via the census
    stashed above, keyed by nodeid, built before deselection) is orthogonal
    to which items THIS run happens to select."""
    config = session.config
    if not config.getoption("--markers-report"):
        return
    census: MarkerCensus = config._rigexp_marker_census  # type: ignore[attr-defined]
    for item in sorted(session.items, key=lambda i: i.nodeid):
        present = {m.name for m in item.iter_markers()}
        tags = [name for name in _REPORTED_MARKERS if name in present]
        _module, classified = census[item.nodeid]
        if not classified:
            tags.insert(0, "UNMARKED")
        print(f"{item.nodeid}\t{' '.join(tags)}")
    pytest.exit("--markers-report: printed, nothing was run", returncode=0)
