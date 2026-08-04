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
    sockets: Dict[str, BoardSocket] = field(default_factory=dict)
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
                   parent: BoardSocket, inst_src: Optional[SourceRef],
                   ) -> Tuple[BoardSocket, List[Diagnostic], List[ScopeEntry]]:
    """Pass-through composition: exposed positions resolve to the parent's
    SoC pins, exposed buses to the parent's controllers (ontology Sec 1).
    Pure over its arguments -- no Instance/Rig/Shield needed, only the
    exposure and the ALREADY-resolved parent socket -- so this is directly
    unit-testable against synthetic ExposedSocket/BoardSocket values.

    Returns (socket, diagnostics, scopes): a NEW synthesized
    BoardSocket, the findings, and any scope entries the composition
    created. Its inputs are read-only; the caller owns all three."""
    diags: List[Diagnostic] = []
    scope_entries: List[ScopeEntry] = []
    gpio_map: Dict[int, Tuple[str, int, int]] = {}
    for pos, (parent_pos, _flags) in exposed.gpio_map.items():
        if parent_pos in parent.gpio_map:
            gpio_map[pos] = parent.gpio_map[parent_pos]
        # else: parent fragment doesn't route it -> stays socket-local (net key)
    buses: Dict[str, BusRef] = {}
    for kind, marker in exposed.buses.items():
        if marker == "plug":                            # pass-through (S6)
            if kind in parent.buses:
                buses[kind] = parent.buses[kind]
            else:
                refs = tuple(x for x in (exposed.src, parent.src, inst_src) if x)
                diags.append(error(
                    "phys-subset",
                    f"carrier '{carrier_name}' passes {kind.upper()} through socket "
                    f"'{exposed.name}', but its parent socket '{parent.label}' offers "
                    f"no socket,{kind} (R19 pass-through needs the parent to provide it)",
                    refs))
        else:                                           # new scope (S8): ("scope", dev-label)
            assert isinstance(marker, tuple)
            root = f"{carrier_name}_{marker[1]}"
            scope_path = socket_label                    # per (carrier, channel); shared by co-plugged modules
            buses[kind] = BusRef(label=f"{root}_ch{exposed.channel}", path=scope_path)
            scope_entries.append((scope_path, (root, exposed.channel)))
    parent_nexus = parent.nexus_label or parent.label
    nexus_rows = [(child_pos, parent_nexus, parent_pos)
                 for child_pos, (parent_pos, _f) in exposed.gpio_map.items()]
    cs_pool = exposed.cs_pool
    assert cs_pool is None or isinstance(cs_pool, list)
    socket = BoardSocket(
        label=socket_label, path=f"{parent.path}/{exposed.name}",
        type_name=exposed.type_name, gpio_map=gpio_map, buses=buses,
        cs_pool=cs_pool, src=exposed.src,
        nexus_label=f"{carrier_name}_{exposed.name}", nexus_rows=nexus_rows,
        parent=parent)
    return socket, diags, scope_entries


def resolve_sockets(rig: Rig, board: Board, types: Dict[str, ConnectorType],
                    ) -> Tuple[SocketResolution, List[Diagnostic]]:
    """The pass: `_check_matings`/`_resolve_socket` reproduced value-shaped.
    Returns the resolution (sockets + scopes) alongside every diagnostic,
    in the SAME order the blueprint's single accumulator would have
    emitted them (per-instance mating/subset checks in rig.instances
    order, recursing into not-yet-resolved carriers depth-first; the
    stackability sweep last, over sorted RESOLVED socket labels)."""
    diags: List[Diagnostic] = []
    sockets: Dict[str, BoardSocket] = {}
    scopes: Dict[str, Tuple[str, object]] = {}
    by_name = {i.name: i for i in rig.instances}
    # keyed by the RESOLVED socket's own label, never the reference string
    # that named it -- a board socket can be named by either its defining
    # label or a conventional alias (board-as-invocation-coordinate-brief.md
    # Sec 2.1), so two instances naming the SAME physical socket by
    # DIFFERENT strings must still land in the same bucket for the
    # exclusivity check below to see them.
    per_socket: Dict[str, List[Instance]] = {}

    def infer_socket(inst: Instance) -> Optional[BoardSocket]:
        """socket-inference-brief.md Sec 1/2: `mating_ok` run in REVERSE
        across every board socket, keeping the candidates instead of a
        boolean -- board sockets only, never a carrier's own exported
        ones (Sec 4: those come from instances, so the candidate set
        would change as instances are parsed, making inference
        order-dependent). Exactly one candidate resolves silently; zero
        or two-or-more is always an error, never a guess (Sec 1's
        strictness IS the design -- an implementation that picks between
        several reasonable candidates is wrong however sensible its
        tie-break looks)."""
        candidates = [s for s in board.sockets.values()
                     if mating_ok(inst.shield.plugs, s.type_name)]
        if not candidates:
            diags.append(error(
                "phys-socket",
                f"instance '{inst.name}': shield '{inst.shield.name}' plugs "
                f"'{inst.shield.plugs}', but no socket of board "
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
                f"instance '{inst.name}': shield '{inst.shield.name}' plugs "
                f"'{inst.shield.plugs}', which mates more than one socket "
                f"of board '{board.name}' -- add an explicit socket: to "
                "pick one\n"
                "candidates: " + ", ".join(s.label for s in candidates),
                (inst.src,) if inst.src else ()))
            return None
        return candidates[0]

    def resolve_one(inst: Instance, stack: Tuple[str, ...]) -> Optional[BoardSocket]:
        if inst.name in sockets:
            return sockets[inst.name]
        ref = inst.socket
        if ref is None:                                      # inferred board socket
            socket = infer_socket(inst)
            if socket is None:
                return None
            sockets[inst.name] = socket
            return socket
        if "." not in ref:                                  # board socket
            socket = board.resolve(ref)
            if socket is None:
                diags.append(error(
                    "phys-socket",
                    f"instance '{inst.name}': board '{board.name}' has no socket "
                    f"'{ref}'\n"
                    f"sockets of {board.name}: "
                    + ", ".join(f"{s.label} ({s.type_name})"
                                for s in board.sockets.values()),
                    (inst.src,) if inst.src else ()))
                return None
            sockets[inst.name] = socket
            return socket

        # carrier-exported socket: "<carrier instance>.<exposed socket>"
        carrier_name, _, exp_name = ref.partition(".")
        if inst.name in stack or carrier_name in stack:
            diags.append(error(
                "phys-socket",
                f"instance '{inst.name}': socket nesting is cyclic ({ref})",
                (inst.src,) if inst.src else ()))
            return None
        carrier = by_name.get(carrier_name)
        if carrier is None:
            diags.append(error(
                "phys-socket",
                f"instance '{inst.name}': socket '{ref}' names no instance "
                f"'{carrier_name}' in this rig\n"
                f"instances: {', '.join(sorted(by_name))}",
                (inst.src,) if inst.src else ()))
            return None
        parent = resolve_one(carrier, stack + (inst.name,))
        if parent is None:
            return None
        exposed = carrier.shield.exposes.get(exp_name)
        if exposed is None:
            diags.append(error(
                "phys-socket",
                f"instance '{inst.name}': carrier '{carrier_name}' (shield "
                f"'{carrier.shield.name}') exposes no socket '{exp_name}'\n"
                f"exposed sockets: {', '.join(sorted(carrier.shield.exposes)) or 'none'}",
                tuple(x for x in (inst.src, carrier.src) if x)))
            return None
        socket, d, scope_entries = compose_socket(
            ref, carrier.name, exposed, parent, inst.src)
        diags.extend(d)
        for path, entry in scope_entries:
            scopes[path] = entry
        sockets[inst.name] = socket
        return socket

    for inst in rig.instances:
        socket = resolve_one(inst, ())
        if socket is None:
            continue
        log.debug("instance '%s': resolved socket '%s' (%s)",
                 inst.name, socket.label, socket.type_name)
        if not mating_ok(inst.shield.plugs, socket.type_name):
            diags.append(error(
                "phys-mating",
                f"instance '{inst.name}': shield '{inst.shield.name}' plugs "
                f"'{inst.shield.plugs}' but socket '{socket.label}' is a "
                f"'{socket.type_name}' socket — the connectors do not mate",
                tuple(x for x in (inst.src, socket.src) if x)))
            continue
        per_socket.setdefault(socket.label, []).append(inst)

        # subset exposure (R20/S6): used proxies vs offered socket,<bus>
        used = {d.bus for d in inst.shield.devices if d.bus}
        for bus in subset_gaps(used, socket.buses):
            diags.append(error(
                "phys-subset",
                f"instance '{inst.name}': shield '{inst.shield.name}' needs the "
                f"socket's {bus.upper()} but '{socket.label}' does not expose "
                f"socket,{bus} (subset exposure is declared by absence)",
                tuple(x for x in (inst.src, socket.src) if x)))

    for label, insts in sorted(per_socket.items()):
        if len(insts) < 2:
            continue
        ctype = types[sockets[insts[0].name].type_name]
        if not ctype.stackable:
            diags.append(error(
                "phys-mating",
                f"{len(insts)} instances mate socket '{label}' but connector type "
                f"'{ctype.name}' takes exactly one module (not stackable): "
                + ", ".join(i.name for i in insts),
                tuple(i.src for i in insts if i.src)))

    return SocketResolution(sockets=sockets, scopes=scopes), diags
