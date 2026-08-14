"""Mating and socket resolution, with carrier/mux composition (rigc-r4-brief.md
Sec 3). Ported from rigexp/analyzer.py's `_check_matings`/`_resolve_socket`/
`_compose_socket` (`analyzer.py:105-236`), value-shaped: `resolve_sockets`
returns the instance->BoardSocket map plus every mux-channel scope entry
composition creates, alongside its diagnostics -- no `Solved` accumulator,
no `diags` side channel.

Two pieces are pulled out as PURE value functions on their own (Sec 6's
"Mating/subset decision as a value function", "Socket composition ...
stack-guarded"):

  mating_ok / subset_gaps  -- plug-type-vs-socket-type and needed-vs-offered
                              bus decisions, each a one-line predicate over
                              plain strings/sets.
  compose_socket           -- (parent socket, exposure) -> synthesized
                              socket + scope entries, over PLAIN
                              ExposedSocket/BoardSocket values -- no
                              Instance/Rig/Shield needed to call it.

`resolve_sockets` is the pass: it walks `rig.instances`, recursing through
carrier chains (stack-guarded against cycles, memoizing into the returned
map exactly as the blueprint's `solved.sockets` memoizes), and folds in the
stackability check once every instance's socket is known. Skip-don't-abort
is structural here: an instance whose socket never resolves is simply
absent from the returned map, and every later pass (rigc-r4-brief.md's
observable contract) already skips a missing entry rather than aborting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ..buskind import bus_kind_of, is_bus_kind
from ..diag import Diagnostic, SourceRef, error
from ..model import (Board, BoardSocket, BusRef, ConnectorType, ExposedSocket,
                     Instance, Rig)

log = logging.getLogger(__name__)

#: One mux-channel scope this rig's composition created: scope PATH (the
#: composing instance's own socket reference string) -> (mux root label,
#: channel index) -- R26/R27.
ScopeEntry = Tuple[str, Tuple[str, object]]


@dataclass
class SocketResolution:
    # instance name -> slot name -> resolved socket (multi-plug-shield-
    # brief.md Sec 3): a slot absent from the inner map never resolved.
    # The single-plug form's own shape is one entry, `{"plug": socket}`.
    # Consumed ONLY through analyzer/socketmap.py's accessor family
    # (acceptance criterion 6) -- this pass, and this module's own
    # `resolve_sockets`, are the sole exception (they BUILD the map).
    sockets: Dict[str, Dict[str, BoardSocket]] = field(default_factory=dict)
    scopes: Dict[str, Tuple[str, object]] = field(default_factory=dict)


def mating_ok(plug_type: str, socket_type: str) -> bool:
    """R19/R20: a shield's plug type must equal the socket's own connector
    type -- the mating decision as a pure value function (rigc-r4-brief.md
    Sec 6)."""
    return plug_type == socket_type


def subset_gaps(needed: Set[str], offered: Iterable[str]) -> List[str]:
    """R20/S6: which of the buses a shield's devices actually use are NOT
    among the buses the socket exposes -- subset exposure is declared by
    ABSENCE (a socket offering no socket,uart rejects a uart-needing plug).
    Sorted so a caller renders a stable, deterministic list."""
    return sorted(needed - set(offered))


def compose_socket(socket_label: str, carrier_name: str, exposed: ExposedSocket,
                   parents: Dict[str, BoardSocket], inst_src: Optional[SourceRef],
                   ) -> Tuple[BoardSocket, List[Diagnostic], List[ScopeEntry]]:
    """Pass-through composition, now over SEVERAL named parents (multi-
    plug-carrier-brief.md Sec 3): exposed positions resolve to the NAMED
    parent's SoC pins, exposed buses to the named parent's controllers
    (ontology Sec 1) -- each gpio-map row and each pass-through bus
    carries its OWN slot, so a mixed-parent exposed socket routes
    different rows/buses through different parents. Pure over its
    arguments -- no Instance/Rig/Shield needed, only the exposure and the
    ALREADY-resolved parents (every one of the carrier's slots; the
    caller -- `resolve_one` -- guarantees this before ever calling in) --
    so this is directly unit-testable against synthetic ExposedSocket/
    BoardSocket values. `parents` has exactly one entry (slot "plug") for
    a single-plug carrier, which is what keeps that composition's output
    byte-identical to before plurality existed.

    A pass-through selects the named parent's bus of the same KIND, never
    an exact-name match -- the child-side qualified name (validated at
    parse time against the exposed type's own vocabulary) is independent
    of whatever the parent happens to call its own bus (Sec 2). A parent
    offering MORE than one bus of that kind is a loud, not-yet-supported
    ambiguity (phys-ambiguous-bus) rather than a guess.

    Returns (socket, diagnostics, scopes): a NEW synthesized
    BoardSocket, the findings, and any scope entries the composition
    created. Its inputs are read-only; the caller owns all three."""
    diags: List[Diagnostic] = []
    scope_entries: List[ScopeEntry] = []
    is_plural = len(parents) > 1

    gpio_map: Dict[int, Tuple[str, int, int]] = {}
    nexus_rows: List[Tuple[int, str, int]] = []
    for pos, (slot, parent_pos, _flags) in exposed.gpio_map.items():
        parent = parents[slot]
        nexus_rows.append((pos, parent.nexus_label or parent.label, parent_pos))
        if parent_pos in parent.gpio_map:
            gpio_map[pos] = parent.gpio_map[parent_pos]
        # else: parent fragment doesn't route it -> stays socket-local (net key)

    pwm_map, pwm_nexus_rows, pwm_cells, d = _compose_channel_map(
        "pwm", exposed.pwm_map, exposed.pwm_cells, carrier_name, exposed,
        parents, inst_src, is_plural)
    diags += d
    adc_map, adc_nexus_rows, adc_cells, d = _compose_channel_map(
        "adc", exposed.adc_map, exposed.adc_cells, carrier_name, exposed,
        parents, inst_src, is_plural)
    diags += d

    buses: Dict[str, BusRef] = {}
    for kind, marker in exposed.buses.items():
        assert isinstance(marker, tuple)
        if marker[0] == "plug":                          # pass-through (S6)
            slot = marker[1]
            parent = parents[slot]
            kind_query = bus_kind_of(kind) or kind
            candidates = sorted(b for b in parent.buses if is_bus_kind(b, kind_query))
            slot_note = f" (slot '{slot}')" if is_plural else ""
            refs = tuple(x for x in (exposed.src, parent.src, inst_src) if x)
            if len(candidates) > 1:
                diags.append(error(
                    "phys-ambiguous-bus",
                    f"carrier '{carrier_name}' passes {kind.upper()} through socket "
                    f"'{exposed.name}' from parent socket '{parent.label}'{slot_note}, "
                    f"which offers more than one {kind_query.upper()} bus "
                    f"({', '.join(candidates)}) -- ambiguous pass-through is not "
                    "supported yet",
                    refs))
            elif len(candidates) == 1:
                parent_bus = parent.buses[candidates[0]]
                buses[kind] = BusRef(
                    label=parent_bus.label, path=parent_bus.path,
                    cs_pool=exposed.cs_pool.get(kind))
            else:
                diags.append(error(
                    "phys-subset",
                    f"carrier '{carrier_name}' passes {kind.upper()} through socket "
                    f"'{exposed.name}', but its parent socket '{parent.label}'{slot_note} "
                    f"offers no socket,{kind} (R19 pass-through needs the parent to provide it)",
                    refs))
        else:                                           # new scope (S8): ("scope", dev-label)
            root = f"{carrier_name}_{marker[1]}"
            scope_path = socket_label                    # per (carrier, channel); shared by co-plugged modules
            buses[kind] = BusRef(label=f"{root}_ch{exposed.channel}", path=scope_path)
            scope_entries.append((scope_path, (root, exposed.channel)))

    # Single-parent path is BYTE-IDENTICAL to before plurality existed
    # (golden safety): the composed path is the parent's own path plus
    # the exposed node's name, exactly as today. A multi-parent
    # composition has no single parent path to anchor to, so it uses the
    # socket_label instead -- the <carrier>.<exposed> reference string,
    # unique per carrier instance and deterministic.
    if len(parents) == 1:
        (only_parent,) = parents.values()
        path = f"{only_parent.path}/{exposed.name}"
    else:
        path = socket_label

    socket = BoardSocket(
        label=socket_label, path=path,
        type_name=exposed.type_name, gpio_map=gpio_map, buses=buses,
        pwm_map=pwm_map, pwm_cells=pwm_cells,
        adc_map=adc_map, adc_cells=adc_cells,
        src=exposed.src,
        nexus_label=f"{carrier_name}_{exposed.name}", nexus_rows=nexus_rows,
        pwm_nexus_rows=pwm_nexus_rows, adc_nexus_rows=adc_nexus_rows,
        parents=dict(parents))
    return socket, diags, scope_entries


def _compose_channel_map(fn: str, exposed_map: Dict[int, Tuple[str, int, int]],
                         declared_cells: Optional[int], carrier_name: str,
                         exposed: ExposedSocket, parents: Dict[str, BoardSocket],
                         inst_src: Optional[SourceRef], is_plural: bool,
                         ) -> Tuple[Dict[int, Tuple[str, int]],
                                    List[Tuple[int, str, int]], Optional[int],
                                    List[Diagnostic]]:
    """The pwm/adc twin of `compose_socket`'s own gpio_map loop above,
    factored out because PWM and ADC need the IDENTICAL treatment (Sec 2:
    a branch for one function and a silent hole for the other is the
    exact shape of the b16c314 bug) at BOTH of the places gpio and
    pwm/adc genuinely differ:

      Ruling 2 -- a row whose parent does not route it is an ERROR here,
      never gpio_map's own "stays socket-local" silent drop: an unrouted
      analog position is not a meaningful net, it is a mistake.

      RULED require-and-check -- the carrier's own declared cell count
      (`declared_cells`, ExposedSocket.pwm_cells/.adc_cells) must equal
      the resolved parent's (BoardSocket.pwm_cells/.adc_cells) or the
      whole slot is refused up front, naming BOTH counts and BOTH sides
      (the carrier's shield name and the parent socket's own label) --
      checked ONCE per distinct slot a row actually draws from, not once
      per row, so a plural carrier passing several positions through one
      mismatched slot gets one finding, not N duplicates.

    `fn` is "pwm" or "adc"; `exposed_map`/`declared_cells` are that
    function's own ExposedSocket fields. Returns (composed map, nexus
    rows, this socket's OWN carried cell count, diagnostics) -- the cell
    count is None whenever nothing actually composed (mirrors nexus_rows
    being empty in the same case: a socket with no resolved rows for a
    function has no nexus to synthesize for it either, L3's own
    concern)."""
    diags: List[Diagnostic] = []
    if not exposed_map:
        return {}, [], None, diags

    prop = "pwm" if fn == "pwm" else "io-channel"
    parent_map_of = (lambda p: p.pwm_map) if fn == "pwm" else (lambda p: p.adc_map)
    parent_cells_of = (lambda p: p.pwm_cells) if fn == "pwm" else (lambda p: p.adc_cells)

    # RULED require-and-check, once per distinct slot referenced.
    bad_slots: Set[str] = set()
    for slot in sorted({slot for slot, _pp, _f in exposed_map.values()}):
        parent = parents[slot]
        parent_cells = parent_cells_of(parent)
        if parent_cells == declared_cells:
            continue
        bad_slots.add(slot)
        slot_note = f" (slot '{slot}')" if is_plural else ""
        refs = tuple(x for x in (exposed.src, parent.src, inst_src) if x)
        diags.append(error(
            "phys-subset",
            f"carrier '{carrier_name}' declares #{prop}-cells = <{declared_cells}> "
            f"on exposed socket '{exposed.name}', but its parent socket "
            f"'{parent.label}'{slot_note} declares #{prop}-cells = "
            f"<{parent_cells}> -- a carrier does not get to choose its own "
            "cell count, it inherits whatever the board it lands on declares",
            refs))

    composed: Dict[int, Tuple[str, int]] = {}
    nexus_rows: List[Tuple[int, str, int]] = []
    for pos, (slot, parent_pos, _filler) in exposed_map.items():
        if slot in bad_slots:
            continue
        parent = parents[slot]
        parent_map = parent_map_of(parent)
        if parent_pos not in parent_map:
            slot_note = f" (slot '{slot}')" if is_plural else ""
            refs = tuple(x for x in (exposed.src, parent.src, inst_src) if x)
            diags.append(error(
                "phys-subset",
                f"carrier '{carrier_name}' passes {fn.upper()} through socket "
                f"'{exposed.name}' at position {pos}, but its parent socket "
                f"'{parent.label}'{slot_note} does not route it there (no "
                f"{prop}-map entry at parent position {parent_pos})",
                refs))
            continue
        composed[pos] = parent_map[parent_pos]
        nexus_rows.append((pos, parent.nexus_label or parent.label, parent_pos))

    cells = declared_cells if composed else None
    return composed, nexus_rows, cells, diags


def _subject(inst: Instance, slot: str) -> str:
    """The diagnostic subject phrase for one (instance, slot): bare
    `instance '<name>'` for a single-slot shield (byte-identical to
    every diagnostic this module emitted before plurality existed --
    acceptance criterion 1), slot-qualified for a plural one (Sec 4's
    rendering rule). Pure: builds a string from its two arguments alone."""
    if len(inst.shield.plugs) > 1:
        return f"instance '{inst.name}': slot '{slot}'"
    return f"instance '{inst.name}'"


def resolve_sockets(rig: Rig, board: Board, types: Dict[str, ConnectorType],
                    ) -> Tuple[SocketResolution, List[Diagnostic]]:
    """The pass: `_check_matings`/`_resolve_socket` reproduced value-shaped,
    now PER SLOT (multi-plug-shield-brief.md Sec 4) -- inference, mating,
    and subset exposure each run once per (instance, slot), independently
    (no bipartite matching between two slots of one instance). Returns
    the resolution (sockets + scopes) alongside every diagnostic, in the
    SAME order the blueprint's single accumulator would have emitted them
    for a single-slot shield (per-instance, per-slot-in-authoring-order
    mating/subset checks in rig.instances order, recursing into
    not-yet-resolved carriers depth-first; the stackability sweep last,
    over sorted RESOLVED socket labels) -- criterion 1 holds by
    construction, since a single-slot shield's one slot is always named
    "plug" and iterates exactly once."""
    diags: List[Diagnostic] = []
    sockets: Dict[str, Dict[str, BoardSocket]] = {}
    scopes: Dict[str, Tuple[str, object]] = {}
    by_name = {i.name: i for i in rig.instances}
    # keyed by the RESOLVED socket's own label, never the reference string
    # that named it -- a board socket can be named by either its defining
    # label or a conventional alias (board-as-invocation-coordinate-brief.md
    # Sec 2.1), so two instances (or two slots of ONE instance) naming the
    # SAME physical socket by DIFFERENT strings must still land in the
    # same bucket for the exclusivity check below to see them.
    per_socket: Dict[str, List[Tuple[Instance, BoardSocket]]] = {}

    def infer_socket(inst: Instance, slot: str, plug_type: str) -> Optional[BoardSocket]:
        """socket-inference-brief.md Sec 1/2, now per slot: `mating_ok`
        run in REVERSE across every board socket for THIS slot's own
        connector type, keeping the candidates instead of a boolean --
        board sockets only, never a carrier's own exported ones (Sec 4:
        those come from instances, so the candidate set would change as
        instances are parsed, making inference order-dependent). Exactly
        one candidate resolves silently; zero or two-or-more is always an
        error, never a guess (Sec 1's strictness IS the design -- an
        implementation that picks between several reasonable candidates
        is wrong however sensible its tie-break looks). No bipartite
        matching between slots either: two same-type slots on a
        two-candidate board both refuse independently -- the explicit
        `sockets:` map is the answer, not a tie-break of this function's
        own."""
        subject = _subject(inst, slot)
        candidates = [s for s in board.sockets.values()
                     if mating_ok(plug_type, s.type_name)]
        if not candidates:
            diags.append(error(
                "phys-socket",
                f"{subject}: shield '{inst.shield.name}' plugs "
                f"'{plug_type}', but no socket of board "
                f"'{board.name}' offers a matching type -- add an explicit "
                "socket: to a socket of a different type, or use a "
                "different board\n"
                f"sockets of {board.name}: "
                + ", ".join(f"{s.label} ({s.type_name})"
                            for s in board.sockets.values()),
                (inst.src,) if inst.src else ()))
            return None
        if len(candidates) > 1:
            diags.append(error(
                "phys-socket",
                f"{subject}: shield '{inst.shield.name}' plugs "
                f"'{plug_type}', which mates more than one socket "
                f"of board '{board.name}' -- add an explicit socket: to "
                "pick one\n"
                "candidates: " + ", ".join(s.label for s in candidates),
                (inst.src,) if inst.src else ()))
            return None
        return candidates[0]

    def resolve_one(inst: Instance, slot: str, stack: Tuple[str, ...],
                    ) -> Optional[BoardSocket]:
        cached = sockets.get(inst.name, {}).get(slot)
        if cached is not None:
            return cached
        subject = _subject(inst, slot)
        ref = inst.sockets.get(slot)
        plug_type = inst.shield.plugs[slot]
        if ref is None:                                      # inferred board socket
            socket = infer_socket(inst, slot, plug_type)
            if socket is None:
                return None
            sockets.setdefault(inst.name, {})[slot] = socket
            return socket
        if "." not in ref:                                  # board socket
            socket = board.resolve(ref)
            if socket is None:
                diags.append(error(
                    "phys-socket",
                    f"{subject}: board '{board.name}' has no socket "
                    f"'{ref}'\n"
                    f"sockets of {board.name}: "
                    + ", ".join(f"{s.label} ({s.type_name})"
                                for s in board.sockets.values()),
                    (inst.src,) if inst.src else ()))
                return None
            sockets.setdefault(inst.name, {})[slot] = socket
            return socket

        # carrier-exported socket: "<carrier instance>.<exposed socket>"
        carrier_name, _, exp_name = ref.partition(".")
        if inst.name in stack or carrier_name in stack:
            diags.append(error(
                "phys-socket",
                f"{subject}: socket nesting is cyclic ({ref})",
                (inst.src,) if inst.src else ()))
            return None
        carrier = by_name.get(carrier_name)
        if carrier is None:
            diags.append(error(
                "phys-socket",
                f"{subject}: socket '{ref}' names no instance "
                f"'{carrier_name}' in this rig\n"
                f"instances: {', '.join(sorted(by_name))}",
                (inst.src,) if inst.src else ()))
            return None
        # A carrier's exposed socket may draw from ANY of its own plugs
        # (multi-plug-carrier-brief.md Sec 3) -- resolve EVERY slot the
        # carrier declares before composing, regardless of which ones the
        # NAMED exposed socket actually uses: any slot failing to resolve
        # fails the whole composition (skip-don't-abort, as today).
        parents: Dict[str, BoardSocket] = {}
        for carrier_slot in carrier.shield.plugs:
            parent = resolve_one(carrier, carrier_slot, stack + (inst.name,))
            if parent is None:
                return None
            parents[carrier_slot] = parent
        # resolved by the exposed node's DTS LABEL (item 30) -- the same
        # naming authority config:/params:/wires: already share (item 29);
        # a node name that differs from its own label no longer resolves.
        exposed = carrier.shield.exposed_socket(exp_name)
        if exposed is None:
            diags.append(error(
                "phys-socket",
                f"{subject}: carrier '{carrier_name}' (shield "
                f"'{carrier.shield.name}') exposes no socket '{exp_name}'\n"
                "exposed sockets: "
                + (', '.join(sorted(e.label for e in carrier.shield.exposes.values()))
                   or 'none'),
                tuple(x for x in (inst.src, carrier.src) if x)))
            return None
        socket, d, scope_entries = compose_socket(
            ref, carrier.name, exposed, parents, inst.src)
        diags.extend(d)
        for path, entry in scope_entries:
            scopes[path] = entry
        sockets.setdefault(inst.name, {})[slot] = socket
        return socket

    for inst in rig.instances:
        resolved_slots: Dict[str, BoardSocket] = {}
        for slot, plug_type in inst.shield.plugs.items():
            socket = resolve_one(inst, slot, ())
            if socket is None:
                continue
            log.debug("instance '%s': slot '%s': resolved socket '%s' (%s)",
                     inst.name, slot, socket.label, socket.type_name)
            resolved_slots[slot] = socket
            if not mating_ok(plug_type, socket.type_name):
                diags.append(error(
                    "phys-mating",
                    f"{_subject(inst, slot)}: shield '{inst.shield.name}' plugs "
                    f"'{plug_type}' but socket '{socket.label}' is a "
                    f"'{socket.type_name}' socket — the connectors do not mate",
                    tuple(x for x in (inst.src, socket.src) if x)))
                continue
            per_socket.setdefault(socket.label, []).append((inst, socket))

            # subset exposure (R20/S6): used proxies vs offered socket,<bus>,
            # per slot -- a bus needed only by ANOTHER slot must never be
            # demanded of this one's socket (Sec 4).
            used = {d.bus for d in inst.shield.devices if d.bus and d.plug == slot}
            for bus in subset_gaps(used, socket.buses):
                diags.append(error(
                    "phys-subset",
                    f"{_subject(inst, slot)}: shield '{inst.shield.name}' needs the "
                    f"socket's {bus.upper()} but '{socket.label}' does not expose "
                    f"socket,{bus} (subset exposure is declared by absence)",
                    tuple(x for x in (inst.src, socket.src) if x)))

        # Distinct slots of ONE instance must resolve to DISTINCT physical
        # sockets (Sec 4) -- one physical connector cannot take two plugs
        # at once. Checked regardless of the per-slot mating outcome
        # above: the impossibility is physical, not a function of whether
        # the connector TYPES happen to agree. The stackability census
        # below would only ever catch this as a non-stackable-type
        # collision, and with a message that counts "instances" rather
        # than slots -- a genuinely miscounting message for this case,
        # which is exactly why this gets its own, precise diagnostic.
        if len(resolved_slots) > 1:
            by_label: Dict[str, List[str]] = {}
            for slot, socket in resolved_slots.items():
                by_label.setdefault(socket.label, []).append(slot)
            for label, slots in sorted(by_label.items()):
                if len(slots) > 1:
                    diags.append(error(
                        "phys-socket",
                        f"instance '{inst.name}': slots "
                        f"{', '.join(repr(s) for s in sorted(slots))} both "
                        f"resolve to physical socket '{label}' — one "
                        "physical connector cannot take two plugs at once",
                        (inst.src,) if inst.src else ()))

    for label, entries in sorted(per_socket.items()):
        if len(entries) < 2:
            continue
        ctype = types[entries[0][1].type_name]
        if not ctype.stackable:
            diags.append(error(
                "phys-mating",
                f"{len(entries)} instances mate socket '{label}' but connector type "
                f"'{ctype.name}' takes exactly one module (not stackable): "
                + ", ".join(inst.name for inst, _socket in entries),
                tuple(inst.src for inst, _socket in entries if inst.src)))

    return SocketResolution(sockets=sockets, scopes=scopes), diags
