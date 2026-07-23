"""Connector-type registry. A type IS three artifacts (Conv. 1): the
socket binding (board side, edtlib's job in the real build), the plug
binding (shield side, consumed HERE by the loaders), and the index header
(position single source of truth). This module assembles the three into
model.ConnectorType.

Data sources (Bridge-A rewrite step 3, AMENDED -- see
claude/rigs/implementation-plan.md "Connector types -> binding YAML"):
  - plug facts:      dts/connectors/plug,<type>.yaml (never dts/bindings/ --
                      see dts/connectors/README.md for why: edtlib globs +
                      schema-checks every binding dir wholesale, and this
                      shape -- plug/bus-proxies/positions -- is not part of
                      its allowed top-level keys).
  - socket facts:     the REAL dts/bindings/connector/<type>.yaml, read with
                      a plain yaml.safe_load of the raw file rather than
                      edtlib.Binding -- the two rig-extension properties
                      (socket,stackable presence, socket,cs-pool default)
                      are declared INLINE in every real binding (no
                      `include:`-composed indirection to resolve), so the
                      raw YAML dict already has them at
                      doc["properties"]["socket,cs-pool"]["default"] --
                      exactly what edtlib.Binding would also expose via
                      Binding.raw, with far less machinery.
  - i2c-port is the one type with no real socket binding at all (its
    sockets are shield-synthesized only, never in a real board DT -- see
    dts/connectors/README.md, "The i2c-port exception"): its socket facts
    are declared inline in its OWN plug YAML instead, under a `socket:` key.
"""
from __future__ import annotations

import glob
import os

import yaml

from .diag import Depends
from .dtsio import MODULE_ROOT, parse_header_indices
from .model import ConnectorType, Position

CONNECTORS = os.path.join(MODULE_ROOT, "dts", "connectors")
BINDINGS = os.path.join(MODULE_ROOT, "dts", "bindings", "connector")


def _socket_facts(name: str, plug: dict,
                  deps: Depends | None) -> tuple[bool, list[int]]:
    """(stackable, cs_pool) -- the socket-side type facts. Real binding if
    one exists for this type; else the plug YAML's own inline `socket:` key
    (the i2c-port exception, see module docstring)."""
    socket_path = os.path.join(BINDINGS, f"{name}.yaml")
    if os.path.exists(socket_path):
        if deps is not None:
            deps.see(socket_path)
        with open(socket_path) as f:
            socket = yaml.safe_load(f)
        sprops = socket.get("properties", {})
        # type-level facts read off the SOCKET binding:
        # mating multiplicity = presence of socket,stackable in the schema;
        # default CS candidate list = the socket,cs-pool default.
        stackable = "socket,stackable" in sprops
        cs_pool = sprops.get("socket,cs-pool", {}).get("default", [])
        return bool(stackable), list(cs_pool)

    inline = plug.get("socket", {})
    return bool(inline.get("stackable", False)), list(inline.get("cs-pool", []))


def load_types(deps: Depends | None = None) -> dict[str, ConnectorType]:
    types = {}
    for plug_path in sorted(glob.glob(os.path.join(CONNECTORS, "plug,*.yaml"))):
        if deps is not None:
            deps.see(plug_path)
        with open(plug_path) as f:
            plug = yaml.safe_load(f)
        name = plug["plug"]

        stackable, cs_pool = _socket_facts(name, plug, deps)

        indices = parse_header_indices(name, deps)
        positions = {}
        for pname, meta in plug.get("positions", {}).items():
            if pname not in indices:
                raise KeyError(
                    f"plug binding for '{name}' names position '{pname}' "
                    f"which is not in dt-bindings/connector/{name}.h")
            positions[pname] = Position(
                name=pname, index=indices[pname],
                function=meta.get("function", "gpio"),
                optional=bool(meta.get("optional", False)))

        types[name] = ConnectorType(
            name=name,
            positions=positions,
            index2name={v: k for k, v in indices.items()},
            bus_proxies=list(plug.get("bus-proxies", [])),
            stackable=stackable,
            cs_pool=list(cs_pool),
        )
    return types
