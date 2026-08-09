"""config-sheet.md -- the physical configuration sheet (R17). Ported from
rigexp/emitter.py's sheet half (rigc-r5-brief.md Sec 1): the ONE place a
symbol's resolved value is shown to a human; emission itself never
resolves anything (overlay.py emits params verbatim), so without this
table a rig-assigned INPUT_KEY_1 would mean nothing to a reader who has
not memorized the header.

**Reads `solved.wires`, never `rig.wires`** (rigc-r5-brief.md Sec 1): the
Wires section is the one place in this module a wire's raw `Rig` data
would silently diverge from what got resolved -- `solved.wires` carries
the route already resolved to a connector-type position index.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..analyzer import Solved
from ..dtsio import is_int_literal, resolve_token
from ..model import ConnectorType, Instance, Rig
from . import GEN


def _socket_display(inst: Instance, s: Solved) -> str:
    """The socket name a bench instruction shows: the instance's own
    declared reference wherever it authored one, else the label
    inference resolved to (socket-inference-brief.md Sec 7) --
    `s.sockets[inst.name]` is always present here, since the emitter
    only ever runs on an accepted rig where every instance's socket
    already resolved. Read-only over its arguments; returns a plain str
    the caller owns."""
    if inst.socket is not None:
        return inst.socket
    return s.sockets[inst.name].label


def render_sheet(rig: Rig, s: Solved, types: Dict[str, ConnectorType], workdir: str,
                 include_dirs: Optional[List[str]] = None) -> str:
    """config-sheet.md's full text. rig/s/types are read-only; returns a
    fresh string the caller owns. workdir/include_dirs feed the params
    table's own token resolution (a synthetic cpp/dtlib TU, the same
    mechanism the loader's own per-instance-parameter resolution uses --
    see dtsio.resolve_token)."""
    out = [f"# Physical configuration sheet — rig `{rig.name}`",
           "", f"<!-- {GEN} -->", "",
           f"Board: **{rig.board}**", "",
           "## Socket assignment", "",
           "| instance | shield | socket |", "|---|---|---|"]
    for inst in sorted(rig.instances, key=lambda i: i.name):
        out.append(f"| {inst.name} | {inst.shield.name} | {_socket_display(inst, s)} |")

    if s.straps or s.jumpers_set:
        out += ["", "## Straps / jumpers", ""]
        for inst, strap, state, addr in sorted(
                s.straps, key=lambda t: (t[0].name, t[1].name)):
            sheet = strap.sheet_label or strap.name
            out.append(
                f"- **{inst.name}** ({_socket_display(inst, s)}): set **{sheet}** to state "
                f"{state} → device address {addr:#04x}")
        for inst, jmp, jmp_state, pos in sorted(
                s.jumpers_set, key=lambda t: (t[0].name, t[1].name)):
            sheet = jmp.sheet_label or jmp.name
            posname = types[s.sockets[inst.name].type_name].posname(pos)
            out.append(
                f"- **{inst.name}** ({_socket_display(inst, s)}): set **{sheet}** to state "
                f"{jmp_state} → routed to pin {posname}")

    if s.channels:
        out += ["", "## PWM / analog pin-mux (board-provided pinctrl)", "",
                "The expander enables these controllers; the SoC pin-mux for "
                "each pin is board-provided and must be applied (stubbed):", ""]
        # keys are (instance NAME, device NAME, prop) strings, unlike the
        # Instance/Strap/Jumper OBJECTS the straps/jumpers loops above bind
        # -- named distinctly (inst_name/dev_name) so the two shapes never
        # share a variable name of two different types.
        for (inst_name, dev_name, prop), (fn, ctrl, ch, _p, _f, pos) in sorted(
                s.channels.items()):
            socket = s.sockets[inst_name]
            posname = types[socket.type_name].posname(pos)
            out.append(f"- {inst_name}/{dev_name} ({socket.label} {posname}) → "
                       f"{fn.upper()} {ctrl} ch{ch}: mux the pin to the controller")

    if s.wires:
        out += ["", "## Wires", ""]
        for w in s.wires:
            route = ("ad-hoc jumper wire (in no connector)"
                     if w.route == "adhoc" else f"via header position {w.route}")
            out.append(
                f"- connect **{w.frm.instance_name}.{w.frm.node}** → "
                f"**{w.to.instance_name}.{w.to.node}** — {route}")

    if s.cs:
        out += ["", "## Chip-selects", ""]
        for (inst_name, dev_name), (index, pos) in sorted(s.cs.items()):
            socket = s.sockets[inst_name]
            posname = types[socket.type_name].posname(pos)
            mapping = socket.gpio_map.get(pos)
            soc = f" → SoC {mapping[0]} pin {mapping[1]}" if mapping else ""
            out.append(f"- {inst_name}/{dev_name}: CS index {index}, {posname}{soc}")

    out += _params_table(rig, workdir, include_dirs)
    return "\n".join(out) + "\n"


def _params_table(rig: Rig, workdir: str,
                  include_dirs: Optional[List[str]] = None) -> List[str]:
    """Per-instance parameter assignments (rig-variants-revisions.md): the
    ONE place a symbol's resolved value is shown to a human -- emission
    itself never resolves anything, so without this table a rig-assigned
    INPUT_KEY_1 would mean nothing to a reader who has not memorized the
    header. Empty (no section at all) for every rig that assigns none,
    which is all but one of the corpus today.

    Each row resolves against its OWN device's declared_param_includes
    (param-vocabulary-brief.md) -- the vocabulary is the owning shield
    device's, never a rig-wide list, so two rows on different devices may
    resolve against entirely different headers."""
    rows = []
    for inst in sorted(rig.instances, key=lambda i: i.name):
        devices_by_label = {d.label: d for d in inst.shield.devices}
        for dev_label, props in sorted(inst.params.items()):
            for prop, value in sorted(props.items()):
                display = value
                if not is_int_literal(value):
                    dev = devices_by_label.get(dev_label)
                    headers = dev.declared_param_includes if dev is not None else []
                    tag = f"sheet_{inst.name}_{dev_label}_{prop}"
                    resolved = resolve_token(value, headers, workdir, tag,
                                            include_dirs)
                    if resolved is not None:
                        display = f"{value} ({resolved})"
                rows.append((inst.name, dev_label, prop, display))
    if not rows:
        return []
    out = ["", "## Parameters", "",
           "| instance | device | property | value |", "|---|---|---|---|"]
    for inst_name, dev_label, prop, display in rows:
        out.append(f"| {inst_name} | {dev_label} | {prop} | {display} |")
    return out
