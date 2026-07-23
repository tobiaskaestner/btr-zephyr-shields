# SPDX-License-Identifier: Apache-2.0
"""Board DT reader, edtlib-based (Bridge-A rewrite, phase 1 -- the READ side).

Projects a real board's own devicetree, read via a standalone
`edtlib.EDT` (see `edt_build.py`), onto the SAME `model.Board` /
`model.BoardSocket` dataclasses `boarddt.load_board` populates from the
common-dts scaffold (Conv. 4: "the expander reads the board DT to find
socket nodes by compatible"). `model.py` is FROZEN (saferail 9) -- this
module only populates it.

This is the SHADOW reader for saferail 2: during the rewrite, both this
module and `boarddt.py` read a board and their `Board` models are compared
for equality (see `tests/test_board_dualread.py`). It is not yet wired into
the production expander path -- `boarddt.load_board` stays the authority
until the whole corpus passes dual-read (saferail 2/6).

pwm_map / adc_map are intentionally left EMPTY here: the real board sockets
carry no standard `pwm-map`/`io-channel-map` nexus yet (that is Bridge-A
phase 2, "PWM/ADC via real nexuses" -- lotus/quail's multi-function routing
currently lives ONLY in the common-dts scaffold's `socket,pwm-map` /
`socket,adc-map`, a rig-model-only convention no real board node carries,
see `boards/seeed/seeeduino_lotus_btr/grove_sockets_btr.dtsi`'s NOTE).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, cast

# Import order matters: edt_build inserts zephyr's python-devicetree `src`
# onto sys.path as an import-time side effect (from $ZEPHYR_BASE), so it
# must be imported before `devicetree.edtlib` is reachable at all.
from .edt_build import BuildRecipe, build_edt
from devicetree import edtlib

from .model import Board, BoardSocket, BusRef

_BUS_PROPS = {"socket,i2c": "i2c", "socket,spi": "spi", "socket,uart": "uart"}


def load_board(name: str, dts_path: str, recipe: BuildRecipe,
               workdir: str) -> Board:
    """Build a standalone `edtlib.EDT` over the board's OWN `.dts`
    (`dts_path`, no rig overlay, no shield/app context) and project every
    `socket,*` node into a `model.Board` -- the edtlib-side counterpart of
    `boarddt.load_board`."""
    edt = build_edt(dts_path, recipe, workdir)
    return project_edt(edt, name)


def project_edt(edt: edtlib.EDT, name: str) -> Board:
    """Project an ALREADY-BUILT `edtlib.EDT` (fresh, or unpickled from a
    real build's `edt.pickle` -- saferail 3's cross-check) into a
    `model.Board`. Split out from `load_board` so both sides of that
    cross-check can share this exact projection."""
    sockets: Dict[str, BoardSocket] = {}
    for node in edt.nodes:
        compat = node.matching_compat
        if compat is None or not compat.startswith("socket,"):
            continue
        socket = _project_socket(node, compat)
        sockets[socket.label] = socket
    return Board(name=name, sockets=sockets)


def _project_socket(node: edtlib.Node, compat: str) -> BoardSocket:
    if not node.labels:
        raise ValueError(
            f"socket node {node.path} has no label -- rig,socket references "
            "sockets by label")
    label = node.labels[0]
    type_name = compat.split(",", 1)[1]

    gpio_map: Dict[int, Tuple[str, int, int]] = {}
    for entry in node.maps.get("gpio", []):
        pos, _pos_flags = entry.child_specifiers
        pin, flags = entry.parent_specifiers
        ctrl = entry.parent
        if not ctrl.labels:
            raise ValueError(f"gpio controller {ctrl.path} has no label")
        gpio_map[pos] = (ctrl.labels[0], pin, flags)

    buses: Dict[str, BusRef] = {}
    for prop_name, kind in _BUS_PROPS.items():
        prop = node.props.get(prop_name)
        if prop is None:
            continue
        bus_node = prop.val
        assert isinstance(bus_node, edtlib.Node)
        if not bus_node.labels:
            raise ValueError(f"bus controller {bus_node.path} has no label")
        buses[kind] = BusRef(label=bus_node.labels[0], path=bus_node.path)

    # NOTE (Bridge-A saferail 2, AMENDED): edtlib back-fills the binding
    # default here when the socket doesn't author `socket,cs-pool` (grove
    # doesn't even declare the property -- absent from node.props entirely).
    # This is EXPECTED and matches the analyzer's own effective-value merge
    # (analyzer.py:533: `socket.cs_pool if not None else ctype.cs_pool`) --
    # once backfilled, this value already IS the effective one; the dual-read
    # test computes the common-dts side's effective value the same way for
    # an apples-to-apples comparison.
    cs_pool: Optional[List[int]] = None
    cs_prop = node.props.get("socket,cs-pool")
    if cs_prop is not None:
        assert isinstance(cs_prop.val, list)
        cs_pool = cast(List[int], cs_prop.val)

    return BoardSocket(
        label=label, path=node.path, type_name=type_name,
        gpio_map=gpio_map, buses=buses, cs_pool=cs_pool)
