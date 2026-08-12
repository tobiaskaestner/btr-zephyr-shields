"""Shield parsing: a `.shield` translation unit -> model.Shield. Ported
from rigexp/shields.py (rigc-r3-brief.md Sec 3). Loader-side validation
done here:

  - shield,plugs names a known connector type
  - bus proxy nodes are allowed by the plug binding (Conv. 1)
  - position references target one of THIS shield's plugs and exist in
    that plug's connector type
  - exactly one of reg / shield,addr-from on addressable-bus devices
    (forgot-vs-deferred: address authority rule)
  - authored reg matches the unit-address; symbolic unit-addresses are
    linted against the addr-from target

**Two authored forms** (multi-plug-shield-brief.md Sec 2), discriminated
by the template-level `shield,plugs` property's presence:

  single (unchanged, byte-identical forever) -- `shield,plugs` on the
    template node + the reserved `plug` child; normalizes internally to
    one slot named `"plug"`, the node's own literal name.
  plural -- template-level `shield,plugs` ABSENT; instead N children
    `compatible = "shield,plug"`, each naming its own connector type. The
    child's NODE NAME is the slot name (shield-owned). Bus groups nest
    UNDER their owning plug node; a bus group at template level is
    rejected. Plain (non-bus) device groups stay at template level,
    plug-agnostic -- their devices' refs each carry their own plug by
    phandle (Conv. 2/3, widened from "must be THIS shield's plug" to
    "one of this shield's plugs", ruling 2). Promotion and routing
    jumpers are refused outright on a plural shield (Sec 6) -- straps are
    unaffected (bus-scoped, not plug-scoped). A plural shield MAY declare
    an exposed socket (multi-plug-carrier-brief.md): its gpio-map rows and
    socket,<bus> properties each resolve through one of the carrier's
    plugs, exactly like a device's own cross-plug refs.

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

from typing import Any, Dict, List, Optional, Tuple

from .buskind import BUS_PROP_RE as _BUS_PROP_RE
from .buskind import CS_POOL_PROP_RE as _CS_POOL_PROP_RE
from .buskind import bus_kind_of, is_bus_kind
from .diag import Diagnostic, SourceRef, error, warning
from .dtsio import get_dtlib, render_prop, src_of, words
from .model import (ConnectorType, Device, ExposedSocket, GpioRef, Jumper,
                    Pad, Shield, Strap)

#: socket,<kind> or socket,<kind>-<role> -- an exposed socket's own bus
#: vocabulary is the qualified multi-bus pattern (multi-plug-carrier-
#: brief.md Sec 2), the same shared pattern board_edt.py/registry.py read
#: off their own inputs (a connector type's bus names mean the same thing
#: on either side of a pass-through) -- see buskind.py for the regex
#: itself and why it lives there.
#:
#: socket,<kind>-<role>-cs-pool -- a named bus's own authored cs-pool
#: override on an exposed socket node, keyed the same qualified way. The
#: legacy, role-less "socket,cs-pool" (every carrier's own spelling
#: today) is handled separately below: it carries no kind in its own
#: name, so it is not this pattern's concern.

_RESERVED = {"plug", "pads", "config"}
_MODEL_PROPS = {"reg", "compatible", "shield,addr-from", "shield,cs-position",
               "shield,collect", "shield,params", "shield,param-includes"}

#: path -> (slot name, connector type) for every plug this shield declares
#: (one entry for the single form, N for the plural form) -- the map
#: `_parse_pos_ref` resolves a phandle against to decide which slot a
#: reference names and to validate its position, replacing "the shield's
#: one plug" with "one of the shield's plugs" (ruling 2).
PlugsByPath = Dict[str, Tuple[str, Optional[ConnectorType]]]


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


def _is_plug_node(g) -> bool:
    return "compatible" in g.props and g.props["compatible"].to_string() == "shield,plug"


def _parse_shield(node, types: Dict[str, ConnectorType],
                  ) -> Tuple[Shield, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    label = node.labels[0] if node.labels else node.name
    plugs_prop = node.props.get("shield,plugs")
    plug_children = [c for c in node.nodes.values() if _is_plug_node(c)]

    if plugs_prop is not None and plug_children:
        diags.append(error(
            "lang-shield-plurality",
            f"shield '{node.name}' declares template-level shield,plugs "
            "AND one or more 'shield,plug'-compatible children -- a "
            "shield is either the single form (shield,plugs on the "
            "template) or the plural form (N plug nodes), never both",
            (src_of(node),)))
        return Shield(name=node.name, label=label, plugs={}, src=src_of(node)), diags

    named_plug = next((c for c in plug_children if c.name == "plug"), None)
    if named_plug is not None:
        diags.append(error(
            "lang-shield-plurality",
            f"shield '{node.name}': a plural shield's plug node may not "
            "be named 'plug' -- that name is reserved for the "
            "single-plug form's own default slot",
            (src_of(named_plug),)))
        return Shield(name=node.name, label=label, plugs={}, src=src_of(node)), diags

    is_plural = bool(plug_children)
    shield = Shield(name=node.name, label=label, plugs={}, src=src_of(node))
    shield.by_path[node.path] = shield

    ctypes_by_slot: Dict[str, Optional[ConnectorType]] = {}
    nodes_by_slot: Dict[str, Any] = {}
    plugs_by_path: PlugsByPath = {}

    if is_plural:
        for child in plug_children:
            slot = child.name
            type_v = child.props.get("shield,plugs")
            if type_v is None:
                diags.append(error(
                    "lang-shield-type",
                    f"shield '{shield.name}': plug '{slot}' declares no "
                    "shield,plugs of its own -- every plug of a plural "
                    "shield names its own connector type",
                    (src_of(child),)))
                continue
            type_name = type_v.to_string()
            ctype = types.get(type_name)
            if ctype is None:
                diags.append(error(
                    "lang-shield-type",
                    f"shield '{shield.name}': plug '{slot}' plugs unknown "
                    f"connector type '{type_name}'\nknown types: "
                    f"{', '.join(sorted(types))}",
                    (src_of(type_v),)))
            shield.plugs[slot] = type_name
            ctypes_by_slot[slot] = ctype
            nodes_by_slot[slot] = child
            plugs_by_path[child.path] = (slot, ctype)
    else:
        if plugs_prop is None:
            diags.append(error(
                "lang-shield-plug",
                f"shield '{shield.name}' declares no shield,plugs and no "
                "shield,plug-compatible child -- a shield names its "
                "connector type either way (Conv. 2)",
                (src_of(node),)))
            return shield, diags
        type_name = plugs_prop.to_string()
        ctype = types.get(type_name)
        if ctype is None:
            diags.append(error(
                "lang-shield-type",
                f"shield '{shield.name}' plugs unknown connector type "
                f"'{type_name}'\nknown types: {', '.join(sorted(types))}",
                (src_of(plugs_prop),)))
        shield.plugs["plug"] = type_name
        plug_node = node.nodes.get("plug")
        if plug_node is None:
            diags.append(error(
                "lang-shield-plug",
                f"shield '{shield.name}' has no plug node — the plug is the "
                "position reference frame (Conv. 2)", (src_of(node),)))
        else:
            ctypes_by_slot["plug"] = ctype
            nodes_by_slot["plug"] = plug_node
            plugs_by_path[plug_node.path] = ("plug", ctype)

    # two-phase: pads/config first -- devices reference straps
    # (shield,addr-from) regardless of group order in the file. Both stay
    # TEMPLATE-LEVEL regardless of plurality (shield-level facts) -- a
    # routing jumper is the one exception: its position domain has no
    # plug axis, so a plural shield declaring one is refused (Sec 4/6)
    # rather than silently mishandled; straps are address-domain and
    # bus-scoped, unaffected either way.
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
                    if is_plural:
                        diags.append(error(
                            "lang-shield-plurality",
                            f"shield '{shield.name}': plural shields "
                            f"cannot declare a routing jumper "
                            f"('{snode.name}') -- the position domain has "
                            "no plug axis (multi-plug slice 1)",
                            (src_of(snode),)))
                        continue
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
    if not is_plural:
        ctype = ctypes_by_slot.get("plug")
        for group in node.nodes.values():
            if group.name in _RESERVED or is_exposed(group):
                continue
            bus = group.name if ctype and group.name in ctype.bus_proxies else None
            if bus is None and ctype and bus_kind_of(group.name) is not None:
                diags.append(error(
                    "lang-shield-proxy",
                    f"shield '{shield.name}' has a '{group.name}' bus proxy "
                    f"but the '{ctype.name}' plug binding allows only: "
                    f"{', '.join(ctype.bus_proxies)}",
                    (src_of(group),)))
            for dnode in group.nodes.values():
                dev, d = _parse_device(dnode, shield, plugs_by_path, bus,
                                       None if bus else group.name, "plug")
                diags += d
                shield.devices.append(dev)
                shield.by_path[dnode.path] = dev
    else:
        # template-level groups: plug-agnostic (plain groups) -- a group
        # whose name is bus-shaped is rejected, since a plural shield's
        # bus groups must nest under their owning plug (Sec 2 placement
        # rule), never sit at template level.
        for group in node.nodes.values():
            if group.name in _RESERVED or is_exposed(group) or group in plug_children:
                continue
            if bus_kind_of(group.name) is not None:
                candidates = sorted(
                    slot for slot, ct in ctypes_by_slot.items()
                    if ct and group.name in ct.bus_proxies)
                diags.append(error(
                    "lang-shield-proxy",
                    f"shield '{shield.name}' has a '{group.name}' bus proxy "
                    "at template level, but a plural shield nests bus "
                    "groups under their owning plug"
                    + (f" — candidate plugs: {', '.join(candidates)}"
                       if candidates else ""),
                    (src_of(group),)))
            for dnode in group.nodes.values():
                dev, d = _parse_device(dnode, shield, plugs_by_path, None,
                                       group.name, None)
                diags += d
                shield.devices.append(dev)
                shield.by_path[dnode.path] = dev

        # each plug's OWN bus groups, matched against ITS OWN connector
        # type's bus_proxies -- the plug binding, structural (Sec 2). A
        # group nested under a plug that is NEITHER a bus this plug's
        # ctype allows NOR bus-kind-named at all is a plain group in the
        # wrong place: Sec 2's placement rule keeps plain groups at
        # template level (plug-agnostic), so nesting one under a plug is
        # rejected here rather than silently recorded with Device.plug =
        # slot -- the same symmetry the template-level walk above applies
        # to a misplaced BUS group (its own lang-shield-proxy branch).
        for slot, plug_node in nodes_by_slot.items():
            ctype = ctypes_by_slot[slot]
            for group in plug_node.nodes.values():
                bus = group.name if ctype and group.name in ctype.bus_proxies else None
                if bus is None:
                    if ctype and bus_kind_of(group.name) is not None:
                        diags.append(error(
                            "lang-shield-proxy",
                            f"shield '{shield.name}': plug '{slot}' has a "
                            f"'{group.name}' bus proxy but the '{ctype.name}' "
                            f"plug binding allows only: "
                            f"{', '.join(ctype.bus_proxies)}",
                            (src_of(group),)))
                    else:
                        diags.append(error(
                            "lang-shield-proxy",
                            f"shield '{shield.name}': plug '{slot}' has a "
                            f"'{group.name}' group nested under it -- plain "
                            "device groups belong at template level "
                            "(plug-agnostic; their devices' refs each carry "
                            "their own plug by phandle)",
                            (src_of(group),)))
                for dnode in group.nodes.values():
                    dev, d = _parse_device(dnode, shield, plugs_by_path, bus,
                                           None if bus else group.name,
                                           slot if bus else None)
                    diags += d
                    shield.devices.append(dev)
                    shield.by_path[dnode.path] = dev

    # then re-exported sockets (R19 pass-through, or S8 scope creation) --
    # a plural shield may declare one too (multi-plug-carrier-brief.md):
    # each gpio-map row and each socket,<bus> resolves through ONE of the
    # carrier's plugs, per plugs_by_path, exactly as a device's own
    # cross-plug refs do (ruling 2, applied one level up).
    for group in node.nodes.values():
        if group.name in _RESERVED or not is_exposed(group) or group in plug_children:
            continue
        exp, d = _parse_exposed(group, plugs_by_path, shield, types)
        diags += d
        shield.exposes[exp.name] = exp
        shield.by_path[group.path] = exp
    return shield, diags


def _parse_device(node, shield: Shield, plugs_by_path: PlugsByPath, bus, group,
                  dev_plug: Optional[str]) -> Tuple[Device, List[Diagnostic]]:
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
    if is_bus_kind(bus, "i2c"):
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
                addr_from=addr_from, cs_position=cs_position, plug=dev_plug,
                collect=collect, declared_params=declared_params,
                declared_param_includes=declared_param_includes, src=src_of(node))

    for prop in node.props.values():
        if prop.name in _MODEL_PROPS or prop.name == "phandle":
            continue
        fn = _function_of(prop.name)
        if fn is not None:
            refs, d = _parse_pos_ref(prop, fn, shield, plugs_by_path)
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


def _parse_pos_ref(prop, function: str, shield: Shield, plugs_by_path: PlugsByPath,
                   ) -> Tuple[List[GpioRef], List[Diagnostic]]:
    """Nexus-aware position reference, per function. A plug is a
    multi-function nexus: a claim reads the plug's #<fn>-cells cells.
    Granularity is PER-REFERENCE (ruling 2): the phandle names WHICH of
    the shield's plugs this claim resolves through, independent of which
    plug the surrounding device's own bus binds to -- a cross-plug
    reference is zero new syntax, just a wider set of valid targets."""
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
        plug_entry = plugs_by_path.get(target.path)
        if plug_entry is not None:                              # fixed position
            slot, ctype = plug_entry
            pos = args[0]
            ok, d = _valid_position(prop, pos, ctype)
            diags += d
            if not ok:
                continue
            if function == "gpio":
                refs.append(GpioRef(prop=prop.name, position=pos, flags=args[1],
                                    function="gpio", src=src_of(prop), plug=slot))
            elif function == "pwm":
                refs.append(GpioRef(prop=prop.name, position=pos, period=args[1],
                                    flags=args[2], function="pwm", src=src_of(prop),
                                    plug=slot))
            else:  # adc
                refs.append(GpioRef(prop=prop.name, position=pos, flags=0,
                                    function="adc", src=src_of(prop), plug=slot))
        elif function == "gpio" and isinstance(elem, Jumper):  # deferred position (R6)
            flags = args[0] if args else 0
            refs.append(GpioRef(prop=prop.name, position=None, flags=flags,
                                jumper=elem.name, function="gpio", src=src_of(prop)))
        else:
            where = target.path if target else "?"
            if len(plugs_by_path) > 1:
                what = "one of this shield's plug nodes"
            else:
                what = "THIS shield's plug node"
            diags.append(error(
                "lang-pos-ref",
                f"'{prop.name}' must reference {what} (fixed position, "
                "Conv. 3)"
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


def _parse_exposed(node, plugs_by_path: PlugsByPath, shield: Shield,
                   types: Dict[str, ConnectorType],
                   ) -> Tuple[ExposedSocket, List[Diagnostic]]:
    """A re-exported socket, now potentially composed from SEVERAL named
    parents (multi-plug-carrier-brief.md Sec 1 ruling 1). gpio-map binds
    exposed positions to ONE of the carrier's own plug positions
    (pass-through, R19) -- RECORDING which slot the phandle named, per
    row, exactly as `_parse_pos_ref` widens "must be THIS shield's plug"
    to "one of this shield's plugs" (ruling 2, applied one level up).
    socket,<bus> (bare, or role-qualified per the multi-bus vocabulary)
    is either <&some-plug> (pass through THAT plug's own bus, S6) or
    <&device> (a NEW scope rooted in that device of the shield, S8). The
    CHILD-side qualified name is the EXPOSED connector type's OWN
    vocabulary -- validated exact-match against its declared bus_proxies,
    no fallback, independent of whichever parent-side bus a pass-through
    eventually selects (that selection is compose_socket's own job, by
    KIND, once the parent is a real resolved socket)."""
    diags: List[Diagnostic] = []
    type_name = node.props["compatible"].to_string().split(",", 1)[1]
    ctype = types.get(type_name)
    is_plural = len(plugs_by_path) > 1

    gpio_map: Dict[int, Tuple[str, int, int]] = {}
    if "gpio-map" in node.props:
        cells = words(node.props["gpio-map"])
        dt = node.dt
        for i in range(0, len(cells) - len(cells) % 5, 5):
            pos, _f, phandle, parent_pos, parent_flags = cells[i:i + 5]
            target = dt.phandle2node.get(phandle)
            plug_entry = plugs_by_path.get(target.path) if target is not None else None
            if plug_entry is None:
                what = "one of the carrier's plugs" if is_plural else "the carrier's plug"
                diags.append(error(
                    "lang-exposed",
                    f"exposed socket '{node.name}': gpio-map parent must "
                    f"be {what} (pass-through, R19)",
                    (src_of(node),)))
                continue
            slot, _pctype = plug_entry
            gpio_map[pos] = (slot, parent_pos, parent_flags)

    buses: Dict[str, object] = {}
    qualified_props = sorted(name for name in node.props if _BUS_PROP_RE.match(name))
    for prop_name in qualified_props:
        kind = prop_name[len("socket,"):]
        if ctype is not None and kind not in ctype.bus_proxies:
            diags.append(error(
                "lang-exposed",
                f"exposed socket '{node.name}': {prop_name} names a bus "
                f"'{kind}' that connector type '{type_name}' does not "
                "declare -- declared buses: "
                f"{', '.join(sorted(ctype.bus_proxies)) or 'none'}",
                (src_of(node),)))
            continue
        target = node.props[prop_name].to_node()
        by_path = shield.by_path.get(target.path)
        plug_entry = plugs_by_path.get(target.path)
        if plug_entry is not None:
            slot, _pctype = plug_entry
            buses[kind] = ("plug", slot)                # pass-through (S6)
        elif isinstance(by_path, Device):
            buses[kind] = ("scope", by_path.label)       # new scope (S8)
        else:
            what = "one of the carrier's plugs" if is_plural else "<&plug>"
            diags.append(error(
                "lang-exposed",
                f"exposed socket '{node.name}': {prop_name} must be "
                f"{what} (pass-through, R19) or <&device> (new scope, "
                "R26)", (src_of(node),)))

    cs_pool: Dict[str, List[int]] = {}
    if "socket,cs-pool" in node.props:
        cs_pool["spi"] = list(node.props["socket,cs-pool"].to_nums())
    for prop_name in sorted(node.props):
        m = _CS_POOL_PROP_RE.match(prop_name)
        if m is None:
            continue
        cs_pool[m.group(1)] = list(node.props[prop_name].to_nums())

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
