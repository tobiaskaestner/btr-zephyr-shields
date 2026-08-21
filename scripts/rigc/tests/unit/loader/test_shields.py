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
from rigc.loader.shields import parse_shields

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
    cs_pool={},
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t};
""")
    assert diags == []
    assert set(shields) == {"fx"}
    shield = shields["fx"]
    assert shield.name == "fx"
    assert shield.label == "fx"
    assert shield.plugs == {"plug": "fixture-type"}


def test_unknown_connector_type_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "no-such-type";
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-type"
    assert "no-such-type" in diags[0].message


def test_missing_plug_node_is_rejected(tmp_path) -> None:
    """A template with no plug node at all: the plug is the position
    reference frame, and it is where a shield names its connector type."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-plug"
    assert "shield,plug" in diags[0].message
    assert shields["fx"].plugs == {}


def test_template_level_shield_plugs_is_retired(tmp_path) -> None:
    """The retired single form -- `shield,plugs` on the TEMPLATE node --
    is refused, and the message says where the property moved
    (plug-unification-brief.md). It must FAIL rather than read as a
    device group named `plug`, which is what silently dropped every
    nested group before unification."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tshield,plugs = "fixture-type";
\t\t\tplug: plug { };
\t\t\ti2c {
\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-plug"
    assert "retired" in diags[0].message
    assert shields["fx"].plugs == {}
    assert shields["fx"].devices == []


# ---------------------------------------------------------------- devices


def test_device_bus_membership_by_parentage(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
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


def test_device_bus_membership_by_a_qualified_named_bus_proxy(tmp_path) -> None:
    """A multi-bus connector type names an additional bus of a kind by
    suffixing the kind with a role (bus_proxies, an open string list, is
    already wide enough for this -- shields.py needs no code change to
    recognize one: a device group node literally named "spi-motors"
    matches it exactly as "spi"/"i2c" match today)."""
    named_type = ConnectorType(
        name="fixture-multibus", positions={}, index2name={},
        bus_proxies=["spi-sensors", "spi-motors"], stackable=False, cs_pool={})
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-multibus";

\t\t\t\tspi-motors {
\t\t\t\t\tdrv: drv8825@0 { compatible = "vnd,motor-driver"; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, {"fixture-multibus": named_type})

    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.bus == "spi-motors"
    assert dev.group is None


def test_device_in_a_non_bus_group_gets_the_group_name(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\tuart {
\t\t\t\t\tdev1: dev@1 { compatible = "vnd,thing"; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"


def test_unrecognized_qualified_bus_proxy_group_is_rejected(tmp_path) -> None:
    """A ROLE-QUALIFIED group name ("spi-nonexistent-role") that still
    names a recognized kind (spi) but is NOT in this connector type's own
    bus_proxies vocabulary must raise lang-shield-proxy exactly like an
    unqualified name does -- the kind-prefix check that recognizes
    "spi-nonexistent-role" as bus-shaped at all must not stop at the
    three bare kind names."""
    named_type = ConnectorType(
        name="fixture-multibus", positions={}, index2name={},
        bus_proxies=["spi-sensors", "spi-motors"], stackable=False, cs_pool={})
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-multibus";

\t\t\t\tspi-nonexistent-role {
\t\t\t\t\tdev1: dev@0 { compatible = "vnd,thing"; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, {"fixture-multibus": named_type})

    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"
    dev = shields["fx"].devices[0]
    assert dev.bus is None
    assert dev.group == "spi-nonexistent-role"


def test_declared_params_from_shield_params(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\treg = <0x50>;
\t\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\treg = <0x50>;
\t\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t\t\tshield,param-includes = "vnd/threshold.h";
\t\t\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\treg = <0x50>;
\t\t\t\t\t\tshield,params = "vnd,threshold";
\t\t\t\t\t\tvnd,threshold = <10>;
\t\t\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\treg = <0x50>;
\t\t\t\t\t\tshield,addr-from = <&addr_strap>;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};
\t\t\tconfig {
\t\t\t\taddr_strap: addr-strap {
\t\t\t\t\tshield,domain = <0x48 0>, <0x49 1>;
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-addr-authority"
    assert "neither" in diags[0].message


def test_addr_authority_rule_applies_to_a_qualified_named_i2c_bus(tmp_path) -> None:
    """The address-authority rule (exactly one of reg / shield,addr-from)
    is a fact of the I2C KIND, not of the bare string "i2c" -- a device
    on a role-suffixed i2c bus a multi-bus connector type offers
    ("i2c-sensors") must be checked exactly like a device on bare "i2c",
    never silently skipped because the literal string differs."""
    named_type = ConnectorType(
        name="fixture-multibus", positions={}, index2name={},
        bus_proxies=["i2c-sensors"], stackable=False, cs_pool={})
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-multibus";

\t\t\t\ti2c-sensors {
\t\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, {"fixture-multibus": named_type})

    assert len(diags) == 1
    assert diags[0].code == "lang-addr-authority"
    assert "neither" in diags[0].message
    assert shields["fx"].devices[0].bus == "i2c-sensors"


def test_addr_from_must_point_at_a_strap(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\tshield,addr-from = <&plug>;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert diags[0].code == "lang-addr-from"


def test_unit_address_must_match_authored_reg(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@51 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-unit-addr"
    assert "!=" in diags[0].message


def test_symbolic_unit_address_with_authored_reg_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@symbolic { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-unit-addr"
    assert "symbolic markers are for deferred" in diags[0].message


# ---------------------------------------------------------------- pads/straps/jumpers


def test_pads_straps_jumpers_and_lookup_helpers(tmp_path) -> None:
    """`config_element`/`by_name`/`names()` all resolve by DTS LABEL
    (item 29), never by node name -- exercised here via `addr_strap`/
    `addr-strap` and `irq_jmp`/`irq-jmp`, which deliberately differ (the
    real corpus's own naming convention), so a same-spelling coincidence
    can never hide a label-vs-name bug."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
    assert shield.straps["addr-strap"].label == "addr_strap"
    assert shield.straps["addr-strap"].domain == [(0x48, 0), (0x49, 1)]
    assert isinstance(shield.jumpers["irq-jmp"], Jumper)
    assert shield.jumpers["irq-jmp"].label == "irq_jmp"
    assert shield.jumpers["irq-jmp"].domain == [(0, 0), (1, 1)]
    assert shield.jumpers["irq-jmp"].positions() == [0, 1]
    assert shield.jumpers["irq-jmp"].state_of(1) == 1
    assert shield.jumpers["irq-jmp"].state_of(99) is None

    # by LABEL resolves; the node name (the pre-item-29 spelling) is
    # REJECTED outright, never a fallback.
    assert shield.config_element("addr_strap") is shield.straps["addr-strap"]
    assert shield.config_element("addr-strap") is None
    assert shield.config_element("irq_jmp") is shield.jumpers["irq-jmp"]
    assert shield.config_element("irq-jmp") is None
    assert shield.config_element("no-such") is None

    assert shield.by_name("sq") == [shield.pads["sq"]]
    assert shield.by_name("addr_strap") == [shield.straps["addr-strap"]]
    assert shield.by_name("addr-strap") == []
    assert shield.by_name("no-such") == []
    assert shield.names() == sorted(["sq", "addr_strap"])


def test_unlabeled_device_is_a_loud_error(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-label"
    assert "device 'dev@50'" in diags[0].message
    assert "fx" in diags[0].message
    assert "no DTS label" in diags[0].message


def test_unlabeled_pad_is_a_loud_error(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tpads {
\t\t\t\tsq { shield,role = "driver"; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-label"
    assert "pad 'sq'" in diags[0].message
    assert "no DTS label" in diags[0].message


def test_unlabeled_strap_is_a_loud_error(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tconfig {
\t\t\t\taddr-strap {
\t\t\t\t\tshield,domain = <0x48 0>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-label"
    assert "strap 'addr-strap'" in diags[0].message
    assert "no DTS label" in diags[0].message


def test_unlabeled_jumper_is_a_loud_error(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tconfig {
\t\t\t\tirq-jmp {
\t\t\t\t\t#gpio-cells = <1>;
\t\t\t\t\tshield,position-domain = <0 0>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-label"
    assert "jumper 'irq-jmp'" in diags[0].message
    assert "no DTS label" in diags[0].message


def test_unlabeled_exposed_socket_is_a_loud_error(tmp_path) -> None:
    """The fourth (and last) rig-facing reference surface (item 30) --
    `_parse_exposed` used to fall back to the node name silently, same as
    devices/pads/straps/jumpers did before item 29; now it goes through
    the same `_require_label` helper they do."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tmb1 {
\t\t\t\tcompatible = "socket,mikrobus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tsocket,i2c = <&plug>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-label"
    assert "exposed socket 'mb1'" in diags[0].message
    assert "fx" in diags[0].message
    assert "no DTS label" in diags[0].message


def test_exposed_socket_label_is_the_naming_authority(tmp_path) -> None:
    """`Shield.exposed_socket` resolves by DTS LABEL, never by node name
    -- exercised with a label that DIFFERS from the node name (`span_ch0`
    labelling `ch0`), since the real corpus's own 8 exposed nodes all
    happen to share the two spellings and so cannot show which one
    actually resolves."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tspan_ch0: ch0 {
\t\t\t\tcompatible = "socket,mikrobus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tsocket,i2c = <&plug>;
\t\t\t};
\t\t};
""")
    assert diags == []
    shield = shields["fx"]
    assert shield.exposes["ch0"].label == "span_ch0"
    assert shield.exposed_socket("span_ch0") is shield.exposes["ch0"]
    assert shield.exposed_socket("ch0") is None
    assert shield.exposed_socket("no-such") is None


def test_invalid_pad_role_is_rejected(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 0 3>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    dev = shields["fx"].devices[0]
    ref = dev.function_refs[0]
    assert ref.position == 0
    assert ref.flags == 3
    assert ref.function == "gpio"
    assert ref.jumper is None


def test_gpio_position_ref_deferred_to_a_jumper(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
    ref = shields["fx"].devices[0].function_refs[0]
    assert ref.position is None
    assert ref.jumper == "irq-jmp"
    assert ref.flags == 1


def test_position_ref_must_target_the_plug_or_a_jumper(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tother: other@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tmb1: mb1 {
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
    assert exp.gpio_map == {0: ("plug", 1, 0)}
    assert exp.buses["i2c"] == ("plug", "plug")


def test_exposed_socket_cs_pool_qualified_and_bare_both_parse(tmp_path) -> None:
    """Sec 2: a bare socket,cs-pool override lands in the "spi" entry
    (byte-identical meaning to the old flat-list shape); a qualified
    socket,<kind>-<role>-cs-pool lands under its OWN qualified key --
    mirrors board/project.py's/registry.py's own _CS_POOL_PROP_RE."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tmb1: mb1 {
\t\t\t\tcompatible = "socket,fixture-multibus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tsocket,cs-pool = <3 4>;
\t\t\t\tsocket,spi-sensors-cs-pool = <5 6>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["mb1"]
    assert exp.cs_pool == {"spi": [3, 4], "spi-sensors": [5, 6]}


def test_exposed_socket_new_scope_on_a_device(tmp_path) -> None:
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tmux: mux@70 { compatible = "vnd,mux"; reg = <0x70>; };
\t\t\t\t};
\t\t\t};
\t\t\tch0: ch0 {
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
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tpads {
\t\t\t\tsq: sq { };
\t\t\t};
\t\t\tch0: ch0 {
\t\t\t\tcompatible = "socket,i2c-port";
\t\t\t\tsocket,i2c = <&sq>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"


# --------------------------------------- exposed sockets: pwm/adc pass-through
# (carrier-analog-passthrough-brief.md Sec 5)


def test_exposed_socket_pwm_and_adc_pass_through(tmp_path) -> None:
    """pwm-map/io-channel-map parse the SAME way gpio-map already does --
    slot-widened (parent SLOT, parent plug position, filler) -- and each
    map's own declared cell count is captured for compose_socket's
    require-and-check (Sec 3c/Sec 5 RULED)."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\t#pwm-cells = <2>;
\t\t\t\tpwm-map = <0 0 &plug 0 0 0>;
\t\t\t\t#io-channel-cells = <1>;
\t\t\t\tio-channel-map = <0 &plug 0>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["ao"]
    assert exp.pwm_cells == 2
    assert exp.pwm_map == {0: ("plug", 0, 0)}
    assert exp.adc_cells == 1
    assert exp.adc_map == {0: ("plug", 0, 0)}


def test_exposed_socket_pwm_map_two_rows(tmp_path) -> None:
    """Multi-row stride derivation: TWO pwm-map rows parse to two entries,
    proving the derived (not hardcoded) stride advances `i` correctly."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>, <1 0 &plug 1 0>;
\t\t\t\t#pwm-cells = <2>;
\t\t\t\tpwm-map = <0 0 &plug 0 0 0>, <1 0 &plug 1 0 0>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["ao"]
    assert exp.pwm_map == {0: ("plug", 0, 0), 1: ("plug", 1, 0)}


def test_exposed_socket_pwm_map_without_pwm_cells_is_rejected(tmp_path) -> None:
    """RULED require-and-check: a pwm-map with no #pwm-cells alongside it
    is a parse-time lang-exposed error, not a guess at the stride."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\tpwm-map = <0 0 &plug 0 0>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "#pwm-cells" in diags[0].message
    exp = shields["fx"].exposes["ao"]
    assert exp.pwm_map == {}
    assert exp.pwm_cells is None


def test_exposed_socket_pwm_cells_without_pwm_map_is_rejected(tmp_path) -> None:
    """The reverse pairing (Sec 5: 'so is the reverse pairing if it is
    cheap to detect') is equally a parse-time lang-exposed error."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\t#pwm-cells = <2>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "pwm-map" in diags[0].message


def test_exposed_socket_io_channel_map_without_cells_is_rejected(tmp_path) -> None:
    """Same require-and-check, ADC side (#io-channel-cells / io-channel-map)."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\tio-channel-map = <0 &plug 0>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "#io-channel-cells" in diags[0].message
    exp = shields["fx"].exposes["ao"]
    assert exp.adc_map == {}
    assert exp.adc_cells is None


def test_exposed_socket_pwm_map_parent_must_be_a_plug(tmp_path) -> None:
    """Mirrors gpio-map's own parent-must-be-a-plug check (lang-exposed) --
    a pwm-map row pointing at anything else (here, a pad, which declares
    no #pwm-cells of its own -- so the row's parent side is read at the
    3-cell generic Zephyr default, _FUNCTION_DEFAULT_CELLS) is rejected
    the same way."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tpads {
\t\t\t\tsq: sq { };
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\t#pwm-cells = <2>;
\t\t\t\tpwm-map = <0 0 &sq 0 0 0>;
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "pwm-map parent must be" in diags[0].message


def test_exposed_socket_pwm_map_stride_from_a_three_cell_plug(tmp_path) -> None:
    """The plug's OWN declared #pwm-cells drives the PARENT half of the
    stride (mirroring _parse_pos_ref's own _ncells(target, function)
    lookup) -- a 3-cell plug makes each row 6 words (2 child + phandle +
    3 parent), never the 5 a 2-cell plug needs, so this must still parse
    (not truncate) when the plug declares 3."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tao: ao {
\t\t\t\tcompatible = "socket,grove";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &plug 0 0>;
\t\t\t\t#pwm-cells = <2>;
\t\t\t\tpwm-map = <0 0 &plug 0 0 0>;
\t\t\t};
\t\t};
""")
    assert diags == []
    exp = shields["fx"].exposes["ao"]
    assert exp.pwm_map == {0: ("plug", 0, 0)}
    assert exp.pwm_cells == 2


# ---------------------------------------------------------------- plural plugs (multi-plug-shield-brief.md)

# A second connector type distinct from _PLUG_TYPE, so a two-slot shield
# naming one of each proves per-slot resolution against genuinely
# different types, never accidentally sharing one ConnectorType object.
_PLUG_TYPE_2 = ConnectorType(
    name="fixture-type-2",
    positions={"Q0": Position(name="Q0", index=0, function="gpio")},
    index2name={0: "Q0"},
    bus_proxies=["i2c"],
    stackable=True,
    cs_pool={},
)
_PLURAL_TYPES = {"fixture-type": _PLUG_TYPE, "fixture-type-2": _PLUG_TYPE_2}


def test_single_form_device_plug_defaults_to_the_default_slot(tmp_path) -> None:
    """Single form normalizes to one slot, literally named 'plug' -- every
    device (bus or plain) records it, not just bus devices, since there
    is only one plug to belong to."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";

\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t\t};
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 0 1>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    shield = shields["fx"]
    assert shield.plugs == {"plug": "fixture-type"}
    bus_dev = next(d for d in shield.devices if d.name == "dev")
    plain_dev = next(d for d in shield.devices if d.name == "button")
    assert bus_dev.plug == "plug"
    assert plain_dev.plug == "plug"
    assert plain_dev.function_refs[0].plug == "plug"


def test_plural_shield_two_plugs_and_bus_membership(tmp_path) -> None:
    """The can_span_click shape: two plugs of the SAME connector type,
    each with its own bus group nested under it -- the plug node NAME is
    the slot, and each bus device records its OWN plug's slot."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\ti2c {
\t\t\t\t\tdev_l: devl@10 { compatible = "vnd,thing"; reg = <0x10>; };
\t\t\t\t};
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\ti2c {
\t\t\t\t\tdev_r: devr@20 { compatible = "vnd,thing"; reg = <0x20>; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    shield = shields["fx"]
    assert shield.plugs == {"left": "fixture-type", "right": "fixture-type"}
    dev_l = next(d for d in shield.devices if d.name == "devl")
    dev_r = next(d for d in shield.devices if d.name == "devr")
    assert dev_l.plug == "left"
    assert dev_r.plug == "right"


def test_plural_shield_cross_plug_gpio_ref_records_the_named_plug(tmp_path) -> None:
    """Ruling 2 (per-reference granularity): a device on the LEFT plug's
    bus may still carry a gpio ref naming the RIGHT plug -- the phandle
    widens from "must be THIS shield's plug" to "one of this shield's
    plugs", and FunctionRef.plug records which one, independent of the
    device's own bus slot."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\tspi {
\t\t\t\t\tdevl: devl { compatible = "vnd,thing";
\t\t\t\t\t\tint-gpios = <&right_plug 0 1>;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.plug == "left"          # the device's OWN bus slot
    ref = dev.function_refs[0]
    assert ref.plug == "right"         # the CROSS-PLUG reference's own slot
    assert ref.position == 0


def test_plural_shield_two_different_connector_types(tmp_path) -> None:
    """The acq_bridge shape: two plugs of DIFFERENT connector types."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tard: ard {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tmb: mb {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type-2";
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    assert shields["fx"].plugs == {"ard": "fixture-type", "mb": "fixture-type-2"}


def test_plural_shield_unknown_connector_type_on_one_plug(tmp_path) -> None:
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "no-such-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-type"
    assert "left" in diags[0].message
    assert "no-such-type" in diags[0].message


def test_plain_group_device_is_plug_agnostic_in_the_plural_form(tmp_path) -> None:
    """Sec 2 placement rule: a plain (non-bus) device group stays
    template-level in a plural shield, and its device is plug-AGNOSTIC
    (plug is None) -- its own refs each carry their own plug instead."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&left_plug 0 1>; };
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    dev = shields["fx"].devices[0]
    assert dev.bus is None
    assert dev.plug is None
    assert dev.group == "gpio"
    assert dev.function_refs[0].plug == "left"


def test_one_plug_is_the_same_form_as_many(tmp_path) -> None:
    """There is ONE authored form: a shield with a single plug declares it
    exactly as a shield with two does, and its slot name is that node's
    own name (plug-unification-brief.md). This is the shape every migrated
    corpus shield now has."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type-2";
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&left_plug 0 1>; };
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    assert shields["fx"].plugs == {"left": "fixture-type-2"}
    # a plain-group device is attributed to the ONE plug by its own slot
    # name -- never to the literal "plug" the retired form hardcoded
    assert shields["fx"].devices[0].plug == "left"


def test_a_plug_node_may_be_named_plug_beside_another(tmp_path) -> None:
    """`plug` is an ordinary slot NAME -- conventional for a shield with
    one, reserved for nothing. The rule that refused it existed only to
    keep the two retired forms apart."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    assert shields["fx"].plugs == {"plug": "fixture-type",
                                   "right": "fixture-type"}


def test_plural_shield_template_level_bus_group_is_rejected(tmp_path) -> None:
    """Sec 2 placement rule: a plural shield's bus groups must nest under
    their owning plug -- a bus-shaped group at TEMPLATE level is a loud
    lang-shield-proxy error naming the candidate plugs."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\ti2c {
\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"
    assert "template level" in diags[0].message
    assert "left" in diags[0].message and "right" in diags[0].message


def test_plural_shield_plain_group_nested_under_a_plug_is_rejected(tmp_path) -> None:
    """The reverse of the template-level case above: a plain (non-bus,
    not even bus-kind-named) group nested UNDER a plug is not a bus this
    plug's ctype could ever allow, so it is rejected -- reviewer finding
    4. Before this fix it was silently accepted, recording Device.plug =
    slot and contradicting the invariant that a plain-group device is
    plug-agnostic (plug is None)."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\tgpio {
\t\t\t\t\tbtn: button { gpios = <&left_plug 0 1>; };
\t\t\t\t};
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"
    assert ("plug 'left' has a 'gpio' group nested under it -- plain "
           "device groups belong at template level" in diags[0].message)
    assert shields["fx"].devices[0].plug is None


# ------------------------------------------- the placement rule at ONE plug
# The same three laws as above, at a plug count of one -- the case the
# retired single form inverted (bus groups as SIBLINGS of `plug`), which is
# why a nested group was silently dropped instead of parsed
# (plug-unification-brief.md Sec 1).


def test_one_plug_template_level_bus_group_is_rejected(tmp_path) -> None:
    """The retired single form's OWN spelling, now refused: a bus group
    beside the plug rather than under it. The message names the plug it
    should have nested under."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\ti2c {
\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>; };
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"
    assert "template level" in diags[0].message
    assert "candidate plugs: plug" in diags[0].message


def test_one_plug_nested_plain_group_is_rejected(tmp_path) -> None:
    """And the reverse, at one plug: a plain group stays at template
    level whatever the count, so nesting one is refused rather than
    silently attributed to the plug."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\tgpio {
\t\t\t\t\tbtn: button { gpios = <&plug 0 1>; };
\t\t\t\t};
\t\t\t};
\t\t};
""")
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-proxy"
    assert "belong at template level" in diags[0].message


def test_one_plug_nested_bus_group_parses_its_devices(tmp_path) -> None:
    """The positive half, and the whole point of the slice: the nested
    spelling PARSES at one plug. Before unification this produced zero
    devices and zero diagnostics -- the plug node's children were never
    visited at all, because its NAME was reserved."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\ti2c {
\t\t\t\t\tdev1: dev@50 { compatible = "vnd,thing"; reg = <0x50>;
\t\t\t\t\t\tint-gpios = <&plug 0 1>; };
\t\t\t\t};
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 1 0>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    devs = {d.name: d for d in shields["fx"].devices}
    assert set(devs) == {"dev", "button"}
    assert devs["dev"].bus == "i2c"
    assert devs["dev"].plug == "plug"
    assert [(r.prop, r.position) for r in devs["dev"].function_refs] == [
        ("int-gpios", 0)]
    # the plain-group device is attributed to the ONLY plug, not to the
    # literal name "plug" -- the retired single form hardcoded the latter
    assert devs["button"].bus is None
    assert devs["button"].group == "gpio"
    assert devs["button"].plug == "plug"


# ------------------------------------------------------ cells on a plug node


def test_cells_on_a_plug_node_are_rejected(tmp_path) -> None:
    """A plug declares no cell counts: every value the corpus ever gave
    one restated _FUNCTION_DEFAULT_CELLS, the node is never emitted so
    nothing validated it, and a wrong value silently changed a
    reference's arity (plug-unification-brief.md Sec 5). One diagnostic
    per property, each naming the property."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\t#pwm-cells = <3>;
\t\t\t\t#io-channel-cells = <1>;
\t\t\t};
\t\t};
""")
    assert [d.code for d in diags] == ["lang-shield-plug-cells"] * 3
    assert {"#gpio-cells", "#pwm-cells", "#io-channel-cells"} == {
        w for d in diags for w in d.message.split() if w.startswith("#")}


def test_a_reference_through_a_plug_uses_the_generic_cell_count(tmp_path) -> None:
    """The counterpart: with no declaration to read, a claim through the
    plug carries the generic count for its function -- 2 for gpio, which
    is what every stripped corpus declaration said."""
    shields, diags = _one_shield(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tgpio {
\t\t\t\tbtn: button { gpios = <&plug 0 1>, <&plug 1 0>; };
\t\t\t};
\t\t};
""")
    assert diags == []
    refs = shields["fx"].devices[0].function_refs
    assert [(r.position, r.flags) for r in refs] == [(0, 1), (1, 0)]


def test_plural_shield_routing_jumper_is_rejected(tmp_path) -> None:
    """Sec 4/6: routing jumpers have no plug axis, so a plural shield
    declaring one is refused outright this slice."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tconfig {
\t\t\t\tirq_jmp: irq-jmp {
\t\t\t\t\t#gpio-cells = <1>;
\t\t\t\t\tshield,position-domain = <0 0>, <1 1>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-plurality"
    assert "jumper" in diags[0].message
    assert shields["fx"].jumpers == {}


def test_plural_shield_exposed_socket_mixed_parents(tmp_path) -> None:
    """multi-plug-carrier-brief.md Sec 1 ruling 1: a plural shield MAY
    declare an exposed socket -- each gpio-map row and each socket,<bus>
    resolves through ONE of the carrier's plugs, and the marker/tuple
    RECORDS which one, exactly like the single-plug form's own "plug"
    slot does."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tcombined: combined {
\t\t\t\tcompatible = "socket,mikrobus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &left_plug 0 0>,
\t\t\t\t\t   <1 0 &right_plug 1 0>;
\t\t\t\tsocket,i2c = <&right_plug>;
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    exp = shields["fx"].exposes["combined"]
    assert exp.gpio_map == {0: ("left", 0, 0), 1: ("right", 1, 0)}
    assert exp.buses["i2c"] == ("plug", "right")


def test_plural_shield_exposed_socket_gpio_map_parent_must_be_a_plug(tmp_path) -> None:
    """A gpio-map row's phandle must name one of the carrier's OWN plugs
    -- naming any other node of the shield is rejected, worded to list
    the carrier's plugs (plural) rather than the singular single-plug
    wording."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tpads {
\t\t\t\tsq: sq { };
\t\t\t};
\t\t\tcombined: combined {
\t\t\t\tcompatible = "socket,mikrobus";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tgpio-map = <0 0 &sq 0 0>;
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "one of the carrier's plugs" in diags[0].message
    assert shields["fx"].exposes["combined"].gpio_map == {}


def test_exposed_socket_qualified_bus_name_the_type_does_not_declare_is_rejected(tmp_path) -> None:
    """Sec 2: the child-side qualified bus name is validated exact-match
    against the exposed type's OWN declared bus_proxies, no fallback --
    "spi" is not among fixture-type-2's own vocabulary (i2c only)."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tplug: plug {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tch0: ch0 {
\t\t\t\tcompatible = "socket,fixture-type-2";
\t\t\t\t#gpio-cells = <2>;
\t\t\t\tsocket,spi = <&plug>;
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert len(diags) == 1
    assert diags[0].code == "lang-exposed"
    assert "does not declare" in diags[0].message
    assert shields["fx"].exposes["ch0"].buses == {}


def test_plural_shield_straps_are_unaffected_template_level_facts(tmp_path) -> None:
    """Straps (address-domain, bus-scoped) are NOT refused on a plural
    shield -- only routing jumpers are (Sec 4)."""
    dt = _dt(tmp_path, """
\t\tfx: fx {
\t\t\tleft_plug: left {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t\ti2c {
\t\t\t\t\tdevl: devl@addr_strap {
\t\t\t\t\t\tcompatible = "vnd,thing";
\t\t\t\t\t\tshield,addr-from = <&addr_strap>;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};
\t\t\tright_plug: right {
\t\t\t\tcompatible = "shield,plug";
\t\t\t\tshield,plugs = "fixture-type";
\t\t\t};
\t\t\tconfig {
\t\t\t\taddr_strap: addr-strap {
\t\t\t\t\tshield,domain = <0x48 0>, <0x49 1>;
\t\t\t\t};
\t\t\t};
\t\t};
""")
    shields, diags = parse_shields(dt, _PLURAL_TYPES)
    assert diags == []
    assert "addr-strap" in shields["fx"].straps
