# Slice brief — CUTOVER: rigc becomes the tool, and the goldens stop being bytes

Drafted 2026-07-30 by the driver, after R5 landed (`380f69c`, differential
**146/146**, conformance complete). Inputs: `rigc-mission-brief.md` §3
(the banner finding) and §5, `rigc-r1-brief.md` §3 (the anchor rule,
designed for exactly this move), the R0 harness record, Tobi's direction
2026-07-30b — *"the goldens have served their purpose but they become a
burden to stay byte-identical for the next design iterations"* — and a
fresh census the driver ran at `380f69c` (every count below was measured,
not recalled).

**Status: RATIFIED by Tobi 2026-07-30b**, except §8.2 (overlay comparator
strength), which is OPEN and under discussion. Ratified as recommended:
§8.1 comparators BEFORE the tool-identity refreeze (C1 move → C2
comparators → C3 retire → C4 discipline); §8.3 exit vocabulary collapses
to 0/1/2; §8.4 the knob survives with default `rigc`, its banner
normalization deleted; §8.5 `fail_under` set as part of C2; §8.6 C1/C3 on
sonnet with driver-verified zero-churn claims, C2 split per artifact
class with a review round each.

**§8.2 RESOLVED 2026-07-30b — the SPLIT CONTRACT.** Both options the
first draft offered were impossible: `dts_equiv.py` cannot parse a
`rig-gen.overlay` at all (measured — `DTError: expected '/dts-v1/;' at
start of file`; the overlay is a fragment with a cpp `#include`,
unresolved macros, and `&label` references defined only in the board DT),
and a bespoke comparator would mean reimplementing cpp + board-label
resolution. Ratified instead: (1) overlay SEMANTICS ride the existing
`zephyr.dts` + `dts_equiv` comparison, which is post-resolution and
strictly stronger; (2) the overlay's IRREDUCIBLE contracts — the ones
that vanish on resolution — get targeted assertions: verbatim/unresolved
param tokens (`<INPUT_KEY_0>` must NOT be a bare number; `zephyr.dts`
shows only the resolved value so it structurally cannot prove this), the
quoted `#include "rig-gen-includes.dtsi"` as first line, and the
human-facing position/pinctrl comments; (3) **add a tier-2 build for
`shield-uart-subset-frdm`** — the only accept rig with an overlay golden
but no `zephyr.dts`, which would otherwise lose its semantic check
entirely. Consequence accepted knowingly: overlay semantics become
build-marked only, with `tests/unit/emitter/` carrying the fast
rendering checks.

**C3/C4 DECISIONS RATIFIED 2026-07-30b:** (1) the five `rigexp`-importing
integration modules (`test_connector_bindings`, `test_controller_label`,
`test_edt_build`, `test_board_read`, `test_resolved_corpus`) get AUDITED
against rigc's unit equivalents — redundant ones are DELETED, only the
rest ported (note `rigexp.diag.Diagnostics` has no rigc counterpart by
design, so porting means rewriting call shape, and
`test_connector_bindings` is the one expected to survive since it
validates production connector content). (2) `west.yml` keeps a PIN,
moved to the current branch tip — the five carried commits are not
upstream and that branch already rebased once, silently invalidating a
differential run; tracking the branch again is a separate later decision.
(3) The `rigexp-` workdir prefix and `<RIGEXP_WORKDIR>` placeholder are
BOTH renamed, accepting a deliberate one-file `stderr.txt` refreeze
(`<RIGEXP_BUILD>`'s 18 `zephyr.dts` goldens are free — verified
`dts_equiv`-only, never byte-diffed, and dtlib discards comments).
(4) Layer markers are DROPPED: directory decides the layer, `build`
survives as the only marker, and `-m unit` becomes
`pytest scripts/rigc/tests/unit` — an explicit workflow swap to record,
not silent breakage.

**C1 LAYOUT REQUIREMENT, driver-verified before dispatch (2026-07-30b):**
fixtures must land at `scripts/rigc/tests/fixtures/` — DEPTH PRESERVED.
`anchor_path()` renders relative to the `scripts/<module>/` component, so
that path yields `tests/fixtures/...`, byte-identical to what all 48
reject goldens carry. Putting them under `tests/integration/fixtures/`
instead yields `tests/integration/fixtures/...` and churns every one of
them. Measured, both ways, before the slice was dispatched.

## Goal

rigc is the tool: the frozen suite and its fixtures live in
`scripts/rigc/tests/`, rigexp is gone, `west.yml` is un-pinned, and the
test suite asserts **each artifact's actual contract** instead of its
bytes — so the queued design work stops paying a refreeze tax for
changes that alter no behavior.

## 0. Why now, measured rather than asserted

Byte-identity had exactly one job: being the oracle for the differential.
R5 finished it. What remains is cost, and it is concentrated in the queue:

- **BRIDLE MIGRATION** is the sharp one. The eager scan makes RIG_DEPENDS
  O(shield-tree size), so importing a 19-folder shield library rewrites
  every corpus rig's `context.cmake`. Measured today: `lotus_buttons`
  lists **14** `.shield` files for a rig naming **2**.
- **LAZY SHIELD LIBRARY** is the burden in pure form: zero user-visible
  semantic change, blocked only by frozen deps lists and frozen
  scan-time diagnostic order.
- **`rig-gen.overlay`'s label scheme is explicitly parked-and-provisional**
  (R10; `emitter/overlay.py`'s own docstring says so) — the most
  expensive artifact to refreeze is one already meant to change.
- **hwmv2 revision semantics**, **rig-schema.yaml** (`additionalProperties:
  false` adds rejections that shift existing diagnostics) and **shield
  plurality** (`RIG_SHIELDS`) each churn goldens incidentally.

**The suite already contains the answer.** `dts_equiv.py` decided long ago
that for the resolved devicetree, labels/phandle numbers/ordering are not
the contract, and compares structure. Cutover extends that principle to
the other artifact classes — each on its own terms, because each has a
different real contract.

## 1. The ordering law

**Nothing loosens while rigexp is the oracle.** A weaker comparator during
the differential could let a genuine rigc divergence through undetected.
That window closed with R5; it must not be reopened by doing C1 and C2
in one commit.

Second law, from T0b/T0c: **a loosened comparator must first be proven to
accept the CURRENT bytes.** Land each comparator with the goldens
unchanged and the suite still green. A comparator that accepts today's
goldens is provably no weaker than the one it replaces. Only after that
does golden *content* become free to change.

## 2. C1 — the move (zero golden churn, and that is the acceptance)

`scripts/rigexp/tests/` → `scripts/rigc/tests/`: `conftest.py` (679
lines), the 10 test modules (3594 lines total), `fixtures/`, `goldens/`.
`git mv`, so history follows.

**The anchor rule makes this byte-inert, and the driver verified it
rather than trusting the design note.** `diag.anchor_path()`
(`scripts/rigc/diag.py:84`) renders any path under a `scripts/<module>/`
component relative to that component. Measured on a real golden:
`goldens/route-no-via/stderr.txt` reads
`at tests/fixtures/boards/rigs/route-no-via/route-no-via.yml:17` — no
module name in it. Moving `scripts/rigexp/tests/fixtures/...` to
`scripts/rigc/tests/fixtures/...` yields the identical string, so **none
of the 48 reject goldens' anchor lines churn.** This is precisely what
R1 §3 ratified the module-agnostic rule for; cutover is where it pays.

Also in C1: `conftest.py`'s own path constants, `check.sh`'s pytest
paths, `pyproject.toml` (`[tool.coverage.*]` source/omit, any testpaths).
Nothing else.

**⚠ THE MOVE RETIRES THE DIFFERENTIAL, unavoidably** (driver finding
2026-07-30b, mid-C1; this corrects an impossible criterion in the first
draft). rigexp's anchor rule (`rigexp/diag.py:17-26`) is
`relpath(path, ROOT)` against rigexp's OWN package dir, returning the
path unchanged when the result starts with `..`. With fixtures under
`scripts/rigc/`, rigexp therefore renders anchors ABSOLUTE while the
goldens carry `tests/fixtures/...` — measured: **43 reject goldens
mismatch**. The module-agnostic anchor rule was ratified for **rigc
only**; rigexp is frozen and never received it. So the suite cannot be
green in the rigexp direction after C1, at any fixture location that
also satisfies rigc. Consequently the ratified §8.4 default flip
(`RIG_EXPAND_COMPILE` → `rigc`: `cmake/dts.cmake:147` + conftest's
constant) MOVES INTO C1 — it is what the move requires, not a C3 nicety.
rigexp stays on disk until C3 but stops being runnable against the suite
here. Acceptable only because R5 already completed conformance (the
oracle's job is done), and recorded as a deliberate step rather than a
side effect. Side effect to expect: with the default now `rigc`,
`conftest._normalize_banner` becomes ACTIVE, which is what keeps the 58
banner-carrying accept goldens matching.

**Acceptance: `git diff` touches ZERO golden bytes** (`git diff --stat --
'*/goldens/*'` empty; renames only) and the DEFAULT run — now rigc — is
146 green. The rigexp direction is expected-red from C1 onward: run it
once, record the number and its cause.

## 3. C2 — the comparator re-basing (the design work)

Per artifact class, because the contract differs per class:

| artifact | today | contract, and therefore the comparator |
|---|---|---|
| `exit_code` | bytes | **the integer.** Keep byte-exact. |
| `zephyr.dts` (18) | `dts_equiv.py` structural | already right. Unchanged. |
| `rig-gen.overlay` (19) | bytes | **the devicetree it denotes.** Structural — frees formatting, node/property ordering, and the parked R10 label scheme. `dts_equiv.py` is the precedent and possibly the tool. |
| `context.cmake` (19) | bytes | **a parsed key→value mapping** consumed by `dts.cmake`. Compare keys and values; `RIG_DEPENDS` as a **SET**, with must-contain / must-not-contain assertions. This alone unblocks the lazy shield library. |
| `config-sheet.md` (19) | bytes | **human prose.** Assert the FACTS it must carry (this instance on this socket, this address, this CS index, this strap state) — never the rendering. The clearest mis-application of byte-freezing in the suite. |
| `rig-gen-includes.dtsi` (1) | bytes | the include list. Set of headers, order as declared. |
| `stderr.txt` (48) | bytes | **see §4 — the one that earned its keep.** |

**Acceptance, per comparator, in this order:**

1. Land it with **goldens unchanged**; suite green under the default
   (rigexp). Proves no-weaker.
2. Then **delete `_normalize_banner`** (`conftest.py:228`) and run
   `RIG_EXPAND_COMPILE=rigc`: still 146. This proves the new comparators
   genuinely tolerate honest tool identity, with no normalization
   propping them up — and it is the step that may retire the entire
   banner refreeze (§8.1).
3. Record, per class, one deliberate NEGATIVE control: a mutation the new
   comparator must still reject (reorder two properties → overlay
   comparator accepts; change an address → it rejects). A comparator
   nobody proved can still fail is the tautological-test defect at suite
   scale — R5's review caught exactly that shape in a unit test, and the
   same discipline applies here.

## 4. What must NOT loosen

**The reject corpus's diagnostic wording.** Tobi's ratified position
(2026-07-28) kept 40 reclassified tests precisely because they *"freeze
user-facing diagnostic wording, a real contract"* — the message a rig
author reads IS the product surface. That ruling stands and this brief
does not reopen it.

What *is* separable inside those 48 goldens:

- **Diagnostic IDENTITY** — category, anchor, which input rejects, and
  ordering — stays hard, byte-exact.
- **PROSE** wants a cheap blessing path, not a loosened comparator: a
  wording improvement should be one reviewed refreeze of the affected
  messages, not a reason to stop comparing text.

Also unchanged: `exit_code`, and the rule that a refreeze is always a
reviewed, classified diff (never `RIGEXP_REFREEZE` run casually).

## 5. C3 — retire rigexp

- Delete `scripts/rigexp/` (production only; its tests already moved in
  C1). It has not been edited since the freeze and R5 proved it
  reproducible.
- `west.yml:29` — un-pin `revision:` from `8da5b3a0f60` back to
  `tskr/zephyr-rigs`. The pin's own comment says "un-pin back to the
  branch name at rigc cutover".
- **Flip `RIG_EXPAND_COMPILE`'s default to `rigc`** —
  `cmake/dts.cmake:142-149` and `conftest.py:184`. Recommendation: KEEP
  the knob (one cmake var + one test constant; it is the seam that made
  this mission possible, and cheap insurance for any future
  re-implementation), but delete the banner normalization it carried.
  R0's design record says how to re-add that if ever needed.
- **Workdir prefix**: `scripts/rigc/cli.py:173` still uses
  `prefix="rigexp-"` because `conftest.py:186`'s `_WORKDIR_RE` hardcodes
  `/tmp/rigexp-`. Rename both to `rigc-` together. Golden impact is
  ONE file (only 1 golden contains `<RIGEXP_WORKDIR>`).
- **Placeholder names**: `<RIGEXP_WORKDIR>` (1 golden) and
  `<RIGEXP_BUILD>` (18 goldens, the `zephyr.dts` provenance comments).
  19 files, mechanical, one class — and under C2's structural
  comparators the `zephyr.dts` 18 may not need touching at all.
- **Retire `unimplemented.py`** and the unreachable
  `raise Unimplemented` in `cli.py:221`. Exit vocabulary then becomes
  0/1/2, matching rigexp's — see ruling §8.3.
- `check.sh`: `targets="scripts/rigexp scripts/rigc"` → `scripts/rigc`.

## 6. C4 — merge the two discipline regimes

They currently **contradict each other**, which is why rigc's tests run
as a separate pytest invocation (`rigc-r1-brief.md` §5):

- `scripts/rigexp/tests/test_marker_discipline.py:27` REQUIRES every
  collected test to carry a layer marker (`unit`/`integration`) plus
  `build` where it builds.
- `scripts/rigc/tests/unit/test_layer_discipline.py:110`
  (`test_no_pytest_markers_in_the_tree`) FORBIDS markers — rigc
  classifies by DIRECTORY.

Markers cannot simply be abolished: `check.sh`'s `CHECK_FAST=1` path
runs `pytest -m "not build"`. The natural merge, which this brief
proposes: **directory classification decides the layer**
(`tests/unit/` vs `tests/integration/`); `build` survives as a marker on
the integration side only; the rigc rule narrows to "no markers under
`tests/unit/`"; the rigexp rule narrows to "every `tests/integration/`
test that runs a build is `build`-marked". Both enforcement tests
survive, each scoped to its own half.

**Keep the two pytest invocations even so**, for a reason independent of
markers: coverage is measured over the in-process unit layer only. The
integration suite drives rigc as a SUBPROCESS, so folding it into the
coverage run dilutes the number with work coverage cannot see — the
original T3 finding, still true after cutover.

## 7. Acceptance (whole cutover)

A. Suite 146 green at every slice boundary, and `check.sh` ALL GREEN
   with its exit code read DIRECTLY (never through a pipe into `tail` —
   that reports tail's status; it hid a failing gate for a full cycle
   during R5).
B. C1: zero golden bytes changed. C2: goldens unchanged, plus the
   negative controls of §3.3 recorded. C3: no `scripts/rigexp/` on disk
   and the suite still green.
C. Purge `__pycache__` before any verification run that follows a
   mutate-and-restore: a size-preserving edit restored within the same
   second leaves bytecode Python considers valid (memory
   `reference_stale_pyc_same_second`; it cost a cycle in R5).
D. Each slice its own commit. **The tool-identity refreeze must never
   share a commit with a comparator change** — mixing them makes neither
   diff reviewable, and a refreeze is only trustworthy when its diff is
   mechanically classifiable into one class.
E. `west.yml` un-pinned only in C3, and one full suite run AFTER the
   un-pin against the branch tip — the pin existed so that any red
   golden was ours by construction, and removing it re-admits upstream
   drift as a cause.

## 8. Needs Tobi's ratification

1. **Slice ORDER — and this may delete a work item.** Driver recommends
   **C1 move → C2 comparators → C3 retire → C4 discipline**, i.e.
   comparators BEFORE the tool-identity refreeze, inverting the order the
   old handoff assumed. Reasoning: every artifact carrying the banner is
   a *comment* (`/* */`, `<!-- -->`, `#`), so once the overlay /
   context.cmake / config-sheet comparators stop comparing raw text, the
   banner stops mattering — and the **58-file banner refreeze may
   disappear entirely** rather than being performed and verified. A
   refreeze you do not have to do beats one you classify mechanically.
   The measured class it would retire: 19 `rig-gen.overlay` + 19
   `config-sheet.md` + 19 `context.cmake` + 1 `rig-gen-includes.dtsi` =
   **58 files across 19 accept dirs** (no reject golden carries the
   banner — verified). Against: it delays rigexp's retirement, so the two
   implementations coexist for one slice longer.
2. **Comparator strength for `rig-gen.overlay`** — reuse `dts_equiv.py`
   (proven, already trusted for `zephyr.dts`, ignores comments and
   ordering) or write a narrower overlay-specific comparator? Driver
   leans `dts_equiv.py`: a second comparator with subtly different rules
   is how two oracles start disagreeing.
3. **Exit vocabulary after retiring `unimplemented.py`**: collapse to
   0/1/2 (matching rigexp, one less concept) or keep 3 reserved? Driver
   recommends collapse — exit 3 existed so a differential red could never
   be mistaken for a wrong diagnostic, and there is no differential
   after cutover.
4. **Does the knob survive?** Driver recommends keeping
   `RIG_EXPAND_COMPILE` with default `rigc` and deleting only its banner
   normalization (§5). Against: with rigexp gone it has no second value
   to take, which is the definition of speculative.
5. **`fail_under` — now genuinely due.** As the goldens loosen, the unit
   layer becomes the PRIMARY correctness evidence rather than a
   supplement, so the still-open ruling gets more consequential, not
   less. Today: 89% total, `sheet.py` 59%, `overlay.py` 77%. Recommend
   setting it as part of C2, at a floor at or just below today's number,
   because that is the slice that shifts the evidentiary burden.
6. **Implementor/reviewer split.** C1 and C3 are mechanical (sonnet, with
   the driver verifying the zero-churn claims independently — they are
   the whole acceptance). C2 is design work and the driver recommends it
   be split per artifact class, each with its own review round, rather
   than one large slice: the comparators are exactly where a too-weak
   assertion would be invisible.
