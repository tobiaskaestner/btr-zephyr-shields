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
from typing import Dict, List, Optional

import yaml

from .loader.library import load_shield_library


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


def promote_shield(name: str, revision: Optional[str] = None) -> PromotedRig:
    """The natural mapping `a -> [a]` (ruling 4), written out: a rig.yml
    with NO `board:` (legal only when a board is INJECTED -- S1 relaxed
    `resolve_board`'s "never neither" to "never neither unless injected",
    never to "never required at all"; a promoted rig's board reaches it
    only that way, per Sec 3's own symmetry argument) and a content file
    with exactly one instance, socket-LESS (the Sec 4.2 unique-by-type
    inference resolves it board-agnostically at analysis time, once a
    board is actually in play).

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
