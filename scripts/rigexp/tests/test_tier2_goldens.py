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
import pickle
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import (
    ACCEPT_CASES,
    DTS_EQUIV,
    GOLDENS_DIR,
    REFREEZE,
    REJECT_CASES,
    REPO_ROOT,
    RigCase,
    WEST_EXE,
    WEST_TOPDIR,
    zephyr_base,
)

# Triggers python-devicetree onto sys.path (from $ZEPHYR_BASE) as an
# import-time side effect, exactly like test_board_read.py -- needed to
# unpickle a real edt.pickle below (its classes live in `devicetree.edtlib`).
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import edt_build  # noqa: E402,F401

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


def test_tier2_lotus_pwm_semantic_pin(tmp_path: Path) -> None:
    """The PERMANENT semantic invariant Bridge-A step 2b's socket-relative
    pwm/adc emission must hold (review finding, 2026-07-23): pass-2's own
    `edt.pickle` -- the resolved `ControllerAndData` edtlib built while
    compiling the real devicetree -- must show the servo's `pwms` and the
    light sensor's `io-channels` landing on the SAME (controller, channel/
    input, period) as before the socket-relative rewrite, now that
    `vnd,pwm-servo`/`vnd,light-sensor` are typed (dts/bindings/test/) and
    pass-2 actually resolves the nexus instead of leaving the props inert.
    This is the REAL ground truth the vacuous devicetree_generated.h
    identity check (phase 2b's original proof) failed to be, since neither
    compatible had a binding typing these props at the time."""
    build_dir = tmp_path / "build"
    result = _run_build("lotus-pwm", build_dir)
    assert result.returncode == 0, (
        f"lotus-pwm: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    with open(build_dir / "zephyr" / "edt.pickle", "rb") as f:
        edt = pickle.load(f)
    nodes = {node.path: node for node in edt.nodes}

    servo = nodes["/servo_1/servo"]
    assert len(servo.props["pwms"].val) == 1, (
        "servo pwms must resolve to exactly ONE entry — a trailing bogus "
        "element means a flags cell crept back into the 2-cell emission")
    pwm_spec = servo.props["pwms"].val[0]
    assert "tcc0" in pwm_spec.controller.labels, (
        f"servo pwms resolved to {pwm_spec.controller!r}, expected tcc0")
    assert pwm_spec.data == {"channel": 0, "period": 20000000}, (
        f"servo pwms resolved to {pwm_spec.data!r}, expected "
        "channel 0 / period 20000000ns")

    light = nodes["/light_1/light"]
    assert len(light.props["io-channels"].val) == 1, (
        "light io-channels must resolve to exactly ONE entry")
    adc_spec = light.props["io-channels"].val[0]
    assert "adc0" in adc_spec.controller.labels, (
        f"light io-channels resolved to {adc_spec.controller!r}, expected adc0")
    assert adc_spec.data == {"input": 0}, (
        f"light io-channels resolved to {adc_spec.data!r}, expected input 0")


def test_tier2_build_info_rig_provenance(tmp_path: Path) -> None:
    """rig-build provenance (NEW requirement): a rig build must record what
    it looked at into `build_info.yml`, via zephyr's own `build_info()`
    (cmake/rig.cmake). It lands under `cmake.vendor-specific.rig.*` (the
    schema's own downstream-owned escape hatch, NOT the naively-expected
    `cmake.rig.*` -- build-schema.yaml is upstream, not ours to extend; see
    cmake/rig.cmake and the handoff report). Deliberately uses frdm-eth-nest:
    it names TWO distinct shields (arduino_uno_click, eth_click carried by
    THREE instances) -- the case that caught a real bug (build_info()'s
    vendor-specific VALUE silently truncates a multi-element CMake list to
    its first entry unless pre-JOINed)."""
    build_dir = tmp_path / "build"
    result = _run_build("frdm-eth-nest", build_dir)
    assert result.returncode == 0, (
        f"frdm-eth-nest: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    assert rig["name"] == "frdm-eth-nest"
    assert rig["board"] == "frdm_k64f_btr"
    assert rig["rig-yml"].endswith("boards/rigs/s6-eth-click/rig.yml")
    assert rig["board-dts"].endswith(
        "boards/nxp/frdm_k64f_btr/frdm_k64f_btr.dts")

    shields = {s.strip() for s in rig["shields"].split(",")}
    assert shields == {"arduino_uno_click", "eth_click"}, (
        f"rig-provenance 'shields' must list BOTH distinct shields "
        f"(not truncated to the first): {rig['shields']!r}")
    assert "arduino_uno_click" in rig["shield-dirs"]
    assert "eth_click" in rig["shield-dirs"]
    assert Path(rig["out-dir"]).is_dir()
