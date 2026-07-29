"""Unit: loader.delta -- base topology parsing and the V1b delta engine.

The stable contracts: delta operations over a synthetic effective
topology (match/add/remove for instances and wires, `removed_by`
propagation), dt-includes union (order, dedup, SrcRef retention), and
diagnostic ORDERING on a multi-error synthetic input -- composed upward
in document/traversal order, never accumulated into a side channel.

R3 closes R2's ShieldRef seam: `parse_instance`/`apply_delta` now resolve
`shield:` against a REAL (synthetic, hermetic) `ShieldLibrary` built
in-process from a hand-constructed `Shield` value -- never a filesystem
scan, never cpp (the cpp/unit-test seam, rigc-r3-brief.md Sec 2). Params/
pin application and wire node-existence/ambiguity checks get their own
unit coverage in test_params.py; this module's tests exercise the SHIELD
RESOLUTION seam itself (a resolve() that succeeds, fails "unknown shield",
or is never reached because a required key is missing) plus everything
that needs no shield data at all (removal/collision/ordering mechanics).
"""
from __future__ import annotations

from textwrap import dedent

from rigc.diag import SourceRef
from rigc.loader.binding import SocketBinding
from rigc.loader.delta import (Topology, apply_delta, find_wire,
                               parse_instance, parse_wire, resolve_dotted,
                               union_dt_includes)
from rigc.loader.documents import Val, parse_marked
from rigc.loader.library import ShieldLibrary
from rigc.model import Device, Instance, Pad, Shield, Wire, WireEnd

_BINDING = SocketBinding()


def _shield(name: str = "sh", pads=(), devices=()) -> Shield:
    shield = Shield(name=name, label=name, plugs="synthetic-type",
                    src=SourceRef("synthetic", 1))
    for pad_name in pads:
        shield.pads[pad_name] = Pad(name=pad_name, label=pad_name, role="bidir", of=None)
    for dev in devices:
        shield.devices.append(dev)
    return shield


def _library(*shields: Shield) -> ShieldLibrary:
    """A hermetic, in-memory library: every shield already PARSED (no
    scan, no cpp) -- the synthetic value the cpp/unit-test seam calls
    for."""
    return ShieldLibrary(
        shields={s.name: s for s in shields},
        axes={s.name: None for s in shields},
        pending={}, ymls={}, types={}, workdir="/nonexistent")


def _inst(name: str, shield: Shield, socket: str = "s") -> Instance:
    src = SourceRef("synthetic", 1, name)
    return Instance(name=name, shield=shield, socket=socket, src=src)


def _doc(tmp_path, text: str, name: str = "d.yml") -> Val:
    path = tmp_path / name
    path.write_text(dedent(text))
    return parse_marked(str(path))


# ---------------------------------------------------------------- parse_instance

def test_parse_instance_resolves_the_shield_against_the_library(tmp_path) -> None:
    lib = _library(_shield("sh"))
    item = _doc(tmp_path, """\
        name: a
        shield: sh
        socket: nucleo_ard
        """)
    inst, diags, deps = parse_instance(item, _BINDING, lib, "rig", [], str(tmp_path))
    assert diags == []
    assert inst is not None
    assert inst.name == "a"
    assert inst.shield.name == "sh"
    assert inst.socket == "nucleo_ard"


def test_parse_instance_unknown_shield_is_rejected(tmp_path) -> None:
    lib = _library()
    item = _doc(tmp_path, """\
        name: a
        shield: ghost
        socket: s
        """)
    inst, diags, deps = parse_instance(item, _BINDING, lib, "rig", [], str(tmp_path))
    assert inst is None
    assert len(diags) == 1
    assert diags[0].code == "lang-instance-shield"


def test_parse_instance_applies_the_socket_binding(tmp_path) -> None:
    lib = _library(_shield("sh"))
    item = _doc(tmp_path, """\
        name: a
        shield: sh
        socket: ard
        """)
    inst, diags, deps = parse_instance(
        item, SocketBinding({"ard": "nucleo_ard"}), lib, "rig", [], str(tmp_path))
    assert inst is not None
    assert inst.socket == "nucleo_ard"


def test_parse_instance_missing_required_key_returns_diagnostic(tmp_path) -> None:
    item = _doc(tmp_path, """\
        name: a
        socket: s
        """)   # no shield:
    inst, diags, deps = parse_instance(item, _BINDING, _library(), "rig", [], str(tmp_path))
    assert inst is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


# --------------------------------------------------------------- resolve_dotted

def test_resolve_dotted_valid_reference_resolves_the_node(tmp_path) -> None:
    doc = _doc(tmp_path, "x: a.sq\n")
    by_name = {"a": _inst("a", _shield("sh", pads=["sq"]))}
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
    by_name = {"a": _inst("a", _shield("sh", pads=["sq"]))}
    end, diags = resolve_dotted(doc.value["x"], by_name, "from")
    assert end is None
    assert diags[0].code == "lang-wire-ref"


def test_resolve_dotted_rejects_unknown_node_in_the_shield(tmp_path) -> None:
    """R3 closes the R2 deferral: node existence is now validated via
    Shield.by_name (no frozen golden covers this wording -- hand-
    differential rule, recorded in the slice report)."""
    doc = _doc(tmp_path, """\
        x: a.no-such-node
        """)
    by_name = {"a": _inst("a", _shield("sh", pads=["sq"]))}
    end, diags = resolve_dotted(doc.value["x"], by_name, "from")
    assert end is None
    assert diags[0].code == "lang-wire-ref"
    assert "has no node 'no-such-node'" in diags[0].message


def test_resolve_dotted_rejects_ambiguous_node(tmp_path) -> None:
    """A name matching more than one of pads/devices/straps is ambiguous
    (Shield.by_name's own contract) -- exercised here via two pads
    sharing a name, the simplest synthetic collision."""
    shield = _shield("sh")
    shield.pads["dup"] = Pad(name="dup", label="dup", role="bidir", of=None)
    shield.by_path["p1"] = shield.pads["dup"]
    # Shield.by_name scans self.pads.items() by NAME match, so a single
    # dict cannot itself hold two same-named pads -- simulate the
    # ambiguity the way the model actually allows it: a device sharing a
    # pad's name.
    shield.devices.append(Device(name="dup", label="dup_dev", compatible=None,
                                 bus=None, group="gpio", reg=None,
                                 addr_from=None, cs_position=None))
    doc = _doc(tmp_path, "x: a.dup\n")
    by_name = {"a": _inst("a", shield)}
    end, diags = resolve_dotted(doc.value["x"], by_name, "from")
    assert end is None
    assert diags[0].code == "lang-wire-ref"
    assert "is ambiguous" in diags[0].message


def test_resolve_dotted_missing_key() -> None:
    end, diags = resolve_dotted(None, {}, "from")
    assert end is None
    assert diags[0].code == "lang-schema"


# ------------------------------------------------------------------- parse_wire

def test_parse_wire_bare_string_route(tmp_path) -> None:
    item = _doc(tmp_path, """\
        from: a.sq
        to: b.led
        route: adhoc
        """)
    by_name = {"a": _inst("a", _shield("sh_a", pads=["sq"])),
              "b": _inst("b", _shield("sh_b", pads=["led"]))}
    wire, diags = parse_wire(item, by_name)
    assert diags == []
    assert wire is not None
    assert wire.route == "adhoc"


def test_parse_wire_via_mapping_route(tmp_path) -> None:
    item = _doc(tmp_path, """\
        from: a.sq
        to: b.led
        route: {via: D2}
        """)
    by_name = {"a": _inst("a", _shield("sh_a", pads=["sq"])),
              "b": _inst("b", _shield("sh_b", pads=["led"]))}
    wire, diags = parse_wire(item, by_name)
    assert diags == []
    assert wire is not None
    assert wire.route == "D2"


def test_parse_wire_mapping_route_without_via_is_rejected(tmp_path) -> None:
    item = _doc(tmp_path, """\
        from: a.sq
        to: b.led
        route: {}
        """)
    by_name = {"a": _inst("a", _shield("sh_a", pads=["sq"])),
              "b": _inst("b", _shield("sh_b", pads=["led"]))}
    wire, diags = parse_wire(item, by_name)
    assert wire is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert "via" in diags[0].message


def test_parse_wire_missing_route_key_is_rejected(tmp_path) -> None:
    item = _doc(tmp_path, """\
        from: a.sq
        to: b.led
        """)
    by_name = {"a": _inst("a", _shield("sh_a", pads=["sq"])),
              "b": _inst("b", _shield("sh_b", pads=["led"]))}
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
    doc = _doc(tmp_path, """\
        dt-includes: [a.h, b.h]
        """)
    headers, refs = union_dt_includes([], [], doc.value["dt-includes"])
    assert headers == ["a.h", "b.h"]
    assert len(refs) == 2


def test_union_dt_includes_dedups_keeping_the_earlier_srcref(tmp_path) -> None:
    doc = _doc(tmp_path, """\
        dt-includes: [a.h]
        """)
    first_ref = SourceRef("earlier", 1, "dt-includes[0]")
    headers, refs = union_dt_includes(["a.h"], [first_ref], doc.value["dt-includes"])
    assert headers == ["a.h"]
    assert refs == [first_ref]           # the LATER duplicate's ref is dropped


def test_union_dt_includes_none_is_a_no_op() -> None:
    headers, refs = union_dt_includes(["a.h"], [SourceRef("s", 1)], None)
    assert headers == ["a.h"]


def test_union_dt_includes_does_not_mutate_its_inputs(tmp_path) -> None:
    doc = _doc(tmp_path, """\
        dt-includes: [b.h]
        """)
    original = ["a.h"]
    union_dt_includes(original, [], doc.value["dt-includes"])
    assert original == ["a.h"]


# ------------------------------------------------------------------- apply_delta

def _topology_with(*names: str, shield=None) -> Topology:
    sh = shield or _shield("sh")
    effective = {n: _inst(n, sh) for n in names}
    return Topology(effective=effective, order=list(names))


def _apply(delta, stage, stage_value, topology, lib=None, binding=_BINDING,
          variant=None, rig_name="rig", dt_includes=(), workdir="/nonexistent"):
    return apply_delta(delta, stage, stage_value, topology, binding,
                       lib or _library(_shield("sh")), variant, rig_name,
                       list(dt_includes), workdir)


def test_instances_patch_matching_by_name_replaces_socket(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        instances: [{name: a, socket: new_ard}]
        """)
    topology = _topology_with("a")
    new_topology, diags, deps = _apply(delta, "variant", "b", topology)
    assert diags == []
    assert new_topology.effective["a"].socket == "new_ard"
    # the ORIGINAL topology's instance is untouched -- a new value, not a
    # mutation of the one handed in.
    assert topology.effective["a"].socket == "s"


def test_instances_patch_unknown_name_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        instances: [{name: ghost, socket: x}]
        """)
    topology = _topology_with("a")
    _, diags, deps = _apply(delta, "variant", "b", topology)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "does not have" in diags[0].message


def test_instances_patch_can_swap_the_shield(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        instances: [{name: a, shield: sh2}]
        """)
    topology = _topology_with("a")
    lib = _library(_shield("sh"), _shield("sh2"))
    new_topology, diags, deps = _apply(delta, "variant", "b", topology, lib=lib)
    assert diags == []
    assert new_topology.effective["a"].shield.name == "sh2"


def test_instances_patch_unknown_shield_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        instances: [{name: a, shield: ghost}]
        """)
    topology = _topology_with("a")
    _, diags, deps = _apply(delta, "variant", "b", topology)
    assert len(diags) == 1
    assert diags[0].code == "lang-instance-shield"


def test_add_instances_new_name_is_appended_to_order(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        add-instances: [{name: c, shield: sh, socket: s}]
        """)
    topology = _topology_with("a")
    new_topology, diags, deps = _apply(delta, "variant", "b", topology)
    assert diags == []
    assert new_topology.order == ["a", "c"]
    assert "c" in new_topology.effective


def test_add_instances_existing_name_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        add-instances: [{name: a, shield: sh, socket: s}]
        """)
    topology = _topology_with("a")
    _, diags, deps = _apply(delta, "variant", "b", topology)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "already exists" in diags[0].message


def test_remove_instances_removes_and_records_removed_by(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        remove-instances: [a]
        """)
    topology = _topology_with("a")
    new_topology, diags, deps = _apply(delta, "variant", "b", topology)
    assert diags == []
    assert "a" not in new_topology.effective
    assert new_topology.removed_by["a"] == "b"


def test_remove_instances_absent_name_is_rejected_and_names_prior_remover(
        tmp_path) -> None:
    delta = _doc(tmp_path, """\
        remove-instances: [a]
        """)
    topology = Topology(removed_by={"a": "b"})   # already removed by variant b
    _, diags, deps = _apply(delta, "revision", "2", topology)
    assert len(diags) == 1
    assert diags[0].code == "lang-rev"
    # The prior remover is NAMED (data presence, not wording -- the exact
    # phrasing belongs to the remove-instance-drift golden alone).
    assert "'b'" in diags[0].message


def test_remove_wires_matches_endpoint_pair(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        remove-wires: [{from: x.sq, to: y.led-1}]
        """)
    end_a = WireEnd(instance_name="x", node="sq", src=SourceRef("s", 1))
    end_b = WireEnd(instance_name="y", node="led-1", src=SourceRef("s", 1))
    wire = Wire(frm=end_a, to=end_b, route="adhoc", src=SourceRef("s", 1))
    topology = Topology(wires=[wire])
    new_topology, diags, deps = _apply(delta, "variant", "b", topology)
    assert diags == []
    assert new_topology.wires == []


def test_remove_wires_missing_pair_is_rejected(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        remove-wires: [{from: x.sq, to: y.led-2}]
        """)
    topology = Topology()
    _, diags, deps = _apply(delta, "variant", "b", topology)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "does not exist" in diags[0].message


def test_add_wires_parses_like_base_wires(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        add-wires: [{from: a.sq, to: b.led, route: adhoc}]
        """)
    shield = _shield("sh", pads=["sq", "led"])
    topology = _topology_with("a", "b", shield=shield)
    new_topology, diags, deps = _apply(delta, "variant", "b", topology)
    assert diags == []
    assert len(new_topology.wires) == 1


def test_metadata_keys_are_rejected_before_any_other_delta_operation(tmp_path) -> None:
    delta = _doc(tmp_path,
               """\
        board: some/other/board
        remove-instances: [ghost]
        """)
    topology = _topology_with("a")
    _, diags, deps = _apply(delta, "revision", "2", topology)
    assert [d.code for d in diags] == ["lang-schema", "lang-rev"]
    assert "is rig.yml metadata" in diags[0].message


def test_multiple_delta_errors_compose_in_document_order(tmp_path) -> None:
    """Diagnostic ordering: several operations in ONE delta each raise,
    and the composed order must equal document/traversal order -- never
    a mutable side channel's own append order."""
    delta = _doc(tmp_path,
               """\
        instances: [{name: ghost1, socket: s}]
        remove-instances: [ghost2]
        """)
    topology = _topology_with("a")
    _, diags, deps = _apply(delta, "variant", "b", topology)
    assert len(diags) == 2
    assert "ghost1" in diags[0].message
    assert "ghost2" in diags[1].message


def test_apply_delta_never_mutates_the_topology_it_was_given(tmp_path) -> None:
    delta = _doc(tmp_path, """\
        add-instances: [{name: c, shield: sh, socket: s}]
        """)
    topology = _topology_with("a")
    _apply(delta, "variant", "b", topology)
    assert topology.order == ["a"]
    assert "c" not in topology.effective


# ------------------------------------------------ apply_delta <-> params glue

def test_instance_patch_shield_swap_drops_the_old_params(tmp_path) -> None:
    """When shield: changes, the OLD params are keyed to the OLD
    shield's devices and are dropped rather than carried forward -- the
    glue `_apply_instance_patch` itself owns (params.py's own functions
    are pure and know nothing about a "previous" shield)."""
    dev = Device(name="d", label="dl", compatible=None, bus="i2c", group=None,
                reg=None, addr_from=None, cs_position=None)
    old_shield = _shield("sh", devices=[dev])
    new_shield = _shield("sh2")
    topology = _topology_with("a", shield=old_shield)
    topology.effective["a"].params = {"dl": {"x": "1"}}
    delta = _doc(tmp_path, """\
        instances: [{name: a, shield: sh2}]
        """)
    lib = _library(old_shield, new_shield)
    new_topology, diags, deps = _apply(delta, "variant", "b", topology, lib=lib)
    assert diags == []
    assert new_topology.effective["a"].params == {}


def test_instance_patch_params_without_shield_change_runs_the_restate_check(
        tmp_path) -> None:
    """params: for an instance whose shield: is UNCHANGED must restate
    every already-assigned property (rule 11) -- the glue that decides
    WHEN to call check_restate lives in `_apply_instance_patch`."""
    dev = Device(name="d", label="dl", compatible=None, bus="i2c", group=None,
                reg=None, addr_from=None, cs_position=None,
                declared_params=["vnd,threshold"])
    shield = _shield("sh", devices=[dev])
    topology = _topology_with("a", shield=shield)
    topology.effective["a"].params = {"dl": {"vnd,threshold": "10"}}
    delta = _doc(tmp_path, """\
        instances: [{name: a, params: {dl: {}}}]
        """)
    lib = _library(shield)
    _, diags, deps = _apply(delta, "variant", "b", topology, lib=lib)
    assert len(diags) == 1
    assert diags[0].code == "lang-param"
    assert "without restating" in diags[0].message
