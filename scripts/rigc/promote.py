# SPDX-License-Identifier: Apache-2.0
"""S3a's own unit (board-coordinate-s3-brief.md, parent ruling 5/6): the
`--rig <shield>` desugaring and the namespace rule that decides when a
bare name resolves as a shield at all -- everything `west rigs --explain`
(west_commands/rigs.py) needs, factored so the printer stays a thin
caller over pure values.

Three things, matching the brief's own split (Sec 7):

  promote_shield()   -- the natural mapping a -> [a] (ruling 4), PURE: a
                        shield name (+ optional revision) -> the rig.yml/
                        content-file TEXT a checked-in rig meaning the
                        same thing would have to contain.
  discover_shields() -- the IO edge: which names ARE shields at all,
                        reusing loader/library.py's OWN scan verbatim
                        (never a second glob restating it, so
                        "resolvable by the expander" and "known here"
                        cannot drift apart) -- plus, per shield.yml, its
                        `template:` flag, the SECOND authority ruling 5
                        assigns to PROMOTABLE (Sec 4: two facts about one
                        thing, on purpose, tied together by this module's
                        own census test).
  check_promotable() / both_paths_error() -- the promotability gate (Sec
                        4) and the namespace rule's "both" branch (Sec
                        5), pure decisions over already-discovered facts.

No cmake, no cpp, no board: printing a promoted shield's two documents
needs none of rigc's heavier machinery -- `promote_shield` never touches
a filesystem. `rigc.loader.load` is what PROVES the printed text is real
(the round-trip test, criterion 2.2); this module never imports it.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from .diag import SourceRef
from .loader.library import load_shield_library
from .loader.params import device_required_params
from .model import Shield


@dataclass(frozen=True)
class ShieldInfo:
    """One name `discover_shields` found -- a rig template
    (`loader/library.py`'s own `pending`) or a legacy shield whose
    shield.yml merely declares metadata (never a `<name>.shield` marker
    of its own kind that library.py resolves against). `template` is
    THIS entry's own `template:` flag, ruling 5's PROMOTABLE authority --
    since plurality (shield-plurality-brief.md), a name's OWN entry
    carries this flag, not its folder's, so two names sharing one folder
    may answer differently. `has_yml` distinguishes "no shield.yml at
    all" from "shield.yml present but omits the flag" -- the two reasons
    `check_promotable`'s error tells apart."""

    name: str
    dir: str
    template: bool
    has_yml: bool


def discover_shields(shield_dirs: Optional[List[str]] = None,
                     ) -> Dict[str, ShieldInfo]:
    """Every name `loader/library.py`'s own scan discovers, keyed by
    name -- every resolvable rig template (`lib.pending`) UNION every
    name any shield.yml under `shield_dirs` declares (`lib.ymls`), since
    a legacy shield with metadata but no matching `<name>.shield` is
    still a name `check_promotable` must be able to name and explain
    (shield-plurality-brief.md Sec 3's third consequence). Reuses that
    ONE scan verbatim (`load_shield_library`) rather than a second glob,
    so a name this module calls a shield and a name the expander can
    actually resolve `shield:` against never disagree; `template` reads
    `lib.promotable` -- the same per-entry `template:` flag the scan
    already read off shield.yml -- rather than re-opening any file this
    module's own caller already paid to parse.

    `shield_dirs` defaults to the vendored shield library
    (`load_shield_library`'s own default), which is narrower than the rig
    namespace a caller resolves against: `west rigs` finds rigs under EVERY
    module board root, so a caller comparing the two namespaces must pass
    the matching `<root>/boards/shields` list, or a shield in another
    module is invisible here and the both-a-rig-and-a-shield collision
    goes undetected. A root with no `boards/shields` simply contributes
    nothing. The scan's `workdir` argument
    is never touched by a scan that resolves nothing -- no `.resolve()`
    call happens here -- so an inert placeholder is passed rather than
    creating a real temporary directory for what is a read-only query.

    Discovery-time diagnostics (a malformed shield.yml `revisions:`
    block, a `template: true` entry with no matching `<name>.shield`)
    are discarded here: they concern a shield's own template/axis shape,
    orthogonal to the promotability question this function answers, and
    a caller that actually loads a rig (never this function alone) is
    what surfaces them. Returns a dict the caller owns."""
    lib, _diags, _deps = load_shield_library(
        "<rigc-promote-discovery-unused>", shield_dirs)
    out: Dict[str, ShieldInfo] = {}
    for name in set(lib.pending) | set(lib.ymls):
        has_yml = name in lib.ymls
        shield_dir = (lib.pending[name].shield_dir if name in lib.pending
                     else os.path.dirname(lib.ymls[name]))
        template = lib.promotable.get(name, False) if has_yml else False
        out[name] = ShieldInfo(name=name, dir=shield_dir,
                               template=template, has_yml=has_yml)
    return out


@dataclass(frozen=True)
class PromotedRig:
    """The two documents `promote_shield` synthesizes, plus the content
    file's own NAME -- returned together so a caller never re-derives the
    filename from the rig name itself (documents.content_file_name's own
    convention, restated here in text form since `promote_shield` is pure
    and takes no rig directory to build a real path from). Every string
    is newline-terminated; copied verbatim into
    `boards/rigs/<name>/rig.yml` and `boards/rigs/<name>/<content_name>`
    respectively, the two files load through `rigc.loader.load` with no
    diagnostics given a board (criterion 2.2; the printed rig.yml
    declares no board of its own, so an INJECTED one is what a real
    build -- or this module's own round-trip test -- supplies) -- that
    is this dataclass's whole contract."""

    rig_yml: str
    content_name: str
    content: str


#: The promotion options a target string may carry after `:`. A CLOSED
#: set, deliberately (Tobi, 2026-08-08, decision 2): `socket` alone to
#: start, everything else later. Two names are excluded on purpose rather
#: than merely absent -- `name`, because S4's singleton identity law pins
#: the desugared instance name to the shield name and that name reaches
#: config-sheet.md, so a CLI slot for it would let a user break the law
#: from the command line; and `shield`, which is the target itself.
#:
#: A key containing a literal `.` is never a member of this tuple, and
#: never will be: it is a `<device>.<prop>` parameter assignment, a
#: DIFFERENT grammar category reached by different syntax (see
#: `ParsedPromotionOpts`), not a new fixed keyword growing this set.
_PROMOTION_OPTS = ("socket",)


@dataclass(frozen=True)
class ParsedPromotionOpts:
    """A parsed promotion target's `:`-separated assignment list, split
    into its two grammar categories: `fixed`, the closed `_PROMOTION_OPTS`
    keywords (today just socket), and `params`, every `<device>.<prop>=
    <value>` assignment -- device label -> property name -> value, the
    identical shape `Instance.params` (model.py) already carries, so
    `promote_shield` can print it with the SAME structure a real rig.yml's
    own params: block already uses. A flat `Dict[str, str]` cannot hold
    both without overloading one key namespace with two unrelated
    meanings, so the two live in separate fields rather than one mapping.

    Both are fresh dicts the caller owns."""
    fixed: Dict[str, str]
    params: Dict[str, Dict[str, str]]


def parse_promotion_opts(opts: Optional[str], target: str,
                         ) -> Union[ParsedPromotionOpts, str]:
    """Parse the `:`-separated assignment list a promotion target may
    carry -- `<shield>[@rev][:<key>=<value>[:<key>=<value>...]]` -- into
    a `ParsedPromotionOpts` for the ONE desugared instance.

    Returns the parsed opts, or an ERROR MESSAGE string when the text
    does not parse (the same return convention `check_promotable` uses,
    so a caller handles both refusals the same way). `None`/empty opts
    parses to an empty `ParsedPromotionOpts`, never an error.

    EXPLICIT `key=value` ONLY, with no bare-word shorthand for the
    common case (Tobi, 2026-08-08, decision 3): `flash_click:quail_sock1`
    is refused, not read as a socket. A positional rule would have to be
    re-litigated the moment a second option lands.

    `:` separates, NOT `,` -- and that is a hard constraint, not a
    preference: real devicetree property names contain commas
    (`zephyr,code` is exactly the property the two param-blocked shields
    need), so a comma-separated list could never carry the parameter
    syntax this grammar is designed to grow into.

    A key containing a literal `.` is routed to `params` instead of
    checked against `_PROMOTION_OPTS`: split on the FIRST dot only
    (`str.partition`, never `str.split`) into a device label and a
    property name, everything after the first dot -- dots included --
    staying part of the property name. Devicetree property names may
    legally contain a literal `.` themselves (rare, but the grammar does
    not forbid it); shield-local device labels in this corpus never do,
    so the first dot is always the real boundary between the two."""
    if not opts:
        return ParsedPromotionOpts(fixed={}, params={})
    fixed: Dict[str, str] = {}
    params: Dict[str, Dict[str, str]] = {}
    for assignment in opts.split(":"):
        key, sep, value = assignment.partition("=")
        if not sep:
            return (f"'{target}': promotion option '{assignment}' is not "
                    f"'<key>=<value>' -- promotion options are explicit "
                    f"assignments (known keys: "
                    f"{', '.join(_PROMOTION_OPTS)})")
        if "." in key:
            dev_label, _, prop_name = key.partition(".")
            if not dev_label or not prop_name:
                return (f"'{target}': promotion parameter '{key}' is not "
                        f"'<device>.<prop>=<value>' -- both the device "
                        f"label and the property name must be non-empty")
            if prop_name in params.get(dev_label, {}):
                return (f"'{target}': parameter '{dev_label}.{prop_name}' "
                        f"given more than once")
            if not value:
                return (f"'{target}': promotion parameter '{key}=' has an "
                        f"empty value")
            params.setdefault(dev_label, {})[prop_name] = value
            continue
        if key not in _PROMOTION_OPTS:
            return (f"'{target}': unknown promotion option '{key}' "
                    f"(known keys: {', '.join(_PROMOTION_OPTS)})")
        if key in fixed:
            return (f"'{target}': promotion option '{key}' given more "
                    f"than once")
        if not value:
            return (f"'{target}': promotion option '{key}=' has an empty "
                    f"value")
        fixed[key] = value
    return ParsedPromotionOpts(fixed=fixed, params=params)


def promote_shield(name: str, revision: Optional[str] = None,
                   socket: Optional[str] = None,
                   params: Optional[Dict[str, Dict[str, str]]] = None,
                   ) -> PromotedRig:
    """The natural mapping `a -> [a]` (ruling 4), written out: a rig.yml
    with NO `board:` (a promoted rig's board reaches it only by
    INJECTION, per Sec 3's own symmetry argument -- and, since
    board-coordinate-s6-brief.md Sec 11 retired the grammar entirely,
    `board:` is no longer something ANY rig.yml could declare, promoted
    or persisted) and a content file
    with exactly one instance, socket-LESS BY DEFAULT (the Sec 4.2
    unique-by-type inference resolves it board-agnostically at analysis
    time, once a board is actually in play).

    `socket`, when given, emits `socket: <label>` on that instance and
    inference never runs for it. This is what makes a shield promotable
    onto a board carrying MORE THAN ONE socket of its type, where
    inference is right to refuse: measured 2026-08-08, four mikrobus
    shields (eth_click, flash_click, temp_click, temp_hum_click) could
    not be promoted onto mikroe_quail at all, because quail offers four
    mikrobus sockets and the desugared instance named none of them.

    The label is BOARD-SPECIFIC (`quail_sock1`, not `mikrobus`), and
    that is correct rather than a regression of S5: S5 moved board-
    specific labels out of CONTENT, which must stay portable. An
    invocation already names the board -- it is the one place a
    board-specific label belongs. This function does not check that the
    label exists on the board; that is the analyzer's job, and it
    already renders the candidates (error[phys-socket]).

    The instance is named after THE SHIELD ITSELF, never a placeholder
    like "inst": instance names reach config-sheet.md
    (emitter/sheet.py:48, a C2b-compared fact), so a checked-in rig this
    desugaring is ever compared against (S4's singleton identity law)
    must use the identical name.

    `revision`, when given, desugars to `shield: <name>@<revision>` --
    the SHIELD's own revision axis; rig.yml is unaffected, since a
    promoted rig has no revision axis of its own to declare. This
    function never checks whether `revision` is actually declared by the
    shield -- that validation belongs to `rigc.loader.load`, the one
    place a shield's `revisions:` axis is already read; duplicating it
    here would be a second authority for the same fact.

    `params`, when given (device label -> property name -> value, the
    identical shape `ParsedPromotionOpts.params`/`Instance.params` both
    carry), prints one `params:` block onto the same instance, in the
    SAME shape any authored rig.yml already uses (4-space `params:`,
    6-space device label, 8-space `<prop>: <value>`). This function
    performs NO validation of its own against device or property
    existence, declared-parameter membership, or token resolution --
    the printed text flows through the identical `rigc.loader.load`
    path every promoted document already goes through (`PromotedRig`'s
    own contract, above), which is the one place those facts are
    already checked; a second check here would be a second authority
    for facts the loader already owns. An empty or absent mapping omits
    the block entirely, matching params-less promotion exactly as
    before.

    Pure over its arguments: no filesystem, no promotability or
    namespace decision (the caller's job, via `check_promotable`,
    before this ever runs). Returns a PromotedRig the caller owns."""
    shield_ref = f"{name}@{revision}" if revision else name
    rig_yml = f"rig:\n  name: {name}\n"
    content = ("instances:\n"
              f"  - name: {name}\n"
              f"    shield: {shield_ref}\n")
    if socket is not None:
        content += f"    socket: {socket}\n"
    if params:
        content += "    params:\n"
        for dev_label, props in params.items():
            content += f"      {dev_label}:\n"
            for prop_name, value in props.items():
                content += f"        {prop_name}: {value}\n"
    return PromotedRig(rig_yml=rig_yml, content_name=f"{name}.yml", content=content)


def shield_is_multiplug(shield: Shield) -> bool:
    """Whether `shield` declares more than one plug (multi-plug-shield-
    brief.md ruling 4): the eligibility predicate `check_promotable`'s
    plurality gate applies, and the singleton-identity-law census's own
    domain split reads directly -- never a hand-listed shield name, so
    the day promotion of a plural shield lands, this predicate (and every
    set it feeds) shrinks on its own. Pure: `shield` is read-only."""
    return len(shield.plugs) > 1


def resolve_for_promotion(name: str, shield_dirs: Optional[List[str]] = None,
                          ) -> Optional[Shield]:
    """Resolve `name`'s own template -- the IO edge a promotability check
    reaches for when it needs a fact `discover_shields`'s cheap scan does
    not carry (its own plug count, `shield_is_multiplug`): a SEPARATE,
    small parse from `discover_shields`'s own scan, on purpose, since
    that scan is deliberately lazy (module docstring, `loader/
    library.py`) and answering "is this shield plural" needs the
    template's actual plug nodes.

    Returns the resolved Shield, or None when resolution fails for any
    reason (an unknown name, a malformed template) -- the caller's own
    subsequent `check_promotable`/`promote_shield`/`loader.load` call is
    what surfaces the real diagnostic; this function exists only to
    answer the plug-count question cheaply and is not itself a
    diagnostic source. The caller owns the returned Shield.

    Unlike `discover_shields`'s own inert placeholder workdir, this
    function actually PARSES the template (cpp + dtlib), so it needs a
    real scratch directory -- a fresh `TemporaryDirectory`, removed
    before this returns (D10: no workdir left behind for a query)."""
    with tempfile.TemporaryDirectory(prefix="rigc-promote-plug-count-") as workdir:
        lib, _diags, _deps = load_shield_library(workdir, shield_dirs)
        shield, _diags2, _deps2 = lib.resolve(
            name, "promotion plug-count probe", SourceRef("<promote>", 0))
        return shield


def check_promotable(name: str, info: ShieldInfo, variant: Optional[str],
                     plug_count: int = 1) -> Optional[str]:
    """Whether `name` -- already known to `discover_shields` (`info` is
    its own entry, read-only to this call) -- may be promoted at all, in
    the order a user's own target string is checked: a `/variant` names
    an axis a promoted shield does not have (Sec 3's ruling: `@rev` is
    the shield's own revision, and that is the only axis a promoted
    shield has to select from), then `template: true` (ruling 5's
    promotability gate, Sec 4), naming whichever of the two ways a shield
    falls short of it -- missing shield.yml entirely, or one that omits
    the flag -- then plurality (ruling 4, multi-plug-shield-brief.md Sec
    6): a shield plugging more than one socket has no single `:socket=`
    slot to promote onto, a separate future slice's own design question.
    `plug_count` is the caller's own `len(shield.plugs)` of the resolved
    template (`resolve_for_promotion`) -- defaults to 1 (no plurality
    gate) for a caller that has not resolved the shield at all, so this
    check stays backward-compatible for anything not yet threading it.

    Returns an error message naming why promotion is refused, or None
    when `promote_shield` may run. Pure: makes no filesystem call of its
    own."""
    if variant is not None:
        return (f"'{name}/{variant}': a promoted shield has no variant "
                "axis to select from -- '@rev' is the only axis it "
                "promotes with, and it selects the SHIELD's own "
                "revision, never a rig variant")
    if not info.template:
        missing = ("no shield.yml" if not info.has_yml else
                   "shield.yml does not declare 'template: true'")
        return (f"shield '{name}' is discoverable but not promotable to "
                f"a rig -- {missing}")
    if plug_count > 1:
        return (f"shield '{name}' plugs {plug_count} sockets -- "
                "multi-plug shields cannot be promoted (yet)")
    return None


def shield_declares_required_params(shield: Shield) -> bool:
    """Whether ANY device of `shield` declares a `shield,params` name with
    no authored default -- `params.device_required_params` applied across
    every device, never re-derived a second time (a second hand-rolled
    copy of "declared, no default" is a review finding). This is the S4
    singleton-law census's own eligibility predicate (board-coordinate-
    s4-brief.md Sec 2.3): a shield this returns True for can never be
    promoted, because a promoted rig's content file has no `params:` slot
    to satisfy `params.check_param_invariant` with (Sec 9.6's CLI grammar,
    still unruled) -- `check_promotable` does not itself gate on this (it
    only gates on `template:`/`@variant`, ruling 5), so a caller building
    the LAW's own domain applies this separately, over an already-resolved
    Shield (not a bare name -- resolving one needs the shield library's
    own lazy parse, `ShieldLibrary.resolve`, which this module's `promote_
    shield` deliberately never touches).

    Pure: makes no filesystem call of its own; shield is read-only."""
    return any(device_required_params(dev) for dev in shield.devices)


def both_paths_error(name: str, rig_dir: Path, shield_dir: str) -> str:
    """The Sec 5 namespace rule's third branch, spelled out: `name`
    matches BOTH a persisted rig folder and a discovered shield -- ruled
    an error rather than a guess, the same tie-break discipline Sec 4.2's
    socket inference already refuses to make between two equally
    plausible candidates.

    BOTH paths are real, DISCOVERED ones, never constructed from `name`:
    `rig_dir` is list_rigs.find_rigs's own Rig.dir and `shield_dir` is
    ShieldInfo.dir, straight off library.py's scan. A message that told
    the user to go look at a path nobody had actually found would be
    wrong for any shield outside the vendored library -- exactly the
    cross-module case that makes a name collide in the first place.

    Pure: builds a message from its three arguments alone."""
    return (f"'{name}' names both a rig ({rig_dir}) and a shield "
            f"({shield_dir}) -- rename one; a name that is both "
            "is ambiguous by construction, never guessed between")
