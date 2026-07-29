"""Board projection over a SYNTHETIC, cpp-free board DT (rigc-r4-brief.md
Sec 6): board_edt.project_edt is called directly against an edtlib.EDT
built from `tests/fixtures/boards/fixture_board.dts` -- purpose-built
fixture data in rigc's own tree, never a copy of the frozen suite's own
`fixtures/boards/mainboards/socket.dts` (the blueprint's own
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
own test_controller_label.py), io-channel-map, an i2c bus phandle, and an
authored socket,cs-pool override.
"""
from __future__ import annotations

from pathlib import Path

from rigc import board_edt
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
    # subset exposure: a socket declaring no socket,spi/uart at all simply
    # has no entry for it -- never a placeholder.
    assert "spi" not in socket.buses
    assert "uart" not in socket.buses


def test_authored_cs_pool_is_read_verbatim() -> None:
    assert _socket().cs_pool == [2, 3]


def test_absent_cs_pool_stays_none() -> None:
    """A socket node that authors no socket,cs-pool at all keeps
    cs_pool=None -- never an invented empty list. The ctype-fallback
    merge (analyzer/cs.py's effective_cs_pool) exists specifically for
    this case."""
    assert _bare_socket().cs_pool is None


def test_bare_socket_has_no_bus_pwm_or_adc_entries() -> None:
    """Subset exposure and multi-function maps alike are declared by
    ABSENCE: a socket authoring none of socket,i2c/pwm-map/io-channel-map
    projects empty dicts, never placeholders."""
    socket = _bare_socket()
    assert socket.buses == {}
    assert socket.pwm_map == {}
    assert socket.adc_map == {}


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
