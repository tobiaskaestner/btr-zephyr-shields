"""Rule 10: a selected NON-DEFAULT axis value that contributes NOTHING --
the constructed-fragment-file existence check, plus the VARIANT-only
second avenue of contribution (a per-variant board/socket map that
actually DIFFERS from the default variant's). Ported value-shaped from
rigexp/loader_yml.py's `_check_fragment_presence`/`_variant_metadata_differs`
(rigc-r2-brief.md Sec 5).
"""
from __future__ import annotations

import os

from ..diag import Diagnostic, SourceRef, error
from ..model import Rig
from .axes import normalize_revision


def variant_metadata_differs(rig: Rig) -> bool:
    """Rule 10's metadata avenue: whether the SELECTED variant's own
    board and socket map actually differ from the declared DEFAULT
    variant's -- a bare board: key's presence does not itself satisfy
    this. A rig with no per-variant boards at all never contributes this
    way, since there is nothing per-variant to differ."""
    if rig.variants is None or rig.variant is None or rig.variants.default is None:
        return False
    if rig.variant == rig.variants.default:
        return False
    boards = rig.variants.boards
    if not boards:
        return False
    if boards.get(rig.variant) != boards.get(rig.variants.default):
        return True
    sockets = rig.variants.sockets
    return sockets.get(rig.variant, {}) != sockets.get(rig.variants.default, {})


def check_fragment_presence(rig: Rig, rig_dir: str, src: SourceRef,
                            has_variant_delta: bool = False,
                            has_revision_delta: bool = False,
                            ) -> list[Diagnostic]:
    """A selected NON-DEFAULT axis value naming the fragment files it
    was expected to contribute via (naming what was looked for) when
    NONE of them exist. The declared DEFAULT of an axis is exempt: the
    base rig file IS that value's content. A variant has a second way to
    contribute -- its own board/socket map, if it actually DIFFERS from
    the default's (`variant_metadata_differs`); merely declaring one is
    not itself contribution."""
    diags: list[Diagnostic] = []
    if rig.variant is not None and not (
            rig.variants is not None and rig.variant == rig.variants.default):
        overlay = f"{rig.name}_{rig.variant}.overlay"
        defconfig = f"{rig.name}_{rig.variant}_defconfig"
        delta = f"{rig.name}_{rig.variant}.yml"
        if not (has_variant_delta
                or os.path.isfile(os.path.join(rig_dir, overlay))
                or os.path.isfile(os.path.join(rig_dir, defconfig))
                or variant_metadata_differs(rig)):
            metadata_hint = ""
            if rig.variants is not None and rig.variants.boards:
                metadata_hint = (", and its board/sockets metadata does "
                                 "not differ from the default variant's")
            diags.append(error(
                "lang-variant",
                f"rig '{rig.name}': variant '{rig.variant}' contributes "
                f"nothing -- looked for {overlay}, {defconfig} and {delta}, "
                f"none exist{metadata_hint}",
                (src,)))
    if rig.revision is not None and not (
            rig.revisions is not None and rig.revision == rig.revisions.default):
        norm = normalize_revision(rig.revision)
        defconfig = f"{rig.name}_{norm}_defconfig"
        delta = f"{rig.name}_{norm}.yml"
        if not (has_revision_delta
                or os.path.isfile(os.path.join(rig_dir, defconfig))):
            diags.append(error(
                "lang-rev",
                f"rig '{rig.name}': revision '{rig.revision}' contributes "
                f"nothing -- looked for {defconfig} and {delta}, neither "
                "exists",
                (src,)))
    return diags
