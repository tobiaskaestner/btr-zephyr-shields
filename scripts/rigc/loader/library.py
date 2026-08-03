"""The shield library: scan, axes, lazy revision resolution
(rigc-r3-brief.md Sec 4). Ported from rigexp/loader_yml.py's
`ShieldLibrary` + `load_shield_library` + `_pick_shield` +
`_load_shield_revisions` -- this is what replaces R2's ShieldRef seam:
`resolve()` returns a REAL `Shield`, or diagnostics explaining why not.

**Discovery**: per folder, exactly `<dir>/<basename>.shield` -- never a
`*.shield` glob (`Kconfig.shield` ends in the literal substring and would
be mis-globbed; the presence check also self-filters a shields directory
to rig templates only, skipping legacy overlay-only shields).

**shield.yml** supplies ONLY the `revisions:` axis (never identity),
parsed by `loader.axes.parse_axis_decl` -- the SAME `{default:, list:}`
shape rig.yml's own axes use, reused rather than reimplemented (the two
lang-schema shield-side flips come from this reuse for free).

**Eager vs lazy**: discovery (the folder walk, the `<name>.shield`
presence probe, `shield.yml`'s axis read) is ALWAYS eager -- it is cheap,
has no subprocess, and is what builds the known-shields census
`lang-instance-shield` prints. Parsing a template -- base or revision --
never happens at scan time; every discovered shield is recorded as
`_Pending` and its template parses on `resolve()`'s first reference,
whether or not it declares a `revisions:` axis. Eagerly parsing every
discovered shield regardless of use would do needless cpp/dtlib work (a
rig referencing 2 of 14 discovered shields has no business preprocessing
the other 12) and leak an unreferenced template's path into dependency
data; eagerly combining every declared REVISION of a referenced shield
would repeat the same mistake one level down, so that stays deferred to
each revision's own first selection too.

A base parse that fails (its template defines no node matching the
folder name) is memoized in `ShieldLibrary.failed` so a second reference
reports nothing new -- the scan-time echo this replaces fired exactly
once by construction (one folder, one scan pass); a lazy re-parse per
reference would otherwise re-run cpp and re-report the same defect once
per referencing instance.

**Diagnostics and dependency data are RETURN values** (mission brief Sec
6, ratified ruling 3): `resolve()` never writes into an accumulator
handed in from outside. `ShieldLibrary.shields` IS mutated in place by
`resolve()` -- that is the lazy-parse MEMOIZATION cache the whole design
requires (exactly the shape rigexp's own `self.shields[key] = shield`
already is), a self-contained value the library keeps about itself, not a
side channel written into by many unrelated callers.
"""
from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..deps import Deps, touch, union
from ..diag import Diagnostic, LoadError, SourceRef, error
from ..dtsio import MODULE_ROOT, parse_tu, source_files
from ..model import AxisDecl, ConnectorType, Shield
from ..registry import load_types
from ..shields import parse_shields
from .axes import normalize_revision, parse_axis_decl
from .documents import parse_marked

log = logging.getLogger(__name__)

#: The vendored default shield library (direct API / test use only -- the
#: CLI always resolves --shield-dir roots and threads them down instead).
SHIELDS_DIR = os.path.join(MODULE_ROOT, "boards", "shields")


@dataclass(frozen=True)
class _Pending:
    """A discovered shield whose template has NOT been parsed yet --
    every discovered shield gets one of these, whether or not it
    declares a `revisions:` axis. `decl` is `None` for an axis-less
    shield (its base template is what `resolve()` parses on first bare
    reference) or the parsed `AxisDecl` for a revisioned one (each
    revision, including the declared default, parses on its own first
    selection)."""

    shield_dir: str
    base_file: str
    decl: Optional[AxisDecl]


@dataclass
class ShieldLibrary:
    """The discovered shield library. `axes` and `pending` name EVERY
    discovered shield -- `axes` is the known-shields census a
    lang-instance-shield diagnostic prints, `pending` is what each one
    needs to parse itself on first reference -- while `shields` holds
    only what has actually been PARSED so far, filled in by `resolve()`
    as references arrive rather than by the scan.

    `shields` is keyed for V1c revision resolution: by the CONSTRUCTED
    stems rule 13 resolves against -- "<name>" (a revision-less shield,
    or a revisioned one's DEFAULT) and "<name>@<rev>" (any declared
    revision, once resolved) -- never by the `.shield` DT node name
    alone, which is IDENTICAL across a shield's own revisions."""

    shields: Dict[str, Shield]
    axes: Dict[str, Optional[AxisDecl]]
    pending: Dict[str, _Pending]
    ymls: Dict[str, str]                 # name -> shield.yml, when present
    types: Dict[str, ConnectorType]
    workdir: str
    include_dirs: Optional[List[str]] = None
    #: Axis-less shields whose base parse has already failed once (a
    #: template that defines no node matching its folder name) -- checked
    #: before a second reference would re-run cpp and re-report the same
    #: defect. `_resolve_revision`'s own failures are deliberately NOT
    #: recorded here (see its docstring): this asymmetry is a decision,
    #: not an oversight.
    failed: Set[str] = field(default_factory=set)

    def resolve(self, ref: str, ctx: str, src: SourceRef,
               ) -> Tuple[Optional[Shield], List[Diagnostic], Deps]:
        """`<name>` or `<name>@<rev>` (rule 13's identical @rev grammar)
        -> the Shield, parsing a not-yet-parsed template on first use --
        the base template of an axis-less shield exactly like a
        revisioned shield's own selected revision. Mirrors
        `resolve_axis`'s three failure shapes (not declared at all / not
        a member / no default), reported as lang-rev -- the shield-side
        analogue of a qualified rig target's own axis resolution -- plus
        lang-instance-shield for a name this library never discovered at
        all. `ctx` names the caller (e.g. "instance 'sensor_0'") for that
        diagnostic's message.

        Returns (shield, diagnostics, deps); shield is None when
        resolution failed (the diagnostics say why) or when this
        shield's base parse already failed on an earlier reference (the
        failure was reported then, silently now). The library memoizes
        parsed shields (and axis-less parse failures) in place -- its own
        cache, not a shared accumulator; the caller owns diagnostics and
        deps."""
        name, sep, rev = ref.partition("@")
        if name not in self.axes:
            return None, [error(
                "lang-instance-shield",
                f"{ctx}: unknown shield '{name}'\n"
                f"known shields: {', '.join(sorted(self.axes))}",
                (src,))], frozenset()
        # This reference makes the shield's OWN shield.yml load-bearing
        # for this rig: recorded here (not at scan time) so a rig depends
        # only on the metadata of shields it actually names.
        deps: Deps = touch(self.ymls[name]) if name in self.ymls else frozenset()
        decl = self.axes[name]
        if sep:
            if decl is None:
                return None, [error(
                    "lang-rev",
                    f"shield '{name}' names a revision ({rev!r}), but "
                    "this shield declares no revisions: at all",
                    (src,))], deps
            if rev not in decl.values:
                return None, [error(
                    "lang-rev",
                    f"shield '{name}': revision '{rev}' is not declared "
                    f"-- known revisions: {', '.join(decl.values)}",
                    (src,))], deps
            shield, d, rdeps = self._resolve_revision(name, rev, decl, src)
            return shield, d, union(deps, rdeps)
        if name in self.shields:
            return self.shields[name], [], deps
        if decl is None:
            if name in self.failed:
                return None, [], deps
            pending = self.pending[name]
            shield, parse_diags, pdeps = _parse_shield_template(
                name, pending.base_file, [pending.base_file],
                f"shield-{name}.dts", self.workdir, self.include_dirs,
                self.types)
            deps = union(deps, touch(pending.base_file), pdeps)
            if shield is None:
                self.failed.add(name)
                return None, parse_diags, deps
            self.shields[name] = shield
            return shield, parse_diags, deps
        if decl.default is not None:
            shield, d, rdeps = self._resolve_revision(name, decl.default, decl, src)
            return shield, d, union(deps, rdeps)
        return None, [error(
            "lang-rev",
            f"shield '{name}': no revision selected, and this shield "
            "declares no default revision -- choose one of: "
            f"{', '.join(decl.values)}",
            (src,))], deps

    def _resolve_revision(self, name: str, rev: str, decl: AxisDecl,
                          src: SourceRef,
                          ) -> Tuple[Optional[Shield], List[Diagnostic], Deps]:
        """A single revision's own lazy parse -- deliberately UNMEMOIZED
        on failure (unlike the axis-less base parse `resolve()` handles
        directly): a bad revision is pre-existing behaviour that
        re-reports on every reference, no golden distinguishes it, and
        changing that is out of scope here."""
        key = f"{name}@{rev}"
        cached = self.shields.get(key)
        if cached is not None:
            return cached, [], frozenset()
        pending = self.pending[name]
        rev_norm = normalize_revision(rev)
        rev_file = os.path.join(pending.shield_dir, f"{name}_{rev_norm}.shield")
        rev_conf = os.path.join(pending.shield_dir, f"{name}_{rev_norm}.conf")
        has_rev_file = os.path.isfile(rev_file)
        is_default = rev == decl.default
        # Shield-side analogue of rule 10's default exemption: a
        # NON-DEFAULT revision that contributes NOTHING is an authoring
        # error; the default is exempt (the base template IS its
        # content).
        if not is_default and not (has_rev_file or os.path.isfile(rev_conf)):
            return None, [error(
                "lang-rev",
                f"shield '{name}': revision '{rev}' contributes nothing "
                f"-- looked for {name}_{rev_norm}.shield and "
                f"{name}_{rev_norm}.conf, neither exists",
                (src,))], frozenset()
        includes = [pending.base_file] + ([rev_file] if has_rev_file else [])
        # The base template is touched explicitly (not left to cpp
        # linemarker recovery alone): a revision fragment that defines no
        # node of its own still #includes the base, but a base that
        # defined no node EITHER would otherwise drop out of
        # dependency data entirely.
        deps: Deps = touch(pending.base_file)
        if has_rev_file:
            deps = union(deps, touch(rev_file))
        shield, diags, pdeps = _parse_shield_template(
            name, pending.base_file, includes,
            f"shield-{name}-{rev_norm}.dts", self.workdir, self.include_dirs,
            self.types)
        deps = union(deps, pdeps)
        if shield is None:
            return None, diags, deps
        shield.revisions = decl
        shield.revision = rev
        self.shields[key] = shield
        if is_default:
            self.shields[name] = shield
        return shield, diags, deps


def _parse_shield_template(name: str, template: str, includes: List[str],
                          dts_name: str, workdir: str,
                          include_dirs: Optional[List[str]],
                          types: Dict[str, ConnectorType],
                          ) -> Tuple[Optional[Shield], List[Diagnostic], Deps]:
    """Build one shield translation unit (`parse_tu`) and pick its node
    (`_pick_shield`) -- the parse body `resolve()`'s axis-less path and
    `_resolve_revision` both need, factored so neither hand-duplicates
    the cpp/dtlib wiring. May raise LoadError (a real cpp/dtlib failure);
    callers decide whether that failure gets memoized.

    Returns (shield, diagnostics, deps); shield is None only when the
    template parsed but defined no node named `name` (`_pick_shield`'s
    own diagnostic is included). `deps` are the real source files THIS
    parse touched, recovered from cpp linemarkers (`source_files`) --
    never `includes` themselves, since only the caller knows whether
    those are a base template or a revision fragment and which of the
    two dependency rules (Sec 2.3) applies."""
    log.debug("shield library: parsing %s (%s)", name, os.path.basename(template))
    dt = parse_tu(includes, workdir, dts_name, include_dirs)
    deps = frozenset(source_files(dt, workdir))
    parsed, diags = parse_shields(dt, types)
    shield, pd = _pick_shield(parsed, name, template)
    return shield, diags + pd, deps


def _pick_shield(parsed: Dict[str, Shield], name: str, template: str,
                 ) -> Tuple[Optional[Shield], List[Diagnostic]]:
    """The shield a template's translation unit defines, looked up by the
    FOLDER name rather than whatever node name parse_shields returned
    (byte-identical to the blueprint, rigc-r2-brief.md's recorded
    decision: rigexp/loader_yml.py:1426-1440's sibling check for the
    resolution key)."""
    shield = parsed.get(name)
    if shield is not None:
        return shield, []
    defined = ", ".join(sorted(parsed)) or "none"
    return None, [error(
        "lang-shield-name",
        f"shield template {os.path.basename(template)} defines no shield "
        f"node named '{name}' -- a .shield node name must match the "
        "folder it lives in, because that folder name is what an "
        "instance's shield: reference and shield discovery both "
        f"construct\nnodes defined here: {defined}",
        (SourceRef(template, 1),))]


def _load_shield_revisions(shield_dir: str,
                           ) -> Tuple[Optional[AxisDecl], List[Diagnostic]]:
    """shield.yml's `revisions:` declaration (V1c): the SAME axis shape
    as rig.yml's own, so `loader.axes.parse_axis_decl` is reused as-is.
    shield.yml stays OPTIONAL -- a folder with none (or one with no
    revisions: key) declares no axis."""
    path = os.path.join(shield_dir, "shield.yml")
    if not os.path.isfile(path):
        return None, []
    doc = parse_marked(path)          # Unimplemented on a YAML parse
                                       # failure -- no frozen golden (R2's
                                       # own choice, unchanged here)
    shield_v = doc.value.get("shield")
    if shield_v is None:
        return None, []
    return parse_axis_decl(shield_v, "revisions",
                           owner=f"shield '{os.path.basename(shield_dir)}'")


def load_shield_library(workdir: str, shield_dirs: Optional[List[str]] = None,
                        types: Optional[Dict[str, ConnectorType]] = None,
                        include_dirs: Optional[List[str]] = None,
                        ) -> Tuple[ShieldLibrary, List[Diagnostic], Deps]:
    """Load every shield template. Each `.shield` file (base + any
    resolved revision fragment) is its OWN translation unit (Ground rule
    3) -- labels are shield-scoped, no cross-shield prefix discipline
    needed.

    `shield_dirs` is a LIST of shield-library roots, unioned into one
    library; None falls back to the vendored default (direct API / test
    use only). `types` is the connector-type registry every shield's plug
    is checked against; None falls back to `registry.load_types()`.

    Returns (library, diagnostics, deps): the library, with every
    discovered shield recorded as pending -- NOTHING parsed yet,
    regardless of whether it declares a `revisions:` axis; every
    scan-time finding in discovery order (shield.yml's own `revisions:`
    schema, the only diagnostic the scan itself can produce now); and
    every file the scan actually READ (shield.yml when present, the
    connector-type registry) -- a discovered `.shield` template is not
    itself a dependency until something references it (Sec 2.3). The
    caller owns all three."""
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    if types is None:
        types, tdeps = load_types()
        deps = union(deps, tdeps)
    shields: Dict[str, Shield] = {}
    axes: Dict[str, Optional[AxisDecl]] = {}
    pending: Dict[str, _Pending] = {}
    ymls: Dict[str, str] = {}
    directories = shield_dirs if shield_dirs is not None else [SHIELDS_DIR]
    # A malformed member hard-errors the whole scan (blueprint wart,
    # reproduce-first) -- but the members already scanned may have
    # reported findings of their own, and rigexp renders those TOO (its
    # shared accumulator survives the raise by ownership). Re-raise with
    # this scan's priors prepended so the boundary that catches renders
    # the same bytes (R3 review finding D1).
    try:
        for directory in directories:
            for shield_dir in sorted(glob.glob(os.path.join(directory, "*"))):
                if not os.path.isdir(shield_dir):
                    continue
                name = os.path.basename(shield_dir)
                base_file = os.path.join(shield_dir, name + ".shield")
                if not os.path.isfile(base_file):
                    continue
                # The template itself is NOT touched here (Sec 2.3): a
                # rig depends on a discovered shield's translation unit
                # only once something actually references it, recorded
                # by resolve()/_resolve_revision at that point instead.
                shield_yml = os.path.join(shield_dir, "shield.yml")
                if os.path.isfile(shield_yml):
                    ymls[name] = shield_yml
                decl, d = _load_shield_revisions(shield_dir)
                diags += d
                axes[name] = decl
                pending[name] = _Pending(shield_dir, base_file, decl)
    except LoadError as e:
        raise LoadError(*diags, *e.diags) from None
    log.info("shield library: %d shields discovered", len(pending))
    lib = ShieldLibrary(shields=shields, axes=axes, pending=pending,
                       ymls=ymls, types=types, workdir=workdir,
                       include_dirs=include_dirs)
    return lib, diags, deps
