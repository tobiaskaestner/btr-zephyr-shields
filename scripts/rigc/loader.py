"""Loader, R1 sliver: exactly what the proof-of-life rejects need.

The full loader is R2's slice. What exists here, deliberately thin
(rigc-r1-brief.md Sec 6):

  - mark-aware YAML parsing (value-node line marks, dotted key paths) --
    the anchor machinery has to be real for the golden anchor lines to
    match byte-for-byte;
  - content filename CONSTRUCTION from the rig's own name: (construct-
    don't-parse, the Q6 discipline -- never parsed from the folder), and
    the hwmv2 fragment-stem normalization (dots -> underscores);
  - the missing-content-file rejection;
  - the metadata/content key split: a content document (base or delta)
    carrying `board:` or `sockets:` is rejected -- those are rig.yml
    metadata;
  - just enough revision-axis selection to reach a revision delta
    fragment (--revision naming a declared list member whose fragment
    file exists).

Everything else raises Unimplemented, which cli.main() turns into the
exit-3 refusal -- never a traceback, never a wrong verdict.

Diagnostics are RETURN values (see diag.py): load() returns the list of
findings; the caller decides what an error-carrying list means.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from .diag import Diagnostic, SourceRef, error
from .unimplemented import Unimplemented

#: Top-level keys that are rig.yml METADATA and therefore never legal in
#: a content document of any kind (base <rigname>.yml or delta fragment).
METADATA_ONLY_KEYS = ("board", "sockets")

#: Top-level content-document keys the R1 sliver knows how to look at.
_CONTENT_KEYS_IN_SCOPE = frozenset(METADATA_ONLY_KEYS + ("instances",))
_DELTA_KEYS_IN_SCOPE = frozenset(METADATA_ONLY_KEYS)


@dataclass(frozen=True)
class Val:
    """A YAML scalar/collection plus its source position. Mappings hold
    {key: Val}, sequences hold [Val]; src carries the VALUE node's own
    start line (a mapping value under a key therefore anchors at its
    first entry's line, one below the key that introduces it) and the
    dotted key path as the human label."""

    value: Any
    src: SourceRef


def _scalar(node: Any) -> Any:
    v = node.value
    if node.tag.endswith(":int"):
        return int(v.replace("_", ""), 0)
    if node.tag.endswith(":bool"):
        return v.lower() in ("true", "yes", "on")
    if node.tag.endswith(":null"):
        return None
    return v


def _walk(node: Any, path: str, fname: str) -> Val:
    src = SourceRef(fname, node.start_mark.line + 1, path)
    if isinstance(node, yaml.MappingNode):
        m = {}
        for k, v in node.value:
            key = k.value
            m[key] = _walk(v, f"{path}.{key}" if path else key, fname)
        return Val(m, src)
    if isinstance(node, yaml.SequenceNode):
        return Val([_walk(v, f"{path}[{i}]", fname)
                    for i, v in enumerate(node.value)], src)
    return Val(_scalar(node), src)


def parse_marked(path: str) -> Val:
    """Parse one YAML file into a Val tree with line-accurate marks."""
    try:
        with open(path) as f:
            try:
                root = yaml.compose(f, yaml.SafeLoader)
            except yaml.YAMLError:
                raise Unimplemented(f"YAML parse failure in {path}")
    except OSError:
        raise Unimplemented(f"cannot read {path}")
    if root is None:
        raise Unimplemented(f"empty YAML document {path}")
    return _walk(root, "", path)


def _as_mapping(v: Val, what: str) -> dict[str, Val]:
    if not isinstance(v.value, dict):
        raise Unimplemented(f"{what} that is not a mapping")
    return v.value


def content_file_name(rig_name: str) -> str:
    """<rigname>.yml -- CONSTRUCTED from the rig's own name:, never
    parsed from the folder it happens to live in."""
    return f"{rig_name}.yml"


def fragment_file_name(rig_name: str, axis_value: str) -> str:
    """<rigname>_<value>.yml -- the delta-fragment stem, with hwmv2's own
    revision normalization: a dotted id becomes underscores in the
    CONSTRUCTED filename only (1.2 -> 1_2); the selected value itself
    stays the raw declared string."""
    return f"{rig_name}_{axis_value.replace('.', '_')}.yml"


def reject_metadata_keys(doc: Val) -> list[Diagnostic]:
    """The metadata/content split: board:/sockets: are rig.yml metadata
    (declared per variant, or once at top level), never legal in a
    content document -- the base <rigname>.yml and every delta fragment
    alike. Returns one error per offending key, anchored at the key's
    value node."""
    mapping = _as_mapping(doc, f"content document {doc.src.file}")
    diags: list[Diagnostic] = []
    for key in METADATA_ONLY_KEYS:
        key_v = mapping.get(key)
        if key_v is not None:
            diags.append(error(
                "lang-schema",
                f"{doc.src.file}: '{key}:' is rig.yml metadata -- move "
                "it to the variant that owns it (or the top-level rig: "
                "block, for a single-board rig), not a content file",
                (key_v.src,)))
    return diags


def _select_revision(rig_map: dict[str, Val], revision: str | None) -> str | None:
    """Just enough of the revisions: axis to reach a revision delta: an
    explicit --revision naming a member of a well-formed declared list is
    selected; every other combination is beyond the R1 sliver."""
    axis_v = rig_map.get("revisions")
    if revision is None:
        if axis_v is not None:
            raise Unimplemented(
                "bare target against a revisions: axis (default selection)")
        return None
    if axis_v is None:
        raise Unimplemented("--revision against a rig declaring no revisions: axis")
    axis = _as_mapping(axis_v, "revisions: declaration")
    list_v = axis.get("list")
    if list_v is None or not isinstance(list_v.value, list):
        raise Unimplemented("revisions: declaration without a well-formed list:")
    values: list[str] = []
    for item in list_v.value:
        if isinstance(item.value, (dict, list)):
            raise Unimplemented("revisions: list entry that is not a scalar")
        values.append(str(item.value))
    if revision not in values:
        raise Unimplemented(
            f"--revision '{revision}' outside the declared revisions: list")
    return revision


def _guard_keys(mapping: dict[str, Val], in_scope: frozenset[str],
                what: str) -> None:
    for key in sorted(mapping):
        if key not in in_scope:
            raise Unimplemented(f"{what} key '{key}:'")


def load(rig_path: str, revision: str | None = None,
         variant: str | None = None) -> list[Diagnostic]:
    """Load rig_path (absolute) as far as the R1 sliver reaches and
    return every finding as data. An empty list means nothing in scope
    rejected the input -- which R1 has no accept path for, so the caller
    refuses onward from there."""
    doc = parse_marked(rig_path)
    rig_v = _as_mapping(doc, "rig.yml top level").get("rig")
    if rig_v is None:
        raise Unimplemented("rig.yml without a rig: block")
    rig_map = _as_mapping(rig_v, "rig: block")

    name_v = rig_map.get("name")
    if name_v is None or not isinstance(name_v.value, str):
        raise Unimplemented("rig: block without a scalar name:")
    name = name_v.value

    if variant is not None:
        raise Unimplemented("--variant selection")
    if "variants" in rig_map:
        raise Unimplemented("variants: axis")
    selected_revision = _select_revision(rig_map, revision)
    if "board" not in rig_map:
        raise Unimplemented("rig.yml without a top-level board:")

    # The rig's REQUIRED content file, named from the rig's own identity.
    rig_dir = os.path.dirname(rig_path)
    content_path = os.path.join(rig_dir, content_file_name(name))
    if not os.path.isfile(content_path):
        return [error(
            "lang-content",
            f"rig '{name}': no content file found -- expected {content_path}",
            (rig_v.src,))]

    content = parse_marked(content_path)
    diags = reject_metadata_keys(content)
    content_map = _as_mapping(content, f"content document {content_path}")
    _guard_keys(content_map, _CONTENT_KEYS_IN_SCOPE, "content file")
    insts_v = content_map.get("instances")
    if insts_v is None:
        raise Unimplemented("content file without instances:")
    if not (isinstance(insts_v.value, list) and not insts_v.value):
        raise Unimplemented("instances: entries")

    # Delta stage, revision only: the one fragment shape in scope.
    if selected_revision is not None:
        frag_path = os.path.join(
            rig_dir, fragment_file_name(name, selected_revision))
        if not os.path.isfile(frag_path):
            raise Unimplemented(
                f"revision '{selected_revision}' selected with no fragment file")
        frag = parse_marked(frag_path)
        frag_map = _as_mapping(frag, f"revision fragment {frag_path}")
        _guard_keys(frag_map, _DELTA_KEYS_IN_SCOPE, "revision fragment")
        diags += reject_metadata_keys(frag)

    return diags
