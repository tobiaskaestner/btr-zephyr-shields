"""Unit: loader.fragments -- rule 10, the fragment-presence check.

The stable contract: a selected NON-DEFAULT axis value must contribute
something (an existing delta doc, a cmake-collected overlay/defconfig,
or -- variants only -- board/socket metadata that actually differs from
the default variant's); the declared DEFAULT is always exempt. The rule
is PURE: which files exist arrives as a FragmentPresence VALUE (the IO
phase probes; joint review 2026-07-29), so nothing here touches a
filesystem -- no tmp_path, no fixture files.
`variant_metadata_differs` is exercised directly, since it is the one
"presence is not itself contribution" subtlety the wording alone would
not make obvious to a future rewrite.
"""
from __future__ import annotations

from rigc.diag import SourceRef
from rigc.loader.fragments import (FragmentPresence,
                                   check_fragment_presence,
                                   revision_contribution_names,
                                   variant_contribution_names,
                                   variant_metadata_differs)
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

def test_default_variant_and_revision_are_exempt() -> None:
    variants = AxisDecl(values=["a"], default="a")
    revisions = AxisDecl(values=["1"], default="1")
    rig = _rig(variant="a", revision="1", variants=variants, revisions=revisions)
    diags = check_fragment_presence(rig, _SRC, FragmentPresence())
    assert diags == []


def test_nondefault_variant_with_a_loaded_delta_is_exempt() -> None:
    variants = AxisDecl(values=["a", "b"], default="a")
    rig = _rig(variant="b", variants=variants)
    diags = check_fragment_presence(rig, _SRC,
                                    FragmentPresence(variant_delta=True))
    assert diags == []


def test_nondefault_variant_contributing_nothing_is_rejected() -> None:
    variants = AxisDecl(values=["a", "b"], default="a")
    rig = _rig(variant="b", variants=variants)
    diags = check_fragment_presence(rig, _SRC, FragmentPresence())
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "r_b.overlay" in diags[0].message
    assert "r_b_defconfig" in diags[0].message
    assert "r_b.yml" in diags[0].message


def test_metadata_hint_appears_only_when_variants_declare_boards() -> None:
    """Structural, not wording (the exact hint bytes belong to the
    variant-board-restated golden alone): the same selection produces a
    LONGER message when per-variant boards exist -- the hint is appended
    -- and the boards-less message is its prefix."""
    with_boards = AxisDecl(values=["a", "b"], default="a",
                           boards={"a": "x/s/rig", "b": "x/s/rig"})
    without_boards = AxisDecl(values=["a", "b"], default="a")
    hinted = check_fragment_presence(
        _rig(variant="b", variants=with_boards), _SRC, FragmentPresence())
    plain = check_fragment_presence(
        _rig(variant="b", variants=without_boards), _SRC, FragmentPresence())
    assert hinted[0].message.startswith(plain[0].message)
    assert len(hinted[0].message) > len(plain[0].message)


def test_nondefault_revision_contributing_nothing_is_rejected() -> None:
    revisions = AxisDecl(values=["1", "2"], default="1")
    rig = _rig(revision="2", revisions=revisions)
    diags = check_fragment_presence(rig, _SRC, FragmentPresence())
    assert len(diags) == 1
    assert diags[0].code == "lang-rev"
    assert "r_2_defconfig" in diags[0].message
    assert "r_2.yml" in diags[0].message


def test_dotted_revision_names_the_normalized_filename() -> None:
    revisions = AxisDecl(values=["1", "1.5"], default="1")
    rig = _rig(revision="1.5", revisions=revisions)
    diags = check_fragment_presence(rig, _SRC, FragmentPresence())
    assert "r_1_5_defconfig" in diags[0].message
    assert "r_1.5_defconfig" not in diags[0].message


def test_an_existing_overlay_or_defconfig_counts_as_contribution() -> None:
    """The two cmake-collected artifact kinds satisfy rule 10 exactly
    like a loaded delta does -- the presence FACT arrives as a value."""
    variants = AxisDecl(values=["a", "b"], default="a")
    rig = _rig(variant="b", variants=variants)
    assert check_fragment_presence(
        rig, _SRC, FragmentPresence(variant_overlay=True)) == []
    assert check_fragment_presence(
        rig, _SRC, FragmentPresence(variant_defconfig=True)) == []
    revisions = AxisDecl(values=["1", "2"], default="1")
    rig = _rig(revision="2", revisions=revisions)
    assert check_fragment_presence(
        rig, _SRC, FragmentPresence(revision_defconfig=True)) == []


def test_contribution_names_are_the_single_stem_source() -> None:
    """The probes (IO phase) and the message text share these
    constructors -- variant stems stay RAW, revision stems normalize."""
    assert variant_contribution_names("r", "b.1") == (
        "r_b.1.overlay", "r_b.1_defconfig", "r_b.1.yml")
    assert revision_contribution_names("r", "1.5") == (
        "r_1_5_defconfig", "r_1_5.yml")
