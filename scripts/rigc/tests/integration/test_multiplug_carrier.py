"""Multi-plug carriers, slice 2 (multi-plug-carrier-brief.md): a plural
shield may declare an exposed socket, composed from SEVERAL named
parents. Two halves, mirroring test_multiplug_shield.py's own shape:

  - the REAL corpus example, mikrobus_span_adapter on quail (multi-plug-
    carrier-brief.md Sec 7): plugs two of quail's own mikroBUS sockets and
    re-exports ONE ordinary socket,mikrobus with the EXISTING eth_click
    (byte-untouched) plugged on it. SPI/CS chain through the LEFT parent,
    int-gpios chain through the RIGHT -- the cross-plug falsifier one
    level up from can_span_click's own cross-plug DEVICE ref. This half
    owns acceptance criterion 2.
  - the combined-SPI negative control (Sec 7's fixture-only case, reusing
    the EXISTING fixture-multibus connector type and fixture_spi_sensor/
    fixture_spi_motor shields from test_multibus_socket.py's own fixture
    tree): a plural fixture carrier re-exports one socket,fixture-
    multibus, spi-sensors from its left plug and spi-motors from its
    right -- proving the two buses' CS namespaces stay independent
    through a CARRIER's pass-through composition, not just a board
    socket's own two named buses. This half owns acceptance criterion 3
    (accept + reject fixture pair; the collapse-to-one-parent mutation is
    probed by hand, see the module docstring in analyzer/sockets.py's own
    compose_socket -- reported in the implementor's handoff, not re-run
    automatically here).

test_mikrobus_span_adapter_build_round_trip and
test_mikrobus_span_adapter_cross_plug_cs_and_nexus (the @pytest.mark.build
tests) are the only tests in this module that launch a real toolchain.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from conftest import (FIXTURES_DIR, REPO_ROOT, SHIELD_DIR, WEST_EXE,
                      WEST_TOPDIR, assert_fixture_local, plain_build_for,
                      render_argv, run_expand, subprocess_timeout,
                      write_rerun_script, zephyr_base)

sys.path.insert(0, str(REPO_ROOT / "scripts"))

_QUAIL_BOARD = "mikroe_quail/stm32f427xx/rig"
_QUAIL_BOARD_DTS = (REPO_ROOT / "boards" / "extend" / "mikroe" / "quail"
                    / "mikroe_quail_stm32f427xx_rig.dts")

# ---------------------------------------------------------------- combined-SPI negative control

_CARRIER_CONNECTOR_BINDINGS = FIXTURES_DIR / "dts" / "multiplug-carrier-connectors"
# The EXPOSED type (fixture-multibus) lives in the multi-bus feature's own
# fixture tree, reused byte-untouched -- this slice composes with that
# vocabulary rather than duplicating it (multi-plug-carrier-brief.md
# Sec 1 ruling 1 is exactly "apply the multi-bus ownership ruling one
# level up").
_MULTIBUS_CONNECTOR_BINDINGS = FIXTURES_DIR / "dts" / "multibus-connectors"
_CONNECTOR_INCLUDE = FIXTURES_DIR / "include"
_CARRIER_SHIELDS = FIXTURES_DIR / "boards" / "rigs" / "multiplug-carrier-sockets" / "shields"
_MULTIBUS_SHIELDS = FIXTURES_DIR / "boards" / "rigs" / "multibus-sockets" / "shields"
_CARRIER_BOARD_DTS = FIXTURES_DIR / "boards" / "mainboards" / "multiplug_carrier_board.dts"
_ACCEPT_RIG = FIXTURES_DIR / "boards" / "rigs" / "multiplug-carrier-sockets" / "rig.yml"
_REJECT_RIG = (FIXTURES_DIR / "boards" / "rigs" / "multiplug-carrier-sockets-reject"
               / "rig.yml")


def _run_carrier_fixture(rig_yml: Path, out_dir: Path,
                         ) -> "subprocess.CompletedProcess[str]":
    assert_fixture_local([_CARRIER_BOARD_DTS, _CARRIER_CONNECTOR_BINDINGS,
                          _MULTIBUS_CONNECTOR_BINDINGS, _CONNECTOR_INCLUDE,
                          _CARRIER_SHIELDS, _MULTIBUS_SHIELDS])
    return run_expand(
        rig_yml, out_dir,
        board="multiplug_carrier_fixture_board",
        shield_dirs=[_CARRIER_SHIELDS, _MULTIBUS_SHIELDS],
        board_dts=_CARRIER_BOARD_DTS,
        bindings_dirs=[_CARRIER_CONNECTOR_BINDINGS, _MULTIBUS_CONNECTOR_BINDINGS],
        include_dirs=[_CONNECTOR_INCLUDE],
        connector_dirs=[_CARRIER_CONNECTOR_BINDINGS, _MULTIBUS_CONNECTOR_BINDINGS])


def test_combined_spi_accept_both_devices_land_at_cs_index_zero(tmp_path: Path) -> None:
    """Accept case: fixture_span_bridge (a PLURAL fixture carrier) plugs
    fx_left/fx_right and re-exports one socket,fixture-multibus; the
    EXISTING fixture_spi_sensor (bus: "spi-sensors") and fixture_spi_motor
    (bus: "spi-motors") both mate the COMPOSED socket and both build. The
    negative control test_multibus_socket.py's own accept case proves at
    the board-socket level, now proven through a carrier's pass-through
    composition: both devices may legally share the SAME cs-pool INDEX
    (0) without collision, since they sit on two INDEPENDENT physical
    sockets/buses (left_spi_ctrl vs right_spi_ctrl) -- collapsing the
    composition's own parents map back to one socket would make this
    assertion fail (probed by hand, see analyzer/sockets.py's compose_
    socket; reported in the implementor's handoff)."""
    out_dir = tmp_path / "out"
    result = _run_carrier_fixture(_ACCEPT_RIG, out_dir)

    assert result.returncode == 0, (
        f"multiplug_carrier_sockets: expected accept\n--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()
    assert "&fx_left_spi {" in overlay
    assert "&fx_right_spi {" in overlay
    sensors_block = overlay.split("&fx_left_spi {")[1].split("};")[0]
    motors_block = overlay.split("&fx_right_spi {")[1].split("};")[0]
    assert "sensor@0" in sensors_block
    assert "driver@0" in motors_block
    # both devices legally land at cs-gpios index 0 (the FIRST, and only,
    # entry in each of their two independent &<bus> blocks) despite
    # sharing the same fx_span_gpio CS-line controller underneath -- the
    # negative control.
    assert "cs-gpios = <&bridge_combined 10 1" in sensors_block
    assert "cs-gpios = <&bridge_combined 11 1" in motors_block


def test_combined_spi_reject_parent_lacking_spi_is_slot_qualified_phys_subset(
        tmp_path: Path) -> None:
    """Reject case (Sec 7): the right plug resolves to fx_right_no_spi,
    which never wires socket,spi at all -- the carrier is plural, so the
    phys-subset finding names the parent's own SLOT (Sec 4's rendering
    rule), never just its label alone."""
    out_dir = tmp_path / "out"
    result = _run_carrier_fixture(_REJECT_RIG, out_dir)

    assert result.returncode != 0, (
        "multiplug_carrier_sockets_reject: expected reject (phys-subset)")
    assert "phys-subset" in result.stderr
    assert "slot 'right'" in result.stderr
    assert "fx_right_no_spi" in result.stderr


# ---------------------------------------------------------------- the real corpus example


def _run_mikrobus_span_adapter(out_dir: Path,
                               tmp_path_factory: "pytest.TempPathFactory",
                               ) -> "subprocess.CompletedProcess[str]":
    plain_build = plain_build_for(_QUAIL_BOARD, tmp_path_factory)
    rig_dir = out_dir.parent / "rig"
    rig_dir.mkdir(exist_ok=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: eth_span_probe\n")
    (rig_dir / "eth_span_probe.yml").write_text(dedent("""\
        instances:
          - name: span
            shield: mikrobus_span_adapter
            sockets:
              left: quail_sock2
              right: quail_sock3
          - name: eth_mod
            shield: eth_click
            socket: span.combined
        """))
    return run_expand(
        rig_dir / "rig.yml", out_dir,
        board=_QUAIL_BOARD,
        board_dts=_QUAIL_BOARD_DTS,
        build_info=plain_build.build_info)


@pytest.mark.build
def test_mikrobus_span_adapter_cross_plug_cs_and_nexus(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """Marked build (test_layer_discipline.py's own static rule): reaches
    plain_build_for's cached real `west build --cmake-only` of quail
    (memoized per board for the whole session, shared with
    test_multiplug_shield.py's own can_span_click tests) -- needed for
    pass-1's real board-DT read, not a verification build of its own.

    Acceptance criterion 2, named in an assertion (not just a golden):
    eth's int-gpios renders through the RIGHT parent's own nexus
    (quail_sock3) while its SPI/CS chains through the LEFT (quail_sock2)
    -- the multi-parent cross-plug falsifier, one level up from
    can_span_click's own cross-plug DEVICE ref (there, one device reaches
    across for one pin; here, one composed SOCKET routes different
    positions/buses to different parents, and the click plugged on it
    carries no plug axis of its own at all)."""
    out_dir = tmp_path / "out"
    result = _run_mikrobus_span_adapter(out_dir, tmp_path_factory)

    assert result.returncode == 0, (
        f"mikrobus_span_adapter on quail: expected accept\n"
        f"--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()

    # The synthesized nexus (span_combined) carries BOTH rows, each
    # chaining to its OWN parent -- position 2 (CS) to quail_sock2
    # (LEFT), position 7 (INT) to quail_sock3 (RIGHT). THE cross-plug
    # falsifier: one composed socket, two rows, two different parents.
    assert "gpio-map = <2 0 &quail_sock2 2 0>,\n\t\t\t   <7 0 &quail_sock3 7 0>;" in overlay

    # eth on spi1 (LEFT/quail_sock2's own bus), CS index 0 -- both the
    # CS line and the INT line are rendered through the span_combined
    # nexus (Option C: a carrier-exported socket is never a real DT node
    # of its own), which is what actually carries the LEFT/RIGHT split.
    spi1_block = overlay.split("&spi1 {")[1].split("};")[0]
    assert "eth_mod_eth: eth@0 {" in spi1_block
    assert "cs-gpios = <&span_combined 2 1" in spi1_block
    assert "int-gpios = <&span_combined 7 0x1>;" in spi1_block

    sheet = (out_dir / "config-sheet.md").read_text()
    assert "| span | mikrobus_span_adapter | left: quail_sock2 |" in sheet
    assert "| span | mikrobus_span_adapter | right: quail_sock3 |" in sheet
    assert "eth_mod/eth: CS index 0" in sheet


# ---------------------------------------------------------------- build round-trip


@pytest.mark.build
def test_mikrobus_span_adapter_build_round_trip(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """The expand+build round trip for the real corpus example -- quail is
    a REAL, already-supported board (no fixture-board substitution
    needed), mirroring test_can_span_click_build_round_trip's own shape:
    the generated overlay is injected as EXTRA_DTC_OVERLAY_FILE on top of
    quail's OWN board.dts via a real `west build --cmake-only`, proving
    the devicetree text the expander emits for a multi-parent composed
    socket is genuine, toolchain-buildable devicetree. enc28j60's own
    Kconfig was already probed clean by can_span_click's neighbor
    (jedec,spi-nor/microchip,mcp2515); eth_click's own corpus build
    (frdm_eth_nest et al.) already proves it does not wall a --cmake-only
    configure either."""
    out_dir = tmp_path / "expand-out"
    expand_result = _run_mikrobus_span_adapter(out_dir, tmp_path_factory)
    assert expand_result.returncode == 0, (
        f"mikrobus_span_adapter on quail: expected accept\n"
        f"--- stderr ---\n{expand_result.stderr}")

    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    build_dir = tmp_path / "build"
    cmd = [
        WEST_EXE, "build", "-b", _QUAIL_BOARD,
        "zephyr/samples/hello_world", "--cmake-only", "-p", "always",
        "-d", str(build_dir), "--",
        f"-DEXTRA_DTC_OVERLAY_FILE={out_dir / 'rig-gen.overlay'}",
    ]
    write_rerun_script(build_dir, WEST_TOPDIR, cmd, env)
    result = subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                            capture_output=True, text=True,
                            timeout=subprocess_timeout(600))
    assert result.returncode == 0, (
        "mikrobus_span_adapter: expected quail's own board.dts + "
        "rig-gen.overlay to configure clean against a real toolchain\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    spi1_ctrl = zephyr_dts.split("spi1:")[1].split("\n\t};")[0]
    assert "eth_mod_eth: eth@0 {" in spi1_ctrl
    assert "cs-gpios = < &span_combined" in spi1_ctrl
    assert "int-gpios = < &span_combined" in spi1_ctrl
    # the synthesized nexus itself is a real node in the resolved tree,
    # and ITS OWN gpio-map is what actually carries the LEFT/RIGHT split
    # down to quail_sock2/quail_sock3 -- the falsifier at the fully
    # resolved level, not just the expander's own overlay text.
    span_combined_node = zephyr_dts.split("span_combined:")[1].split("\n\t};")[0]
    assert "&quail_sock2" in span_combined_node
    assert "&quail_sock3" in span_combined_node


def test_mikrobus_span_adapter_is_now_promotable_with_explicit_slot_options() -> None:
    """Ruling 4's plurality gate is RETIRED as of multi-plug-promotion-
    brief.md slice 3, for a carrier exactly as for an ordinary plural
    shield (the gate never distinguished the two) -- the mechanism this
    test used to pin (check_promotable's own plug_count refusal) is
    gone, and this test flips with it rather than merely dying, mirroring
    can_span_click's own flip in test_multiplug_shield.py
    (test_singleton_identity_law.py pins the census side, criterion 2 --
    EXCLUDED == set())."""
    from rigc.promote import (check_promotable, discover_shields,
                              parse_promotion_opts, resolve_for_promotion,
                              shield_is_multiplug)

    shields = discover_shields([str(SHIELD_DIR)])
    assert "mikrobus_span_adapter" in shields
    assert shields["mikrobus_span_adapter"].template is True

    resolved = resolve_for_promotion("mikrobus_span_adapter", [str(SHIELD_DIR)])
    assert resolved is not None
    assert shield_is_multiplug(resolved) is True

    assert check_promotable("mikrobus_span_adapter",
                            shields["mikrobus_span_adapter"], None) is None

    bare = parse_promotion_opts("socket=quail_sock2", "mikrobus_span_adapter",
                                resolved)
    assert isinstance(bare, str)
    assert "plugs 2 sockets" in bare

    optioned = parse_promotion_opts(
        "socket.left=quail_sock2:socket.right=quail_sock3",
        "mikrobus_span_adapter", resolved)
    assert not isinstance(optioned, str)
    assert optioned.sockets == {"left": "quail_sock2", "right": "quail_sock3"}
