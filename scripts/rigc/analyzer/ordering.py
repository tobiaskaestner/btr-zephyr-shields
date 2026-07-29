"""Allocation ordering: R18's `_key` (rigc-r4-brief.md Sec 2 -- "Allocation
order is R18's `_key` ... a named unit contract, never rig-file declaration
order"). Every allocator (addresses, CS) sorts its scope members through
this ONE function before assigning anything, so a rig author reordering
`instances:` never changes what gets allocated where -- deterministic,
order-independent, pinnable (R18).

Ported from rigexp/analyzer.py's `_key(inst, dev)` (`analyzer.py:68-70`),
unchanged in shape: `(socket, instance name, device name)`, read straight
off the Instance/Device values already in hand -- no BoardSocket or Rig
needed, which is what makes it a value function on its own."""
from __future__ import annotations

from typing import Tuple

from ..model import Device, Instance

#: The stable allocation order: (the instance's own socket REFERENCE
#: string -- not the resolved BoardSocket's label, the same string
#: Instance.socket already carries -- then instance name, then device
#: name).
AllocationKey = Tuple[str, str, str]


def allocation_key(inst: Instance, dev: Device) -> AllocationKey:
    return (inst.socket, inst.name, dev.name)
