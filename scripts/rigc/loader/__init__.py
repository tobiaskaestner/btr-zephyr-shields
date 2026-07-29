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
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from ..diag import Diagnostic, LoadError, SourceRef, error
from ..model import Rig
from ..unimplemented import Unimplemented
from . import axes, binding, fragments
from .axes import revision_fragment_name, variant_fragment_name
from .delta import (Topology, apply_delta, parse_instance, parse_wire,
                   union_dt_includes)
from .documents import (Val, as_mapping, content_file_name,
                        parse_marked, reject_metadata_keys, require)
from .library import load_shield_library
from .params import check_dt_includes, check_param_invariant

__all__ = ["load"]


def _missing_content_diag(rig_name: str, path: str, src: SourceRef) -> Diagnostic:
    return error(
        "lang-content",
        f"rig '{rig_name}': no content file found -- expected {path}",
        (src,))


def load(rig_path: str, workdir: str,
        shield_dirs: Optional[List[str]] = None,
        revision: Optional[str] = None,
        variant: Optional[str] = None,
        types: Optional[dict] = None,
        include_dirs: Optional[List[str]] = None,
        ) -> Tuple[Optional[Rig], List[Diagnostic]]:
    """Load rig_path (absolute) as far as rigc's loader reaches, returning
    the built Rig (best-effort; None only when nothing further could be
    attempted at all) alongside every diagnostic found. rigexp CONTINUES
    after most errors -- this reproduces that shape rather than stopping
    at the first diagnostic, so a later one is never dropped.

    `workdir` is where every `.shield` translation unit and dt-includes
    probe gets synthesized (cli.py's responsibility to create/clean up).
    Dependency data (every real file this load touched) is computed
    internally as a value but not yet returned -- nothing asserts it until
    the emitter slice wires RIG_DEPENDS (rigc-r3-brief.md Sec 4); the
    shape lives in library.py/registry.py's own return values already."""
    # LoadError (a fatal parse/cpp failure, dtsio.py) can surface from
    # the library scan below or a lazy shield resolve mid-topology.
    # rigexp's shared accumulator survives that raise by OWNERSHIP;
    # with diagnostics as return values, THIS boundary catches instead
    # and returns everything gathered so far plus what the exception
    # carries -- one shape, no finding lost (R3 review, D1).
    diags: List[Diagnostic] = []
    try:
        lib, diags, _deps = load_shield_library(
            workdir, shield_dirs, types=types, include_dirs=include_dirs)

        doc = parse_marked(rig_path)
        rig_v, d = require(doc, "rig", "top level")
        diags += d
        if rig_v is None:
            return None, diags
        name_v, d = require(rig_v, "name", "rig")
        diags += d
        if name_v is None:
            return None, diags

        rig = Rig(name=name_v.value, src=rig_v.src)
        rig_dir = os.path.dirname(rig_path)
        rig_map = as_mapping(rig_v, "rig: block")

        # Qualifier axes: declare (shape-validated), then resolve the
        # SELECTED value for each.
        revisions, d = axes.parse_axis_decl(rig_v, "revisions", owner="rig")
        diags += d
        variants, d = axes.parse_axis_decl(rig_v, "variants", owner="rig",
                                           allow_variant_metadata=True)
        diags += d
        rig.revisions, rig.variants = revisions, variants
        diags += axes.check_axis_collision(rig.name, variants, revisions, rig_v.src)

        rig.revision, d = axes.resolve_axis(rig.name, "revision", "revisions",
                                            revisions, revision, rig_v.src)
        diags += d
        rig.variant, d = axes.resolve_axis(rig.name, "variant", "variants",
                                           variants, variant, rig_v.src)
        diags += d

        # The board this rig builds, and the SocketBinding its topology
        # resolves socket: references through -- from rig.yml metadata
        # alone, before any content file is opened.
        board_v = rig_map.get("board")
        sockets_v = rig_map.get("sockets")
        rig.board, sock_binding, d = binding.resolve_board(
            rig.name, variants, rig.variant, board_v, sockets_v, rig_v.src)
        diags += d

        # The rig's REQUIRED content file (the metadata/content split):
        # instances:/wires:/dt-includes: live here, never in rig.yml.
        content_path = os.path.join(rig_dir, content_file_name(rig.name))
        if not os.path.isfile(content_path):
            diags.append(_missing_content_diag(rig.name, content_path, rig_v.src))
            return None, diags
        content_v = parse_marked(content_path)
        diags += reject_metadata_keys(content_v)

        # V1b delta fragments: looked up by the SAME constructed stems rule
        # 10 checks, built from rig.revision/rig.variant alone -- never
        # ${RIG}. Loaded (not yet APPLIED) here, before rule 10 and before
        # the dt-includes union.
        variant_delta_v: Optional[Val] = None
        if rig.variant is not None:
            p = os.path.join(rig_dir, variant_fragment_name(rig.name, rig.variant))
            if os.path.isfile(p):
                variant_delta_v = parse_marked(p)

        revision_delta_v: Optional[Val] = None
        if rig.revision is not None:
            p = os.path.join(rig_dir, revision_fragment_name(rig.name, rig.revision))
            if os.path.isfile(p):
                revision_delta_v = parse_marked(p)

        if rig.revision is not None or rig.variant is not None:
            diags += fragments.check_fragment_presence(
                rig, rig_dir, rig_v.src,
                has_variant_delta=variant_delta_v is not None,
                has_revision_delta=revision_delta_v is not None)

        # dt-includes: UNION base + variant delta + revision delta, all
        # BEFORE any params get token-validated below.
        content_map = as_mapping(content_v, f"content document {content_path}")
        rig.dt_includes, rig.dt_includes_refs = union_dt_includes(
            rig.dt_includes, rig.dt_includes_refs, content_map.get("dt-includes"))
        if variant_delta_v is not None:
            rig.dt_includes, rig.dt_includes_refs = union_dt_includes(
                rig.dt_includes, rig.dt_includes_refs,
                as_mapping(variant_delta_v, "variant delta").get("dt-includes"))
        if revision_delta_v is not None:
            rig.dt_includes, rig.dt_includes_refs = union_dt_includes(
                rig.dt_includes, rig.dt_includes_refs,
                as_mapping(revision_delta_v, "revision delta").get("dt-includes"))
        if rig.dt_includes:
            diags += check_dt_includes(rig.name, rig.dt_includes,
                                       rig.dt_includes_refs, workdir, include_dirs)

        # Stage 0: base topology, read from the content file, preserving
        # ORDER. An empty instances: list stays legal and distinct from a
        # missing content file. The per-stage invariant (rule 2) is checked
        # PER INSTANCE, immediately after each is parsed.
        topology = Topology()
        insts_v, d = require(content_v, "instances", "rig")
        diags += d
        for item in (insts_v.value if insts_v is not None else []):
            inst, d, _idep = parse_instance(item, sock_binding, lib, rig.name,
                                            rig.dt_includes, workdir, include_dirs)
            diags += d
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
        if variant_delta_v is not None:
            assert rig.variant is not None    # a delta only loads for a selected axis
            topology, d, _idep = apply_delta(
                variant_delta_v, "variant", rig.variant, topology, sock_binding,
                lib, rig.variant, rig.name, rig.dt_includes, workdir, include_dirs)
            diags += d
            diags += check_param_invariant(topology.instances())

        # Stage 2: revision delta -- ONE family-wide stream, applied AFTER
        # the variant.
        if revision_delta_v is not None:
            assert rig.revision is not None   # a delta only loads for a selected axis
            topology, d, _idep = apply_delta(
                revision_delta_v, "revision", rig.revision, topology, sock_binding,
                lib, rig.variant, rig.name, rig.dt_includes, workdir, include_dirs)
            diags += d
            diags += check_param_invariant(topology.instances())

        rig.instances = topology.instances()
        rig.wires = topology.wires
        return rig, diags
    except LoadError as e:
        return None, diags + list(e.diags)
