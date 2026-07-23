"""Shared fixtures and helpers for the rig-expander golden tests.

Bridge-A saferail 1 (amended 2026-07-23, `claude/rigs/implementation-plan.md`):
freeze the CURRENT observed behavior of the rig expander for every corpus rig,
as committed fixtures, in two tiers:

  tier 1 (test_tier1_goldens.py) — expander-level, every rig, fast: verdict +
  rendered diagnostics + emitted overlay/context.cmake/config-sheet.md/conf.

  tier 2 (test_tier2_goldens.py, `@pytest.mark.build`) — the real pass-2
  `zephyr.dts`, the structural-equivalence invariant that survives phases of
  the rewrite that legitimately change tier 1 (e.g. step 2's nexus rewiring).

This module holds only the plumbing both tiers share: the corpus table, path
discovery (self-locating — no workspace-name literals), the expander
subprocess runner, normalization, and the freeze/assert primitives.
`expectations.yml` is deliberately never read here — parked to
`claude/hw-expectations/`, never gated (see `claude/rigs/parked.md`).
"""
from __future__ import annotations

import dataclasses
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import yaml

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]   # scripts/rigexp/tests -> btr-shields
GOLDENS_DIR = TESTS_DIR / "goldens"
FIXTURES_DIR = TESTS_DIR / "fixtures"
SHIELD_DIR = REPO_ROOT / "boards" / "shields"
RIGS_DIR = REPO_ROOT / "boards" / "rigs"
DTS_EQUIV = REPO_ROOT / "scripts" / "dts_equiv.py"

# board name -> its OWN .dts, relative to the repo root (Conv. 4: typed
# socket nodes live in the board's own devicetree). Shared by test_tier1_
# goldens.py (--board-dts per rig) and test_board_read.py (the plain-build /
# edt.pickle-cross-check corpus).
#
# nucleo_f401re: hwmv2 board EXTENSION (E1 slice, board-extension-
# migration.md), not a clone -- `board:` is the FULL qualified target
# (rig.yml names it explicitly, no expander-side sugar) and its .dts lives
# under boards/extend/, layered on top of the REAL upstream
# zephyr-rigs/boards/st/nucleo_f401re/nucleo_f401re.dts via `#include`. The
# other three boards stay `_btr` clones (E2/E3 -- untouched by this slice).
BOARD_DTS: Dict[str, str] = {
    "nucleo_f401re/stm32f401xe/rig":
        "boards/extend/st/nucleo_f401re/nucleo_f401re_stm32f401xe_rig.dts",
    "mikroe_quail_btr": "boards/mikroe/mikroe_quail_btr/mikroe_quail_btr.dts",
    "frdm_k64f_btr": "boards/nxp/frdm_k64f_btr/frdm_k64f_btr.dts",
    "seeeduino_lotus_btr": "boards/seeed/seeeduino_lotus_btr/seeeduino_lotus_btr.dts",
}
BOARDS: List[str] = list(BOARD_DTS)


def _find_west_topdir(start: Path) -> Path:
    """Walk upward from `start` to the west workspace root (the directory
    holding `.west/`) — self-locating, no hardcoded workspace-name literal."""
    for candidate in (start, *start.parents):
        if (candidate / ".west").is_dir():
            return candidate
    raise RuntimeError(f"no .west/ found above {start} — is this a west workspace?")


WEST_TOPDIR = _find_west_topdir(REPO_ROOT)
_VENV_WEST = WEST_TOPDIR / ".venv" / "bin" / "west"
WEST_EXE = str(_VENV_WEST) if _VENV_WEST.is_file() else "west"

# RIGEXP_REFREEZE=1 rewrites goldens instead of asserting against them (both
# tiers). Always inspect `git diff tests/goldens` after a refreeze — it must
# reflect an INTENTIONAL, understood behavior change, never silent drift.
REFREEZE = bool(os.environ.get("RIGEXP_REFREEZE"))

_WORKDIR_RE = re.compile(r"/tmp/rigexp-[^/\s]+")

# A tier-2 `zephyr.dts`'s own DT provenance comments (`/* in PATH:LINE */`,
# `/* node 'X' defined in PATH:LINE */`) render PATH relative to the build's
# cwd (WEST_TOPDIR) — e.g. `../../../tmp/pytest-of-tobi/pytest-52/
# test_tier2_accept_zephyr_dts_l0/build/rig/overlay:25` — which embeds
# pytest's OWN per-session tmp dir (`tmp_path`, a fresh directory every test
# run: `test_tier2_goldens._run_build` builds into `tmp_path / "build"`).
# Byte-freezing that raw text would make every refreeze session rewrite all
# 8 tier-2 goldens on this fragment alone, with no content change at all.
# `(?:\.\./)+` (not a fixed count) tolerates whatever depth WEST_TOPDIR sits
# at under the filesystem root on a given machine.
_DTS_BUILD_PROVENANCE_RE = re.compile(
    r"(?:\.\./)+tmp/pytest-of-[^/\s]+/pytest-\d+/[^/\s]+/build/(rig/[^:\s*]+):(\d+)")


def normalize_dts_provenance(text: str) -> str:
    """Replace a tier-2 `zephyr.dts`'s pytest-tmp-dir-dependent provenance
    comment paths with a stable placeholder, keeping the meaningful
    generated-file-relative part (`rig/<file>:<line>`) intact — comments
    only; the DT content itself is untouched, and dts_equiv.py's structural
    comparison ignores comments regardless (assert-mode was never affected;
    this is purely a refreeze-churn fix, see test_tier2_goldens.py)."""
    return _DTS_BUILD_PROVENANCE_RE.sub(r"<RIGEXP_BUILD>/\1:\2", text)


def zephyr_base() -> str:
    """The zephyr tree the expander / dts_equiv.py need, from $ZEPHYR_BASE."""
    value = os.environ.get("ZEPHYR_BASE")
    if not value:
        pytest.fail(
            "ZEPHYR_BASE is not set — export it (the zephyr-rigs tree), the "
            "same way scripts/check.sh requires.")
    return value


def normalize(text: str, zb: str) -> str:
    """Replace machine-/run-specific absolute paths with stable placeholders
    before freezing/comparing (saferail 1): the expander's own temp workdir,
    $ZEPHYR_BASE, and the repo root (in that order — repo root and zephyr
    base can each be a prefix of the other under a shared workspace topdir, so
    the more specific substitutions must land first). Everything else must
    match byte-exact."""
    text = _WORKDIR_RE.sub("<RIGEXP_WORKDIR>", text)
    text = text.replace(zb, "<ZEPHYR_BASE>")
    text = text.replace(str(REPO_ROOT), "<REPO_ROOT>")
    text = text.replace(str(WEST_TOPDIR), "<WEST_TOPDIR>")
    return text


@dataclasses.dataclass(frozen=True)
class RigCase:
    """One corpus rig: its folder under `boards/rigs/`, its rig.yml identity
    (`rig.name` — NOT the folder basename), and the expected verdict."""

    folder: str
    name: str
    accept: bool
    category: Optional[str] = None   # expected phys-* code, reject rigs only


# The 3a/3b/3c corpus, per the task's expected-verdict table (verified against
# actual `rigexp expand` output before freezing — see the handoff report).
ACCEPT_CASES: List[RigCase] = [
    RigCase("s1", "nucleo-datalogger", True),
    RigCase("s5-temp-farm", "quail-temp-farm", True),
    RigCase("s4b-sockets", "quail-sockets", True),
    RigCase("s2-wifi-logger-ok", "nucleo-wifi-logger-ok", True),
    RigCase("s6-eth-click", "frdm-eth-nest", True),
    RigCase("s8-mux", "nucleo-mux-farm", True),
    RigCase("lotus-pwm", "lotus-pwm", True),
    RigCase("lotus-buttons", "lotus-buttons", True),
]

REJECT_CASES: List[RigCase] = [
    RigCase("s2-wifi-logger", "nucleo-wifi-logger", False, "phys-net"),
    RigCase("s4b-dup-addr", "quail-dup-th", False, "phys-addr"),
    RigCase("s6-cross-layer", "frdm-cs-clash", False, "phys-cs"),
    RigCase("s8-mux-collision", "nucleo-mux-clash", False, "phys-addr"),
    RigCase("lotus-pwm-clash", "lotus-pwm-clash", False, "phys-channel"),
]

ALL_CASES: List[RigCase] = ACCEPT_CASES + REJECT_CASES


def rig_yml_name(folder: str) -> str:
    """The rig.yml `rig.name` for a corpus folder — rig identity, not the
    folder basename (see the `RigCase` docstring)."""
    with open(RIGS_DIR / folder / "rig.yml") as f:
        doc = yaml.safe_load(f)
    return str(doc["rig"]["name"])


def rig_board_name(folder: str) -> str:
    """The rig.yml `rig.board` for a corpus folder — which of `BOARDS` this
    rig needs a plain build (and --board-dts) for."""
    with open(RIGS_DIR / folder / "rig.yml") as f:
        doc = yaml.safe_load(f)
    return str(doc["rig"]["board"])


# ---------------------------------------------------------------- cached plain builds


@dataclasses.dataclass(frozen=True)
class PlainBuild:
    """One board's plain (no shield, no rig) `west build --cmake-only` — the
    "cached-plain-build pattern" (Bridge-A saferail 13): the real recipe
    (cpp include dirs + edtlib bindings dirs) a Zephyr configure computed for
    this board, recovered from its own `build_info.yml` rather than
    re-deriving `cmake/rig.cmake`'s pre_dt.cmake mirror a second time in
    Python. Session-memoized by board (see `plain_build_for`) — every rig
    naming the same board reuses ONE configure."""
    board: str
    build_dir: Path

    @property
    def build_info(self) -> Path:
        return self.build_dir / "build_info.yml"

    @property
    def edt_pickle(self) -> Path:
        return self.build_dir / "zephyr" / "edt.pickle"


# Any app works for a cmake-only PLAIN configure; hello_world is the corpus's
# own reference app (see test_tier2_goldens.py).
_PLAIN_BUILD_APP = "zephyr/samples/hello_world"

_plain_build_cache: Dict[str, PlainBuild] = {}


def _run_plain_build(board: str, build_dir: Path) -> "subprocess.CompletedProcess[str]":
    """`west build --cmake-only -b <board>` of `hello_world` — deliberately
    PLAIN: no `--shield`, no `-DRIG`, so this exercises the legacy/plain
    board path a board conversion must never break (saferail 11)."""
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    cmd = [WEST_EXE, "build", "--cmake-only", "-b", board, _PLAIN_BUILD_APP,
           "-p", "always", "-d", str(build_dir)]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                           capture_output=True, text=True, timeout=600)


def plain_build_for(board: str, tmp_path_factory: "pytest.TempPathFactory") -> PlainBuild:
    """The cached-plain-build pattern: build `board` once per test session
    (memoized across every test in every file that asks for it — a plain
    function rather than a `@pytest.fixture(params=...)`, so a rig case can
    request the ONE board it names without pytest cross-producting every rig
    case against every board)."""
    if board not in _plain_build_cache:
        # A qualified hwmv2 target (e.g. "nucleo_f401re/stm32f401xe/rig")
        # carries "/" -- sanitize for the tmp-dir BASENAME only; `board`
        # itself is passed to `-b` unchanged just below.
        build_dir = tmp_path_factory.mktemp(f"plain-{board.replace('/', '_')}")
        result = _run_plain_build(board, build_dir)
        assert result.returncode == 0, (
            f"{board}: plain `west build --cmake-only` (no shield, no rig) "
            f"must configure clean — saferail 11\n--- stdout ---\n"
            f"{result.stdout}\n--- stderr ---\n{result.stderr}")
        _plain_build_cache[board] = PlainBuild(board=board, build_dir=build_dir)
    return _plain_build_cache[board]


def run_expand(rig_yml: Path, out_dir: Path,
               shield_dirs: Optional[List[Path]] = None,
               board_dts: Optional[Path] = None,
               build_info: Optional[Path] = None,
               bindings_dirs: Optional[List[Path]] = None,
               ) -> "subprocess.CompletedProcess[str]":
    """Run `python -m rigexp expand` exactly as rig.cmake does (modulo the
    recipe form: rig.cmake passes --include-dir/--bindings-dir explicitly;
    this harness reuses a cached plain build's --build-info instead, per the
    cached-plain-build pattern — see `plain_build_for`) — a real subprocess,
    cwd pinned to the repo root so any process-cwd-relative path a
    diagnostic renders (e.g. boarddt.py's unknown-board message, which uses a
    bare `os.path.relpath`) is reproducible regardless of the caller's cwd.

    `board_dts`/`build_info` are both None for the unknown-board fixture —
    deliberately, so the CLI exercises boarddt's own name->dts DISCOVERY
    (list_boards.py) and its "board not found" diagnostic, exactly as a bare
    standalone invocation would."""
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
    cmd += ["--out-dir", str(out_dir)]
    return subprocess.run(cmd, env=env, cwd=str(REPO_ROOT),
                           capture_output=True, text=True, timeout=120)


def freeze_or_assert(golden_path: Path, content: str) -> None:
    """Write `content` as the golden (RIGEXP_REFREEZE=1) or assert it matches
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
