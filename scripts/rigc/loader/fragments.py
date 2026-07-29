"""Rule 10: a selected NON-DEFAULT axis value that contributes NOTHING --
the constructed-fragment-file contribution check, plus the VARIANT-only
second avenue of contribution (a per-variant board/socket map that
actually DIFFERS from the default variant's). Ported value-shaped from
rigexp/loader_yml.py's `_check_fragment_presence`/`_variant_metadata_differs`
(rigc-r2-brief.md Sec 5).

PURE, deliberately (joint review 2026-07-29: IO at the edges, compute on
values): which files exist is probed by the CALLER -- the loader's IO
phase, `_gather_content` -- and arrives here as a `FragmentPresence`
value, so the rule itself decides over values and its tests construct
values instead of a tmp directory. The name CONSTRUCTION stays here, in
the two `*_contribution_names` helpers, single-sourced for both the
caller's probes and this module's own message text (the R2-review lesson:
duplicated stem construction is where variant/revision normalization
drift hides).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..diag import Diagnostic, SourceRef, error
from ..model import Rig
from .axes import normalize_revision


def variant_contribution_names(rig_name: str, variant: str,
                               ) -> tuple[str, str, str]:
    """Returns the three artifact names a selected variant may contribute
    via, in message order: (overlay, defconfig, yml delta). Pure
    construction from the SELECTED value -- raw, never normalized
    (normalization is a revision concept)."""
    return (f"{rig_name}_{variant}.overlay",
            f"{rig_name}_{variant}_defconfig",
            f"{rig_name}_{variant}.yml")


def revision_contribution_names(rig_name: str, revision: str,
                                ) -> tuple[str, str]:
    """Returns the two artifact names a selected revision may contribute
    via, in message order: (defconfig, yml delta) -- stems built from the
    NORMALIZED revision (the one place dots become underscores,
    axes.normalize_revision)."""
    norm = normalize_revision(revision)
    return (f"{rig_name}_{norm}_defconfig", f"{rig_name}_{norm}.yml")


@dataclass(frozen=True)
class FragmentPresence:
    """Which contribution artifacts EXIST on disk for the selected axis
    values -- the caller probes the filesystem (using the
    `*_contribution_names` helpers above) and hands the facts in. The
    yml-delta flags double as "the delta was found AND loaded" (the
    caller already opened them)."""

    variant_delta: bool = False
    variant_overlay: bool = False
    variant_defconfig: bool = False
    revision_delta: bool = False
    revision_defconfig: bool = False


def variant_metadata_differs(rig: Rig) -> bool:
    """Rule 10's metadata avenue: whether the SELECTED variant's own
    board and socket map actually differ from the declared DEFAULT
    variant's -- a bare board: key's presence does not itself satisfy
    this. A rig with no per-variant boards at all never contributes this
    way, since there is nothing per-variant to differ. Returns the bare
    decision; reads rig only."""
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


def check_fragment_presence(rig: Rig, src: SourceRef,
                            present: FragmentPresence,
                            ) -> list[Diagnostic]:
    """A selected NON-DEFAULT axis value naming the fragment files it
    was expected to contribute via (naming what was looked for) when
    NONE of them exist. The declared DEFAULT of an axis is exempt: the
    base rig file IS that value's content. A variant has a second way to
    contribute -- its own board/socket map, if it actually DIFFERS from
    the default's (`variant_metadata_differs`); merely declaring one is
    not itself contribution. Returns zero, one or two error diagnostics
    (variant first, then revision -- the frozen order); never mutates its
    inputs."""
    diags: list[Diagnostic] = []
    if rig.variant is not None and not (
            rig.variants is not None and rig.variant == rig.variants.default):
        overlay, defconfig, delta = variant_contribution_names(
            rig.name, rig.variant)
        if not (present.variant_delta or present.variant_overlay
                or present.variant_defconfig or variant_metadata_differs(rig)):
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
        defconfig, delta = revision_contribution_names(rig.name, rig.revision)
        if not (present.revision_delta or present.revision_defconfig):
            diags.append(error(
                "lang-rev",
                f"rig '{rig.name}': revision '{rig.revision}' contributes "
                f"nothing -- looked for {defconfig} and {delta}, neither "
                "exists",
                (src,)))
    return diags
