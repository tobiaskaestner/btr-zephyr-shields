"""Bus-kind matching: whether a bus name (a `Device.bus` value, or a
shield group/proxy name authored in a `.shield` file) names a given
socket bus KIND -- bare ("spi"), or a named variant a multi-bus
connector type suffixes with a role ("spi-sensors"). One shared
implementation for every pass that gates behavior on which kind a
qualified bus name is, rather than each duplicating the same
kind-prefix match (or, worse, a literal three-name membership check
that silently stops covering a role-suffixed name)."""
from __future__ import annotations

from typing import Optional

#: Every socket bus kind the schema recognizes (multi-bus-socket-brief.md
#: Sec 2) -- the vocabulary `bus_kind_of` matches a qualified name
#: against, in order.
BUS_KINDS = ("i2c", "spi", "uart")


def is_bus_kind(bus: Optional[str], kind: str) -> bool:
    """Whether `bus` names `kind` -- bare, or `kind` suffixed with a role
    ("-sensors", "-motors", ...). `bus` may be absent (a device with no
    bus at all), which never matches any kind."""
    return bus is not None and (bus == kind or bus.startswith(f"{kind}-"))


def bus_kind_of(name: Optional[str]) -> Optional[str]:
    """Which of `BUS_KINDS` `name` names, bare or role-suffixed, else
    None -- the general form of `is_bus_kind` for a caller that must
    recognize ANY of the schema's kinds rather than one it already
    knows."""
    return next((k for k in BUS_KINDS if is_bus_kind(name, k)), None)
