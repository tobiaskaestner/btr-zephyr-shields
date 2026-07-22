"""DTS plumbing shared by everything that reads DTS-shaped input: CPP
invocation (one translation unit, Ground rule 3), stock-dtlib parsing,
dt-bindings header parsing, and generic property rendering for passthrough.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from .diag import ROOT, Diagnostic, LoadError, SrcRef

# The zephyr tree (dtlib source + includes) is located via $ZEPHYR_BASE, which
# the build sets and rig.cmake passes through to the expander explicitly — no
# hardcoded checkout path. For standalone/API use, export ZEPHYR_BASE first.
_ZEPHYR_BASE = os.environ.get("ZEPHYR_BASE")
if not _ZEPHYR_BASE:
    raise RuntimeError(
        "rigexp: $ZEPHYR_BASE is not set — it is required to locate zephyr's "
        "devicetree library and includes. The build (rig.cmake) passes it "
        "automatically; for standalone use, export ZEPHYR_BASE=<zephyr tree>.")
ZEPHYR_DT_SRC = os.path.join(_ZEPHYR_BASE, "scripts", "dts", "python-devicetree", "src")
ZEPHYR_INC = os.path.join(_ZEPHYR_BASE, "include")
COMMON = os.path.join(ROOT, "common-dts")
COMMON_INC = os.path.join(COMMON, "include")

sys.path.insert(0, ZEPHYR_DT_SRC)
from devicetree import dtlib  # noqa: E402


def src_of(obj) -> SrcRef:
    """SrcRef from a dtlib Node or Prop (both carry filename/lineno)."""
    label = ""
    if isinstance(obj, dtlib.Node):
        label = obj.labels[0] if obj.labels else obj.path
    elif isinstance(obj, dtlib.Property):
        label = f"{obj.node.path}: {obj.name}"
    return SrcRef(obj.filename, obj.lineno, label)


def run_cpp(dts_path: str, out_path: str) -> None:
    cmd = [
        "gcc", "-E", "-x", "assembler-with-cpp", "-nostdinc",
        "-I", ZEPHYR_INC, "-I", COMMON_INC,
        "-undef", "-D__DTS__", dts_path, "-o", out_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise LoadError(Diagnostic(
            "error", "lang-cpp",
            "preprocessing failed\n" + res.stderr.strip(),
            [SrcRef(dts_path, 0)]))


def parse_dts(dts_path: str, workdir: str) -> dtlib.DT:
    """CPP + stock dtlib. dtlib reads the CPP linemarkers, so node/prop
    source references point at the ORIGINAL files — free for candidate-1."""
    os.makedirs(workdir, exist_ok=True)
    pre = os.path.join(workdir, os.path.basename(dts_path) + ".pre")
    run_cpp(dts_path, pre)
    try:
        return dtlib.DT(pre)
    except dtlib.DTError as e:
        raise LoadError(Diagnostic("error", "lang-parse", str(e))) from e


def parse_tu(includes: list[str], workdir: str, name: str) -> dtlib.DT:
    """Build + parse a one-off translation unit that includes the given files."""
    os.makedirs(workdir, exist_ok=True)
    tu = os.path.join(workdir, name)
    with open(tu, "w") as f:
        f.write("/dts-v1/;\n")
        for inc in includes:
            f.write(f'#include "{inc}"\n')
    return parse_dts(tu, workdir)


_DEFINE_RE = re.compile(r"^\s*#define\s+(\w+)\s+(\d+|0x[0-9a-fA-F]+)\s*$", re.M)


def parse_header_indices(type_name: str) -> dict[str, int]:
    """dt-bindings/connector/<type>.h — the position-index single source of
    truth. Returns {short position name: index} with the common macro prefix
    stripped (ARDUINO_HEADER_R3_D7 -> D7)."""
    path = os.path.join(COMMON_INC, "dt-bindings", "connector", f"{type_name}.h")
    with open(path) as f:
        defines = {m[1]: int(m[2], 0) for m in _DEFINE_RE.finditer(f.read())}
    prefix = os.path.commonprefix(list(defines))
    return {name[len(prefix):]: val for name, val in defines.items()}


def words(prop) -> list[int]:
    """Raw 32-bit cells of a property value."""
    v = prop.value
    return [int.from_bytes(v[i:i + 4], "big") for i in range(0, len(v) - len(v) % 4, 4)]


def render_prop(prop) -> str | None:
    """Generic passthrough rendering for props the rig model doesn't
    interpret (compatible, spi-max-frequency, jedec-id, ...). Returns a
    complete 'name = value;' string, or None if the type can't passthrough
    (phandles — those must have been interpreted upstream)."""
    T = dtlib.Type
    t = prop.type
    if t is T.EMPTY:
        return f"{prop.name};"
    if t is T.NUM:
        return f"{prop.name} = <{prop.to_num()}>;"
    if t is T.NUMS:
        return f"{prop.name} = <{' '.join(str(n) for n in prop.to_nums())}>;"
    if t is T.STRING or t is T.STRINGS:
        vals = ", ".join(f'"{s}"' for s in prop.to_strings())
        return f"{prop.name} = {vals};"
    if t is T.BYTES:
        return f"{prop.name} = [{prop.value.hex(' ')}];"
    return None
