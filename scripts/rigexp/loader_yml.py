"""Candidate-2 loader: rig.yml + <rigname>.yml (YAML/DTS hybrid) -> rig model.

Two files, two roles, mirroring board.yml+<board>.dts and
shield.yml+<name>.shield: rig.yml is METADATA, named after the entity TYPE
and carrying no hardware description at all -- name:, board:, revisions:,
variants:, all nested under a rig: key. <rigname>.yml is CONTENT, named
after the entity INSTANCE (constructed from rig.yml's own name:, never
parsed from the folder) and holds everything that describes an assembled
topology -- instances:, wires:, dt-includes: -- as a FLAT top-level
mapping, structurally identical to the <rigname>_<variant>.yml /
<rigname>_<rev>.yml delta fragments that already layer onto it (both are
"a document about topology"; only one of them is the base). The content
file is REQUIRED: a rig whose metadata resolves but has no content file is
an authoring mistake, not a rig with zero instances (an empty instances:
list is legal and distinct).

Everything candidate-1 gets from dtlib must be built here by hand: the
dotted-reference resolution rules and their error reporting are THE open
comparison (EVALUATION.md). Rules implemented (defining them is part of the
trial):

  instances[].shield    shield node name, resolved against the shield library
  instances[].socket    cross-tree string, passed through (analyzer checks it)
  instances[].pin       {strap-name: value} — strap resolved WITHIN the
                        instance's shield (config straps only)
  instances[].params    {device-label: {property: value}} — per-instance
                        property assignment, resolved WITHIN the instance's
                        shield the same way pin is (device label, not node
                        name); the property must be one the device declared
                        via shield,params (rig-variants-revisions.md
                        "PER-INSTANCE PARAMETERS")
  dt-includes           list of headers (as written in a DTS #include
                        <...>) the rig's assigned param tokens resolve
                        against
  wires[].from/to       <instance>.<node> — instance by name; node resolved
                        within that instance's shield over pads ∪ devices ∪
                        straps; must be unique there
  wires[].route         "adhoc" | {via: <position name>} (name from the
                        dt-bindings header, e.g. D2)
  rig.revisions/        {default:, list: []} qualifier axis declarations
  rig.variants          (rig-variants-revisions.md V1a); load()'s
                        revision:/variant: params select against them,
                        applying the declared default for a bare target.
                        A variants: list entry is either a bare name or a
                        mapping {name:, board:, sockets:} -- board:/
                        sockets: are METADATA, resolved before any content
                        file is read; a rig instead declares them once at
                        top level (rig: board:/sockets:) in the degenerate
                        single-board shape. Neither key is ever legal in a
                        revisions: list entry (variant-only) or in ANY
                        content file (base or delta) -- see
                        _reject_metadata_keys.
  <rigname>_<variant>.yml / <rigname>_<rev>.yml -- delta fragments (V1b):
                        instances: (shallow replace, matched by name),
                        add-instances:, remove-instances:, add-wires:/
                        remove-wires: (matched by endpoint pair),
                        dt-includes: (unions), params: (wholesale replace
                        + restate-check). Resolution order is base ->
                        variant -> revision; the per-instance-parameter
                        invariant is re-checked after every stage.
  instances[].shield    also accepts the identical <name>@<rev> grammar
                        (V1c): shield.yml gains the SAME {default:, list:
                        []} revisions: axis as rig.yml (one schema, reused
                        via _parse_axis_decl), and a revision is a native
                        DT overlay -- base <name>.shield plus
                        <name>_<rev>.shield cpp-included after it into the
                        SAME translation unit, DT's own overlay-by-label
                        semantics doing the merge. No YAML merge
                        vocabulary on the shield side at all.

Source locations come from YAML composer marks (line-accurate), so the
comparison against dtlib file:line quality is fair.
"""
from __future__ import annotations

import dataclasses
import glob
import os

import yaml

from .ctypes_registry import load_types
from .diag import Depends, Diagnostic, Diagnostics, LoadError, SrcRef
from .dtsio import (MODULE_INC, MODULE_ROOT, ZEPHYR_INC, check_include,
                    is_int_literal, parse_tu, resolve_token, source_files)
from .model import (AxisDecl, ConnectorType, Instance, Rig, Shield, Strap,
                    Wire, WireEnd)
from .shields import parse_shields

# The vendored default shield library (direct API / test use only — see
# load_shield_library below): this module's OWN boards/shields, the real
# location it ships alongside this package.
SHIELDS_DIR = os.path.join(MODULE_ROOT, "boards", "shields")


@dataclasses.dataclass
class ShieldLibrary:
    """Every discovered shield template, keyed for V1c revision resolution.

    shields is keyed by the CONSTRUCTED stems rule 13 resolves against —
    "<name>" (a revision-less shield, or a revisioned one's DEFAULT) and
    "<name>@<rev>" (any declared revision, once resolved) — never by the
    .shield DT node name alone, which is IDENTICAL across a shield's own
    revisions (the base and every <name>_<rev>.shield fragment share one
    node label, since the fragment only ever augments it by reference).
    axes maps every discovered shield NAME to its declared revisions:
    axis (None if shield.yml is absent, or present but declares no
    revisions: block) — needed so resolve() can tell "no such shield"
    apart from "declares revisions:, but no default", a case that has no
    entry in shields under the bare name either.

    A shield's BASE template is parsed eagerly when the library is built
    (this runs before rig.yml is even opened, so the loader does not yet
    know which shields any instance will name — the existing per-folder
    eager parse this replaces already had no other option). A revision
    OTHER than the default is resolved LAZILY, the first time resolve()
    sees an instance actually select it: eagerly combining every declared
    revision's translation unit regardless of use would (a) do real
    cpp/dtlib work for revisions nothing in this rig ever selects, and
    (b) leak that revision fragment's path into RIG_DEPENDS for every
    OTHER rig sharing this shield library, purely because the revision was
    DECLARED somewhere, not because anything in THIS rig referenced it —
    breaking the very "declaring an axis is not a breaking change until a
    fragment is authored" property rule 10 already established rig-side."""
    shields: dict[str, Shield]
    axes: dict[str, "AxisDecl | None"]
    _pending: dict[str, tuple[str, str, "AxisDecl"]]   # name -> (dir, base_file, decl)
    _ymls: dict[str, str]                              # name -> shield.yml, when present
    _types: dict[str, ConnectorType]
    _workdir: str
    _diags: Diagnostics
    _deps: Depends | None

    def resolve(self, ref: str, ctx: str, src: SrcRef) -> Shield | None:
        """<name> or <name>@<rev> (rule 13's identical @rev grammar) -> the
        Shield object, parsing a not-yet-resolved revision on first use.
        Mirrors _resolve_axis's three failure shapes (not declared at all /
        not a member / no default), reported as lang-rev — the shield-side
        analogue of a qualified rig target's own axis resolution — plus the
        pre-existing lang-instance-shield "unknown shield" diagnostic for a
        name this library never discovered at all. ctx names the caller
        (e.g. "instance 'sensor_0'") for that diagnostic's message."""
        name, sep, rev = ref.partition("@")
        if name not in self.axes:
            self._diags.error(
                "lang-instance-shield",
                f"{ctx}: unknown shield '{name}'\n"
                f"known shields: {', '.join(sorted(self.axes))}",
                [src])
            return None
        # This reference makes the shield's OWN shield.yml load-bearing for
        # this rig: its revisions: block decides which revision a bare
        # reference resolves to and which @rev values are legal, so editing
        # it must retrigger configure. Recorded here rather than during the
        # library scan so a rig depends only on the metadata of shields it
        # actually names -- and recorded before resolution can fail, since
        # declaring the missing revision is exactly how such a failure gets
        # fixed.
        if self._deps is not None and name in self._ymls:
            self._deps.see(self._ymls[name])
        decl = self.axes[name]
        if sep:
            if decl is None:
                self._diags.error(
                    "lang-rev",
                    f"shield '{name}' names a revision ({rev!r}), but this "
                    "shield declares no revisions: at all",
                    [src])
                return None
            if rev not in decl.values:
                self._diags.error(
                    "lang-rev",
                    f"shield '{name}': revision '{rev}' is not declared -- "
                    f"known revisions: {', '.join(decl.values)}",
                    [src])
                return None
            return self._resolve_revision(name, rev, decl, src)
        if name in self.shields:
            return self.shields[name]
        if decl is None:
            # A shield with no declared axis is parsed EAGERLY, so a missing
            # entry here means its template defined no shield node under this
            # folder name -- already reported against the template itself by
            # _pick_shield during the scan. Returning quietly keeps the
            # diagnostic pointed at the file that is wrong instead of
            # echoing it once per instance that referenced the shield.
            return None
        # A DECLARED default is resolved lazily here, on this bare
        # reference's first use -- exactly like an explicit @rev, since
        # load_shield_library defers every revisioned shield's parse
        # (default included) until something actually selects it.
        if decl.default is not None:
            return self._resolve_revision(name, decl.default, decl, src)
        self._diags.error(
            "lang-rev",
            f"shield '{name}': no revision selected, and this shield "
            f"declares no default revision -- choose one of: "
            f"{', '.join(decl.values)}",
            [src])
        return None

    def _resolve_revision(self, name: str, rev: str, decl: "AxisDecl",
                          src: SrcRef) -> Shield | None:
        key = f"{name}@{rev}"
        cached = self.shields.get(key)
        if cached is not None:
            return cached
        shield_dir, base_file, _ = self._pending[name]
        rev_norm = _normalize_revision(rev)
        rev_file = os.path.join(shield_dir, f"{name}_{rev_norm}.shield")
        rev_conf = os.path.join(shield_dir, f"{name}_{rev_norm}.conf")
        has_rev_file = os.path.isfile(rev_file)
        is_default = rev == decl.default
        # Shield-side analogue of rule 10's default exemption: a NON-DEFAULT
        # revision that contributes NOTHING (neither DT nor Kconfig) is an
        # authoring error, named by the files that were looked for; the
        # default is exempt, exactly as the base shield template already IS
        # that revision's content.
        if not is_default and not (has_rev_file or os.path.isfile(rev_conf)):
            self._diags.error(
                "lang-rev",
                f"shield '{name}': revision '{rev}' contributes nothing -- "
                f"looked for {name}_{rev_norm}.shield and "
                f"{name}_{rev_norm}.conf, neither exists",
                [src])
            return None
        includes = [base_file] + ([rev_file] if has_rev_file else [])
        if has_rev_file and self._deps is not None:
            self._deps.see(rev_file)
        dt = parse_tu(includes, self._workdir, f"shield-{name}-{rev_norm}.dts")
        if self._deps is not None:
            for real_src in source_files(dt, self._workdir):
                self._deps.see(real_src)
        parsed = parse_shields(dt, self._types, self._diags)
        shield = _pick_shield(parsed, name, base_file, self._diags)
        if shield is None:
            return None
        shield.revisions = decl
        shield.revision = rev
        self.shields[key] = shield
        if is_default:
            self.shields[name] = shield
        return shield


def _pick_shield(parsed: dict[str, Shield], name: str, template: str,
                 diags: Diagnostics) -> Shield | None:
    """The shield a template's translation unit defines, looked up by the
    FOLDER name rather than by whatever node name parse_shields returned.

    Shield.name is the .shield DT node name and remains the identity every
    diagnostic and every generated artifact spells. The RESOLUTION key,
    however, is the folder basename: it is what <name>.shield discovery
    constructs, what shield.yml's revisions: block is read from, and what an
    instance's shield: reference carries into RIG_SHIELDS (hence into
    list_shields.py's own name for the same shield). Those two names must
    therefore AGREE, and nothing in the tree enforces it -- so a mismatch is
    reported here instead of silently resolving to whichever single shield
    the file happened to define, which would leave the folder name and the
    node name disagreeing about what was built."""
    shield = parsed.get(name)
    if shield is not None:
        return shield
    defined = ", ".join(sorted(parsed)) or "none"
    diags.error(
        "lang-shield-name",
        f"shield template {os.path.basename(template)} defines no shield "
        f"node named '{name}' -- a .shield node name must match the folder "
        f"it lives in, because that folder name is what an instance's "
        f"shield: reference and shield discovery both construct\n"
        f"nodes defined here: {defined}",
        [SrcRef(template, 1)])
    return None


def _load_shield_revisions(shield_dir: str, diags: Diagnostics) -> "AxisDecl | None":
    """shield.yml's revisions: declaration (rig-variants-revisions.md V1c):
    the SAME axis shape as rig.yml's own revisions:/variants: blocks, so
    _parse_axis_decl is reused as-is rather than writing a second parser —
    shield.yml wraps its metadata under a shield: key exactly as rig.yml
    wraps its own under rig:, so the same {default:, list: []} extraction
    applies unchanged.

    shield.yml itself stays OPTIONAL from the loader's own perspective —
    a folder with no shield.yml at all (or one with no revisions: key)
    declares no axis, exactly like every shield with no revisions to
    represent and every fixture-only shield used elsewhere in this test
    suite.

    Dependency tracking happens in ShieldLibrary.resolve, NOT here: this
    function runs for every discoverable shield folder during the library
    scan, so recording the file here would put every shield's shield.yml
    into every rig's RIG_DEPENDS regardless of what that rig references.
    A shield.yml's revisions: block can only affect a rig that actually
    NAMES that shield, so the dependency is recorded exactly where that
    reference is resolved."""
    path = os.path.join(shield_dir, "shield.yml")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        try:
            root_node = yaml.compose(f, yaml.SafeLoader)
        except yaml.YAMLError as e:
            raise LoadError(Diagnostic(
                "error", "lang-parse", f"YAML parse error in {path}\n{e}",
                [SrcRef(path, getattr(getattr(e, 'problem_mark', None), 'line', 0) + 1)]))
    doc = _walk(root_node, "", path)
    shield_v = doc.v.get("shield")
    if shield_v is None:
        return None
    return _parse_axis_decl(shield_v, "revisions", diags,
                            owner=f"shield '{os.path.basename(shield_dir)}'")


def load_shield_library(workdir: str, diags: Diagnostics,
                        shield_dirs: list[str] | None = None,
                        deps: Depends | None = None) -> ShieldLibrary:
    """Load every shield template. Each .shield file (base + any resolved
    revision fragment) is its OWN translation unit (Ground rule 3), so
    labels are shield-scoped — two shields may reuse gl_plug etc. without
    colliding, and no cross-shield prefix discipline is needed.

    Shields live one per folder, upstream-shield-shape: <shield-dir>/<name>/
    <name>.shield. We therefore look for exactly <dir>/<dir-basename>.shield
    per subfolder, rather than a */*.shield glob — the folder now also holds
    upstream-convention Kconfig fragments (Kconfig.shield, Kconfig.defconfig),
    which also end in the literal substring ".shield" and would otherwise be
    mis-globbed as shield templates (Kconfig.shield matches a bare *.shield
    wildcard). This <name>.shield-presence check is also what self-filters a
    shields directory: legacy (non-rig) shields ship a <name>.overlay, not a
    .shield, so scanning a whole boards/shields tree picks up ONLY rig
    templates and silently skips the rest.

    The .shield DT node name remains the SOLE identity source (Shield.name
    = node.name in shields.py) — shield.yml supplies only the revisions:
    axis declaration (V1c), read via _load_shield_revisions, never a second
    identity. A folder with no declared axis keeps a plain one-name-one-
    parse arrangement; one WITH a declared axis defers every revision but
    the default to ShieldLibrary.resolve (see its docstring for why).

    shield_dirs is a LIST of shield-library roots (each a boards/shields
    directory), unioned into one library — because rig shield templates are
    ordinary discoverable content that may live in ANY board_root of ANY
    Zephyr module, not just this one. The build system (dts.cmake) derives the
    list from BOARD_ROOT, exactly as list_shields.py does; None falls back to
    the vendored default (SHIELDS_DIR), used only by direct API / tests.

    deps, if given, records every .shield file this call parses (base
    templates unconditionally; a revision fragment only once resolve()
    actually selects it), plus (via dtsio.source_files) whatever real
    files each one's translation unit #includes — the temp workdir the TU
    is synthesized in is excluded, since it holds a generated file with no
    counterpart in the source tree."""
    types = load_types(deps)
    shields: dict[str, Shield] = {}
    axes: dict[str, "AxisDecl | None"] = {}
    pending: dict[str, tuple[str, str, "AxisDecl"]] = {}
    ymls: dict[str, str] = {}
    directories = shield_dirs if shield_dirs is not None else [SHIELDS_DIR]
    for directory in directories:
        for shield_dir in sorted(glob.glob(os.path.join(directory, "*"))):
            if not os.path.isdir(shield_dir):
                continue
            name = os.path.basename(shield_dir)
            base_file = os.path.join(shield_dir, name + ".shield")
            if not os.path.isfile(base_file):
                continue
            if deps is not None:
                deps.see(base_file)
            shield_yml = os.path.join(shield_dir, "shield.yml")
            if os.path.isfile(shield_yml):
                ymls[name] = shield_yml
            decl = _load_shield_revisions(shield_dir, diags)
            axes[name] = decl
            if decl is None:
                dt = parse_tu([base_file], workdir, f"shield-{name}.dts")
                if deps is not None:
                    for src in source_files(dt, workdir):
                        deps.see(src)
                shield = _pick_shield(parse_shields(dt, types, diags), name,
                                      base_file, diags)
                if shield is not None:
                    shields[name] = shield
            else:
                pending[name] = (shield_dir, base_file, decl)
    return ShieldLibrary(shields=shields, axes=axes, _pending=pending,
                         _ymls=ymls, _types=types, _workdir=workdir,
                         _diags=diags, _deps=deps)


# ---------------------------------------------------------------- mark-aware YAML

class _Val:
    """A YAML scalar/collection + its source position."""
    __slots__ = ("v", "src")

    def __init__(self, v, src):
        self.v, self.src = v, src


def _walk(node, path, fname):
    src = SrcRef(fname, node.start_mark.line + 1, path)
    if isinstance(node, yaml.MappingNode):
        m = {}
        for k, v in node.value:
            key = k.value
            m[key] = _walk(v, f"{path}.{key}" if path else key, fname)
        return _Val(m, src)
    if isinstance(node, yaml.SequenceNode):
        return _Val([_walk(v, f"{path}[{i}]", fname)
                     for i, v in enumerate(node.value)], src)
    return _Val(_scalar(node), src)


def _scalar(node):
    v = node.value
    if node.tag.endswith(":int"):
        return int(v.replace("_", ""), 0)
    if node.tag.endswith(":bool"):
        return v.lower() in ("true", "yes", "on")
    if node.tag.endswith(":null"):
        return None
    return v


def _require(mapping: _Val, key: str, ctx: str, diags) -> _Val | None:
    if key not in mapping.v:
        diags.error("lang-schema", f"{ctx}: required key '{key}' is missing",
                    [mapping.src])
        return None
    return mapping.v[key]


# ---------------------------------------------------------------- V1a qualifier axes

def _parse_axis_decl(container_v: _Val, key: str, diags,
                     owner: str = "rig",
                     allow_variant_metadata: bool = False) -> AxisDecl | None:
    """A revisions:/variants: declaration block: {default:, list: []}.
    Absent key -> no axis declared (None). Shape is validated strictly
    here: list: must be non-empty, and default: (if given) must be one of
    its own members -- both are lang-schema, like every other
    malformed-shape error this loader reports, since they are defects of
    the declaring FILE itself, not of a particular selection.

    owner names the file that declares the block, and it must, because this
    one parser serves BOTH rig.yml and shield.yml (V1c reuses it rather than
    growing a second parser for the same shape). Without it every shield.yml
    shape defect reported "rig revisions: ..." -- blaming the rig for a
    shield's own malformed declaration, and naming no shield at all. Callers
    pass the specific spelling ("rig", "shield 'x'").

    allow_variant_metadata gates the ONE shape a rig's own variants: list
    may take that no other axis may: a list entry given as a mapping
    {name:, board:, sockets:} rather than a bare name, carrying the board
    that variant selects and its abstract-socket map. A rig's revisions:
    axis and every shield.yml revisions: axis pass False (the default) and
    so keep taking scalars only -- a revision is a change within one
    physical family, never a move to a different host board, and this is
    what enforces that at the declaration itself rather than leaving it to
    a later semantic check."""
    axis_v = container_v.v.get(key)
    if axis_v is None:
        return None
    list_v = axis_v.v.get("list")
    values: list[str] = []
    boards: dict[str, str] = {}
    sockets: dict[str, dict[str, str]] = {}
    for item_v in (list_v.v if list_v is not None else []):
        if isinstance(item_v.v, dict):
            if not allow_variant_metadata:
                diags.error(
                    "lang-schema",
                    f"{owner} {key}: a mapping entry (name:/board:/"
                    "sockets:) is legal only in a rig's variants: list -- "
                    "this axis takes bare names",
                    [item_v.src])
                continue
            name_v = _require(item_v, "name", f"{owner} {key} entry", diags)
            if name_v is None:
                continue
            name = str(name_v.v)
            values.append(name)
            board_v = item_v.v.get("board")
            if board_v is not None:
                boards[name] = board_v.v
            sockets_v = item_v.v.get("sockets")
            if sockets_v is not None:
                sockets[name] = {k: v.v for k, v in sockets_v.v.items()}
        else:
            values.append(str(item_v.v))
    if not values:
        diags.error("lang-schema",
                    f"{owner} {key}: 'list' must be a non-empty list",
                    [axis_v.src])
        return None
    default_v = axis_v.v.get("default")
    if default_v is None:
        return AxisDecl(values=values, boards=boards, sockets=sockets)
    default = str(default_v.v)
    if default not in values:
        diags.error(
            "lang-schema",
            f"{owner} {key}: default '{default}' is not one of the declared "
            f"values ({', '.join(values)})",
            [default_v.src])
        return None
    return AxisDecl(values=values, default=default, boards=boards, sockets=sockets)


def _resolve_board(rig: Rig, board_v: _Val | None, sockets_v: _Val | None,
                   src: SrcRef, diags) -> dict[str, str]:
    """The board this rig actually builds, and the abstract-socket map its
    content resolves against. Two legal shapes, and mixing them is an
    error: a single top-level board: (optionally paired with a top-level
    sockets: map, applied regardless of which variant is selected), or a
    board: declared beside EVERY variants: list entry (each with its own
    optional sockets:). A silent fallback between the two would make
    "which board won" unanswerable from the file alone -- exactly the
    defect this split exists to remove -- so a top-level board: alongside
    any per-variant board:, or only SOME variants declaring one, is
    rejected rather than resolved.

    Sets rig.board and returns the socket map to apply while parsing this
    rig's topology (base content and every delta). On any rejection here
    rig.board is left as the empty string and the returned map is empty;
    neither is read again, since the CLI stops before the analyzer once
    the loader has recorded a diagnostic."""
    variants = rig.variants
    per_variant_boards = variants.boards if variants is not None else {}
    if variants is not None and per_variant_boards:
        if board_v is not None:
            diags.error(
                "lang-schema",
                f"rig '{rig.name}' declares a top-level board: while its "
                "variants also declare their own -- a rig may declare a "
                "board per variant or once at the top level, never both",
                [board_v.src, src])
            rig.board = ""
            return {}
        missing = [v for v in variants.values if v not in per_variant_boards]
        if missing:
            diags.error(
                "lang-schema",
                f"rig '{rig.name}': variant(s) {', '.join(missing)} declare "
                f"no board:, but variant(s) "
                f"{', '.join(sorted(per_variant_boards))} do -- every "
                "variant must declare a board, or none should",
                [src])
            rig.board = ""
            return {}
        if sockets_v is not None:
            diags.error(
                "lang-schema",
                f"rig '{rig.name}' declares a top-level sockets: map "
                "while its variants declare their own boards -- put each "
                "variant's own socket map beside its board: under "
                "variants: list instead",
                [sockets_v.src])
            rig.board = ""
            return {}
        if rig.variant is None:
            rig.board = ""    # an earlier axis error already reported why
            return {}
        rig.board = per_variant_boards[rig.variant]
        return dict(variants.sockets.get(rig.variant, {}))
    if board_v is None:
        diags.error(
            "lang-schema",
            f"rig '{rig.name}' declares no board: -- add a top-level "
            "board:, or give every declared variant its own",
            [src])
        rig.board = ""
        return {}
    rig.board = board_v.v
    if sockets_v is None:
        return {}
    return {k: v.v for k, v in sockets_v.v.items()}


def _normalize_revision(rev: str) -> str:
    """hwmv2's own revision normalization (zephyr_build_string,
    extensions.cmake:1772, design-log 2026-07-26d): a dotted revision id
    becomes underscores in the constructed filename (1.2 -> 1_2). Applied
    everywhere a revision segment is joined into a fragment filename --
    never to the SELECTED value itself, which stays the raw declared
    string for validation/provenance."""
    return rev.replace(".", "_")


def _check_axis_collision(rig: Rig, src: SrcRef, diags) -> None:
    """Rule 4, WIDENED for combined fragments (design-log 2026-07-26d): no
    two distinct (variant, revision) SELECTIONS may construct the same
    fragment stem. Q6's protection is that filenames are only ever
    CONSTRUCTED, never parsed, so the hazard is not misparsing -- it is two
    DIFFERENT selections landing on one literal filename (e.g. a variant
    literally named 'variant_a_2' constructs the same stem as variant
    'variant_a' + revision '2' combined). Enumerates every stem the
    declared axes could ever construct -- each axis alone, plus every
    combined (variant, revision) pair -- and checks none of them collide.
    This subsumes the original (narrower) rule: a variant name equal to a
    revision id is just the case where two SINGLE-axis stems collide."""
    variants = rig.variants.values if rig.variants is not None else []
    revisions = rig.revisions.values if rig.revisions is not None else []
    origins: dict[str, list[str]] = {}

    def note(stem: str, origin: str) -> None:
        origins.setdefault(stem, []).append(origin)

    for v in variants:
        note(f"{rig.name}_{v}", f"variant '{v}'")
    for r in revisions:
        note(f"{rig.name}_{_normalize_revision(r)}", f"revision '{r}'")
    for v in variants:
        for r in revisions:
            note(f"{rig.name}_{v}_{_normalize_revision(r)}",
                 f"variant '{v}' + revision '{r}'")

    for stem in sorted(origins):
        stem_origins = origins[stem]
        if len(stem_origins) > 1:
            diags.error(
                "lang-variant",
                f"rig '{rig.name}': {' and '.join(stem_origins)} all "
                f"construct the same fragment stem '{stem}' -- the "
                "constructed filenames would be ambiguous about which "
                "selection a fragment belongs to",
                [src])


def _resolve_axis(rig_name: str, axis_kind: str, decl_key: str,
                  decl: AxisDecl | None, selected: str | None,
                  src: SrcRef, diags) -> str | None:
    """Resolve ONE qualifier axis (`revision` or `variant`) to its final
    SELECTED value. A `selected` value naming an UNDECLARED axis says so by
    name ("this rig declares no revisions:") rather than the generic
    not-a-member wording (P's rule-5 precedent) -- it points the author at
    the right place, given the loader's own permissiveness about unknown
    rig-level keys. A selected value against a DECLARED axis must be one of
    its members (rule 1/2). A bare (unselected) axis takes the declared
    default; if the axis is declared but has none, that is rule 3."""
    code = "lang-rev" if axis_kind == "revision" else "lang-variant"
    if selected is not None:
        if decl is None:
            diags.error(
                code,
                f"rig '{rig_name}' names a {axis_kind} ({selected!r}), but "
                f"this rig declares no {decl_key}: at all",
                [src])
            return None
        if selected not in decl.values:
            diags.error(
                code,
                f"rig '{rig_name}': {axis_kind} '{selected}' is not "
                f"declared -- known {axis_kind}s: {', '.join(decl.values)}",
                [src])
            return None
        return selected
    if decl is None:
        return None
    if decl.default is not None:
        return decl.default
    diags.error(
        code,
        f"rig '{rig_name}': no {axis_kind} selected, and this rig declares "
        f"no default {axis_kind} -- choose one of: {', '.join(decl.values)}",
        [src])
    return None


def _variant_metadata_differs(rig: Rig) -> bool:
    """Rule 10's metadata avenue: whether the SELECTED variant's own board
    and socket map actually differ from the declared default variant's --
    the strengthened reading a bare board: key's presence does not itself
    satisfy. A rig with no per-variant boards at all (rig.variants.boards
    empty) never contributes this way, since there is nothing per-variant
    to differ."""
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


def _check_fragment_presence(rig: Rig, rig_dir: str, src: SrcRef, diags,
                             has_variant_delta: bool = False,
                             has_revision_delta: bool = False) -> None:
    """Rule 10: a selected NON-DEFAULT axis value that contributes NOTHING --
    no fragment of any kind found for it -- naming the files that were looked
    for. A value that changes nothing is meaningless, so it is an authoring
    error rather than a silent no-op.

    The DECLARED DEFAULT of an axis is exempt: the base rig file IS that
    value's content, exactly as hwmv2 boards have <board>.dts plus
    <board>_<variant>.dts and never a <board>_<default>.dts. A default MAY
    still carry a fragment (see the pilot's variant_a) -- it just must not
    be required to, or declaring an axis on an existing rig would break it
    until a fragment describing what the rig already is gets authored.

    A variant has a SECOND way to contribute, carrying no fragment at all:
    its own declared board and/or socket map, if either actually DIFFERS
    from the default variant's. Merely declaring a board is not enough --
    a variant restating the default's board and map verbatim is precisely
    the silent no-op this rule exists to catch (_variant_metadata_differs
    is the comparison).

    Three fragment kinds count as "contributes something" as of V1b: the
    cmake-collected .overlay/_defconfig (V1a), and now the .yml delta this
    module itself applies -- has_variant_delta/has_revision_delta report
    whether one was found on disk (the caller already looked, to load it)."""
    if rig.variant is not None and not (
            rig.variants is not None and rig.variant == rig.variants.default):
        overlay = f"{rig.name}_{rig.variant}.overlay"
        defconfig = f"{rig.name}_{rig.variant}_defconfig"
        delta = f"{rig.name}_{rig.variant}.yml"
        if not (has_variant_delta
                or os.path.isfile(os.path.join(rig_dir, overlay))
                or os.path.isfile(os.path.join(rig_dir, defconfig))
                or _variant_metadata_differs(rig)):
            metadata_hint = ""
            if rig.variants is not None and rig.variants.boards:
                metadata_hint = (", and its board/sockets metadata does "
                                 "not differ from the default variant's")
            diags.error(
                "lang-variant",
                f"rig '{rig.name}': variant '{rig.variant}' contributes "
                f"nothing -- looked for {overlay}, {defconfig} and {delta}, "
                f"none exist{metadata_hint}",
                [src])
    if rig.revision is not None and not (
            rig.revisions is not None
            and rig.revision == rig.revisions.default):
        norm = _normalize_revision(rig.revision)
        defconfig = f"{rig.name}_{norm}_defconfig"
        delta = f"{rig.name}_{norm}.yml"
        if not (has_revision_delta
                or os.path.isfile(os.path.join(rig_dir, defconfig))):
            diags.error(
                "lang-rev",
                f"rig '{rig.name}': revision '{rig.revision}' contributes "
                f"nothing -- looked for {defconfig} and {delta}, neither "
                "exists",
                [src])


# ---------------------------------------------------------------- V1b delta engine

def _load_delta_doc(path: str, deps: Depends | None) -> _Val:
    """Parse ONE FLAT top-level YAML document naming real source-tree
    content: either the rig's <rigname>.yml BASE CONTENT file (the
    metadata/content split) or a <rigname>_<variant|rev>.yml delta
    fragment (rig-variants-revisions.md V1b Sec. 5) layered onto it. There
    is no `rig:` wrapper in either case -- unlike rig.yml, neither is a
    rig IDENTITY of its own, both are a document ABOUT topology (one the
    base, one a patch), so the same top-level shape and the same parser
    serve both: instances:/wires:/dt-includes: (base and delta alike),
    board:/sockets:/add-instances:/remove-instances:/add-wires:/
    remove-wires:/params (delta-only keys, rejected or ignored by whichever
    caller does not expect them)."""
    if deps is not None:
        deps.see(path)
    with open(path) as f:
        try:
            root_node = yaml.compose(f, yaml.SafeLoader)
        except yaml.YAMLError as e:
            raise LoadError(Diagnostic(
                "error", "lang-parse", f"YAML parse error in {path}\n{e}",
                [SrcRef(path, getattr(getattr(e, 'problem_mark', None), 'line', 0) + 1)]))
    return _walk(root_node, "", path)


def _load_base_content(rig_name: str, rig_dir: str, rig_src: SrcRef,
                       deps: Depends | None, diags: Diagnostics) -> _Val | None:
    """<rigname>.yml — the rig's REQUIRED content file (the metadata/content
    split): instances:/wires:/dt-includes: live here, never in rig.yml.
    Named from the rig's own IDENTITY (rig.yml's name:), constructed —
    never parsed from the folder — exactly like every delta fragment
    already is; structurally identical to one (see _load_delta_doc), so
    parsing reuses it rather than a second parser.

    Absent entirely is a hard error naming the file that was looked for,
    in the lang-* family every other loader defect uses: a rig whose
    metadata resolves but has nothing to build is an authoring mistake,
    distinct from a rig with zero instances (an empty instances: list is
    legal — a content file missing altogether is not)."""
    path = os.path.join(rig_dir, f"{rig_name}.yml")
    if not os.path.isfile(path):
        diags.error(
            "lang-content",
            f"rig '{rig_name}': no content file found -- expected {path}",
            [rig_src])
        return None
    return _load_delta_doc(path, deps)


def _union_dt_includes(rig: Rig, dt_includes_v: _Val | None) -> None:
    """dt-includes: UNIONS across delta stages (Sec. 5, NEW 2026-07-26) --
    the one merge key with union semantics: a vocabulary is additive by
    nature, and a variant substituting a different shield legitimately
    needs a header the base never declared. A header already present
    (declared by an earlier stage) is skipped, keeping that stage's own
    SrcRef rather than the later one."""
    if dt_includes_v is None:
        return
    for h_v in dt_includes_v.v:
        if h_v.v not in rig.dt_includes:
            rig.dt_includes.append(h_v.v)
            rig.dt_includes_refs.append(h_v.src)


def _check_param_invariant(instances, diags) -> None:
    """The per-stage invariant (Sec. 4, NEW 2026-07-26): after EVERY delta
    stage, every instance's EFFECTIVE shield/params must satisfy P's rule 2
    (every declared, no-default-authored parameter is assigned). This
    REPLACES an earlier proposal to forbid revisions from touching
    parameters at all -- deltas never "add parameters", shields DECLARE
    them and rigs ASSIGN them, so a parameter set changes only as a
    consequence of a shield change, and a revision swapping a shield is the
    motivating example for revisions existing at all. A shield REVISION
    (V1c) can change the set too (a default authored where the base had
    none, or a new required device); this ONE invariant, re-checked fresh
    after every stage, covers all three sources with no special-casing."""
    for inst in instances:
        shield = inst.shield
        assigned = inst.params
        for dev in shield.devices:
            pset = assigned.get(dev.label, {})
            for pname in dev.declared_params:
                if pname in pset:
                    continue
                if any(name == pname for name, _ in dev.extra_props):
                    continue      # shield authored a default; may be omitted
                diags.error(
                    "lang-param",
                    f"instance '{inst.name}': device '{dev.label}' of "
                    f"shield '{shield.name}' declares '{pname}' as "
                    "required (shield,params, no default authored) but "
                    f"this instance does not assign it — add params: "
                    f"{{{dev.label}: {{{pname}: <value>}}}}",
                    [inst.src])


def _apply_params_block(params_v: _Val | None, inst: Instance, shield: Shield,
                        rig: Rig, workdir: str, diags,
                        unknown_device_context: str | None = None) -> None:
    """Parse ONE params: block -- the base assignment, OR a delta's
    wholesale replacement (Sec. 5) -- into inst.params/param_refs. Rules 1/3
    (undeclared property / unknown device) fire immediately against the
    CURRENT shield; rules 4/5 (token resolution) too. Rule 2 (every
    required parameter assigned) is deliberately NOT checked here -- it is
    the per-stage invariant (_check_param_invariant), run once per stage
    over every instance, since a LATER stage may still supply what an
    EARLIER one left required-but-unassigned.

    unknown_device_context, if given, is folded into rule 3's message when
    it fires (rule 12, NEW 2026-07-26): a family-wide revision's params
    naming a device the POST-VARIANT shield does not have is unavoidable by
    construction whenever a variant already substituted the shield (under
    variant hpm the delta must say hpm_dev, under bosch bme_dev, and one
    fragment cannot serve both) -- so the message names the variant rather
    than leaving the author to guess why an existing label stopped
    resolving."""
    if params_v is None:
        return
    devices_by_label = {d.label: d for d in shield.devices}
    for dev_label, props_v in params_v.v.items():
        dev = devices_by_label.get(dev_label)
        if dev is None:
            context = f" ({unknown_device_context})" if unknown_device_context else ""
            diags.error(
                "lang-param",
                f"instance '{inst.name}': params names no device "
                f"'{dev_label}' of shield '{shield.name}'{context}\n"
                f"devices of '{shield.name}': "
                f"{', '.join(sorted(devices_by_label)) or 'none'}",
                [props_v.src])
            continue
        for prop_name, val_v in props_v.v.items():
            if prop_name not in dev.declared_params:
                diags.error(
                    "lang-param",
                    f"instance '{inst.name}': device '{dev_label}' of "
                    f"shield '{shield.name}' declares no parameter "
                    f"'{prop_name}' (shield,params)\n"
                    f"declared parameters of '{dev_label}': "
                    f"{', '.join(dev.declared_params) or 'none'}",
                    [val_v.src])
                continue
            raw = str(val_v.v)
            inst.params.setdefault(dev_label, {})[prop_name] = raw
            inst.param_refs.setdefault(dev_label, {})[prop_name] = val_v.src
            if not is_int_literal(raw):
                _check_param_token(inst, dev_label, prop_name, raw, rig,
                                   workdir, val_v.src, diags)


def _apply_pin_block(pin_v: _Val | None, inst: Instance, shield: Shield,
                     diags) -> None:
    """pin: {config-element-name: value} -- shared by the base parse and a
    delta's instances: patch (which resets pins/jumpers first, so this
    always starts from empty when called from a patch)."""
    if pin_v is None:
        return
    for cfg_name, val_v in pin_v.v.items():
        # resolution rule: pin keys name a config element (strap OR
        # routing jumper) WITHIN the named shield
        elem = shield.config_element(cfg_name.replace("_", "-")) \
            or shield.config_element(cfg_name)
        if elem is None:
            names = sorted(list(shield.straps) + list(shield.jumpers))
            diags.error(
                "lang-pin",
                f"instance '{inst.name}': pin names no config element "
                f"'{cfg_name}' of shield '{shield.name}'\n"
                f"config elements of '{shield.name}': {', '.join(names) or 'none'}",
                [val_v.src])
            continue
        if isinstance(elem, Strap):
            inst.pins[elem.name] = val_v.v
            inst.pin_refs[elem.name] = val_v.src
        else:                                   # Jumper: position value
            inst.jumpers[elem.name] = val_v.v
            inst.jumper_refs[elem.name] = val_v.src


def _check_restate(params_v: _Val, inst: Instance, diags) -> None:
    """Rule 11 (Sec. 5): if a delta supplies params for an instance whose
    shield it does NOT change, it must RESTATE every property the
    effective topology had already assigned; omitting one is an error
    naming it. The hazard this closes: same shield + a previously-assigned
    OPTIONAL parameter + a delta that forgets to repeat it = a SILENT
    revert to the shield default, since params: replaces WHOLESALE (Sec.
    5) rather than deep-merging. Called BEFORE inst.params is cleared for
    the wholesale replace, so it sees what the effective topology had."""
    restated = {
        (dev_label, prop_name)
        for dev_label, props_v in params_v.v.items()
        for prop_name in props_v.v
    }
    for dev_label, props in inst.params.items():
        for prop_name in props:
            if (dev_label, prop_name) not in restated:
                diags.error(
                    "lang-param",
                    f"instance '{inst.name}': this delta supplies params "
                    f"for device '{dev_label}' without restating "
                    f"'{prop_name}', which the effective topology already "
                    "assigns -- wholesale replace means omitting it "
                    "silently reverts to the shield default; restate it "
                    "explicitly or remove it deliberately",
                    [params_v.src])


def _find_wire(wires: list[Wire], frm: str | None, to: str | None) -> Wire | None:
    """Match remove-wires: by RAW endpoint pair (<instance>.<node> strings on
    both sides, Sec. 5) -- a wire carries no identity beyond its endpoints
    (Q7), so this is the only stable way to find one to remove."""
    if frm is None or to is None:
        return None
    for w in wires:
        if (f"{w.frm.instance.name}.{w.frm.node}" == frm
                and f"{w.to.instance.name}.{w.to.node}" == to):
            return w
    return None


def _apply_instance_patch(item: _Val, inst: Instance, lib: ShieldLibrary, rig: Rig,
                          workdir: str, diags, stage: str, stage_value: str,
                          socket_map: dict[str, str]) -> None:
    """Shallow-replace an EXISTING instance's top-level keys (Sec. 5): a
    GIVEN key REPLACES; an unspecified key INHERITS. shield/socket/invert/
    pin/params are each the deepest merge unit -- no key merges into what
    was there before, it wholesale replaces it. When shield changes, the
    OLD params are keyed to the OLD shield's devices and are therefore
    meaningless against the new one, so they are dropped rather than
    carried forward (Sec. 5's reasoning for why wholesale replace is
    REQUIRED, not merely acceptable).

    A delta's shield: value carries the identical <name>@<rev> grammar as
    a base instance's own (V1c) -- lib.resolve is the single resolution
    path for both, so a variant/revision substituting a shield may equally
    substitute a specific revision of it.

    socket_map is the SAME abstract-socket map the base topology resolved
    against -- the selected variant's own, or the rig's top-level one --
    never a delta-local map: sockets: is metadata, declared once in
    rig.yml, so there is nothing for a delta to carry."""
    shield_changed = False
    if "shield" in item.v:
        shield_v = item.v["shield"]
        shield = lib.resolve(shield_v.v, f"instance '{inst.name}'", shield_v.src)
        if shield is None:
            return
        inst.shield = shield
        shield_changed = True
        inst.params = {}
        inst.param_refs = {}

    if "socket" in item.v:
        value = item.v["socket"].v
        inst.socket = socket_map.get(value, value)

    if "invert" in item.v:
        inst.invert = bool(item.v["invert"].v)

    if "pin" in item.v:
        inst.pins = {}
        inst.pin_refs = {}
        inst.jumpers = {}
        inst.jumper_refs = {}
        _apply_pin_block(item.v["pin"], inst, inst.shield, diags)

    if "params" in item.v:
        if not shield_changed:
            _check_restate(item.v["params"], inst, diags)   # rule 11
            inst.params = {}
            inst.param_refs = {}
        # rule 12: a family-wide revision's params landing on a device the
        # POST-VARIANT shield lacks needs the variant named, since that is
        # unavoidably why an existing device label stopped resolving.
        context = None
        if stage == "revision" and rig.variant is not None:
            context = (f"this instance's shield is '{inst.shield.name}' "
                       f"because of variant '{rig.variant}'")
        _apply_params_block(item.v["params"], inst, inst.shield, rig,
                            workdir, diags, unknown_device_context=context)


def _reject_metadata_keys(doc_v: _Val, diags) -> None:
    """board:/sockets: are rig.yml metadata now -- the axis declaration
    carries them (per variant, or once at top level), never a content
    file. A content file still carrying either -- the base <rigname>.yml
    or any variant/revision delta alike -- names an authoring mistake at
    the wrong layer, pointed at the place it now belongs."""
    for key in ("board", "sockets"):
        key_v = doc_v.v.get(key)
        if key_v is not None:
            diags.error(
                "lang-schema",
                f"{doc_v.src.file}: '{key}:' is rig.yml metadata -- move "
                "it to the variant that owns it (or the top-level rig: "
                "block, for a single-board rig), not a content file",
                [key_v.src])


def _apply_delta(delta_v: _Val, stage: str, stage_value: str, rig: Rig,
                 lib: ShieldLibrary, effective: dict[str, Instance], order: list[str],
                 wires: list[Wire], removed_by: dict[str, str],
                 workdir: str, socket_map: dict[str, str], diags) -> None:
    """Apply ONE delta stage (Sec. 5) onto the effective topology IN PLACE.
    `stage` is "variant" or "revision" (rules 6-9 differ only in the
    diagnostic code); `stage_value` is the selected axis value itself,
    folded into rule-8/12 wording so drift cannot hide. socket_map is the
    rig's own metadata map (see _apply_instance_patch), threaded through
    unchanged -- a delta never carries its own."""
    code = "lang-variant" if stage == "variant" else "lang-rev"
    doc = delta_v.v

    _reject_metadata_keys(delta_v, diags)

    # instances: -- matched by name against the EFFECTIVE topology; a
    # match that is not found is always an error (rule 6): additions are
    # never implicit, that is what add-instances: is for.
    instances_v = doc.get("instances")
    if instances_v is not None:
        for item in instances_v.v:
            name_v = _require(item, "name", f"{stage} instances:", diags)
            if name_v is None:
                continue
            name = name_v.v
            inst = effective.get(name)
            if inst is None:
                diags.error(
                    code,
                    f"{stage} '{stage_value}': instances: names '{name}', "
                    "which the effective topology does not have",
                    [item.src])
                continue
            _apply_instance_patch(item, inst, lib, rig, workdir, diags,
                                  stage, stage_value, socket_map)

    # add-instances: -- full declarations; the name must NOT already exist
    # (rule 7).
    add_v = doc.get("add-instances")
    if add_v is not None:
        for item in add_v.v:
            new_inst = _parse_instance(item, lib, rig, workdir, diags, socket_map)
            if new_inst is None:
                continue
            if new_inst.name in effective:
                diags.error(
                    code,
                    f"{stage} '{stage_value}': add-instances: names "
                    f"'{new_inst.name}', which already exists",
                    [item.src])
                continue
            effective[new_inst.name] = new_inst
            order.append(new_inst.name)

    # remove-instances: -- names must exist (rule 8); if a variant already
    # removed it, the message NAMES the variant so drift cannot hide.
    remove_v = doc.get("remove-instances")
    if remove_v is not None:
        for name_v in remove_v.v:
            name = name_v.v
            if name not in effective:
                prior = removed_by.get(name)
                hint = f" (variant '{prior}' already removed it)" if prior else ""
                diags.error(
                    code,
                    f"{stage} '{stage_value}': remove-instances: names "
                    f"'{name}', which does not exist{hint}",
                    [name_v.src])
                continue
            del effective[name]
            removed_by[name] = stage_value

    # remove-wires:/add-wires: -- matched by endpoint pair (rule 9); a
    # re-route is remove+add, there is no wire "replace".
    remove_wires_v = doc.get("remove-wires")
    if remove_wires_v is not None:
        for item in remove_wires_v.v:
            frm_v = item.v.get("from")
            to_v = item.v.get("to")
            frm = frm_v.v if frm_v is not None else None
            to = to_v.v if to_v is not None else None
            match = _find_wire(wires, frm, to)
            if match is None:
                diags.error(
                    code,
                    f"{stage} '{stage_value}': remove-wires: names "
                    f"{{from: {frm}, to: {to}}}, which does not exist",
                    [item.src])
                continue
            wires.remove(match)

    add_wires_v = doc.get("add-wires")
    if add_wires_v is not None:
        for item in add_wires_v.v:
            wire = _parse_wire(item, effective, diags)
            if wire is not None:
                wires.append(wire)


# ---------------------------------------------------------------- loader

def load(rig_path: str, workdir: str, diags: Diagnostics,
        shield_dirs: list[str] | None = None,
        deps: Depends | None = None,
        revision: str | None = None,
        variant: str | None = None) -> Rig | None:
    if deps is not None:
        deps.see(rig_path)
    lib = load_shield_library(workdir, diags, shield_dirs, deps)

    with open(rig_path) as f:
        try:
            root_node = yaml.compose(f, yaml.SafeLoader)
        except yaml.YAMLError as e:
            raise LoadError(Diagnostic(
                "error", "lang-parse", f"YAML parse error\n{e}",
                [SrcRef(rig_path, getattr(getattr(e, 'problem_mark', None), 'line', 0) + 1)]))
    doc = _walk(root_node, "", rig_path)

    rig_v = _require(doc, "rig", "top level", diags)
    if rig_v is None:
        return None
    name_v = _require(rig_v, "name", "rig", diags)
    if name_v is None:
        return None
    rig = Rig(name=name_v.v, board="", src=rig_v.src)
    rig_dir = os.path.dirname(rig_path)

    # Qualifier axes: declare (shape-validated), resolve the SELECTED value
    # for each (rules 1-4). rig.revision/rig.variant exist for validation
    # and provenance (context.cmake, build_info) regardless of whether a
    # delta engine ever runs below.
    rig.revisions = _parse_axis_decl(rig_v, "revisions", diags)
    rig.variants = _parse_axis_decl(rig_v, "variants", diags,
                                    allow_variant_metadata=True)
    _check_axis_collision(rig, rig_v.src, diags)
    rig.revision = _resolve_axis(rig.name, "revision", "revisions",
                                 rig.revisions, revision, rig_v.src, diags)
    rig.variant = _resolve_axis(rig.name, "variant", "variants",
                                rig.variants, variant, rig_v.src, diags)

    # The board this rig builds, and the abstract-socket map its topology
    # resolves against -- from rig.yml metadata alone (either the
    # degenerate top-level pair, or the resolved variant's own), before any
    # content file is opened (_resolve_board's own docstring has the two
    # shapes and their mixing rule).
    socket_map = _resolve_board(rig, rig_v.v.get("board"), rig_v.v.get("sockets"),
                                rig_v.src, diags)

    # The rig's REQUIRED content file (the metadata/content split):
    # instances:/wires:/dt-includes: live here, never in rig.yml -- named
    # from the rig's own identity (rig.name), never the folder.
    content_v = _load_base_content(rig.name, rig_dir, rig_v.src, deps, diags)
    if content_v is None:
        return None
    _reject_metadata_keys(content_v, diags)

    # V1b delta fragments: looked up by the SAME constructed stems rule 10
    # checks, built from rig.revision/rig.variant alone -- never ${RIG},
    # per THE TRAP. Loaded (not yet APPLIED) here, before rule 10 (an
    # existing .yml counts as "contributes something") and before
    # dt-includes union (a delta's own vocabulary must be known before ANY
    # params get token-validated, including the base's own).
    variant_delta_v: _Val | None = None
    if rig.variant is not None:
        variant_delta_path = os.path.join(rig_dir, f"{rig.name}_{rig.variant}.yml")
        if os.path.isfile(variant_delta_path):
            variant_delta_v = _load_delta_doc(variant_delta_path, deps)

    revision_delta_v: _Val | None = None
    if rig.revision is not None:
        rev_norm = _normalize_revision(rig.revision)
        revision_delta_path = os.path.join(rig_dir, f"{rig.name}_{rev_norm}.yml")
        if os.path.isfile(revision_delta_path):
            revision_delta_v = _load_delta_doc(revision_delta_path, deps)

    if rig.revision is not None or rig.variant is not None:
        _check_fragment_presence(
            rig, rig_dir, rig_v.src, diags,
            has_variant_delta=variant_delta_v is not None,
            has_revision_delta=revision_delta_v is not None)

    # dt-includes: UNION base + variant delta + revision delta (Sec. 5, NEW
    # 2026-07-26), all BEFORE any params get token-validated below.
    _union_dt_includes(rig, content_v.v.get("dt-includes"))
    if variant_delta_v is not None:
        _union_dt_includes(rig, variant_delta_v.v.get("dt-includes"))
    if revision_delta_v is not None:
        _union_dt_includes(rig, revision_delta_v.v.get("dt-includes"))
    if rig.dt_includes:
        _check_dt_includes(rig, workdir, diags)

    # Stage 0: base topology, read from the content file. The per-stage
    # invariant (rule 2) is checked PER INSTANCE, immediately after each is
    # parsed -- exactly the order V1a used, so the 13 axis-less corpus rigs
    # see byte-identical diagnostics (no delta ever selected for them, so
    # nothing below this comment ever runs for them beyond this loop).
    effective: dict[str, Instance] = {}
    order: list[str] = []
    insts_v = _require(content_v, "instances", "rig", diags)
    for item in (insts_v.v if insts_v else []):
        inst = _parse_instance(item, lib, rig, workdir, diags, socket_map)
        if inst:
            effective[inst.name] = inst
            order.append(inst.name)
            _check_param_invariant([inst], diags)

    wires: list[Wire] = []
    for item in content_v.v.get("wires", _Val([], content_v.src)).v:
        wire = _parse_wire(item, effective, diags)
        if wire:
            wires.append(wire)

    removed_by: dict[str, str] = {}

    # Stage 1: variant delta.
    if variant_delta_v is not None:
        assert rig.variant is not None    # a delta only loads for a selected axis
        _apply_delta(variant_delta_v, "variant", rig.variant, rig, lib,
                     effective, order, wires, removed_by, workdir, socket_map, diags)
        _check_param_invariant(effective.values(), diags)

    # Stage 2: revision delta -- ONE family-wide stream, applied AFTER the
    # variant (Q9); per-variant streams stay deferred (rule 12).
    if revision_delta_v is not None:
        assert rig.revision is not None   # a delta only loads for a selected axis
        _apply_delta(revision_delta_v, "revision", rig.revision, rig, lib,
                     effective, order, wires, removed_by, workdir, socket_map, diags)
        _check_param_invariant(effective.values(), diags)

    rig.instances = [effective[n] for n in order if n in effective]
    rig.wires = wires
    return rig


def _parse_instance(item: _Val, lib: ShieldLibrary, rig: Rig, workdir: str, diags,
                    socket_map: dict[str, str]) -> Instance | None:
    name_v = _require(item, "name", "instance", diags)
    shield_v = _require(item, "shield", "instance", diags)
    socket_v = _require(item, "socket", "instance", diags)
    if not (name_v and shield_v and socket_v):
        return None

    shield = lib.resolve(shield_v.v, f"instance '{name_v.v}'", shield_v.src)
    if shield is None:
        return None

    socket_value = socket_v.v
    inst = Instance(name=name_v.v, shield=shield,
                    socket=socket_map.get(socket_value, socket_value), src=item.src)
    inv_v = item.v.get("invert")
    inst.invert = bool(inv_v.v) if inv_v is not None else False

    _apply_pin_block(item.v.get("pin"), inst, shield, diags)
    _apply_params_block(item.v.get("params"), inst, shield, rig, workdir, diags)
    return inst


def _check_param_token(inst: Instance, dev_label: str, prop_name: str, raw: str,
                       rig: Rig, workdir: str, ref: SrcRef, diags) -> None:
    """Rules 4/5: an assigned token that is not a bare integer literal must
    resolve against the rig's declared dt-includes list."""
    tag = f"{rig.name}_{inst.name}_{dev_label}_{prop_name}"
    if resolve_token(raw, rig.dt_includes, workdir, tag) is not None:
        return
    if not rig.dt_includes:
        diags.error(
            "lang-dt-include",
            f"instance '{inst.name}': device '{dev_label}' property "
            f"'{prop_name}' assigns '{raw}', which does not resolve — this "
            "rig declares no dt-includes: at all; add the header that "
            f"defines '{raw}'",
            [ref])
        return
    diags.error(
        "lang-dt-include",
        f"instance '{inst.name}': device '{dev_label}' property "
        f"'{prop_name}' assigns '{raw}', which does not resolve against "
        f"this rig's declared dt-includes ({', '.join(rig.dt_includes)}) — "
        f"add the header that defines it to {rig.name}.yml dt-includes:",
        [ref])


def _check_dt_includes(rig: Rig, workdir: str, diags) -> None:
    """Rule 6: every declared dt-includes: header must exist and
    preprocess cleanly on its own, checked once per rig regardless of
    whether any parameter ends up resolving against it."""
    for i, (header, ref) in enumerate(zip(rig.dt_includes, rig.dt_includes_refs)):
        detail = check_include(header, workdir, f"{rig.name}_{i}")
        if detail is not None:
            diags.error(
                "lang-dt-include",
                f"rig '{rig.name}': dt-includes header '{header}' not "
                f"found or fails to preprocess (searched {ZEPHYR_INC}, "
                f"{MODULE_INC})\n{detail}",
                [ref])


def _parse_wire(item: _Val, by_name, diags) -> Wire | None:
    frm = _resolve_dotted(item.v.get("from"), by_name, "from", diags)
    to = _resolve_dotted(item.v.get("to"), by_name, "to", diags)
    route_v = item.v.get("route")
    if frm is None or to is None or route_v is None:
        if route_v is None:
            diags.error("lang-schema", "wire: required key 'route' is missing",
                        [item.src])
        return None
    if isinstance(route_v.v, dict):
        via_v = route_v.v.get("via")
        if via_v is None:
            diags.error("lang-schema",
                        "wire: route is a mapping but names no 'via' key",
                        [route_v.src])
            return None
        route = via_v.v   # position NAME; analyzer maps to index
    else:
        route = route_v.v
    return Wire(frm=frm, to=to, route=route, src=item.src)


def _resolve_dotted(ref_v: _Val | None, by_name, key, diags) -> WireEnd | None:
    """<instance>.<node> — the candidate-2 reference syntax (Conv. 5 #2)."""
    if ref_v is None:
        diags.error("lang-schema", f"wire: required key '{key}' is missing")
        return None
    ref = ref_v.v
    if not isinstance(ref, str) or "." not in ref:
        diags.error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' is not an <instance>.<node> reference",
            [ref_v.src])
        return None
    inst_name, _, node_name = ref.partition(".")
    inst = by_name.get(inst_name)
    if inst is None:
        diags.error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' — no instance named '{inst_name}' in this rig\n"
            f"instances: {', '.join(sorted(by_name))}",
            [ref_v.src])
        return None
    hits = inst.shield.by_name(node_name)
    if not hits:
        diags.error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' — shield '{inst.shield.name}' has no node "
            f"'{node_name}'\n"
            f"referencable nodes of '{inst.shield.name}': {', '.join(inst.shield.names())}",
            [ref_v.src])
        return None
    if len(hits) > 1:
        diags.error(
            "lang-wire-ref",
            f"wire {key}: '{ref}' is ambiguous within shield '{inst.shield.name}' "
            f"({len(hits)} matches)", [ref_v.src])
        return None
    return WireEnd(instance=inst, node=node_name, src=ref_v.src)
