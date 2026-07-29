"""Base topology parsing and the V1b delta engine: instances, wires, and
the four delta operations (`instances:`, `add-instances:`,
`remove-instances:`, `add-wires:`/`remove-wires:`), all matched against
an in-memory EFFECTIVE topology. Diagnostic code is lang-variant or
lang-rev by STAGE, mirroring rigexp/loader_yml.py's own `_apply_delta`
dispatch.

**R2's ShieldRef seam is CLOSED** (rigc-r3-brief.md Sec 0): `shield:`
references resolve against a REAL `ShieldLibrary` (`loader/library.py`)
here, and `params:`/`pin:` are fully applied (`loader/params.py`) rather
than raising Unimplemented. Wire endpoints get their node-existence/
ambiguity check back too (`resolve_dotted`, via `Shield.by_name`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..deps import Deps, union
from ..diag import Diagnostic, SourceRef, error
from ..model import Instance, Wire, WireEnd
from .binding import SocketBinding
from .documents import Val, as_mapping, reject_metadata_keys, require
from .library import ShieldLibrary
from .params import apply_params_block, apply_pin_block, check_restate

log = logging.getLogger(__name__)


@dataclass
class Topology:
    """The rig's EFFECTIVE topology as the delta engine sees it: instances
    keyed by NAME, ORDER preserved separately, the wire list, and which
    STAGE VALUE last removed each now-absent instance name (removed_by --
    rule 8's drift-cannot-hide hint).

    `apply_delta` returns a NEW Topology rather than mutating this one in
    place: diagnostics stay the only thing composed as a side value,
    never a mutable accumulator -- and the same discipline extends
    naturally to the value the diagnostics accompany."""

    effective: Dict[str, Instance] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    wires: List[Wire] = field(default_factory=list)
    removed_by: Dict[str, str] = field(default_factory=dict)

    def instances(self) -> List[Instance]:
        return [self.effective[n] for n in self.order if n in self.effective]


def union_dt_includes(headers: List[str], refs: List[SourceRef],
                      dt_includes_v: Optional[Val],
                      ) -> Tuple[List[str], List[SourceRef]]:
    """dt-includes: UNIONS across delta stages -- a header already
    present (declared by an earlier stage) is skipped, keeping that
    stage's own SrcRef. Pure: returns NEW lists rather than mutating the
    caller's.

    Returns fresh (headers, refs) lists -- the inputs are copied,
    never extended in place."""
    headers = list(headers)
    refs = list(refs)
    if dt_includes_v is not None:
        for h_v in dt_includes_v.value:
            if h_v.value not in headers:
                headers.append(h_v.value)
                refs.append(h_v.src)
    return headers, refs


def parse_instance(item: Val, binding: SocketBinding, lib: ShieldLibrary,
                   rig_name: str, dt_includes: List[str], workdir: str,
                   include_dirs: Optional[List[str]] = None,
                   ) -> Tuple[Optional[Instance], List[Diagnostic], Deps]:
    """One `instances:` entry (base content, or an `add-instances:` item
    -- the identical shape): name/shield/socket required. `shield:`
    resolves against the REAL library (`lib.resolve`) -- the R2 seam this
    slice closes. `socket:` applies through the binding, `pin:`/`params:`
    apply fully against the resolved shield.

    Returns (instance, diagnostics, deps); instance is None when a
    required key is missing or the shield reference did not resolve.
    The caller owns the new Instance."""
    name_v, diags = require(item, "name", "instance")
    shield_v, d = require(item, "shield", "instance")
    diags += d
    socket_v, d = require(item, "socket", "instance")
    diags += d
    if name_v is None or shield_v is None or socket_v is None:
        return None, diags, frozenset()
    name = str(name_v.value)
    shield, d, deps = lib.resolve(shield_v.value, f"instance '{name}'", shield_v.src)
    diags += d
    if shield is None:
        return None, diags, deps

    inv_v = item.value.get("invert")
    pins, pin_refs, jumpers, jumper_refs, d = apply_pin_block(
        item.value.get("pin"), name, shield)
    diags += d
    tag = f"{rig_name}_{name}"
    params, param_refs, d = apply_params_block(
        item.value.get("params"), name, shield, dt_includes, rig_name,
        workdir, tag, include_dirs=include_dirs)
    diags += d

    inst = Instance(
        name=name, shield=shield, socket=binding.get(socket_v.value),
        invert=bool(inv_v.value) if inv_v is not None else False,
        pins=pins, pin_refs=pin_refs, jumpers=jumpers, jumper_refs=jumper_refs,
        params=params, param_refs=param_refs, src=item.src)
    log.debug("instance '%s': shield=%r socket=%r", name, shield.name, inst.socket)
    return inst, diags, deps


def _apply_instance_patch(item: Val, inst: Instance, binding: SocketBinding,
                          lib: ShieldLibrary, stage: str, stage_value: str,
                          variant: Optional[str], rig_name: str,
                          dt_includes: List[str], workdir: str,
                          include_dirs: Optional[List[str]] = None,
                          ) -> Tuple[Instance, List[Diagnostic], Deps]:
    """Shallow-replace an EXISTING instance's top-level keys: a GIVEN key
    REPLACES; an unspecified key INHERITS. shield/socket/invert/pin/params
    are each the deepest merge unit -- no key merges into what was there
    before, it wholesale replaces it. When shield changes, the OLD params
    are keyed to the OLD shield's devices and are therefore meaningless
    against the new one, so they are dropped rather than carried forward.

    Returns a NEW Instance (never mutates the one it was handed), always
    preserving the ORIGINAL `src` -- so a diagnostic raised many delta
    stages later still anchors at the base instance's own declaration,
    exactly as rigexp's in-place mutation does by never touching
    `inst.src`."""
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    shield = inst.shield
    shield_changed = False
    if "shield" in item.value:
        shield_v = item.value["shield"]
        new_shield, d, deps = lib.resolve(shield_v.value, f"instance '{inst.name}'",
                                         shield_v.src)
        diags += d
        if new_shield is None:
            return inst, diags, deps
        shield = new_shield
        shield_changed = True

    socket = inst.socket
    if "socket" in item.value:
        socket = binding.get(item.value["socket"].value)

    invert = inst.invert
    if "invert" in item.value:
        invert = bool(item.value["invert"].value)

    # NOTE: reproduced from the blueprint AS-IS (rigc-mission-brief.md
    # Sec 2's "reproduce first" discipline): a shield swap with no `pin:`
    # key alongside it leaves pins/jumpers referencing the OLD shield's
    # config elements untouched -- only params: is unconditionally reset
    # on a shield change. Revisiting this is a deliberate, post-green,
    # golden-changing decision, never something that happens en route.
    pins, pin_refs, jumpers, jumper_refs = (
        inst.pins, inst.pin_refs, inst.jumpers, inst.jumper_refs)
    if "pin" in item.value:
        pins, pin_refs, jumpers, jumper_refs, d = apply_pin_block(
            item.value["pin"], inst.name, shield)
        diags += d

    params, param_refs = inst.params, inst.param_refs
    if shield_changed:
        params, param_refs = {}, {}
    if "params" in item.value:
        params_v = item.value["params"]
        if not shield_changed:
            diags += check_restate(params_v, inst.params, inst.name)
        # rule 12: a family-wide revision's params landing on a device
        # the POST-VARIANT shield lacks needs the variant named.
        context = None
        if stage == "revision" and variant is not None:
            context = (f"this instance's shield is '{shield.name}' "
                      f"because of variant '{variant}'")
        tag = f"{rig_name}_{inst.name}"
        params, param_refs, d = apply_params_block(
            params_v, inst.name, shield, dt_includes, rig_name, workdir,
            tag, unknown_device_context=context, include_dirs=include_dirs)
        diags += d

    new_inst = Instance(
        name=inst.name, shield=shield, socket=socket, invert=invert,
        pins=pins, pin_refs=pin_refs, jumpers=jumpers, jumper_refs=jumper_refs,
        params=params, param_refs=param_refs, src=inst.src)
    log.debug("instance '%s': shield=%r socket=%r (%s stage '%s')",
             inst.name, shield.name, socket, stage, stage_value)
    return new_inst, diags, deps


def resolve_dotted(ref_v: Optional[Val], by_name: Dict[str, Instance],
                   key: str) -> Tuple[Optional[WireEnd], List[Diagnostic]]:
    """`<instance>.<node>` -- now fully validated (rigc-r3-brief.md Sec
    5): dotted FORM, instance EXISTENCE in the effective topology, and
    (closing the R2 deferral) node existence/ambiguity WITHIN that
    instance's own resolved shield, via `Shield.by_name`.

    Returns (end, diagnostics); end is None on every rejection shape."""
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
    inst = by_name.get(inst_name)
    if inst is None:
        return None, [error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' — no instance named '{inst_name}' in "
            f"this rig\ninstances: {', '.join(sorted(by_name))}",
            (ref_v.src,))]
    hits = inst.shield.by_name(node_name)
    if not hits:
        return None, [error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' — shield '{inst.shield.name}' has no "
            f"node '{node_name}'\nreferencable nodes of "
            f"'{inst.shield.name}': {', '.join(inst.shield.names())}",
            (ref_v.src,))]
    if len(hits) > 1:
        return None, [error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' is ambiguous within shield "
            f"'{inst.shield.name}' ({len(hits)} matches)", (ref_v.src,))]
    return WireEnd(instance_name=inst_name, node=node_name, src=ref_v.src), []


def parse_wire(item: Val, by_name: Dict[str, Instance],
              ) -> Tuple[Optional[Wire], List[Diagnostic]]:
    """One wires: entry -- both endpoints resolved (resolve_dotted),
    route shape validated (a mapping route must name via:).

    Returns (wire, diagnostics); wire is None when an endpoint or the
    route was rejected. The caller owns the new Wire."""
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


def find_wire(wires: List[Wire], frm: Optional[str],
             to: Optional[str]) -> Optional[Wire]:
    """Match `remove-wires:` by RAW endpoint pair (`<instance>.<node>`
    strings on both sides) -- a wire carries no identity beyond its
    endpoints, so this is the only stable way to find one to remove.
    Needs no shield data at all.

    Returns the first wire whose raw endpoint pair matches, else None;
    wires is read-only."""
    if frm is None or to is None:
        return None
    for w in wires:
        if (f"{w.frm.instance_name}.{w.frm.node}" == frm
                and f"{w.to.instance_name}.{w.to.node}" == to):
            return w
    return None


def apply_delta(delta: Val, stage: str, stage_value: str,
                topology: Topology, binding: SocketBinding, lib: ShieldLibrary,
                variant: Optional[str], rig_name: str, dt_includes: List[str],
                workdir: str, include_dirs: Optional[List[str]] = None,
                ) -> Tuple[Topology, List[Diagnostic], Deps]:
    """Apply ONE delta stage ("variant" or "revision") onto the topology,
    returning a NEW Topology plus every diagnostic raised plus every real
    file this stage's shield resolutions touched. `stage_value` is the
    selected axis value itself, folded into the rule-8 drift-hint
    wording. Metadata-key rejection (board:/sockets:) fires first, exactly
    as rigexp's own `_apply_delta` does. `variant` is the RIG's selected
    variant (rule 12's context, only meaningful when stage == "revision").

    Returns (topology, diagnostics, deps): a NEW Topology -- the input
    one is never mutated -- plus this stage's findings in document
    order and the files its shield resolutions touched."""
    code = "lang-variant" if stage == "variant" else "lang-rev"
    diags: List[Diagnostic] = list(reject_metadata_keys(delta))
    deps: Deps = frozenset()

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
            new_inst, d, idep = _apply_instance_patch(
                item, inst, binding, lib, stage, stage_value, variant,
                rig_name, dt_includes, workdir, include_dirs)
            diags += d
            deps = union(deps, idep)
            effective[name] = new_inst

    # add-instances: -- full declarations; the name must NOT already
    # exist.
    add_v = doc.get("add-instances")
    if add_v is not None:
        for item in add_v.value:
            added_inst, d, idep = parse_instance(
                item, binding, lib, rig_name, dt_includes, workdir, include_dirs)
            diags += d
            deps = union(deps, idep)
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
                    removed_by=removed_by), diags, deps
