"""Params, pins, dt-includes vocabulary -- closing R2's ShieldRef
deferrals (rigc-r3-brief.md Sec 5). Ported value-shaped from
rigexp/loader_yml.py's `_apply_params_block`/`_check_param_invariant`/
`_check_restate`/`_apply_pin_block`/`_check_param_token`/
`_check_dt_includes`.

Every function here takes the NARROW values it needs (a shield, a params:
Val, a dt-includes list, a rig NAME) rather than a whole `Rig` or
`Instance` (mission brief Sec 6, rule 2 -- "whole-model inputs where a
value would do"): the caller (loader/delta.py) already holds these pieces
and assigns the result onto a freshly constructed Instance, matching its
own no-mutation discipline.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..deps import Deps, touch, union
from ..diag import Diagnostic, SourceRef, error
from ..dtsio import (MODULE_INC, check_include, is_int_literal,
                    resolve_token, zephyr_inc)
from ..model import Shield, Strap
from .documents import Val


def check_param_invariant(instances) -> List[Diagnostic]:
    """The per-stage invariant (rule 2, re-checked fresh after EVERY delta
    stage): every instance's EFFECTIVE shield/params must have every
    declared, no-default-authored parameter ASSIGNED. Covers all three
    sources of a parameter-set change (a base assignment, a shield swap,
    a shield REVISION introducing a new requirement) with no special
    casing, since it only ever looks at the CURRENT shield + CURRENT
    params.

    Returns one error per required-but-unassigned parameter; instances
    are read-only."""
    diags: List[Diagnostic] = []
    for inst in instances:
        shield = inst.shield
        assigned = inst.params
        refs = (inst.src,) if inst.src is not None else ()
        for dev in shield.devices:
            pset = assigned.get(dev.label, {})
            for pname in dev.declared_params:
                if pname in pset:
                    continue
                if any(name == pname for name, _ in dev.extra_props):
                    continue      # shield authored a default; may be omitted
                diags.append(error(
                    "lang-param",
                    f"instance '{inst.name}': device '{dev.label}' of "
                    f"shield '{shield.name}' declares '{pname}' as "
                    "required (shield,params, no default authored) but "
                    f"this instance does not assign it — add params: "
                    f"{{{dev.label}: {{{pname}: <value>}}}}",
                    refs))
    return diags


def check_param_token(raw: str, dt_includes: List[str], rig_name: str,
                      workdir: str, tag: str, inst_name: str, dev_label: str,
                      prop_name: str, ref: SourceRef,
                      include_dirs: Optional[List[str]] = None,
                      ) -> List[Diagnostic]:
    """Rules 4/5: an assigned token that is not a bare integer literal
    must resolve against the rig's declared dt-includes list.

    Returns the resolution findings -- empty when the token resolves;
    inputs are read-only."""
    if resolve_token(raw, dt_includes, workdir, tag, include_dirs) is not None:
        return []
    if not dt_includes:
        return [error(
            "lang-dt-include",
            f"instance '{inst_name}': device '{dev_label}' property "
            f"'{prop_name}' assigns '{raw}', which does not resolve — "
            "this rig declares no dt-includes: at all; add the header "
            f"that defines '{raw}'",
            (ref,))]
    return [error(
        "lang-dt-include",
        f"instance '{inst_name}': device '{dev_label}' property "
        f"'{prop_name}' assigns '{raw}', which does not resolve against "
        f"this rig's declared dt-includes ({', '.join(dt_includes)}) — "
        f"add the header that defines it to {rig_name}.yml dt-includes:",
        (ref,))]


def apply_params_block(params_v: Optional[Val], inst_name: str, shield: Shield,
                       dt_includes: List[str], rig_name: str, workdir: str,
                       tag_prefix: str,
                       unknown_device_context: Optional[str] = None,
                       include_dirs: Optional[List[str]] = None,
                       ) -> Tuple[Dict[str, Dict[str, str]],
                                 Dict[str, Dict[str, SourceRef]],
                                 List[Diagnostic]]:
    """Parse ONE params: block -- the base assignment, OR a delta's
    wholesale replacement -- into (params, param_refs, diagnostics), a
    PURE function of its inputs: never mutates the Instance it describes,
    the caller assigns the result onto a freshly constructed one. Rules
    1/3 (undeclared property / unknown device) fire immediately against
    the CURRENT shield; rules 4/5 (token resolution) too. Rule 2 (every
    required parameter assigned) is deliberately NOT checked here -- it
    is the per-stage invariant, run once per stage over every instance,
    since a LATER stage may still supply what an EARLIER one left
    required-but-unassigned.

    `unknown_device_context`, if given, is folded into rule 3's message
    when it fires (rule 12): a family-wide revision's params naming a
    device the POST-VARIANT shield does not have is unavoidable by
    construction whenever a variant already substituted the shield.

    Returns (params, refs, diagnostics): fresh dicts the caller owns;
    nothing handed in is touched."""
    if params_v is None:
        return {}, {}, []
    diags: List[Diagnostic] = []
    params: Dict[str, Dict[str, str]] = {}
    param_refs: Dict[str, Dict[str, SourceRef]] = {}
    devices_by_label = {d.label: d for d in shield.devices}
    for dev_label, props_v in params_v.value.items():
        dev = devices_by_label.get(dev_label)
        if dev is None:
            context = f" ({unknown_device_context})" if unknown_device_context else ""
            diags.append(error(
                "lang-param",
                f"instance '{inst_name}': params names no device "
                f"'{dev_label}' of shield '{shield.name}'{context}\n"
                f"devices of '{shield.name}': "
                f"{', '.join(sorted(devices_by_label)) or 'none'}",
                (props_v.src,)))
            continue
        for prop_name, val_v in props_v.value.items():
            if prop_name not in dev.declared_params:
                diags.append(error(
                    "lang-param",
                    f"instance '{inst_name}': device '{dev_label}' of "
                    f"shield '{shield.name}' declares no parameter "
                    f"'{prop_name}' (shield,params)\n"
                    f"declared parameters of '{dev_label}': "
                    f"{', '.join(dev.declared_params) or 'none'}",
                    (val_v.src,)))
                continue
            raw = str(val_v.value)
            params.setdefault(dev_label, {})[prop_name] = raw
            param_refs.setdefault(dev_label, {})[prop_name] = val_v.src
            if not is_int_literal(raw):
                tag = f"{tag_prefix}_{dev_label}_{prop_name}"
                diags += check_param_token(
                    raw, dt_includes, rig_name, workdir, tag, inst_name,
                    dev_label, prop_name, val_v.src, include_dirs)
    return params, param_refs, diags


def apply_pin_block(pin_v: Optional[Val], inst_name: str, shield: Shield,
                    ) -> Tuple[Dict[str, int], Dict[str, SourceRef],
                              Dict[str, object], Dict[str, SourceRef],
                              List[Diagnostic]]:
    """pin: {config-element-name: value} -- shared by the base parse and
    a delta's instances: patch (which resets pins/jumpers first, so this
    always starts from empty when called from a patch). PURE: returns
    fresh dicts, never mutates an Instance.

    Returns (pins, pin_refs, jumpers, jumper_refs, diagnostics), all
    fresh values the caller owns."""
    pins: Dict[str, int] = {}
    pin_refs: Dict[str, SourceRef] = {}
    jumpers: Dict[str, object] = {}
    jumper_refs: Dict[str, SourceRef] = {}
    diags: List[Diagnostic] = []
    if pin_v is None:
        return pins, pin_refs, jumpers, jumper_refs, diags
    for cfg_name, val_v in pin_v.value.items():
        # resolution rule: pin keys name a config element (strap OR
        # routing jumper) WITHIN the named shield
        elem = (shield.config_element(cfg_name.replace("_", "-"))
               or shield.config_element(cfg_name))
        if elem is None:
            names = sorted(list(shield.straps) + list(shield.jumpers))
            diags.append(error(
                "lang-pin",
                f"instance '{inst_name}': pin names no config element "
                f"'{cfg_name}' of shield '{shield.name}'\n"
                f"config elements of '{shield.name}': "
                f"{', '.join(names) or 'none'}",
                (val_v.src,)))
            continue
        if isinstance(elem, Strap):
            pins[elem.name] = val_v.value
            pin_refs[elem.name] = val_v.src
        else:                                   # Jumper: position value
            jumpers[elem.name] = val_v.value
            jumper_refs[elem.name] = val_v.src
    return pins, pin_refs, jumpers, jumper_refs, diags


def check_restate(params_v: Val, prior_params: Dict[str, Dict[str, str]],
                  inst_name: str) -> List[Diagnostic]:
    """Rule 11: if a delta supplies params for an instance whose shield it
    does NOT change, it must RESTATE every property the effective
    topology had already assigned; omitting one is an error naming it --
    otherwise wholesale replace means a silent revert to the shield
    default. Called with the PRIOR params (before the wholesale replace
    clears them).

    Returns one error per property omitted from the restatement;
    prior_params is read-only."""
    restated = {
        (dev_label, prop_name)
        for dev_label, props_v in params_v.value.items()
        for prop_name in props_v.value
    }
    diags: List[Diagnostic] = []
    for dev_label, props in prior_params.items():
        for prop_name in props:
            if (dev_label, prop_name) not in restated:
                diags.append(error(
                    "lang-param",
                    f"instance '{inst_name}': this delta supplies params "
                    f"for device '{dev_label}' without restating "
                    f"'{prop_name}', which the effective topology already "
                    "assigns -- wholesale replace means omitting it "
                    "silently reverts to the shield default; restate it "
                    "explicitly or remove it deliberately",
                    (params_v.src,)))
    return diags


def check_dt_includes(rig_name: str, dt_includes: List[str],
                      dt_includes_refs: List[SourceRef], workdir: str,
                      include_dirs: Optional[List[str]] = None,
                      ) -> Tuple[List[Diagnostic], Deps]:
    """Rule 6: every declared dt-includes: header must exist and
    preprocess cleanly on its own, checked once per rig regardless of
    whether any parameter ends up resolving against it.

    Returns (diagnostics, deps): one diagnostic per header that is
    missing or fails to preprocess, empty when all resolve; deps is the
    UNION of every real file each declared header's own preprocess
    opened (dtsio.check_include), recorded for EVERY header regardless
    of whether its own check passed -- a rig's declared token vocabulary
    is a real dependency of that rig even on the header that currently
    fails, since that header is exactly the one an author is about to
    edit. Inputs are read-only; the caller owns the returned Deps."""
    diags: List[Diagnostic] = []
    deps: Deps = frozenset()
    searched = ", ".join([*(include_dirs or []), zephyr_inc(), MODULE_INC])
    for i, (header, ref) in enumerate(zip(dt_includes, dt_includes_refs)):
        detail, files = check_include(header, workdir, f"{rig_name}_{i}", include_dirs)
        deps = union(deps, *(touch(f) for f in files))
        if detail is not None:
            diags.append(error(
                "lang-dt-include",
                f"rig '{rig_name}': dt-includes header '{header}' not "
                f"found or fails to preprocess (searched {searched})\n"
                f"{detail}",
                (ref,)))
    return diags, deps
