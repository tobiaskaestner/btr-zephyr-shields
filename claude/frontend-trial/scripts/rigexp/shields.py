"""Shield parsing: /rig-shields subtree -> model.Shield. Shared by BOTH
loaders (the candidates differ only in the rig topology file; shield
payloads are DTS either way). Loader-side validation done here:

  - shield,plugs names a known connector type
  - bus proxy nodes are allowed by the plug binding (Conv. 1)
  - position references target THIS shield's plug and exist in the type
  - exactly one of reg / shield,addr-from on addressable-bus devices
    (forgot-vs-deferred, pushback round 3)
  - authored reg matches the unit-address; symbolic unit-addresses are
    linted against the addr-from target
"""
from __future__ import annotations

from .diag import Diagnostics, SrcRef
from .dtsio import dtlib, render_prop, src_of, words
from .model import (ConnectorType, Device, ExposedSocket, GpioRef, Jumper,
                    Pad, Shield, Strap)

_BUS_PROPS = {"socket,i2c": "i2c", "socket,spi": "spi", "socket,uart": "uart"}

_RESERVED = {"plug", "pads", "config"}
_ADDRESSABLE = {"i2c"}          # buses with device-static in-band addressing
_MODEL_PROPS = {"reg", "compatible", "shield,addr-from", "shield,cs-position",
                "shield,collect"}


def parse_shields(dt: dtlib.DT, types: dict[str, ConnectorType],
                  diags: Diagnostics) -> dict[str, Shield]:
    shields: dict[str, Shield] = {}
    root = dt.root.nodes.get("rig-shields")
    if root is None:
        return shields
    for node in root.nodes.values():
        shield = _parse_shield(node, types, diags)
        shields[shield.name] = shield
    return shields


def _parse_shield(node: dtlib.Node, types, diags) -> Shield:
    shield = Shield(
        name=node.name,
        label=node.labels[0] if node.labels else node.name,
        plugs=node.props["shield,plugs"].to_string(),
        src=src_of(node))
    shield.by_path[node.path] = shield

    ctype = types.get(shield.plugs)
    if ctype is None:
        diags.error(
            "lang-shield-type",
            f"shield '{shield.name}' plugs unknown connector type '{shield.plugs}'\n"
            f"known types: {', '.join(sorted(types))}",
            [src_of(node.props["shield,plugs"])])

    plug = node.nodes.get("plug")
    if plug is None:
        diags.error("lang-shield-plug",
                    f"shield '{shield.name}' has no plug node — the plug is the "
                    "position reference frame (Conv. 2)", [src_of(node)])

    # two-phase: pads/config first — devices reference straps (shield,addr-from)
    # regardless of group order in the file
    for group in node.nodes.values():
        if group.name == "pads":
            for pnode in group.nodes.values():
                pad = _parse_pad(pnode, diags)
                shield.pads[pad.name] = pad
                shield.by_path[pnode.path] = pad
        elif group.name == "config":
            for snode in group.nodes.values():
                if "shield,position-domain" in snode.props:
                    jmp = _parse_jumper(snode)
                    shield.jumpers[jmp.name] = jmp
                    shield.by_path[snode.path] = jmp
                else:
                    strap = _parse_strap(snode)
                    shield.straps[strap.name] = strap
                    shield.by_path[snode.path] = strap

    def is_exposed(g):
        return "compatible" in g.props and \
            g.props["compatible"].to_string().startswith("socket,")

    # device groups FIRST — an exposed socket may reference a device as its
    # scope root (S8 mux channel), so the device must be in by_path already.
    for group in node.nodes.values():
        if group.name in _RESERVED or is_exposed(group):
            continue
        bus = group.name if ctype and group.name in ctype.bus_proxies else None
        if bus is None and ctype and group.name in ("i2c", "spi", "uart"):
            diags.error(
                "lang-shield-proxy",
                f"shield '{shield.name}' has a '{group.name}' bus proxy but the "
                f"'{ctype.name}' plug binding allows only: {', '.join(ctype.bus_proxies)}",
                [src_of(group)])
        for dnode in group.nodes.values():
            dev = _parse_device(dnode, shield, plug, ctype, bus,
                                None if bus else group.name, diags)
            shield.devices.append(dev)
            shield.by_path[dnode.path] = dev

    # then re-exported sockets (R19 pass-through, or S8 scope creation)
    for group in node.nodes.values():
        if group.name in _RESERVED or not is_exposed(group):
            continue
        exp = _parse_exposed(group, plug, shield, diags)
        shield.exposes[exp.name] = exp
        shield.by_path[group.path] = exp
    return shield


def _parse_device(node, shield, plug, ctype, bus, group, diags) -> Device:
    name, _, unit = node.name.partition("@")
    compat = node.props["compatible"].to_string() if "compatible" in node.props else None

    reg = node.props["reg"].to_num() if "reg" in node.props else None
    addr_from = None
    if "shield,addr-from" in node.props:
        target = node.props["shield,addr-from"].to_node()
        strap = shield.by_path.get(target.path)
        if not isinstance(strap, Strap):
            diags.error(
                "lang-addr-from",
                f"shield,addr-from on '{shield.name}/{node.name}' does not point at a "
                "config strap of this shield",
                [src_of(node.props["shield,addr-from"])])
        else:
            addr_from = strap.name

    # exactly-one-of rule: forgot-reg is detectable, deferred is explicit
    if bus in _ADDRESSABLE:
        if (reg is None) == (addr_from is None):
            which = "both" if reg is not None else "neither"
            diags.error(
                "lang-addr-authority",
                f"device '{shield.name}/{node.name}' on an addressable bus carries "
                f"{which} of reg / shield,addr-from — exactly one is required "
                "(address authority rule)", [src_of(node)])

    # authored reg == unit-address (validated, Conv. 2); symbolic unit-address
    # is a documentation marker linted against the addr-from target
    if unit and reg is not None:
        try:
            if int(unit, 16) != reg:
                diags.error(
                    "lang-unit-addr",
                    f"'{node.name}': unit-address @{unit} != authored reg <{reg:#x}> — "
                    "they must be a matching pair", [src_of(node)])
        except ValueError:
            diags.error("lang-unit-addr",
                        f"'{node.name}': symbolic unit-address with authored reg — "
                        "symbolic markers are for deferred addresses only",
                        [src_of(node)])
    elif unit and addr_from and unit.replace("-", "_") != addr_from.replace("-", "_"):
        diags.warning(
            "lang-unit-addr",
            f"'{node.name}': symbolic unit-address @{unit} does not match its "
            f"resolver '{addr_from}' (lint: marker must name the addr-from target)",
            [src_of(node)])

    cs_position = None
    if "shield,cs-position" in node.props:
        cs_position = node.props["shield,cs-position"].to_num()

    collect = None
    if "shield,collect" in node.props:
        collect = node.props["shield,collect"].to_string()

    dev = Device(name=name, label=node.labels[0] if node.labels else name,
                 compatible=compat, bus=bus, group=group, reg=reg,
                 addr_from=addr_from, cs_position=cs_position, collect=collect,
                 src=src_of(node))

    for prop in node.props.values():
        if prop.name in _MODEL_PROPS or prop.name == "phandle":
            continue
        fn = _function_of(prop.name)
        if fn is not None:
            dev.gpio_refs.extend(_parse_pos_ref(prop, fn, shield, plug, ctype, diags))
            continue
        if prop.type is dtlib.Type.PHANDLES_AND_NUMS:
            diags.warning(
                "lang-prop",
                f"phandle property '{prop.name}' of '{shield.name}/{node.name}' is "
                "not a recognized function ref (gpios/pwms/io-channels) — dropped",
                [src_of(prop)])
            continue
        rendered = render_prop(prop)
        if rendered is None:
            diags.warning(
                "lang-prop",
                f"property '{prop.name}' of '{shield.name}/{node.name}' has a type the "
                "prototype cannot pass through — dropped from output", [src_of(prop)])
        elif prop.name != "compatible":
            dev.extra_props.append((prop.name, rendered))
    if compat:
        dev.extra_props.insert(0, ("compatible", f'compatible = "{compat}";'))
    return dev


_FUNCTION_CELLS = {"gpio": "#gpio-cells", "pwm": "#pwm-cells", "adc": "#io-channel-cells"}
_FUNCTION_DEFAULT_CELLS = {"gpio": 2, "pwm": 3, "adc": 1}


def _function_of(prop_name: str):
    """Which function-nexus a property resolves through (Slice A). Detected by
    property name — the shield picks the function by using the standard
    property for it."""
    if prop_name == "gpios" or prop_name.endswith("-gpios"):
        return "gpio"
    if prop_name == "pwms":
        return "pwm"
    if prop_name == "io-channels":
        return "adc"
    return None


def _parse_pos_ref(prop, function, shield, plug, ctype, diags):
    """Nexus-aware position reference, per function. The plug is a
    multi-function nexus: a claim reads the plug's #<fn>-cells cells. Layout:
      gpio  <&plug POSITION flags>          (2 cells)  — or <&jumper flags> (R6)
      pwm   <&plug POSITION period flags>   (3 cells)
      adc   <&plug POSITION>                (1 cell)
    The expander resolves POSITION through the matching board map."""
    cells = words(prop)
    dt = prop.node.dt
    i = 0
    while i < len(cells):
        target = dt.phandle2node.get(cells[i])
        ncells = _ncells(target, function)
        args = cells[i + 1: i + 1 + ncells]
        i += 1 + ncells
        if target is None or len(args) < ncells:
            diags.error("lang-pos-ref",
                        f"'{prop.name}' has a malformed {function} entry",
                        [src_of(prop)])
            return

        elem = shield.by_path.get(target.path)
        if plug is not None and target.path == plug.path:      # fixed position
            pos = args[0]
            if not _valid_position(prop, pos, ctype, diags):
                continue
            if function == "gpio":
                yield GpioRef(prop=prop.name, position=pos, flags=args[1],
                              function="gpio", src=src_of(prop))
            elif function == "pwm":
                yield GpioRef(prop=prop.name, position=pos, period=args[1],
                              flags=args[2], function="pwm", src=src_of(prop))
            else:  # adc
                yield GpioRef(prop=prop.name, position=pos, flags=0,
                              function="adc", src=src_of(prop))
        elif function == "gpio" and isinstance(elem, Jumper):  # deferred position (R6)
            flags = args[0] if args else 0
            yield GpioRef(prop=prop.name, position=None, flags=flags,
                          jumper=elem.name, function="gpio", src=src_of(prop))
        else:
            where = target.path if target else "?"
            diags.error(
                "lang-pos-ref",
                f"'{prop.name}' must reference THIS shield's plug node "
                f"(fixed position, Conv. 3)"
                + ("" if function != "gpio" else " or one of its routing jumpers (R6)")
                + f" — it points at {where}",
                [src_of(prop)])


def _ncells(node, function) -> int:
    prop = _FUNCTION_CELLS[function]
    if node is not None and prop in node.props:
        return node.props[prop].to_num()
    return _FUNCTION_DEFAULT_CELLS[function]


def _valid_position(prop, pos, ctype, diags) -> bool:
    if ctype and pos not in ctype.index2name:
        diags.error("lang-position",
                    f"'{prop.name}' claims position index {pos}, which does not "
                    f"exist on connector type '{ctype.name}'", [src_of(prop)])
        return False
    if ctype and ctype.index2name[pos] not in ctype.positions:
        diags.error(
            "lang-position",
            f"'{prop.name}' claims {ctype.index2name[pos]} — bus copper, not a "
            f"claimable position of '{ctype.name}' (electrical realization is "
            "not modeled)", [src_of(prop)])
        return False
    return True


def _parse_exposed(node, plug, shield, diags) -> ExposedSocket:
    """A re-exported socket. gpio-map binds exposed positions to the carrier's
    own plug positions (pass-through, R19). socket,<bus> is either:
      <&plug>    pass through the parent's bus (S6 passive adapter), or
      <&device>  a NEW scope rooted in that device of the shield (S8 mux
                 channel) — address uniqueness is then per-scope."""
    type_name = node.props["compatible"].to_string().split(",", 1)[1]
    gpio_map = {}
    if "gpio-map" in node.props:
        cells = words(node.props["gpio-map"])
        dt = node.dt
        for i in range(0, len(cells) - len(cells) % 5, 5):
            pos, _f, phandle, parent_pos, parent_flags = cells[i:i + 5]
            target = dt.phandle2node.get(phandle)
            if plug is None or target is None or target.path != plug.path:
                diags.error(
                    "lang-exposed",
                    f"exposed socket '{node.name}': gpio-map parent must be the "
                    "carrier's plug (pass-through, R19)", [src_of(node)])
                continue
            gpio_map[pos] = (parent_pos, parent_flags)

    buses = {}
    for prop_name, kind in _BUS_PROPS.items():
        if prop_name not in node.props:
            continue
        target = node.props[prop_name].to_node()
        if plug is not None and target.path == plug.path:
            buses[kind] = "plug"                       # pass-through (S6)
        elif isinstance(shield.by_path.get(target.path), Device):
            buses[kind] = ("scope", shield.by_path[target.path].label)  # new scope (S8)
        else:
            diags.error(
                "lang-exposed",
                f"exposed socket '{node.name}': {prop_name} must be <&plug> "
                "(pass-through, R19) or <&device> (new scope, R26)", [src_of(node)])

    cs_pool = list(node.props["socket,cs-pool"].to_nums()) \
        if "socket,cs-pool" in node.props else None
    channel = node.props["shield,channel"].to_num() \
        if "shield,channel" in node.props else None
    return ExposedSocket(
        name=node.name, label=node.labels[0] if node.labels else node.name,
        type_name=type_name, gpio_map=gpio_map, buses=buses,
        cs_pool=cs_pool, channel=channel, src=src_of(node))


def _parse_pad(node, diags) -> Pad:
    role = node.props["shield,role"].to_string() if "shield,role" in node.props else "bidir"
    if role not in ("driver", "listener", "bidir"):
        diags.error("lang-pad-role",
                    f"pad '{node.name}': unknown role '{role}' "
                    "(driver / listener / bidir, R23)", [src_of(node)])
    of = None
    if "shield,of" in node.props:
        of = node.props["shield,of"].to_node().name.partition("@")[0]
    return Pad(name=node.name, label=node.labels[0] if node.labels else node.name,
               role=role, of=of, src=src_of(node))


def _parse_strap(node) -> Strap:
    dom = words(node.props["shield,domain"])
    domain = [(dom[i], dom[i + 1]) for i in range(0, len(dom), 2)]
    return Strap(name=node.name, label=node.labels[0] if node.labels else node.name,
                 domain=domain, sheet_label=_sheet_label(node), src=src_of(node))


def _parse_jumper(node) -> Jumper:
    dom = words(node.props["shield,position-domain"])
    domain = [(dom[i], dom[i + 1]) for i in range(0, len(dom), 2)]
    return Jumper(name=node.name, label=node.labels[0] if node.labels else node.name,
                  domain=domain, sheet_label=_sheet_label(node), src=src_of(node))


def _sheet_label(node) -> str:
    if "shield,sheet-label" in node.props:
        return node.props["shield,sheet-label"].to_string()
    return ""
