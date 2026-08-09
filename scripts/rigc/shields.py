"""Shield parsing: a `.shield` translation unit -> model.Shield. Ported
from rigexp/shields.py (rigc-r3-brief.md Sec 3). Loader-side validation
done here:

  - shield,plugs names a known connector type
  - bus proxy nodes are allowed by the plug binding (Conv. 1)
  - position references target THIS shield's plug and exist in the type
  - exactly one of reg / shield,addr-from on addressable-bus devices
    (forgot-vs-deferred: address authority rule)
  - authored reg matches the unit-address; symbolic unit-addresses are
    linted against the addr-from target

**Diagnostics are RETURN values** (mission brief Sec 6): every parse
function below returns (value, diagnostics) rather than writing into a
diags parameter handed in from outside -- the local list a function
builds and returns is not the banned accumulator shape (nothing outside
this module ever mutates one), it is composition-by-return exactly like
every other rigc module.

**The cpp/unit-test seam** (rigc-r3-brief.md Sec 2): everything here
operates on a `dtlib.DT` that ALREADY EXISTS -- it never calls cpp itself
-- so it is unit-testable directly against a synthetic, cpp-free `.dts`
text parsed with `dtsio.get_dtlib().DT(path)`.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .diag import Diagnostic, SourceRef, error, warning
from .dtsio import get_dtlib, render_prop, src_of, words
from .model import (ConnectorType, Device, ExposedSocket, GpioRef, Jumper,
                    Pad, Shield, Strap)

_BUS_PROPS = {"socket,i2c": "i2c", "socket,spi": "spi", "socket,uart": "uart"}

_RESERVED = {"plug", "pads", "config"}
_ADDRESSABLE = {"i2c"}          # buses with device-static in-band addressing
_MODEL_PROPS = {"reg", "compatible", "shield,addr-from", "shield,cs-position",
               "shield,collect", "shield,params", "shield,param-includes"}


def parse_shields(dt, types: Dict[str, ConnectorType],
                  ) -> Tuple[Dict[str, Shield], List[Diagnostic]]:
    """Every `.shield` file has exactly one shield node under the
    `shield-templates` wrapper (a marker that distinguishes a TEMPLATE
    from a real Zephyr shield's applied `<name>.overlay`)."""
    shields: Dict[str, Shield] = {}
    diags: List[Diagnostic] = []
    root = dt.root.nodes.get("shield-templates")
    if root is None:
        return shields, diags
    for node in root.nodes.values():
        shield, d = _parse_shield(node, types)
        diags += d
        shields[shield.name] = shield
    return shields, diags


def _parse_shield(node, types: Dict[str, ConnectorType],
                  ) -> Tuple[Shield, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    shield = Shield(
        name=node.name,
        label=node.labels[0] if node.labels else node.name,
        plugs=node.props["shield,plugs"].to_string(),
        src=src_of(node))
    shield.by_path[node.path] = shield

    ctype = types.get(shield.plugs)
    if ctype is None:
        diags.append(error(
            "lang-shield-type",
            f"shield '{shield.name}' plugs unknown connector type "
            f"'{shield.plugs}'\nknown types: {', '.join(sorted(types))}",
            (src_of(node.props["shield,plugs"]),)))

    plug = node.nodes.get("plug")
    if plug is None:
        diags.append(error(
            "lang-shield-plug",
            f"shield '{shield.name}' has no plug node — the plug is the "
            "position reference frame (Conv. 2)", (src_of(node),)))

    # two-phase: pads/config first -- devices reference straps
    # (shield,addr-from) regardless of group order in the file
    for group in node.nodes.values():
        if group.name == "pads":
            for pnode in group.nodes.values():
                pad, d = _parse_pad(pnode)
                diags += d
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

    def is_exposed(g) -> bool:
        return "compatible" in g.props and \
            g.props["compatible"].to_string().startswith("socket,")

    # device groups FIRST -- an exposed socket may reference a device as
    # its scope root (S8 mux channel), so the device must be in by_path
    # already.
    for group in node.nodes.values():
        if group.name in _RESERVED or is_exposed(group):
            continue
        bus = group.name if ctype and group.name in ctype.bus_proxies else None
        if bus is None and ctype and group.name in ("i2c", "spi", "uart"):
            diags.append(error(
                "lang-shield-proxy",
                f"shield '{shield.name}' has a '{group.name}' bus proxy "
                f"but the '{ctype.name}' plug binding allows only: "
                f"{', '.join(ctype.bus_proxies)}",
                (src_of(group),)))
        for dnode in group.nodes.values():
            dev, d = _parse_device(dnode, shield, plug, ctype, bus,
                                   None if bus else group.name)
            diags += d
            shield.devices.append(dev)
            shield.by_path[dnode.path] = dev

    # then re-exported sockets (R19 pass-through, or S8 scope creation)
    for group in node.nodes.values():
        if group.name in _RESERVED or not is_exposed(group):
            continue
        exp, d = _parse_exposed(group, plug, shield)
        diags += d
        shield.exposes[exp.name] = exp
        shield.by_path[group.path] = exp
    return shield, diags


def _parse_device(node, shield: Shield, plug, ctype, bus, group,
                  ) -> Tuple[Device, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    name, _, unit = node.name.partition("@")
    compat = node.props["compatible"].to_string() if "compatible" in node.props else None

    reg = node.props["reg"].to_num() if "reg" in node.props else None
    addr_from = None
    if "shield,addr-from" in node.props:
        target = node.props["shield,addr-from"].to_node()
        strap = shield.by_path.get(target.path)
        if not isinstance(strap, Strap):
            diags.append(error(
                "lang-addr-from",
                f"shield,addr-from on '{shield.name}/{node.name}' does not "
                "point at a config strap of this shield",
                (src_of(node.props["shield,addr-from"]),)))
        else:
            addr_from = strap.name

    # exactly-one-of rule: forgot-reg is detectable, deferred is explicit
    if bus in _ADDRESSABLE:
        if (reg is None) == (addr_from is None):
            which = "both" if reg is not None else "neither"
            diags.append(error(
                "lang-addr-authority",
                f"device '{shield.name}/{node.name}' on an addressable bus "
                f"carries {which} of reg / shield,addr-from — exactly one "
                "is required (address authority rule)", (src_of(node),)))

    # authored reg == unit-address (validated, Conv. 2); symbolic
    # unit-address is a documentation marker linted against the addr-from
    # target
    if unit and reg is not None:
        try:
            if int(unit, 16) != reg:
                diags.append(error(
                    "lang-unit-addr",
                    f"'{node.name}': unit-address @{unit} != authored reg "
                    f"<{reg:#x}> — they must be a matching pair",
                    (src_of(node),)))
        except ValueError:
            diags.append(error(
                "lang-unit-addr",
                f"'{node.name}': symbolic unit-address with authored reg "
                "— symbolic markers are for deferred addresses only",
                (src_of(node),)))
    elif unit and addr_from and unit.replace("-", "_") != addr_from.replace("-", "_"):
        diags.append(warning(
            "lang-unit-addr",
            f"'{node.name}': symbolic unit-address @{unit} does not match "
            f"its resolver '{addr_from}' (lint: marker must name the "
            "addr-from target)", (src_of(node),)))

    cs_position = None
    if "shield,cs-position" in node.props:
        cs_position = node.props["shield,cs-position"].to_num()

    collect = None
    if "shield,collect" in node.props:
        collect = node.props["shield,collect"].to_string()

    declared_params: List[str] = []
    if "shield,params" in node.props:
        declared_params = list(node.props["shield,params"].to_strings())

    # The vocabulary declared_params' own tokens resolve against (Sec 3):
    # a device-node property, sibling to shield,params, since the header
    # is a contract of the parameter, not an accident of what the
    # template happened to #include.
    declared_param_includes: List[str] = []
    if "shield,param-includes" in node.props:
        declared_param_includes = list(node.props["shield,param-includes"].to_strings())

    dev = Device(name=name, label=node.labels[0] if node.labels else name,
                compatible=compat, bus=bus, group=group, reg=reg,
                addr_from=addr_from, cs_position=cs_position, collect=collect,
                declared_params=declared_params,
                declared_param_includes=declared_param_includes, src=src_of(node))

    for prop in node.props.values():
        if prop.name in _MODEL_PROPS or prop.name == "phandle":
            continue
        fn = _function_of(prop.name)
        if fn is not None:
            refs, d = _parse_pos_ref(prop, fn, shield, plug, ctype)
            dev.gpio_refs.extend(refs)
            diags += d
            continue
        dtlib = get_dtlib()
        if prop.type is dtlib.Type.PHANDLES_AND_NUMS:
            diags.append(warning(
                "lang-prop",
                f"phandle property '{prop.name}' of "
                f"'{shield.name}/{node.name}' is not a recognized function "
                "ref (gpios/pwms/io-channels) — dropped", (src_of(prop),)))
            continue
        rendered = render_prop(prop)
        if rendered is None:
            diags.append(warning(
                "lang-prop",
                f"property '{prop.name}' of '{shield.name}/{node.name}' "
                "has a type the prototype cannot pass through — dropped "
                "from output", (src_of(prop),)))
        elif prop.name != "compatible":
            dev.extra_props.append((prop.name, rendered))
    if compat:
        dev.extra_props.insert(0, ("compatible", f'compatible = "{compat}";'))
    return dev, diags


_FUNCTION_CELLS = {"gpio": "#gpio-cells", "pwm": "#pwm-cells", "adc": "#io-channel-cells"}
_FUNCTION_DEFAULT_CELLS = {"gpio": 2, "pwm": 3, "adc": 1}


def _function_of(prop_name: str) -> Optional[str]:
    """Which function-nexus a property resolves through, by name."""
    if prop_name == "gpios" or prop_name.endswith("-gpios"):
        return "gpio"
    if prop_name == "pwms":
        return "pwm"
    if prop_name == "io-channels":
        return "adc"
    return None


def _parse_pos_ref(prop, function: str, shield: Shield, plug, ctype,
                   ) -> Tuple[List[GpioRef], List[Diagnostic]]:
    """Nexus-aware position reference, per function. The plug is a
    multi-function nexus: a claim reads the plug's #<fn>-cells cells."""
    refs: List[GpioRef] = []
    diags: List[Diagnostic] = []
    cells = words(prop)
    dt = prop.node.dt
    i = 0
    while i < len(cells):
        target = dt.phandle2node.get(cells[i])
        ncells = _ncells(target, function)
        args = cells[i + 1: i + 1 + ncells]
        i += 1 + ncells
        if target is None or len(args) < ncells:
            diags.append(error(
                "lang-pos-ref",
                f"'{prop.name}' has a malformed {function} entry",
                (src_of(prop),)))
            return refs, diags

        elem = shield.by_path.get(target.path)
        if plug is not None and target.path == plug.path:      # fixed position
            pos = args[0]
            ok, d = _valid_position(prop, pos, ctype)
            diags += d
            if not ok:
                continue
            if function == "gpio":
                refs.append(GpioRef(prop=prop.name, position=pos, flags=args[1],
                                    function="gpio", src=src_of(prop)))
            elif function == "pwm":
                refs.append(GpioRef(prop=prop.name, position=pos, period=args[1],
                                    flags=args[2], function="pwm", src=src_of(prop)))
            else:  # adc
                refs.append(GpioRef(prop=prop.name, position=pos, flags=0,
                                    function="adc", src=src_of(prop)))
        elif function == "gpio" and isinstance(elem, Jumper):  # deferred position (R6)
            flags = args[0] if args else 0
            refs.append(GpioRef(prop=prop.name, position=None, flags=flags,
                                jumper=elem.name, function="gpio", src=src_of(prop)))
        else:
            where = target.path if target else "?"
            diags.append(error(
                "lang-pos-ref",
                f"'{prop.name}' must reference THIS shield's plug node "
                f"(fixed position, Conv. 3)"
                + ("" if function != "gpio" else " or one of its routing jumpers (R6)")
                + f" — it points at {where}",
                (src_of(prop),)))
    return refs, diags


def _ncells(node, function: str) -> int:
    prop = _FUNCTION_CELLS[function]
    if node is not None and prop in node.props:
        return node.props[prop].to_num()
    return _FUNCTION_DEFAULT_CELLS[function]


def _valid_position(prop, pos: int, ctype) -> Tuple[bool, List[Diagnostic]]:
    if ctype and pos not in ctype.index2name:
        return False, [error(
            "lang-position",
            f"'{prop.name}' claims position index {pos}, which does not "
            f"exist on connector type '{ctype.name}'", (src_of(prop),))]
    if ctype and ctype.index2name[pos] not in ctype.positions:
        return False, [error(
            "lang-position",
            f"'{prop.name}' claims {ctype.index2name[pos]} — bus copper, "
            f"not a claimable position of '{ctype.name}' (electrical "
            "realization is not modeled)", (src_of(prop),))]
    return True, []


def _parse_exposed(node, plug, shield: Shield,
                   ) -> Tuple[ExposedSocket, List[Diagnostic]]:
    """A re-exported socket. gpio-map binds exposed positions to the
    carrier's own plug positions (pass-through, R19). socket,<bus> is
    either <&plug> (pass through the parent's bus, S6) or <&device> (a
    NEW scope rooted in that device of the shield, S8)."""
    diags: List[Diagnostic] = []
    type_name = node.props["compatible"].to_string().split(",", 1)[1]
    gpio_map: Dict[int, Tuple[int, int]] = {}
    if "gpio-map" in node.props:
        cells = words(node.props["gpio-map"])
        dt = node.dt
        for i in range(0, len(cells) - len(cells) % 5, 5):
            pos, _f, phandle, parent_pos, parent_flags = cells[i:i + 5]
            target = dt.phandle2node.get(phandle)
            if plug is None or target is None or target.path != plug.path:
                diags.append(error(
                    "lang-exposed",
                    f"exposed socket '{node.name}': gpio-map parent must "
                    "be the carrier's plug (pass-through, R19)",
                    (src_of(node),)))
                continue
            gpio_map[pos] = (parent_pos, parent_flags)

    buses: Dict[str, object] = {}
    for prop_name, kind in _BUS_PROPS.items():
        if prop_name not in node.props:
            continue
        target = node.props[prop_name].to_node()
        by_path = shield.by_path.get(target.path)
        if plug is not None and target.path == plug.path:
            buses[kind] = "plug"                       # pass-through (S6)
        elif isinstance(by_path, Device):
            buses[kind] = ("scope", by_path.label)      # new scope (S8)
        else:
            diags.append(error(
                "lang-exposed",
                f"exposed socket '{node.name}': {prop_name} must be "
                "<&plug> (pass-through, R19) or <&device> (new scope, "
                "R26)", (src_of(node),)))

    cs_pool = list(node.props["socket,cs-pool"].to_nums()) \
        if "socket,cs-pool" in node.props else None
    channel = node.props["shield,channel"].to_num() \
        if "shield,channel" in node.props else None
    return ExposedSocket(
        name=node.name, label=node.labels[0] if node.labels else node.name,
        type_name=type_name, gpio_map=gpio_map, buses=buses,
        cs_pool=cs_pool, channel=channel, src=src_of(node)), diags


def _parse_pad(node) -> Tuple[Pad, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    role = node.props["shield,role"].to_string() if "shield,role" in node.props else "bidir"
    if role not in ("driver", "listener", "bidir"):
        diags.append(error(
            "lang-pad-role",
            f"pad '{node.name}': unknown role '{role}' (driver / listener "
            "/ bidir, R23)", (src_of(node),)))
    of = None
    if "shield,of" in node.props:
        of = node.props["shield,of"].to_node().name.partition("@")[0]
    return Pad(name=node.name, label=node.labels[0] if node.labels else node.name,
              role=role, of=of, src=src_of(node)), diags


def _parse_strap(node) -> Strap:
    dom = node.props["shield,domain"].to_nums()
    domain = [(dom[i], dom[i + 1]) for i in range(0, len(dom), 2)]
    return Strap(name=node.name, label=node.labels[0] if node.labels else node.name,
                domain=domain, sheet_label=_sheet_label(node), src=src_of(node))


def _parse_jumper(node) -> Jumper:
    dom = node.props["shield,position-domain"].to_nums()
    domain = [(dom[i], dom[i + 1]) for i in range(0, len(dom), 2)]
    return Jumper(name=node.name, label=node.labels[0] if node.labels else node.name,
                 domain=domain, sheet_label=_sheet_label(node), src=src_of(node))


def _sheet_label(node) -> str:
    if "shield,sheet-label" in node.props:
        return node.props["shield,sheet-label"].to_string()
    return ""
