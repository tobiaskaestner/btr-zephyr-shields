"""V1a qualifier axes: declaration parsing, selection resolution, the
constructed-fragment-stem collision check, and revision normalization --
ported value-shaped from rigexp/loader_yml.py's `_parse_axis_decl`/
`_resolve_axis`/`_check_axis_collision`/`_normalize_revision`
(rigc-r2-brief.md Sec 3).

**The hwmv2 seam**: this module is the ONLY place a `revisions:`/
`variants:` declaration's raw YAML is read (`parse_axis_decl`). The
resolution of a selection against a declaration is a SINGLE shared
decision, `resolve_axis_selection`, also defined here: a rig's own axis
resolution (`resolve_axis`, below) and `ShieldLibrary.resolve`
(`loader/library.py`) both delegate to it rather than each re-deriving
the three failure shapes (not-declared-at-all / not-a-member /
no-default) with their own wording. `normalize_revision` applies ONLY
at filename construction, never to a selected value. That ratified
slice later replaces the declaration shape and the resolution semantics
for rigs AND shields, in this one function -- nothing else in the
loader may inspect a declaration's raw YAML or re-derive resolution.
"""
from __future__ import annotations

from typing import Optional

from ..diag import Diagnostic, SourceRef, error
from ..model import AxisDecl
from .documents import Val, require


def normalize_revision(rev: str) -> str:
    """hwmv2's own revision normalization (zephyr_build_string,
    extensions.cmake:1772): a dotted revision id becomes underscores in
    the CONSTRUCTED filename only (1.2 -> 1_2); the SELECTED value stays
    the raw declared string for validation/provenance."""
    return rev.replace(".", "_")


def variant_fragment_name(rig_name: str, variant: str) -> str:
    """<rigname>_<variant>.yml -- the variant delta-fragment stem, from
    the RAW selected value: normalization is a REVISION concept (hwmv2
    dots-in-ids), never applied to variants (blueprint loader_yml.py:1244
    vs :1250 -- the two axes construct differently). Lives beside
    normalize_revision because stem construction IS the hwmv2 seam: the
    collision enumerator below builds the same stems."""
    return f"{rig_name}_{variant}.yml"


def revision_fragment_name(rig_name: str, revision: str) -> str:
    """<rigname>_<norm(rev)>.yml -- the revision delta-fragment stem,
    normalized in exactly ONE place (normalize_revision above); the
    selected value itself stays the raw declared string."""
    return f"{rig_name}_{normalize_revision(revision)}.yml"


def parse_axis_decl(container_v: Val, key: str,
                    owner: str = "rig",
                    allow_variant_metadata: bool = False,
                    ) -> tuple[Optional[AxisDecl], list[Diagnostic]]:
    """A `revisions:`/`variants:` declaration block: {default:, list: []}.
    Absent key -> no axis declared (None, no diagnostics). Shape is
    validated strictly: `list:` must be non-empty, and `default:` (if
    given) must be one of its own members -- both are lang-schema, since
    they are defects of the declaring FILE, not of a particular
    selection.

    `owner` names the file that declares the block: this ONE parser
    serves both rig.yml (owner="rig") and, from R3 on, shield.yml
    (owner="shield '<name>'") -- reused unchanged rather than growing a
    second parser for the identical shape.

    `allow_variant_metadata` gates the ONE shape only a rig's own
    `variants:` list may take that no other axis may: a list entry given
    as a mapping {name:, board:, sockets:} rather than a bare name. A
    rig's `revisions:` axis (and every shield.yml `revisions:`) passes
    False and so takes scalars only.

    Returns (decl, diagnostics): the parsed declaration, or None when
    the key is absent or its shape was rejected -- the diagnostics
    distinguish the two."""
    axis_v = container_v.value.get(key)
    if axis_v is None:
        return None, []
    diags: list[Diagnostic] = []
    axis_map = axis_v.value if isinstance(axis_v.value, dict) else {}
    list_v = axis_map.get("list")
    values: list[str] = []
    boards: dict[str, str] = {}
    sockets: dict[str, dict[str, str]] = {}
    for item_v in (list_v.value if list_v is not None else []):
        if isinstance(item_v.value, dict):
            if not allow_variant_metadata:
                diags.append(error(
                    "lang-schema",
                    f"{owner} {key}: a mapping entry (name:/board:/"
                    "sockets:) is legal only in a rig's variants: list -- "
                    "this axis takes bare names",
                    (item_v.src,)))
                continue
            name_v, d = require(item_v, "name", f"{owner} {key} entry")
            diags += d
            if name_v is None:
                continue
            name = str(name_v.value)
            values.append(name)
            board_v = item_v.value.get("board")
            if board_v is not None:
                boards[name] = board_v.value
            sockets_v = item_v.value.get("sockets")
            if sockets_v is not None:
                sockets[name] = {k: v.value for k, v in sockets_v.value.items()}
        else:
            values.append(str(item_v.value))
    if not values:
        diags.append(error(
            "lang-schema", f"{owner} {key}: 'list' must be a non-empty list",
            (axis_v.src,)))
        return None, diags
    default_v = axis_map.get("default")
    if default_v is None:
        return AxisDecl(values=values, boards=boards, sockets=sockets), diags
    default = str(default_v.value)
    if default not in values:
        diags.append(error(
            "lang-schema",
            f"{owner} {key}: default '{default}' is not one of the declared "
            f"values ({', '.join(values)})",
            (default_v.src,)))
        return None, diags
    return AxisDecl(values=values, default=default, boards=boards,
                    sockets=sockets), diags


def check_axis_collision(rig_name: str, variants: Optional[AxisDecl],
                         revisions: Optional[AxisDecl],
                         src: SourceRef) -> list[Diagnostic]:
    """Rule 4, WIDENED for combined fragments: no two distinct (variant,
    revision) SELECTIONS may construct the same fragment stem.
    Enumerates every stem the declared axes could ever construct -- each
    axis alone, plus every combined (variant, revision) pair -- and
    reports every collision. Subsumes the original (narrower) rule: a
    variant name equal to a revision id is the case where two
    SINGLE-axis stems collide.

    Returns the collision findings, possibly empty; the declarations
    are read-only."""
    variant_values = variants.values if variants is not None else []
    revision_values = revisions.values if revisions is not None else []
    origins: dict[str, list[str]] = {}

    def note(stem: str, origin: str) -> None:
        origins.setdefault(stem, []).append(origin)

    for v in variant_values:
        note(f"{rig_name}_{v}", f"variant '{v}'")
    for r in revision_values:
        note(f"{rig_name}_{normalize_revision(r)}", f"revision '{r}'")
    for v in variant_values:
        for r in revision_values:
            note(f"{rig_name}_{v}_{normalize_revision(r)}",
                 f"variant '{v}' + revision '{r}'")

    diags: list[Diagnostic] = []
    for stem in sorted(origins):
        stem_origins = origins[stem]
        if len(stem_origins) > 1:
            diags.append(error(
                "lang-variant",
                f"rig '{rig_name}': {' and '.join(stem_origins)} all "
                f"construct the same fragment stem '{stem}' -- the "
                "constructed filenames would be ambiguous about which "
                "selection a fragment belongs to",
                (src,)))
    return diags


def resolve_axis_selection(owner_kind: str, owner_name: str, axis_kind: str,
                           decl_key: str, decl: Optional[AxisDecl],
                           selected: Optional[str], src: SourceRef,
                           ) -> tuple[Optional[str], list[Diagnostic]]:
    """The three failure shapes a qualifier-axis resolution can hit, as
    ONE decision over values -- shared by a rig's own axis resolution
    (`resolve_axis`, below) and `ShieldLibrary.resolve`
    (`loader/library.py`), which each re-derived this inline with
    slightly different wording before this function existed. A
    `selected` value naming an axis its owner does not declare AT ALL
    says so by name ("this rig declares no revisions:" / "this shield
    declares no revisions:") rather than the generic not-a-member
    wording -- it points the author at the right place. A selected
    value against a DECLARED axis must be one of its members. A bare
    (unselected) axis takes the declared default; if the axis is
    declared but has none, that is an error.

    `owner_kind` ("rig" or "shield") constructs both the quoted-name
    prefix and the possessive ("this rig" / "this shield") -- the two
    callers' wording differs in exactly that one word, nowhere else.
    `axis_kind` ("revision" or "variant") and `decl_key` (the declaring
    YAML key: "revisions" or "variants") construct the rest; a shield
    always passes ("shield", name, "revision", "revisions"), since a
    shield declares only that one axis. This function does no IO and
    triggers no parsing -- callers that need to act on the resolved
    value (constructing a fragment filename, parsing a shield revision's
    template) do that themselves, around this decision.

    Returns (value, diagnostics): the selected axis value, or None
    either legitimately (no axis declared and nothing selected) or
    after a reported failure -- an error in the list is what
    distinguishes them. `decl` is read-only to this function."""
    code = "lang-rev" if axis_kind == "revision" else "lang-variant"
    if selected is not None:
        if decl is None:
            return None, [error(
                code,
                f"{owner_kind} '{owner_name}' names a {axis_kind} "
                f"({selected!r}), but this {owner_kind} declares no "
                f"{decl_key}: at all",
                (src,))]
        if selected not in decl.values:
            return None, [error(
                code,
                f"{owner_kind} '{owner_name}': {axis_kind} '{selected}' is "
                f"not declared -- known {axis_kind}s: "
                f"{', '.join(decl.values)}",
                (src,))]
        return selected, []
    if decl is None:
        return None, []
    if decl.default is not None:
        return decl.default, []
    return None, [error(
        code,
        f"{owner_kind} '{owner_name}': no {axis_kind} selected, and this "
        f"{owner_kind} declares no default {axis_kind} -- choose one of: "
        f"{', '.join(decl.values)}",
        (src,))]


def resolve_axis(rig_name: str, axis_kind: str, decl_key: str,
                 decl: Optional[AxisDecl], selected: Optional[str],
                 src: SourceRef) -> tuple[Optional[str], list[Diagnostic]]:
    """Resolve ONE of a rig's own qualifier axes (`revision` or
    `variant`) to its final SELECTED value -- the rig-owned instance of
    `resolve_axis_selection`'s shared decision (`owner_kind="rig"`).

    Returns (value, diagnostics): the selected axis value, or None
    either legitimately (no axis declared and nothing selected) or
    after a reported failure -- an error in the list is what
    distinguishes them."""
    return resolve_axis_selection("rig", rig_name, axis_kind, decl_key,
                                  decl, selected, src)
