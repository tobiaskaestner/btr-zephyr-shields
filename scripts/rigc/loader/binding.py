"""The SocketBinding seam (board-as-invocation-coordinate.md Sec 6;
rigc-r2-brief.md Sec 4): a rig's abstract `socket:` references resolve
through ONE value, applied at exactly one seam (instance construction,
loader/delta.py) -- the delta engine itself never touches a socket map,
only abstract references.

`board:`/`sockets:` retired from rig.yml's own grammar entirely
(board-coordinate-s6-brief.md Sec 11's ruling; the declaration-mixing
rules S2 authored -- board declared twice, a partial per-variant
declaration, a top-level sockets: alongside per-variant boards -- went
with the grammar they policed, since none of the three shapes they
protected against can be authored any more). `SocketBinding` survives
as the always-empty identity seam a future re-introduction could still
populate; `resolve_board` survives as the one place the invocation's
`--board` becomes `rig.board`, so a later change to how a board reaches
this pipeline still touches only this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SocketBinding:
    """The abstract-socket map an instance's `socket:` resolves through:
    `get(name)` returns the mapped board-socket label, or NAME ITSELF if
    the map does not cover it (lookup-else-identity,
    rigexp/loader_yml.py:1028) -- an unmapped name is a BOARD-side
    question (phys-socket, deferred to R3+), never a loader-level
    error. Nothing in rig.yml's own grammar populates `_map` any more
    (board-coordinate-s6-brief.md Sec 11), so every rig resolves through
    an empty instance today; the map stays a constructor argument rather
    than a bare identity function so a later mechanism (a board-side
    alias table, say) has a seam to populate without every call site
    changing shape."""

    _map: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        return self._map.get(name, name)


def resolve_board(injected_board: Optional[str] = None) -> str:
    """The board this rig actually builds: the invocation's own
    `--board` (board-coordinate-s1-brief.md Sec 4), unconditionally, or
    "" when none was given.

    Returning "" rather than raising is deliberate: a rig's TOPOLOGY
    (this loader's own job) never needed a board to assemble, and
    board-coordinate-s6-brief.md Sec 11 removed the only thing that
    once required one here -- rig.yml's own declaration. Something
    downstream that actually needs a real board devicetree (cli.py,
    right before boarddt.load_board) is where a still-empty board
    becomes a diagnostic; a bare load (`west rigs --boards-for`'s own
    census, `rigc.promote`'s round-trip check) never reaches that
    point and so never needs one either."""
    return injected_board if injected_board is not None else ""
