"""Mating and socket resolution, with carrier/mux composition
(rigc-r4-brief.md Sec 3). `mating_ok`/`subset_gaps` are the plug-vs-socket
and needed-vs-offered decisions as pure value functions over plain
strings/sets. `compose_socket` is exercised directly against synthetic
ExposedSocket/BoardSocket values -- no Instance/Rig/Shield needed to call
it. `resolve_sockets` (the pass, including the stack-guard against cyclic
carrier references) gets minimal constructed Rig/Instance/Shield values,
since resolving a CHAIN of instances is inherently the pass's own
subject."""
from __future__ import annotations

from rigc.analyzer.sockets import compose_socket, mating_ok, resolve_sockets, subset_gaps
from rigc.model import (Board, BoardSocket, BusRef, ConnectorType,
                        ExposedSocket, Instance, Rig, Shield)

# ---------------------------------------------------------------- mating_ok / subset_gaps


def test_mating_ok_when_plug_and_socket_types_match() -> None:
    assert mating_ok("arduino-r3", "arduino-r3") is True


def test_mating_ok_false_on_a_type_mismatch() -> None:
    assert mating_ok("arduino-r3", "mikrobus") is False


def test_subset_gaps_empty_when_socket_offers_everything_needed() -> None:
    assert subset_gaps({"i2c"}, offered=["i2c", "spi"]) == []


def test_subset_gaps_names_every_bus_the_socket_does_not_offer() -> None:
    """Subset exposure is declared by ABSENCE: a socket offering no
    socket,uart rejects a uart-needing plug."""
    assert subset_gaps({"i2c", "uart"}, offered=["i2c"]) == ["uart"]


def test_subset_gaps_is_sorted_for_deterministic_rendering() -> None:
    assert subset_gaps({"uart", "spi"}, offered=[]) == ["spi", "uart"]


# ---------------------------------------------------------------- compose_socket


def _parent(gpio_map=None, buses=None, path="/board_ard", label="board_ard") -> BoardSocket:
    return BoardSocket(label=label, path=path, type_name="arduino-r3",
                      gpio_map=gpio_map or {}, buses=buses or {}, cs_pool=None)


def test_compose_socket_passes_through_a_routed_position() -> None:
    parent = _parent(gpio_map={7: ("gpiod", 0, 0)})
    exposed = ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                            gpio_map={2: (7, 0)}, buses={})

    socket, diags, scopes = compose_socket("adapter_1.mb1", "adapter_1",
                                          exposed, parent, None)

    assert diags == []
    assert scopes == []
    assert socket.gpio_map[2] == ("gpiod", 0, 0)
    assert socket.label == "adapter_1.mb1"
    assert socket.parent is parent


def test_compose_socket_position_the_parent_fragment_never_routes_stays_local() -> None:
    """A position the exposed socket declares but the parent's own
    gpio-map does not route stays absent from the composed gpio_map,
    which keeps it socket-local (analyzer/gpio.py's soc_net) rather than
    inventing a routing."""
    parent = _parent(gpio_map={})
    exposed = ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                            gpio_map={2: (7, 0)}, buses={})

    socket, _diags, _scopes = compose_socket(
        "adapter_1.mb1", "adapter_1", exposed, parent, None)

    assert 2 not in socket.gpio_map


def test_compose_socket_bus_pass_through() -> None:
    parent = _parent(buses={"spi": BusRef(label="spi0", path="/spi0")})
    exposed = ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                            gpio_map={}, buses={"spi": "plug"})

    socket, diags, _scopes = compose_socket(
        "adapter_1.mb1", "adapter_1", exposed, parent, None)

    assert diags == []
    assert socket.buses["spi"].label == "spi0"


def test_compose_socket_pass_through_without_parent_bus_is_phys_subset() -> None:
    """R19 pass-through needs the parent to actually provide the bus it
    passes through -- a carrier claiming to pass through SPI when its own
    parent socket offers none is rejected."""
    parent = _parent(buses={})
    exposed = ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                            gpio_map={}, buses={"spi": "plug"})

    _socket, diags, _scopes = compose_socket(
        "adapter_1.mb1", "adapter_1", exposed, parent, None)

    assert len(diags) == 1
    assert diags[0].code == "phys-subset"


def test_compose_socket_scope_creation_registers_a_scope_entry() -> None:
    """S8: a bus routed to a DEVICE of the shield (not the plug) creates a
    NEW scope, keyed by the composing instance's own socket reference."""
    parent = _parent(buses={"i2c": BusRef(label="i2c1", path="/i2c1")})
    exposed = ExposedSocket(name="ch0", label="ch0", type_name="i2c-mux-ch",
                            gpio_map={}, buses={"i2c": ("scope", "mux_dev")},
                            channel=0)

    socket, diags, scopes = compose_socket(
        "mux_1.ch0", "mux_1", exposed, parent, None)

    assert diags == []
    assert scopes == [("mux_1.ch0", ("mux_1_mux_dev", 0))]
    assert socket.buses["i2c"].path == "mux_1.ch0"


def test_compose_socket_cs_pool_override_travels_with_the_composed_socket() -> None:
    parent = _parent()
    exposed = ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                            gpio_map={}, buses={}, cs_pool=[3, 4])

    socket, _diags, _scopes = compose_socket(
        "adapter_1.mb1", "adapter_1", exposed, parent, None)

    assert socket.cs_pool == [3, 4]


# ---------------------------------------------------------------- resolve_sockets


def _shield(plugs="arduino-r3", exposes=None) -> Shield:
    return Shield(name="sh", label="sh", plugs=plugs, exposes=exposes or {})


def _inst(name: str, socket: str, shield: Shield) -> Instance:
    return Instance(name=name, shield=shield, socket=socket)


def test_resolve_sockets_finds_a_direct_board_socket() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={}, buses={}, cs_pool=None)})
    inst = _inst("i1", "ard", _shield())
    rig = Rig(name="r", instances=[inst])

    resolution, diags = resolve_sockets(rig, board, {"arduino-r3": _ctype()})

    assert diags == []
    assert resolution.sockets["i1"].label == "ard"


def test_resolve_sockets_unknown_board_socket_is_phys_socket() -> None:
    board = Board(name="b", sockets={})
    inst = _inst("i1", "nope", _shield())
    rig = Rig(name="r", instances=[inst])

    resolution, diags = resolve_sockets(rig, board, {"arduino-r3": _ctype()})

    assert resolution.sockets == {}
    assert len(diags) == 1
    assert diags[0].code == "phys-socket"


def test_resolve_sockets_plug_type_mismatch_is_phys_mating() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="mikrobus",
                          gpio_map={}, buses={}, cs_pool=None)})
    inst = _inst("i1", "ard", _shield(plugs="arduino-r3"))
    rig = Rig(name="r", instances=[inst])

    resolution, diags = resolve_sockets(rig, board, {"mikrobus": _ctype()})

    assert resolution.sockets["i1"] is not None    # the socket still resolves
    assert len(diags) == 1
    assert diags[0].code == "phys-mating"


def test_resolve_sockets_subset_gap_is_phys_subset() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={}, buses={}, cs_pool=None)})
    shield = _shield()
    from rigc.model import Device
    shield.devices.append(Device(name="d", label="d", compatible=None,
                                 bus="uart", group=None, reg=None,
                                 addr_from=None, cs_position=None))
    inst = _inst("i1", "ard", shield)
    rig = Rig(name="r", instances=[inst])

    _resolution, diags = resolve_sockets(rig, board, {"arduino-r3": _ctype()})

    assert len(diags) == 1
    assert diags[0].code == "phys-subset"


def test_resolve_sockets_carrier_chain_composes() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={7: ("gpiod", 0, 0)}, buses={}, cs_pool=None)})
    carrier_shield = _shield(plugs="arduino-r3", exposes={
        "mb1": ExposedSocket(name="mb1", label="mb1", type_name="mikrobus",
                             gpio_map={2: (7, 0)}, buses={})})
    carrier = _inst("adapter_1", "ard", carrier_shield)
    leaf = _inst("eth_1", "adapter_1.mb1", _shield(plugs="mikrobus"))
    rig = Rig(name="r", instances=[carrier, leaf])

    resolution, diags = resolve_sockets(
        rig, board, {"arduino-r3": _ctype(), "mikrobus": _ctype("mikrobus")})

    assert diags == []
    assert resolution.sockets["eth_1"].gpio_map[2] == ("gpiod", 0, 0)


def test_resolve_sockets_cyclic_carrier_reference_is_stack_guarded() -> None:
    """A instance naming its OWN carrier chain cyclically must be rejected
    (phys-socket), never recurse forever."""
    a = _inst("a", "b.x", _shield(exposes={
        "x": ExposedSocket(name="x", label="x", type_name="arduino-r3",
                           gpio_map={}, buses={})}))
    b = _inst("b", "a.x", _shield(exposes={
        "x": ExposedSocket(name="x", label="x", type_name="arduino-r3",
                           gpio_map={}, buses={})}))
    rig = Rig(name="r", instances=[a, b])
    board = Board(name="b", sockets={})

    resolution, diags = resolve_sockets(rig, board, {"arduino-r3": _ctype()})

    assert resolution.sockets == {}
    assert all(d.code == "phys-socket" for d in diags)
    assert len(diags) >= 1


def test_resolve_sockets_two_non_stackable_instances_on_one_socket_is_phys_mating() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={}, buses={}, cs_pool=None)})
    a = _inst("a", "ard", _shield())
    b = _inst("b", "ard", _shield())
    rig = Rig(name="r", instances=[a, b])

    _resolution, diags = resolve_sockets(
        rig, board, {"arduino-r3": _ctype(stackable=False)})

    assert len(diags) == 1
    assert diags[0].code == "phys-mating"
    assert "not stackable" in diags[0].message


def test_resolve_sockets_stackable_type_allows_multiple_instances() -> None:
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={}, buses={}, cs_pool=None)})
    a = _inst("a", "ard", _shield())
    b = _inst("b", "ard", _shield())
    rig = Rig(name="r", instances=[a, b])

    _resolution, diags = resolve_sockets(
        rig, board, {"arduino-r3": _ctype(stackable=True)})

    assert diags == []


def test_resolve_sockets_skips_a_failed_instance_but_keeps_going() -> None:
    """Skip-don't-abort: one instance's board-socket failure never stops
    resolution of the REST of the rig."""
    board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="arduino-r3",
                          gpio_map={}, buses={}, cs_pool=None)})
    bad = _inst("bad", "nope", _shield())
    good = _inst("good", "ard", _shield())
    rig = Rig(name="r", instances=[bad, good])

    resolution, diags = resolve_sockets(rig, board, {"arduino-r3": _ctype()})

    assert "bad" not in resolution.sockets
    assert "good" in resolution.sockets
    assert len(diags) == 1


def _ctype(name: str = "arduino-r3", stackable: bool = True) -> ConnectorType:
    return ConnectorType(name=name, positions={}, index2name={}, bus_proxies=[],
                        stackable=stackable, cs_pool=[])
