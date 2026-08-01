#!/usr/bin/env python3
"""Spike 2a: read the REAL lotus grove socket nodes' pwm-map/io-channel-map
the edtlib way (via Node.maps, the public API) and compare position ->
(controller, channel) against boarddt.load_board's common-dts model
(socket,pwm-map / socket,adc-map) for seeeduino_lotus_btr."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from build_edt import build_edt  # noqa: E402

WORKDIR = os.path.join(os.path.dirname(__file__), "_work")

# GROVE_SIG0 = 0, GROVE_SIG1 = 1 (dt-bindings/connector/grove.h)
SIG_NAME = {0: "SIG0", 1: "SIG1"}


def edtlib_model():
    edt = build_edt(WORKDIR)
    sockets = [n for n in edt.nodes if n.matching_compat == "socket,grove"]

    pwm_map = {}   # socket_label -> {pos: (ctrl_label, channel)}
    adc_map = {}   # socket_label -> {pos: (ctrl_label, channel)}

    for node in sockets:
        label = node.labels[0]

        pwm_entries = node.maps.get("pwm", [])
        if pwm_entries:
            m = {}
            for entry in pwm_entries:
                pos, _period_placeholder = entry.child_specifiers
                channel, _period_placeholder2 = entry.parent_specifiers
                m[pos] = (entry.parent.labels[0], channel)
            pwm_map[label] = m

        io_entries = node.maps.get("io-channel", [])
        if io_entries:
            m = {}
            for entry in io_entries:
                (pos,) = entry.child_specifiers
                (channel,) = entry.parent_specifiers
                # entry.parent.labels[0] is the node's PRIMARY label ("adc",
                # from the real SAMD21 SoC dtsi) -- "adc0" is an ADDITIVE
                # second label attached in grove_sockets_btr.dtsi (same real
                # node, `adc0: &adc {};`), matching the name boarddt's
                # common-dts stub uses. Prefer it when present so the compare
                # is against the same real controller by the label boarddt
                # knows it as (non-functional: both labels name one node).
                labels = entry.parent.labels
                ctrl_label = "adc0" if "adc0" in labels else labels[0]
                m[pos] = (ctrl_label, channel)
            adc_map[label] = m

    return {"pwm_map": pwm_map, "adc_map": adc_map}


def boarddt_model():
    os.environ.setdefault("ZEPHYR_BASE", "/wrk/z/ws-up/zephyr-rigs")
    sys.path.insert(0, "/wrk/z/ws-up/btr-shields/scripts")
    from rigexp import boarddt
    from rigexp.diag import Diagnostics

    diags = Diagnostics()
    board = boarddt.load_board("seeeduino_lotus_btr", os.path.join(WORKDIR, "boarddt"), diags)
    if board is None:
        print("boarddt errors:", diags)
        sys.exit(1)

    pwm_map = {label: sock.pwm_map for label, sock in board.sockets.items() if sock.pwm_map}
    adc_map = {label: sock.adc_map for label, sock in board.sockets.items() if sock.adc_map}
    return {"pwm_map": pwm_map, "adc_map": adc_map}


def fmt_map(m):
    lines = []
    for label, positions in sorted(m.items()):
        for pos, (ctrl, chan) in sorted(positions.items()):
            lines.append(f"    {label}.{SIG_NAME.get(pos, pos)} -> {ctrl} ch{chan}")
    return "\n".join(lines) if lines else "    (empty)"


def main():
    edtm = edtlib_model()
    bdtm = boarddt_model()

    print("=== edtlib Node.maps()-derived model (real board nexuses) ===")
    print("  pwm_map:")
    print(fmt_map(edtm["pwm_map"]))
    print("  adc_map (via io-channel-map):")
    print(fmt_map(edtm["adc_map"]))
    print()
    print("=== boarddt.load_board model (common-dts socket,pwm-map/socket,adc-map) ===")
    print("  pwm_map:")
    print(fmt_map(bdtm["pwm_map"]))
    print("  adc_map:")
    print(fmt_map(bdtm["adc_map"]))
    print()

    print("=== DIFF ===")
    ok = True

    if edtm["pwm_map"] != bdtm["pwm_map"]:
        ok = False
        print("pwm_map MISMATCH:")
        all_labels = sorted(set(edtm["pwm_map"]) | set(bdtm["pwm_map"]))
        for label in all_labels:
            e = edtm["pwm_map"].get(label)
            b = bdtm["pwm_map"].get(label)
            if e != b:
                print(f"  {label}: edtlib={e}  boarddt={b}")
    else:
        print(f"pwm_map: MATCH ({sum(len(v) for v in edtm['pwm_map'].values())} positions "
              f"across {len(edtm['pwm_map'])} sockets)")

    if edtm["adc_map"] != bdtm["adc_map"]:
        ok = False
        print("adc_map MISMATCH:")
        all_labels = sorted(set(edtm["adc_map"]) | set(bdtm["adc_map"]))
        for label in all_labels:
            e = edtm["adc_map"].get(label)
            b = bdtm["adc_map"].get(label)
            if e != b:
                print(f"  {label}: edtlib={e}  boarddt={b}")
    else:
        print(f"adc_map: MATCH ({sum(len(v) for v in edtm['adc_map'].values())} positions "
              f"across {len(edtm['adc_map'])} sockets)")

    # Explicit clash-fact spotlight (grove_d2 SIG0 and grove_d4 SIG0 both -> tcc0 ch0)
    print()
    print("=== clash-fact spotlight (grove_d2/grove_d4 -> tcc0 ch0) ===")
    d2 = edtm["pwm_map"].get("grove_d2", {}).get(0)
    d4 = edtm["pwm_map"].get("grove_d4", {}).get(0)
    print(f"  edtlib:  grove_d2.SIG0={d2}  grove_d4.SIG0={d4}  "
          f"clash={d2 == d4 and d2 is not None}")
    bd2 = bdtm["pwm_map"].get("grove_d2", {}).get(0)
    bd4 = bdtm["pwm_map"].get("grove_d4", {}).get(0)
    print(f"  boarddt: grove_d2.SIG0={bd2}  grove_d4.SIG0={bd4}  "
          f"clash={bd2 == bd4 and bd2 is not None}")

    print()
    print("RESULT:", "MATCH" if ok else "MISMATCH")


if __name__ == "__main__":
    main()
