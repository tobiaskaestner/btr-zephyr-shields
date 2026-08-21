"""Multi-bus sockets: a socket may offer more than one bus of the same
kind (multi-bus-socket schema). Proved with a NEW fixture connector type
only (socket,fixture-multibus, tests/fixtures/dts/multibus-connectors/)
-- no real board or shield in the corpus needs this, following the same
fixture-connector precedent socket,fixture-nexus already established for
test_reference_shields.py.

`multibus_board.dts` offers ONE socket with two independent, named SPI
buses (socket,spi-sensors / socket,spi-motors), each with its own
binding-default cs_pool, mated by two fixture shields on the SAME socket
instance (accept case, below) plus a third shield naming a bus the
connector type's vocabulary allows but no socket ever wires (reject
case). No golden is frozen here, the same shape test_reference_shields.py
already uses for a fixture-only accept scenario: this feature adds no
new corpus consumer for a golden to protect, and every assertion below
targets the specific fact under test rather than the whole artifact.

test_multibus_expand_and_build_round_trip (the one @pytest.mark.build
test) is the only test in this module that launches a real toolchain --
see its own docstring for why a REAL `west build-rig` is unreachable for
a fixture-only connector type (ctypes_registry.load_types's
connector_dirs is never threaded by cmake/dts.cmake for a real build) and
what it checks instead.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (FIXTURES_DIR, REPO_ROOT, WEST_EXE, WEST_TOPDIR,
                      assert_fixture_local, render_argv, run_expand,
                      subprocess_timeout, write_rerun_script, zephyr_base)

sys.path.insert(0, str(REPO_ROOT / "scripts"))

_BOARD_DTS = FIXTURES_DIR / "boards" / "mainboards" / "multibus_board.dts"
# A directory of its own, deliberately separate from
# tests/fixtures/dts/connectors/ (fixture-nexus.yaml's own home): that
# directory's OWN registry test (test_connector_bindings.py) asserts it
# holds EXACTLY {"fixture-nexus"}, so adding a second type there would
# perturb an existing, unrelated fixture's own precise assertion.
_CONNECTOR_BINDINGS = FIXTURES_DIR / "dts" / "multibus-connectors"
_CONNECTOR_INCLUDE = FIXTURES_DIR / "include"
_SHIELDS = FIXTURES_DIR / "boards" / "rigs" / "multibus-sockets" / "shields"
_ACCEPT_RIG = FIXTURES_DIR / "boards" / "rigs" / "multibus-sockets" / "rig.yml"
_REJECT_RIG = (FIXTURES_DIR / "boards" / "rigs" / "multibus-sockets-reject"
               / "rig.yml")


def _run(rig_yml: Path, out_dir: Path) -> "subprocess.CompletedProcess[str]":
    assert_fixture_local([_BOARD_DTS, _CONNECTOR_BINDINGS, _CONNECTOR_INCLUDE,
                          _SHIELDS])
    return run_expand(
        rig_yml, out_dir,
        board="multibus_fixture_board",
        shield_dirs=[_SHIELDS],
        board_dts=_BOARD_DTS,
        bindings_dirs=[_CONNECTOR_BINDINGS],
        include_dirs=[_CONNECTOR_INCLUDE],
        connector_dirs=[_CONNECTOR_BINDINGS])


def test_multibus_accept_both_devices_land_at_cs_index_zero(tmp_path: Path) -> None:
    """Accept case: fixture_spi_sensor (bus: "spi-sensors") and
    fixture_spi_motor (bus: "spi-motors") both mate multibus_socket and
    both build. The negative control this project's discipline demands:
    both devices may legally share the SAME
    cs-pool INDEX (0) without collision, since they sit on DIFFERENT
    physical SPI buses -- CS allocation is scoped by bus.path, never by
    kind string. Without this assertion, a regression that accidentally
    merged the two buses' CS namespaces back into one would still pass
    every other check (it would only ever place ONE of the two devices,
    reporting the other's single-candidate pool exhausted -- itself
    caught by the plain accept assertion below, but the shared-index
    claim is the more specific, mutation-resistant one)."""
    out_dir = tmp_path / "out"
    result = _run(_ACCEPT_RIG, out_dir)

    assert result.returncode == 0, (
        f"multibus_sockets: expected accept\n--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()
    assert "&multibus_spi_sensors {" in overlay
    assert "&multibus_spi_motors {" in overlay
    # Both devices are the sole member of their own bus's scope, so both
    # land at cs-gpios array index 0 (the FIRST, and only, cs-gpios entry
    # in each of their two &<bus> blocks) -- the shared-index claim.
    sensors_block = overlay.split("&multibus_spi_sensors {")[1].split("};")[0]
    motors_block = overlay.split("&multibus_spi_motors {")[1].split("};")[0]
    assert "sensor@0" in sensors_block
    assert "driver@0" in motors_block


def test_multibus_reject_unknown_named_bus_is_phys_subset(tmp_path: Path) -> None:
    """Reject case: fixture_spi_unknown declares bus: "spi-unknown-name"
    -- allowed by the fixture-multibus connector type's own bus_proxies
    vocabulary (so it mates the socket and passes lang-shield-proxy), but
    no socket of that type ever wires a matching phandle. subset_gaps'
    exact-string membership check (needed - set(offered)) rejects it
    without any fallback, confirmed with a genuinely novel string rather
    than a name that happens to coincide with something else in the
    corpus."""
    out_dir = tmp_path / "out"
    result = _run(_REJECT_RIG, out_dir)

    assert result.returncode != 0, (
        "multibus_sockets_reject: expected reject (phys-subset)")
    assert "phys-subset" in result.stderr
    assert "spi-unknown-name" in result.stderr


# ---------------------------------------------------------------- build round-trip


@pytest.mark.build
def test_multibus_expand_and_build_round_trip(tmp_path: Path) -> None:
    """The expand+build round trip for the fixture connector. A REAL
    `west build-rig` cannot exercise this
    fixture connector type at all: registry.load_types's connector_dirs
    override is a standalone-CLI recipe argument (cli.py's own
    --connector-dir), and cmake/dts.cmake's fork never threads it for a
    real build -- pass 2 always resolves connector types from
    dts/bindings/connectors alone, so shields.py would reject
    "fixture-multibus" as an unknown connector type before the analyzer
    ever ran. What IS reachable, and what this test proves instead: the
    devicetree TEXT the expander emits for a multi-bus socket is genuine,
    toolchain-buildable devicetree, not merely internally-consistent
    Python state that happens to satisfy this suite's own dts_equiv.py.

    Mechanism: run the expander exactly as the accept test above does
    (hermetic, no real board needed for THAT step), then hand its
    rig-gen.overlay -- together with multibus_board.dts's own node
    content, which supplies every label the overlay references -- to a
    REAL `west build --cmake-only` as EXTRA_DTC_OVERLAY_FILE entries, on
    top of an arbitrary already-working real board (nucleo_f401re/
    stm32f401xe/rig, reused rather than invented so this needs no new
    board bring-up). Real dtc/cmake accepting the combined tree is the
    round trip: the fixture board's own devicetree is unrelated to
    nucleo_f401re's, so a label failing to resolve or a malformed
    property would fail THIS configure exactly as it would fail a real
    board's, regardless of which arbitrary board supplies the toolchain."""
    out_dir = tmp_path / "expand-out"
    expand_result = _run(_ACCEPT_RIG, out_dir)
    assert expand_result.returncode == 0, (
        f"multibus_sockets: expected accept\n--- stderr ---\n{expand_result.stderr}")

    # multibus_board.dts, minus its own leading "/dts-v1/;" (a version
    # marker legal only once per merged devicetree; the REAL base board
    # -b supplies its own) -- everything else is plain node text, valid
    # as an EXTRA_DTC_OVERLAY_FILE fragment exactly as authored.
    board_lines = _BOARD_DTS.read_text().splitlines(keepends=True)
    board_overlay_text = "".join(
        line for line in board_lines if line.strip() != "/dts-v1/;")
    combined = tmp_path / "multibus-combined.overlay"
    combined.write_text(
        board_overlay_text + "\n" + (out_dir / "rig-gen.overlay").read_text())

    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    build_dir = tmp_path / "build"
    cmd = [
        WEST_EXE, "build", "-b", "nucleo_f401re/stm32f401xe/rig",
        "zephyr/samples/hello_world", "--cmake-only", "-p", "always",
        "-d", str(build_dir), "--",
        f"-DEXTRA_DTC_OVERLAY_FILE={combined}",
    ]
    write_rerun_script(build_dir, WEST_TOPDIR, cmd, env)
    result = subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                            capture_output=True, text=True,
                            timeout=subprocess_timeout(600))
    assert result.returncode == 0, (
        "multibus_sockets: expected the combined fixture-board + rig-gen "
        "overlay to configure clean against a real toolchain\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    assert "multibus_socket" in zephyr_dts
    assert "spi_sensors_ctrl" in zephyr_dts
    assert "spi_motors_ctrl" in zephyr_dts
    # Non-vacuous: the emitted device nodes must actually land NESTED
    # under their respective bus controller, and that controller's own
    # cs-gpios must resolve through the fixture socket -- not merely
    # appear SOMEWHERE in the merged tree. Sliced to the controller's own
    # node body (up to its closing brace at the SAME one-tab indent the
    # opening brace is at; a child node's own closing brace is indented
    # deeper, so this never truncates early).
    sensors_ctrl = zephyr_dts.split("spi_sensors_ctrl {")[1].split("\n\t};")[0]
    assert "cs-gpios = < &multibus_socket" in sensors_ctrl
    assert "sensor_inst_fss_sensor: sensor@0 {" in sensors_ctrl

    motors_ctrl = zephyr_dts.split("spi_motors_ctrl {")[1].split("\n\t};")[0]
    assert "cs-gpios = < &multibus_socket" in motors_ctrl
    assert "motor_inst_fsm_driver: driver@0 {" in motors_ctrl
