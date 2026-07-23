# SPDX-License-Identifier: Apache-2.0
"""Board DT reader, edtlib-based (Bridge-A rewrite, phase 1 -- the READ side).

THE FLIP: this is now the PRODUCTION reader `boarddt.load_board` delegates
to. It projects a real board's own devicetree, read via a standalone
`edtlib.EDT` (see `edt_build.py`), onto `model.Board` / `model.BoardSocket`
(Conv. 4: "the expander reads the board DT to find socket nodes by
compatible"). `model.py` is FROZEN (saferail 9) -- this module only
populates it. Its predecessor, a bundled `common-dts` scaffold parsed
standalone with dtlib, is gone (saferail 8: deleted in full); a shadow
dual-read against it (saferail 2) proved this reader produces the exact same
`Board` on every rig-relevant axis, for all four board clones, before the
flip (see `tests/test_board_dualread.py`, now the production-plumbing guard
that replaced it).

pwm_map / adc_map (Bridge-A phase 2a) project the socket node's standard
`pwm-map` / `io-channel-map` nexuses -- read the same way `gpio-map` already
is, via `edtlib.Node.maps()` -- onto a position -> (controller label,
channel) shape (see
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

from .diag import SrcRef
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

    # NOTE (Bridge-A saferail 2, AMENDED, post-flip cs-pool merge investigation
    # 2026-07-23): edtlib back-fills the binding default here when the socket
    # doesn't author `socket,cs-pool` itself, PROVIDED the type's binding
    # declares the property with a `default:` (arduino-r3.yaml, mikrobus.yaml
    # both do). For those types this value is already the EFFECTIVE one, same
    # as the analyzer's own merge would compute (analyzer.py's
    # `socket.cs_pool if not None else ctype.cs_pool`) -- so for a REAL board
    # socket of such a type, `cs_pool` here is NEVER None and that merge's
    # ctype-fallback branch is inert.
    #
    # This does NOT make the analyzer's merge dead code in general, and this
    # function is not the only source of a `BoardSocket`: grove.yaml declares
    # no `socket,cs-pool` property at all (Grove never exposes SPI/CS), so a
    # grove socket's `cs_pool` stays None here too -- harmlessly, since
    # `_allocate_cs` never reaches a socket with no "spi" bus. More
    # significantly, `analyzer.py`'s carrier/mux composition
    # (`_compose_exposed_socket`) builds SYNTHESIZED `BoardSocket`s from
    # `model.ExposedSocket.cs_pool`, which comes from `shields.py` -- a plain
    # dtlib parse of the carrier `.shield` template with NO binding-default
    # backfill at all. A carrier that never authors `socket,cs-pool` on its
    # exposed socket node (arduino_uno_click, i2c_mux) yields `cs_pool=None`
    # there regardless of the connector type's binding default, so the
    # analyzer's ctype-fallback branch is very much alive for THAT path.
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
        pwm_map=pwm_map, adc_map=adc_map,
        src=SrcRef(node.filename, node.lineno, label))


def _controller_label(node: edtlib.Node) -> str:
    """The controller's own label for a `*-map` target, preferring the LAST
    one attached over the SoC dtsi's original (first) one: a socket-file
    alias attached after the fact (e.g. `adc0: &adc {};` in
    `grove_sockets_btr.dtsi`) is appended to `Node.labels` without
    displacing the primary label the SoC dtsi already gave the node
    (dtlib's label list is append-only, first-wins on duplicates, never
    reordered). Before THE FLIP, this projected onto the SAME label the
    (now-retired) common-dts scaffold's board stub used for that controller
    (dual-read comparability, saferail 2); both named one real node --
    single-labeled nodes (e.g. &tcc0) are unaffected, since labels[-1] ==
    labels[0] there.

    INVARIANT (review 2026-07-23): what this must return is the
    board-conventional alias the emitter will emit verbatim into overlays
    (`&adc0 ...`) -- "last-attached" is only a proxy for that, diverging
    from the `labels[0]` used for gpio/bus targets solely on RE-ALIASED
    nodes (today: lotus adc). It is order-fragile by construction: a later
    include attaching yet another label to a `*-map` target silently
    changes the emitted label, and now that common-dts is deleted (saferail
    8) nothing but tier-1 overlay text guards this floor label choice
    (tier-2 dts_equiv resolves labels away). Treat any change here as
    overlay-affecting, never cosmetic."""
    if not node.labels:
        raise ValueError(f"controller node {node.path} has no label")
    return node.labels[-1]
