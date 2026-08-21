"""Multi-plug shields: a shield
mates more than one socket at once. Two halves, mirroring
test_multibus_socket.py's own shape:

  - the REAL corpus example, can_span_click on quail (two mikroBUS
    sockets): proves the mechanism against real board/shield
    content, through the real CLI -- the cross-plug falsifier and the
    negative control.
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

from conftest import (FIXTURES_DIR, REPO_ROOT, RIG_EXPAND_COMPILE,
                      SHIELD_DIR, WEST_EXE, WEST_TOPDIR, assert_fixture_local,
                      plain_build_for, render_argv, run_expand,
                      subprocess_timeout, write_rerun_script, zephyr_base)

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


# ---------------------------------------------------------------- per-slot inference


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


# ---------------------------------------------------------------- per-slot subset


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


# ---------------------------------------------------------------- distinct-socket refusal


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


# ---------------------------------------------------------------- socket:/sockets: grammar


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

    Named in assertions (not just a
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


def _run_can_span_click_shared_controller(
        out_dir: Path, tmp_path_factory: "pytest.TempPathFactory",
        ) -> "subprocess.CompletedProcess[str]":
    """Same shield, same helper shape as `_run_can_span_click`, but the two
    slots land on quail_sock1/quail_sock2 -- the shared-controller variant
    (both wire socket,spi = &spi1, mikrobus_sockets.dtsi:50,72), rather than
    quail_sock2/quail_sock3 (spi1 vs spi3)."""
    plain_build = plain_build_for(_QUAIL_BOARD, tmp_path_factory)
    rig_dir = out_dir.parent / "rig"
    rig_dir.mkdir(exist_ok=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: can_span_shared_probe\n")
    (rig_dir / "can_span_shared_probe.yml").write_text(dedent("""\
        instances:
          - name: canspan
            shield: can_span_click
            sockets:
              left: quail_sock1
              right: quail_sock2
        """))
    return run_expand(
        rig_dir / "rig.yml", out_dir,
        board=_QUAIL_BOARD,
        board_dts=_QUAIL_BOARD_DTS,
        build_info=plain_build.build_info)


@pytest.mark.build
def test_can_span_click_shared_controller_two_slot_contract(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """Marked build for the same reason as test_can_span_click_cross_plug_
    cs_and_nexus above: reaches plain_build_for (memoized per board, so this
    shares quail's ONE cached plain configure with every other test in this
    module).

    Does a multi-plug shield whose two
    slots land on two sockets wired to the SAME controller resolve
    correctly? It does by construction -- allocation scope identity is
    bus.path, and quail_sock1/quail_sock2 share bus.path (&spi1) while
    remaining two DISTINCT physical connectors -- but nothing pinned it
    before this test. Unlike the sock2/sock3 case above (two independent
    buses, so both devices legally land at cs-pool index 0), the SAME
    bus.path here means can0 and log_flash share ONE cs allocation scope:
    both devices render inside ONE &spi1 overlay node, with two DISTINCT
    cs-gpios entries (one through each slot's own socket) and two DIFFERENT
    reg/cs indexes -- collapsing the per-slot resolution back to one socket
    per instance would either exhaust quail_sock1's single-candidate CS
    pool or merge the two devices onto the SAME cs-gpios entry, either of
    which this test would catch."""
    out_dir = tmp_path / "out"
    result = _run_can_span_click_shared_controller(out_dir, tmp_path_factory)

    assert result.returncode == 0, (
        f"can_span_click (shared controller) on quail: expected accept\n"
        f"--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()

    # Both devices land inside ONE &spi1 node -- not two nodes, not spi3
    # (quail_sock1/quail_sock2 both wire socket,spi = &spi1; quail's other
    # two sockets, spi3, never enter this rig at all).
    assert overlay.count("&spi1 {") == 1
    assert "&spi3 {" not in overlay
    # Split on the ZERO-indent closing brace (the &spi1 node's own), not
    # the first "};" at all -- that would be can0's own inner closing
    # brace, truncating the block before log_flash (this node has TWO
    # device children, unlike every other bus block this suite's own
    # split idiom has had to isolate so far).
    spi1_block = overlay.split("&spi1 {")[1].split("\n};")[0]

    # ONE combined cs-gpios property, two DISTINCT physical nets: one
    # entry through quail_sock1's own nexus (LEFT/can0's own socket), one
    # through quail_sock2's (RIGHT/log_flash's own socket) -- sharing the
    # SAME controller does not collapse them into one net.
    assert ("cs-gpios = <&quail_sock1 2 1 /* ACTIVE_LOW */>, "
           "<&quail_sock2 2 1 /* ACTIVE_LOW */>;") in spi1_block

    # can0 (LEFT) and log_flash (RIGHT) each claim their OWN cs-gpios
    # entry -- reg/cs index 0 and 1 respectively, not the same index
    # twice: the shared bus.path scopes their CS allocation TOGETHER.
    assert "canspan_can0: can0@0 {" in spi1_block
    assert "canspan_log_flash: log_flash@1 {" in spi1_block

    # can0's int-gpios still resolves through quail_sock2 -- the RIGHT
    # slot -- exactly as it does in the sock2/sock3 case above; sharing a
    # controller with the LEFT slot changes nothing about the cross-plug
    # GPIO resolution, only the CS/bus scope.
    assert "int-gpios = <&quail_sock2 7 0x1>;" in spi1_block

    sheet = (out_dir / "config-sheet.md").read_text()
    assert "| canspan | can_span_click | left: quail_sock1 |" in sheet
    assert "| canspan | can_span_click | right: quail_sock2 |" in sheet
    assert "canspan/can0: CS index 0" in sheet
    assert "canspan/log_flash: CS index 1" in sheet


def test_can_span_click_is_now_promotable_with_explicit_slot_options() -> None:
    """A multi-plug shield is promotable: check_promotable's own
    plug_count refusal is gone, so this pins the POSITIVE fact, from the
    promotion seam's own angle (test_singleton_identity_law.py pins the
    census side: EXCLUDED == set()). can_span_click still needs
    explicit slot options to promote onto quail at all (four mikroBUS
    candidates per slot kills per-slot inference by construction,
    exactly as it does for the persisted rig's own sockets: map) -- a
    bare socket= is refused for a DIFFERENT reason (the plural-shield
    grammar refusal, parse_promotion_opts's own sentence), pinned here
    too so the two refusal reasons are never confused for one another."""
    from rigc.promote import (check_promotable, discover_shields,
                              parse_promotion_opts, resolve_for_promotion,
                              shield_is_multiplug)

    shields = discover_shields([str(SHIELD_DIR)])
    assert "can_span_click" in shields
    assert shields["can_span_click"].template is True   # discoverable, has the flag

    resolved = resolve_for_promotion("can_span_click", [str(SHIELD_DIR)])
    assert resolved is not None
    assert shield_is_multiplug(resolved) is True

    # The plug-count gate is gone: check_promotable no longer refuses a
    # multi-plug shield at all.
    assert check_promotable("can_span_click", shields["can_span_click"],
                            None) is None

    # A bare socket= is still refused -- not by check_promotable any
    # more, but by parse_promotion_opts's own plural-shield sentence.
    bare = parse_promotion_opts("socket=quail_sock2", "can_span_click",
                                resolved)
    assert isinstance(bare, str)
    assert "plugs 2 sockets" in bare
    assert "socket.<slot>=" in bare

    # The slot-optioned form parses clean.
    optioned = parse_promotion_opts(
        "socket.left=quail_sock2:socket.right=quail_sock3",
        "can_span_click", resolved)
    assert not isinstance(optioned, str)
    assert optioned.sockets == {"left": "quail_sock2", "right": "quail_sock3"}


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
    buildable devicetree -- and confirms
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


# --------------------------------------------------- the promoted round trip


def _run_can_span_click_promoted(
        out_dir: Path, tmp_path_factory: "pytest.TempPathFactory",
        ) -> "subprocess.CompletedProcess[str]":
    """The --promote counterpart of _run_can_span_click: the SAME two
    board sockets (quail_sock2/quail_sock3), named via the slot-optioned
    promotion grammar instead of a
    persisted sockets: map -- run through the real CLI exactly as
    cmake's --promote seam (rigs.py's PromotedTarget.promotion_target)
    would invoke it. run_expand has no --promote mode (it always takes a
    rig_yml PATH), so this builds the argv directly rather than
    stretching that helper to cover a shape it was never meant to."""
    plain_build = plain_build_for(_QUAIL_BOARD, tmp_path_factory)
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")
    cmd = [sys.executable, "-m", RIG_EXPAND_COMPILE, "expand",
          "--promote",
          "can_span_click:socket.left=quail_sock2:socket.right=quail_sock3",
          "--shield-dir", str(SHIELD_DIR),
          "--board", _QUAIL_BOARD,
          "--board-dts", str(_QUAIL_BOARD_DTS),
          "--build-info", str(plain_build.build_info),
          "--out-dir", str(out_dir)]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True,
                          timeout=subprocess_timeout(120))


@pytest.mark.build
def test_can_span_click_promoted_round_trip_matches_the_persisted_cross_plug_facts(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """The
    promoted form of can_span_click, given the ONLY spelling its own
    four-candidate-per-slot ambiguity leaves it (explicit
    socket.left=/socket.right= options), produces the SAME cross-plug/CS
    facts test_can_span_click_cross_plug_cs_and_nexus already pins for
    the persisted quail_can_span rig -- can0's CS from the LEFT socket's
    own pool, log_flash's from the RIGHT's, can0's int-gpios through the
    RIGHT socket's nexus (the cross-plug falsifier, named here again
    rather than trusted from the golden alone). The promoted instance is
    named after the shield itself (promote_shield's own contract), never
    "canspan" -- every label below substitutes that one name; the
    structural facts (which socket, which pool index, which nexus) do
    not move."""
    out_dir = tmp_path / "out"
    result = _run_can_span_click_promoted(out_dir, tmp_path_factory)

    assert result.returncode == 0, (
        f"promoted can_span_click on quail: expected accept\n"
        f"--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()

    # can0 on spi1 (LEFT/quail_sock2's own bus), CS index 0 at quail_sock2.
    spi1_block = overlay.split("&spi1 {")[1].split("};")[0]
    assert "can_span_click_can0: can0@0 {" in spi1_block
    assert "cs-gpios = <&quail_sock2 2 1" in spi1_block
    # THE cross-plug falsifier: can0's INT line resolves through the
    # RIGHT socket's own nexus, not the LEFT socket its bus sits on.
    assert "int-gpios = <&quail_sock3 7 0x1>;" in spi1_block

    # log_flash on spi3 (RIGHT/quail_sock3's own bus), CS index 0 at
    # quail_sock3 -- the SAME index as can0's, on a DIFFERENT physical
    # socket/bus: the negative control survives promotion too.
    spi3_block = overlay.split("&spi3 {")[1].split("};")[0]
    assert "can_span_click_log_flash: log_flash@0 {" in spi3_block
    assert "cs-gpios = <&quail_sock3 2 1" in spi3_block

    sheet = (out_dir / "config-sheet.md").read_text()
    assert "| can_span_click | can_span_click | left: quail_sock2 |" in sheet
    assert "| can_span_click | can_span_click | right: quail_sock3 |" in sheet
    assert "can_span_click/can0: CS index 0" in sheet
    assert "can_span_click/log_flash: CS index 0" in sheet


def test_can_span_click_promotion_refuses_a_bare_socket_naming_the_slots(
        tmp_path: Path) -> None:
    """The negative control for the test above: a bare socket= (the
    single-plug spelling) is refused for THIS shield with its own
    sentence, naming both real slots -- proving the promoted round trip
    above passed BECAUSE of the slot-optioned grammar, not despite it.
    Driven through the real CLI (not parse_promotion_opts in-process)
    since the refusal must fire at cli.py's own --promote seam too."""
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zephyr_base()
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")
    result = subprocess.run(
        [sys.executable, "-m", RIG_EXPAND_COMPILE, "expand",
         "--promote", "can_span_click:socket=quail_sock2",
         "--shield-dir", str(SHIELD_DIR),
         "--board", _QUAIL_BOARD, "--board-dts", str(_QUAIL_BOARD_DTS),
         "--out-dir", str(tmp_path / "out")],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        timeout=subprocess_timeout(60))
    assert result.returncode != 0
    assert "plugs 2 sockets" in result.stderr
    assert "socket.<slot>=" in result.stderr
    assert "left" in result.stderr and "right" in result.stderr
