"""The loader proper: rig.yml metadata (qualifier axes, board/socket
resolution), the shield library, the required content file, fragment
discovery, and the V1b delta engine with params/pins/dt-includes fully
wired -- assembled here from the loader's own submodules:

  documents.py  -- mark-aware YAML, content-filename construction, the
                   metadata/content key split
  axes.py       -- revisions:/variants: declaration + resolution (the
                   hwmv2 seam) -- reused unchanged for shield.yml's own
                   revisions: axis (V1c)
  binding.py    -- board/SocketBinding resolution (the S2 seam)
  fragments.py  -- rule 10, the fragment-presence check
  library.py    -- the shield library: scan, axes, lazy revision
                   resolution (rigc-r3-brief.md Sec 4)
  params.py     -- params/pin/dt-includes machinery (Sec 5)
  delta.py      -- base topology + the V1b delta engine, now resolving
                   `shield:` against the REAL library (R2's ShieldRef
                   seam, closed)

**Ordering** (rigc-r3-brief.md Sec 4): the shield library is scanned
BEFORE rig.yml even opens, mirroring the blueprint's own `load():1186` --
`shield-node-name-mismatch` and every other scan-time diagnostic
therefore precedes every rig-side one.

`load()` returns (Rig | None, diagnostics) rather than raising on a
reject: a load that finds nothing wrong falls through to cli.py's own
Unimplemented("expand: the accept path...") -- never a silent 0.

**Three phases (rigc-r45-brief.md Part A)**: `load()` itself is now just
the library scan, three phase calls, and the final Rig assembly --
`_resolve_metadata` (rig.yml's shell: name, qualifier axes, board +
SocketBinding -- entirely cpp-free), `_gather_content` (the required
content file, the two delta fragments, rule 10, the dt-includes union +
probe), `_build_topology` (stage 0 plus the two delta stages, the
per-stage invariant). Each phase returns its OWN small value -- never a
shared mutable "context" written into across phases (rigc-mission-brief.md
Sec 6; a bespoke accumulator by another name is still the banned shape).
`load()` concatenates each phase's diagnostics onto its own running list,
in the phases' own call order -- reproducing today's traversal order
byte for byte, since that order is the frozen stderr contract. The D1
LoadError boundary (R3 review: rigexp's shared accumulator survives a
raise by ownership; a return-value shape needs the exception itself to
carry every prior finding, or a raise silently drops them) stays at the
TOP of `load()`, wrapping the library scan and all three phases --
`_build_topology` carries its OWN inner instance of the same guard,
because a shield revision resolved LAZILY, mid-topology (`ShieldLibrary.
resolve`), can still raise LoadError from inside that one phase call,
same as the library scan already does in library.py."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..deps import Deps, touch, union
from ..diag import Diagnostic, LoadError, SourceRef, anchor_path, error
from ..model import ConnectorType, Rig
from ..unimplemented import Unimplemented
from . import axes, binding, fragments
from .axes import revision_fragment_name, variant_fragment_name
from .binding import SocketBinding
from .delta import (Topology, apply_delta, parse_instance, parse_wire,
                   union_dt_includes)
from .documents import (Val, as_mapping, content_file_name,
                        parse_marked, reject_metadata_keys, require)
from .library import ShieldLibrary, load_shield_library
from .params import check_dt_includes, check_param_invariant

__all__ = ["load"]

log = logging.getLogger(__name__)


def _missing_content_diag(rig_name: str, path: str, src: SourceRef) -> Diagnostic:
    # anchor_path so the expected location renders the same way every other
    # path in a diagnostic does. A real rig lives outside scripts/<module>/,
    # so its path stays absolute here -- which is what an author needs in
    # order to create the file.
    return error(
        "lang-content",
        f"rig '{rig_name}': no content file found -- expected {anchor_path(path)}",
        (src,))


# ---------------------------------------------------------------- phase 1


@dataclass(frozen=True)
class MetadataResult:
    """Phase 1's own value: rig.yml's shell -- name, qualifier axes
    resolved, and the SocketBinding this rig's topology resolves socket:
    references through. `rig` is None only when rig.yml is malformed
    enough that nothing further can be attempted (no `rig:` block, or no
    `name:` inside it); every OTHER defect found here (an axis collision,
    an unresolved axis, a bad board:) still produces a Rig plus
    diagnostics naming what is wrong -- exactly as before the split."""

    rig: Optional[Rig]
    binding: SocketBinding = field(default_factory=SocketBinding)


def _resolve_metadata(doc: Val, revision: Optional[str], variant: Optional[str],
                      board: Optional[str] = None,
                      ) -> Tuple[MetadataResult, List[Diagnostic]]:
    """Steps 2-5 of the blueprint's load(): the rig shell, its qualifier
    axes (declaration, collision, resolution), and the board +
    SocketBinding its topology resolves socket: references through.
    Entirely cpp-free -- reads `doc`'s own parsed YAML tree alone, so a
    synthetic Val tree exercises every branch here with no shield
    library, no ZEPHYR_BASE, no file on disk (this is the side benefit
    the brief calls out: the future hwmv2 revision-semantics seam lands
    entirely inside this one function).

    `board`, when given, is the invocation's injected board
    (board-coordinate-s1-brief.md Sec 4): it wins over whatever this rig
    declares, unconditionally -- see binding.resolve_board."""
    diags: List[Diagnostic] = []
    rig_v, d = require(doc, "rig", "top level")
    diags += d
    if rig_v is None:
        return MetadataResult(rig=None), diags
    name_v, d = require(rig_v, "name", "rig")
    diags += d
    if name_v is None:
        return MetadataResult(rig=None), diags

    rig = Rig(name=name_v.value, src=rig_v.src)
    rig_map = as_mapping(rig_v, "rig: block")

    revisions, d = axes.parse_revision_decl(rig_v, "revision", owner="rig")
    diags += d
    variants, d = axes.parse_variant_decl(rig_v, "variants", owner="rig")
    diags += d
    rig.revisions, rig.variants = revisions, variants
    diags += axes.check_axis_collision(rig.name, variants, revisions, rig_v.src)

    rig.revision_requested = revision
    rig.revision, d = axes.resolve_axis(rig.name, "revision", "revision",
                                        revisions, revision, rig_v.src)
    diags += d
    rig.variant, d = axes.resolve_axis(rig.name, "variant", "variants",
                                       variants, variant, rig_v.src)
    diags += d
    log.debug("rig '%s': selected revision=%r variant=%r",
             rig.name, rig.revision, rig.variant)
    if (rig.revision is not None and rig.revision_requested is not None
            and rig.revision != rig.revision_requested):
        log.info("rig '%s': revision requested %r resolved to %r",
                 rig.name, rig.revision_requested, rig.revision)

    board_v = rig_map.get("board")
    sockets_v = rig_map.get("sockets")
    rig.board, sock_binding, d = binding.resolve_board(
        rig.name, variants, rig.variant, board_v, sockets_v, rig_v.src,
        injected_board=board)
    diags += d
    log.debug("rig '%s': board=%r socket binding=%r", rig.name, rig.board, sock_binding)

    return MetadataResult(rig=rig, binding=sock_binding), diags


# ---------------------------------------------------------------- phase 2


@dataclass(frozen=True)
class Deltas:
    """The rig's two (parsed, not yet APPLIED) qualifier delta fragments
    -- V1b's fixed variant-then-revision stage order, carried to phase 3
    as a value rather than two loose fields on `ContentResult`, since
    phase 3 applies them as a PAIR in that one fixed order."""

    variant_v: Optional[Val] = None
    revision_v: Optional[Val] = None


@dataclass(frozen=True)
class ContentResult:
    """Phase 2's own value: the rig's required content document, its two
    delta fragments (unapplied), and the dt-includes list already unioned
    across base + both fragments and probed (`check_dt_includes`) once,
    before any stage's own params resolve against it."""

    content_v: Val
    deltas: Deltas
    dt_includes: List[str] = field(default_factory=list)
    dt_includes_refs: List[SourceRef] = field(default_factory=list)


def _gather_content(rig: Rig, rig_dir: str, workdir: str,
                    include_dirs: Optional[List[str]],
                    ) -> Tuple[Optional[ContentResult], List[Diagnostic], Deps]:
    """Steps 6-9: the rig's REQUIRED content file, its two qualifier delta
    fragments (looked up by the constructed stems `loader.axes` builds,
    never `${RIG}` literally), rule 10 (a selected non-default axis value
    that contributes nothing), and the dt-includes union across base +
    both fragments. Returns None only when the content file itself is
    missing -- every other finding here still returns a value, matching
    phase 1's own only-truly-fatal-stops-here shape.

    Never raises LoadError itself: the one cpp-reaching call here
    (`check_dt_includes`) catches it internally per header
    (`dtsio.check_include`), so this phase needs no D1-style inner
    boundary of its own (unlike phase 3, see `_build_topology`).

    Returns (result, diagnostics, deps): deps names the content file
    itself, whichever of the two qualifier delta fragments actually
    exist, and every real file each declared dt-includes: header's own
    preprocess opened (`check_dt_includes`, recorded whether or not that
    header's own check passed) -- the closure this phase owns of
    rigc-r5-brief.md Sec 2's RIG_DEPENDS handoff (the fragments' own
    #include chains are not opened here at all, since a delta fragment is
    parsed the same mark-aware-YAML way the base content is, never
    cpp)."""
    assert rig.src is not None   # phase 1 always sets it before returning a Rig
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    content_path = os.path.join(rig_dir, content_file_name(rig.name))
    if not os.path.isfile(content_path):
        diags.append(_missing_content_diag(rig.name, content_path, rig.src))
        return None, diags, deps
    deps = union(deps, touch(content_path))
    content_v = parse_marked(content_path)
    diags += reject_metadata_keys(content_v)

    variant_delta_v: Optional[Val] = None
    if rig.variant is not None:
        p = os.path.join(rig_dir, variant_fragment_name(rig.name, rig.variant))
        if os.path.isfile(p):
            deps = union(deps, touch(p))
            variant_delta_v = parse_marked(p)

    revision_delta_v: Optional[Val] = None
    if rig.revision is not None:
        p = os.path.join(rig_dir, revision_fragment_name(rig.name, rig.revision))
        if os.path.isfile(p):
            deps = union(deps, touch(p))
            revision_delta_v = parse_marked(p)

    if rig.revision is not None or rig.variant is not None:
        # Rule 10 is a PURE decision (fragments.py); this IO phase probes
        # which contribution artifacts exist and hands the facts in as a
        # value. Names come from fragments' own constructors -- the one
        # source both the probes and the message text share.
        variant_overlay = variant_defconfig = revision_defconfig = False
        if rig.variant is not None:
            overlay, defconfig, _ = fragments.variant_contribution_names(
                rig.name, rig.variant)
            variant_overlay = os.path.isfile(os.path.join(rig_dir, overlay))
            variant_defconfig = os.path.isfile(os.path.join(rig_dir, defconfig))
        if rig.revision is not None:
            defconfig, _ = fragments.revision_contribution_names(
                rig.name, rig.revision)
            revision_defconfig = os.path.isfile(os.path.join(rig_dir, defconfig))
        diags += fragments.check_fragment_presence(
            rig, rig.src, fragments.FragmentPresence(
                variant_delta=variant_delta_v is not None,
                variant_overlay=variant_overlay,
                variant_defconfig=variant_defconfig,
                revision_delta=revision_delta_v is not None,
                revision_defconfig=revision_defconfig))

    content_map = as_mapping(content_v, f"content document {content_path}")
    dt_includes, dt_includes_refs = union_dt_includes(
        [], [], content_map.get("dt-includes"))
    if variant_delta_v is not None:
        dt_includes, dt_includes_refs = union_dt_includes(
            dt_includes, dt_includes_refs,
            as_mapping(variant_delta_v, "variant delta").get("dt-includes"))
    if revision_delta_v is not None:
        dt_includes, dt_includes_refs = union_dt_includes(
            dt_includes, dt_includes_refs,
            as_mapping(revision_delta_v, "revision delta").get("dt-includes"))
    if dt_includes:
        d, dt_deps = check_dt_includes(rig.name, dt_includes, dt_includes_refs,
                                       workdir, include_dirs)
        diags += d
        deps = union(deps, dt_deps)

    return ContentResult(
        content_v=content_v,
        deltas=Deltas(variant_v=variant_delta_v, revision_v=revision_delta_v),
        dt_includes=dt_includes, dt_includes_refs=dt_includes_refs), diags, deps


# ---------------------------------------------------------------- phase 3


def _build_topology(rig: Rig, sock_binding: SocketBinding, lib: ShieldLibrary,
                    content: ContentResult, workdir: str,
                    include_dirs: Optional[List[str]],
                    ) -> Tuple[Topology, List[Diagnostic], Deps]:
    """Steps 10-11: stage 0 (the base content's instances:/wires:, order
    preserved, the per-stage invariant checked per instance as it is
    parsed), then the variant delta stage, then the revision delta stage
    -- each re-checking the invariant over the whole topology afterward.

    A shield revision resolved LAZILY here (`ShieldLibrary.resolve`,
    reached through `parse_instance`/`apply_delta`) can raise LoadError
    mid-loop -- this phase's OWN try/except carries this call's
    diagnostics-so-far into the exception (the same D1 shape
    `load_shield_library` already applies to its own scan loop), so the
    outer boundary in `load()` renders every finding gathered before the
    raise, never just the fatal one.

    Returns (topology, diagnostics, deps): deps is the UNION of every
    shield resolution this phase made -- stage 0's own `parse_instance`
    calls AND both delta stages' `apply_delta` -- never derived from the
    final topology alone (rigc-r5-brief.md Sec 2, fact 2): a variant
    stage that SUBSTITUTES one instance's shield for another still
    leaves the base stage's own resolution (of the shield the variant
    replaced) in this union, because that resolution genuinely happened
    -- RIG_DEPENDS records resolution HISTORY, not final topology."""
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    try:
        content_map = as_mapping(
            content.content_v, f"content document {content.content_v.src.file}")

        topology = Topology()
        insts_v, d = require(content.content_v, "instances", "rig")
        diags += d
        for item in (insts_v.value if insts_v is not None else []):
            inst, d, idep = parse_instance(item, sock_binding, lib, rig.name,
                                           content.dt_includes, workdir, include_dirs)
            diags += d
            deps = union(deps, idep)
            if inst is not None:
                topology.effective[inst.name] = inst
                topology.order.append(inst.name)
                diags += check_param_invariant([inst])

        wires_v = content_map.get("wires")
        for item in (wires_v.value if wires_v is not None else []):
            wire, d = parse_wire(item, topology.effective)
            diags += d
            if wire is not None:
                topology.wires.append(wire)

        # Stage 1: variant delta.
        if content.deltas.variant_v is not None:
            assert rig.variant is not None    # a delta only loads for a selected axis
            topology, d, idep = apply_delta(
                content.deltas.variant_v, "variant", rig.variant, topology,
                sock_binding, lib, rig.variant, rig.name, content.dt_includes,
                workdir, include_dirs)
            diags += d
            deps = union(deps, idep)
            diags += check_param_invariant(topology.instances())

        # Stage 2: revision delta -- ONE family-wide stream, applied AFTER
        # the variant.
        if content.deltas.revision_v is not None:
            assert rig.revision is not None   # a delta only loads for a selected axis
            topology, d, idep = apply_delta(
                content.deltas.revision_v, "revision", rig.revision, topology,
                sock_binding, lib, rig.variant, rig.name, content.dt_includes,
                workdir, include_dirs)
            diags += d
            deps = union(deps, idep)
            diags += check_param_invariant(topology.instances())

        return topology, diags, deps
    except LoadError as e:
        raise LoadError(*diags, *e.diags) from None


# ---------------------------------------------------------------- load()


def load(rig_path: str, workdir: str,
        shield_dirs: Optional[List[str]] = None,
        revision: Optional[str] = None,
        variant: Optional[str] = None,
        board: Optional[str] = None,
        types: Optional[Dict[str, ConnectorType]] = None,
        include_dirs: Optional[List[str]] = None,
        ) -> Tuple[Optional[Rig], List[Diagnostic], Deps]:
    """Load rig_path (absolute) as far as rigc's loader reaches, returning
    the built Rig (best-effort; None only when nothing further could be
    attempted at all) alongside every diagnostic found. rigexp CONTINUES
    after most errors -- this reproduces that shape rather than stopping
    at the first diagnostic, so a later one is never dropped.

    `workdir` is where every `.shield` translation unit and dt-includes
    probe gets synthesized (cli.py's responsibility to create/clean up).

    `board`, when given, is the invocation's injected board (the cmake
    seam always supplies one; the standalone CLI passes None to keep
    today's rig.yml-derived behaviour) -- threaded straight to
    `_resolve_metadata`/`binding.resolve_board`, which is the only place
    it changes anything.

    Returns (rig, diagnostics, deps): deps is the UNION of every real
    source-tree file this load touched -- rig_path itself, the shield
    library scan (library.py's own eager-breadth deps, unchanged whether
    a rig ends up naming the shield or not: rigc-r5-brief.md Sec 2, fact
    1), the content file plus whichever qualifier delta fragments exist
    (`_gather_content`), and every shield resolution the topology stages
    made (`_build_topology`, unioned rather than derived from the final
    instance list -- fact 2). This is the RIG_DEPENDS handoff's own
    value; cli.py composes it with the connector-registry and board
    deps and hands the result to `context.render`. The caller owns the
    Rig and the Deps alike."""
    # LoadError (a fatal parse/cpp failure, dtsio.py) can surface from
    # the library scan below or a lazy shield resolve mid-topology.
    # rigexp's shared accumulator survives that raise by OWNERSHIP; with
    # diagnostics as return values, THIS boundary catches instead and
    # returns everything gathered so far plus what the exception carries
    # -- one shape, no finding lost (R3 review, D1).
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    try:
        lib, diags, lib_deps = load_shield_library(
            workdir, shield_dirs, types=types, include_dirs=include_dirs)
        deps = union(deps, lib_deps)

        deps = union(deps, touch(rig_path))
        doc = parse_marked(rig_path)

        log.info("load(): resolving metadata")
        meta, d = _resolve_metadata(doc, revision, variant, board)
        diags += d
        if meta.rig is None:
            return None, diags, deps
        rig, sock_binding = meta.rig, meta.binding

        log.info("load(): gathering content")
        rig_dir = os.path.dirname(rig_path)
        content, d, cdeps = _gather_content(rig, rig_dir, workdir, include_dirs)
        diags += d
        deps = union(deps, cdeps)
        if content is None:
            return None, diags, deps

        log.info("load(): building topology")
        topology, d, tdeps = _build_topology(
            rig, sock_binding, lib, content, workdir, include_dirs)
        diags += d
        deps = union(deps, tdeps)

        rig.dt_includes = content.dt_includes
        rig.dt_includes_refs = content.dt_includes_refs
        rig.instances = topology.instances()
        rig.wires = topology.wires
        for inst in rig.instances:
            socket_desc = inst.socket if inst.socket is not None else "(inferred)"
            log.info("rig '%s': instance '%s' requires shield '%s', "
                     "mated to socket '%s'",
                     rig.name, inst.name, inst.shield.name, socket_desc)
        return rig, diags, deps
    except LoadError as e:
        return None, diags + list(e.diags), deps
