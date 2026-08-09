"""expectations.yml (A6): a runtime-harness stub naming what must be
observed on real hardware. Ported from rigexp/emitter.py's expectations
half (rigc-r5-brief.md Sec 1) -- emitted for every accepted rig, gated by
no golden (test_emitted_corpus.py's own docstring: "expectations.yml is
deliberately excluded -- it is emitted but never gated").

**Reads `solved.wires`, never `rig.wires`** (rigc-r5-brief.md Sec 1) --
same reasoning as sheet.py's Wires section.
"""
from __future__ import annotations

from ..analyzer import Solved
from ..model import Rig
from . import GEN


def _bus_name(rig: Rig, inst_name: str, dev_name: str, default: str) -> str:
    """The qualified Device.bus name recorded for (inst_name, dev_name),
    recovered by name since Solved.addr/Solved.cs key by plain strings,
    never the Device object itself. Falls back to `default` (the bare
    kind) when `rig` carries no matching Instance/Device -- this
    function is also called against a synthetic Solved built directly
    for a test, with no backing rig content at all; every ENTRY a real
    analyzer run actually produces always has a matching device, so the
    fallback is inert on that path."""
    inst = next((i for i in rig.instances if i.name == inst_name), None)
    if inst is None:
        return default
    dev = next((d for d in inst.shield.devices if d.name == dev_name), None)
    if dev is None or dev.bus is None:
        return default
    return dev.bus


def render_expectations(rig: Rig, s: Solved) -> str:
    """expectations.yml's full text. rig/s are read-only; returns a fresh
    string the caller owns."""
    out = [f"# {GEN}",
           "# test expectations stub (A6): what a runtime harness must observe",
           f"rig: {rig.name}", f"board: {rig.board}", "expect:"]
    for (inst, dev), addr in sorted(s.addr.items()):
        socket = s.sockets[inst]
        bus = _bus_name(rig, inst, dev, "i2c")
        out.append(f"  - {{instance: {inst}, device: {dev}, "
                   f"bus: {socket.buses[bus].label}, address: {addr:#04x}, "
                   "check: probe}")
    for (inst, dev), (index, _pos) in sorted(s.cs.items()):
        socket = s.sockets[inst]
        bus = _bus_name(rig, inst, dev, "spi")
        out.append(f"  - {{instance: {inst}, device: {dev}, "
                   f"bus: {socket.buses[bus].label}, cs-index: {index}, "
                   "check: probe}")
    for w in s.wires:
        out.append(f"  - {{signal: {w.frm.instance_name}.{w.frm.node} -> "
                   f"{w.to.instance_name}.{w.to.node}, check: manual}}")
    return "\n".join(out) + "\n"
