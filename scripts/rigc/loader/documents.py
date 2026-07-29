"""The document model: mark-aware YAML parsing shared by rig.yml (the
METADATA document) and every content/delta document -- the base
<rigname>.yml and every <rigname>_<variant|rev>.yml fragment, all the
SAME flat top-level shape (rigc-r2-brief.md Sec 2, rigexp/loader_yml.py
`_load_delta_doc`'s own docstring: "there is no rig: wrapper in either
case ... so the same top-level shape and the same parser serve both").

Line-accurate anchors ride on YAML composer marks (ported from the R1
sliver unchanged): a scalar value's own start line, a nested mapping's
FIRST ENTRY line (one below the key that introduces it), a sequence
item's own line -- proven byte-exact against the frozen goldens already
by R1's four flips, which this module's rewrite must keep flipping.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from ..diag import Diagnostic, SourceRef, error
from ..unimplemented import Unimplemented

#: Top-level keys that are rig.yml METADATA and therefore never legal in
#: a content document of any kind (base <rigname>.yml or delta fragment).
METADATA_ONLY_KEYS = ("board", "sockets")


@dataclass(frozen=True)
class Val:
    """A YAML scalar/collection plus its source position. Mappings hold
    {key: Val}, sequences hold [Val]; src carries the VALUE node's own
    start line and the dotted/bracketed key path as the human label."""

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
    """Parse one YAML file into a Val tree with line-accurate marks.

    YAML parse errors (lang-parse) have no frozen golden (rigc-r2-brief.md
    Sec 2) -- Unimplemented is the always-acceptable choice (Sec 6), taken
    here rather than inventing unverified wording."""
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


def as_mapping(v: Val, what: str) -> dict[str, Val]:
    """The Val's own value as a mapping, or a loud (Unimplemented)
    refusal if it is not one -- a document shape no frozen golden
    exercises and R2 has no reason to invent wording for."""
    if not isinstance(v.value, dict):
        raise Unimplemented(f"{what} that is not a mapping")
    return v.value


def require(mapping: Val, key: str, ctx: str) -> tuple[Val | None, list[Diagnostic]]:
    """A required key's Val, or a lang-schema diagnostic naming what is
    missing -- rigexp's own `_require`, ported as a return-value
    function (diagnostics stay RETURN values, mission brief Sec 6). No
    frozen golden covers this exact wording; hand-differentialed against
    rigexp per rigc-r2-brief.md Sec 6 (recorded in the slice report)."""
    m = as_mapping(mapping, ctx)
    if key not in m:
        return None, [error(
            "lang-schema", f"{ctx}: required key '{key}' is missing",
            (mapping.src,))]
    return m[key], []


def content_file_name(rig_name: str) -> str:
    """<rigname>.yml -- CONSTRUCTED from the rig's own name:, never
    parsed from the folder it happens to live in."""
    return f"{rig_name}.yml"




def reject_metadata_keys(doc: Val) -> list[Diagnostic]:
    """The metadata/content split: board:/sockets: are rig.yml metadata
    (declared per variant, or once at top level), never legal in a
    content document -- the base <rigname>.yml and every delta fragment
    alike. Returns one error per offending key, anchored at the key's
    value node, in DECLARATION order (dict iteration order, matching
    rigexp's own fixed METADATA_ONLY_KEYS scan order)."""
    mapping = as_mapping(doc, f"content document {doc.src.file}")
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
