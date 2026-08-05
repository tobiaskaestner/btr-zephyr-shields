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


# ------------------------------------------------- injected board (S1)

def test_injection_overrides_a_top_level_board() -> None:
    board, binding, diags = resolve_board(
        "r", None, None, _val("declared/s/rig"), None, _SRC,
        injected_board="given/s/rig")
    assert diags == []
    assert board == "given/s/rig"


def test_injection_overrides_a_per_variant_board_while_its_sockets_still_apply() -> None:
    """The variant's OWN sockets: map still applies to its board being
    overridden (board-coordinate-s1-brief.md Sec 4) -- asserting the
    binding, not just the returned board, is the point: a wrong
    implementation could return the injected board while silently
    dropping or swapping the socket map."""
    variants = AxisDecl(
        values=["a", "b"], default="a",
        boards={"a": "va/s/rig", "b": "vb/s/rig"},
        sockets={"b": {"ard": "nucleo_ard"}})
    board, binding, diags = resolve_board(
        "r", variants, "b", None, None, _SRC, injected_board="given/s/rig")
    assert diags == []
    assert board == "given/s/rig"
    assert binding.get("ard") == "nucleo_ard"
    assert binding.get("other") == "other"


def test_injection_satisfies_never_neither() -> None:
    """A rig declaring no board: anywhere is legal once a board is
    injected -- the one rule injection relaxes."""
    board, binding, diags = resolve_board(
        "r", None, None, None, None, _SRC, injected_board="given/s/rig")
    assert diags == []
    assert board == "given/s/rig"
    assert binding.get("x") == "x"


def test_injection_satisfies_never_neither_with_a_top_level_sockets_map() -> None:
    """The board-agnostic shape a free-board rig actually wants: no
    board: at all, but a top-level sockets: map naming the abstract
    sockets its content uses -- the shape S5/S6 lean on. Only board_v is
    None here; sockets_v is not, so this is the other half of the branch
    test_injection_satisfies_never_neither leaves uncovered."""
    board, binding, diags = resolve_board(
        "r", None, None, None, _val({"ard": _val("nucleo_ard")}), _SRC,
        injected_board="given/s/rig")
    assert diags == []
    assert board == "given/s/rig"
    assert binding.get("ard") == "nucleo_ard"
    assert binding.get("other") == "other"


def test_no_injection_and_no_board_declared_still_rejects() -> None:
    """The negative control for the one relaxed rule: omitting
    injected_board must reproduce today's exact rejection, unchanged."""
    board, binding, diags = resolve_board("r", None, None, None, None, _SRC)
    assert board == ""
    assert binding.get("x") == "x"
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert "declares no board" in diags[0].message


def test_board_declared_twice_still_rejects_under_injection() -> None:
    """The declaration-coherence rules fire on the DECLARATION alone and
    are unaffected by injection -- a board declared twice is still an
    error even though a board was also given on the command line."""
    variants = AxisDecl(values=["a"], default="a", boards={"a": "va/s/rig"})
    board, binding, diags = resolve_board(
        "r", variants, "a", _val("b/s/rig"), None, _SRC,
        injected_board="given/s/rig")
    assert board == ""
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_partial_per_variant_board_still_rejects_under_injection() -> None:
    variants = AxisDecl(values=["a", "b"], default="a",
                        boards={"a": "va/s/rig"})   # b declares none
    board, binding, diags = resolve_board(
        "r", variants, "a", None, None, _SRC, injected_board="given/s/rig")
    assert board == ""
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
