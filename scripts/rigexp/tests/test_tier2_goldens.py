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
    normalize_dts_provenance,
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
        golden.write_text(normalize_dts_provenance(candidate.read_text()))
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
    (cmake/dts.cmake). It lands under `cmake.vendor-specific.rig.*` (the
    schema's own downstream-owned escape hatch, NOT the naively-expected
    `cmake.rig.*` -- build-schema.yaml is upstream, not ours to extend; see
    cmake/dts.cmake and the handoff report). Deliberately uses frdm-eth-nest:
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


def test_tier2_build_info_shield_dir_collision(tmp_path: Path) -> None:
    """Shield name-collision across BOARD_ROOT (review finding, 2026-07-23):
    BOARD_ROOT holds both btr-shields and $ZEPHYR_BASE (zephyr-rigs), and the
    latter ships its own stock `boards/shields/adafruit_data_logger` -- a
    plain upstream shield (no `<name>.shield` rig-template marker), same name
    as btr-shields' rig-template shield. `cmake/dts.cmake`'s shield tail must
    resolve the collision to OUR (rig-template) folder, not whichever root
    `list_shields.py` happened to sort last. `nucleo-datalogger` (s1) is the
    corpus rig naming `adafruit_data_logger`, so it's the collision witness."""
    build_dir = tmp_path / "build"
    result = _run_build("nucleo-datalogger", build_dir)
    assert result.returncode == 0, (
        f"nucleo-datalogger: expected `west build-rig --cmake-only` to "
        f"configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")
    assert "shield name 'adafruit_data_logger' is offered by" not in (
        result.stdout + result.stderr), (
        "unexpected ambiguity warning -- the marker-preference rule should "
        "have resolved this collision silently")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    shield_dir = rig["shield-dirs"]
    assert "adafruit_data_logger" in shield_dir
    assert str(REPO_ROOT) in shield_dir, (
        f"shield-dirs must record btr-shields' OWN adafruit_data_logger "
        f"folder (the rig-template one, marked by "
        f"adafruit_data_logger.shield), not $ZEPHYR_BASE's stock shield of "
        f"the same name: {shield_dir!r}")
    zb = zephyr_base()
    assert not shield_dir.startswith(zb), (
        f"shield-dirs resolved into $ZEPHYR_BASE ({zb}) -- the stock, "
        f"non-rig-template adafruit_data_logger folder won the collision: "
        f"{shield_dir!r}")


def test_tier2_rig_depends_provenance(tmp_path: Path) -> None:
    """Dependency-tracking handoff (RIG_DEPENDS): `cmake/dts.cmake` appends
    the expander's own generated `context.cmake` `RIG_DEPENDS` list to
    CMAKE_CONFIGURE_DEPENDS, so editing a `.shield` template or a connector
    binding — not just rig.yml/rig.conf/rig.overlay, the pre-existing static
    registrations — retriggers configure. What's testable HERE, without
    mutating any corpus file (forbidden — modifying fixtures in a test would
    make the test self-fulfilling): that `context.cmake`, as ACTUALLY written
    into a real build dir, carries the rig.yml, at least one `.shield`, one
    connector plug YAML, and the board `.dts`. The other half — that CMake
    actually retriggers configure when a CMAKE_CONFIGURE_DEPENDS-listed file
    changes — is CMake's own long-standing guarantee for that property, not
    something this project needs to (or reasonably can, without touching
    corpus files) re-prove; `set_property(... APPEND PROPERTY
    CMAKE_CONFIGURE_DEPENDS ...)` in dts.cmake is the whole of our contribution."""
    build_dir = tmp_path / "build"
    result = _run_build("lotus-pwm", build_dir)
    assert result.returncode == 0, (
        f"lotus-pwm: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    context_cmake = (build_dir / "rig" / "context.cmake").read_text()
    depends_line = next(
        (line for line in context_cmake.splitlines() if "RIG_DEPENDS" in line),
        None)
    assert depends_line is not None, (
        f"no RIG_DEPENDS in generated context.cmake:\n{context_cmake}")

    assert "boards/rigs/lotus-pwm/rig.yml" in depends_line
    assert "boards/shields/grove_servo/grove_servo.shield" in depends_line
    assert "dts/connectors/plug,grove.yaml" in depends_line
    assert "boards/seeed/seeeduino_lotus_btr/seeeduino_lotus_btr.dts" in depends_line
