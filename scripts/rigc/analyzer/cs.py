"""CS pool allocation (R4/R16, rigc-r4-brief.md Sec 2) -- the mission's
acid test: "where and how is the final cs-gpios property calculated?"
(mission brief Sec 6). Ported from rigexp/analyzer.py's `_allocate_cs`
(`analyzer.py:538-610`), split into the value-shaped contract the
blueprint's `_allocate_cs(rig, solved, types, diags)` hides:

  effective_cs_pool     -- the pool-MERGE fallback (one upstream source of
                            the four the ANALYSIS brief names): a socket's
                            own authored override wins, else the connector
                            type's binding default.
  allocate_cs_positions -- THE algorithm, and the part this module exists
                            to make unit-testable on its own: given an
                            ORDERED pool (as (position, net-identity)
                            pairs -- net identity, not a bare position
                            index, because two DIFFERENT sockets in one
                            SPI scope are compared through the SAME SoC
                            pin, R13), the net identities ALREADY taken,
                            and the scope's members in R18 allocation
                            order (some copper-fixed), assign each a
                            position or report the pool exhausted. No
                            Rig/Instance/Shield/Board needed to call it.
  allocate_cs           -- the PASS: walks rig.instances, groups SPI-bus
                            members into scopes (a mux channel is its own
                            scope, R26), builds each member's CsMember from
                            its resolved socket + connector type, and
                            folds the placements into cs/cs_gpios plus the
                            NEW net claims (for the composer to merge into
                            the shared net-claim map before the final
                            conflict check, analyzer/gpio.py's
                            `check_nets`)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from ..buskind import is_bus_kind
from ..diag import Diagnostic, error
from ..model import BoardSocket, ConnectorType, Device, Instance, Rig
from .gpio import NetClaim, NetKey, Nets, soc_net
from .ordering import allocation_key

log = logging.getLogger(__name__)


def effective_cs_pool(bus_cs_pool: Optional[List[int]],
                      type_default_pool: List[int]) -> List[int]:
    """The cs_pool None-if-absent merge (rigc-r4-brief.md Sec 2): a real
    board socket whose connector type's binding declares a cs-pool
    default for this bus already has it backfilled by edtlib
    (board_edt.py), making this merge inert there -- but a
    shield-SYNTHESIZED socket (carrier/mux composition, analyzer/
    sockets.py's `compose_socket`) comes from a plain dtlib parse with no
    binding-default backfill, so this is very much alive for that path."""
    return bus_cs_pool if bus_cs_pool is not None else type_default_pool


@dataclass(frozen=True)
class CsMember:
    """One SPI-scope member's CS-allocation input, already in R18
    allocation order by the time the caller builds a list of these:
    `identity` is opaque (used only for reporting which member exhausted
    its pool), `fixed` is (position, net-identity) when copper-fixed
    (`shield,cs-position`), else None and `pool` carries the member's OWN
    ordered (position, net-identity) candidates -- different members in
    one scope may draw from DIFFERENT pools (different sockets), which is
    exactly why the pool travels with the member rather than the call."""

    identity: str
    fixed: Optional[Tuple[int, object]] = None
    pool: Tuple[Tuple[int, object], ...] = ()


@dataclass(frozen=True)
class CsPlacement:
    identity: str
    position: int
    fixed: bool


def allocate_cs_positions(members: Sequence[CsMember], occupied: FrozenSet[object],
                          ) -> Tuple[List[CsPlacement], List[str]]:
    """THE acid-test contract (mission brief Sec 6, rigc-r4-brief.md Sec
    2): given an ordered pool, the already-taken net identities, and the
    members of one SPI scope in allocation order (some copper-fixed),
    assign each a position -- or report the pool exhausted. Copper-fixed
    members win OUTRIGHT (never consulted against the pool, never
    reported exhausted); everything else takes the first pool candidate
    whose net identity is not yet taken, checked against BOTH `occupied`
    and every identity already placed earlier IN THIS SAME CALL (matching
    the blueprint's single sequential pass, where each registration is
    visible to every later member of the scope, fixed or free alike).
    Returns (placements in input order, identities whose pool was
    exhausted)."""
    taken = set(occupied)
    placements: List[CsPlacement] = []
    exhausted: List[str] = []
    for m in members:
        if m.fixed is not None:
            pos, net_key = m.fixed
            placements.append(CsPlacement(m.identity, pos, True))
            taken.add(net_key)
            continue
        choice = next(((p, k) for p, k in m.pool if k not in taken), None)
        if choice is None:
            exhausted.append(m.identity)
            continue
        pos, net_key = choice
        placements.append(CsPlacement(m.identity, pos, False))
        taken.add(net_key)
    return placements, exhausted


@dataclass
class CsAllocation:
    cs: Dict[Tuple[str, str], Tuple[int, int]] = field(default_factory=dict)   # (inst, dev) -> (index, position)
    cs_gpios: Dict[str, List[Tuple[BoardSocket, int]]] = field(default_factory=dict)  # bus path -> [(socket, pos)]
    bus_label: Dict[str, str] = field(default_factory=dict)                   # bus path -> label
    nets: Nets = field(default_factory=dict)                                  # NEW claims only


def allocate_cs(rig: Rig, sockets: Dict[str, BoardSocket],
                types: Dict[str, ConnectorType], nets_before: Nets,
                ) -> Tuple[CsAllocation, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    result = CsAllocation()
    scopes: Dict[str, List[Tuple[Instance, Device, BoardSocket]]] = {}
    for inst in rig.instances:
        socket = sockets.get(inst.name)
        if socket is None:
            continue
        for dev in inst.shield.devices:
            if not is_bus_kind(dev.bus, "spi") or dev.bus not in socket.buses:
                continue
            bus = socket.buses[dev.bus]
            result.bus_label[bus.path] = bus.label
            scopes.setdefault(bus.path, []).append((inst, dev, socket))

    # A running view of CLAIMED NET KEYS, threaded sequentially across
    # scopes exactly as the blueprint's single solved.nets accumulator
    # would see them (a position claimed while processing one bus scope is
    # visible to the next) -- LOCAL to this one function call, never a
    # cross-module accumulator. A KEY SET, deliberately: only membership
    # is ever consulted (`occupied` below). The earlier shape --
    # `dict(nets_before)` -- shallow-copied the dict but SHARED the
    # per-key claim lists with the caller's gpio_result.nets, so the
    # append below mutated a value another pass had returned: the banned
    # accumulator shape reintroduced by an alias, duplicating every CS
    # claim that lands on an already-claimed net (R4 review, D1).
    seen: set[NetKey] = set(nets_before)

    for bus_path, raw_members in sorted(scopes.items()):
        members = sorted(raw_members, key=lambda m: allocation_key(m[0], m[1], m[2]))
        cs_members = []
        for inst, dev, socket in members:
            ctype = types[socket.type_name]
            identity = f"{inst.name}/{dev.name}"
            if dev.cs_position is not None:
                pos = dev.cs_position
                cs_members.append(CsMember(
                    identity=identity, fixed=(pos, soc_net(socket, pos))))
            else:
                assert dev.bus is not None   # narrowed by the scope-building filter above
                bus = socket.buses[dev.bus]
                pool = effective_cs_pool(bus.cs_pool, ctype.cs_pool.get(dev.bus, []))
                cs_members.append(CsMember(
                    identity=identity,
                    pool=tuple((p, soc_net(socket, p)) for p in pool)))

        occupied = frozenset(seen)
        placements, exhausted = allocate_cs_positions(cs_members, occupied)

        by_identity = {f"{inst.name}/{dev.name}": (inst, dev, socket)
                      for inst, dev, socket in members}
        for identity in exhausted:
            inst, dev, socket = by_identity[identity]
            ctype = types[socket.type_name]
            assert dev.bus is not None   # narrowed by the scope-building filter above
            bus = socket.buses[dev.bus]
            pool = effective_cs_pool(bus.cs_pool, ctype.cs_pool.get(dev.bus, []))
            diags.append(error(
                "phys-cs",
                f"CS pool of socket '{socket.label}' is exhausted for "
                f"'{identity}': candidates "
                f"{', '.join(ctype.posname(p) for p in pool)} are all claimed",
                tuple(x for x in (dev.src, inst.src) if x)))

        placed = []
        for placement in placements:
            inst, dev, socket = by_identity[placement.identity]
            ctype = types[socket.type_name]
            what = (f"{dev.name}: CS copper-fixed at {ctype.posname(placement.position)} "
                   "(shield,cs-position)" if placement.fixed else
                   f"{dev.name}: CS allocated at {ctype.posname(placement.position)}")
            log.debug("instance '%s': device '%s' allocated CS position %s (%s)",
                     inst.name, dev.name, placement.position,
                     "fixed" if placement.fixed else "pool")
            key = soc_net(socket, placement.position)
            claim = NetClaim(instance=inst, device=dev, what=what, role="dedicated",
                            socket=socket, position=placement.position, src=dev.src)
            result.nets.setdefault(key, []).append(claim)
            seen.add(key)
            placed.append((inst, dev, socket, placement.position))

        entries: List[Tuple[BoardSocket, int]] = []
        for index, (inst, dev, socket, pos) in enumerate(placed):
            result.cs[(inst.name, dev.name)] = (index, pos)
            if socket.gpio_map.get(pos) is None:     # must resolve to a real SoC pin
                ctype = types[socket.type_name]
                diags.append(error(
                    "phys-cs",
                    f"socket '{socket.label}' has no gpio-map entry for position "
                    f"{ctype.posname(pos)} — the board fragment "
                    "cannot route this CS",
                    tuple(x for x in (socket.src, dev.src) if x)))
                continue
            entries.append((socket, pos))            # emitted through the nexus
        result.cs_gpios[bus_path] = entries

    return result, diags
