"""Wires and emission feasibility of routes (`_check_wires`,
`analyzer.py:615-650`, rigc-r4-brief.md Sec 5). No frozen golden covers
this family (phys-wire) -- every diagnostic here falls under the
hand-differential rule (rigc-mission-brief.md Sec 2's standing
discipline, rigc-r2-brief.md Sec 6).

Value-shaped and non-mutating: the blueprint resolves a `route: via
<name>` string to its connector-type position INDEX by mutating
`wire.route` in place; this module instead returns a NEW list of Wire
values with the route already resolved, so the pass composes like every
other one here (`(its piece, diagnostics)`), never writing into a Rig it
was handed."""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..diag import Diagnostic, error
from ..model import BoardSocket, ConnectorType, Instance, Rig, Wire


def check_wires(rig: Rig, sockets: Dict[str, BoardSocket],
                types: Dict[str, ConnectorType],
                ) -> Tuple[List[Wire], List[Diagnostic]]:
    diags: List[Diagnostic] = []
    by_name: Dict[str, Instance] = {i.name: i for i in rig.instances}
    resolved: List[Wire] = []

    for wire in rig.wires:
        roles = []
        for end in (wire.frm, wire.to):
            inst = by_name.get(end.instance_name)
            pad = inst.shield.pads.get(end.node) if inst is not None else None
            if pad is None:
                diags.append(error(
                    "phys-wire",
                    f"wire end '{end.instance_name}.{end.node}' is not a pad — "
                    "only pads (arity-1 connectors) are wireable in the prototype",
                    (end.src,)))
                continue
            roles.append((end, pad.role))
        if len(roles) < 2:
            resolved.append(wire)
            continue

        drivers = [e for e, r in roles if r == "driver"]
        if len(drivers) != 1:
            claims = ", ".join(
                f"{e.instance_name}.{e.node} ({r})" for e, r in roles)
            diags.append(error(
                "phys-wire",
                f"a net needs exactly one driver and ≥1 listener (R22); "
                f"wire has {len(drivers)} drivers: {claims}",
                (wire.src,)))

        route = wire.route
        if isinstance(route, str) and route != "adhoc":
            # route: via <position name> -- resolved to the connector
            # type's own position INDEX, through the FROM end's socket.
            socket = sockets.get(wire.frm.instance_name)
            ctype = types[socket.type_name] if socket is not None else None
            if ctype is not None and route in ctype.positions:
                route = ctype.positions[route].index
            else:
                diags.append(error(
                    "phys-wire",
                    f"route 'via {route}': no such position on connector type "
                    f"'{ctype.name if ctype is not None else '?'}'", (wire.src,)))
        resolved.append(Wire(frm=wire.frm, to=wire.to, route=route, src=wire.src))
    return resolved, diags
