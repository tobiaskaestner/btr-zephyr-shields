#!/usr/bin/env python3
"""Spike 2a: build an edtlib.EDT over the REAL seeeduino_lotus_btr board
.dts, standalone (no rig overlay, no shield) -- mirrors
cmake/modules/dts.cmake's cpp -> edtlib.EDT recipe, using the include/bindings
dirs actually recorded by a real `west build-rig --rig lotus-pwm` of this
board (see build-lotus-pwm/build_info.yml), west topdir /wrk/z/ws-up.
"""
from __future__ import annotations

import os
import subprocess
import sys

ZEPHYR_BASE = os.environ["ZEPHYR_BASE"]  # must be zephyr-rigs
WEST_TOPDIR = "/wrk/z/ws-up"
BTR = os.path.join(WEST_TOPDIR, "btr-shields")

sys.path.insert(0, os.path.join(ZEPHYR_BASE, "scripts", "dts", "python-devicetree", "src"))
from devicetree import edtlib  # noqa: E402

BOARD_DTS = os.path.join(BTR, "boards/seeed/seeeduino_lotus_btr/seeeduino_lotus_btr.dts")

# -isystem dirs -- taken verbatim from build-lotus-pwm/build_info.yml's
# devicetree.include-dirs for this exact board build (west topdir /wrk/z/ws-up).
INCLUDE_DIRS = [
    f"{BTR}/include",
    f"{BTR}/dts",
    f"{WEST_TOPDIR}/modules/hal/ambiq/dts",
    f"{WEST_TOPDIR}/modules/hal/atmel/include",
    f"{WEST_TOPDIR}/modules/hal/bouffalolab/include",
    f"{WEST_TOPDIR}/modules/hal/bouffalolab/include/zephyr",
    f"{WEST_TOPDIR}/modules/hal/gigadevice/include",
    f"{WEST_TOPDIR}/modules/hal/infineon/dts",
    f"{WEST_TOPDIR}/modules/hal/microchip/include",
    f"{WEST_TOPDIR}/modules/hal/microchip/dts",
    f"{WEST_TOPDIR}/modules/hal/nuvoton/dts",
    f"{WEST_TOPDIR}/modules/hal/nxp/dts",
    f"{WEST_TOPDIR}/modules/hal/stm32/dts",
    f"{WEST_TOPDIR}/modules/hal/ti/dts",
    f"{ZEPHYR_BASE}/include",
    f"{ZEPHYR_BASE}/include/zephyr",
    f"{ZEPHYR_BASE}/dts/common",
    f"{ZEPHYR_BASE}/dts/vendor",
    f"{ZEPHYR_BASE}/dts/arm",
    f"{ZEPHYR_BASE}/dts",
]

BINDINGS_DIRS = [
    f"{BTR}/dts/bindings",
    f"{ZEPHYR_BASE}/dts/bindings",
]


def run_cpp(dts_path: str, out_path: str) -> None:
    cmd = ["gcc", "-E", "-x", "assembler-with-cpp", "-nostdinc"]
    for d in INCLUDE_DIRS:
        cmd += ["-isystem", d]
    cmd += ["-D__DTS__", dts_path, "-o", out_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("cpp failed:\n" + res.stderr)


def build_edt(workdir: str) -> edtlib.EDT:
    os.makedirs(workdir, exist_ok=True)
    pre = os.path.join(workdir, "seeeduino_lotus_btr.dts.pre")
    run_cpp(BOARD_DTS, pre)
    edt = edtlib.EDT(
        pre, BINDINGS_DIRS,
        werror=False,
        default_prop_types=True,
        infer_binding_for_paths=["/zephyr,user", "/cpus"],
    )
    return edt


if __name__ == "__main__":
    workdir = os.path.join(os.path.dirname(__file__), "_work")
    edt = build_edt(workdir)
    print(f"OK: EDT built, {len(edt.nodes)} nodes")
    socket_nodes = [n for n in edt.nodes if n.matching_compat == "socket,grove"]
    print("socket,grove nodes:", [n.path for n in socket_nodes])
