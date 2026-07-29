"""Unit: loader.params -- the per-instance-parameter invariant as a VALUE
function (rigc-r3-brief.md Sec 6): "(declared params, authored defaults,
assignments) -> findings", restate as "(previously-assigned set, delta-
restated set) -> findings", and pin/params block application (a PURE
function of a Val + a Shield, never mutating an Instance).

**The cpp/unit-test seam**: `apply_params_block`'s token-resolution branch
calls `dtsio.resolve_token`/`check_include` (cpp, a real subprocess) only
when an assigned value is NOT a bare integer literal. Every test here
assigns bare integer literals (`is_int_literal` is unit-tested directly in
test_dtsio.py) precisely so this module's OWN logic -- undeclared/unknown-
device/required/restate decisions -- gets covered without ever reaching
cpp. `check_dt_includes`/`check_param_token`'s cpp-reaching branches are
integration-only by construction, covered through the frozen suite.
"""
from __future__ import annotations

from rigc.diag import SourceRef
from rigc.loader.documents import parse_marked
from rigc.loader.params import (apply_params_block, apply_pin_block,
                               check_param_invariant, check_restate)
from rigc.model import Device, Instance, Jumper, Shield, Strap

_SRC = SourceRef("synthetic", 1)


def _val(tmp_path, text: str, key: str = "v"):
    path = tmp_path / "d.yml"
    path.write_text(text)
    return parse_marked(str(path)).value[key]


def _device(label: str, declared_params=(), extra_props=()) -> Device:
    return Device(name=label, label=label, compatible=None, bus="i2c",
                 group=None, reg=None, addr_from=None, cs_position=None,
                 declared_params=list(declared_params),
                 extra_props=list(extra_props))


def _shield(*devices: Device, name: str = "sh") -> Shield:
    shield = Shield(name=name, label=name, plugs="fixture-type", src=_SRC)
    shield.devices.extend(devices)
    return shield


def _inst(name: str, shield: Shield, params=None) -> Instance:
    inst = Instance(name=name, shield=shield, socket="s", src=_SRC)
    if params is not None:
        inst.params = params
    return inst


# --------------------------------------------------------- check_param_invariant

def test_invariant_passes_when_every_required_param_is_assigned() -> None:
    dev = _device("d", declared_params=["x"])
    inst = _inst("a", _shield(dev), params={"d": {"x": "1"}})
    assert check_param_invariant([inst]) == []


def test_invariant_fires_for_an_unassigned_required_param() -> None:
    dev = _device("d", declared_params=["x"])
    inst = _inst("a", _shield(dev))
    diags = check_param_invariant([inst])
    assert len(diags) == 1
    assert diags[0].code == "lang-param"
    assert "required" in diags[0].message


def test_invariant_is_satisfied_by_an_authored_default() -> None:
    """A declared param WITH a shield-authored default (present among
    extra_props) is OPTIONAL -- omitting it is not a violation."""
    dev = _device("d", declared_params=["x"], extra_props=[("x", "x = <5>;")])
    inst = _inst("a", _shield(dev))
    assert check_param_invariant([inst]) == []


def test_invariant_checks_every_instance_independently() -> None:
    dev = _device("d", declared_params=["x"])
    ok = _inst("ok", _shield(dev, name="sh1"), params={"d": {"x": "1"}})
    bad = _inst("bad", _shield(dev, name="sh2"))
    diags = check_param_invariant([ok, bad])
    assert len(diags) == 1
    assert "'bad'" in diags[0].message


# --------------------------------------------------------------- check_restate

def test_restate_passes_when_every_prior_property_is_restated(tmp_path) -> None:
    params_v = _val(tmp_path, "v: {d: {x: 1}}\n")
    diags = check_restate(params_v, {"d": {"x": "1"}}, "a")
    assert diags == []


def test_restate_fires_for_an_omitted_prior_property(tmp_path) -> None:
    params_v = _val(tmp_path, "v: {d: {}}\n")
    diags = check_restate(params_v, {"d": {"x": "1"}}, "a")
    assert len(diags) == 1
    assert diags[0].code == "lang-param"
    assert "without restating" in diags[0].message
    assert "'x'" in diags[0].message


def test_restate_ignores_a_device_with_no_prior_assignment(tmp_path) -> None:
    params_v = _val(tmp_path, "v: {other: {y: 1}}\n")
    diags = check_restate(params_v, {}, "a")
    assert diags == []


# ---------------------------------------------------------- apply_params_block

def test_apply_params_block_none_is_a_no_op() -> None:
    params, refs, diags = apply_params_block(
        None, "a", _shield(), [], "rig", "/nonexistent", "tag")
    assert (params, refs, diags) == ({}, {}, [])


def test_apply_params_block_assigns_a_declared_bare_int(tmp_path) -> None:
    dev = _device("d", declared_params=["x"])
    params_v = _val(tmp_path, "v: {d: {x: 5}}\n")
    params, refs, diags = apply_params_block(
        params_v, "a", _shield(dev), [], "rig", "/nonexistent", "tag")
    assert diags == []
    assert params == {"d": {"x": "5"}}
    assert "d" in refs and "x" in refs["d"]


def test_apply_params_block_unknown_device_is_rejected(tmp_path) -> None:
    dev = _device("d", declared_params=["x"])
    params_v = _val(tmp_path, "v: {ghost: {x: 5}}\n")
    params, refs, diags = apply_params_block(
        params_v, "a", _shield(dev), [], "rig", "/nonexistent", "tag")
    assert len(diags) == 1
    assert diags[0].code == "lang-param"
    assert "names no device 'ghost'" in diags[0].message


def test_apply_params_block_unknown_device_context_is_folded_into_the_message(
        tmp_path) -> None:
    dev = _device("d", declared_params=["x"])
    params_v = _val(tmp_path, "v: {ghost: {x: 5}}\n")
    _, _, diags = apply_params_block(
        params_v, "a", _shield(dev), [], "rig", "/nonexistent", "tag",
        unknown_device_context="because of variant 'hpm'")
    assert "(because of variant 'hpm')" in diags[0].message


def test_apply_params_block_undeclared_property_is_rejected(tmp_path) -> None:
    dev = _device("d", declared_params=["x"])
    params_v = _val(tmp_path, "v: {d: {y: 5}}\n")
    params, refs, diags = apply_params_block(
        params_v, "a", _shield(dev), [], "rig", "/nonexistent", "tag")
    assert len(diags) == 1
    assert diags[0].code == "lang-param"
    assert "declares no parameter 'y'" in diags[0].message
    assert params == {}


def test_apply_params_block_one_bad_property_does_not_block_the_others(
        tmp_path) -> None:
    dev = _device("d", declared_params=["x", "y"])
    params_v = _val(tmp_path, "v: {d: {x: 1, z: 2}}\n")
    params, refs, diags = apply_params_block(
        params_v, "a", _shield(dev), [], "rig", "/nonexistent", "tag")
    assert len(diags) == 1
    assert params == {"d": {"x": "1"}}


# ------------------------------------------------------------- apply_pin_block

def test_apply_pin_block_none_is_a_no_op() -> None:
    result = apply_pin_block(None, "a", _shield())
    assert result == ({}, {}, {}, {}, [])


def test_apply_pin_block_assigns_a_strap(tmp_path) -> None:
    shield = _shield()
    shield.straps["addr-strap"] = Strap(name="addr-strap", label="addr-strap",
                                       domain=[(0x48, 0), (0x49, 1)], sheet_label="")
    pin_v = _val(tmp_path, "v: {addr-strap: 73}\n")
    pins, pin_refs, jumpers, jumper_refs, diags = apply_pin_block(pin_v, "a", shield)
    assert diags == []
    assert pins == {"addr-strap": 73}
    assert jumpers == {}


def test_apply_pin_block_assigns_a_jumper(tmp_path) -> None:
    shield = _shield()
    shield.jumpers["irq-jmp"] = Jumper(name="irq-jmp", label="irq-jmp",
                                       domain=[(0, 0), (1, 1)], sheet_label="")
    pin_v = _val(tmp_path, "v: {irq-jmp: 1}\n")
    pins, pin_refs, jumpers, jumper_refs, diags = apply_pin_block(pin_v, "a", shield)
    assert diags == []
    assert jumpers == {"irq-jmp": 1}
    assert pins == {}


def test_apply_pin_block_underscore_normalizes_to_hyphen(tmp_path) -> None:
    """rig pin: keys may spell a config element with underscores; the
    shield's own element names are hyphenated (YAML/DTS convention) --
    tried literal first, then with underscores replaced by hyphens."""
    shield = _shield()
    shield.straps["addr-strap"] = Strap(name="addr-strap", label="addr-strap",
                                       domain=[(0x48, 0)], sheet_label="")
    pin_v = _val(tmp_path, "v: {addr_strap: 72}\n")
    pins, _, _, _, diags = apply_pin_block(pin_v, "a", shield)
    assert diags == []
    assert pins == {"addr-strap": 72}


def test_apply_pin_block_unknown_config_element_is_rejected(tmp_path) -> None:
    pin_v = _val(tmp_path, "v: {ghost: 1}\n")
    _, _, _, _, diags = apply_pin_block(pin_v, "a", _shield())
    assert len(diags) == 1
    assert diags[0].code == "lang-pin"
    assert "names no config element 'ghost'" in diags[0].message
