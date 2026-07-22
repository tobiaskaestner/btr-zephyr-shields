"""Tier-2 goldens: the real pass-2 `zephyr.dts`, via `west build-rig
--cmake-only` (Bridge-A saferail 1, amended 2026-07-23 — see
`claude/rigs/implementation-plan.md`).

This is THE invariant that must hold across every phase of the rewrite: when
a phase legitimately changes tier 1 (e.g. step 2's pwm/adc nexus rewiring),
tier 2 is the oracle and tier 1 gets re-frozen with a justification note.

For each ACCEPT rig: `west build-rig --cmake-only` must configure clean, and
the produced `zephyr.dts` must be STRUCTURALLY EQUIVALENT (via
`scripts/dts_equiv.py`, NOT a byte diff — labels/phandle numbers/ordering are
irrelevant, see that script's docstring) to the frozen golden.

For each REJECT rig: the same `--cmake-only` invocation must FAIL, and its
output must contain the expected `phys-*` diagnostic category string —
diagnostic parity through west/CMake (saferail 4).

These tests run a real CMake configure per rig (several minutes for the full
13-rig corpus) — marked `@pytest.mark.build`; `CHECK_FAST=1` (scripts/check.sh)
deselects them via `pytest -m "not build"`.

Refreeze: RIGEXP_REFREEZE=1 rewrites tests/goldens/<rig-name>/zephyr.dts
(ACCEPT rigs only) instead of comparing — inspect the diff before committing,
same rule as tier 1.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    ACCEPT_CASES,
    DTS_EQUIV,
    GOLDENS_DIR,
    REFREEZE,
    REJECT_CASES,
    RigCase,
    WEST_EXE,
    WEST_TOPDIR,
    zephyr_base,
)

pytestmark = pytest.mark.build

# Relative to WEST_TOPDIR — any app works for a cmake-only configure; hello_world
# is the corpus's own reference app (implementation-plan.md, NEXT-SESSION.md).
_APP = "zephyr/samples/hello_world"


def _run_build(rig_name: str, build_dir: Path) -> "subprocess.CompletedProcess[str]":
    """`west build-rig --cmake-only` for one rig — a temp build dir; `-p
    always` wipes it, so nothing durable may be read back from `build_dir`
    beyond this one process's own output."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, _APP,
        "--cmake-only", "-p", "always", "-d", str(build_dir),
    ]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=dict(os.environ),
                           capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("case", ACCEPT_CASES, ids=lambda c: c.name)
def test_tier2_accept_zephyr_dts(case: RigCase, tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    result = _run_build(case.name, build_dir)
    assert result.returncode == 0, (
        f"{case.name}: expected `west build-rig --cmake-only` to configure "
        f"clean (an ACCEPT rig)\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    candidate = build_dir / "zephyr" / "zephyr.dts"
    assert candidate.is_file(), f"{case.name}: no zephyr.dts at {candidate}"

    golden = GOLDENS_DIR / case.name / "zephyr.dts"
    if REFREEZE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(candidate.read_text())
        return

    if not golden.is_file():
        pytest.fail(
            f"golden missing: {golden} (run with RIGEXP_REFREEZE=1 to create it)")

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(golden), str(candidate)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        f"{case.name}: zephyr.dts not structurally equivalent to the golden "
        f"(dts_equiv.py):\n{check.stdout}\n{check.stderr}")


@pytest.mark.parametrize("case", REJECT_CASES, ids=lambda c: c.name)
def test_tier2_reject_configure_fails(case: RigCase, tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    result = _run_build(case.name, build_dir)
    assert result.returncode != 0, (
        f"{case.name}: expected `west build-rig --cmake-only` to FAIL (a "
        f"REJECT rig) but it exited 0")

    combined = result.stdout + result.stderr
    assert case.category is not None   # every REJECT case declares one
    assert f"[{case.category}]" in combined, (
        f"{case.name}: expected diagnostic category [{case.category}] in "
        f"the build output (diagnostic parity through west/CMake, saferail "
        f"4)\n{combined}")
