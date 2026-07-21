"""Candidate-1 loader: rig.dts (pure valid-DTS) -> rig model.

What dtlib gives for free: parsing, label resolution (dangling references
die at PARSE time with file:line), phandle-pair mechanics (R24 via
to_nodes()). What it does NOT give: cross-pair validation — <&counter_1
&dl_sq> parses fine even though dl_sq belongs to another instance's shield.
That check is explicit loader work here, same as in candidate-2.
"""
from __future__ import annotations

from .ctypes_registry import load_types
from .diag import Diagnostics
from .dtsio import dtlib, parse_dts, src_of, words
from .model import Instance, Rig, Shield, Strap, Wire, WireEnd
from .shields import parse_shields


def load(rig_path: str, workdir: str, diags: Diagnostics) -> Rig | None:
    dt = parse_dts(rig_path, workdir)      # LoadError w/ file:line on parse issues
    types = load_types()
    shields = parse_shields(dt, types, diags)
    by_path = {}
    for s in shields.values():
        by_path.update(s.by_path)

    rig_node = dt.root.nodes.get("rig")
    if rig_node is None:
        diags.error("lang-rig", f"no /rig node in {rig_path}")
        return None

    rig = Rig(
        name=rig_node.props["rig,name"].to_string(),
        board=rig_node.props["rig,board"].to_string(),
        src=src_of(rig_node))

    inst_by_path: dict[str, Instance] = {}
    for node in rig_node.nodes.values():
        if "rig,shield" not in node.props:
            continue
        inst = _parse_instance(node, dt, by_path, shields, diags)
        if inst:
            rig.instances.append(inst)
            inst_by_path[node.path] = inst

    wires = rig_node.nodes.get("wires")
    if wires is not None:
        for wnode in wires.nodes.values():
            wire = _parse_wire(wnode, inst_by_path, diags)
            if wire:
                rig.wires.append(wire)
    return rig


def _parse_instance(node, dt, by_path, shields, diags) -> Instance | None:
    name = node.labels[0] if node.labels else node.name
    target = node.props["rig,shield"].to_node()
    shield = by_path.get(target.path)
    if not isinstance(shield, Shield):
        diags.error(
            "lang-instance-shield",
            f"instance '{name}': rig,shield does not point at a shield under "
            f"/rig-shields (it points at {target.path})\n"
            f"known shields: {', '.join(sorted(shields))}",
            [src_of(node.props["rig,shield"])])
        return None

    inst = Instance(name=name, shield=shield,
                    socket=node.props["rig,socket"].to_string(), src=src_of(node))

    if "rig,pin" in node.props:
        prop = node.props["rig,pin"]
        cells = words(prop)
        for i in range(0, len(cells), 2):
            strap_node = dt.phandle2node.get(cells[i])
            strap = shield.by_path.get(strap_node.path) if strap_node else None
            if not isinstance(strap, Strap):
                where = strap_node.path if strap_node else "?"
                diags.error(
                    "lang-pin",
                    f"instance '{name}': rig,pin does not reference a config strap of "
                    f"shield '{shield.name}' (it points at {where})\n"
                    f"straps of '{shield.name}': {', '.join(sorted(shield.straps)) or 'none'}",
                    [src_of(prop)])
                continue
            inst.pins[strap.name] = cells[i + 1]
            inst.pin_refs[strap.name] = src_of(prop)
    return inst


def _parse_wire(node, inst_by_path, diags) -> Wire | None:
    ends = {}
    for key in ("rig,from", "rig,to"):
        prop = node.props.get(key)
        if prop is None:
            diags.error("lang-wire", f"wire {node.name}: missing {key}", [src_of(node)])
            return None
        pair = prop.to_nodes()          # phandle pair, R24/Conv. 6
        if len(pair) != 2:
            diags.error("lang-wire",
                        f"wire {node.name}: {key} must be an <&instance &node> pair",
                        [src_of(prop)])
            return None
        inst_node, elem_node = pair
        inst = inst_by_path.get(inst_node.path)
        if inst is None:
            diags.error(
                "lang-wire",
                f"wire {node.name}: {key} first phandle is not a rig instance "
                f"(it points at {inst_node.path})", [src_of(prop)])
            return None
        elem = inst.shield.by_path.get(elem_node.path)
        if elem is None:
            # the cross-pair check dtlib can NOT do: both labels exist, but the
            # element is not part of THIS instance's shield
            owner = elem_node.path.split("/")[2] if elem_node.path.startswith("/rig-shields/") else "?"
            diags.error(
                "lang-wire-crosspair",
                f"wire {node.name}: {key} = <&{inst.name} &{elem_node.labels[0] if elem_node.labels else elem_node.name}> — "
                f"'{elem_node.name}' is not part of '{inst.name}' (shield "
                f"'{inst.shield.name}'); it belongs to shield '{owner}'\n"
                f"referencable nodes of '{inst.shield.name}': {', '.join(inst.shield.names())}",
                [src_of(prop)])
            return None
        ends[key] = WireEnd(instance=inst, node=getattr(elem, "name"), src=src_of(prop))

    if "rig,route" in node.props:
        route = node.props["rig,route"].to_string()
    elif "rig,route-via" in node.props:
        route = node.props["rig,route-via"].to_num()
    else:
        diags.error("lang-wire", f"wire {node.name}: no rig,route / rig,route-via",
                    [src_of(node)])
        return None
    return Wire(frm=ends["rig,from"], to=ends["rig,to"], route=route, src=src_of(node))
