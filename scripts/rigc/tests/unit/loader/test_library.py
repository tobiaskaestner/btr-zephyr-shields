"""Unit: loader.library -- the shield library's VALUE-shaped contracts
(rigc-r3-brief.md Sec 6): `_pick_shield`'s folder-name-vs-node-name
decision (a pure function over already-parsed Shield values), `resolve()`'s
three failure shapes plus lazy-parse memoization (exercised against a
synthetic library VALUE, never a filesystem scan), and shield.yml's
`revisions:` axis parsing (`_load_shield_revisions`, file-based but
cpp-free).

**The cpp/unit-test seam**: `load_shield_library`'s EAGER parse branch and
`ShieldLibrary._resolve_revision`'s SUCCESS path both call `dtsio.parse_tu`
(cpp, a real subprocess) -- integration-only by construction, covered
through the frozen suite's front door. Every test here either constructs a
`ShieldLibrary` value directly (never scanning a filesystem) or arranges
for `resolve()` to return before ever reaching `_resolve_revision`'s
parse_tu call (a cache hit, or one of the three failure shapes) --
`load_shield_library`'s DISCOVERY is exercised too, but only over shield
folders that declare a `revisions:` axis (deferred to `pending`, never
eagerly parsed), so scanning itself stays subprocess-free here.
"""
from __future__ import annotations

from textwrap import dedent

from pathlib import Path

from rigc.diag import SourceRef
from rigc.model import AxisDecl, Shield
from rigc.loader.library import (ShieldLibrary, _load_shield_revisions,
                                 _pick_shield, load_shield_library)

_SRC = SourceRef("synthetic", 1, "instance 'x'")


def _shield(name: str) -> Shield:
    return Shield(name=name, label=name, plugs="fixture-type",
                  src=SourceRef("synthetic", 1))


# ---------------------------------------------------------------- _pick_shield

def test_pick_shield_matches_by_folder_name() -> None:
    parsed = {"other": _shield("other"), "wanted": _shield("wanted")}
    shield, diags = _pick_shield(parsed, "wanted", "/some/wanted/wanted.shield")
    assert diags == []
    assert shield is parsed["wanted"]


def test_pick_shield_mismatch_is_rejected() -> None:
    parsed = {"other_name": _shield("other_name")}
    shield, diags = _pick_shield(parsed, "misnamed", "/x/misnamed/misnamed.shield")
    assert shield is None
    assert len(diags) == 1
    assert diags[0].code == "lang-shield-name"
    assert "other_name" in diags[0].message
    assert "misnamed.shield" in diags[0].message


def test_pick_shield_reports_none_when_the_template_defines_nothing() -> None:
    shield, diags = _pick_shield({}, "empty", "/x/empty/empty.shield")
    assert shield is None
    assert "nodes defined here: none" in diags[0].message


# ------------------------------------------------------- _load_shield_revisions

def test_load_shield_revisions_absent_file_declares_no_axis(tmp_path: Path) -> None:
    decl, diags = _load_shield_revisions(str(tmp_path))
    assert decl is None
    assert diags == []


def test_load_shield_revisions_no_revisions_key_declares_no_axis(tmp_path: Path) -> None:
    (tmp_path / "shield.yml").write_text(dedent("""\
        shield:
          name: fx
        """))
    decl, diags = _load_shield_revisions(str(tmp_path))
    assert decl is None
    assert diags == []


def test_load_shield_revisions_parses_the_declared_axis(tmp_path: Path) -> None:
    (tmp_path / "shield.yml").write_text(
        dedent("""\
        shield:
          name: fx
          revisions:
            default: "1"
            list: ["1", "2"]
        """))
    decl, diags = _load_shield_revisions(str(tmp_path))
    assert diags == []
    assert decl == AxisDecl(values=["1", "2"], default="1")


def test_load_shield_revisions_bad_default_is_blamed_on_the_shield(tmp_path: Path) -> None:
    shield_dir = tmp_path / "fx"
    shield_dir.mkdir()
    (shield_dir / "shield.yml").write_text(
        dedent("""\
        shield:
          name: fx
          revisions:
            default: "3"
            list: ["1", "2"]
        """))
    decl, diags = _load_shield_revisions(str(shield_dir))
    assert decl is None
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert "shield 'fx' revisions:" in diags[0].message


def test_load_shield_revisions_mapping_entry_is_blamed_on_the_shield(tmp_path: Path) -> None:
    """A mapping entry in a shield's OWN revisions: list is illegal (only
    a rig's variants: list allows it) -- rejected per-entry, so the
    remaining well-formed entries still constitute a valid (partial) axis
    (parse_axis_decl's own per-item `continue`, ported unchanged)."""
    shield_dir = tmp_path / "fx"
    shield_dir.mkdir()
    (shield_dir / "shield.yml").write_text(
        dedent("""\
        shield:
          name: fx
          revisions:
            list: ["1", {name: "2", board: some/board}]
        """))
    decl, diags = _load_shield_revisions(str(shield_dir))
    assert decl == AxisDecl(values=["1"])
    assert len(diags) == 1
    assert diags[0].code == "lang-schema"
    assert "shield 'fx' revisions:" in diags[0].message
    assert "legal only in a rig's variants: list" in diags[0].message


# ------------------------------------------------------- resolve(): failure shapes

def test_resolve_unknown_shield_is_lang_instance_shield() -> None:
    lib = ShieldLibrary(shields={}, axes={}, pending={}, ymls={}, types={},
                        workdir="/nonexistent")
    shield, diags, deps = lib.resolve("ghost", "instance 'x'", _SRC)
    assert shield is None
    assert len(diags) == 1
    assert diags[0].code == "lang-instance-shield"
    assert deps == frozenset()


def test_resolve_a_declared_default_axis_shield_returns_the_cached_value() -> None:
    """The general (non-@rev, already-cached) path never needs
    `_resolve_revision`/parse_tu at all."""
    sh = _shield("plain")
    lib = ShieldLibrary(shields={"plain": sh}, axes={"plain": None}, pending={},
                        ymls={}, types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("plain", "instance 'x'", _SRC)
    assert shield is sh
    assert diags == []


def test_resolve_bare_name_with_no_declared_axis_and_no_eager_parse_returns_none() -> None:
    """A shield with NO declared axis but ALSO not in `shields` (its
    template defined no matching node -- already reported by
    `_pick_shield` at scan time) resolves quietly, no echo."""
    lib = ShieldLibrary(shields={}, axes={"plain": None}, pending={}, ymls={},
                        types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("plain", "instance 'x'", _SRC)
    assert shield is None
    assert diags == []


def test_resolve_at_rev_against_undeclared_axis() -> None:
    lib = ShieldLibrary(shields={}, axes={"fx": None}, pending={}, ymls={},
                        types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("fx@1", "instance 'x'", _SRC)
    assert shield is None
    assert diags[0].code == "lang-rev"
    assert "declares no revisions: at all" in diags[0].message


def test_resolve_at_rev_not_a_declared_member() -> None:
    decl = AxisDecl(values=["1", "2"], default="1")
    lib = ShieldLibrary(shields={}, axes={"fx": decl}, pending={}, ymls={},
                        types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("fx@99", "instance 'x'", _SRC)
    assert shield is None
    assert diags[0].code == "lang-rev"
    assert "not declared" in diags[0].message
    assert "1, 2" in diags[0].message


def test_resolve_bare_name_with_a_declared_axis_but_no_default() -> None:
    decl = AxisDecl(values=["1", "2"], default=None)
    lib = ShieldLibrary(shields={}, axes={"fx": decl}, pending={}, ymls={},
                        types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("fx", "instance 'x'", _SRC)
    assert shield is None
    assert diags[0].code == "lang-rev"
    assert "no default revision" in diags[0].message


def test_resolve_memoizes_a_cached_revision_without_reparsing() -> None:
    """Lazy-parse memoization: a revision already resolved once (present
    in `shields` under its "<name>@<rev>" key) is returned AS-IS on a
    second call -- the cache-hit branch inside `_resolve_revision`, which
    never touches parse_tu/cpp."""
    decl = AxisDecl(values=["1", "2"], default="1")
    cached = _shield("fx")
    lib = ShieldLibrary(shields={"fx@2": cached}, axes={"fx": decl}, pending={},
                        ymls={}, types={}, workdir="/nonexistent")
    shield, diags, deps = lib.resolve("fx@2", "instance 'x'", _SRC)
    assert shield is cached
    assert diags == []
    assert deps == frozenset()


def test_resolve_records_the_shield_yml_dependency_when_referenced() -> None:
    """A shield's own shield.yml becomes load-bearing (dependency data)
    only once something actually NAMES it -- recorded at resolve() time,
    never at scan time (rigc-r3-brief.md Sec 4)."""
    cached = _shield("fx")
    lib = ShieldLibrary(shields={"fx": cached}, axes={"fx": None}, pending={},
                        ymls={"fx": "/some/fx/shield.yml"}, types={},
                        workdir="/nonexistent")
    shield, diags, deps = lib.resolve("fx", "instance 'x'", _SRC)
    assert shield is cached
    assert deps == frozenset({"/some/fx/shield.yml"})


def test_resolve_no_dependency_when_the_shield_has_no_yml() -> None:
    cached = _shield("fx")
    lib = ShieldLibrary(shields={"fx": cached}, axes={"fx": None}, pending={},
                        ymls={}, types={}, workdir="/nonexistent")
    _, _, deps = lib.resolve("fx", "instance 'x'", _SRC)
    assert deps == frozenset()


# ------------------------------------------------------- load_shield_library scan

def _declared_shield_folder(root: Path, name: str, revisions: str = "1") -> None:
    """A shield folder that declares a revisions: axis -- scanned but
    deferred to `pending`, so `load_shield_library` never calls
    parse_tu/cpp for it (keeps this whole test subprocess-free)."""
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.shield").write_text(f"/* fixture: {name} */\n")
    (d / "shield.yml").write_text(
        f"shield:\n  name: {name}\n  revisions:\n"
        f"    default: \"{revisions}\"\n    list: [\"{revisions}\"]\n")


def test_scan_discovers_exactly_basename_dot_shield(tmp_path: Path) -> None:
    root = tmp_path / "shields"
    _declared_shield_folder(root, "fx_a")
    _declared_shield_folder(root, "fx_b")
    # A legacy Kconfig.shield fragment -- must NOT be mis-globbed as a
    # shield template (it ends in the literal substring ".shield").
    (root / "fx_a" / "Kconfig.shield").write_text(dedent("""\
        # not a shield template
        """))
    lib, diags, deps = load_shield_library(str(tmp_path / "work"),
                                          shield_dirs=[str(root)], types={})
    assert diags == []
    assert set(lib.pending) == {"fx_a", "fx_b"}
    assert lib.shields == {}    # both deferred (declared axis), never eager-parsed


def test_scan_skips_a_folder_with_no_matching_dot_shield_file(tmp_path: Path) -> None:
    root = tmp_path / "shields"
    root.mkdir()
    stray = root / "not_a_shield"
    stray.mkdir()
    (stray / "Kconfig.shield").write_text(dedent("""\
        # no not_a_shield.shield beside it
        """))
    lib, diags, deps = load_shield_library(str(tmp_path / "work"),
                                          shield_dirs=[str(root)], types={})
    assert diags == []
    assert lib.pending == {}
    assert lib.shields == {}


def test_scan_unions_multiple_shield_dirs(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _declared_shield_folder(root_a, "from_a")
    _declared_shield_folder(root_b, "from_b")
    lib, diags, deps = load_shield_library(
        str(tmp_path / "work"), shield_dirs=[str(root_a), str(root_b)], types={})
    assert set(lib.pending) == {"from_a", "from_b"}


# NOTE: a malformed shield.yml revisions: block (`_load_shield_revisions`
# returning decl=None from a BAD declaration, tested directly above) makes
# `load_shield_library`'s scan treat the shield as axis-less and eagerly
# parse its base template -- exactly the golden fixture
# `shield-bad-revisions-block`'s own shape. That eager parse calls
# dtsio.parse_tu (cpp, a real subprocess), so the scenario stays
# integration-only (covered already, through the frozen suite's front
# door) rather than getting a second unit test here that would need a
# real `.shield` DTS body and a real cpp call to reach.
