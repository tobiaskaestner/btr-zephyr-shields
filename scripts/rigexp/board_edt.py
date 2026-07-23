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

pwm_map / adc_map (Bridge-A phase 2a) project the socket node's standard
`pwm-map` / `io-channel-map` nexuses -- read the same way `gpio-map` already
is, via `edtlib.Node.maps()` -- onto the SAME position -> (controller label,
channel) shape `boarddt.load_board` derives from the common-dts scaffold's
`socket,pwm-map` / `socket,adc-map` (see
`boards/seeed/seeeduino_lotus_btr/grove_sockets_btr.dtsi`). Not every socket
carries these maps (only PWM/ADC-capable ones do); `node.maps` simply omits
the key for a `*-map` property the node doesn't author, so the loops below
are no-ops for sockets without one.
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

    pwm_map: Dict[int, Tuple[str, int]] = {}
    for entry in node.maps.get("pwm", []):
        pos, _pos_period = entry.child_specifiers
        channel, _channel_period = entry.parent_specifiers
        pwm_map[pos] = (_controller_label(entry.parent), channel)

    adc_map: Dict[int, Tuple[str, int]] = {}
    for entry in node.maps.get("io-channel", []):
        (pos,) = entry.child_specifiers
        (channel,) = entry.parent_specifiers
        adc_map[pos] = (_controller_label(entry.parent), channel)

    return BoardSocket(
        label=label, path=node.path, type_name=type_name,
        gpio_map=gpio_map, buses=buses, cs_pool=cs_pool,
        pwm_map=pwm_map, adc_map=adc_map)


def _controller_label(node: edtlib.Node) -> str:
    """The controller's own label for a `*-map` target, preferring the LAST
    one attached over the SoC dtsi's original (first) one: a socket-file
    alias attached after the fact (e.g. `adc0: &adc {};` in
    `grove_sockets_btr.dtsi`) is appended to `Node.labels` without
    displacing the primary label the SoC dtsi already gave the node
    (dtlib's label list is append-only, first-wins on duplicates, never
    reordered). This projects onto the SAME label the common-dts scaffold's
    board stub uses for that controller (dual-read comparability, saferail
    2) -- both name one real node; single-labeled nodes (e.g. &tcc0) are
    unaffected, since labels[-1] == labels[0] there.

    INVARIANT (review 2026-07-23): what this must return is the
    board-conventional alias the emitter will emit verbatim into overlays
    (`&adc0 ...`) -- "last-attached" is only a proxy for that, diverging
    from the `labels[0]` used for gpio/bus targets solely on RE-ALIASED
    nodes (today: lotus adc). It is order-fragile by construction: a later
    include attaching yet another label to a `*-map` target silently
    changes the emitted label, and once common-dts is deleted (saferail 8)
    the dual-read no longer guards this -- only tier-1 overlay text does
    (tier-2 dts_equiv resolves labels away). Treat any change here as
    overlay-affecting, never cosmetic."""
    if not node.labels:
        raise ValueError(f"controller node {node.path} has no label")
    return node.labels[-1]
