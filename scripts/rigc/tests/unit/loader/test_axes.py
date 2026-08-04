"""Unit: loader.axes -- V1a qualifier axes.

The stable contracts (rigc-r2-brief.md Sec 7): axis declaration parsing
(including the mapping-entry gate `variants:` alone gets), axis
resolution's three failure shapes (undeclared axis / not-a-member /
no-default), revision normalization, and the widened fragment-stem
collision enumeration. Wording stays out of these tests where a frozen
golden already owns it (the goldens assert the target fixtures' exact
message text); here the SHAPE -- values, defaults, boards/sockets maps,
which diagnostic code fires -- is what must survive a rewrite.
"""
from __future__ import annotations

from textwrap import dedent

from pathlib import Path

from rigc.diag import SourceRef
from rigc.loader.axes import (check_axis_collision, normalize_revision,
                              revision_fragment_name, variant_fragment_name,
                              parse_axis_decl, resolve_axis)
from rigc.loader.documents import Val, parse_marked
from rigc.model import AxisDecl

_SRC = SourceRef("synthetic", 1, "rig")


def _rig(tmp_path: Path, text: str) -> Val:
    path = tmp_path / "rig.yml"
    path.write_text(dedent(text))
    doc = parse_marked(str(path))
    return doc.value["rig"]


# -------------------------------------------------------- normalization

def test_normalize_revision_replaces_dots_with_underscores() -> None:
    assert normalize_revision("1.2") == "1_2"


def test_normalize_revision_is_a_no_op_without_dots() -> None:
    assert normalize_revision("2") == "2"


def test_fragment_stem_is_name_underscore_value() -> None:
    assert variant_fragment_name("pilot", "b") == "pilot_b.yml"
    assert revision_fragment_name("pilot", "2") == "pilot_2.yml"


def test_revision_fragment_stem_normalizes_dots() -> None:
    """hwmv2's own normalization: 1.2 -> 1_2 in the CONSTRUCTED filename
    (the selected value itself stays the raw declared string)."""
    assert revision_fragment_name("pilot", "1.2") == "pilot_1_2.yml"


def test_variant_fragment_stem_is_never_normalized() -> None:
    """Normalization is a REVISION concept: a variant legally named with
    a dot keeps its raw stem (blueprint loader_yml.py:1244 vs :1250) --
    normalizing it would make the loader look for a file rule 10 and the
    collision enumerator never construct."""
    assert variant_fragment_name("pilot", "b.1") == "pilot_b.1.yml"


# ---------------------------------------------------------- declaration

def test_absent_axis_key_declares_nothing(tmp_path: Path) -> None:
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
        """)
    decl, diags = parse_axis_decl(rig_v, "revisions")
    assert decl is None
    assert diags == []


def test_bare_scalar_list_declares_values_with_no_metadata(tmp_path: Path) -> None:
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
          revisions:
            default: 1
            list: [1, 2]
        """)
    decl, diags = parse_axis_decl(rig_v, "revisions")
    assert diags == []
    assert decl == AxisDecl(values=["1", "2"], default="1")


def test_no_default_leaves_default_none(tmp_path: Path) -> None:
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
          variants:
            list: [a, b]
        """)
    decl, diags = parse_axis_decl(rig_v, "variants", allow_variant_metadata=True)
    assert diags == []
    assert decl is not None
    assert decl.default is None
    assert decl.values == ["a", "b"]


def test_default_not_a_member_is_rejected(tmp_path: Path) -> None:
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
          revisions:
            default: 3
            list: [1, 2]
        """)
    decl, diags = parse_axis_decl(rig_v, "revisions")
    assert decl is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"


def test_empty_list_is_rejected(tmp_path: Path) -> None:
    """Asserts the message text too, not just the code -- deliberately,
    against this module's own general policy above: a code-only
    assertion is exactly what let this wording go unfrozen with no
    reject-corpus fixture pinning it (now added alongside the golden
    fixture empty-revisions-list)."""
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
          revisions:
            list: []
        """)
    decl, diags = parse_axis_decl(rig_v, "revisions")
    assert decl is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert diags[0].message == "rig revisions: 'list' must be a non-empty list"


def test_mapping_entry_gated_to_variants_only(tmp_path: Path) -> None:
    """The ONE shape only variants: may take: {name:, board:, sockets:}."""
    rig_v = _rig(tmp_path, """\
        rig:
          name: r
          revisions:
            list: [1, {name: 2, board: b/s/rig}]
        """)
    decl, diags = parse_axis_decl(rig_v, "revisions",
                                  allow_variant_metadata=False)
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    # the malformed entry is skipped, not silently accepted
    assert decl is not None
    assert decl.values == ["1"]


def test_mapping_entry_collects_board_and_sockets_when_allowed(
        tmp_path: Path) -> None:
    rig_v = _rig(tmp_path,
                """\
        rig:
          name: r
          variants:
            default: a
            list:
              - name: a
                board: b1/s/rig
                sockets: {ard: nucleo_ard}
              - b
        """)
    decl, diags = parse_axis_decl(rig_v, "variants", allow_variant_metadata=True)
    assert diags == []
    assert decl is not None
    assert decl.values == ["a", "b"]
    assert decl.boards == {"a": "b1/s/rig"}
    assert decl.sockets == {"a": {"ard": "nucleo_ard"}}


# -------------------------------------------------------------- resolution

def test_resolve_selected_member_of_declared_axis() -> None:
    decl = AxisDecl(values=["1", "2"], default="1")
    value, diags = resolve_axis("r", "revision", "revisions", decl, "2", _SRC)
    assert value == "2"
    assert diags == []


def test_resolve_bare_target_takes_the_declared_default() -> None:
    decl = AxisDecl(values=["1", "2"], default="1")
    value, diags = resolve_axis("r", "revision", "revisions", decl, None, _SRC)
    assert value == "1"
    assert diags == []


def test_resolve_selected_against_undeclared_axis() -> None:
    """Failure shape 1: a selection naming an axis the rig does not
    declare AT ALL -- distinct code path from "not a member"."""
    value, diags = resolve_axis("r", "variant", "variants", None, "x", _SRC)
    assert value is None
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"


def test_resolve_selected_not_a_declared_member() -> None:
    """Failure shape 2: a selection against a declared axis, but not one
    of its values."""
    decl = AxisDecl(values=["a", "b"], default="a")
    value, diags = resolve_axis("r", "variant", "variants", decl, "c", _SRC)
    assert value is None
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"


def test_resolve_bare_target_no_default_declared() -> None:
    """Failure shape 3: a bare target against a declared axis with no
    default."""
    decl = AxisDecl(values=["a", "b"])
    value, diags = resolve_axis("r", "variant", "variants", decl, None, _SRC)
    assert value is None
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"


def test_resolve_bare_target_undeclared_axis_is_silent() -> None:
    """No selection + no declaration at all: nothing to resolve, nothing
    to report -- this is the ordinary axis-less rig."""
    value, diags = resolve_axis("r", "revision", "revisions", None, None, _SRC)
    assert value is None
    assert diags == []


def test_revision_kind_uses_lang_rev_code() -> None:
    _, diags = resolve_axis("r", "revision", "revisions", None, "9", _SRC)
    assert diags[0].code == "lang-rev"


# --------------------------------------------------- fragment-stem collision

def test_no_collision_when_axes_share_no_stem() -> None:
    variants = AxisDecl(values=["a"], default="a")
    revisions = AxisDecl(values=["1"], default="1")
    assert check_axis_collision("r", variants, revisions, _SRC) == []


def test_single_axis_collision_variant_equals_revision() -> None:
    variants = AxisDecl(values=["2"], default="2")
    revisions = AxisDecl(values=["2"], default="2")
    diags = check_axis_collision("r", variants, revisions, _SRC)
    assert len(diags) == 1
    assert diags[0].code == "lang-variant"
    assert "r_2" in diags[0].message


def test_combined_stem_collision_variant_plus_revision_vs_another_variant() -> None:
    """variant 'a_2' collides with variant 'a' + revision '2'."""
    variants = AxisDecl(values=["a", "a_2"], default="a")
    revisions = AxisDecl(values=["2"], default="2")
    diags = check_axis_collision("r", variants, revisions, _SRC)
    assert len(diags) == 1
    assert "r_a_2" in diags[0].message


def test_no_axes_declared_never_collides() -> None:
    assert check_axis_collision("r", None, None, _SRC) == []
