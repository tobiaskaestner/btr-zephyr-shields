"""Unit: loader.delta -- base topology parsing and the V1b delta engine.

The stable contracts (rigc-r2-brief.md Sec 7): delta operations over a
synthetic effective topology (match/add/remove for instances and wires,
`removed_by` propagation), dt-includes union (order, dedup, SrcRef
retention), and diagnostic ORDERING on a multi-error synthetic input --
composed upward in document/traversal order, never accumulated into a
side channel. The ShieldRef seam (params:/pin: raising Unimplemented
immediately) is exercised directly, since it is the one place R2's
deferral boundary is a hard stop rather than a diagnostic.
"""
from __future__ import annotations

import pytest

from rigc.diag import SourceRef
from rigc.loader.binding import SocketBinding
from rigc.loader.delta import (Topology, apply_delta, find_wire,
                               parse_instance, parse_wire, resolve_dotted,
                               union_dt_includes)
from rigc.loader.documents import Val, parse_marked
from rigc.model import Instance, ShieldRef, Wire, WireEnd
from rigc.unimplemented import Unimplemented

_BINDING = SocketBinding()


def _doc(tmp_path, text: str, name: str = "d.yml") -> Val:
    path = tmp_path / name
    path.write_text(text)
    return parse_marked(str(path))


def _inst(name: str, ref: str = "sh", socket: str = "s") -> Instance:
    src = SourceRef("synthetic", 1, name)
    return Instance(name=name, shield=ShieldRef(ref=ref, src=src),
                   socket=socket, src=src)


# ---------------------------------------------------------------- parse_instance

def test_parse_instance_constructs_a_shieldref_without_resolving_it(tmp_path) -> None:
    item = _doc(tmp_path, "name: a\nshield: unresolved_name\nsocket: nucleo_ard\n")
    inst, diags = parse_instance(item, _BINDING)
    assert diags == []
    assert inst is not None
    assert inst.name == "a"
    assert inst.shield.ref == "unresolved_name"    # no library, no existence check
    assert inst.socket == "nucleo_ard"


def test_parse_instance_applies_the_socket_binding(tmp_path) -> None:
    item = _doc(tmp_path, "name: a\nshield: sh\nsocket: ard\n")
    inst, diags = parse_instance(item, SocketBinding({"ard": "nucleo_ard"}))
    assert inst is not None
    assert inst.socket == "nucleo_ard"


def test_parse_instance_missing_required_key_returns_diagnostic(tmp_path) -> None:
    item = _doc(tmp_path, "name: a\nsocket: s\n")   # no shield:
    inst, diags = parse_instance(item, _BINDING)
    assert inst is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_parse_instance_with_params_raises_unimplemented(tmp_path) -> None:
    item = _doc(tmp_path, "name: a\nshield: sh\nsocket: s\n"
                        "params: {dev: {x: '1'}}\n")
    with pytest.raises(Unimplemented):
        parse_instance(item, _BINDING)


def test_parse_instance_with_pin_raises_unimplemented(tmp_path) -> None:
    item = _doc(tmp_path, "name: a\nshield: sh\nsocket: s\npin: {p1: 1}\n")
    with pytest.raises(Unimplemented):
        parse_instance(item, _BINDING)


# --------------------------------------------------------------- resolve_dotted

def test_resolve_dotted_valid_reference_needs_no_shield_data(tmp_path) -> None:
    doc = _doc(tmp_path, "x: a.sq\n")
    by_name = {"a": _inst("a")}
    end, diags = resolve_dotted(doc.value["x"], by_name, "from")
    assert diags == []
    assert end == WireEnd(instance_name="a", node="sq", src=doc.value["x"].src)


def test_resolve_dotted_rejects_non_dotted_form(tmp_path) -> None:
    doc = _doc(tmp_path, "x: nodot\n")
    end, diags = resolve_dotted(doc.value["x"], {}, "from")
    assert end is None
    assert diags[0].code == "lang-wire-ref"


def test_resolve_dotted_rejects_unknown_instance(tmp_path) -> None:
    doc = _doc(tmp_path, "x: ghost.sq\n")
    end, diags = resolve_dotted(doc.value["x"], {"a": _inst("a")}, "from")
    assert end is None
    assert diags[0].code == "lang-wire-ref"


def test_resolve_dotted_does_not_validate_the_node_name(tmp_path) -> None:
    """The ShieldRef seam: node existence needs shield data, deferred to
    R3 -- any node string past the instance name is accepted."""
    doc = _doc(tmp_path, "x: a.no-such-node\n")
    end, diags = resolve_dotted(doc.value["x"], {"a": _inst("a")}, "from")
    assert diags == []
    assert end is not None
    assert end.node == "no-such-node"


def test_resolve_dotted_missing_key() -> None:
    end, diags = resolve_dotted(None, {}, "from")
    assert end is None
    assert diags[0].code == "lang-schema"


# ------------------------------------------------------------------- parse_wire

def test_parse_wire_bare_string_route(tmp_path) -> None:
    item = _doc(tmp_path, "from: a.sq\nto: b.led\nroute: adhoc\n")
    by_name = {"a": _inst("a"), "b": _inst("b")}
    wire, diags = parse_wire(item, by_name)
    assert diags == []
    assert wire is not None
    assert wire.route == "adhoc"


def test_parse_wire_via_mapping_route(tmp_path) -> None:
    item = _doc(tmp_path, "from: a.sq\nto: b.led\nroute: {via: D2}\n")
    by_name = {"a": _inst("a"), "b": _inst("b")}
    wire, diags = parse_wire(item, by_name)
    assert diags == []
    assert wire is not None
    assert wire.route == "D2"


def test_parse_wire_mapping_route_without_via_is_rejected(tmp_path) -> None:
    item = _doc(tmp_path, "from: a.sq\nto: b.led\nroute: {}\n")
    by_name = {"a": _inst("a"), "b": _inst("b")}
    wire, diags = parse_wire(item, by_name)
    assert wire is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert "via" in diags[0].message


def test_parse_wire_missing_route_key_is_rejected(tmp_path) -> None:
    item = _doc(tmp_path, "from: a.sq\nto: b.led\n")
    by_name = {"a": _inst("a"), "b": _inst("b")}
    wire, diags = parse_wire(item, by_name)
    assert wire is None
    assert diags[0].code == "lang-schema"


# ------------------------------------------------------------------- find_wire

def test_find_wire_matches_raw_endpoint_pair_with_no_shield_data() -> None:
    end_a = WireEnd(instance_name="x", node="sq", src=SourceRef("s", 1))
    end_b = WireEnd(instance_name="y", node="led-1", src=SourceRef("s", 1))
    wire = Wire(frm=end_a, to=end_b, route="adhoc", src=SourceRef("s", 1))
    assert find_wire([wire], "x.sq", "y.led-1") is wire
    assert find_wire([wire], "x.sq", "y.led-2") is None


def test_find_wire_none_endpoint_never_matches() -> None:
    assert find_wire([], None, "y.led-1") is None


# ------------------------------------------------------------- union_dt_includes

def test_union_dt_includes_appends_new_headers(tmp_path) -> None:
    doc = _doc(tmp_path, "dt-includes: [a.h, b.h]\n")
    headers, refs = union_dt_includes([], [], doc.value["dt-includes"])
    assert headers == ["a.h", "b.h"]
    assert len(refs) == 2


def test_union_dt_includes_dedups_keeping_the_earlier_srcref(tmp_path) -> None:
    doc = _doc(tmp_path, "dt-includes: [a.h]\n")
    first_ref = SourceRef("earlier", 1, "dt-includes[0]")
    headers, refs = union_dt_includes(["a.h"], [first_ref], doc.value["dt-includes"])
    assert headers == ["a.h"]
    assert refs == [first_ref]           # the LATER duplicate's ref is dropped


def test_union_dt_includes_none_is_a_no_op() -> None:
    headers, refs = union_dt_includes(["a.h"], [SourceRef("s", 1)], None)
    assert headers == ["a.h"]


def test_union_dt_includes_does_not_mutate_its_inputs(tmp_path) -> None:
    doc = _doc(tmp_path, "dt-includes: [b.h]\n")
    original = ["a.h"]
    union_dt_includes(original, [], doc.value["dt-includes"])
    assert original == ["a.h"]


# ------------------------------------------------------------------- apply_delta

def _topology_with(*names: str) -> Topology:
    effective = {n: _inst(n) for n in names}
    return Topology(effective=effective, order=list(names))


def test_instances_patch_matching_by_name_replaces_socket(tmp_path) -> None:
    delta = _doc(tmp_path, "instances: [{name: a, socket: new_ard}]\n")
    topology = _topology_with("a")
    new_topology, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert diags == []
    assert new_topology.effective["a"].socket == "new_ard"
    # the ORIGINAL topology's instance is untouched -- a new value, not a
    # mutation of the one handed in.
    assert topology.effective["a"].socket == "s"


def test_instances_patch_unknown_name_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, "instances: [{name: ghost, socket: x}]\n")
    topology = _topology_with("a")
    _, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "does not have" in diags[0].message


def test_add_instances_new_name_is_appended_to_order(tmp_path) -> None:
    delta = _doc(tmp_path, "add-instances: [{name: c, shield: sh, socket: s}]\n")
    topology = _topology_with("a")
    new_topology, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert diags == []
    assert new_topology.order == ["a", "c"]
    assert "c" in new_topology.effective


def test_add_instances_existing_name_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, "add-instances: [{name: a, shield: sh, socket: s}]\n")
    topology = _topology_with("a")
    _, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "already exists" in diags[0].message


def test_remove_instances_removes_and_records_removed_by(tmp_path) -> None:
    delta = _doc(tmp_path, "remove-instances: [a]\n")
    topology = _topology_with("a")
    new_topology, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert diags == []
    assert "a" not in new_topology.effective
    assert new_topology.removed_by["a"] == "b"


def test_remove_instances_absent_name_is_rejected_and_names_prior_remover(
        tmp_path) -> None:
    delta = _doc(tmp_path, "remove-instances: [a]\n")
    topology = Topology(removed_by={"a": "b"})   # already removed by variant b
    _, diags = apply_delta(delta, "revision", "2", topology, _BINDING)
    assert len(diags) == 1
    assert diags[0].code == "lang-rev"
    # The prior remover is NAMED (data presence, not wording -- the exact
    # phrasing belongs to the remove-instance-drift golden alone).
    assert "'b'" in diags[0].message


def test_remove_wires_matches_endpoint_pair(tmp_path) -> None:
    delta = _doc(tmp_path, "remove-wires: [{from: x.sq, to: y.led-1}]\n")
    end_a = WireEnd(instance_name="x", node="sq", src=SourceRef("s", 1))
    end_b = WireEnd(instance_name="y", node="led-1", src=SourceRef("s", 1))
    wire = Wire(frm=end_a, to=end_b, route="adhoc", src=SourceRef("s", 1))
    topology = Topology(wires=[wire])
    new_topology, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert diags == []
    assert new_topology.wires == []


def test_remove_wires_missing_pair_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, "remove-wires: [{from: x.sq, to: y.led-2}]\n")
    topology = Topology()
    _, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "does not exist" in diags[0].message


def test_add_wires_parses_like_base_wires(tmp_path) -> None:
    delta = _doc(tmp_path, "add-wires: [{from: a.sq, to: b.led, route: adhoc}]\n")
    topology = _topology_with("a", "b")
    new_topology, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert diags == []
    assert len(new_topology.wires) == 1


def test_metadata_keys_are_rejected_before_any_other_delta_operation(tmp_path) -> None:
    delta = _doc(tmp_path,
               "board: some/other/board\n"
               "remove-instances: [ghost]\n")
    topology = _topology_with("a")
    _, diags = apply_delta(delta, "revision", "2", topology, _BINDING)
    assert [d.code for d in diags] == ["lang-schema", "lang-rev"]
    assert "is rig.yml metadata" in diags[0].message


def test_multiple_delta_errors_compose_in_document_order(tmp_path) -> None:
    """Diagnostic ordering: several operations in ONE delta each raise,
    and the composed order must equal document/traversal order -- never
    a mutable side channel's own append order."""
    delta = _doc(tmp_path,
               "instances: [{name: ghost1, socket: s}]\n"
               "remove-instances: [ghost2]\n")
    topology = _topology_with("a")
    _, diags = apply_delta(delta, "variant", "b", topology, _BINDING)
    assert len(diags) == 2
    assert "ghost1" in diags[0].message
    assert "ghost2" in diags[1].message


def test_instance_patch_with_params_raises_unimplemented(tmp_path) -> None:
    delta = _doc(tmp_path, "instances: [{name: a, params: {d: {x: '1'}}}]\n")
    topology = _topology_with("a")
    with pytest.raises(Unimplemented):
        apply_delta(delta, "variant", "b", topology, _BINDING)


def test_apply_delta_never_mutates_the_topology_it_was_given(tmp_path) -> None:
    delta = _doc(tmp_path, "add-instances: [{name: c, shield: sh, socket: s}]\n")
    topology = _topology_with("a")
    apply_delta(delta, "variant", "b", topology, _BINDING)
    assert topology.order == ["a"]
    assert "c" not in topology.effective
