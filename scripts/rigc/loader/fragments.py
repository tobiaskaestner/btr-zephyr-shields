"""Rule 10: a selected NON-DEFAULT axis value that contributes NOTHING --
the constructed-fragment-file contribution check. Ported value-shaped
from rigexp/loader_yml.py's `_check_fragment_presence` (rigc-r2-brief.md
Sec 5); its sibling `_variant_metadata_differs` -- the VARIANT-only
second avenue of contribution a per-variant board/socket map differing
from the default's used to open -- retired with that grammar
(board-coordinate-s6-brief.md Sec 11): `AxisDecl.boards`/`.sockets` are
never populated any more, so a variant's only way to contribute is the
same fragment-file avenue a revision has.

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


def check_fragment_presence(rig: Rig, src: SourceRef,
                            present: FragmentPresence,
                            ) -> list[Diagnostic]:
    """A selected NON-DEFAULT axis value naming the fragment files it
    was expected to contribute via (naming what was looked for) when
    NONE of them exist. The declared DEFAULT of an axis is exempt: the
    base rig file IS that value's content. Returns zero, one or two
    error diagnostics (variant first, then revision -- the frozen
    order); never mutates its inputs."""
    diags: list[Diagnostic] = []
    if rig.variant is not None and not (
            rig.variants is not None and rig.variant == rig.variants.default):
        overlay, defconfig, delta = variant_contribution_names(
            rig.name, rig.variant)
        if not (present.variant_delta or present.variant_overlay
                or present.variant_defconfig):
            diags.append(error(
                "lang-variant",
                f"rig '{rig.name}': variant '{rig.variant}' contributes "
                f"nothing -- looked for {overlay}, {defconfig} and {delta}, "
                f"none exist",
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
