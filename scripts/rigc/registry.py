"""Connector-type registry. A type IS two artifacts (Conv. 1): the unified
socket+plug binding (board side, edtlib's job in the real build; shield
side, consumed HERE by the loader) and the index header (position single
source of truth). Ported from rigexp/ctypes_registry.py (rigc-r3-brief.md
Sec 1): the registry is a PREREQUISITE, not a nicety -- shields.py checks
every shield's plug against it (lang-shield-type), so an empty or stubbed
registry would emit errors on perfectly valid fixture/corpus shields and
corrupt every golden's bytes.

Data source: ONE file per type, dts/bindings/connectors/<type>.yaml -- the
real socket binding plus the shield-side plug contract folded in as
`plug,*` top-level extension keys (namespaced by the SIDE they describe,
never the project) -- legal since edtlib treats any top-level binding key
containing a comma as an opaque vendor-namespaced extension. Read HERE with
a plain `yaml.safe_load` rather than edtlib.Binding: the plug,* keys are
declared inline in every unified binding, so the raw YAML dict already has
them.

Resolved ONCE at CLI entry and threaded down as a value (T0b's shape,
rigc-r3-brief.md Sec 1) -- the hardcoded BINDINGS default below is for
direct API / test use only.
"""
from __future__ import annotations

import glob
import os
from typing import Dict, List, Optional, Tuple

import yaml

from .buskind import CS_POOL_PROP_RE as _CS_POOL_PROP_RE
from .deps import Deps, touch, union
from .dtsio import MODULE_ROOT, parse_header_indices
from .model import ConnectorType, Position

#: The default connector-type root: every real connector's unified binding.
BINDINGS = os.path.join(MODULE_ROOT, "dts", "bindings", "connectors")

#: socket,<kind>-<role>-cs-pool -- a named bus's own CS pool default,
#: keyed the qualified way. This module reads the raw binding dict,
#: board_edt.py reads an already-built edtlib.EDT -- two different
#: inputs to the same fact; see buskind.py for the regex itself and why
#: it lives there rather than as a third verbatim copy.


def _socket_facts(binding: dict) -> Tuple[bool, Dict[str, List[int]]]:
    """(stackable, cs_pool) -- the socket-side type facts, read off the
    unified binding's own schema: mating multiplicity = presence of
    socket,stackable in the schema; default CS candidate lists, keyed by
    qualified bus name -- the legacy, role-less socket,cs-pool default
    always means the bare "spi" bus (CS only ever applies to SPI), and
    socket,<kind>-<role>-cs-pool is a named bus's own."""
    sprops = binding.get("properties", {})
    stackable = "socket,stackable" in sprops
    cs_pool: Dict[str, List[int]] = {}
    legacy = sprops.get("socket,cs-pool")
    if legacy is not None:
        cs_pool["spi"] = list(legacy.get("default", []))
    for prop_name, meta in sprops.items():
        m = _CS_POOL_PROP_RE.match(prop_name)
        if m is None:
            continue
        cs_pool[m.group(1)] = list((meta or {}).get("default", []))
    return bool(stackable), cs_pool


def load_types(connector_dirs: Optional[List[str]] = None,
              header_dirs: Optional[List[str]] = None,
              ) -> Tuple[Dict[str, ConnectorType], Deps]:
    """Assemble every connector type found under connector_dirs (default:
    [BINDINGS]). header_dirs is the search list parse_header_indices
    resolves each type's <type>.h against (deliberately the SAME list a
    caller threads as --include-dir for cpp).

    Returns (types, deps) -- deps is every real file this call opened
    (ratified ruling 3: dependency data is a returned value, never a
    mutable accumulator passed in and written to)."""
    dirs = connector_dirs if connector_dirs is not None else [BINDINGS]
    types: Dict[str, ConnectorType] = {}
    deps: Deps = frozenset()
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
            deps = union(deps, touch(path))
            with open(path) as f:
                binding = yaml.safe_load(f)
            name = os.path.splitext(os.path.basename(path))[0]

            stackable, cs_pool = _socket_facts(binding)

            indices, hdeps = parse_header_indices(name, header_dirs)
            deps = union(deps, hdeps)
            positions = {}
            for pname, meta in binding.get("plug,positions", {}).items():
                if pname not in indices:
                    raise KeyError(
                        f"unified binding for '{name}' names position "
                        f"'{pname}' which is not in "
                        f"dt-bindings/connector/{name}.h")
                positions[pname] = Position(
                    name=pname, index=indices[pname],
                    function=meta.get("function", "gpio"),
                    optional=bool(meta.get("optional", False)))

            types[name] = ConnectorType(
                name=name,
                positions=positions,
                index2name={v: k for k, v in indices.items()},
                bus_proxies=list(binding.get("plug,bus-proxies", [])),
                stackable=stackable,
                cs_pool=cs_pool,
            )
    return types, deps
