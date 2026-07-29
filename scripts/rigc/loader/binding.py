"""Board and socket-map resolution -- the SocketBinding seam
(board-as-invocation-coordinate.md Sec 6; rigc-r2-brief.md Sec 4). ONE
constructor (`resolve_board`) produces ONE value (`SocketBinding`),
applied at exactly one seam later (instance construction, loader/delta.py)
-- the delta engine itself never touches a socket map, only abstract
references. Every board/sockets diagnostic S2's five shape rules can
raise lives in this ONE module, so the frozen wording survives a later
SocketBinding mechanism swap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..diag import Diagnostic, SourceRef, error
from ..model import AxisDecl
from .documents import Val


@dataclass(frozen=True)
class SocketBinding:
    """The abstract-socket map an instance's `socket:` resolves through:
    `get(name)` returns the mapped board-socket label, or NAME ITSELF if
    the map does not cover it (lookup-else-identity,
    rigexp/loader_yml.py:1028) -- an unmapped name is a BOARD-side
    question (phys-socket, deferred to R3+), never a loader-level
    error."""

    _map: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        return self._map.get(name, name)


def resolve_board(rig_name: str, variants: Optional[AxisDecl],
                  selected_variant: Optional[str],
                  board_v: Optional[Val], sockets_v: Optional[Val],
                  src: SourceRef,
                  ) -> tuple[str, SocketBinding, list[Diagnostic]]:
    """The board this rig actually builds, and the SocketBinding its
    content resolves socket: references through. Two legal shapes, and
    mixing them is an error (S2's five rules, rigexp/loader_yml.py
    `_resolve_board`, ported unchanged): a single top-level `board:`
    (optionally paired with a top-level `sockets:` map), or a `board:`
    declared beside EVERY `variants:` list entry (each with its own
    optional `sockets:`) -- never both, never partial, never a
    top-level `sockets:` alongside per-variant boards, never neither.

    Returns (rig.board, the binding to apply while parsing this rig's
    topology, diagnostics). On any rejection here board is "" and the
    binding is empty; neither is read again once a diagnostic exists,
    matching the continuation shape the rest of the loader reproduces
    (rigc-r2-brief.md Sec 6): the caller keeps going regardless, since a
    later diagnostic must not be dropped just because this one fired."""
    per_variant_boards = variants.boards if variants is not None else {}
    if variants is not None and per_variant_boards:
        if board_v is not None:
            return "", SocketBinding(), [error(
                "lang-schema",
                f"rig '{rig_name}' declares a top-level board: while its "
                "variants also declare their own -- a rig may declare a "
                "board per variant or once at the top level, never both",
                (board_v.src, src))]
        missing = [v for v in variants.values if v not in per_variant_boards]
        if missing:
            return "", SocketBinding(), [error(
                "lang-schema",
                f"rig '{rig_name}': variant(s) {', '.join(missing)} declare "
                f"no board:, but variant(s) "
                f"{', '.join(sorted(per_variant_boards))} do -- every "
                "variant must declare a board, or none should",
                (src,))]
        if sockets_v is not None:
            return "", SocketBinding(), [error(
                "lang-schema",
                f"rig '{rig_name}' declares a top-level sockets: map "
                "while its variants declare their own boards -- put each "
                "variant's own socket map beside its board: under "
                "variants: list instead",
                (sockets_v.src,))]
        if selected_variant is None:
            return "", SocketBinding(), []   # an earlier axis error already said why
        board = per_variant_boards[selected_variant]
        return (board,
               SocketBinding(dict(variants.sockets.get(selected_variant, {}))),
               [])
    if board_v is None:
        return "", SocketBinding(), [error(
            "lang-schema",
            f"rig '{rig_name}' declares no board: -- add a top-level "
            "board:, or give every declared variant its own",
            (src,))]
    board = board_v.value
    if sockets_v is None:
        return board, SocketBinding(), []
    return board, SocketBinding({k: v.value for k, v in sockets_v.value.items()}), []
