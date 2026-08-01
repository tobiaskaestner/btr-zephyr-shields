#!/usr/bin/env python3
"""Read the nucleo_ard socket node the edtlib way and compare against
boarddt.load_board's model."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from build_edt import build_edt  # noqa: E402

WORKDIR = os.path.join(os.path.dirname(__file__), "_work")


def edtlib_model():
    edt = build_edt(WORKDIR)
    (node,) = [n for n in edt.nodes if n.matching_compat == "socket,arduino-r3"]

    # --- gpio-map, via Node.maps (public edtlib API) ---
    gpio_map = {}
    for entry in node.maps.get("gpio", []):
        pos, _pos_flags = entry.child_specifiers
        pin, flags = entry.parent_specifiers
        ctrl_label = entry.parent.labels[0]
        gpio_map[pos] = (ctrl_label, pin, flags)

    # --- bus phandles, via normal typed Property (socket,i2c/spi/uart) ---
    buses = {}
    for prop_name, kind in (("socket,i2c", "i2c"), ("socket,spi", "spi"),
                            ("socket,uart", "uart")):
        prop = node.props.get(prop_name)
        if prop is not None:
            bus_node = prop.val
            buses[kind] = (bus_node.labels[0], bus_node.path)

    stackable = "socket,stackable" in node.props and node.props["socket,stackable"].val

    # --- binding-level facts (connector-type), via Binding.raw ---
    binding = node.binding
    cs_pool_default = binding.raw["properties"]["socket,cs-pool"]["default"]

    # AUTHORED-ONLY cs_pool, matching boarddt's BoardSocket.cs_pool contract
    # (None = not authored on THIS socket, else-type-default applied later by
    # the analyzer/ctypes_registry -- see analyzer.py:533). edtlib's typed
    # node.props always back-fills the binding default when default_prop_types
    # is on, so "authored vs defaulted" is invisible there; the raw dtlib node
    # (node._node, private-by-convention) still distinguishes them.
    cs_pool = (list(node.props["socket,cs-pool"].val)
               if "socket,cs-pool" in node._node.props else None)

    return {
        "label": node.labels[0],
        "path": node.path,
        "type_name": node.matching_compat.split(",", 1)[1],
        "gpio_map": gpio_map,
        "buses": buses,
        "stackable": stackable,
        "cs_pool": cs_pool,
    }


def boarddt_model():
    os.environ.setdefault("ZEPHYR_BASE", "/wrk/z/ws-up/zephyr-rigs")
    sys.path.insert(0, "/wrk/z/ws-up/btr-shields/scripts")
    from rigexp import boarddt
    from rigexp.diag import Diagnostics

    diags = Diagnostics()
    board = boarddt.load_board("nucleo_f401re_btr", os.path.join(WORKDIR, "boarddt"), diags)
    if board is None:
        print("boarddt errors:", diags)
        sys.exit(1)
    sock = board.sockets["nucleo_ard"]
    return {
        "label": sock.label,
        "path": sock.path,
        "type_name": sock.type_name,
        "gpio_map": sock.gpio_map,
        "buses": {k: (v.label, v.path) for k, v in sock.buses.items()},
        "cs_pool": sock.cs_pool,
    }


def main():
    edtm = edtlib_model()
    bdtm = boarddt_model()

    print("=== edtlib-derived model ===")
    for k, v in edtm.items():
        print(f"  {k}: {v}")
    print()
    print("=== boarddt.load_board model ===")
    for k, v in bdtm.items():
        print(f"  {k}: {v}")
    print()

    print("=== DIFF ===")
    ok = True

    if edtm["gpio_map"] != bdtm["gpio_map"]:
        ok = False
        print("gpio_map MISMATCH:")
        all_pos = sorted(set(edtm["gpio_map"]) | set(bdtm["gpio_map"]))
        for pos in all_pos:
            e = edtm["gpio_map"].get(pos)
            b = bdtm["gpio_map"].get(pos)
            if e != b:
                print(f"  pos {pos}: edtlib={e}  boarddt={b}")
    else:
        print(f"gpio_map: MATCH ({len(edtm['gpio_map'])} positions)")

    edt_labels = {k: v[0] for k, v in edtm["buses"].items()}
    bdt_labels = {k: v[0] for k, v in bdtm["buses"].items()}
    if edt_labels != bdt_labels:
        ok = False
        print("bus LABELS MISMATCH:", edt_labels, "vs", bdt_labels)
    else:
        print(f"bus labels (the emission target, &i2c1/&spi1): MATCH {edt_labels}")
    if edtm["buses"] != bdtm["buses"]:
        print("  (bus dtlib PATHS differ, expected: edtlib reads the real SoC tree "
              f"{edtm['buses']}, boarddt reads _soc-stubs.dtsi fakes {bdtm['buses']} "
              "-- path is only used by boarddt for scope identity within its own "
              "vendored tree, not compared cross-tree, so this is not a functional "
              "regression, just a side effect of retiring the stub)")

    if edtm["cs_pool"] != bdtm["cs_pool"]:
        ok = False
        print("cs_pool MISMATCH:", edtm["cs_pool"], "vs", bdtm["cs_pool"])
    else:
        print(f"cs_pool: MATCH {edtm['cs_pool']}")

    print()
    print("RESULT:", "MATCH" if ok else "MISMATCH")


if __name__ == "__main__":
    main()
