"""The analyzer: rig model + board -> solved rig (rigc-r4-brief.md Sec 2).

The blueprint's shape (`rigexp/analyzer.py`) is the counterexample the
mission brief Sec 6 was written against: a mutable `Solved` accumulator
threaded through seven passes, 20 of 23 functions taking `solved` and/or
`diags`. This package reproduces the BEHAVIOR (the frozen goldens) with
the OPPOSITE shape: each pass is a value function taking exactly the
prior pieces it needs and returning `(its piece, diagnostics)`; `analyze`
below is the ONE composing function that assembles the solved model, in
the blueprint's own pass order (`analyzer.py:91-99`) -- sockets -> gpio
nets -> addresses -> CS -> wires -> net conflicts -> labels.

**Skip-don't-abort** is the observable contract this composer preserves
structurally rather than by convention: a slot whose socket never
resolved (analyzer/sockets.py's `resolve_sockets`) is simply absent from
`resolution.sockets`, and every later pass already guards its own lookup
through the accessor family (analyzer/socketmap.py's `for_ref`/
`for_bus_device`) -- there is no separate "abort" path to avoid taking.

**Solved is the emitter's input contract** (Sec 2): a frozen value
(the blueprint's `Solved` minus `rig`/`board`/`types` -- those are
already in the emitter's own hands as inputs, not something the analyzer
need re-expose) the emitter slice consumes unchanged. One deliberate
addition beyond the blueprint's own field list: `wires`, holding the
ROUTE-RESOLVED wire list analyzer/wires.py returns -- the blueprint
stores this by mutating `wire.route` in place on the rig's own Wire
objects (banned here, Sec 6), so the resolved value needs a field of its
own for the emitter to read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..diag import Diagnostic
from ..model import (Board, BoardSocket, ConnectorType, Instance, Jumper,
                     Rig, Strap, Wire)
from .addresses import allocate_addresses
from .cs import allocate_cs
from .gpio import Nets, check_nets, collect_gpio_nets, merge_nets
from .labels import check_labels
from .sockets import resolve_sockets
from .wires import check_wires

__all__ = ["Solved", "analyze"]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Solved:
    """The solved model -- the emitter's input contract.

    Frozen: it is assembled exactly once, from the passes' returned
    pieces, and every consumer downstream is read-only. The freeze states
    that ownership in the type rather than in prose alone -- a pass
    rebinding a field on a model another pass already produced is this
    codebase's recurring failure mode, and here it is now a TypeError."""

    # instance -> slot -> socket (multi-plug-shield-brief.md Sec 3);
    # consumed ONLY through analyzer/socketmap.py's accessor family
    # (acceptance criterion 6) -- every downstream pass and emitter
    # module reaches a socket through `for_ref`/`for_bus_device`/
    # `for_slot`/`slots_of`, never a bare per-instance dict lookup of
    # this map's own two levels.
    sockets: Dict[str, Dict[str, BoardSocket]] = field(default_factory=dict)
    addr: Dict[Tuple[str, str], int] = field(default_factory=dict)         # (inst, dev) -> address
    straps: List[Tuple[Instance, Strap, int, int]] = field(default_factory=list)   # (inst, strap, state, addr)
    cs: Dict[Tuple[str, str], Tuple[int, int]] = field(default_factory=dict)       # (inst, dev) -> (index, position)
    cs_gpios: Dict[str, List[Tuple[BoardSocket, int]]] = field(default_factory=dict)  # bus path -> [(socket, pos)]
    bus_label: Dict[str, str] = field(default_factory=dict)                # bus path -> label
    nets: Nets = field(default_factory=dict)                               # net key -> [NetClaim]
    positions: Dict[Tuple[str, str, str], int] = field(default_factory=dict)       # (inst, dev, prop) -> resolved position
    jumpers_set: List[Tuple[Instance, Jumper, Optional[int], int]] = field(default_factory=list)
    channels: Dict[Tuple[str, str, str], Tuple[str, str, int, Optional[int], int, int]] = \
        field(default_factory=dict)                                        # (inst, dev, prop) -> (fn, ctrl, channel, period, flags, position)
    controllers: Dict[str, str] = field(default_factory=dict)              # ctrl label -> function (timer/adc to enable)
    scopes: Dict[str, Tuple[str, object]] = field(default_factory=dict)    # scope bus path -> (mux output label, channel) [R26]
    wires: List[Wire] = field(default_factory=list)                        # route-resolved (not on Solved in the blueprint, Sec 6)


def analyze(rig: Rig, board: Board, types: Dict[str, ConnectorType],
           ) -> Tuple[Solved, List[Diagnostic]]:
    """Run every pass over `rig` against the already-loaded `board`,
    composing their pieces into one Solved value. Board resolution itself
    (boarddt.load_board) happens BEFORE this is ever called -- its own
    failure is a `phys-board` diagnostic reported upstream (cli.py), never
    a None return from here: once a board is in hand, this composer
    always produces a Solved, even when passes along the way append
    errors (the caller decides whether to reject, exactly as the
    blueprint's own `analyze()` does -- `diags.errors` gates acceptance,
    not the return value's presence).

    Returns (solved, diagnostics): the Solved model, assembled once
    from the passes' returned pieces, plus every finding in pass
    order. The caller owns both; rig/board/types are read-only here."""
    diags: List[Diagnostic] = []

    log.info("analyze(): pass 'sockets'")
    resolution, d = resolve_sockets(rig, board, types)
    diags += d
    # instances whose mating failed are absent from resolution.sockets;
    # every later pass skips them individually rather than aborting the
    # whole rig.
    log.info("analyze(): pass 'gpio nets'")
    gpio_result, d = collect_gpio_nets(rig, resolution.sockets, types)
    diags += d
    log.info("analyze(): pass 'addresses'")
    addr_result, d = allocate_addresses(rig, resolution.sockets)
    diags += d
    log.info("analyze(): pass 'cs'")
    cs_result, d = allocate_cs(rig, resolution.sockets, types, gpio_result.nets)
    diags += d
    all_nets = merge_nets(gpio_result.nets, cs_result.nets)
    log.info("analyze(): pass 'wires'")
    wires, d = check_wires(rig, resolution.sockets, types)
    diags += d
    log.info("analyze(): pass 'net conflicts'")
    diags += check_nets(all_nets, types)
    log.info("analyze(): pass 'labels'")
    diags += check_labels(rig)

    solved = Solved(
        sockets=resolution.sockets,
        addr=addr_result.addr,
        straps=addr_result.straps,
        cs=cs_result.cs,
        cs_gpios=cs_result.cs_gpios,
        bus_label={**addr_result.bus_label, **cs_result.bus_label},
        nets=all_nets,
        positions=gpio_result.positions,
        jumpers_set=gpio_result.jumpers_set,
        channels=gpio_result.channels,
        controllers=gpio_result.controllers,
        scopes=resolution.scopes,
        wires=wires,
    )
    return solved, diags
