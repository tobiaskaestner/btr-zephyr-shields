"""Connector-type registry. A type IS three artifacts (Conv. 1): the
socket binding (board side, edtlib's job in the real build), the plug
binding (shield side, consumed HERE by the loaders), and the index header
(position single source of truth). This module assembles the three into
model.ConnectorType.
"""
from __future__ import annotations

import glob
import os

import yaml

from .dtsio import COMMON, parse_header_indices
from .model import ConnectorType, Position

BINDINGS = os.path.join(COMMON, "bindings")


def load_types() -> dict[str, ConnectorType]:
    types = {}
    for plug_path in sorted(glob.glob(os.path.join(BINDINGS, "plug,*.yaml"))):
        with open(plug_path) as f:
            plug = yaml.safe_load(f)
        name = plug["plug"]

        socket_path = os.path.join(BINDINGS, f"socket,{name}.yaml")
        with open(socket_path) as f:
            socket = yaml.safe_load(f)
        sprops = socket.get("properties", {})
        # type-level facts read off the SOCKET binding:
        # mating multiplicity = presence of socket,stackable in the schema;
        # default CS candidate list = the socket,cs-pool default.
        stackable = "socket,stackable" in sprops
        cs_pool = sprops.get("socket,cs-pool", {}).get("default", [])

        indices = parse_header_indices(name)
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
