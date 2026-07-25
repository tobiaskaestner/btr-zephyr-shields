"""Tier-2 goldens: the real pass-2 `zephyr.dts`, via `west build-rig
--cmake-only`.

This is THE invariant that must hold regardless of how tier 1's exact text
is produced: if a future change to the expander legitimately alters what
tier 1 freezes (e.g. how a nexus is wired in the overlay), tier 2 confirms
whether the BUILT devicetree actually changed; tier 1 then gets re-frozen
with a justification note, using tier 2 as the oracle that nothing else
moved.

For each ACCEPT rig: `west build-rig --cmake-only` must configure clean, and
the produced `zephyr.dts` must be STRUCTURALLY EQUIVALENT (via
`scripts/dts_equiv.py`, NOT a byte diff — labels/phandle numbers/ordering are
irrelevant, see that script's docstring) to the frozen golden.

For each REJECT rig: the same `--cmake-only` invocation must FAIL, and its
output must contain the expected `phys-*` diagnostic category string — the
same diagnostic category must surface through the full west/CMake path, not
just the standalone expander.

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
from typing import List, Optional

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
    board_extra_defines,
    normalize_dts_provenance,
    rig_board_name,
    zephyr_base,
)

# Triggers python-devicetree onto sys.path (from $ZEPHYR_BASE) as an
# import-time side effect, exactly like test_board_read.py -- needed to
# unpickle a real edt.pickle below (its classes live in `devicetree.edtlib`).
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import edt_build  # noqa: E402,F401

pytestmark = pytest.mark.build

# Relative to WEST_TOPDIR — any app works for a cmake-only configure;
# hello_world is the reference app this suite standardizes on.
_APP = "zephyr/samples/hello_world"


def _run_build(rig_name: str, build_dir: Path,
                extra_defines: Optional[List[str]] = None) -> "subprocess.CompletedProcess[str]":
    """`west build-rig --cmake-only` for one rig — a temp build dir; `-p
    always` wipes it, so nothing durable may be read back from `build_dir`
    beyond this one process's own output. `extra_defines` is threaded after
    `--` -- empty for every rig except the lotus ones, whose board needs
    `-DEXTRA_ZEPHYR_MODULES=<bridle_root>`."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, _APP,
        "--cmake-only", "-p", "always", "-d", str(build_dir),
    ]
    if extra_defines:
        cmd += ["--", *extra_defines]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=dict(os.environ),
                           capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("case", ACCEPT_CASES, ids=lambda c: c.name)
def test_tier2_accept_zephyr_dts(case: RigCase, tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name(case.name))
    result = _run_build(case.name, build_dir, extra)
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
    extra = board_extra_defines(rig_board_name(case.name))
    result = _run_build(case.name, build_dir, extra)
    assert result.returncode != 0, (
        f"{case.name}: expected `west build-rig --cmake-only` to FAIL (a "
        f"REJECT rig) but it exited 0")

    combined = result.stdout + result.stderr
    assert case.category is not None   # every REJECT case declares one
    assert f"[{case.category}]" in combined, (
        f"{case.name}: expected diagnostic category [{case.category}] in "
        f"the build output -- the same category must surface through the "
        f"full west/CMake path, not just the standalone expander\n{combined}")


def test_tier2_user_extra_conf_wins_over_rig(tmp_path: Path) -> None:
    """The rig's own `<rigname>_defconfig` rides `shield_conf_files` (an
    APPEND) rather than prepending onto EXTRA_CONF_FILE -- "user extras
    win" now falls out of upstream's own merge ordering
    (kconfig.cmake's `merge_config_files`: shield_conf_files lands BEFORE
    EXTRA_CONF_FILE_AS_LIST), not from anything this fork does. Nothing of
    ours enforces that ordering any more, so pin it directly on the real
    outcome: a user-passed `-DEXTRA_CONF_FILE` overriding a symbol
    nucleo_mux_farm_defconfig also sets must win in the resulting
    `.config`. Contends over CONFIG_I2C_TCA954X_ROOT_INIT_PRIO (61 in the
    rig's own defconfig); the driver's BUILD_ASSERT(CHANNEL_INIT_PRIO >
    ROOT_INIT_PRIO) only fires on a full compile, never at --cmake-only, but
    55 keeps the override physically sensible regardless (still below the
    channel's 62)."""
    user_conf = tmp_path / "user.conf"
    user_conf.write_text("CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=55\n")

    build_dir = tmp_path / "build"
    result = _run_build("nucleo_mux_farm", build_dir,
                        [f"-DEXTRA_CONF_FILE={user_conf}"])
    assert result.returncode == 0, (
        f"nucleo_mux_farm: expected `west build-rig --cmake-only` with a "
        f"user -DEXTRA_CONF_FILE to configure clean\n--- stdout ---\n"
        f"{result.stdout}\n--- stderr ---\n{result.stderr}")

    dotconfig = (build_dir / "zephyr" / ".config").read_text()
    assert "CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=55" in dotconfig, (
        "user -DEXTRA_CONF_FILE must win over the rig's own "
        "nucleo_mux_farm_defconfig (CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=61)\n"
        f"--- .config ---\n{dotconfig}")
    assert "CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=61" not in dotconfig, (
        f"the rig's own value leaked into .config alongside the user's\n"
        f"--- .config ---\n{dotconfig}")


def test_tier2_lotus_pwm_semantic_pin(tmp_path: Path) -> None:
    """The permanent semantic invariant the expander's socket-relative
    pwm/adc emission must hold: pass-2's own `edt.pickle` -- the resolved
    `ControllerAndData` edtlib builds while compiling the real devicetree --
    must show the servo's `pwms` and the light sensor's `io-channels`
    landing on the expected (controller, channel/input, period). This is
    real ground truth rather than a text check on the generated overlay:
    `vnd,pwm-servo`/`vnd,light-sensor` are typed (dts/bindings/test/), so
    pass 2 actually resolves the socket's pwm-map/io-channel-map nexus
    instead of leaving the props inert -- a text-only check on the emitted
    `pwms`/`io-channels` line could pass even if the nexus itself were
    unresolvable."""
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name("lotus_pwm"))
    result = _run_build("lotus_pwm", build_dir, extra)
    assert result.returncode == 0, (
        f"lotus_pwm: expected `west build-rig --cmake-only` to configure "
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
    """A rig build must record what it looked at into `build_info.yml`, via
    zephyr's own `build_info()` (cmake/dts.cmake). It lands under
    `cmake.vendor-specific.rig.*` -- `build-schema.yaml` is upstream and not
    ours to extend, so this rides the schema's own downstream-owned escape
    hatch rather than the naively-expected `cmake.rig.*`. Deliberately uses
    frdm_eth_nest: it names TWO distinct shields (arduino_uno_click,
    eth_click carried by THREE instances), because `build_info()`'s
    vendor-specific VALUE silently truncates a multi-element CMake list to
    its first entry unless pre-JOINed -- a single-shield rig would not catch
    a regression in that join."""
    build_dir = tmp_path / "build"
    result = _run_build("frdm_eth_nest", build_dir)
    assert result.returncode == 0, (
        f"frdm_eth_nest: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    assert rig["name"] == "frdm_eth_nest"
    assert rig["board"] == "frdm_k64f/mk64f12/rig"
    assert rig["yml"].endswith("boards/rigs/frdm_eth_nest/rig.yml")
    assert rig["board-dts"].endswith(
        "boards/extend/nxp/frdm_k64f/frdm_k64f_mk64f12_rig.dts")

    shields = {s.strip() for s in rig["shields"].split(",")}
    assert shields == {"arduino_uno_click", "eth_click"}, (
        f"rig-provenance 'shields' must list BOTH distinct shields "
        f"(not truncated to the first): {rig['shields']!r}")
    assert "arduino_uno_click" in rig["shield-dirs"]
    assert "eth_click" in rig["shield-dirs"]
    assert Path(rig["out-dir"]).is_dir()

    # The generated overlay is unconditional; frdm_eth_nest also has its own
    # hand-authored `frdm_eth_nest_defconfig` (one of the corpus's 8 rigs
    # that do), but no `rig-gen.conf` -- the emitter never produces one
    # today, so `defconfig-gen` must be absent, not present-but-empty.
    assert Path(rig["overlay-gen"]).is_file()
    assert rig["defconfig"].endswith("frdm_eth_nest_defconfig")
    assert "defconfig-gen" not in rig


def test_tier2_build_info_shield_dir_collision(tmp_path: Path) -> None:
    """Shield name-collision across BOARD_ROOT: BOARD_ROOT holds both
    btr-shields and $ZEPHYR_BASE (zephyr-rigs), and the
    latter ships its own stock `boards/shields/adafruit_data_logger` -- a
    plain upstream shield (no `<name>.shield` rig-template marker), same name
    as btr-shields' rig-template shield. `cmake/dts.cmake`'s shield tail must
    resolve the collision to OUR (rig-template) folder, not whichever root
    `list_shields.py` happened to sort last. `nucleo_datalogger` is the
    corpus rig naming `adafruit_data_logger`, so it's the collision witness."""
    build_dir = tmp_path / "build"
    result = _run_build("nucleo_datalogger", build_dir)
    assert result.returncode == 0, (
        f"nucleo_datalogger: expected `west build-rig --cmake-only` to "
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
    binding — not just rig.yml or the rig's own `<name>_defconfig`/
    `<name>.overlay`, the pre-existing static registrations — retriggers
    configure. What's testable HERE, without
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
    extra = board_extra_defines(rig_board_name("lotus_pwm"))
    result = _run_build("lotus_pwm", build_dir, extra)
    assert result.returncode == 0, (
        f"lotus_pwm: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    context_cmake = (build_dir / "rig" / "context.cmake").read_text()
    depends_line = next(
        (line for line in context_cmake.splitlines() if "RIG_DEPENDS" in line),
        None)
    assert depends_line is not None, (
        f"no RIG_DEPENDS in generated context.cmake:\n{context_cmake}")

    assert "boards/rigs/lotus_pwm/rig.yml" in depends_line
    assert "boards/shields/grove_servo/grove_servo.shield" in depends_line
    assert "dts/bindings/connectors/grove.yaml" in depends_line
    assert ("boards/extend/seeed/seeeduino_lotus/"
            "seeeduino_lotus_samd21g18a_rig.dts") in depends_line
