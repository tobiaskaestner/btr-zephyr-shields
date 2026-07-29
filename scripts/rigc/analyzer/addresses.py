"""Address allocation (R9/R17/R18, rigc-r4-brief.md Sec 2). Ported from
rigexp/analyzer.py's `_allocate_addresses`/`_allocate_scope`
(`analyzer.py:444-533`), value-shaped: per I2C-bus SCOPE (a mux channel is
a NEW scope, R26), fixed (copper `reg`) wins outright, pinned (R18 `pin:`
strap) resolves through the strap's own domain, and everything else is
allocated free from that same domain -- each in R18's stable `_key` order
(analyzer/ordering.py), never rig-file declaration order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..diag import Diagnostic, SourceRef, error
from ..model import BoardSocket, Device, Instance, Rig, Strap
from .ordering import allocation_key


@dataclass
class AddressAllocation:
    addr: Dict[Tuple[str, str], int] = field(default_factory=dict)         # (inst, dev) -> address
    straps: List[Tuple[Instance, Strap, int, int]] = field(default_factory=list)   # (inst, strap, state, addr)
    bus_label: Dict[str, str] = field(default_factory=dict)                # bus path -> label


def allocate_addresses(rig: Rig, sockets: Dict[str, BoardSocket],
                       ) -> Tuple[AddressAllocation, List[Diagnostic]]:
    diags: List[Diagnostic] = []
    result = AddressAllocation()
    scopes: Dict[str, List[Tuple[Instance, Device, BoardSocket]]] = {}
    for inst in rig.instances:
        socket = sockets.get(inst.name)
        if socket is None:
            continue
        for dev in inst.shield.devices:
            if dev.bus != "i2c" or "i2c" not in socket.buses:
                continue
            bus = socket.buses["i2c"]
            result.bus_label[bus.path] = bus.label
            scopes.setdefault(bus.path, []).append((inst, dev, socket))

    for bus_path, members in sorted(scopes.items()):
        diags += _allocate_scope(bus_path, members, result)
    return result, diags


def _allocate_scope(bus_path: str, members: List[Tuple[Instance, Device, BoardSocket]],
                    result: AddressAllocation) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    bus_label = result.bus_label[bus_path]
    taken: Dict[int, Tuple[Instance, Device, BoardSocket, str]] = {}

    def claim(addr: int, inst: Instance, dev: Device, socket: BoardSocket,
             how: str, src: Optional[SourceRef]) -> bool:
        if addr in taken:
            o_inst, o_dev, o_socket, o_how = taken[addr]
            diags.append(error(
                "phys-addr",
                f"I2C address {addr:#04x} is required twice on bus &{bus_label} "
                "(one address space per scope):\n"
                f"- {o_inst.name} (socket {o_socket.label}): {o_dev.name} — {o_how}\n"
                f"- {inst.name} (socket {socket.label}): {dev.name} — {how}\n"
                "two devices cannot share one address on one bus. This topology is "
                "not realizable as assembled: use a second I2C bus, put one device "
                "behind an I2C mux (scope creation, S8), or drop one instance.",
                tuple(x for x in (o_dev.src, o_inst.src, dev.src, inst.src) if x)))
            return False
        taken[addr] = (inst, dev, socket, how)
        result.addr[(inst.name, dev.name)] = addr
        return True

    fixed = []
    pinned = []
    free = []
    for inst, dev, socket in members:
        if dev.reg is not None:
            fixed.append((inst, dev, socket))
        elif dev.addr_from and dev.addr_from in inst.pins:
            pinned.append((inst, dev, socket))
        else:
            free.append((inst, dev, socket))

    for inst, dev, socket in sorted(fixed, key=lambda m: allocation_key(m[0], m[1])):
        assert dev.reg is not None
        claim(dev.reg, inst, dev, socket,
             f"address domain {{{dev.reg:#04x}}}, fixed by copper "
             "(no address-select)", dev.src)

    for inst, dev, socket in sorted(pinned, key=lambda m: allocation_key(m[0], m[1])):
        assert dev.addr_from is not None
        strap = inst.shield.straps[dev.addr_from]
        want = inst.pins[dev.addr_from]
        match = [(a, s) for a, s in strap.domain if a == want]
        if not match:
            diags.append(error(
                "phys-pin",
                f"instance '{inst.name}': pinned address {want:#04x} is not in the "
                f"domain of strap '{strap.name}' "
                f"({{{', '.join(f'{a:#04x}' for a, _ in strap.domain)}}}) — "
                "the copper cannot select it",
                tuple(x for x in (inst.pin_refs.get(dev.addr_from), strap.src) if x)))
            continue
        if claim(want, inst, dev, socket,
                f"pinned via rig (strap '{strap.name}')",
                inst.pin_refs.get(dev.addr_from)):
            result.straps.append((inst, strap, match[0][1], want))

    for inst, dev, socket in sorted(free, key=lambda m: allocation_key(m[0], m[1])):
        free_strap = inst.shield.straps.get(dev.addr_from) if dev.addr_from else None
        if free_strap is None:
            continue  # the loader already reported the addr-authority violation
        strap = free_strap
        pick = next(((a, s) for a, s in strap.domain if a not in taken), None)
        if pick is None:
            diags.append(error(
                "phys-addr",
                f"address domain of '{inst.name}/{dev.name}' is exhausted on bus "
                f"&{bus_label}: every selectable address "
                f"{{{', '.join(f'{a:#04x}' for a, _ in strap.domain)}}} is already "
                "taken by:\n"
                + "\n".join(f"- {t[0].name}: {t[1].name} at {a:#04x}"
                            for a, t in sorted(taken.items())),
                tuple(x for x in (dev.src, inst.src) if x)))
            continue
        if claim(pick[0], inst, dev, socket, f"allocated (strap '{strap.name}')",
                dev.src):
            result.straps.append((inst, strap, pick[1], pick[0]))
    return diags
