"""Base topology parsing and the V1b delta engine: instances, wires, and
the four delta operations (`instances:`, `add-instances:`,
`remove-instances:`, `add-wires:`/`remove-wires:`), all matched against
an in-memory EFFECTIVE topology (rigc-r2-brief.md Sec 5). Diagnostic code
is lang-variant or lang-rev by STAGE, mirroring rigexp/loader_yml.py's own
`_apply_delta` dispatch.

**The ShieldRef seam** (rigc-r2-brief.md Sec 1): an instance's `shield:`
reference never resolves against real shield data here -- it constructs a
ShieldRef unconditionally. `params:`/`pin:` anywhere an instance is
described (base parse, a delta patch, or add-instances:) raise
Unimplemented immediately rather than silently doing nothing: the
machinery that would apply them (and the per-stage parameter invariant
re-checking them) is wholesale deferred to R3, and no R2 target uses
either (verified against the census, rigc-r2-brief.md Sec 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..diag import Diagnostic, SourceRef, error
from ..model import Instance, ShieldRef, Wire, WireEnd
from ..unimplemented import Unimplemented
from .binding import SocketBinding
from .documents import Val, as_mapping, reject_metadata_keys, require


@dataclass
class Topology:
    """The rig's EFFECTIVE topology as the delta engine sees it: instances
    keyed by NAME (matched/added/removed by name, Sec 5), ORDER preserved
    separately (a plain dict does not by itself survive add-then-remove
    reordering the way a corpus rig's own instance order must), the wire
    list, and which STAGE VALUE last removed each now-absent instance name
    (removed_by -- rule 8's drift-cannot-hide hint).

    `apply_delta` returns a NEW Topology rather than mutating this one in
    place: diagnostics stay the only thing composed as a side value,
    never a mutable accumulator (mission brief Sec 6) -- and the same
    discipline extends naturally to the value the diagnostics accompany."""

    effective: dict[str, Instance] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    removed_by: dict[str, str] = field(default_factory=dict)

    def instances(self) -> list[Instance]:
        return [self.effective[n] for n in self.order if n in self.effective]


def union_dt_includes(headers: list[str], refs: list[SourceRef],
                      dt_includes_v: Optional[Val],
                      ) -> tuple[list[str], list[SourceRef]]:
    """dt-includes: UNIONS across delta stages -- the one merge key with
    union semantics: a vocabulary is additive by nature, and a variant
    substituting a different shield legitimately needs a header the base
    never declared. A header already present (declared by an earlier
    stage) is skipped, keeping that stage's own SrcRef rather than the
    later one. Pure: returns NEW lists rather than mutating the caller's,
    so a rig's own progressive dt_includes/dt_includes_refs fields are
    reassigned at each call site instead of appended into."""
    headers = list(headers)
    refs = list(refs)
    if dt_includes_v is not None:
        for h_v in dt_includes_v.value:
            if h_v.value not in headers:
                headers.append(h_v.value)
                refs.append(h_v.src)
    return headers, refs


def _reject_instance_extras(item: Val, inst_name: str) -> None:
    """`params:`/`pin:` anywhere an instance is described raise
    Unimplemented immediately (rigc-r2-brief.md Sec 1): the machinery
    that would apply them is wholesale deferred to R3."""
    for key in ("params", "pin"):
        if key in item.value:
            raise Unimplemented(
                f"instance '{inst_name}': '{key}:' (needs the shield "
                "library, deferred to R3)")


def parse_instance(item: Val, binding: SocketBinding,
                   ) -> tuple[Optional[Instance], list[Diagnostic]]:
    """One `instances:` entry (base content, or an `add-instances:` item
    -- the identical shape): name/shield/socket required. `shield:`
    constructs a ShieldRef UNCONDITIONALLY (the seam -- never resolved
    against a library). `socket:` applies through the binding -- the ONE
    seam a SocketBinding is used at (rigc-r2-brief.md Sec 4)."""
    name_v, diags = require(item, "name", "instance")
    shield_v, d = require(item, "shield", "instance")
    diags += d
    socket_v, d = require(item, "socket", "instance")
    diags += d
    if name_v is None or shield_v is None or socket_v is None:
        return None, diags
    _reject_instance_extras(item, str(name_v.value))
    inv_v = item.value.get("invert")
    inst = Instance(
        name=name_v.value,
        shield=ShieldRef(ref=shield_v.value, src=shield_v.src),
        socket=binding.get(socket_v.value),
        invert=bool(inv_v.value) if inv_v is not None else False,
        src=item.src)
    return inst, diags


def _apply_instance_patch(item: Val, inst: Instance, binding: SocketBinding,
                          ) -> tuple[Instance, list[Diagnostic]]:
    """Shallow-replace an EXISTING instance's top-level keys: a GIVEN key
    REPLACES; an unspecified key INHERITS. Returns a NEW Instance (never
    mutates the one it was handed) so a delta stage's Topology stays a
    freshly constructed value, matching `apply_delta`'s own contract."""
    _reject_instance_extras(item, inst.name)
    shield = inst.shield
    if "shield" in item.value:
        shield_v = item.value["shield"]
        shield = ShieldRef(ref=shield_v.value, src=shield_v.src)
    socket = inst.socket
    if "socket" in item.value:
        socket = binding.get(item.value["socket"].value)
    invert = inst.invert
    if "invert" in item.value:
        invert = bool(item.value["invert"].value)
    return Instance(name=inst.name, shield=shield, socket=socket,
                    invert=invert, src=inst.src), []


def resolve_dotted(ref_v: Optional[Val], by_name: dict[str, Instance],
                   key: str) -> tuple[Optional[WireEnd], list[Diagnostic]]:
    """`<instance>.<node>` -- the RIG-SIDE half only (rigc-r2-brief.md
    Sec 1): dotted FORM, and instance EXISTENCE in the effective
    topology. Node existence/ambiguity within the instance's own shield
    needs shield data (deferred to R3 via ShieldRef) -- `node` is kept as
    the raw string, unvalidated; safe, since R2 has no accept path a
    wrong node name could silently reach."""
    if ref_v is None:
        return None, [error(
            "lang-schema", f"wire: required key '{key}' is missing", ())]
    ref = ref_v.value
    if not isinstance(ref, str) or "." not in ref:
        return None, [error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' is not an <instance>.<node> reference",
            (ref_v.src,))]
    inst_name, _, node_name = ref.partition(".")
    if inst_name not in by_name:
        return None, [error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' — no instance named '{inst_name}' in "
            f"this rig\ninstances: {', '.join(sorted(by_name))}",
            (ref_v.src,))]
    return WireEnd(instance_name=inst_name, node=node_name, src=ref_v.src), []


def parse_wire(item: Val, by_name: dict[str, Instance],
              ) -> tuple[Optional[Wire], list[Diagnostic]]:
    frm, diags = resolve_dotted(item.value.get("from"), by_name, "from")
    to, d = resolve_dotted(item.value.get("to"), by_name, "to")
    diags += d
    route_v = item.value.get("route")
    if frm is None or to is None or route_v is None:
        if route_v is None:
            diags.append(error(
                "lang-schema", "wire: required key 'route' is missing",
                (item.src,)))
        return None, diags
    if isinstance(route_v.value, dict):
        via_v = route_v.value.get("via")
        if via_v is None:
            diags.append(error(
                "lang-schema",
                "wire: route is a mapping but names no 'via' key",
                (route_v.src,)))
            return None, diags
        route = via_v.value
    else:
        route = route_v.value
    return Wire(frm=frm, to=to, route=route, src=item.src), diags


def find_wire(wires: list[Wire], frm: Optional[str],
             to: Optional[str]) -> Optional[Wire]:
    """Match `remove-wires:` by RAW endpoint pair (`<instance>.<node>`
    strings on both sides) -- a wire carries no identity beyond its
    endpoints, so this is the only stable way to find one to remove.
    Needs no shield data at all."""
    if frm is None or to is None:
        return None
    for w in wires:
        if (f"{w.frm.instance_name}.{w.frm.node}" == frm
                and f"{w.to.instance_name}.{w.to.node}" == to):
            return w
    return None


def apply_delta(delta: Val, stage: str, stage_value: str,
                topology: Topology, binding: SocketBinding,
                ) -> tuple[Topology, list[Diagnostic]]:
    """Apply ONE delta stage ("variant" or "revision") onto the topology,
    returning a NEW Topology plus every diagnostic raised. `stage_value`
    is the selected axis value itself, folded into the rule-8 drift-hint
    wording. Metadata-key rejection (board:/sockets:) fires first, exactly
    as rigexp's own `_apply_delta` does."""
    code = "lang-variant" if stage == "variant" else "lang-rev"
    diags: list[Diagnostic] = list(reject_metadata_keys(delta))

    effective = dict(topology.effective)
    order = list(topology.order)
    wires = list(topology.wires)
    removed_by = dict(topology.removed_by)

    doc = as_mapping(delta, f"{stage} delta {delta.src.file}")

    # instances: -- matched by name against the EFFECTIVE topology; a
    # non-match is always an error (additions are never implicit, that
    # is what add-instances: is for).
    instances_v = doc.get("instances")
    if instances_v is not None:
        for item in instances_v.value:
            name_v, d = require(item, "name", f"{stage} instances:")
            diags += d
            if name_v is None:
                continue
            name = name_v.value
            inst = effective.get(name)
            if inst is None:
                diags.append(error(
                    code,
                    f"{stage} '{stage_value}': instances: names '{name}', "
                    "which the effective topology does not have",
                    (item.src,)))
                continue
            new_inst, d = _apply_instance_patch(item, inst, binding)
            diags += d
            effective[name] = new_inst

    # add-instances: -- full declarations; the name must NOT already
    # exist.
    add_v = doc.get("add-instances")
    if add_v is not None:
        for item in add_v.value:
            added_inst, d = parse_instance(item, binding)
            diags += d
            if added_inst is None:
                continue
            if added_inst.name in effective:
                diags.append(error(
                    code,
                    f"{stage} '{stage_value}': add-instances: names "
                    f"'{added_inst.name}', which already exists",
                    (item.src,)))
                continue
            effective[added_inst.name] = added_inst
            order.append(added_inst.name)

    # remove-instances: -- names must exist; if a prior stage already
    # removed it, the message NAMES that stage so drift cannot hide.
    remove_v = doc.get("remove-instances")
    if remove_v is not None:
        for name_v in remove_v.value:
            name = name_v.value
            if name not in effective:
                prior = removed_by.get(name)
                hint = f" (variant '{prior}' already removed it)" if prior else ""
                diags.append(error(
                    code,
                    f"{stage} '{stage_value}': remove-instances: names "
                    f"'{name}', which does not exist{hint}",
                    (name_v.src,)))
                continue
            del effective[name]
            removed_by[name] = stage_value

    # remove-wires:/add-wires: -- matched by endpoint pair; a re-route is
    # remove+add, there is no wire "replace".
    remove_wires_v = doc.get("remove-wires")
    if remove_wires_v is not None:
        for item in remove_wires_v.value:
            frm_v = item.value.get("from")
            to_v = item.value.get("to")
            frm = frm_v.value if frm_v is not None else None
            to = to_v.value if to_v is not None else None
            match = find_wire(wires, frm, to)
            if match is None:
                diags.append(error(
                    code,
                    f"{stage} '{stage_value}': remove-wires: names "
                    f"{{from: {frm}, to: {to}}}, which does not exist",
                    (item.src,)))
                continue
            wires.remove(match)

    add_wires_v = doc.get("add-wires")
    if add_wires_v is not None:
        for item in add_wires_v.value:
            wire, d = parse_wire(item, effective)
            diags += d
            if wire is not None:
                wires.append(wire)

    return Topology(effective=effective, order=order, wires=wires,
                    removed_by=removed_by), diags
