"""Connector-type registry. A type IS two artifacts (Conv. 1): the unified
socket+plug binding (board side, edtlib's job in the real build; shield side,
consumed HERE by the loaders) and the index header (position single source
of truth). This module assembles the two into model.ConnectorType.

Data source: ONE file per type, dts/bindings/connectors/<type>.yaml -- the
real socket binding (a board's compatible = "socket,<type>" node genuinely
gets loaded and validated by edtlib on every real build, rig or plain) plus
the shield-side plug contract folded in as plug,* top-level extension keys
(plug,positions, plug,bus-proxies) -- extension keys are namespaced by the
SIDE they describe (plug,* here, socket,* for socket-side facts), never
by the project. This is legal since 1a657124349 (carried on the
zephyr-rigs tree this module builds against, not touched by this module):
edtlib treats any top-level binding key containing a comma as an opaque
vendor-namespaced extension, preserved in Binding.raw rather than erroring
"unknown key". Read HERE with a plain yaml.safe_load of the raw file rather
than edtlib.Binding -- the plug,* keys are declared inline in every unified
binding (no include:-composed indirection to resolve), so the raw YAML dict
already has them at, e.g., doc["plug,positions"] -- exactly what
edtlib.Binding.raw would also expose, with far less machinery. This
equivalence holds only as long as no unified binding needs an
include:-composed plug,* key; none currently do.

i2c-port is the one type with no socket node ever compiled for real (its
sockets are shield-synthesized only, lowered to plain, compatible-less
channel@N mux children before pass 2 -- see emitter.py's _mux_node); it
still gets a unified file here, compatible-bearing (edtlib's binding scan
is content-sniffing: a compatible-less file under dts/bindings/ would be
build-dependent to validate) but otherwise ordinary -- its socket,*
properties are schema decoration no real node ever exercises, read here
the same way as every other type's.
"""
from __future__ import annotations

import glob
import os
from typing import List, Optional

import yaml

from .diag import Depends
from .dtsio import MODULE_ROOT, parse_header_indices
from .model import ConnectorType, Position

# The default connector-type root: every real connector's unified binding.
# load_types's connector_dirs parameter overrides this (test-fixture
# connector types live elsewhere); every existing caller that omits it keeps
# reading exactly this directory, unchanged.
BINDINGS = os.path.join(MODULE_ROOT, "dts", "bindings", "connectors")


def _socket_facts(binding: dict) -> tuple[bool, list[int]]:
    """(stackable, cs_pool) -- the socket-side type facts, read off the
    unified binding's own schema: mating multiplicity = presence of
    socket,stackable in the schema; default CS candidate list = the
    socket,cs-pool default."""
    sprops = binding.get("properties", {})
    stackable = "socket,stackable" in sprops
    cs_pool = sprops.get("socket,cs-pool", {}).get("default", [])
    return bool(stackable), list(cs_pool)


def load_types(connector_dirs: Optional[List[str]] = None,
               header_dirs: Optional[List[str]] = None,
               deps: Depends | None = None) -> dict[str, ConnectorType]:
    """Assemble every connector type found under connector_dirs (default:
    [BINDINGS], today's single real directory -- a caller omitting this
    argument sees no behavior change at all).

    header_dirs is the search list parse_header_indices resolves each
    type's <type>.h against, first match wins, with MODULE_INC always tried
    last -- deliberately the SAME list a caller threads as --include-dir for
    cpp, so a type's YAML and its header are found by the identical rule cpp
    itself uses for #include <dt-bindings/connector/x.h>. A caller wanting
    more than one connector root (a fixture tree, alongside the real one)
    passes both directories in connector_dirs and the matching header root
    in header_dirs; resolve ONCE per CLI invocation and thread the result
    down, rather than calling this six times per run."""
    dirs = connector_dirs if connector_dirs is not None else [BINDINGS]
    types = {}
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
            if deps is not None:
                deps.see(path)
            with open(path) as f:
                binding = yaml.safe_load(f)
            name = os.path.splitext(os.path.basename(path))[0]

            stackable, cs_pool = _socket_facts(binding)

            indices = parse_header_indices(name, header_dirs, deps)
            positions = {}
            for pname, meta in binding.get("plug,positions", {}).items():
                if pname not in indices:
                    raise KeyError(
                        f"unified binding for '{name}' names position '{pname}' "
                        f"which is not in dt-bindings/connector/{name}.h")
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
                cs_pool=list(cs_pool),
            )
    return types
