"""Unit: shields -- the `.shield` translation-unit model, over cpp-free
synthetic DTs (rigc-r3-brief.md Sec 6: "shield-model parse over cpp-free
synthetic DTs (devices by parentage, declared_params, by_name)"). Every
DT here is built with `dtlib.DT()` DIRECTLY from hand-written, already-
preprocessed text -- no cpp, no subprocess (the cpp/unit-test seam) --
and every connector type is a PURPOSE-BUILT synthetic value (T0's
hermeticity rule), never a real corpus one.
"""
from __future__ import annotations

from textwrap import dedent

from rigc.dtsio import get_dtlib
from rigc.model import ConnectorType, Jumper, Pad, Position, Strap
from rigc.shields import parse_shields

_PLUG_TYPE = ConnectorType(
    name="fixture-type",
    positions={
        "P0": Position(name="P0", index=0, function="gpio"),
        "P1": Position(name="P1", index=1, function="gpio"),
        # BUS_COPPER (index 2) is deliberately ABSENT here -- it exists
        # on index2name (the header's full index) but is not a claimable
        # plug,positions entry.
    },
    index2name={0: "P0", 1: "P1", 2: "BUS_COPPER"},
    bus_proxies=["i2c", "spi"],
    stackable=True,
    cs_pool=[],
)
# BUS_COPPER (index 2) is NOT in .positions -- it exists on the header
# (index2name) but is bus copper, not a claimable position (mirrors real
# connector types' D11-D13-doubles-as-SPI shape).
_TYPES = {"fixture-type": _PLUG_TYPE}


def _dt(tmp_path, body: str):
    path = tmp_path / "fixture.dts"
    path.write_text(f"/dts-v1/;\n/ {{\n\tshield-templates {{\n{body}\n\t}};\n}};\n")
    return get_dtlib().DT(str(path))


def _one_shield(tmp_path, body: str):
    dt = _dt(tmp_path, body)
    shields, diags = parse_shields(dt, _TYPES)
    return shields, diags


# ---------------------------------------------------------------- parse_shields

def test_no_shield_templates_root_yields_nothing(tmp_path) -> None:
    path = tmp_path / "empty.dts"
    path.write_text(dedent("""\
        /dts-v1/;
        / { };
        """))
    dt = get_dtlib().DT(str(path))
    shields, diags = parse_shields(dt, _TYPES)
    assert shields == {}
    assert diags == []


def test_basic_identity(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t};
""")
    assert diags == []
    assert set(shields) == {"fx"}
    shield = shields["fx"]
    assert shield.name == "fx"
    assert shield.label == "fx"
    assert shield.plugs == "fixture-type"


def test_unknown_connector_type_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "no-such-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-type"
    assert "no-such-type" in diags[0].message


def test_missing_plug_node_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-plug"


# ---------------------------------------------------------------- devices


def test_device_bus_membership_by_parentage(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.name == "dev"
    assert dev.label == "dev1"
    assert dev.bus == "i2c"
    assert dev.group is None
    assert dev.reg == 0x50
    assert dev.compatible == "vnd,thing"


def test_device_in_a_non_bus_group_gets_the_group_name(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tgpio {
\t\t\t\tbtn: button {
\t\t\t\t\tgpios = <&plug 0 1>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.bus is None
    assert dev.group == "gpio"


def test_unrecognized_bus_proxy_group_is_rejected(tmp_path) -> None:
    """A group named like a bus (i2c/spi/uart) that the plug binding does
    NOT allow as a proxy (rigc-r3-brief.md's lang-shield-proxy -- no
    frozen golden, hand-differential rule)."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tuart {
\t\t\t\tdev1: dev@1 { compatible = "vnd,thing"; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"


def test_declared_params_from_shield_params(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 {
\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\treg = <0x50>;
\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.declared_params == ["vnd,threshold"]
    assert dev.extra_props == [("compatible", 'compatible = "vnd,thing";')]


def test_declared_param_includes_from_shield_param_includes(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 {
\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\treg = <0x50>;
\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t\tshield,param-includes = "vnd/threshold.h";
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.declared_param_includes == ["vnd/threshold.h"]
    # excluded from the passthrough allowlist -- it is a rigc-only
    # vocabulary declaration, never a real DTS property to render.
    assert dev.extra_props == [("compatible", 'compatible = "vnd,thing";')]


def test_authored_default_shows_up_in_extra_props(tmp_path) -> None:
    """A declared param WITH an authored default is OPTIONAL: its name
    appears among extra_props too -- the invariant check's own "may be
    omitted" signal."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 {
\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\treg = <0x50>;
\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t\tvnd,threshold = <10>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    names = [n for n, _ in dev.extra_props]
    assert "vnd,threshold" in names


def test_addr_authority_rejects_both_reg_and_addr_from(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tconfig {
\t\t\t\taddr_strap: addr-strap {
\t\t\t\t\tshield,domain = <0x48 0>, <0x49 1>;
\t\t\t\t};
\t\t\t};
\t\t\ti2c {
\t\t\t\tdev1: dev@50 {
\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\treg = <0x50>;
\t\t\t\t\tshield,addr-from = <&addr_strap>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-addr-authority"
    assert "both" in diags[0].message


def test_addr_authority_rejects_neither_reg_nor_addr_from(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-addr-authority"
    assert "neither" in diags[0].message


def test_addr_from_must_point_at_a_strap(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 {
\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\tshield,addr-from = <&plug>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags[0].code == "lang-addr-from"


def test_unit_address_must_match_authored_reg(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@51 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-unit-addr"
    assert "!=" in diags[0].message


def test_symbolic_unit_address_with_authored_reg_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tdev1: dev@symbolic { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-unit-addr"
    assert "symbolic markers are for deferred" in diags[0].message


# ---------------------------------------------------------------- pads/straps/jumpers


def test_pads_straps_jumpers_and_lookup_helpers(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tpads {
\t\t\t\tsq: sq { shield,role = "driver"; };
\t\t\t};
\t\t\tconfig {
\t\t\t\taddr_strap: addr-strap {
\t\t\t\t\tshield,domain = <0x48 0>, <0x49 1>;
\t\t\t\t\tshield,sheet-label = "ADDR";
\t\t\t\t};
\t\t\t\tirq_jmp: irq-jmp {
\t\t\t\t\t#gpio-cells = <1>;
\t\t\t\t\tshield,position-domain = <0 0>, <1 1>;
\t\t\t\t\tshield,sheet-label = "IRQ";
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags == []
    shield = shields["fx"]
    assert isinstance(shield.pads["sq"], Pad)
    assert shield.pads["sq"].role == "driver"
    assert isinstance(shield.straps["addr-strap"], Strap)
    assert shield.straps["addr-strap"].domain == [(0x48, 0), (0x49, 1)]
    assert isinstance(shield.jumpers["irq-jmp"], Jumper)
    assert shield.jumpers["irq-jmp"].domain == [(0, 0), (1, 1)]
    assert shield.jumpers["irq-jmp"].positions() == [0, 1]
    assert shield.jumpers["irq-jmp"].state_of(1) == 1
    assert shield.jumpers["irq-jmp"].state_of(99) is None

    assert shield.config_element("addr-strap") is shield.straps["addr-strap"]
    assert shield.config_element("irq-jmp") is shield.jumpers["irq-jmp"]
    assert shield.config_element("no-such") is None

    assert shield.by_name("sq") == [shield.pads["sq"]]
    assert shield.by_name("no-such") == []
    assert shield.names() == sorted(["sq", "addr-strap"])


def test_invalid_pad_role_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tpads {
\t\t\t\tsq: sq { shield,role = "nonsense"; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-pad-role"


# ---------------------------------------------------------------- position refs


def test_gpio_position_ref_on_the_plug(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 0 3>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    ref = dev.gpio_refs[0]
    assert ref.position == 0
    assert ref.flags == 3
    assert ref.function == "gpio"
    assert ref.jumper is None


def test_gpio_position_ref_deferred_to_a_jumper(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tconfig {
\t\t\t\tirq_jmp: irq-jmp {
\t\t\t\t\t#gpio-cells = <1>;
\t\t\t\t\tshield,position-domain = <0 0>, <1 1>;
\t\t\t\t};
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&irq_jmp 1>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    ref = shields["fx"].devices[0].gpio_refs[0]
    assert ref.position is None
    assert ref.jumper == "irq-jmp"
    assert ref.flags == 1


def test_position_ref_must_target_the_plug_or_a_jumper(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tother: other@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&other 0 1>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-pos-ref"
    assert "must reference THIS shield's plug node" in diags[0].message


def test_position_index_must_exist_on_the_connector_type(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 99 1>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-position"
    assert "does not exist" in diags[0].message


def test_position_must_be_claimable_not_bus_copper(tmp_path) -> None:
    """index 2 (BUS_COPPER) exists on the header but is not a claimable
    plug,positions entry -- electrical realization is not modeled."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 2 1>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-position"
    assert "bus copper" in diags[0].message


# ---------------------------------------------------------------- exposed sockets


def test_exposed_socket_pass_through(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tmb1 {
\t\t\t\tcompatible = "socket,mikrobus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 1 0>;
\t\t\t\tsocket,i2c = <&plug>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["mb1"]
    assert exp.type_name == "mikrobus"
    assert exp.gpio_map == {0: (1, 0)}
    assert exp.buses["i2c"] == "plug"


def test_exposed_socket_new_scope_on_a_device(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\ti2c {
\t\t\t\tmux: mux@70 { compatible = "vnd,mux"; reg = <0x70>; };
\t\t\t};
\t\t\tch0 {
\t\t\t\tcompatible = "socket,i2c-port";
\t\t\t\tsocket,i2c = <&mux>;
\t\t\t\tshield,channel = <0>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["ch0"]
    assert exp.buses["i2c"] == ("scope", "mux")
    assert exp.channel == 0


def test_exposed_socket_bus_prop_must_be_plug_or_device(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { #gpio-cells = <2>; };
\t\t\tpads {
\t\t\t\tsq: sq { };
\t\t\t};
\t\t\tch0 {
\t\t\t\tcompatible = "socket,i2c-port";
\t\t\t\tsocket,i2c = <&sq>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
