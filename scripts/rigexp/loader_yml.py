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


def _check_axis_collision(rig: Rig, src: SrcRef, diags) -> None:
    """Rule 4: a variant name equal to a declared revision id -- the
    constructed fragment filenames would collide (both axes join as
    <rigname>_<id>...), so this is checked once, independent of what a
    particular target selects."""
    if rig.variants is None or rig.revisions is None:
        return
    collision = sorted(set(rig.variants.values) & set(rig.revisions.values))
    if collision:
        diags.error(
            "lang-variant",
            f"rig '{rig.name}': variant name(s) {', '.join(collision)} "
            "collide with a declared revision id -- the constructed "
            "fragment filenames (<rigname>_<id>...) would be ambiguous "
            "between the two axes",
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


def _check_fragment_presence(rig: Rig, rig_dir: str, src: SrcRef, diags) -> None:
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

    V1a's only fragment kinds are .overlay/_defconfig (collected by the
    cmake fork); the .yml delta fragment is V1b, not checked here."""
    if rig.variant is not None and not (
            rig.variants is not None and rig.variant == rig.variants.default):
        overlay = f"{rig.name}_{rig.variant}.overlay"
        defconfig = f"{rig.name}_{rig.variant}_defconfig"
        if not (os.path.isfile(os.path.join(rig_dir, overlay))
                or os.path.isfile(os.path.join(rig_dir, defconfig))):
            diags.error(
                "lang-variant",
                f"rig '{rig.name}': variant '{rig.variant}' contributes "
                f"nothing -- looked for {overlay} and {defconfig}, neither "
                "exists",
                [src])
    if rig.revision is not None and not (
            rig.revisions is not None
            and rig.revision == rig.revisions.default):
        defconfig = f"{rig.name}_{rig.revision}_defconfig"
        if not os.path.isfile(os.path.join(rig_dir, defconfig)):
            diags.error(
                "lang-rev",
                f"rig '{rig.name}': revision '{rig.revision}' contributes "
                f"nothing -- looked for {defconfig}, which does not exist",
                [src])


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

    # V1a qualifier axes: declare (shape-validated), resolve the SELECTED
    # value for each (rules 1-4), then check the selection actually
    # contributes a fragment (rule 10). No delta engine yet, so nothing
    # below this depends on rig.revision/rig.variant -- they exist purely
    # for validation and provenance (context.cmake, build_info).
    rig.revisions = _parse_axis_decl(rig_v, "revisions", diags)
    rig.variants = _parse_axis_decl(rig_v, "variants", diags)
    _check_axis_collision(rig, rig_v.src, diags)
    rig.revision = _resolve_axis(rig.name, "revision", "revisions",
                                 rig.revisions, revision, rig_v.src, diags)
    rig.variant = _resolve_axis(rig.name, "variant", "variants",
                                rig.variants, variant, rig_v.src, diags)
    if rig.revision is not None or rig.variant is not None:
        _check_fragment_presence(rig, os.path.dirname(rig_path), rig_v.src, diags)

    # dt-includes: parsed and header-validated (rule 6) BEFORE instances, so
    # every params: assignment resolved while parsing instances below has an
    # already-known-good vocabulary to resolve against.
    dt_includes_v = rig_v.v.get("dt-includes")
    if dt_includes_v is not None:
        for h_v in dt_includes_v.v:
            rig.dt_includes.append(h_v.v)
            rig.dt_includes_refs.append(h_v.src)
        _check_dt_includes(rig, workdir, diags)

    by_name: dict[str, Instance] = {}
    insts_v = _require(rig_v, "instances", "rig", diags)
    for item in (insts_v.v if insts_v else []):
        inst = _parse_instance(item, shields, rig, workdir, diags)
        if inst:
            rig.instances.append(inst)
            by_name[inst.name] = inst

    for item in rig_v.v.get("wires", _Val([], rig_v.src)).v:
        wire = _parse_wire(item, by_name, diags)
        if wire:
            rig.wires.append(wire)
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

    pin_v = item.v.get("pin")
    if pin_v is not None:
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

    _parse_params(item, inst, shield, rig, workdir, diags)
    return inst


def _parse_params(item: _Val, inst: Instance, shield: Shield, rig: Rig,
                  workdir: str, diags) -> None:
    """rig params: — per-instance property assignment (rig-variants-
    revisions.md "PER-INSTANCE PARAMETERS"): keyed by shield-local DEVICE
    LABEL (the same addressing style pin: uses for config elements), then
    by property name. Validates rules 1-5; rule 6 (dt-includes header
    existence) was already checked once for the whole rig, before any
    instance was parsed."""
    devices_by_label = {d.label: d for d in shield.devices}
    params_v = item.v.get("params")
    if params_v is not None:
        for dev_label, props_v in params_v.v.items():
            dev = devices_by_label.get(dev_label)
            if dev is None:
                diags.error(
                    "lang-param",
                    f"instance '{inst.name}': params names no device "
                    f"'{dev_label}' of shield '{shield.name}'\n"
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

    # rule 2: every device's REQUIRED (declared, no shield-authored default)
    # parameter must be assigned by THIS instance — checked for every device
    # of the shield, not just ones params: happens to mention.
    for dev in shield.devices:
        assigned = inst.params.get(dev.label, {})
        for pname in dev.declared_params:
            if pname in assigned:
                continue
            if any(name == pname for name, _ in dev.extra_props):
                continue      # shield authored a default; the rig may omit it
            diags.error(
                "lang-param",
                f"instance '{inst.name}': device '{dev.label}' of shield "
                f"'{shield.name}' declares '{pname}' as required "
                "(shield,params, no default authored) but this instance "
                f"does not assign it — add params: {{{dev.label}: "
                f"{{{pname}: <value>}}}}",
                [inst.src])


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
