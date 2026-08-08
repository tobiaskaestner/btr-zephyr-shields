# S6 — strict symmetry: the board leaves rig.yml

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md`
§9.4 (ruling 7) and §9.5 step 6. **This is the LAST step of §9.5** — with
it, board-as-coordinate is complete.

Prerequisites, all landed: S1 (`462e5c6`, injection wins over
declaration), S2 (`ee52739`, `--boards-for` — promoted to a prerequisite
precisely because it is what enumeration BECOMES once declaration is
gone), S3/S4, and S5 (`03a6928`, content off board-prefixed labels).

## 1. What this slice is

§9.4's stated TARGET, reached:

> **`board:` leaves rig.yml entirely.** A rig describes a topology; the
> invocation supplies the board. Variants return to topology alternates
> only.

The argument that motivated the whole direction: a promoted shield has no
board, so out of symmetry a persisted rig should not declare one either.
S1 inverted step 1's authority (injection wins, declaration became a
default); S6 removes the default.

## 2. Scope — counted, not estimated

- **18 real `board:` keys across 17 rig.yml files** (comments containing
  the token excluded — a naive grep counts 19 and is wrong).
- **16 files carry one top-level `board:`.** `ard_datalogger` carries
  **two, one per variant** — it is the ONLY per-variant case. (§9.4 says
  "three times"; that is wrong, it is twice.)
- **`pilot_variants` is ALREADY the target shape**: a single top-level
  `board:` plus a bare `variants: list: [variant_a, variant_b,
  variant_c]` — topology alternates with no per-variant board. Only its
  `board:` line goes; **its variants survive untouched.**
- So "variants collapse to topology alternates only" affects **exactly
  one rig**: `ard_datalogger`.
- **19 goldens carry `RIG_BOARD`** — but see §4, that is the count
  carrying the key, NOT the count that changes.

## 3. RULING — the corpus harness's board source (driver, 2026-08-06)

This is the question §9.4 never answered, and the slice cannot start
without it. `tests/integration/conftest.py::rig_board` (line ~392) reads
`rig.yml`'s `board:` — top-level, else the selected variant's — to decide
which `--board-dts` each corpus rig gets. **Delete `board:` and that
function has nothing to read, taking every golden test with it.**

> **RULED: `RigCase` gains an explicit `board` field. The test corpus
> table names each rig's board; nothing reads it back out of rig.yml.**

Rejected alternatives, and why:

- *Keep a `board:` in rig.yml as a "default" the harness reads.* That is
  the thing this slice removes. A default that only the test suite
  consumes is the same declaration wearing a disguise.
- *Derive it from `--boards-for`.* Circular — a rig's own golden test
  would depend on the census under test — and `--boards-for`'s claim is
  bounded to SOCKET conformance, never "it builds" (S2's own recorded
  bound). `nucleo_datalogger` now answers two boards; the census cannot
  tell you which one its goldens were frozen against.
- *A side-car file mapping rig → board.* Same content as `RigCase`, one
  more file to drift.

The ruling is also the honest model: under strict symmetry the
**invocation** supplies the board, and the test harness IS the
invocation. Making that explicit in the corpus table is the expectation
coming from OUTSIDE the thing under test — the discipline this project
already holds for every control.

Consequence: **`run_expand` must gain `--board`**, threading
`RigCase.board`. It does not pass one today (verified) — the goldens
currently rely entirely on the declaration.

## 4. PREDICTION — `RIG_BOARD` should NOT churn, and that is checkable

`emitter/context.py`'s own docstring: `RIG_BOARD` is `rig.board`
verbatim, which since S1 is *"the board this build actually used — the
CLI's `--board`, when the invocation gave one, or the rig's own declared
board otherwise"*.

So once the harness injects the SAME board string it used to declare,
`rig.board` is unchanged and **`RIG_BOARD`'s value is identical**.

> **The 19 `RIG_BOARD` goldens are predicted BYTE-UNCHANGED. If one
> churns, that is a FINDING to report, not a refreeze.** §9.4's "the 19
> goldens refreeze" counted the goldens carrying the key, not the ones
> whose value moves.

**The real churn is `ard_datalogger`** (§5), and it should be the only
churn. Classify it per §6.

## 5. `ard_datalogger` — the collapse, ruled into this slice

Ruled 2026-08-06 (Tobi) and recorded in §9.5 step 6: S5 deliberately left
this rig untouched so it would orphan nothing, and the whole collapse
lands here as one piece.

Its `sockets: {ard: nucleo_ard}` / `{ard: frdm_ard}` map exists solely
because the two boards spelled the same connector differently. **S5 made
both carry `arduino_r3`, so the map is already dead weight.** Four
things, together:

1. content's `socket: ard` → `socket: arduino_r3` (the conventional
   label, as every other rig now uses);
2. both `sockets:` maps deleted;
3. `board:` deleted from both variant entries — at which point the two
   variants differ in **nothing**;
4. therefore **the `variants:` block goes entirely**: one variant-less
   rig, built twice by supplying a different `-b`. That is §9.4's own
   headline promise made real.

**Decide and REPORT what happens to its two golden directories**
(`ard_datalogger`, `ard_datalogger_frdm`). A variant-less rig has no
`RIG_VARIANT` and no `_frdm` variant suffix, but it still has two boards
worth freezing. Do NOT quietly drop the frdm coverage — losing the
dual-host case would remove the only evidence the whole direction works.
Propose the shape in your report; the driver rules on it.

## 6. The `sockets:` map vocabulary — retire the DATA, keep the MECHANISM

With `ard_datalogger` migrated, **no rig in the corpus uses `sockets:`**.

> **RULED: delete the corpus's map DATA. Do NOT delete
> `SocketBinding`/`resolve_board`'s handling of it in this slice.**

Why the split: `resolve_board`'s five coherence rules are S2-era frozen
wording with reject goldens behind them (`no-board-declared`,
`variant-board-partial`). Ripping out the mechanism churns a diagnostic
family in the same slice that changes the corpus, and this project's own
rule is mechanism and data move separately. Retiring the mechanism is a
follow-on with its own classified refreeze — **note it in your report as
newly-dead code, do not remove it.**

## 7. `resolve_board`'s "never neither" — keep the diagnostic

S1 relaxed *"a board per variant or once at the top level, never
neither"* to *"never neither unless injected"*. After S6 **every** corpus
rig declares no board, so the un-injected path becomes unreachable for
the corpus — but it is still exactly what a user hits running cmake-alone
with no `-DBOARD`.

> **RULED: the diagnostic STAYS and must stay legible.** S1 and S3b both
> have acceptance criteria on that message. A fixture must keep covering
> it — check `no-board-declared`'s golden still fires, and say so.

## 8. Acceptance criteria

1. **No `board:` key anywhere under `boards/rigs/`.** Assert it as a
   census-style test — falsified by mutating the WORLD (add one back to a
   rig), never by editing its own assertion. S5's
   `test_no_rig_content_names_a_board_prefixed_socket` is the shape to
   follow.
2. **Every `RIG_BOARD` golden byte-identical** (§4). A churn is a finding.
3. **`zephyr.dts` byte-identical for every rig** — this is a declaration
   change, not a topology change.
4. **Every `stderr.txt` and `exit_code` byte-identical except where §7's
   diagnostic family genuinely moves** — byte-exact PERMANENTLY by owner
   ruling, so any movement needs classifying and reporting, never a
   silent refreeze.
5. **`ard_datalogger` is one variant-less rig**, still covered on BOTH
   boards, with the golden shape proposed and justified (§5).
6. **`west rigs` no longer prints a board column** (it has nothing to
   print); `--boards-for` is the enumeration answer. S2 built it for
   exactly this moment.
7. **`west build-rig --rig X` with no `-b` fails legibly** for a
   persisted rig, the same way S3b made it fail for a promoted shield —
   one message family, not two.
8. mypy clean, unit green, coverage at or above the 88 floor.

## 9. Verification contract — REDUCED, and note WHICH modules

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc
$PY -m pytest scripts/rigc/tests/unit -q
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q
$PY -m pytest scripts/rigc/tests/integration/test_emitted_corpus.py -q
$PY -m pytest scripts/rigc/tests/integration/test_resolved_corpus.py -q
git diff --stat -- scripts/rigc/tests/goldens/     # CLASSIFY, do not clear
```

**TWO build-marked modules, deliberately** — S5's brief named only
`test_resolved_corpus.py` and an implementor following it literally would
have classified a refreeze it could not see. The general rule: *the
contract must name the module that OBSERVES the slice's acceptance
criteria.* Here `test_emitted_corpus.py` observes the golden churn and
`test_resolved_corpus.py` observes a real build.

**`RIGC_REFREEZE=1` is BLOCKED by the harness permission classifier in
this environment.** Expect it to fail. S5's approach worked and is the
precedent: run the comparison WITHOUT refreeze to get the exhaustive
mismatch list, then edit exactly those cells. It is more surgical than an
automated whole-file rewrite anyway.

- **Do NOT background a command and end your turn waiting on it.**
- Never `cmd | tail; echo $?` — that reports tail's status.
- Mutation discipline: copy first, sha256 BEFORE, restore FROM THE COPY,
  verify, purge `__pycache__`. **Never `git checkout <file>`.**
- The papers are at `btr-shields/claude/`; `/wrk/z/ws-up/claude/rigs/` is
  stale.

## 10. Out of scope

Retiring `SocketBinding`/`resolve_board`'s map mechanism (§6 — report it
as dead, leave it). The §9.6 params CLI grammar. The production
`i2c-port.yaml` gap (S4's handoff records it; it is a product decision).
Any change to the boards' own DT labels.

## 11. RULED DURING REVIEW (Tobi, 2026-08-06) — the grammar goes too

> *"I want to remove the `board:` from the rig grammar entirely. That's
> confusing in the long run and besides us noone will remember it or miss
> it."*

This **overrides §9.4's staging**, which kept inference as a fallback. It
splits in two:

**Landed with S6 (`40c8d10`) — the half that belongs with the data:**
`cmake/boards.cmake`'s rig→board inference, the `RIG_INFERRED_BOARD`
marker, and the rig-swap guard, together with the four tests covering
them (`reconfigure_of_rig_build_dir_proceeds` and the three
`rig_swap_*`). Those four were **dropped, not adapted** — the guard's
failure mode required a rig with a declared board, so it ceased to exist
rather than merely stopping being tested. Deleting mechanism and tests in
one change is what keeps "no live code left untested" true.

The other five of the nine gained `-DBOARD` and kept their subjects.

**Deferred to its own slice — the grammar itself.** Measured before
committing to it:

- **36 fixture rigs declare `board:`** (not 17 — the corpus was the small
  half). Each needs its board injected via the harness instead.
- **10 fixtures exist to test the declaration grammar**, each with a
  byte-exact reject golden: `board-declared-twice`,
  `content-file-carries-board`, `content-file-carries-sockets`,
  `no-board-declared`, `revision-carries-board`,
  `sockets-with-variant-board`, `variant-board-partial`,
  `variant-board-restated`, plus `unknown-board` and `unmapped-socket`,
  which need judgement (an *injected* unknown board is still a real
  error). Roughly eight of those goldens die outright — a user-facing
  diagnostic family disappearing, byte-exact by ruling, so it wants its
  own classified diff.
- Production: `resolve_board`'s five S2 coherence rules, `SocketBinding`,
  `list_rigs.py`'s board resolution and the `{BOARD}` cmakeformat key.
  **`RIG_BOARD` in `context.cmake` STAYS** — the board actually built is
  still a fact.
- **The `--boards-for` placeholder-board wart disappears** rather than
  needing documentation: with no board required to load a rig, the census
  needs no fake one.
