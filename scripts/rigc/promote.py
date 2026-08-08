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

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml

from .loader.library import load_shield_library
from .loader.params import device_required_params
from .model import Shield


@dataclass(frozen=True)
class ShieldInfo:
    """One name `discover_shields` found -- a folder carrying `<name>.
    shield` (loader/library.py's own discovery marker, the single
    authority for "is this a shield at all"). `template` is shield.yml's
    own `template:` flag, ruling 5's PROMOTABLE authority, read
    independently of library.py (which parses shield.yml only for its
    `revisions:` axis -- Sec 4's two-authorities-on-purpose split).
    `has_yml` distinguishes "no shield.yml at all" from "shield.yml
    present but omits the flag" -- the two reasons `check_promotable`'s
    error tells apart."""

    name: str
    dir: str
    template: bool
    has_yml: bool


def discover_shields(shield_dirs: Optional[List[str]] = None,
                     ) -> Dict[str, ShieldInfo]:
    """Every name loader/library.py's own scan discovers -- a `<name>.
    shield` marker file present -- keyed by name. Reuses that scan
    verbatim (`load_shield_library`) rather than a second glob, so a name
    this module calls a shield and a name the expander can actually
    resolve `shield:` against never disagree.

    `template` is read separately, straight off shield.yml (never parsed
    by library.py itself, which stops at `revisions:`): `False` for a
    shield without a shield.yml (`has_yml=False`) or one whose shield.yml
    omits the flag (`has_yml=True`). Reuses `lib.ymls` (library.py's own
    record of which discovered names carry a shield.yml) rather than
    re-probing the filesystem for the same fact a second time.

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
    block) are discarded here: they concern a shield's REVISION axis,
    orthogonal to the promotability question this function answers, and
    the real corpus carries none today. Returns a dict the caller owns."""
    lib, _diags, _deps = load_shield_library(
        "<rigc-promote-discovery-unused>", shield_dirs)
    out: Dict[str, ShieldInfo] = {}
    for name, pending in lib.pending.items():
        has_yml = name in lib.ymls
        template = False
        if has_yml:
            with open(lib.ymls[name]) as f:
                doc = yaml.safe_load(f) or {}
            template = bool((doc.get("shield") or {}).get("template"))
        out[name] = ShieldInfo(name=name, dir=pending.shield_dir,
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
_PROMOTION_OPTS = ("socket",)


def parse_promotion_opts(opts: Optional[str], target: str,
                         ) -> Union[Dict[str, str], str]:
    """Parse the `:`-separated assignment list a promotion target may
    carry -- `<shield>[@rev][:<key>=<value>[:<key>=<value>...]]` -- into
    a mapping of instance fields for the ONE desugared instance.

    Returns the mapping, or an ERROR MESSAGE string when the text does
    not parse (the same return convention `check_promotable` uses, so a
    caller handles both refusals the same way). `None`/empty opts is an
    empty mapping, never an error.

    EXPLICIT `key=value` ONLY, with no bare-word shorthand for the
    common case (Tobi, 2026-08-08, decision 3): `flash_click:quail_sock1`
    is refused, not read as a socket. A positional rule would have to be
    re-litigated the moment a second option lands.

    `:` separates, NOT `,` -- and that is a hard constraint, not a
    preference: real devicetree property names contain commas
    (`zephyr,code` is exactly the property the two param-blocked shields
    need), so a comma-separated list could never carry the parameter
    syntax this grammar is designed to grow into."""
    if not opts:
        return {}
    parsed: Dict[str, str] = {}
    for assignment in opts.split(":"):
        key, sep, value = assignment.partition("=")
        if not sep:
            return (f"'{target}': promotion option '{assignment}' is not "
                    f"'<key>=<value>' -- promotion options are explicit "
                    f"assignments (known keys: "
                    f"{', '.join(_PROMOTION_OPTS)})")
        if key not in _PROMOTION_OPTS:
            return (f"'{target}': unknown promotion option '{key}' "
                    f"(known keys: {', '.join(_PROMOTION_OPTS)})")
        if key in parsed:
            return (f"'{target}': promotion option '{key}' given more "
                    f"than once")
        if not value:
            return (f"'{target}': promotion option '{key}=' has an empty "
                    f"value")
        parsed[key] = value
    return parsed


def promote_shield(name: str, revision: Optional[str] = None,
                   socket: Optional[str] = None) -> PromotedRig:
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

    Pure over its two string arguments: no filesystem, no promotability
    or namespace decision (the caller's job, via `check_promotable`,
    before this ever runs). Returns a PromotedRig the caller owns."""
    shield_ref = f"{name}@{revision}" if revision else name
    rig_yml = f"rig:\n  name: {name}\n"
    content = ("instances:\n"
              f"  - name: {name}\n"
              f"    shield: {shield_ref}\n")
    if socket is not None:
        content += f"    socket: {socket}\n"
    return PromotedRig(rig_yml=rig_yml, content_name=f"{name}.yml", content=content)


def check_promotable(name: str, info: ShieldInfo, variant: Optional[str],
                     ) -> Optional[str]:
    """Whether `name` -- already known to `discover_shields` (`info` is
    its own entry, read-only to this call) -- may be promoted at all, in
    the order a user's own target string is checked: a `/variant` names
    an axis a promoted shield does not have (Sec 3's ruling: `@rev` is
    the shield's own revision, and that is the only axis a promoted
    shield has to select from), then `template: true` (ruling 5's
    promotability gate, Sec 4), naming whichever of the two ways a shield
    falls short of it -- missing shield.yml entirely, or one that omits
    the flag.

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
