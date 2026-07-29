"""Unit: loader.binding -- board/SocketBinding resolution (the S2 seam,
rigc-r2-brief.md Sec 4).

The stable contracts: SocketBinding's own lookup-else-identity semantics
(the ONE seam a socket: reference resolves through), and all five S2
shape rules resolve_board dispatches on -- board declared twice, no
board at all, a partial per-variant declaration, a top-level sockets:
map alongside per-variant boards, and the two ordinary (single-board /
per-variant-board) success shapes. Wording for these rules IS also
frozen by goldens (board-declared-twice etc.); this module asserts the
STRUCTURE (which shape wins, what the returned board/binding are) so a
rewrite of the wording keeps this contract in view without duplicating
it.
"""
from __future__ import annotations

from rigc.diag import SourceRef
from rigc.loader.binding import SocketBinding, resolve_board
from rigc.loader.documents import Val
from rigc.model import AxisDecl

_SRC = SourceRef("synthetic", 1, "rig")


def _val(value: object, key: str = "") -> Val:
    return Val(value, SourceRef("synthetic", 1, key))


# ------------------------------------------------------------ SocketBinding

def test_binding_maps_a_known_name() -> None:
    binding = SocketBinding({"ard": "nucleo_ard"})
    assert binding.get("ard") == "nucleo_ard"


def test_binding_falls_back_to_identity_for_an_unmapped_name() -> None:
    binding = SocketBinding({"ard": "nucleo_ard"})
    assert binding.get("other") == "other"


def test_empty_binding_is_pure_identity() -> None:
    binding = SocketBinding()
    assert binding.get("anything") == "anything"


# --------------------------------------------------------------- resolve_board

def test_single_top_level_board_with_no_sockets() -> None:
    board, binding, diags = resolve_board(
        "r", None, None, _val("b/s/rig"), None, _SRC)
    assert diags == []
    assert board == "b/s/rig"
    assert binding.get("x") == "x"


def test_single_top_level_board_with_sockets_map() -> None:
    board, binding, diags = resolve_board(
        "r", None, None, _val("b/s/rig"),
        _val({"ard": _val("nucleo_ard")}), _SRC)
    assert diags == []
    assert board == "b/s/rig"
    assert binding.get("ard") == "nucleo_ard"


def test_no_board_declared_at_all_is_rejected() -> None:
    board, binding, diags = resolve_board("r", None, None, None, None, _SRC)
    assert board == ""
    assert binding.get("x") == "x"
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_board_declared_twice_top_level_and_per_variant_is_rejected() -> None:
    variants = AxisDecl(values=["a"], default="a", boards={"a": "va/s/rig"})
    board, binding, diags = resolve_board(
        "r", variants, "a", _val("b/s/rig"), None, _SRC)
    assert board == ""
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_partial_per_variant_board_declaration_is_rejected() -> None:
    variants = AxisDecl(values=["a", "b"], default="a",
                        boards={"a": "va/s/rig"})   # b declares none
    board, binding, diags = resolve_board(
        "r", variants, "a", None, None, _SRC)
    assert board == ""
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_top_level_sockets_alongside_per_variant_boards_is_rejected() -> None:
    variants = AxisDecl(values=["a"], default="a", boards={"a": "va/s/rig"})
    board, binding, diags = resolve_board(
        "r", variants, "a", None, _val({"ard": _val("x")}), _SRC)
    assert board == ""
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_per_variant_board_resolves_the_selected_variants_own_board_and_sockets() -> None:
    variants = AxisDecl(
        values=["a", "b"], default="a",
        boards={"a": "va/s/rig", "b": "vb/s/rig"},
        sockets={"b": {"ard": "nucleo_ard"}})
    board, binding, diags = resolve_board("r", variants, "b", None, None, _SRC)
    assert diags == []
    assert board == "vb/s/rig"
    assert binding.get("ard") == "nucleo_ard"
    assert binding.get("other") == "other"


def test_per_variant_board_with_no_variant_selected_is_silent() -> None:
    """An earlier axis-resolution error already explains why -- this must
    not pile on a second, confusing diagnostic."""
    variants = AxisDecl(values=["a"], default="a", boards={"a": "va/s/rig"})
    board, binding, diags = resolve_board("r", variants, None, None, None, _SRC)
    assert board == ""
    assert diags == []
