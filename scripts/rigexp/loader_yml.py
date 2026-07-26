"""Candidate-2 loader: rig.yml (YAML/DTS hybrid) -> rig model.

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
  rig.dt-includes       list of headers (as written in a DTS #include
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
                        applying the declared default for a bare target
  <rigname>_<variant>.yml / <rigname>_<rev>.yml -- delta fragments (V1b):
                        board:/sockets: (variant only), instances: (shallow
                        replace, matched by name), add-instances:,
                        remove-instances:, add-wires:/remove-wires:
                        (matched by endpoint pair), dt-includes: (unions),
                        params: (wholesale replace + restate-check).
                        Resolution order is base -> variant -> revision;
                        the per-instance-parameter invariant is re-checked
                        after every stage.

Source locations come from YAML composer marks (line-accurate), so the
comparison against dtlib file:line quality is fair.
"""
from __future__ import annotations

import glob
import os

import yaml

from .ctypes_registry import load_types
from .diag import Depends, Diagnostic, Diagnostics, LoadError, SrcRef
from .dtsio import (MODULE_INC, MODULE_ROOT, ZEPHYR_INC, check_include,
                    is_int_literal, parse_tu, resolve_token, source_files)
from .model import AxisDecl, Instance, Rig, Shield, Strap, Wire, WireEnd
from .shields import parse_shields

# The vendored default shield library (direct API / test use only — see
# load_shield_library below): this module's OWN boards/shields, the real
# location it ships alongside this package.
SHIELDS_DIR = os.path.join(MODULE_ROOT, "boards", "shields")


def load_shield_library(workdir: str, diags: Diagnostics,
                        shield_dirs: list[str] | None = None,
                        deps: Depends | None = None) -> dict[str, Shield]:
    """Load every shield template. Each .shield file is its OWN translation
    unit (Ground rule 3), so labels are shield-scoped — two shields may reuse
    gl_plug etc. without colliding, and no cross-shield prefix discipline is
    needed. Merged by shield name (which is unique).

    Shields live one per folder, upstream-shield-shape: <shield-dir>/<name>/
    <name>.shield (alongside that folder's shield.yml metadata, not parsed
    here — the .shield DT node name remains the sole identity source, per
    Shield.name = node.name in shields.py). We therefore look for exactly
    <dir>/<dir-basename>.shield per subfolder, rather than a */*.shield
    glob — the folder now also holds upstream-convention Kconfig fragments
    (Kconfig.shield, Kconfig.defconfig), which also end in the literal
    substring ".shield" and would otherwise be mis-globbed as shield
    templates (Kconfig.shield matches a bare *.shield wildcard). This
    <name>.shield-presence check is also what self-filters a shields
    directory: legacy (non-rig) shields ship a <name>.overlay, not a
    .shield, so scanning a whole boards/shields tree picks up ONLY rig
    templates and silently skips the rest.

    shield_dirs is a LIST of shield-library roots (each a boards/shields
    directory), unioned into one library — because rig shield templates are
    ordinary discoverable content that may live in ANY board_root of ANY
    Zephyr module, not just this one. The build system (dts.cmake) derives the
    list from BOARD_ROOT, exactly as list_shields.py does; None falls back to
    the vendored default (SHIELDS_DIR), used only by direct API / tests.

    deps, if given, records every .shield file this call parses, plus (via
    dtsio.source_files) whatever real files each one's translation unit
    #includes — the temp workdir the TU is synthesized in is excluded,
    since it holds a generated file with no counterpart in the source
    tree."""
    types = load_types(deps)
    shields = {}
    directories = shield_dirs if shield_dirs is not None else [SHIELDS_DIR]
    for directory in directories:
        for shield_dir in sorted(glob.glob(os.path.join(directory, "*"))):
            if not os.path.isdir(shield_dir):
                continue
            name = os.path.basename(shield_dir)
            f = os.path.join(shield_dir, name + ".shield")
            if not os.path.isfile(f):
                continue
            if deps is not None:
                deps.see(f)
            dt = parse_tu([f], workdir, f"shield-{name}.dts")
            if deps is not None:
                for src in source_files(dt, workdir):
                    deps.see(src)
            shields.update(parse_shields(dt, types, diags))
    return shields


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

def _parse_axis_decl(rig_v: _Val, key: str, diags) -> AxisDecl | None:
    """rig.yml's revisions:/variants: declaration block (rig-variants-
    revisions.md V1a): {default:, list: []}. Absent key -> no axis declared
    (None). Shape is validated strictly here: list: must be non-empty, and
    default: (if given) must be one of its own members -- both are
    lang-schema, like every other malformed-shape error this loader reports,
    since they are defects of rig.yml itself, not of a particular
    selection."""
    axis_v = rig_v.v.get(key)
    if axis_v is None:
        return None
    list_v = axis_v.v.get("list")
    values = [str(v.v) for v in list_v.v] if list_v is not None else []
    if not values:
        diags.error("lang-schema",
                    f"rig {key}: 'list' must be a non-empty list",
                    [axis_v.src])
        return None
    default_v = axis_v.v.get("default")
    if default_v is None:
        return AxisDecl(values=values)
    default = str(default_v.v)
    if default not in values:
        diags.error(
            "lang-schema",
            f"rig {key}: default '{default}' is not one of the declared "
            f"values ({', '.join(values)})",
            [default_v.src])
        return None
    return AxisDecl(values=values, default=default)


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
                or os.path.isfile(os.path.join(rig_dir, defconfig))):
            diags.error(
                "lang-variant",
                f"rig '{rig.name}': variant '{rig.variant}' contributes "
                f"nothing -- looked for {overlay}, {defconfig} and {delta}, "
                "none exist",
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
    """Parse ONE <rigname>_<variant|rev>.yml delta fragment (rig-variants-
    revisions.md V1b Sec. 5): a FLAT top-level mapping -- unlike the base
    file, there is no `rig:` wrapper, since a delta is a document about the
    base topology, not a rig identity of its own. board:/sockets:/
    instances:/add-instances:/remove-instances:/add-wires:/remove-wires:/
    dt-includes:/params (the restate-check) all live at this top level."""
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


def _apply_instance_patch(item: _Val, inst: Instance, shields, rig: Rig,
                          workdir: str, diags, stage: str, stage_value: str,
                          resolve_socket) -> None:
    """Shallow-replace an EXISTING instance's top-level keys (Sec. 5): a
    GIVEN key REPLACES; an unspecified key INHERITS. shield/socket/invert/
    pin/params are each the deepest merge unit -- no key merges into what
    was there before, it wholesale replaces it. When shield changes, the
    OLD params are keyed to the OLD shield's devices and are therefore
    meaningless against the new one, so they are dropped rather than
    carried forward (Sec. 5's reasoning for why wholesale replace is
    REQUIRED, not merely acceptable)."""
    shield_changed = False
    if "shield" in item.v:
        shield_v = item.v["shield"]
        shield = shields.get(shield_v.v)
        if shield is None:
            diags.error(
                "lang-instance-shield",
                f"instance '{inst.name}': unknown shield '{shield_v.v}'\n"
                f"known shields: {', '.join(sorted(shields))}",
                [shield_v.src])
            return
        inst.shield = shield
        shield_changed = True
        inst.params = {}
        inst.param_refs = {}

    if "socket" in item.v:
        inst.socket = resolve_socket(item.v["socket"].v)

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


def _apply_delta(delta_v: _Val, stage: str, stage_value: str, rig: Rig,
                 shields, effective: dict[str, Instance], order: list[str],
                 wires: list[Wire], removed_by: dict[str, str],
                 workdir: str, diags) -> None:
    """Apply ONE delta stage (Sec. 5) onto the effective topology IN PLACE.
    `stage` is "variant" or "revision" (rules 5-9 differ only in which
    fragment kind may carry board:/sockets:, and in the diagnostic code);
    `stage_value` is the selected axis value itself, folded into rule-8/12
    wording so drift cannot hide."""
    code = "lang-variant" if stage == "variant" else "lang-rev"
    doc = delta_v.v

    # board:/sockets: -- VARIANT fragments only (rule 5).
    if "board" in doc:
        if stage != "variant":
            diags.error(
                code,
                f"rig '{rig.name}': the {stage} '{stage_value}' fragment "
                "carries board:, a VARIANT-only key",
                [doc["board"].src])
        else:
            # Legal in the vocabulary, but rejected until board resolution
            # itself reads deltas: list_rigs.py resolves the board BEFORE any
            # fragment loads, and cmake sets BOARD from that answer, so
            # applying an override here would leave the model's board (and
            # the overlay header and context.cmake's RIG_BOARD derived from
            # it) disagreeing with the board pass 1 actually read and pass 2
            # actually builds. A loud rejection beats a silent
            # inconsistency; lift this once the resolver reads deltas.
            diags.error(
                code,
                f"rig '{rig.name}': variant '{stage_value}' carries board:, "
                "which is not yet wired into board resolution -- the board "
                "is resolved before any fragment is read, so an override "
                "here would silently disagree with the board actually "
                "built. Use a separate rig until this is supported.",
                [doc["board"].src])

    socket_map: dict[str, str] = {}
    if "sockets" in doc:
        if stage != "variant":
            diags.error(
                code,
                f"rig '{rig.name}': the {stage} '{stage_value}' fragment "
                "carries sockets:, a VARIANT-only key",
                [doc["sockets"].src])
        else:
            socket_map = {k: v.v for k, v in doc["sockets"].v.items()}

    def resolve_socket(value: str) -> str:
        return socket_map.get(value, value)

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
            _apply_instance_patch(item, inst, shields, rig, workdir, diags,
                                  stage, stage_value, resolve_socket)

    # add-instances: -- full declarations; the name must NOT already exist
    # (rule 7).
    add_v = doc.get("add-instances")
    if add_v is not None:
        for item in add_v.v:
            new_inst = _parse_instance(item, shields, rig, workdir, diags)
            if new_inst is None:
                continue
            if "socket" in item.v:
                new_inst.socket = resolve_socket(item.v["socket"].v)
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
    shields = load_shield_library(workdir, diags, shield_dirs, deps)

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
    board_v = _require(rig_v, "board", "rig", diags)
    if name_v is None or board_v is None:
        return None
    rig = Rig(name=name_v.v, board=board_v.v, src=rig_v.src)

    # Qualifier axes: declare (shape-validated), resolve the SELECTED value
    # for each (rules 1-4). rig.revision/rig.variant exist for validation
    # and provenance (context.cmake, build_info) regardless of whether a
    # delta engine ever runs below.
    rig.revisions = _parse_axis_decl(rig_v, "revisions", diags)
    rig.variants = _parse_axis_decl(rig_v, "variants", diags)
    _check_axis_collision(rig, rig_v.src, diags)
    rig.revision = _resolve_axis(rig.name, "revision", "revisions",
                                 rig.revisions, revision, rig_v.src, diags)
    rig.variant = _resolve_axis(rig.name, "variant", "variants",
                                rig.variants, variant, rig_v.src, diags)

    # V1b delta fragments: looked up by the SAME constructed stems rule 10
    # checks, built from rig.revision/rig.variant alone -- never ${RIG},
    # per THE TRAP. Loaded (not yet APPLIED) here, before rule 10 (an
    # existing .yml counts as "contributes something") and before
    # dt-includes union (a delta's own vocabulary must be known before ANY
    # params get token-validated, including the base's own).
    rig_dir = os.path.dirname(rig_path)
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
    _union_dt_includes(rig, rig_v.v.get("dt-includes"))
    if variant_delta_v is not None:
        _union_dt_includes(rig, variant_delta_v.v.get("dt-includes"))
    if revision_delta_v is not None:
        _union_dt_includes(rig, revision_delta_v.v.get("dt-includes"))
    if rig.dt_includes:
        _check_dt_includes(rig, workdir, diags)

    # Stage 0: base topology. The per-stage invariant (rule 2) is checked
    # PER INSTANCE, immediately after each is parsed -- exactly the order
    # V1a used, so the 13 axis-less corpus rigs see byte-identical
    # diagnostics (no delta ever selected for them, so nothing below this
    # comment ever runs for them beyond this loop).
    effective: dict[str, Instance] = {}
    order: list[str] = []
    insts_v = _require(rig_v, "instances", "rig", diags)
    for item in (insts_v.v if insts_v else []):
        inst = _parse_instance(item, shields, rig, workdir, diags)
        if inst:
            effective[inst.name] = inst
            order.append(inst.name)
            _check_param_invariant([inst], diags)

    wires: list[Wire] = []
    for item in rig_v.v.get("wires", _Val([], rig_v.src)).v:
        wire = _parse_wire(item, effective, diags)
        if wire:
            wires.append(wire)

    removed_by: dict[str, str] = {}

    # Stage 1: variant delta.
    if variant_delta_v is not None:
        assert rig.variant is not None    # a delta only loads for a selected axis
        _apply_delta(variant_delta_v, "variant", rig.variant, rig, shields,
                     effective, order, wires, removed_by, workdir, diags)
        _check_param_invariant(effective.values(), diags)

    # Stage 2: revision delta -- ONE family-wide stream, applied AFTER the
    # variant (Q9); per-variant streams stay deferred (rule 12).
    if revision_delta_v is not None:
        assert rig.revision is not None   # a delta only loads for a selected axis
        _apply_delta(revision_delta_v, "revision", rig.revision, rig, shields,
                     effective, order, wires, removed_by, workdir, diags)
        _check_param_invariant(effective.values(), diags)

    rig.instances = [effective[n] for n in order if n in effective]
    rig.wires = wires
    return rig


def _parse_instance(item: _Val, shields, rig: Rig, workdir: str, diags) -> Instance | None:
    name_v = _require(item, "name", "instance", diags)
    shield_v = _require(item, "shield", "instance", diags)
    socket_v = _require(item, "socket", "instance", diags)
    if not (name_v and shield_v and socket_v):
        return None

    shield = shields.get(shield_v.v)
    if shield is None:
        diags.error(
            "lang-instance-shield",
            f"instance '{name_v.v}': unknown shield '{shield_v.v}'\n"
            f"known shields: {', '.join(sorted(shields))}",
            [shield_v.src])
        return None

    inst = Instance(name=name_v.v, shield=shield, socket=socket_v.v, src=item.src)
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
        "add the header that defines it to rig.yml dt-includes:",
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
