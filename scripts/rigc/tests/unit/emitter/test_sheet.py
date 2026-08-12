"""Unit: emitter/sheet -- config-sheet.md (rigc-r5-brief.md Sec 4). The
one contract this module exists to pin: the Wires section reads
`solved.wires`, never `rig.wires` -- they differ (the loader's raw
`via <name>` route string vs the analyzer's resolved connector-position
index), and reading the wrong one is a silent wrong-overlay-class bug no
frozen golden would catch on its own if the two ever diverged in a
fixture the corpus doesn't happen to exercise.
"""
from __future__ import annotations

from rigc.analyzer import Solved
from rigc.diag import SourceRef
from rigc.emitter.sheet import render_sheet
from rigc.model import (BoardSocket, Device, Instance, Rig, Shield, Strap,
                        Wire, WireEnd)

_SRC = SourceRef("f.yml", 1, "k")


def test_wires_section_shows_solveds_resolved_route_not_rigs_raw_one() -> None:
    """Same endpoints, two Wire values: rig.wires carries the raw `via
    D7` name (route="D7"); solved.wires carries the analyzer's own
    resolved position INDEX (route=7). The rendered sheet must show the
    RESOLVED form."""
    frm = WireEnd(instance_name="a", node="x", src=_SRC)
    to = WireEnd(instance_name="b", node="y", src=_SRC)
    raw_wire = Wire(frm=frm, to=to, route="D7", src=_SRC)
    resolved_wire = Wire(frm=frm, to=to, route=7, src=_SRC)

    rig = Rig(name="r", instances=[], wires=[raw_wire])
    s = Solved(wires=[resolved_wire])

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "via header position 7" in text
    assert "via header position D7" not in text


def test_no_wires_section_when_solved_carries_none() -> None:
    rig = Rig(name="r", instances=[])
    s = Solved(wires=[])

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "## Wires" not in text


def test_adhoc_route_renders_as_a_jumper_wire_not_a_header_position() -> None:
    frm = WireEnd(instance_name="a", node="x", src=_SRC)
    to = WireEnd(instance_name="b", node="y", src=_SRC)
    wire = Wire(frm=frm, to=to, route="adhoc", src=_SRC)
    rig = Rig(name="r", instances=[])
    s = Solved(wires=[wire])

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "ad-hoc jumper wire (in no connector)" in text
    assert "connect **a.x** → **b.y**" in text


def test_params_table_shows_an_int_literal_value_with_no_resolution_attempt() -> None:
    """is_int_literal short-circuits before resolve_token ever runs (which
    would need a real cpp/dtlib TU) -- keeps this test hermetic and
    subprocess-free while still exercising the table's own row shape."""
    shield = Shield(name="sh", label="sh", plugs={"plug": "t"})
    inst = Instance(name="i1", shield=shield, sockets={"plug": "sock"},
                   params={"dev": {"debounce-interval-ms": "30"}})
    rig = Rig(name="r", instances=[inst])
    s = Solved()

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "| i1 | dev | debounce-interval-ms | 30 |" in text


def test_socket_assignment_row_shows_the_resolved_label_when_none_was_declared() -> None:
    """socket-inference-brief.md Sec 7: an instance whose socket: was
    omitted and inferred carries no declared string to print -- the sheet
    is a bench instruction and must fall back to the resolved socket's own
    label rather than print "None"."""
    shield = Shield(name="sh", label="sh", plugs={"plug": "t"})
    inst = Instance(name="i1", shield=shield, sockets={"plug": None})
    rig = Rig(name="r", instances=[inst])
    socket = BoardSocket(label="ard", path="/ard", type_name="t",
                        gpio_map={}, buses={})
    s = Solved(sockets={"i1": {"plug": socket}})

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "| i1 | sh | ard |" in text
    assert "None" not in text


def test_socket_assignment_row_shows_the_declared_string_when_one_was_given() -> None:
    """The other half: declared-else-resolved must not disturb the
    everyday case -- a declared socket: still prints verbatim, never the
    resolved label, wherever the two differ (an alias, say)."""
    shield = Shield(name="sh", label="sh", plugs={"plug": "t"})
    inst = Instance(name="i1", shield=shield, sockets={"plug": "arduino_r3"})
    rig = Rig(name="r", instances=[inst])
    socket = BoardSocket(label="nucleo_ard", path="/ard", type_name="t",
                        gpio_map={}, buses={})
    s = Solved(sockets={"i1": {"plug": socket}})

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "| i1 | sh | arduino_r3 |" in text


def test_strap_line_shows_the_owning_devices_own_slot_on_a_plural_shield() -> None:
    """`_strap_owner_slot` pins its CURRENT first-device-wins choice
    (reviewer finding 2, previously uncovered): straps are address-
    domain and bus-scoped, unaffected by plurality itself, but the sheet
    still needs a slot to pick a socket cell for -- it uses the slot of
    the (first) device whose addr_from names this strap. Here that
    device sits on the NON-default 'right' slot, so the straps line must
    show the 'right' socket, not 'left'."""
    shield = Shield(name="sh", label="sh", plugs={"left": "t", "right": "t"})
    strap = Strap(name="addr0", label="addr0", domain=[(0x10, 0), (0x11, 1)],
                 sheet_label="ADDR0")
    shield.straps[strap.name] = strap
    dev = Device(name="d", label="dl", compatible=None, bus="i2c", group=None,
                reg=None, addr_from="addr0", cs_position=None, plug="right")
    shield.devices.append(dev)
    inst = Instance(name="i1", shield=shield,
                    sockets={"left": "sockL", "right": "sockR"})
    rig = Rig(name="r", instances=[inst])
    s = Solved(straps=[(inst, strap, 1, 0x11)])

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "**i1** (sockR): set **ADDR0** to state 1" in text
    assert "sockL): set **ADDR0**" not in text


def test_params_table_absent_when_no_instance_assigns_any() -> None:
    shield = Shield(name="sh", label="sh", plugs={"plug": "t"})
    inst = Instance(name="i1", shield=shield, sockets={"plug": "sock"})
    rig = Rig(name="r", instances=[inst])
    s = Solved()

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "## Parameters" not in text
