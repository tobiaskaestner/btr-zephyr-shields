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
from rigc.model import Instance, Rig, Shield, Wire, WireEnd

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
    shield = Shield(name="sh", label="sh", plugs="t")
    inst = Instance(name="i1", shield=shield, socket="sock",
                   params={"dev": {"debounce-interval-ms": "30"}})
    rig = Rig(name="r", instances=[inst])
    s = Solved()

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "| i1 | dev | debounce-interval-ms | 30 |" in text


def test_params_table_absent_when_no_instance_assigns_any() -> None:
    shield = Shield(name="sh", label="sh", plugs="t")
    inst = Instance(name="i1", shield=shield, socket="sock")
    rig = Rig(name="r", instances=[inst])
    s = Solved()

    text = render_sheet(rig, s, {}, workdir="/does-not-matter")

    assert "## Parameters" not in text
