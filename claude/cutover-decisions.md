# Cutover — driver decision log

Decisions the driver made while running C2b → C4 unattended
(Tobi away, 2026-07-30b). **D9, D10 and D11 were SIGNED OFF by Tobi
2026-07-30b after the cutover landed — see each entry's status line.** Every entry: what was decided, why, and what
the alternative was. Anything here is reversible; nothing here overrode
a ratified ruling.

Ratified rulings live in `cutover-brief.md` §8. This file is only for
calls that came up during execution and had no ruling to point at.

---

## D0 — Process: keep the per-class review round even though it is slower

`cutover-brief.md` §8.6 ratified "C2 split per artifact class, each with
its own review round". With the owner away it would have been faster to
review C2b/C2d myself and reserve an opus round for C2c alone.

**Decided: honour the ruling, review every class.** R5's review round
found a ratified ruling silently dropped (frozen `Solved`) and named the
precedent — rulings becoming optional whenever it is convenient — as the
reason it mattered more than the missing keyword. Economising on process
*specifically while the owner cannot see it* is that precedent in its
purest form. The cost is wall-clock, which is the cheapest thing here.

---

## D1 — `config-sheet.md`'s contract: facts with TOTAL COVERAGE enforcement

The brief (§3) says assert the facts the sheet carries, never the
rendering. That leaves the dangerous half unspecified: a fact extractor
that silently fails to match a line **drops** that fact, and a comparator
that quietly stops checking still reports green. This is the same failure
shape as C1's `check.sh` guard that would have skipped the whole frozen
suite while passing.

**Decided: every non-blank, non-heading line of both documents must be
consumed by exactly one extractor; an unmatched line is a MISMATCH.**
Freedom is then bounded and explicit — it exists only where an extractor
is deliberately tolerant (surrounding prose, heading wording, column
headers, table-vs-list layout), never by accident. Same discipline C2a
already applies with "text that fails to parse is a mismatch, never a
silent skip".

Alternative rejected: extract only recognised patterns and ignore the
rest. Simpler and much more permissive — it cannot distinguish "this
document has no straps section" from "my regex stopped matching the
straps section".

---

## D2 — Section presence is contract; row order within a section is too

The emitter sorts every section deterministically (R7/R18), so row order
is not incidental — it is a property the emitter guarantees and a reader
relies on.

**Decided: compare sections as a SET of section kinds (a missing or extra
section is a mismatch) and rows within a section as an ORDERED list.**
Only `RIG_DEPENDS` in C2a earned set semantics, because cmake genuinely
consumes it as a set. Nothing in the config sheet has that property.

---

## D3 — the strap/jumper `sheet_label` is a compared fact (agent-proposed, accepted)

C2b's implementor pinned the strap/jumper sheet label (e.g. "ADDR
jumper") as part of the compared fact tuple, which the brief's own
enumeration of facts did not name.

**Accepted.** It is the only text identifying WHICH physical strap or
jumper a human must set, so omitting it would let two different jumpers
on the same instance, state and address collapse to equal facts — the
sheet exists to tell a person which piece of hardware to touch. The
change makes the comparator STRONGER than the brief's letter, never
weaker, and all 19 goldens self-compare equal with it in place.

Standing principle this establishes: an implementor may tighten a
comparator beyond the brief without asking; loosening one always needs a
ruling.

---

## D4 — THE INTEGRATION SUITE HAS ZERO FALSIFICATION POWER FOR COMPARATORS

C2b's review established this by mutation testing, and it changes how the
rest of C2 must be judged. Emitter output is byte-identical to the
goldens today, so **every** comparator — correct, weakened, or gutted —
passes the 146-test integration suite trivially. The suite proves the
comparator ACCEPTS truth; it cannot prove the comparator REJECTS
falsehood.

Therefore `tests/unit/test_compare.py` is not supplementary coverage: it
is the only thing standing between a future refactor of that module and
a silently-green comparator. The review injected 10 mutations into
`compare.py` — including deleting the guard that enforces total coverage,
the duplicate-section guard, and the rig-name and board comparisons — and
**all 10 passed the whole suite**.

**Decided, binding on C2c and C2d: every guard a comparator relies on
needs its own negative control, and each new comparator slice must
report a mutation check — break each guard, confirm a unit test fails.**
"The suite is green" is not evidence for a comparator; only a failing
test under a broken guard is.

---

## D5 — zero-golden-coverage fixtures are GENERATED from the emitter

The two config-sheet branches no golden exercises (a chip-select with no
SoC mapping, and the whole `## Wires` section) were pinned by
hand-written fixtures — and the review found the Wires fixture already
WRONG: it wrote a route as a position name where `analyzer/wires.py`
resolves routes to an integer index, so the fixture described output the
emitter cannot produce.

**Decided: generate those fixtures by driving the real `render_sheet`
with a synthetic `Solved`, then feed the result to `parse_config_sheet`.**
Fixture drift becomes structurally impossible instead of a review catch.
`tests/unit/emitter/test_sheet.py` already drives `render_sheet` with no
production data and no subprocess, so the precedent and the machinery
both exist.

---

## D8 — the tier-2 build for `shield-uart-subset-frdm` becomes its OWN slice

**My cost estimate for this was wrong when the owner ratified it.** I said
it was "one more build in a suite that already runs 18". It is not:
`shield-uart-subset` is a FIXTURE rig, not a corpus rig; tier-2 builds go
through `west build-rig --rig <name>`, which resolves rigs from registered
board roots; and **no test has ever built a fixture rig**. The fixture
tree has `boards/`, `dts/`, `include/` but no `zephyr/module.yml`, so it
is shaped like a Zephyr module without being one.

Re-examined, the enabling change is genuinely small: add
`fixtures/zephyr/module.yml` with `board_root: .` / `dts_root: .`
(copying btr-shields' own), activated by `-DEXTRA_ZEPHYR_MODULES=<fixtures>`
— the precedent `test_cmake_alone_entry.py` already uses for bridle. A
stray `module.yml` is INERT: west discovers manifest projects, not stray
files, and `EXTRA_ZEPHYR_MODULES` is the only activation path. So the
blast radius is exactly the one new test.

What remains unproven is whether a fixture rig RESOLVES end to end through
`west build-rig` / `list_rigs.py`. That could be quick or a rabbit hole.

**Decided: split it out.** C2c delivers the overlay comparator (the
ratified split contract) and KEEPS `shield-uart-subset-frdm`'s overlay
byte-compared as an explicit, documented interim exception — it is the one
accept rig with no `zephyr.dts`, so under the split contract it would
otherwise lose semantic checking entirely. A separate slice then adds the
build and retires the exception.

Why this ordering rather than doing both together: the comparator is
ratified and low-risk, the build is ratified but of unknown cost, and
coupling them would let the unknown block the known. The interim
exception is one line of dispatch logic and trivially reversible.

**Flagged for the owner:** if the fixture rig turns out not to be
buildable without structural change, the honest fallback is to keep that
one overlay byte-frozen permanently — which is the option originally
rejected, and rejected partly on my bad estimate. That call should be
the owner's, not mine, so the slice stops and reports rather than
expanding.

**UPDATE (C2c review, measured): the stakes of that decision are close to
zero.** `goldens/shield-uart-subset-frdm/rig-gen.overlay` is THREE LINES
— the provenance banner and nothing else. No nodes, no properties. That
rig exercises subset-exposure acceptance, and its overlay carries no
devicetree content at all. So:

- the exception is INERT today: byte-comparing that file checks a banner,
  and the targeted overlay checks would find zero facts in it either way;
- the "semantic loss" I described when recommending the build — a rig
  losing its only devicetree check — **does not exist for this file**.

The tier-2 build is therefore worth adding for what it would protect if
that fixture ever gains content, not for anything it protects now. If it
proves awkward, keeping the exception permanently costs nothing
measurable. That materially lowers the urgency of the slice, and it is
the second time my framing of this item was wrong — first the cost, now
the benefit.

---

## D11 — the exit-vocabulary collapse (ratified §8.3) rests on a FALSE PREMISE

**STATUS: SIGNED OFF 2026-07-30b — the decline stands.** The exit
vocabulary remains 0 accept / 1 reject / 2 usage / 3 refusal, and
`unimplemented.py` stays. §8.3 is withdrawn rather than deferred: the
four live refusal sites are deliberate, and converting them would be a
product-design slice of its own, not cutover work.

**Needs the owner's ruling. C3 correctly declined to do it.**

§8.3 ratified collapsing the exit vocabulary to 0 accept / 1 reject /
2 usage, retiring `unimplemented.py`. The stated premise was that only ONE
unreachable `raise Unimplemented` remained, in `cli.py`.

That premise is wrong. `loader/documents.py` has **four LIVE, reachable**
`Unimplemented` sites — YAML parse failure, unreadable file, empty
document, non-mapping document — chosen deliberately at R2 on the grounds
that no frozen golden covers `lang-parse` wording, so a loud refusal was
the always-acceptable answer. Four unit tests in `test_cli.py` assert
`ret == 3` through REAL control flow (e.g. a missing rig.yml), not through
the dead branch.

No golden exercises exit 3 (verified: every `exit_code` golden is 0 or 1),
so the frozen suite is indifferent. But collapsing the vocabulary means
converting those four refusals into genuine reject diagnostics — a NEW
diagnostic code and user-facing wording. That is product design, not
mechanical retirement.

Useful for whoever does it: rigexp's `loader_yml.py` already carried real
wording for the YAML-parse case (`error[lang-parse]: YAML parse error`),
recoverable with `git show` from before C3's deletion, so a
hand-differential is available rather than inventing wording from scratch.

`unimplemented.py`, its import, and the 0/1/2/3 vocabulary are therefore
UNCHANGED. This is the third ratified item this run that turned out to
rest on a premise nobody had measured (D8/D9 the tier-2 build, and this).
The pattern is worth naming: **a brief written from a code census is only
as good as the census, and §8's rulings were drafted before several of
those censuses existed.**

---

## D10 — THE EXPANDER LEAKS A TEMP WORKDIR PER INVOCATION (found, recorded, fixed)

**STATUS: SIGNED OFF 2026-07-30b, IMPLEMENTED 2026-07-31 (`84e7e4e`).** The
ratified design landed as specified: `cli.py::_expand` wraps its body in
`try/finally`, removing the workdir only when an `accepted` flag is set
(the clean-accept `return 0`) and `RIGC_KEEP_WORKDIR` is unset; any
non-zero exit (reject, refusal) keeps it. Unit tests pair
accept-removes/reject-keeps as each other's negative control (a
naive always-delete or never-delete implementation passes one but fails
the other), plus a third test for the `RIGC_KEEP_WORKDIR` override.
Verified against real `west build-rig` configures, not just the unit
suite. Backlog group A item 1 closed.

**Needs the owner's ruling; a production behaviour change is not mine to
make unbriefed.**

`cli.py:173` does `tempfile.mkdtemp(prefix="rigexp-")` inside a `try:`
with **no `finally`**, and neither `rigc/cli.py` nor `rigexp/cli.py`
contains an `rmtree` or a `TemporaryDirectory` anywhere. So every single
expand invocation leaves its workdir behind — cpp intermediates, shield
translation units, the lot.

Measured this session: **7001 directories, 787 MB** accumulated in `/tmp`.
On this machine `/tmp` is tmpfs, i.e. RAM, so this is the same resource
the OOM killer was competing for in D7 — that diagnosis blamed the
driver's own pytest basetemps, which was true but was only half of it.
This is the other half, and it is the tool's own doing, not the harness's.

It matters beyond the test suite: `dts.cmake` invokes the expander once
per configure, so every real build leaks one too.

Why I am not fixing it inside C3 even though C3 edits `cli.py`:
- the workdir has genuine debugging value on a REJECT (a cpp failure
  embeds the workdir path in the rendered diagnostic, which is exactly
  why the harness has a `_WORKDIR_RE` normalisation at all), so the fix
  is not "always delete" but something like "delete on success, keep on
  failure" — a behaviour DESIGN call, not a mechanical one;
- it is a production behaviour change, unbriefed, during a cutover, with
  the owner away.

Proposed fix for ratification: remove the workdir when `main()` returns 0
and keep it otherwise, so debuggability survives exactly where it is
useful. Optionally gated by a `RIGC_KEEP_WORKDIR` env knob for the
success path. Expected golden impact: none — the workdir path reaches
stderr before any cleanup, and the harness normalises it regardless.

Interim mitigation, already applied: stale `/tmp/rigexp-*` directories
wiped by hand (spared anything under 10 minutes old, so no in-flight run
lost its workdir).

---

## D9 — the D8 tier-2 build slice is NOT RUN. Its ratified GOAL is already met.

**STATUS: SIGNED OFF 2026-07-30b — the skip stands.** The tier-2 build
is not queued work; `overlay_is_byte_compared` and its census guard are
the permanent arrangement unless that overlay ever gains content.

**Needs the owner's sign-off, because it declines to do something ratified.**

The ratified goal was: `shield-uart-subset-frdm` must not lose its
semantic check when overlay comparison moves to `zephyr.dts`. The ratified
MECHANISM was adding a tier-2 build for it.

As C2c actually landed, that rig lost nothing: its overlay stays
BYTE-COMPARED, which is the strongest check available — stronger than the
targeted comparison every other rig now gets. So the goal is satisfied by
a different means than the mechanism, and the mechanism is redundant.

Measured facts that make this clear-cut:
- the file is **142 bytes, three lines**: the provenance banner and
  nothing else. No nodes, no properties. Byte-comparing it is therefore
  COMPLETE coverage of it, and would remain complete if it ever gained
  content.
- C2c's new census test enforces the invariant structurally: any overlay
  golden without a `zephyr.dts` must be in the byte-compared exception
  set, or the suite fails. The hole D8 was meant to close is closed by
  the exception plus the census, not by a build.
- the build's remaining value would be proving the rig CONFIGURES — a
  different property, for a synthetic fixture whose acceptance is already
  proven at expander level and which has a reject twin
  (`shield-uart-subset-nucleo`).

Against that: unknown cost (no test has ever built a fixture rig; it needs
the fixture tree registered as a Zephyr module), spent on a rig that gains
nothing measurable.

**This is NOT process economy** — the distinction D0 draws. It is a scope
call on measured evidence, in the conservative direction, and trivially
reversible: adding the build later needs only the `module.yml` and one
test. If the owner wants it anyway, it is a clean standalone slice.

Third correction to my framing of this item: I got its cost wrong, then
its benefit, and now conclude it should not run at all. The pattern is
that I recommended it before measuring the artifact it protects.

---

## D7 — driver verification runs use pytest's DEFAULT basetemp

Two consecutive full-gate runs were killed mid-flight with no output.
Cause, diagnosed rather than retried: **`/tmp` here is tmpfs, i.e. RAM.**
Fourteen accumulated `--basetemp` directories from earlier verification
runs held full west build trees — five at ~322 MB each, plus one agent's
at 954 MB — leaving 1.8 GB free on `/tmp` and 877 MB of system memory.
The build-running suites were being OOM-killed by the driver's own
verification debris. Clearing them freed 2.6 GB of tmpfs and took
available memory from 3.6 GB to 6.2 GB.

**Decided: pass no `--basetemp` for verification runs whose artifacts I
do not intend to inspect.** pytest's default root keeps only the last 3
numbered dirs, so it is self-limiting; `check.sh` already relies on that.
Use an explicit basetemp ONLY when an artifact must be inspected (the
recorded reason: `/tmp/pytest-of-tobi` is shared across projects and
pruned, so a shared-root artifact may vanish before you read it) and
delete it in the same turn.

This is the counterpart of the existing rule that a build `-d` directory
is never durable: on this machine a pytest basetemp is not merely
temporary, it is *charged to RAM*.

---

## D6 — the prose whitelist is BOUNDED in code, not just documented

C2b tolerated any number of prose paragraphs before any section's rows,
while three docstrings claimed prose was whitelisted in exactly one slot
(the PWM intro). The review demonstrated a fact-CONTRADICTING sentence
(`Note: temp_a actually sits on sock9.`) inserted at the head of a
section comparing EQUAL.

D1 does license "surrounding prose", so this was arguably in bounds — the
defect was documentation narrower than behaviour, which is worse than
either a wide rule or a narrow one honestly stated.

**Decided: bound it in code — at most ONE paragraph, immediately after
the heading, before that section's first row.** That is exactly what the
emitter produces today (PWM's single intro), it keeps the freedom D1
intended, and it makes the docstrings true. The asymmetry the review
found — prose AFTER a section's rows is a mismatch — is now stated
explicitly rather than left to be rediscovered.

---

