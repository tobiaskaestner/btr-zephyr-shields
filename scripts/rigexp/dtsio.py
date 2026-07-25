"""DTS plumbing for the SHIELD-template side, and for rig-declared token
vocabularies (`dt-includes:`). This module never touches the board DT
(`board_edt`/`edt_build`'s real `edtlib.EDT` owns that). What's here: CPP +
stock dtlib parsing of `.shield` translation units (Ground rule 3), which
stays dtlib by design — shield templates are pre-instantiation text with no
binding/schema to validate against, so there is nothing for edtlib to attach
type info to; dt-bindings/connector/*.h position-index header parsing (the
module's own real headers, shared by both the real gpio-map and the
expander); and `resolve_token`/`check_include`, the per-instance-parameter
mechanism's own synthetic-TU resolution (shared by the loader, for
validation, and the emitter, for the config sheet's display value — one
resolution path, not two).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import List, Optional

from .diag import ROOT, Depends, Diagnostic, LoadError, SrcRef

# The zephyr tree (dtlib source + includes) is located via $ZEPHYR_BASE, which
# the build sets and dts.cmake passes through to the expander explicitly — no
# hardcoded checkout path. For standalone/API use, export ZEPHYR_BASE first.
_ZEPHYR_BASE = os.environ.get("ZEPHYR_BASE")
if not _ZEPHYR_BASE:
    raise RuntimeError(
        "rigexp: $ZEPHYR_BASE is not set — it is required to locate zephyr's "
        "devicetree library and includes. The build (dts.cmake) passes it "
        "automatically; for standalone use, export ZEPHYR_BASE=<zephyr tree>.")
ZEPHYR_DT_SRC = os.path.join(_ZEPHYR_BASE, "scripts", "dts", "python-devicetree", "src")
ZEPHYR_INC = os.path.join(_ZEPHYR_BASE, "include")

# The module root (self-located the same way ROOT is: two levels up from
# scripts/rigexp/), and its real include/ tree -- the single source for the
# dt-bindings/connector/*.h position-index headers (Bridge-A rewrite step 3;
# common-dts no longer carries its own copies).
MODULE_ROOT = os.path.dirname(os.path.dirname(ROOT))
MODULE_INC = os.path.join(MODULE_ROOT, "include")

sys.path.insert(0, ZEPHYR_DT_SRC)
from devicetree import dtlib  # noqa: E402


def src_of(obj: dtlib.Node | dtlib.Property) -> SrcRef:
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
        "-I", ZEPHYR_INC, "-I", MODULE_INC,
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
    source references point at the ORIGINAL `.shield` files, not the
    generated translation unit — free provenance for diagnostics."""
    os.makedirs(workdir, exist_ok=True)
    pre = os.path.join(workdir, os.path.basename(dts_path) + ".pre")
    run_cpp(dts_path, pre)
    try:
        return dtlib.DT(pre)
    except dtlib.DTError as e:
        raise LoadError(Diagnostic("error", "lang-parse", str(e))) from e


def parse_tu(includes: list[str], workdir: str, name: str) -> dtlib.DT:
    """Build + parse a one-off translation unit that includes the given
    files — the shield-TU entry point (one `.shield` per call, per
    loader_yml)."""
    os.makedirs(workdir, exist_ok=True)
    tu = os.path.join(workdir, name)
    with open(tu, "w") as f:
        f.write("/dts-v1/;\n")
        for inc in includes:
            f.write(f'#include "{inc}"\n')
    return parse_dts(tu, workdir)


_DEFINE_RE = re.compile(r"^\s*#define\s+(\w+)\s+(\d+|0x[0-9a-fA-F]+)\s*$", re.M)


def parse_header_indices(type_name: str,
                         deps: Depends | None = None) -> dict[str, int]:
    """include/dt-bindings/connector/<type>.h -- the module's REAL
    position-index single source of truth (Bridge-A rewrite step 3; no
    longer a bundled common-dts copy). Returns {short position name: index}
    with the common macro prefix stripped (ARDUINO_HEADER_R3_D7 -> D7)."""
    path = os.path.join(MODULE_INC, "dt-bindings", "connector", f"{type_name}.h")
    if deps is not None:
        deps.see(path)
    with open(path) as f:
        defines = {m[1]: int(m[2], 0) for m in _DEFINE_RE.finditer(f.read())}
    prefix = os.path.commonprefix(list(defines))
    return {name[len(prefix):]: val for name, val in defines.items()}


def source_files(dt: dtlib.DT, exclude_dir: str) -> list[str]:
    """Every REAL source-tree file `dt` was parsed from, recovered from cpp
    linemarkers via each `Node`/`Property`'s own `.filename` (dtlib records
    these as it walks the preprocessed token stream, so they name the
    ORIGINAL included files, not the preprocessed temp file). EXCLUDES
    `exclude_dir` (and anything under it): the synthesized translation unit
    `parse_tu` builds there is a generated artifact, not a real source file
    -- only its real `#include`d files belong in a dependency list."""
    exclude = os.path.realpath(exclude_dir)
    names = set()
    for node in dt.node_iter():
        names.add(node.filename)
        for prop in node.props.values():
            names.add(prop.filename)
    return sorted(
        name for name in names
        if name and os.path.realpath(name) != exclude
        and not os.path.realpath(name).startswith(exclude + os.sep))


def words(prop: dtlib.Property) -> list[int]:
    """Raw 32-bit cells of a property value.

    Only for `Type.PHANDLES_AND_NUMS` — dtlib has no typed accessor for that
    shape (`to_nums` requires pure NUM/NUMS, `to_nodes` requires pure
    PHANDLE/PHANDLES); a real gap (saferail 10: consume dtlib as-is, report
    the gap rather than fork it), not a style choice. Every other cell shape
    goes through `to_num`/`to_nums` directly at the call site instead."""
    v = prop.value
    return [int.from_bytes(v[i:i + 4], "big") for i in range(0, len(v) - len(v) % 4, 4)]


def render_prop(prop: dtlib.Property) -> str | None:
    """Generic passthrough rendering for props the rig model doesn't
    interpret (compatible, spi-max-frequency, jedec-id, ...). Returns a
    complete 'name = value;' string, or None if the type can't passthrough.

    Deliberately renders via dtlib's typed accessors (to_num/to_nums/
    to_strings/value) with its OWN stable formatting, NOT `str(prop)`:

      - `str(prop)` cannot preserve authored numeric form — every NUM/NUMS
        renders as hex with padded spacing regardless of source radix (a
        shield-authored `spi-max-frequency = <8000000>;` comes back as
        `spi-max-frequency = < 0x7a1200 >;`, verified against dtlib).
      - the None-for-phandles branch is LOAD-BEARING: `str(prop)` renders
        phandle-typed values via their DTS label (e.g. `< &plug >`), but
        that label is a shield-template parsing artifact with no
        counterpart in the composed output (the emitter mints its own
        `<instance>_<shield-local-label>` names) — rendering it would leak
        a dangling, wrong-scope reference into the emitted overlay.
        Phandle-shaped props must already have been interpreted upstream
        (gpio/pwm/adc nexus refs); anything left un-interpreted is
        correctly dropped here (with a diagnostic), never guessed at.
    """
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


# ---------------------------------------------------------------- rig dt-includes vocabulary

_INT_LITERAL_RE = re.compile(r"^-?(0[xX][0-9a-fA-F]+|\d+)$")


def is_int_literal(text: str) -> bool:
    """Whether `text` is already a bare DTS integer literal (decimal or 0x
    hex, optionally negative) needing no `dt-includes:` resolution at all —
    shared by the loader (skip resolving what needs no resolving) and the
    emitter's config sheet (skip showing a redundant "(N)" for a value that
    already IS N)."""
    return bool(_INT_LITERAL_RE.match(text))


def check_include(header: str, workdir: str, tag: str) -> Optional[str]:
    """Confirm one `dt-includes:` header is real and preprocesses cleanly on
    its own (rig-variants-revisions.md per-instance-parameters rule 6:
    `lang-dt-include`, checked at expand time regardless of whether any
    parameter actually resolves against it). Returns an error detail string
    on failure, else None. Each header is checked in isolation — the failure
    this rule targets is the header not existing at all, not an
    inter-header ordering dependency."""
    tu = os.path.join(workdir, f"rig-dt-include-{tag}.dts")
    with open(tu, "w") as f:
        f.write(f'/dts-v1/;\n#include "{header}"\n/ {{ }};\n')
    try:
        parse_dts(tu, workdir)
        return None
    except LoadError as e:
        return e.diag.message


def resolve_token(token: str, headers: List[str], workdir: str, tag: str) -> Optional[int]:
    """cpp+dtlib-resolve one assigned parameter TOKEN against a synthetic TU
    that includes exactly `headers` — a rig's declared `dt-includes:`
    vocabulary, in order. Serves validation (rules 4/5) and the config
    sheet's displayed value; never feeds emission, which emits the token
    text verbatim regardless of whether it resolves. Returns None if cpp
    leaves the token unexpanded: an unresolved bareword identifier is not
    valid syntax inside a DTS cell list, so the embedding `dtlib.DT` parse
    fails — the same failure shape whether the token is a typo or the
    defining header was never declared."""
    tu = os.path.join(workdir, f"rig-param-{tag}.dts")
    with open(tu, "w") as f:
        f.write("/dts-v1/;\n")
        for header in headers:
            f.write(f'#include "{header}"\n')
        f.write(f"/ {{ p {{ v = <{token}>; }}; }};\n")
    try:
        dt = parse_dts(tu, workdir)
    except LoadError:
        return None
    return dt.get_node("/p").props["v"].to_num()
