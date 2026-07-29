"""The rig model, R2: syntax-free semantic representation of everything the
loader can determine WITHOUT shield data, board devicetree, or params/pin
resolution (all wholesale deferred to R3 -- rigc-r2-brief.md Sec 1, the
ShieldRef seam).

Mirrors rigexp/model.py's shape for the same entities (Rig, Instance, Wire,
WireEnd, AxisDecl) closely enough that a later R3 -- which replaces
ShieldRef with the real resolved Shield behind the identical
Instance.shield attribute -- touches only the loader seam, never these
dataclasses' own fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .diag import SourceRef


@dataclass(frozen=True)
class ShieldRef:
    """An instance's `shield:` reference, UNRESOLVED -- the R2/R3 seam
    (rigc-r2-brief.md Sec 1). Carries the raw ref string (the identical
    `<name>` / `<name>@<rev>` grammar V1c gives a base instance and a
    delta patch alike) plus its own source anchor, and always
    constructs: no existence check against a shield library, because R2
    builds no shield library at all. Any access that would need shield
    DATA (devices, declared params, node names, config elements) belongs
    to R3, which resolves this reference against the real library behind
    the same Instance.shield attribute -- nothing upstream of that seam
    needs to change."""

    ref: str
    src: SourceRef


@dataclass
class WireEnd:
    """One `<instance>.<node>` endpoint -- the RIG-SIDE half of resolution
    only (rigc-r2-brief.md Sec 1): dotted form and instance existence in
    the effective topology, both checked by the loader. Node
    existence/ambiguity within the instance's own shield needs shield
    DATA (deferred to R3 via ShieldRef), so `node` is kept as the raw,
    unvalidated string -- safe, since R2 has no accept path a wrong node
    name could silently reach."""

    instance_name: str
    node: str
    src: SourceRef


@dataclass
class Wire:
    frm: WireEnd
    to: WireEnd
    route: Union[str, int]          # "adhoc" | via: position name (raw)
    src: SourceRef


@dataclass
class Instance:
    name: str
    shield: ShieldRef
    socket: str                     # already resolved through a SocketBinding
    invert: bool = False
    src: Optional[SourceRef] = None


@dataclass
class AxisDecl:
    """One declared qualifier axis (rig.yml `revisions:` or `variants:`):
    the values a selection may take, and the one a bare (unqualified)
    target takes by default. Ported value-shaped, unchanged in shape,
    from rigexp/model.py's own AxisDecl -- the hwmv2 seam
    (rigc-r2-brief.md Sec 3) keeps resolution a single pure function
    over (decl, selected), so this dataclass is exactly the value that
    swap will later replace the declaration parsing behind.

    boards/sockets carry, per declared VALUE, the board a rig variant
    selects and its abstract-socket map -- populated only for a rig's
    own `variants:` axis when it uses the per-variant-board shape;
    empty for every other axis."""

    values: list[str]
    default: Optional[str] = None
    boards: dict[str, str] = field(default_factory=dict)
    sockets: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Rig:
    name: str
    board: str = ""
    instances: list[Instance] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    dt_includes: list[str] = field(default_factory=list)
    dt_includes_refs: list[SourceRef] = field(default_factory=list)
    revisions: Optional[AxisDecl] = None
    variants: Optional[AxisDecl] = None
    revision: Optional[str] = None
    variant: Optional[str] = None
    src: Optional[SourceRef] = None
