"""Multi-plug shields, slice 1 (multi-plug-shield-brief.md): a shield
mates more than one socket at once. Two halves, mirroring
test_multibus_socket.py's own shape:

  - the REAL corpus example, can_span_click on quail (two mikroBUS
    sockets, brief Sec 7): proves the mechanism against real board/shield
    content, through the real CLI. This half owns acceptance criteria 2
    (the cross-plug falsifier) and 3 (the negative control).
  - fixture-only per-slot mechanics (inference, subset, the same-
    physical-socket refusal, and the socket:/sockets: grammar) over a
    purpose-built connector-type/board pair, following multibus's own
    precedent: NO golden is frozen for these -- this feature adds no new
    corpus consumer for a golden to protect, and every assertion targets
    the specific fact under test.

test_can_span_click_build_round_trip (the one @pytest.mark.build test) is
the only test in this module that launches a real toolchain -- see its
own docstring for why quail (a REAL, already-supported board) needs no
fixture-board substitution the way multibus's own build test did.
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

_CONNECTOR_BINDINGS = FIXTURES_DIR / "dts" / "multiplug-connectors"
_CONNECTOR_INCLUDE = FIXTURES_DIR / "include"
_MP_SHIELDS = FIXTURES_DIR / "boards" / "rigs" / "multiplug-sockets" / "shields"
_BOARD_ONE_OF_EACH = FIXTURES_DIR / "boards" / "mainboards" / "multiplug_board_one_of_each.dts"
_BOARD_TWO_OF_A = FIXTURES_DIR / "boards" / "mainboards" / "multiplug_board_two_of_a.dts"
_BOARD_B_NO_I2C = FIXTURES_DIR / "boards" / "mainboards" / "multiplug_board_b_no_i2c.dts"
_INFERENCE_RIG = FIXTURES_DIR / "boards" / "rigs" / "multiplug-sockets" / "rig.yml"


def _run_fixture(rig_yml: Path, out_dir: Path, board: str, board_dts: Path,
                 ) -> "subprocess.CompletedProcess[str]":
    assert_fixture_local([board_dts, _CONNECTOR_BINDINGS, _CONNECTOR_INCLUDE,
                          _MP_SHIELDS])
    return run_expand(
        rig_yml, out_dir,
        board=board,
        shield_dirs=[_MP_SHIELDS],
        board_dts=board_dts,
        bindings_dirs=[_CONNECTOR_BINDINGS],
        include_dirs=[_CONNECTOR_INCLUDE],
        connector_dirs=[_CONNECTOR_BINDINGS])


def _write_rig(tmp_path: Path, name: str, content: str) -> Path:
    """One ad-hoc rig.yml + content pair under tmp_path -- for the
    reject scenarios below, which each need their OWN one-line
    difference and gain nothing from a committed fixture folder (the
    per-slot mechanics fixtures above ARE committed, since several
    functions share them)."""
    rig_dir = tmp_path / name
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(f"rig:\n  name: {name}\n")
    (rig_dir / f"{name}.yml").write_text(dedent(content))
    return rig_dir / "rig.yml"


# ---------------------------------------------------------------- per-slot inference (Sec 4)


def test_per_slot_inference_accepts_with_no_sockets_at_all(tmp_path: Path) -> None:
    """Both of fixture_multiplug_bridge's slots ("a" plugs fixture-mp-a,
    "b" plugs fixture-mp-b) resolve by per-slot inference -- the fixture
    board offers exactly one candidate of each type."""
    out_dir = tmp_path / "out"
    result = _run_fixture(_INFERENCE_RIG, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode == 0, (
        f"multiplug_sockets: expected accept\n--- stderr ---\n{result.stderr}")
    overlay = (out_dir / "rig-gen.overlay").read_text()
    assert "&multiplug_i2c_b {" in overlay
    assert "sensor_b@10" in overlay


def test_per_slot_inference_ambiguity_is_slot_qualified(tmp_path: Path) -> None:
    """Slot "a" has TWO fixture-mp-a candidates on this board -- refused
    per slot, never a tie-break; slot "b" (one candidate) is unaffected,
    so only ONE diagnostic names slot "a"."""
    out_dir = tmp_path / "out"
    result = _run_fixture(_INFERENCE_RIG, out_dir, "multiplug_fixture_board_2a",
                          _BOARD_TWO_OF_A)

    assert result.returncode != 0, "expected reject (phys-socket ambiguity)"
    assert "phys-socket" in result.stderr
    assert "slot 'a'" in result.stderr
    assert "fx_a1" in result.stderr and "fx_a2" in result.stderr
    assert "slot 'b'" not in result.stderr


# ---------------------------------------------------------------- per-slot subset (Sec 4)


def test_per_slot_subset_accept_pair(tmp_path: Path) -> None:
    """The ACCEPT half of the falsifier pair: slot "b"'s own device needs
    i2c, and the board's "b" socket offers it -- same rig as the
    inference-accept test above, asserted again here under its own name
    so the subset half of the contract is pinned independently of
    whatever the inference test happens to assert."""
    out_dir = tmp_path / "out"
    result = _run_fixture(_INFERENCE_RIG, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)
    assert result.returncode == 0, (
        f"expected accept\n--- stderr ---\n{result.stderr}")


def test_per_slot_subset_reject_names_the_right_slot_never_the_other(tmp_path: Path) -> None:
    """The REJECT half: slot "b"'s device needs i2c, but THIS board's "b"
    socket (fx_b_bare) offers none -- phys-subset names slot 'b' and
    'fx_b_bare'; slot "a" (which needs nothing) must not appear at all.
    Without a per-slot `needed` computation, a bus needed only by "b"
    could leak into "a"'s own check -- the mutation-sensitive property
    this pins."""
    out_dir = tmp_path / "out"
    result = _run_fixture(_INFERENCE_RIG, out_dir, "multiplug_fixture_board_no_i2c",
                          _BOARD_B_NO_I2C)

    assert result.returncode != 0, "expected reject (phys-subset)"
    assert "phys-subset" in result.stderr
    assert "slot 'b'" in result.stderr
    assert "fx_b_bare" in result.stderr
    assert "slot 'a'" not in result.stderr


# ---------------------------------------------------------------- distinct-socket refusal (Sec 4)


def test_two_slots_resolving_to_one_physical_socket_is_refused(tmp_path: Path) -> None:
    """fixture_multiplug_same_type's two slots (same connector type) both
    explicitly named to the SAME physical socket label -- one physical
    connector cannot take two plugs at once, a loud phys-socket error
    naming both slots, independent of the type's own stackability."""
    rig_yml = _write_rig(tmp_path, "mp_dup", """\
        instances:
          - name: dup_inst
            shield: fixture_multiplug_same_type
            sockets:
              x: fx_a
              y: fx_a
        """)
    out_dir = tmp_path / "out"
    result = _run_fixture(rig_yml, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode != 0, "expected reject (phys-socket, one socket two plugs)"
    assert "phys-socket" in result.stderr
    assert "'x'" in result.stderr and "'y'" in result.stderr
    assert "fx_a" in result.stderr


# ---------------------------------------------------------------- socket:/sockets: grammar (Sec 2)


def test_socket_on_a_plural_instance_is_rejected(tmp_path: Path) -> None:
    rig_yml = _write_rig(tmp_path, "mp_socket_on_plural", """\
        instances:
          - name: bridge_inst
            shield: fixture_multiplug_bridge
            socket: fx_a
        """)
    out_dir = tmp_path / "out"
    result = _run_fixture(rig_yml, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode != 0
    assert "lang-instance-socket" in result.stderr
    assert "plugs 2 sockets" in result.stderr
    assert "use sockets:" in result.stderr


def test_sockets_on_a_single_plug_instance_is_rejected(tmp_path: Path) -> None:
    rig_yml = _write_rig(tmp_path, "mp_sockets_on_single", """\
        instances:
          - name: single_inst
            shield: fixture_singleplug_a
            sockets:
              x: fx_a
        """)
    out_dir = tmp_path / "out"
    result = _run_fixture(rig_yml, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode != 0
    assert "lang-instance-socket" in result.stderr
    assert "single plug" in result.stderr
    assert "use socket:" in result.stderr


def test_both_socket_and_sockets_keys_is_rejected(tmp_path: Path) -> None:
    rig_yml = _write_rig(tmp_path, "mp_both_keys", """\
        instances:
          - name: bridge_inst
            shield: fixture_multiplug_bridge
            socket: fx_a
            sockets:
              a: fx_a
        """)
    out_dir = tmp_path / "out"
    result = _run_fixture(rig_yml, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode != 0
    assert "lang-instance-socket" in result.stderr
    assert "mutually exclusive" in result.stderr


def test_sockets_unknown_slot_is_rejected(tmp_path: Path) -> None:
    rig_yml = _write_rig(tmp_path, "mp_unknown_slot", """\
        instances:
          - name: bridge_inst
            shield: fixture_multiplug_bridge
            sockets:
              bogus: fx_a
        """)
    out_dir = tmp_path / "out"
    result = _run_fixture(rig_yml, out_dir, "multiplug_fixture_board",
                          _BOARD_ONE_OF_EACH)

    assert result.returncode != 0
    assert "lang-instance-socket" in result.stderr
    assert "unknown slot 'bogus'" in result.stderr
    assert "slots: a, b" in result.stderr


# ---------------------------------------------------------------- the real corpus example


def _run_can_span_click(out_dir: Path, tmp_path_factory: "pytest.TempPathFactory",
                        ) -> "subprocess.CompletedProcess[str]":
    plain_build = plain_build_for(_QUAIL_BOARD, tmp_path_factory)
    rig_dir = out_dir.parent / "rig"
    rig_dir.mkdir(exist_ok=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: can_span_probe\n")
    (rig_dir / "can_span_probe.yml").write_text(dedent("""\
        instances:
          - name: canspan
            shield: can_span_click
            sockets:
              left: quail_sock2
              right: quail_sock3
        """))
    return run_expand(
        rig_dir / "rig.yml", out_dir,
        board=_QUAIL_BOARD,
        board_dts=_QUAIL_BOARD_DTS,
        build_info=plain_build.build_info)


@pytest.mark.build
def test_can_span_click_cross_plug_cs_and_nexus(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """Marked build (test_layer_discipline.py's own static rule): this
    reaches `plain_build_for`, the cached-plain-build pattern's own real
    `west build --cmake-only` (memoized per board for the whole session,
    so this and the round-trip test below share ONE real configure of
    quail's plain board) -- needed for pass-1's real board-DT read
    (cpp include dirs + edtlib bindings), not a verification build of
    its own.

    Acceptance criteria 2 and 3, named in assertions (not just a
    golden): can0's CS allocated from the LEFT socket's own pool,
    log_flash's from the RIGHT's; can0's int-gpios rendered through the
    RIGHT socket's nexus -- the cross-plug falsifier. The negative
    control: both devices legally land at the SAME cs-pool index (0)
    because they sit on two INDEPENDENT physical sockets/buses (spi1 vs
    spi3) -- collapsing the per-slot resolution map back to one socket
    per instance would make this assertion fail (either a phys-cs
    exhaustion for whichever device loses the single-candidate mikroBUS
    CS pool, or both devices landing on the SAME socket label, which the
    assertion below explicitly rules out)."""
    out_dir = tmp_path / "out"
    result = _run_can_span_click(out_dir, tmp_path_factory)

    assert result.returncode == 0, (
        f"can_span_click on quail: expected accept\n--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()

    # can0 on spi1 (LEFT/quail_sock2's own bus), CS index 0 at quail_sock2.
    spi1_block = overlay.split("&spi1 {")[1].split("};")[0]
    assert "canspan_can0: can0@0 {" in spi1_block
    assert "cs-gpios = <&quail_sock2 2 1" in spi1_block
    # THE cross-plug falsifier: can0's INT line resolves through the
    # RIGHT socket's own nexus, not the LEFT socket its bus sits on.
    assert "int-gpios = <&quail_sock3 7 0x1>;" in spi1_block

    # log_flash on spi3 (RIGHT/quail_sock3's own bus), CS index 0 at
    # quail_sock3 -- the SAME index as can0's, on a DIFFERENT physical
    # socket/bus: the negative control.
    spi3_block = overlay.split("&spi3 {")[1].split("};")[0]
    assert "canspan_log_flash: log_flash@0 {" in spi3_block
    assert "cs-gpios = <&quail_sock3 2 1" in spi3_block

    sheet = (out_dir / "config-sheet.md").read_text()
    assert "| canspan | can_span_click | left: quail_sock2 |" in sheet
    assert "| canspan | can_span_click | right: quail_sock3 |" in sheet
    assert "canspan/can0: CS index 0" in sheet
    assert "canspan/log_flash: CS index 0" in sheet


def test_can_span_click_is_excluded_from_the_singleton_law_and_promotion() -> None:
    """Ruling 4 (Sec 6): a multi-plug shield cannot be promoted -- pinned
    here from the promotion seam's OWN angle (test_singleton_identity_law.py
    pins the census side, criterion 5)."""
    from rigc.promote import (check_promotable, discover_shields,
                              resolve_for_promotion, shield_is_multiplug)

    shields = discover_shields([str(SHIELD_DIR)])
    assert "can_span_click" in shields
    assert shields["can_span_click"].template is True   # discoverable, has the flag

    resolved = resolve_for_promotion("can_span_click", [str(SHIELD_DIR)])
    assert resolved is not None
    assert shield_is_multiplug(resolved) is True

    err = check_promotable("can_span_click", shields["can_span_click"], None,
                           plug_count=len(resolved.plugs))
    assert err is not None
    assert "can_span_click" in err
    assert "plugs 2 sockets" in err
    assert "cannot be promoted" in err


# ---------------------------------------------------------------- build round-trip


@pytest.mark.build
def test_can_span_click_build_round_trip(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """The expand+build round trip for the real corpus example. Unlike
    test_multibus_socket's own build test, quail is a REAL, already-
    supported board (no fixture-board substitution needed): the
    generated overlay is injected as EXTRA_DTC_OVERLAY_FILE on top of
    quail's OWN board.dts via a real `west build --cmake-only`, proving
    the devicetree text the expander emits is genuine, toolchain-
    buildable devicetree -- and, per brief Sec 7's own probe requirement,
    that neither microchip,mcp2515's nor jedec,spi-nor's Kconfig walls
    the configure the way TCA954x's driver walled a childless mux
    (probed manually before this test was written: CAN_MCP2515 lives
    inside an `if CAN` menu with no `default y` of its own reachable
    without CONFIG_CAN, so it simply stays unselected at --cmake-only
    time -- inert, never a hard failure, since this step never compiles
    the driver C file at all)."""
    out_dir = tmp_path / "expand-out"
    expand_result = _run_can_span_click(out_dir, tmp_path_factory)
    assert expand_result.returncode == 0, (
        f"can_span_click on quail: expected accept\n--- stderr ---\n{expand_result.stderr}")

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
        "can_span_click: expected quail's own board.dts + rig-gen.overlay "
        "to configure clean against a real toolchain\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    # Non-vacuous: the CAN device must actually land nested under spi1
    # (quail_sock2's own controller), with its cross-plug int-gpios
    # resolved through quail_sock3's real gpio-map to a real SoC pin --
    # not merely appear SOMEWHERE in the merged tree.
    spi1_ctrl = zephyr_dts.split("spi1:")[1].split("\n\t};")[0]
    assert "canspan_can0: can0@0 {" in spi1_ctrl
    assert "cs-gpios = < &quail_sock2" in spi1_ctrl
    assert "int-gpios = < &quail_sock3" in spi1_ctrl

    spi3_ctrl = zephyr_dts.split("spi3:")[1].split("\n\t};")[0]
    assert "canspan_log_flash: log_flash@0 {" in spi3_ctrl
    assert "cs-gpios = < &quail_sock3" in spi3_ctrl
