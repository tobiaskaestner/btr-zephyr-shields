"""Board projection over a SYNTHETIC, cpp-free board DT (rigc-r4-brief.md
Sec 6): board_edt.project_edt is called directly against an edtlib.EDT
built from `tests/fixtures/boards/fixture_board.dts` -- purpose-built
fixture data in rigc's own tree, never a copy of the frozen suite's own
`fixtures/boards/fixture_board.dts` (the blueprint's own
test_controller_label.py/test_edt_build.py are the PRECEDENT for the
approach, not the data). No cpp at all: the fixture .dts has no
`#include`/macros, so `edtlib.EDT()` is built straight off it here --
`board_edt.load_board`/`edt_build.build_edt` (which DO invoke cpp) are
integration-only by construction (rigc-r3-brief.md Sec 2's cpp/unit-test
seam applies to the board side exactly as it does to the shield side),
so this module never calls them.

Everything that must resolve out of ONE socket,fixture-nexus node is
covered by construction: gpio-map (two positions), pwm-map (whose
controller carries a SECOND, later-attached label -- the controller-label
determinism invariant, ported as a pair of tests from the blueprint's
own test_controller_label.py), io-channel-map, an i2c bus phandle, an spi
bus phandle, and an authored cs-pool (per-bus, on BusRef -- the i2c bus
of the same socket carries none, pinning that a cs-pool value attaches
to the ONE bus that authors it, never every bus of the socket).

A named, multi-bus connector type (socket,spi-sensors/socket,spi-motors,
board_edt.py's own widened pattern match) is a SEPARATE, hermetic
edtlib.EDT this file builds inline rather than through fixture_board.dts
-- it needs its own binding (the shared socket-fixture-nexus.yaml schema
declares no such properties), and keeping it out of the shared fixture
avoids widening that schema/DTS for every other test in this file.

fixture_socket_bare additionally carries a SECOND label of its own
(fixture_bare_alias) -- the alias-index fixture for
board-as-invocation-coordinate-brief.md Sec 2.1: project_edt must index
every label a socket node declares for RESOLUTION (Board.resolve), while
Board.sockets itself stays keyed by the defining label alone, one entry
per physical socket.

The module-level census below (test_every_board_rig_extension_socket_...)
is a SEPARATE concern from the rest of this file: it scans the REAL
boards/extend/ tree's .dtsi text (regex, not edtlib -- several of those
fragments, e.g. lotus's `adc0: &adc {};`, reference a node their own file
never defines, so they are not standalone-parseable outside a real board
build) for the per-connector-type conventional label
board-as-invocation-coordinate-brief.md Sec 2 rules. It is a census-style
test: falsified by mutating the WORLD it observes (dropping a label from
a real board file), never by editing its own assertion.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import textwrap

from rigc import board_edt
from rigc.board_census import scan_socket_nodes
from rigc.dtsio import MODULE_ROOT
from rigc.edt_build import ensure_devicetree_on_path
from rigc.tests.conftest import FIXTURES_DIR, assert_fixture_local

_BOARD_DTS = FIXTURES_DIR / "boards" / "fixture_board.dts"
_BINDINGS_DIR = FIXTURES_DIR / "dts" / "bindings"


def _edt():
    """Build the fixture's edtlib.EDT directly -- no cpp, no BuildRecipe,
    no workdir: the fixture .dts is already valid, preprocessed-shape DTS
    text."""
    assert_fixture_local([_BOARD_DTS, _BINDINGS_DIR])
    ensure_devicetree_on_path()
    from devicetree import edtlib
    return edtlib.EDT(str(_BOARD_DTS), [str(_BINDINGS_DIR)],
                      default_prop_types=True)


def _socket():
    board = board_edt.project_edt(_edt(), "fixture-board")
    return board.sockets["fixture_socket"]


def _bare_socket():
    board = board_edt.project_edt(_edt(), "fixture-board")
    return board.sockets["fixture_socket_bare"]


# ---------------------------------------------------------------- project_edt


def test_project_edt_finds_every_socket_by_label() -> None:
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.name == "fixture-board"
    assert set(board.sockets) == {"fixture_socket", "fixture_socket_bare"}


def test_project_edt_ignores_non_socket_compatibles() -> None:
    """Only compatible = "socket,*" nodes project -- the gpio/pwm/adc/i2c
    controller nodes in the fixture must never appear as sockets of their
    own (only the two socket,fixture-nexus nodes do)."""
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert len(board.sockets) == 2


# ------------------------------------------------------- alias-aware lookup
#
# fixture_socket_bare's second label (fixture_bare_alias) is the fixture
# for board-as-invocation-coordinate-brief.md Sec 2.1: a socket node may
# declare more than one label, and every one of them must resolve --
# without the defining-label dict growing a second entry per socket.


def test_project_edt_indexes_every_additional_label_as_an_alias() -> None:
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.aliases == {"fixture_bare_alias": "fixture_socket_bare"}


def test_resolve_finds_a_socket_by_its_defining_label() -> None:
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.resolve("fixture_socket_bare") is board.sockets["fixture_socket_bare"]


def test_resolve_finds_the_same_socket_by_its_alias() -> None:
    """The additive-conformance claim itself: BOTH labels of one node
    resolve to the identical BoardSocket."""
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.resolve("fixture_bare_alias") is board.resolve("fixture_socket_bare")


def test_resolve_of_an_unknown_ref_is_none() -> None:
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.resolve("no_such_socket") is None


def test_an_alias_does_not_double_key_the_sockets_census() -> None:
    """The critical constraint: board.sockets stays ONE entry per
    physical socket. analyzer/sockets.py's phys-socket diagnostic
    iterates board.sockets.values() to render "sockets of <board>: ..."
    (wording frozen by the unmapped-socket golden) -- a second key per
    socket would list it twice and churn that census."""
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert len(board.sockets) == 2
    assert "fixture_bare_alias" not in board.sockets


def test_a_bare_dict_get_does_not_find_the_alias() -> None:
    """Negative control: this is what board.sockets.get(ref) alone
    (today's pre-alias lookup, board-as-invocation-coordinate-brief.md
    Sec 2.1) does with an alias -- nothing, since the second label is
    inert without going through resolve(). Proves resolve() is doing
    real work, not just tolerating an already-working lookup."""
    board = board_edt.project_edt(_edt(), "fixture-board")
    assert board.sockets.get("fixture_bare_alias") is None


def test_gpio_map_resolves_position_to_controller_pin_flags() -> None:
    socket = _socket()
    assert socket.type_name == "fixture-nexus"
    assert socket.gpio_map[0] == ("gpio_ctrl0", 5, 0)
    assert socket.gpio_map[1] == ("gpio_ctrl0", 6, 1)


def test_bus_ref_projects_label_and_path() -> None:
    socket = _socket()
    assert "i2c" in socket.buses
    assert socket.buses["i2c"].label == "i2c0"
    assert socket.buses["i2c"].path == "/i2c_ctrl@30"
    assert socket.buses["spi"].label == "spi_ctrl0"
    assert socket.buses["spi"].path == "/spi_ctrl@40"
    # subset exposure: a socket declaring no socket,uart at all simply
    # has no entry for it -- never a placeholder.
    assert "uart" not in socket.buses


def test_authored_cs_pool_is_read_verbatim_onto_its_own_bus() -> None:
    """cs_pool lives on BusRef now, not on BoardSocket -- authored
    verbatim onto the ONE bus (spi) that carries a cs-pool property."""
    assert _socket().buses["spi"].cs_pool == [2, 3]


def test_a_bus_without_its_own_cs_pool_stays_none() -> None:
    """The SAME socket's i2c bus authors no cs-pool of its own -- stays
    None, never inheriting the sibling spi bus's value or an invented
    empty list. The ctype-fallback merge (analyzer/cs.py's
    effective_cs_pool) exists specifically for this case."""
    assert _socket().buses["i2c"].cs_pool is None


def test_bare_socket_has_no_bus_pwm_or_adc_entries() -> None:
    """Subset exposure and multi-function maps alike are declared by
    ABSENCE: a socket authoring none of socket,i2c/pwm-map/io-channel-map
    projects empty dicts, never placeholders."""
    socket = _bare_socket()
    assert socket.buses == {}
    assert socket.pwm_map == {}
    assert socket.adc_map == {}


# ------------------------------------------------- multi-bus socket widening
#
# A connector type naming more than one bus of a kind suffixes it with a
# role ("spi-sensors"/"spi-motors") -- board_edt.py's pattern match against
# EVERY socket,* property name, not the fixed 3-entry table the rest of
# this file's fixture predates. A dedicated, hermetic edtlib.EDT (its own
# binding, its own DTS text) rather than fixture_board.dts/socket-fixture-
# nexus.yaml: no other test in this file needs these properties, and
# widening the shared fixture just for this would be pure churn on it.


def _multibus_edt(tmp_path: Path):
    binding_dir = tmp_path / "bindings"
    binding_dir.mkdir()
    (binding_dir / "socket-fixture-multibus.yaml").write_text(textwrap.dedent("""\
        description: purpose-built fixture binding for the multi-bus widening tests
        compatible: "socket,fixture-multibus"
        properties:
          "#gpio-cells":
            type: int
            required: true
          gpio-map:
            type: compound
            required: true
          gpio-map-mask:
            type: array
          gpio-map-pass-thru:
            type: array
          socket,spi-sensors:
            type: phandle
          socket,spi-motors:
            type: phandle
          socket,spi-sensors-cs-pool:
            type: array
          socket,spi-motors-cs-pool:
            type: array
        """))
    dts_path = tmp_path / "multibus.dts"
    dts_path.write_text(textwrap.dedent("""\
        /dts-v1/;
        / {
            #address-cells = <1>;
            #size-cells = <1>;

            spi_a: spi_ctrl@0 {
                compatible = "fixturetest,spi-ctrl";
                reg = <0x0 0x4>;
            };
            spi_b: spi_ctrl@10 {
                compatible = "fixturetest,spi-ctrl";
                reg = <0x10 0x4>;
            };
            gpio0: gpio_ctrl@20 {
                compatible = "fixturetest,gpio-ctrl";
                reg = <0x20 0x4>;
                gpio-controller;
                #gpio-cells = <2>;
            };

            multibus_socket: connector_multibus {
                compatible = "socket,fixture-multibus";
                #gpio-cells = <2>;
                gpio-map-mask = <0xffffffff 0xffffffff>;
                gpio-map-pass-thru = <0 0>;
                gpio-map = <10 0 &gpio0 0 0>,
                          <11 0 &gpio0 1 0>;
                socket,spi-sensors = <&spi_a>;
                socket,spi-motors = <&spi_b>;
                socket,spi-sensors-cs-pool = <10>;
                socket,spi-motors-cs-pool = <11>;
            };
        };
        """))
    ensure_devicetree_on_path()
    from devicetree import edtlib
    return edtlib.EDT(str(dts_path), [str(binding_dir)], default_prop_types=True)


def test_project_edt_widens_named_bus_properties_to_qualified_keys(
        tmp_path: Path) -> None:
    board = board_edt.project_edt(_multibus_edt(tmp_path), "multibus-board")
    socket = board.sockets["multibus_socket"]
    assert set(socket.buses) == {"spi-sensors", "spi-motors"}
    assert socket.buses["spi-sensors"].label == "spi_a"
    assert socket.buses["spi-motors"].label == "spi_b"


def test_project_edt_widens_cs_pool_per_named_bus(tmp_path: Path) -> None:
    board = board_edt.project_edt(_multibus_edt(tmp_path), "multibus-board")
    socket = board.sockets["multibus_socket"]
    assert socket.buses["spi-sensors"].cs_pool == [10]
    assert socket.buses["spi-motors"].cs_pool == [11]


def test_pwm_map_resolves_position_to_controller_and_channel() -> None:
    assert _socket().pwm_map[0] == ("defining_ctrl", 0)


def test_adc_map_resolves_position_to_controller_and_channel() -> None:
    assert _socket().adc_map[2] == ("adc_ctrl0", 1)


# ------------------------------------------------- controller-label determinism
#
# Ported as a pair from the blueprint's own test_controller_label.py: the
# *-map target's identity must be node.labels[0] -- the DEFINING label --
# stable no matter what else composes onto the same node afterward.


def test_controller_label_is_the_defining_label() -> None:
    label, _channel = _socket().pwm_map[0]
    assert label == "defining_ctrl"


def test_controller_label_ignores_a_later_attached_alias() -> None:
    label, _channel = _socket().pwm_map[0]
    assert label != "legacy_alias"


def test_gpio_map_controller_label_is_the_defining_label() -> None:
    """The gpio side of the same invariant. board_edt resolves the
    controller label INLINE for gpio-map and through _controller_label for
    pwm/adc -- two separate implementations, so pinning only the pwm side
    leaves a label regression on the gpio path undetectable. Position 2
    targets the dual-labelled node for exactly this."""
    ctrl_label, _pin, _flags = _socket().gpio_map[2]
    assert ctrl_label == "defining_ctrl"
    assert ctrl_label != "legacy_alias"


# ------------------------------------------- conventional-label census (Sec 2)
#
# board-as-invocation-coordinate-brief.md Sec 2/2.1's lint: every socket,*
# node a board rig-extension declares must carry its connector type's
# conventional label -- "<type>" for a singleton, "<type>_<silkscreen>"
# for a family -- ALONGSIDE whatever board-prefixed label it already had.
# That is the fact Board.resolve() depends on: an alias only resolves if
# board_edt actually saw it declared in the board's own devicetree.
#
# The node scan itself is board_census.scan_socket_nodes -- production
# code (board-coordinate-s2-brief.md Sec 5.3), shared rather than
# restated here. It reports type_name DASHED, exactly as compatible =
# "socket,<type>" spells it (the census's own mating-facing value); the
# label convention below compares against a LABEL, which uses
# underscores, so the underscoring happens HERE, once, for this one
# comparison only -- never inside the shared scanner.


def _conventional_label_offenders(text: str) -> List[str]:
    """The defining label of every socket,* node in text whose label set
    carries NO label matching its type's convention -- "<type>" or
    "<type>_<anything>". Empty when every node conforms."""
    offenders = []
    for node in scan_socket_nodes("<test>", text):
        type_name = node.type_name.replace("-", "_")
        if not any(label == type_name or label.startswith(type_name + "_")
                  for label in node.labels):
            offenders.append(node.labels[0] if node.labels else "<unlabeled>")
    return offenders


def test_conventional_label_offenders_detects_a_missing_alias() -> None:
    """Mechanism check for the checker itself, on synthetic text -- BEFORE
    trusting it to census the real tree. A node with no conventional
    label is flagged; the identical node WITH one is not."""
    missing = textwrap.dedent("""\
        / {
            board_ard: connector_arduino_r3 {
                compatible = "socket,arduino-r3";
            };
        };
        """)
    assert _conventional_label_offenders(missing) == ["board_ard"]

    present = textwrap.dedent("""\
        / {
            board_ard: arduino_r3: connector_arduino_r3 {
                compatible = "socket,arduino-r3";
            };
        };
        """)
    assert _conventional_label_offenders(present) == []


def test_every_board_rig_extension_socket_carries_its_type_convention_label() -> None:
    """The census over the REAL tree. Falsified by mutating the WORLD it
    observes -- drop a label from a real boards/extend/*.dtsi and this
    fails -- never by editing this assertion."""
    root = Path(MODULE_ROOT) / "boards" / "extend"
    offenders = []
    for path in sorted(root.rglob("*.dtsi")):
        for offender in _conventional_label_offenders(path.read_text()):
            offenders.append(f"{path.relative_to(MODULE_ROOT)}: {offender}")
    assert not offenders, (
        "socket,* node(s) with no label matching their connector type's "
        "convention (board-as-invocation-coordinate-brief.md Sec 2 -- "
        f"'<type>' singleton or '<type>_<silkscreen>' family): {offenders}")
