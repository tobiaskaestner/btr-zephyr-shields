"""Unit: loader.fragments -- rule 10, the fragment-presence check.

The stable contract: a selected NON-DEFAULT axis value must contribute
something (an existing delta doc, a cmake-collected overlay/defconfig,
or -- variants only -- board/socket metadata that actually differs from
the default variant's); the declared DEFAULT is always exempt.
`variant_metadata_differs` is exercised directly, since it is the one
"presence is not itself contribution" subtlety the wording alone would
not make obvious to a future rewrite.
"""
from __future__ import annotations

from pathlib import Path

from rigc.diag import SourceRef
from rigc.loader.fragments import check_fragment_presence, variant_metadata_differs
from rigc.model import AxisDecl, Rig

_SRC = SourceRef("synthetic", 1, "rig")


def _rig(variant: "str | None" = None, revision: "str | None" = None,
        variants: "AxisDecl | None" = None,
        revisions: "AxisDecl | None" = None) -> Rig:
    return Rig(name="r", variant=variant, revision=revision,
              variants=variants, revisions=revisions)


# ------------------------------------------------------ variant_metadata_differs

def test_no_variants_axis_never_differs() -> None:
    assert variant_metadata_differs(_rig(variant="a")) is False


def test_default_variant_never_differs() -> None:
    variants = AxisDecl(values=["a"], default="a", boards={"a": "b/s/rig"})
    assert variant_metadata_differs(_rig(variant="a", variants=variants)) is False


def test_no_per_variant_boards_never_differs() -> None:
    variants = AxisDecl(values=["a", "b"], default="a")   # no boards at all
    assert variant_metadata_differs(_rig(variant="b", variants=variants)) is False


def test_restated_board_and_sockets_do_not_differ() -> None:
    variants = AxisDecl(values=["a", "b"], default="a",
                        boards={"a": "b/s/rig", "b": "b/s/rig"},
                        sockets={"a": {"x": "y"}, "b": {"x": "y"}})
    assert variant_metadata_differs(_rig(variant="b", variants=variants)) is False


def test_different_board_differs() -> None:
    variants = AxisDecl(values=["a", "b"], default="a",
                        boards={"a": "ba/s/rig", "b": "bb/s/rig"})
    assert variant_metadata_differs(_rig(variant="b", variants=variants)) is True


def test_same_board_different_sockets_differs() -> None:
    variants = AxisDecl(values=["a", "b"], default="a",
                        boards={"a": "b/s/rig", "b": "b/s/rig"},
                        sockets={"a": {"x": "y"}, "b": {"x": "z"}})
    assert variant_metadata_differs(_rig(variant="b", variants=variants)) is True


# --------------------------------------------------------- check_fragment_presence

def test_default_variant_and_revision_are_exempt(tmp_path: Path) -> None:
    variants = AxisDecl(values=["a"], default="a")
    revisions = AxisDecl(values=["1"], default="1")
    rig = _rig(variant="a", revision="1", variants=variants, revisions=revisions)
    diags = check_fragment_presence(rig, str(tmp_path), _SRC)
    assert diags == []


def test_nondefault_variant_with_a_delta_file_on_disk_is_exempt(
        tmp_path: Path) -> None:
    variants = AxisDecl(values=["a", "b"], default="a")
    rig = _rig(variant="b", variants=variants)
    diags = check_fragment_presence(rig, str(tmp_path), _SRC,
                                    has_variant_delta=True)
    assert diags == []


def test_nondefault_variant_contributing_nothing_is_rejected(tmp_path: Path) -> None:
    variants = AxisDecl(values=["a", "b"], default="a")
    rig = _rig(variant="b", variants=variants)
    diags = check_fragment_presence(rig, str(tmp_path), _SRC)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "r_b.overlay" in diags[0].message
    assert "r_b_defconfig" in diags[0].message
    assert "r_b.yml" in diags[0].message


def test_metadata_hint_appears_only_when_variants_declare_boards(
        tmp_path: Path) -> None:
    """Structural, not wording (the exact hint bytes belong to the
    variant-board-restated golden alone): the same selection produces a
    LONGER message when per-variant boards exist -- the hint is appended
    -- and the boards-less message is its prefix."""
    with_boards = AxisDecl(values=["a", "b"], default="a",
                           boards={"a": "x/s/rig", "b": "x/s/rig"})
    without_boards = AxisDecl(values=["a", "b"], default="a")
    hinted = check_fragment_presence(
        _rig(variant="b", variants=with_boards), str(tmp_path), _SRC)
    plain = check_fragment_presence(
        _rig(variant="b", variants=without_boards), str(tmp_path), _SRC)
    assert hinted[0].message.startswith(plain[0].message)
    assert len(hinted[0].message) > len(plain[0].message)


def test_nondefault_revision_contributing_nothing_is_rejected(tmp_path: Path) -> None:
    revisions = AxisDecl(values=["1", "2"], default="1")
    rig = _rig(revision="2", revisions=revisions)
    diags = check_fragment_presence(rig, str(tmp_path), _SRC)
    assert len(diags) == 1
    assert diags[0].code == "lang-rev"
    assert "r_2_defconfig" in diags[0].message
    assert "r_2.yml" in diags[0].message


def test_dotted_revision_names_the_normalized_filename(tmp_path: Path) -> None:
    revisions = AxisDecl(values=["1", "1.5"], default="1")
    rig = _rig(revision="1.5", revisions=revisions)
    diags = check_fragment_presence(rig, str(tmp_path), _SRC)
    assert "r_1_5_defconfig" in diags[0].message
    assert "r_1.5_defconfig" not in diags[0].message
