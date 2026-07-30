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


def render_expectations(rig: Rig, s: Solved) -> str:
    """expectations.yml's full text. rig/s are read-only; returns a fresh
    string the caller owns."""
    out = [f"# {GEN}",
           "# test expectations stub (A6): what a runtime harness must observe",
           f"rig: {rig.name}", f"board: {rig.board}", "expect:"]
    for (inst, dev), addr in sorted(s.addr.items()):
        socket = s.sockets[inst]
        out.append(f"  - {{instance: {inst}, device: {dev}, "
                   f"bus: {socket.buses['i2c'].label}, address: {addr:#04x}, "
                   "check: probe}")
    for (inst, dev), (index, _pos) in sorted(s.cs.items()):
        socket = s.sockets[inst]
        out.append(f"  - {{instance: {inst}, device: {dev}, "
                   f"bus: {socket.buses['spi'].label}, cs-index: {index}, "
                   "check: probe}")
    for w in s.wires:
        out.append(f"  - {{signal: {w.frm.instance_name}.{w.frm.node} -> "
                   f"{w.to.instance_name}.{w.to.node}, check: manual}}")
    return "\n".join(out) + "\n"
