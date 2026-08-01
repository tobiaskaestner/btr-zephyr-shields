"""Board DT reader — expander-side input (Conv. 4: 'the expander reads the
board DT to find socket nodes by compatible'). In the real build these
nodes live in the board's own devicetree and are edtlib-validated; the
trial parses the board fragment + SoC stubs standalone with dtlib.
"""
from __future__ import annotations

import os

from .diag import Diagnostic, Diagnostics, LoadError
from .dtsio import COMMON, dtlib, parse_tu, src_of, words
from .model import Board, BoardSocket, BusRef

BOARDS = os.path.join(COMMON, "boards")

_BUS_PROPS = {"socket,i2c": "i2c", "socket,spi": "spi", "socket,uart": "uart"}


def known_boards() -> list[str]:
    return sorted(
        f[: -len(".rig.dtsi")] for f in os.listdir(BOARDS)
        if f.endswith(".rig.dtsi") and not f.startswith("_"))


def load_board(name: str, workdir: str, diags: Diagnostics) -> Board | None:
    """None (+ diagnostic) if the board is unknown — the rig,board string is
    a cross-tree reference, so this is the earliest it can be checked."""
    frag = os.path.join(BOARDS, f"{name}.rig.dtsi")
    if not os.path.isfile(frag):
        diags.error(
            "phys-board",
            f"unknown board '{name}'\n"
            f"no rig-enabled board DT found ({os.path.relpath(frag)})\n"
            f"rig-enabled boards: {', '.join(known_boards())}")
        return None

    dt = parse_tu([os.path.join(BOARDS, "_soc-stubs.dtsi"), frag],
                  workdir, f"board-{name}.dts")

    sockets: dict[str, BoardSocket] = {}
    for node in dt.node_iter():
        compat = node.props.get("compatible")
        if not compat or not compat.to_string().startswith("socket,"):
            continue
        type_name = compat.to_string().split(",", 1)[1]

        gpio_map = {}
        for entry in _gpio_map_entries(node):
            child_pin, _child_flags, phandle, parent_pin, parent_flags = entry
            ctrl = dt.phandle2node[phandle]
            gpio_map[child_pin] = (ctrl.labels[0], parent_pin, parent_flags)

        buses = {}
        for prop_name, kind in _BUS_PROPS.items():
            if prop_name in node.props:
                bus_node = node.props[prop_name].to_node()
                buses[kind] = BusRef(label=bus_node.labels[0], path=bus_node.path)

        cs_pool = None
        if "socket,cs-pool" in node.props:
            cs_pool = list(node.props["socket,cs-pool"].to_nums())

        # multi-function nexus (Slice A): position -> (controller, channel) for
        # the pwm / adc function-views, alongside gpio-map's position -> pin.
        pwm_map = {}
        for pos, _f, phandle, chan, _cf in _map_entries(node, "socket,pwm-map"):
            pwm_map[pos] = (dt.phandle2node[phandle].labels[0], chan)
        adc_map = {}
        for pos, _f, phandle, chan, _cf in _map_entries(node, "socket,adc-map"):
            adc_map[pos] = (dt.phandle2node[phandle].labels[0], chan)

        if not node.labels:
            raise LoadError(Diagnostic(
                "error", "phys-board",
                f"socket node {node.path} in board '{name}' has no label — "
                "rig,socket references sockets by label", [src_of(node)]))
        sockets[node.labels[0]] = BoardSocket(
            label=node.labels[0], path=node.path, type_name=type_name,
            gpio_map=gpio_map, buses=buses, cs_pool=cs_pool,
            pwm_map=pwm_map, adc_map=adc_map, src=src_of(node))

    return Board(name=name, sockets=sockets)


def _gpio_map_entries(node: dtlib.Node):
    return _map_entries(node, "gpio-map")


def _map_entries(node: dtlib.Node, prop: str):
    """Nexus map rows: <position pos_flags &ctrl out_index out_flags>. Uniform
    5-cell rows (the trial's socket,pwm-map / socket,adc-map are rig-model data
    read here, not dtc nexuses; gpio-map is the real thing, same shape)."""
    if prop not in node.props:
        return
    cells = words(node.props[prop])
    if len(cells) % 5:
        raise LoadError(Diagnostic(
            "error", "phys-board",
            f"{prop} of {node.path} is not made of 5-cell rows", [src_of(node)]))
    for i in range(0, len(cells), 5):
        yield cells[i:i + 5]
