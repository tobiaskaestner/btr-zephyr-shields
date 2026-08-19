# Rigs — Session Handoff

## RESUME (2026-08-19b) — THERE IS NOW **ONE** PLUG FORM. Tobi's review of the docs and the corpus killed the single/plural asymmetry and took the cell counts off every plug node. **NOTHING IS COMMITTED** — read the state section before touching anything. NEXT = commit this, then reference slices 2/3, then rig-schema.yaml → BRIDLE MIGRATION.

### STATE AT SESSION CLOSE (2026-08-19b) — UNCOMMITTED, READ THIS FIRST

**The tree is DIRTY and nothing from this slice is committed.** `main` is
still **ahead 54 of origin**, HEAD still `b5d36e5` (the previous block's
own handoff commit). ~66 files are modified in the working tree. Derive
the real state from `git status` and `git diff --stat`, never from this
paragraph — it was written before the commit existed, which is the exact
failure mode the previous three blocks each hit from the other direction.

**Gate DRIVER-VERIFIED at close: `check.sh: ALL GREEN`, exit 0** — the
FULL gate, build tier included, run after the goldens were refrozen. The
first full run FAILED on 6 golden mismatches (see "the goldens" below);
this is the second. Re-derive anyway, per this file's own rule.

| | measured at close |
|---|---|
| mypy | clean, **107** source files |
| unit | **777** passed (was 771: +6 net) |
| coverage | **94%** vs the 88 floor |
| integration | **297** passed, none deselected (was 294: +3 doc laws) |
| docs | `-W --keep-going` **build succeeded**; `sphinxlint` clean |

Note the gate's own exit status is what says this, not a tail of its log:
the first run's `EXIT=1` was masked by how it was invoked (see CARRIED).

### 1. The ruling — one authored form (`claude/plug-unification-brief.md`)

Tobi, reviewing `adafruit_data_logger` against `can_span_click`: *"note how
the adafruit_datalogger defines the i2c and spi nodes as sibling of the
plug node, whereas the can_span_click has these nodes as child nodes of
the left_plug and right_plug nodes respectively. It would be much more
consistent if the single plug syntax would work the same."* Plus a
question: *"for what the #gpio-cells property is actually needed on a plug
node."*

Both were ruled the maximal way, on evidence:

1. **FULL unification.** N plug nodes, N ≥ 1, each carrying
   `compatible = "shield,plug"` and its own `shield,plugs`.
   **Template-level `shield,plugs` is RETIRED** with a diagnostic that
   names where it moved. The `plug`-is-a-reserved-name rule is gone.
2. **Cells leave the plug node** — `#gpio-cells`/`#pwm-cells`/
   `#io-channel-cells` stripped everywhere and now REFUSED there
   (`lang-shield-plug-cells`). `_ncells` and `_FUNCTION_DEFAULT_CELLS`
   stay: a routing jumper's own `<1>` is genuinely load-bearing.

### 2. The asymmetry was a SILENT-FAILURE TRAP, not a style wart

This is the finding that justified the scope. Probed against
`parse_shields` before writing anything: a single-plug shield with its bus
groups **nested** under `plug` — the spelling Tobi wanted to work —
parsed to **0 devices and 0 diagnostics**. Same for a plain group nested
there. `_RESERVED` held `"plug"`, the single-form walk skipped every
reserved name, so the plug node's children were never visited at all. An
author writing the plural spelling on a single-plug shield got an empty
overlay and no complaint: **item 41's defect shape one level up**, and the
tutorial taught the form that hits it.

### 3. THE KEY FACT that made it cheap — downstream never knew

Every consumer of plurality below `shields.py` already discriminated on a
COUNT (`len(shield.plugs) > 1`), never on the authored form:
`analyzer/sockets.py`, `emitter/sheet.py`, `promote.py`. And the retired
single branch already normalized into the same `shield.plugs` /
`nodes_by_slot` / `plugs_by_path` the plural walk consumed. `shields.py`
is the ONLY module that reads `shield,plugs` at all. So the slice was a
parse-layer change plus a mechanical migration — not a pipeline refactor.
Re-derive that before relying on it.

### 4. What moved

- **`shields.py`** — the `is_plural` fork deleted; one group walk with the
  plural rules for everybody; the retirement diagnostic; the cells
  refusal; the jumper refusal now `len(shield.plugs) > 1`; plain-group
  devices get `only_slot` (the one plug's own NAME) instead of the
  hardcoded `"plug"`.
- **22 corpus `.shield` files**, ~32 integration fixtures, ~40 inline
  `test_shields.py` fixtures — migrated by a throwaway brace-aware
  transform (session-local, NOT kept: it emitted a diff per file, reviewed
  one by one, and reported rather than touched anything it could not
  classify). Two negative fixtures it correctly refused were hand-migrated
  — but two it DID rewrite had their deliberately-retired spellings eaten
  and had to be rebuilt as tests of the new refusals. **If a future slice
  scripts a corpus migration, check what it did to the negative fixtures
  first.**
- **Docs** — `shield-template.rst`'s two form sections collapsed to one,
  plus a new "Where a group goes" section stating the placement rule
  once; `write-a-shield-template.rst`; `commands.rst`'s promotion
  grammar (now count-worded); `glossary.rst` gained **routing jumper**.
- **Six stale shield comments** and five stale source comments that the
  change falsified (`model.py`, `analyzer/sockets.py`, `shields.py`).

### 5. Six mutations, and the one that SURVIVED is the useful one

Mutated one at a time, `__pycache__` purged on both sides, source
verified restored byte-identical: the cells refusal; the per-plug walk;
the template-level bus-group refusal; the retirement diagnostic;
`only_slot` → the retired hardcoded `"plug"`; the nested plain-group
refusal. Six mutations, six kills. (The harness was session-local and is
not kept — the list above is the durable part.) The first attempt at one
of them **survived**: restoring
`"plug"` to `_RESERVED` changes NO behavior, because plug nodes are now
skipped by identity and their children are reached by the per-plug walk,
which never consults `_RESERVED`. So that removal is a CLEANUP, not the
fix — mutating the **per-plug walk** is what kills the test. The
`_RESERVED` comment says exactly this and names the mutation. **The rule
holds again: run the mutation, do not reason about it** — I had written a
confident, wrong causal claim in the brief and the mutation corrected it.

### 6. The goldens — Sec 2 of the brief was HALF WRONG

The brief predicted byte-identical goldens. **Overlays: correct, all
untouched. Six stderr goldens: WRONG** — the full gate found them
(`test_emitted_golden` for the five `REJECT_CASES`, plus
`test_pwm_nonzero_flags_golden`). A diagnostic cites its source location,
and moving a bus group moved both halves:

- **line numbers** shifted in every migrated file (a one-line plug node
  became a block);
- **DTS node paths gained a `plug/` segment** for bus devices —
  `/shield-templates/adafruit_winc1500/spi/wifi` →
  `.../adafruit_winc1500/plug/spi/wifi`.

Refrozen with `RIGC_REFREEZE=1`, and **the refrozen diff is itself the
proof the change was placement-only: every changed line is an
`at <file>:<line> (<dts path>)` location** — no verdict, no message body,
no exit code, no overlay. Two things in it worth keeping:

- `grove_servo`'s path stayed `/shield-templates/grove_servo/pwm/servo`.
  `pwm` is a PLAIN group, so it did not move — the goldens confirm on real
  output that the placement rule discriminates bus from plain as intended.
- The `plug/` segment makes the diagnostic strictly better: it now says
  WHICH plug a conflicting reference resolves through, which the old path
  could not carry on a two-plug shield.

**The lesson that outlives this slice:** a byte-compared stderr golden
makes every source LINE NUMBER part of the contract. Any edit that moves
lines in a `.shield` file changes goldens however semantically inert it
is — so "no behavior change" never implies "no golden change", and
`CHECK_FAST=1` checks none of them.

### 7. Two new doc laws, both mutation-checked, and why they were needed

`test_dts_vocabulary_drift.py` gained: **no doc example shows
template-level `shield,plugs`** (every documented `shield,plugs` sits
beside a `compatible = "shield,plug"`), **no doc example declares cells on
a plug node**, and a **vacuity control** (floors on blocks found, pages
covered, plug nodes present). The existing vocabulary scan could see
neither change — `shield,plugs` is a real production literal wherever it
sits, and `#<fn>-cells` is not in the `shield,*`/`plug,*`/`socket,*`
families at all. Both laws were mutated against real doc pages — the
tutorial reverted to template-level `shield,plugs`, the reference given
back a `#gpio-cells` on a plug node — and both killed.

### 8. One fixture had the only non-default plug cells anywhere

`carrier-analog-passthrough`'s `fixture_analog_carrier` declared
`#pwm-cells = <2>` on its plug and shaped its `pwm-map` rows to a 2-cell
parent side. Four integration tests red on `truncated entry` until the
rows gained a third parent cell. **Every real carrier already used three**
(`seeed_grove_base_v2`), so the fixture was the outlier. The consequence,
now documented on `shield-template.rst` and in the fixture header: a
pass-through map row's two halves differ in kind — the CHILD side carries
whatever the exposed socket declares, the PARENT side is a plug and is
therefore always the generic count (2 gpio, 3 pwm, 1 adc), with nothing
left to vary.

### Backlog delta

Closed: nothing numbered — this slice came from Tobi's review, not the
backlog. The `#gpio-cells = <3>`-on-a-plug hole (an unvalidated knob,
item 40's family) is closed by the refusal, incidentally.

Opened: nothing. **41** (`rig.yml` silently ignores unknown keys under
`rig:`) and **42** (`west rigs --rig TARGET` accepted and never read) are
**both still open and still unruled** — untouched by this slice.

Unchanged and still the destination: **rig-schema.yaml (item 7) → BRIDLE
MIGRATION (item 9)**, with reference slices 2/3 still unstarted before
them.

### NEXT

1. **COMMIT THIS SLICE** — it is one coherent change (parse rule + corpus
   + fixtures + tests + docs + goldens) and the gate must be re-derived
   first, since the second full run's verdict never reached this file.
2. **Reference slices 2 and 3** — unchanged, still unstarted: (2)
   `rig-file.rst` + `promotion.rst`, (3) the 42-code diagnostic
   catalogue. `promotion.rst` should take over the promotion grammar's
   semantics from `commands.rst`.
3. **`rig-schema.yaml`** (item 7), which item 41 belongs to.
4. **BRIDLE MIGRATION** (item 9) — the mission goal, and the reason this
   slice went first: every shield ported from bridle would otherwise have
   been authored in the form now retired. Re-run
   `bridle-migration.md`'s triage against bridle's CURRENT upstream.

### CARRIED — one correction

**`RIGC_REFREEZE=1` is NOT blocked** — the previous three blocks carried
"still blocked by the harness classifier" and it ran without complaint
today, refreezing six goldens in 16s. Drop the warning.

Still true: from a session rooted at `/wrk/z/ws-up`,
`rig-implementor`/`rig-reviewer` are NOT agent types. `ZEPHYR_BASE` for
this workspace is `/wrk/z/ws-up/zephyr`. `doc/_build/html` is a local
render, never committed — **rebuild before reading it.**

One harness note worth carrying: invoking the gate as
`scripts/check.sh > log; echo $?; tail log` in a BACKGROUND command
reports the COMPOUND's exit status (`tail`'s, always 0), which read as a
green gate for a run that exited 1. Make `check.sh` the last command.

---

## RESUME (2026-08-19, superseded) — ALL THREE BLOCKERS ARE CLOSED. The expander keeps its workdir, the docs build from the workspace `.venv`, and `doc/reference/` gained a COMMAND reference plus the full rigc API reference. NEXT = reference slices 2/3, then rig-schema.yaml → BRIDLE MIGRATION.

### STATE AT SESSION CLOSE (2026-08-19)

The session's work is `9c84454`..`bcfd327`; **HEAD is this handoff's own
commit**, one past that (the previous two blocks each got this off by one
by naming a hash before their own doc commit existed). `main` is **ahead
54 of origin, NOT pushed** — pushing needs Tobi's word. **Tree is
CLEAN.** Read all three from git anyway, per this file's own rule.

**Gate DRIVER-VERIFIED at close, twice, not carried**: mypy clean
(**107** source files, +2 = the two new drift-guard modules), unit
**771**, integration **294** (+7, both new guards), coverage **94%** vs
the 88 floor. Docs build **`-W --keep-going` clean** from the workspace
`.venv` with the API reference in the toctree, and `sphinxlint` finds
nothing. Re-derive anyway.

| commit | what |
|---|---|
| `9c84454` | **the workdir is KEPT on every exit** (+ two stale `rigc expand --help` strings) |
| `1bd76ae` | **the docs build from the workspace `.venv`** — blocker 3 closed |
| `9804a04` | **`doc/reference/commands.rst`** + the CLI's own documentation made current |
| `bcfd327` | **`doc/reference/api/`** — the whole expander, via autodoc |

### 1. The workdir ruling (`claude/workdir-retention-ruling.md`)

Tobi: *"rigc should not delete the temporary files it writes under
`build/rig/rigc-generated`."* D10's accept-path deletion is REVERSED —
kept on every exit now. The accumulation problem D10 answered (7001
directories / 787MB in one session) was already solved by the move out of
`/tmp`: deterministic name, wiped on entry, so one `--out-dir` holds
exactly ONE of these — **72KB measured** on a real `nucleo_datalogger`
build, 63KB of it the preprocessed board `.dts`.

Three sub-decisions, all mine per Tobi's "decide and move on":
**the entry wipe STAYS** (a `.pre` that no longer matches the overlay
beside it is worse than none); **`RIGC_KEEP_WORKDIR` is RETIRED**, not
inverted (a no-op knob is item 40's defect shape); **the `try/finally`
goes** — `git diff -w` on cli.py shows 22 deletions and nothing else.

Both mutations were run one at a time with `__pycache__` purged between:
restoring the accept-path `rmtree` reds the accept + entry-wipe tests,
neutering the entry wipe reds the entry-wipe test alone.

### 2. The `.venv` ruling — BLOCKER 3 CLOSED

Tobi: *"dismiss `.docvenv`, docs should build from the workspace
`.venv`."* `doc/howto/build-the-docs.rst` was the half that disagreed with
reality. **All three of the 2026-08-15 blockers are now closed.**

### 3. Was rigc's CLI documented and up to date? NO, on both counts

**Not documented at all**: no reference page for any command — the three
surfaces appeared only as steps inside tutorials, and
`grep -rn 'rigc-generated' doc/` found nothing.
`doc/reference/commands.rst` now covers `west build-rig`, `west rigs` and
`rigc expand`: every option, the promotion grammar, the exit vocabulary,
`RIGC_LOG`, the emitted artifacts and the workdir.

**Not up to date**: eight stale statements, six of them S6 fallout
(`board-coordinate-s6-brief.md` retiring rig-level `board:`) — two
`--help` strings on `west build-rig`/`west rigs`, two on `rigc expand`,
two tutorials showing or AUTHORING a `rig.yml` with `board:`, and three
glossary entries describing a rig as carrying a board. Worse: **three
tutorial commands could not work** — `west build-rig --rig <name> <app>`
with no `-b` has been a configure `FATAL_ERROR` since S6, and it was the
headline command of the first tutorial.

**Every command that appears in the fixed docs was RUN.** Four real
builds, and the run is what caught a board name I invented
(`quail/stm32f411xe/rig`; the real one is `mikroe_quail/stm32f427xx/rig`).
Three `--help` strings also cited `claude/` briefs in text argparse prints
to users; those citations moved into code comments.

### 4. The API reference — autodoc, seven pages, all 37 modules

`doc/reference/api/`, one `automodule` per module, no hand-written prose
about any of them. Feasibility was MEASURED first: every rigc module
imports with no Zephyr tree and no `ZEPHYR_BASE` (the `devicetree`
imports are all deferred into function bodies), and a trial build over all
37 produced **ten** reST warnings, not hundreds — all ten formatting, all
ten fixed.

`undoc-members` ON (model.py's dataclasses document fields in trailing
comments autodoc cannot see), `private-members` OFF. Pages split by
pipeline stage, which makes `api/index.rst` the first document in the tree
that states the pipeline's shape to someone not already inside it.

**The one guideline decision**: docstrings cite `claude/` briefs, and
`documentation-guidelines.rst` keeps the design record out of `doc/`.
Rather than strip 9,600 lines of source or hand-write drifting pages, the
rule is scoped to AUTHORED pages, and an admonition on `api/index.rst`
tells the reader those documents are working notes and provenance. Full
reasoning in `claude/api-reference-brief.md`.

### 5. Two new drift guards, both mutation-checked

`test_api_reference_drift.py` (4 tests) and
`test_cli_reference_drift.py` (3), beside `test_dts_vocabulary_drift.py`
as corpus-level laws. Both directions each, plus a
does-the-scan-find-anything control so neither can pass vacuously.

**The lesson worth carrying**: `test_cli_reference_drift`'s forward check
first scanned the whole page and **passed a mutation** that renamed the
`--explain` entry — a paragraph elsewhere begins with ``--explain`` and
reads as a definition term. It now requires a real entry (a table cell, or
a term whose next line is indented). That is
`test_dts_vocabulary_drift.py`'s heading-only rule re-learned by running
the negative control. **Run the mutation; do not reason about it.**

### 6. Writing the reference found five stale docstrings and TWO new defects

Reference slice 1 said "writing reference documentation is a defect-finding
activity"; this slice's mechanism was publication itself, since autodoc puts
a docstring in front of a reader. Fixed: `rigc/__init__.py` still announced
"R2 state" and a loud refusal for anything needing the shield library
(three slices out of date), `loader/__init__.py` claimed a fall-through to
an `Unimplemented` that no longer exists AND called `params.py`
"params/pin machinery" after item 29's rename to `config:`,
`unimplemented.py` described only the finished differential period,
`emitter/context.py::render` claimed `RIG_BOARD` may come from a rig's
declared board.

**Opened, both needing a ruling, neither fixed:**
- **41 — `rig.yml` silently IGNORES unknown keys under `rig:`.** A
  retired `board:` is neither honoured nor refused. Not hypothetical: the
  tutorial taught authoring exactly that file until this morning. Strict
  schema, a specific `board:` diagnostic, or a warning — `rig-schema.yaml`
  (item 7) is the natural home.
- **42 — `west rigs --rig TARGET` is accepted and never read.** Silently
  lists everything. Wire it to `--explain`'s resolver, or stop offering
  it. Documented as ineffective in the meantime.

### NEXT

1. **Reference slices 2 and 3** — still sequenced, still unstarted: (2)
   `rig-file.rst` + `promotion.rst`, (3) the 42-code diagnostic
   catalogue. `commands.rst` documents the promotion target GRAMMAR
   because a reference for `--rig` cannot omit what its value looks like;
   when `promotion.rst` lands it should own the semantics and
   `commands.rst` should link to it rather than restate.
2. **`rig-schema.yaml`** (item 7) — unchanged, and item 41 now belongs to
   it.
3. **BRIDLE MIGRATION** (item 9) — the mission goal. Re-run
   `bridle-migration.md`'s triage against bridle's CURRENT upstream.

### THE BUILT DOCS — rebuilt at close, and a trap to know about

`doc/_build/html/index.html`, rebuilt from the workspace `.venv` at
session close with everything below in it (`doc/.gitignore` ignores
`_build/`, so it is never committed — it is a local render, not an
artifact).

**The trap**: that directory already existed and held a **2026-08-14**
build whose `reference/` had only `glossary.html` and `index.html` — it
predated reference slice 1, never mind this session. A stale render looks
exactly like a current one in a browser. **Rebuild before reading it**:

```
$ sphinx-build -W --keep-going -b html doc doc/_build/html
```

### CARRIED, unchanged

`RIGC_REFREEZE=1` is still blocked by the harness classifier. From a
session rooted at `/wrk/z/ws-up`, `rig-implementor`/`rig-reviewer` are
NOT agent types. `ZEPHYR_BASE` for this workspace is
`/wrk/z/ws-up/zephyr` — there is no `zephyr-rigs` checkout, whatever
`rigs.py`'s discovery heuristic hopes for.

---

## RESUME (2026-08-15, superseded) — THE ANALOG THREAD IS COMPLETE, and TWO OF THREE BLOCKERS ARE CLEARED. Carriers pass PWM and ADC, both twister boards have real nexuses, promotion can select a config element, and `doc/reference/` finally documents the DTS vocabulary. NEXT = reference slices 2/3, the venv ruling, then rig-schema.yaml → BRIDLE MIGRATION.

### STATE AT SESSION CLOSE (2026-08-15)

btr-shields HEAD **`3c69ea6`**. `main` is **ahead 48 of origin, NOT
pushed** — pushing needs Tobi's word. **Tree is CLEAN.**

**Gate DRIVER-VERIFIED at close, not carried**: mypy clean (**105**
source files), unit **771**, integration **287**, coverage **94%** vs
the 88 floor. The docs also build **`-W --keep-going` clean**,
driver-verified. Every slice below was gated by the driver independently,
with its own mutation checks, before commit. Re-derive anyway — this
file has been wrong about counts before, which is why the numbers are
labelled with how they were obtained.

### What this session did, in four threads

**1. The reference vocabulary finished (items 29, 30).** `pin:` became
`config:`, and the DTS LABEL is now the naming authority for **all
four** rig→shield reference surfaces — `config:`, `params:`, `wires:`
and `socket: <carrier>.<exposed>`. `rigc/shields.py::_require_label`
serves every kind of node that carries a label; no `labels[0] if … else
node.name` lookup fallback survives.

Item 30's own backlog entry predicted "labelling 8 nodes, migrating 15
references, and moving goldens". **Only the first happened** — every
node name was already a valid DTS label, so labelling each with its own
name left all 15 references resolving unchanged and every golden
byte-identical. Read a cost estimate here as a hypothesis.

**2. The grove family completed.** `grove_sens` (3 shields, one folder),
`grove_pwm_led`, and the base carriers `seeed_grove_base_v1`/`_v2`
(19 and 12 sockets, one folder named after neither).
`nucleo_grove_farm` is the first NESTED carrier promotion in the
permanent corpus and the first suite under `tests/rigs/`.

`b16c314` fixed a real emitter bug found on the way:
`rigc/emitter/overlay.py::_collection_entry` had no `ref.function`
branch, so a `pwm-leds` entry rendered gpio-shaped — polarity in the
period cell, the real period dropped. Silently valid, silently wrong.
One shared `::_render_ref` now serves both callers.

**3. The analog thread — the session's centre (backlog 33, 34, 35, 36).**
Ruling 3 of the carrier slice said "author the ADC connectors and accept
the breakage". They broke, and the diagnosis was worth more than the
feature:

- **33** — `ExposedSocket` could not hold a PWM/ADC map and
  `rigc/analyzer/sockets.py::compose_socket` never wrote one, so a
  carrier's declared `io-channel-map` was dropped at parse. Fixed in one
  sweep for both functions (`88e53fc`), because splitting them would
  have left a branch for one and a silent hole for the other — the
  `b16c314` bug's exact shape.
- **34** — a survey found **55 of 75** upstream PWM bindings declare
  THREE `pwm-cells` and only 7 declare two, `seeeduino_lotus`'s among
  them. rigc supported only the minority shape and raised `ValueError`
  on the rest. lotus was the outlier, not the norm (`0373cd2`).
- **35, 36** — real ADC and PWM nexuses on `arduino-r3` and both
  twister boards (`d09fd37`, `06ae4ad`). `grove_light` and
  `grove_pwm_led` now resolve through a carrier on a real platform;
  `grove_pwm_led` had never run anywhere but lotus, which is not a
  twister platform.

**4. Promotion grew its missing category (`0246554`).**
`config.<label>=<value>`, reserved exactly as `socket.<slot>=` already
is. The blocked set was never one shield — it was **every shield with a
jumper or strap the rig must select**; `adafruit_winc1500` was just the
only one in the corpus. It left `EXPECTED_REJECTING` and gained a
twister suite.

### THE PROMOTION GRAMMAR AS IT NOW STANDS — supersedes the 2026-08-13 block

```
<target>     := <element>[;<element>...]
<element>    := <shield>[@rev][:<assignment>...]
<assignment> := socket=<label>          # fixed key, single-plug only
              | socket.<slot>=<label>   # per-slot, plural only
              | config.<label>=<value>  # NEW — strap or routing jumper
              | <device>.<prop>=<value> # params (device DTS LABEL)
```

`config` is the SECOND reserved left-half. Values are the same spelling
a rig.yml uses: a position NAME (`D2`), not an index; an address
(`0x77`), not a domain index. Worked example:

```
west build-rig --rig 'adafruit_winc1500:config.w_irq_jmp=D2' -b nucleo_f401re/stm32f401xe/rig <app>
```

Without it the expander refuses with `phys-position` and names the
domain — non-CS positions are never auto-allocated.

**CS position is NOT selectable, deliberately** (asked and answered
2026-08-15). It comes from `shield,cs-position` (copper-fixed in the
shield) or the allocator drawing on `socket,cs-pool`; there is no
rig-facing grammar, so promotion has nothing to pass through. That is
R4's point: a jumper is a choice physics forces on the user, a pool CS
is a routing decision the tool makes to avoid a clash a hand-written
overlay would create silently. The config sheet turns the allocation
into an instruction. If pinning is ever wanted it needs its own name (a
pool CS is not a config element — no `shield,domain`, no sheet label)
and the allocator must treat a pin as occupied when placing the others.

### 5. The three blockers, worked one at a time — TWO CLOSED

**1. `boards/rigs/` layout — CLOSED, ruled 2026-08-15.** Option A of
`claude/rigs-folder-layout-proposal.md`: a README, no second folder
split, no deletions, and `nucleo_datalogger` STAYS. `boards/rigs/README.rst`
(`c0f776c`) says the folder is the frozen test corpus rather than an
example set, names the four rigs worth reading for shape, and states
what a rig is NOT for — building a single shield is promotion, with
three worked commands verified against the real tool. B (a second folder
split) and C (`rig.yml` metadata) are recorded in the proposal as roads
not taken; C should be picked up by item 7 when `rig-schema.yaml` lands.

**2. Item 29 §8's doc page — CLOSED, and scoped up.** Tobi ruled "the
thing the tree needs now", and the survey showed why: `doc/reference/`
held ONE page, `glossary.rst`, so every devicetree property this project
defines was undocumented and a shield author had to read `shields.py`.

`7c3e8b8` lands slice **1 of 3**: `doc/reference/shield-template.rst`
and `board-socket.rst`, 21 properties, each stating where it appears,
its type and cell shape, **what its absence MEANS** (this project
declares by absence deliberately), what refuses it, and one real
attributed example.

The value is as much the guard as the prose:
`test_dts_vocabulary_drift.py` asserts the documented set and the
property literals in `scripts/rigc/` agree in BOTH directions, so a page
that falls behind the code FAILS rather than misleads. Its scan is
deliberately heading-text-only — a whole-page scan let a cross-reference
on the other page mask a missing entry, which the implementor caught by
running the negative control rather than assuming it.

**Reference slices 2 and 3 are sequenced, NOT started**: (2) the YAML
layer — `rig-file.rst` (rig.yml + content keys, axes, deltas) and
`promotion.rst` (the target grammar); (3) the **42-code diagnostic
catalogue**, which is the one a stuck user reaches for first and should
cite the other three. Brief for slice 1 is
`claude/dts-vocabulary-reference-brief.md` — reuse its shape.

**3. The workspace `.venv` vs `.docvenv` question — STILL OPEN, the
only blocker left.** Three Sphinx packages were installed into the
workspace venv at Tobi's request on 2026-08-14, but
`doc/howto/build-the-docs.rst` says doc deps deliberately do NOT go
there and prescribes a throwaway `.docvenv`. **New evidence**: slice 1
built the docs `-W` clean FROM the workspace venv, so the packages work
and the howto is what disagrees with reality. Back them out and follow
the howto, or amend the howto. One line either way; needs a ruling, not
work.

### PROCESS — what went wrong, so it stops

**My briefs were the weak link, not the work.** Three defects, each
caught by an implementor checking rather than complying:

- Twice I asserted a named build module carried `@pytest.mark.build`
  when it did not — `test_singleton_identity_law.py`, then
  `test_emitted_rejects.py`, which also did not own the goldens I said
  it did. **Verify a module's marking and ownership before naming it in
  a contract.**
- One brief contradicted itself on `EXPECTED_REJECTING` because I
  corrected §4 and left §6 stale.
- The `rigs-folder-layout-proposal.md` claimed a non-default strap
  address could not be promoted — an analysis carried from before
  `0246554`, which I had committed myself an hour earlier. Corrected in
  `be76f60`. **Re-check a claim about capability after any slice that
  changes capability.**

**A golden could carry a machine-specific path and nothing caught it.**
Two did — one naming another session's scratch dir — because
`conftest.py::normalize_dts_provenance`'s regex matches only pytest's
DEFAULT basetemp, and `dts_equiv.py` ignores comments. Fixed and guarded
by `test_golden_path_hygiene.py` (`642883b`). **Regenerate goldens under
the default basetemp, and run that test.**

### Backlog delta

Closed: **29** (incl. its §8 doc debt, `7c3e8b8`), **30**, **33**
(model half), **34**, **35**, **36**. Opened: **31** (grove SPI/UART
deferral, incl. the dual-role connectors), **32** (two missing host
connector types blocking `rpipico_v1`/`xiao_v1`), **37**
(`rigc/board_census.py::_SOCKET_NODE_RE` is brace-non-nesting and
comment-blind — a literal brace in a comment silently drops a socket
from the census), **38** (a nexus map row's FLAGS cell is discarded,
which is why nucleo's Arduino D11 is declared by absence where bridle
declares it with `STM32_PWM_COMPLEMENTARY`), **39**
(`rigc/shields.py::_parse_strap` raises a raw `KeyError` — a config
element declaring neither domain property crashes instead of
diagnosing; item 3's family again), **40** (`plug,positions`'
`optional:` sub-key is parsed into `Position.optional` and never read —
dead vocabulary a binding author would expect to mean something).

Items 39 and 40 were found by READING THE PARSERS to write the
reference pages, and reported rather than fixed because that was a docs
slice. Writing reference documentation is a defect-finding activity;
budget for it.

Unchanged and still the destination: **rig-schema.yaml (item 7) →
BRIDLE MIGRATION (item 9)**.

---

## RESUME (2026-08-13, superseded) — MULTI-PLUG IS DONE, ALL FOUR SLICES. PIN PROMOTION IS BRIEFED, RULED AND PARKED (backlog 28). A NEW VOCABULARY QUESTION IS OPEN AND UNRULED (backlog 29). NEXT = rig-schema.yaml, THEN BRIDLE MIGRATION.

### STATE AT SESSION CLOSE (2026-08-13)

btr-shields HEAD **`198cfeb`**. `main` is **ahead 12 of origin, NOT
pushed**. **Tree is CLEAN** — the two docs the 2026-08-10 block left
out for review were committed (`bb8825b`, `4579313`).

**THIS SESSION WROTE NO CODE.** It was a read-only investigation plus
two documents. **The gate was NOT run** — the last driver-verified
numbers are the multi-plug thread's own (unit **709**, integration
**254**, coverage **93%** vs the 88 floor). Treat those as CARRIED, not
as observed today, and re-derive them from a real run before quoting
them anywhere; a count carried forward from a handoff has been wrong
before.

### THE PREVIOUS BLOCK WAS STALE BY A WHOLE THREAD — read this first

The 2026-08-10 block below claimed HEAD `36bf834`, ahead 21, and a
deliberately dirty tree. **All three were wrong by the time anyone read
it**: the entire multi-plug thread (S1–S4) landed on 2026-08-12 and was
never written into this file. The lesson is the one this file already
states about commit counts, generalized: **read HEAD, the ahead-count
and the tree state from git at the START of a session, never from the
top block here.** This block is a summary, not an authority.

| commit | what |
|---|---|
| `8afb15d` | doc: the 2026-08-10 handoff block (below) |
| `bb8825b` | doc: update bridle-migration — the two carried docs, now committed |
| `4579313` | doc: the multi-plug design notes |
| `4bca9b8` | doc: the multi-plug shield brief |
| `99fd59c` | **S1 — a shield may plug more than one socket at once** |
| `b2b5630` | corpus: quail_can_span, the two-socket click rig on quail |
| `79c6260` | doc: the multi-plug carrier brief |
| `88298f9` | **S2 — a carrier may re-export from more than one parent at once** |
| `05efa12` | corpus: quail_eth_span, eth_click on a two-parent adapter |
| `60a6fc7` | doc: the multi-plug promotion brief |
| `643ead7` | **S3 — a multi-plug shield is promotable: `socket.<slot>=<label>`** |
| `6becaee` | twister: the can_span_click suite — 12 → 13 suites |
| `5a07a9d` | doc: the list-promotion brief |
| `7b6d583` | **S4 — a promotion target may name several shields (`;`)** |
| `198cfeb` | doc: the pin-promotion brief + backlog items 28/29 (this session) |

### THE PROMOTION GRAMMAR AS IT NOW STANDS — read this before touching it

```
<target>     := <element>[;<element>...]
<element>    := <shield>[@rev][:<assignment>...]
<assignment> := socket=<label>          # fixed key, single-plug only
              | socket.<slot>=<label>   # per-slot, plural only
              | <device>.<prop>=<value> # params (device DTS LABEL)
```

`_PROMOTION_OPTS` is still the closed tuple `("socket",)`. A key
containing a `.` is never a member of it — it is a param, or a slot
when the device-half is exactly `socket`. Arity refusals live in
`parse_promotion_opts`, NOT in `check_promotable` (ruling 4's plurality
gate there is retired).

### WHAT THIS SESSION ESTABLISHED — four facts, each driver-run

1. **`adafruit_winc1500` is promotable by the GATE and unusable in
   practice.** `shield.yml` declares `template: true`, it is
   single-plug, `check_promotable` returns None and the desugaring
   materializes — then analysis always fails
   (`error[phys-position]`: the `irq-jmp` routing jumper's position
   must be selected, domain D7/D2). **There is no command line that
   works.** Four plausible spellings were probed and each fails on its
   own sentence. It is the sole member of the singleton identity law's
   `EXPECTED_REJECTING` for exactly this reason. → backlog item 28.

2. **A REAL, UNFIXED CRASH, reachable from an authored rig today.** A
   strap value that YAML does not parse as an int reaches
   `f"{want:#04x}"` at `analyzer/addresses.py:233` and raises an
   unhandled `ValueError` — `Instance.pins` is typed `Dict[str, int]`
   and NOTHING enforces it. Reproduced from a hand-written rig, so it
   is not gated on item 28 and is separable and cheap. The two
   in-domain failures are graceful by contrast (`phys-pin`,
   `phys-position`).

3. **The two rig-side assignment blocks resolve against DIFFERENT
   naming authorities, and no document says so.** `params:` keys are
   the device's DTS **LABEL** (`gb_key: button {}` → `params: {gb_key:}`);
   `pin:` keys are the config element's **NODE NAME**
   (`w_irq_jmp: irq-jmp {}` → `pin: {irq_jmp:}`), with the label
   REJECTED. `loader/params.py:227`'s `_`→`-` normalization is the only
   reason the underscore form resolves at all. → backlog item 29.

4. **A config-element reference is not greppable in either direction.**
   `params: {gb_key:}` shares the literal `gb_key` with the shield;
   `pin: {irq_jmp:}` shares NO literal with it (the shield has
   `w_irq_jmp` and `irq-jmp`). Grepping the underscore form appears to
   work only because both corpus config elements happen to be labelled
   `<prefix>_<underscored node name>` — **a coincidence, not a
   contract.** Also measured: `grep -rln 'pin:' doc/` → no match; the
   Sphinx user tree documents `pin:` nowhere.

### THE ONTOLOGY, CLARIFIED — two concepts and one syntax, not three

Asked directly this session, and worth keeping because the syntax
suggests otherwise. `shield,params`, `config { }` nodes and `pin:` are
**not three peers**:

- **Configuration element** (`config { }`: strap or jumper) — a choice
  **a human realizes with their hands**. `ontology.md` §3's projection
  principle: the DT records the RESULT (`reg = <0x49>`, the routed
  pin), the config sheet records the ACTION ("set **ADDR jumper** to
  state 1"). Neither output is redundant.
- **`shield,params`** — a choice **realized by rebuilding**. Lands in
  the overlay verbatim; its config-sheet appearance is a RECORD, not an
  instruction.
- **`pin:`** — **not a concept.** It is the rig-side assignment syntax
  for configuration elements, both kinds. Every axis has this
  declare/assign split: `shield,plugs`→`socket:`/`sockets:`,
  `config { }`→`pin:`, `shield,params`→`params:`. Three declarations,
  three assignment blocks, three names that match nothing.

**Who resolves it when the rig is silent** is a genuine THIRD axis, not
a property of the concept: a param falls back to its authored default
(none → required, `check_param_invariant`); a strap is **allocated**; a
jumper is **nobody's** → hard error; a CS position is **pool-allocated
with no config element involved at all**. Non-CS positions are
un-allocatable BY RULING, not in principle.

### NEXT — the backlog is the authority, not this list

1. **`rig-schema.yaml`** (item 7) — unchanged, still first. Retirement
   debt for three grammars across rig.yml AND shield.yml, plus
   plurality's `shields:`/`shield:` mutual-exclusion gap.
2. **BRIDLE MIGRATION** (item 9) — the mission goal, every named
   prerequisite done. Re-run `bridle-migration.md`'s triage against
   bridle's CURRENT upstream, not the pinned checkout.

**NEW, both parked deliberately by Tobi rather than queued:**

- **Item 28 — pin promotion** (`pin-promotion-brief.md`). BRIEFED and
  RULED 2026-08-12, all four rulings as recommended. **Do not
  dispatch**; it sits behind the queue above. Two sub-rulings inside
  the slice are still open (§5 the strap type check, §7 the law's
  reject branch).
- **Item 29 — the rig→shield reference vocabulary.** Findings 3 and 4
  above, plus `pin:` vs the model's own `config { }`. **NO BRIEF, NO
  RULING** — three non-exclusive options are recorded and none is
  chosen. **This is the one item that needs Tobi before anything can
  be written**, and it SEQUENCES BEFORE item 28 if the `pin:` →
  `config:` rename is wanted, since item 28 bakes `pin.` into a
  user-facing CLI surface.

Off-sequence and unchanged, all Tobi's call: the **i2c-port binding
decision**, the **tutorial playground honesty debt**, `invert:` (the
last instance-level key with no CLI route, one real user).

### OPEN, CARRIED

- Everything in the 2026-08-10 block's own OPEN list is unchanged
  EXCEPT the two uncommitted docs, which are now committed.
- `RIGC_REFREEZE=1` is still BLOCKED by the harness classifier —
  hand-edit goldens and verify BOTH ways.
- From a session rooted at `/wrk/z/ws-up`, `rig-implementor`/
  `rig-reviewer` are **NOT** agent types; dispatch as
  `general-purpose` on **sonnet** with the role rules folded into the
  prompt. Root at `btr-shields` itself if those types matter.

## RESUME (2026-08-10, superseded) — SHIELD PLURALITY IS DONE AND COMMITTED. BACKLOG ITEM 8 IS CLOSED. NEXT = rig-schema.yaml, THEN BRIDLE MIGRATION.

### STATE AT SESSION CLOSE (2026-08-10)

btr-shields HEAD **`36bf834`**. `main` is **ahead 21 of origin, NOT
pushed** — the 18 carried in plus this session's three. **Tree is NOT
clean, deliberately**: the same two docs as yesterday
(`claude/bridle-migration.md` modified, `claude/multi-plug-shield-design.md`
untracked) are still yours to review, untouched by this session.

**Gate, driver-verified independently, FULL, twice** — once on the
implementor's work, once after the review fixes: mypy **97/0**, unit
**630**, integration **203**, coverage **93%** vs the 88 floor.

| commit | what |
|---|---|
| `576d98c` | doc: the shield plurality brief |
| `605d258` | **a shield.yml may declare N shields in one folder** |
| `36bf834` | **twister: the arduino_lcd plural-folder shields, 10 -> 12 suites** |

### THE RULING THAT SHAPED IT — two discriminators, one per case

**Tobi, 2026-08-10, correcting `bridle-migration.md`'s own prediction**
that the self-filter "must become the `template: true` marker": ONE rule
cannot serve both cases. Where a folder has a shield.yml, `template: true`
discriminates a rig template from a legacy overlay-style shield (bridle
and upstream carry dozens, and they increasingly ship a shield.yml of
their own). Where it has none, the `<basename>.shield` marker
discriminates, exactly as before.

**The census that forced the correction, and re-derive it before trusting
it:** 18 shield.yml in the tree, **all 18** declaring `template: true`
(so the corpus changes hands nowhere), against **12 yml-less FIXTURE
folders** that rely on the marker. Requiring shield.yml for discovery
would have meant authoring 12 new fixture files for no test value. "Zero
new fixture shield.yml" became acceptance criterion 6 for exactly that
reason.

### WHAT WAS ALREADY TRUE — read in the tree, not recalled

Three of the brief's four cost estimates turned out to be already paid:

- **The schema already validates the plural form.** Upstream
  `b836fcdd709` brought `shields:`; this project's own carried commits
  `3f205005b99` and `8da5b3a0f60` put `template:`/`revisions:` inside the
  SHARED `$defs/shieldSchema`, so a plural ENTRY already carries either.
  No zephyr-side change in this slice.
- **cmake already consumes it.** `dts.cmake:705+` collects
  `_rig_shield_candidate_dirs_<name>` per NAME, and its collision
  resolution constructs `${cand}/${shield_name}.shield` from the name.
- **Identity was already name-first.** `_pick_shield` does
  `parsed.get(name)`; only where `name` comes from changed.

The one-shield-per-folder assumption really was two lines of the scan.

### DECISIONS INSIDE THE SLICE, each one a decision rather than a detail

- **`template: true` with no `<name>.shield` is now a loud
  `lang-shield-template` finding** naming the entry and the path it
  expected, where it was a silent skip. The folder's authoring intent is
  known there, unlike the yml-less case.
- **`promotable[name]` records what an entry DECLARED, never that a
  template was found.** Such a name stays in `ymls`/`promotable` while
  never entering `pending`, so `discover_shields` still reports it with
  `template=True` and `check_promotable` still PASSES it — deliberately:
  the scan's own finding already says precisely what is wrong, and a
  second vocabulary would duplicate or contradict it. Promotion then
  fails at load, where the name genuinely cannot resolve.
- **`discover_shields` enumerates `pending` UNION `ymls`.** Without that
  widening, a legacy shield's name would vanish from the census and
  `check_promotable`'s "shield.yml does not declare 'template: true'"
  branch would be unreachable, degrading to "no such shield".
- **`revisions:` is read per ENTRY**, its `owner=` naming the declared
  shield rather than the folder basename.

### THE CORPUS EXAMPLE — `boards/shields/arduino_lcd/`

Ruled in by Tobi rather than fixtures-only. **The folder is named after
neither shield it declares** — that is the slice's real falsifier, since
a folder named after one of them would let the old basename path keep
working. `lcd_char_1602` (GPIO, 4-bit character LCD) and `lcd_tft_24`
(SPI + DC/RESET, CS pool-allocated) are genuinely distinct devices no
existing axis collapses: the RESIDUE case, which is what bridle's
`rpi_pico_lcd` (eleven distinct LCDs in one folder) is made of.

Both plug `arduino-r3`, so both promote on `frdm_k64f` and
`nucleo_f401re` with no `:socket=` disambiguation — and
**`test_singleton_identity_law.py`'s derived domain picked both up with
that module BYTE-UNCHANGED, 14 cases to 16.** That is the strongest
end-to-end evidence in the slice and it cost nothing to state.

**Verified rather than assumed: one `Kconfig.shield` serves a two-name
folder.** `zephyr/cmake/modules/kconfig.cmake` `osource`s a DIRECTORY
glob, so the file is sourced exactly once and both `SHIELD_LCD_CHAR_1602`
and `SHIELD_LCD_TFT_24` turn on. **Not demonstrated, and named rather
than skipped:** per-name `<name>.conf` picking — neither shield ships a
`.conf`, so nothing forced a positive confirmation of that path.

### TWO FINDINGS APPLIED AFTER REVIEW — one reviewer's, one driver's

1. **Reviewer's:** `promotable`'s "declared, not resolvable" nuance was
   undocumented and pinned by nothing. Documented on the field, pinned by
   `test_discover_shields_reports_a_template_entry_whose_file_is_missing`.
2. **Driver's, and the reviewer missed it:** a `shields:` block that is
   **not a list** — the one-dash-short typo — was dropped **SILENTLY**.
   Every name in the folder vanished from the namespace with no
   diagnostic, and the only later symptom was an instance's `shield:`
   reference failing to resolve, a diagnostic blaming the innocent rig.
   Now a `lang-schema` error with fixture and byte-exact golden
   (`shield-plural-not-a-list`).

**The implementor's report was WRONG about its own behaviour**, and its
open question for Tobi rested on that error: it claimed a broken
`template: true` entry was "excluded from `discover_shields()` entirely",
but `ymls`/`promotable` are written BEFORE the file check, so the name
survives into the census. Driver ran it to find out; the reviewer reached
the same place independently. **An implementor's account of what it built
is a hypothesis** — this is the third slice running where that held.

### GOLDEN IMPACT — classified in advance, and it held

One stderr golden changed: `shield-node-name-mismatch/stderr.txt`, one
line, hand-edited (`RIGC_REFREEZE=1` is still BLOCKED by the harness
permission classifier) and verified both ways. Five new golden dirs are
pure additions. **No `context.cmake`/`RIG_DEPENDS` movement for the 14
existing shields** — the new corpus folder is additive and nothing
existing references it.

### A PROPERTY OF THE REJECT-FIXTURE FAMILY — know it before writing another

Those fixtures' rigs declare `instances: []` and `run_expand` resolves no
real board, so **expand exits 1 EITHER WAY** — via the intended
diagnostic, or via `phys-board` once the load gets that far. The
`assert result.returncode != 0` line is therefore nearly vacuous; the
stderr assertions and the golden are what discriminate. Found because the
driver's own first negative control ran the fixture from OUTSIDE the tree
and produced a `phys-board` exit that proved nothing. **Run controls
in-tree.**

### A BRIEF-WRITING CORRECTION, the driver's own error

The brief's §9 called `test_singleton_identity_law.py` "the one
build-marked module". **It carries no `@pytest.mark.build` at all** — its
own docstring says so — and neither does `test_emitted_rejects.py`. This
slice has **no build-marked module observing its criteria**, which is a
fact about the slice, not an omission: everything it changes is
observable without a toolchain. Naming a build module by reflex is the
failure mode; check the marker. Recorded in the brief's own §9.

### NEXT — the standing queue, one item shorter

1. **`rig-schema.yaml`** (backlog item 7) — retirement debt for THREE
   grammars (`board:`/`sockets:`, `dt-includes:`), scoped across both
   rig.yml AND shield.yml. **Shield plurality adds to its shield.yml
   half**: `shields:`/`shield:` mutual exclusion is enforced only by the
   zephyr-side jsonschema during a cmake build, never by rigc's own
   `parse_marked` — a folder authoring BOTH keys silently takes
   `shield:` today (named in `_shield_yml_entries`'s docstring, out of
   scope by the same reasoning that queued every other unknown-key rule
   here).
2. **BRIDLE MIGRATION** (item 9) — the mission goal. **Every named
   prerequisite is now done.** Re-run the folder-by-folder triage in
   `bridle-migration.md` against bridle's CURRENT upstream state, not the
   pinned checkout, before estimating cost off its table.

Off-sequence, unchanged and all Tobi's call: **multi-plug shields**
(needs its own brief; root a session at `btr-shields` itself so
`rig-implementor`/`rig-reviewer` resolve), the **i2c-port binding
decision**, the **tutorial playground honesty debt**.

### OPEN, CARRIED

- **The two uncommitted docs** above, both yours to review, unchanged.
- **Cross-folder / cross-root duplicate shield names** stay last-wins in
  the loader, with `cmake/dts.cmake`'s own warn-and-pick for the real
  `adafruit_data_logger` collision. Deliberately NOT hardened — only the
  within-one-`shields:`-list duplicate is an error.
- **Per-name `<name>.conf` picking is undemonstrated** (above).
- Everything else carried from the 2026-08-09 block below is unchanged:
  `_parse_exposed`'s literal 3-kind vocabulary, the unquoted
  promotion-value repr leak, `AxisDecl.boards`/`.sockets` dead fields,
  the stale `/tmp/rigc-*` dirs, `doc/tutorials/give-a-board-a-socket.rst`.

### DISPATCH CONTRACT — confirmed again, unchanged

From a session rooted at `/wrk/z/ws-up`, `rig-implementor`/`rig-reviewer`
are **NOT** agent types; both dispatches this session ran as
`general-purpose` on **sonnet** with the role's rules folded into the
prompt, and both worked. The reduced gate contract held.

## RESUME (2026-08-09, superseded) — §9.6 IS FULLY DONE, BOTH PARTS. MULTI-BUS SOCKETS LANDED. TWISTER GAINED THREE SUITES, INCLUDING A NEW REAL GROVE BOARD. MULTI-PLUG SHIELDS IS A NEW, PAUSED DESIGN THREAD. NEXT = rig-schema.yaml.

### STATE AT SESSION CLOSE (2026-08-09)

btr-shields HEAD **`37ccbdf`**. `main` is **ahead 17 of origin, NOT
pushed** — nine new commits this session on top of the 8 already carried.
**Tree is NOT fully clean, deliberately** — see the end of this block.

**Gate, driver-verified independently, FULL, four times:** mypy **96/0**,
unit **623**, integration **195** (including the build tier), coverage
**93%** vs the 88 floor.

| commit | what |
|---|---|
| `067b4e6` | **§9.6 part 1** — the parameter vocabulary moves to the shield |
| `eef9836` | doc: the multi-bus-socket brief |
| `b9c3be3` | **a socket may offer more than one bus of the same kind** |
| `96d1809` | doc: the promoted-shield-params brief (§9.6 part 2) |
| `617f545` | **§9.6 part 2** — the promotion CLI params grammar |
| `84d0eb8` | **twister: the pilot_alt_button shield suite** — 7 -> 8 |
| `37ccbdf` | **a real upstream grove board (m5stack_nanoc6), grove_btn/grove_led suites** — 8 -> 10 |

### §9.6 IS ENTIRELY DONE — both the vocabulary move and the CLI grammar

Rig-level `dt-includes:` retired wholesale (measured zero users under the
narrower "gains a second source" reading — same shape as the `board:`
retirement). The vocabulary is now the declaring shield's own
`shield,param-includes`. A promoted shield with a required, undefaulted
param can now be satisfied from argv:
`--promote 'grove_btn:gb_key.zephyr,code=INPUT_KEY_0'`. **`test_singleton_
identity_law.py`'s `EXCLUDED`, `{"grove_btn", "pilot_alt_button"}` at the
start of this session, is now `set()`** — verified as a real byte-for-byte
comparison against a real rig.yml carrying the identical assignment, not
an emptied exclusion.

**Twister gained an 8th suite for it**, `tests/shields/pilot_alt_button/`
(`84d0eb8`). Verified directly with `west twister --build-only` on both
target platforms before committing, not assumed from the pattern match.

`grove_btn` looked stuck the same way — its only CORPUS rig
(`lotus_buttons`) targets `seeeduino_lotus`, whose base board lives in
the `bridle` module, still not a twister platform here. **But that
turned out to be a fact about the corpus, not about grove connectors in
general** — scanning `boards/` for real grove content upstream (asked
for explicitly, not initiative) found several m5stack boards ship a
genuine `grove-header` devicetree fragment as part of the standard
zephyr tree. `boards/extend/m5stack/m5stack_nanoc6/` (`37ccbdf`) wraps
one of them (RISC-V, ESP32-C6 — picked over the xtensa `m5stack_atom_
lite` specifically because no xtensa toolchain is installed here) under
this project's typed `socket,grove` contract, same pattern as every
other extension. **Now 10 twister suites, not 8** — `grove_btn` (via
§9.6 part 2's own CLI grammar) and `grove_led` both build and link a
real `zephyr.elf` there.

**One real, previously-unencountered Kconfig limitation surfaced and
was fixed extension-locally.** `boards/m5stack/m5stack_nanoc6/Kconfig(.m5stack_nanoc6)`
selects two HPCORE-critical symbols (`SOC_ESP32C6_HPCORE`,
`HEAP_MEM_POOL_ADD_SIZE_BOARD`) conditionally on the BASE board's own
qualifier-exact symbol, which the `rig` variant's separately-generated
symbol never satisfies — confirmed by diffing a plain build's `.config`
against the rig variant's, not guessed. This is the FIRST rig extension
on a board with a multi-level qualifier (SoC + cpucluster); every prior
one is single-level, where this exact-match pattern cannot arise.
**Check for this again** the day any future extension targets another
multi-cpucluster SoC.

**A real regression in an ALREADY-COMMITTED test**, found by running
the gate rather than assuming the new board was inert:
`test_boards_for.py`'s `..._required_param_answers_once_assigned`
asserted `--boards-for grove_btn:gb_key.zephyr,code=...` answers EMPTY —
true only because `seeeduino_lotus`'s eight sockets made it the sole,
ambiguous candidate. `m5stack_nanoc6` offers exactly one, so the answer
is no longer empty. Fixed in the same commit.

**Two more grove shields deliberately NOT added**, verified rather than
assumed free: `grove_light` (ADC) and `grove_servo` (PWM) fail correctly
(`error[phys-function]`, not a crash) against this socket, which is
digital-only, matching the real upstream fragment it wraps. Adding
either needs ESP32-C6's real ADC-channel-to-GPIO mapping, which nothing
in this zephyr tree currently wires up to cross-reference — recorded in
`tests/shields/grove_led/README.rst` rather than guessed at.

### MULTI-BUS SOCKETS — new capability, fixture-proven, zero real users yet

`socket,<kind>-<role>` (still a bare phandle) names an additional bus of a
kind a connector type offers. Ownership ruling (Tobi, 2026-08-09): the
role name belongs to the CONNECTOR TYPE, never the board — same status as
GPIO position numbering. `cs_pool` moved from `BoardSocket` onto `BusRef`
(CS numbering is a fact of a bus, not the socket as a whole). New shared
`scripts/rigc/buskind.py` (`is_bus_kind`/`bus_kind_of`) replaces three
independent kind-prefix checks that had started to drift.

**Out of scope, left unwidened and NAMED rather than silently skipped:**
`shields.py`'s `_parse_exposed` (carrier/mux re-exported-socket parsing)
still has its own literal 3-kind vocabulary — only matters if carrier
composition itself ever needs named bus variants, which is its own
future slice, not a defect today.

### TWO REVIEW ROUNDS EACH, AND EACH FOUND SOMETHING REAL

**Multi-bus sockets' review found a genuine regression, not polish.**
Moving `cs_pool` onto `BusRef` meant `compose_socket`'s pass-through
branch — which used to alias the parent socket's bus object outright —
started leaking the PARENT's own CS pool into a composed socket of a
DIFFERENT connector type. `arduino_uno_click`'s exposed mikrobus-type
socket inherited the arduino parent's `[16,15,14]` instead of falling
back to mikrobus's own `[2]`, breaking `frdm_eth_nest` and rewriting the
permanently byte-exact `frdm_cs_clash` reject golden. Fixed by building a
fresh `BusRef` at the pass-through site carrying `exposed.cs_pool` (the
carrier's own authored override) instead of aliasing the parent's — which
also resolved a second, wrongly-diagnosed finding from the FIRST review
pass (`ExposedSocket.cs_pool` was reported "orphaned"; it wasn't, it just
needed to travel through this branch correctly).

**§9.6 part 2's review found no regression at all — but a real scope
gap the brief's own file list missed.** The implementor traced every
CALLER of `parse_promotion_opts`/`promote_shield` rather than trusting
the brief's list, and found two the brief never named:
`west_commands/rigs.py`'s `--boards-for` and `--explain`, which would
have hit `AttributeError` the moment the parser's return type changed
from a flat dict to a dataclass. Fixed, and threaded `params` through
both symmetrically rather than leaving it silently dropped. **The gap
the review DID catch was exactly the test coverage for that fix** —
the code was right, nothing pinned it.

**The recurring lesson, worth restating because it keeps recurring:**
run/trace the actual callers and tests; a brief's own scope list is a
prediction, not a guarantee. Every dispatch this session that found an
out-of-list item found it by running mypy/pytest or grepping call sites,
never by re-reading the brief harder.

### MULTI-PLUG SHIELDS — a NEW design thread, paused for a fresh session

Ideation surfaced a second, structurally BIGGER gap while multi-bus
sockets was in flight: **a shield mating more than one socket at once is
not representable today** — `Shield.plugs: str`, `Instance.socket:
Optional[str]`, and `SocketResolution.sockets` (keyed by `inst.name`
alone) are all hard 1:1. Real motivating hardware (Tobi's own past): a
carrier plugging into BOTH a mainboard's arduino AND mikrobus headers at
once, re-exporting the combined connections through a third connector.

Captured in **`claude/multi-plug-shield-design.md`** — NOT a brief, no
ruling, no scope trace verified end-to-end. That document's own **RESUME
HERE** section says exactly how to pick it up: root a fresh session at
`/wrk/z/ws-up/btr-shields` itself (not the west topdir) so `rig-
implementor`/`rig-reviewer` are real agent types there — confirmed this
session that they are NOT discovered from `/wrk/z/ws-up`, and there is no
mid-session fix, only a fresh session rooted correctly. Concrete next
action recorded there: trace how far `sockets.get(inst.name)`'s
single-socket assumption propagates through `cs.py`/`addresses.py`/the
emitter, the same file-by-file way the multi-bus brief's own scope trace
was built — and re-verify that document's `model.py`/`analyzer/sockets.py`
citations first, since both changed shape under this session's multi-bus
work after that document's §2 was written.

### DISPATCH CONTRACT NOTE — confirmed, not assumed, this session

`rig-implementor`/`rig-reviewer` are still **NOT** registered as agent
types from this session's root (`/wrk/z/ws-up`) — every dispatch this
session ran as `general-purpose` with the role's `.claude/agents/*.md`
rules folded directly into the prompt. This was tested directly this
session (previous handoffs had asserted both states at different times
without verifying): project-scoped subagent discovery is fixed at
session launch and only walks UP from the launch directory, never down
into a subdirectory — so a session rooted at the west topdir will never
see `btr-shields/.claude/agents/` no matter what. Root a session directly
at `btr-shields` if those agent types matter for a dispatch.

### NEXT — the standing queue, unchanged in order

1. **`rig-schema.yaml`** (backlog item 7) — now carries retirement debt
   for THREE grammars (`board:`/`sockets:`, and now `dt-includes:`),
   scoped across both rig.yml AND shield.yml.
2. **Shield plurality** (item 8) — unaffected by the bridle correction
   below; `load_shield_library`'s one-per-folder lookup still needs the
   actual implementation.
3. **BRIDLE MIGRATION** (item 9) — the mission goal; every prerequisite
   is now done.

Off-sequence: **multi-plug shields** (above, needs its own brief before
it can be dispatched), the i2c-port binding decision, the tutorial
playground honesty debt — all still Tobi's call, all unchanged from
before this session.

### OPEN, CARRIED

- **Two docs left deliberately uncommitted** — both yours to review:
  - `claude/bridle-migration.md` — a dated correction: upstream bridle
    has adopted shield.yml for most of its shields since the migration
    triage was written (the pinned checkout doesn't reflect this yet).
    Shield plurality's own implementation work is UNAFFECTED either way.
  - `claude/multi-plug-shield-design.md` — the paused design thread
    above.
- Small debt surfaced by review this session, named rather than fixed:
  unquoted CLI-supplied promotion values can leak an internal repr into
  a diagnostic on a YAML-parse failure — pre-existing, confirmed to
  affect the old `socket:` grammar identically, not introduced this
  session; worth a future slice, not urgent.
- Everything else carried from the 2026-08-08 block below is unchanged:
  `AxisDecl.boards`/`.sockets` dead fields under the model.py freeze,
  331 stale `/tmp/rigc-*` dirs, the i2c-port binding decision, the
  tutorial playground debt, `doc/tutorials/give-a-board-a-socket.rst`'s
  stale note.

## RESUME (2026-08-08, superseded) — BOARD-AS-COORDINATE IS **DONE**. TWISTER IS IN. NEXT = §9.6 PART 1, ALREADY BRIEFED.

### STATE AT SESSION CLOSE (2026-08-08)

btr-shields HEAD **`4a6c701`**. Tree clean.

**`main` is ahead 7 of origin, NOT pushed — and the previous block's
"ahead 27+1" was STALE.** `origin/main` had moved to `7a9d760` since:
those 27 got pushed at some point outside a session. **Read the number
from `git rev-list --count origin/main..main`, never from a prior
handoff.** Today's seven are the only unpushed commits.

**Gate, driver-verified, FULL, after every slice:** mypy **94**, unit
**599**, integration **187**, coverage **92%** vs the 88 floor.

The unit/integration counts went 617→627→599 and 184→194→187 across the
day: the socket grammar ADDED tests, the board-grammar retirement deleted
41 test functions whose subjects ceased to exist. **A falling count is
correct here** — read it against what was deleted, not as a regression.

| commit | what |
|---|---|
| `6c8e14e` | twister: rig board targets loadable + first shield suite |
| `8b6a1f1` | twister: the remaining promotable shields, and why only two |
| `8887163` | `--boards-for` resolves promoted shields |
| `12e91e7` | rigc's workdir moves into `--out-dir`, out of /tmp |
| `bde0b0a` | **`--rig <shield>:socket=<label>`** + four mikrobus suites |
| `7c724bd` | **the board declaration grammar is RETIRED** |
| `4a6c701` | doc: the param-vocabulary brief + backlog corrections |

### THE DIRECTION IS FINISHED — backlog item 10 is DONE

"The board is no longer part of the rig definition" is now literally
true. §9.5's six slices made it an independent coordinate and emptied the
corpus; `7c724bd` retired the grammar itself. **Nothing in rig.yml names
a board.** `resolve_board`'s five S2 coherence rules, `reject_metadata_
keys`, `variant_metadata_differs`, list_rigs' whole board-resolution half
and the `--boards-for` placeholder wart are all gone.

### TWISTER INTEGRATION TESTING EXISTS NOW — `tests/shields/`, 7 suites

New top-level `tests/` (twister territory — the python tests stay in
`scripts/rigc/tests`). Run it:

```
west twister -p frdm_k64f/mk64f12/rig -p nucleo_f401re/stm32f401xe/rig \
             -p mikroe_quail/stm32f427xx/rig -T btr-shields/tests
=> 7 scenarios (21 configurations), 10 built (not run), 11 filtered
```

**The bug that blocked it, and it fails SILENTLY:** twister's legacy
board-yaml loader resolves each file by looking its `identifier` up in the
board-target alias table (`platform.py:322-329`) and `continue`s on a
miss. That table only holds SLASH-form targets. All four rig extension
yamls spelled it with underscores (`frdm_k64f_mk64f12_rig`), so every
`/rig` platform was dropped without a word — the only symptom was a
downstream "unrecognized platform". Every one of zephyr's 843
slash-carrying board yamls uses the target form. **Nothing else was
missing**: `board.yml`'s extend/variants was correct, and the module's
`board_root` IS honoured by twister (`environment.py:436-442`).

**`seeeduino_lotus` is NOT a twister platform here** and that is not a
twister problem: its base board lives in `bridle`, which this workspace's
`west.yml` does not import. The cmake side finds bridle by another route
(the build log says "Loading Bridle default modules"), which is why
`--boards-for lotus_buttons` still answers.

### WHY ONLY 7 SUITES — the census, probed not reasoned

3 of 14 shields were promotable when the day started; 7 by the end. Each
exclusion was probed with `west build-rig --cmake-only`:

- **`grove_btn`, `pilot_alt_button`** — required `shield,params`. §9.6.
- **`eth_click`, `flash_click`, `temp_click`, `temp_hum_click`** — plug
  mikrobus, quail offers FOUR. **A THIRD category nobody had named: blocked
  by socket AMBIGUITY, not params** — and the params grammar would never
  have unblocked them. `:socket=` did, same day.
- **`grove_led`, `grove_light`, `grove_servo`** — plug grove; only lotus
  has grove sockets, and it has NINE, so the ambiguity refusal would apply
  even if bridle were in the manifest. Two independent blockers.
- **`i2c_sensor`** — plugs `i2c-port`, which no BOARD offers; only
  `i2c_mux` does, as a carrier. Not promotable standalone anywhere.
- **`adafruit_winc1500`** — `error[phys-position]` on `wifi: irq-gpios`.
  Already S4's one `EXPECTED_REJECTING` shield.

`i2c_mux` needs `CONFIG_I2C_TCA954X=n`: promoted alone the mux has NO
channel nodes (its four channels are SOCKETS with nothing plugged in), and
zephyr's `i2c_tca954x.c` cannot compile against a childless mux
(`tca954x_channel_init` is referenced only from `TCA954x_CHILD_DEFINE` →
`-Werror=unused-function`). No application Kconfig fixes it. Behind that
wall is a second: both its init priorities default to `I2C_INIT_PRIORITY`
while the driver `BUILD_ASSERT`s a strict channel > root, so a TCA954x
never builds on stock defaults at all.

### RULINGS (Tobi, 2026-08-08)

1. **Promotion options are PROMOTION-ONLY.** A persisted rig has N
   instances, so `socket=` could not say which. Refused by `list_rigs` so
   the cmake seam and both query surfaces share one message.
2. **`socket` alone to start**, everything else later. `_PROMOTION_OPTS`
   is a closed tuple.
3. **Explicit `key=value`, no bare-word shorthand.**
   `flash_click:quail_sock1` is an error naming the known keys.
4. **`dt-includes:` retires WHOLESALE** — §9.6's "gains a second source"
   widened to "the source MOVES". See below.
5. **Keep the `phys-board` move** for the no-board-anywhere diagnostic.
6. **A stray retired key is SILENTLY IGNORED for now.** Schema tightening
   for rig.yml AND shield.yml is queued as its own slice (backlog item 7,
   which grew to hold this debt).

### NEXT — §9.6 PART 1 IS BRIEFED AND READY TO DISPATCH

**`claude/param-vocabulary-brief.md`.** The parameter vocabulary moves to
the shield that declares the parameter:

```dts
shield,params = "zephyr,code";
shield,param-includes = "zephyr/dt-bindings/input/input-event-codes.h";
```

**Ruling 4 came from a measurement, and it is worth re-reading before
touching this:** under the narrow "second source" reading, rig-level
`dt-includes:` would have had **ZERO live users** — exactly one corpus rig
declares it (`lotus_buttons`, for the very case this moves), and the only
other param assignment in the corpus is a bare integer literal that
`is_int_literal` short-circuits. Three of six fixture users exist only to
test the grammar. Same shape as `board:`.

**The rejected alternative fails SILENTLY, which is why the brief records
it:** recovering the shield's own `#include`s via `source_files()` would
never find `input-event-codes.h`, because a macro-only header contributes
no node and no property. `linemarker_files()` does see it but drags in
every transitively opened header — `zephyr,code: GPIO_ACTIVE_HIGH` would
then resolve, weakening the exact rules the machinery enforces.

**Its load-bearing criterion:** `goldens/lotus_buttons/context.cmake`
byte-UNCHANGED. `RIG_DEPENDS` reaches that header through the RIG today
and must reach it through the SHIELD after, or editing a keycode header
stops retriggering configure.

Then **part 2**: the `<device>.<prop>=<value>` CLI surface. Its slot
exists — `_PROMOTION_OPTS` is the closed set it joins, and `:` is already
the separator PRECISELY because `zephyr,code` contains a comma. Part 2's
acceptance criterion is S4's `EXCLUDED` assertion
(`test_singleton_identity_law.py:177`) SHRINKING; it must not shrink in
part 1.

Then the standing queue: **rig-schema.yaml** (item 7, now carrying the
unknown-key debt for two retired grammars), **shield plurality**,
**BRIDLE MIGRATION**.

### LESSONS THIS SESSION, each paid for

- **The brief's scope list was INCOMPLETE AGAIN** — six modules
  (`loader/axes.py`, `loader/fragments.py`, `loader/documents.py`,
  `cli.py`, `promote.py`, `cmake/boards.cmake`) were invalidated and none
  were named. The dispatch found them by RUNNING mypy/pytest, not reading
  the diff. The rule holds; the discipline is to run.
- **A test can pass for the wrong reason and only mutation shows it.** The
  new `:socket` variant-refusal test asserted `returncode != 0` and
  `"variant" in stderr` — which still passed with `check_promotable`
  deleted, because the LOADER rejects a variant anyway, later and for an
  unrelated reason. It now asserts `check_promotable`'s own sentence.
- **An existing whole-line golden test caught a real bug in new code.**
  `{PROMOTED}` first rendered the revision too; since `{REVISION}` already
  travels as `--revision`, that desugared to `shield: i2c_sensor@2@2`.
  `test_cmakeformat_line_for_a_revved_promoted_shield` failed because it
  pins the WHOLE line, not just the key under test.
- **A reused build dir gives a FALSE NEGATIVE.** Four "failures" of the
  socket grammar were a stale `-d` directory keeping the old cached `RIG`.
  Remove the build dir at the START of a probe loop, not the end.
- **The /tmp pile was NOT a leak.** D10 keeps the workdir on every
  non-zero exit ON PURPOSE (a cpp failure's diagnostic quotes a path
  inside it). `test_emitted_rejects.py` alone creates exactly 39 per run.
  The defect was that it ESCAPED pytest's `tmp_path`; it now lives at
  `<--out-dir>/rigc-generated` and is reaped by whatever owns the build
  dir. Verified: full integration run, `/tmp/rigc-*` 331 → 331.
- **Counting files vs counting lines, a third time.** The S6 brief's "36
  fixture rigs declare `board:`" was a repeated VALUE line; the truth was
  45 files + 2. Re-derive every count and cite the command.

### DISPATCH CONTRACT — one correction to the old note

**`rig-implementor` IS available as an agent type from this project root**
(the previous block said it is not, and dispatches run as
`general-purpose`). It was used successfully today with an explicit
`model: sonnet`. Its definition still says "run `check.sh`" and still
points at the stale `/wrk/z/ws-up/claude/rigs/` — **correct both in every
prompt** until someone edits the file. The reduced contract (implementor
runs mypy + unit + non-build integration + the named build modules; the
driver runs the full gate once, after review) worked again.

`RIGC_REFREEZE=1` is still BLOCKED by the harness permission classifier.

### OPEN, CARRIED

- **`AxisDecl.boards`/`.sockets`** are dead fields kept under the
  `model.py` freeze. **`{BOARD}`** stays in the cmakeformat contract,
  unconditionally `NOTFOUND`, with a test pinning it.
- **331 stale `/tmp/rigc-*` directories** from before `12e91e7`. Harmless,
  never cleaned — say so before deleting.
- **The i2c-port binding decision** (production
  `dts/bindings/connectors/i2c-port.yaml` never declares `socket,i2c`; the
  S4 fixture board carries a patched local copy). Still Tobi's call.
- **The tutorial playground honesty debt** — `acme-rigs` in tutorials
  2/3/5/6 is narrative, not tree content.
- `doc/tutorials/give-a-board-a-socket.rst` is still accurate but does not
  mention that `--boards-for` takes a shield name now.

## RESUME (2026-08-06d, superseded) — §9.5 IS COMPLETE. S6 LANDED. NEXT = RETIRE THE BOARD GRAMMAR.

### STATE AT SESSION CLOSE (2026-08-06d)

btr-shields HEAD **`40c8d10`** plus the doc commit this block ships in.
`main` is **ahead 27+1 of origin, NOT pushed** — carried since
2026-08-04, still Tobi's call. Tree clean.

**Gate, driver-verified, FULL:** mypy **94**, unit **617**, integration
**184**, coverage **92%** vs the 88 floor.

184 reconciles: 187 after S5, minus the 4 tests S6 retired with the
mechanism they covered, plus the new no-board census test.

**`board-as-coordinate-brief.md` §9.5 is DONE — all six steps landed.**
A rig names a topology; the invocation names the board. `ard_datalogger`,
the dual-host rig that motivated the whole direction, is now literally
`rig: name: ard_datalogger`, built twice by supplying a different `-b`.

### WHAT LANDED — S6 (`40c8d10`)

18 `board:` keys across 17 rig.yml files gone. The harness's board source
is now an explicit `RigCase.board` (the ruling §9.4 never made — see the
brief's §3 for the two rejected alternatives).

**Tobi ruled DURING review that the grammar goes too**, overriding §9.4's
"keep inference as a fallback" staging: *"that's confusing in the long
run and besides us noone will remember it or miss it."* S6 took the half
that belongs with the data — `cmake/boards.cmake`'s inference, the
`RIG_INFERRED_BOARD` marker and the rig-swap guard — **in the same change
as the four tests covering them.** Dropped, not adapted: the guard's
failure mode needed a rig with a declared board, so it *ceased to exist*
rather than merely stopping being tested. Mechanism and tests together is
what keeps "no live code left untested" true.

**Predictions that held, and one that did not:**

- §4's prediction HELD — **no `RIG_BOARD` value moved.** The golden diff
  is 4 files, all `ard_datalogger`. §9.4's "the 19 goldens refreeze"
  counted goldens CARRYING the key, not ones whose value moves.
- §9.4's own numbers were WRONG: 18 real `board:` keys across 17 files,
  not 19 (a naive grep counts comment lines); `ard_datalogger` carried
  **two**, not three; `pilot_variants` was ALREADY the target shape, so
  the collapse touched exactly one rig.
- The dispatch's list of broken tests was a READING, not a run — off by
  one in each direction. **Run the module rather than reason about it.**

**The one test the inference deletion broke that nobody predicted:**
`test_resolved_empty_rig_equals_plain_board`. The `empty_rig` FIXTURE
still spells `board:` and was the only call site relying on inference to
supply it. Every other `_run_build` call already threaded `board=`
(swept, not assumed).

**Fixed in passing:** a STATUS line that read `board: ` with nothing after
it for every promoted shield — it printed `_RIG_RESOLVED_BOARD`, which is
ALWAYS empty for a shield. It prints `${BOARD}` now.

### NEXT — retire the board grammar, its own slice

Scope MEASURED (see `board-coordinate-s6-brief.md` §11):

- **36 fixture rigs declare `board:`** — not 17; the corpus was the small
  half. Each needs its board injected via the harness.
- **10 fixtures exist to test the declaration grammar**, each with a
  byte-exact reject golden. ~8 die outright — a user-facing diagnostic
  family disappearing, byte-exact BY RULING, so it wants its own
  classified diff. `unknown-board` and `unmapped-socket` need judgement
  (an *injected* unknown board is still a real error).
- Production: `resolve_board`'s five S2 coherence rules, `SocketBinding`,
  `list_rigs.py`'s board resolution, the `{BOARD}` cmakeformat key.
  **`RIG_BOARD` STAYS** — the board actually built is still a fact.
- **The `--boards-for` placeholder-board wart disappears** rather than
  needing documentation: S6 had to inject an inert placeholder so
  `resolve_board` would not reject every target; with no board required
  to load a rig, the census needs no fake one.

Then the standing queue: **rig-schema.yaml** (backlog item 7), **shield
plurality**, **BRIDLE MIGRATION**. Off-sequence: **§9.6's params CLI
grammar**, **the i2c-port binding decision**, **the tutorial playground**.

### A BRIEF-WRITING RULE, learned twice in two slices

S5's §7 named the module its code lived nearest; S6's §9 named the
modules that OBSERVE the acceptance criteria. **Both were incomplete.**
The rule is: *name the modules that observe the criteria AND the modules
the change invalidates.* S6's nine broken tests were in a module neither
brief would have listed.

## RESUME (2026-08-06c, superseded) — S4 AND S5 LANDED. NEXT = S6, THE LAST STEP OF §9.5.

### STATE AT SESSION CLOSE (2026-08-06c)

btr-shields HEAD **`03a6928`** plus the doc commit this block ships in.
`main` is **ahead 25+1 of origin, NOT pushed** — carried since 2026-08-04
and still Tobi's call. Tree clean.

**Gate, driver-verified, FULL, three times this session:** mypy **94
files**, unit **617**, integration **187**, coverage **92%** vs the 88
floor.

| commit | what |
|---|---|
| `5040297` | doc: the S4 brief + the correction it makes to §9.1 |
| `6d743a3` | doc: the tutorial series, tutorial 4's not-yet warning retired |
| `0cbfbed` | **S4 — the singleton identity law, as a census** |
| `7ba3cf4` | doc: the S5 brief, with the collapse ruled into S6 |
| `0d0e275` | doc: this handoff block |
| `03a6928` | **S5 — content migration to conventional socket labels** |

Counts reconcile: 172 (post-S3b) + 13 + 1 = 186 after S4, then +1 +1 −1
= 187 after S5. **Note the 170 recorded in the 2026-08-06b block was that
session's gate number, not its total** — two tests landed after it ran.
Read a count as what the FULL integration run reports.

### WHAT LANDED — S4, `board-coordinate-s4-brief.md`

The law, at expand level, both sides named identically with the fixture
given by PATH (`expand <path>` does no namespace resolution — the only
way one name resolves both ways without tripping S3a's both-paths rule).
Parametrized over a DERIVED domain: 12 eligible shields, `grove_btn` and
`pilot_alt_button` excluded and asserted as such so the set visibly
shrinks when §9.6's grammar lands. One declared `RIG_DEPENDS` exemption.
One build-marked `dts_equiv` cross-check.

**Verified, not assumed:** the exemption absorbs nothing else — for
`adafruit_data_logger` the two sides differ by exactly their own two rig
documents and share 11 dependencies exactly.

### FOUR REVIEW FINDINGS, ALL DRIVER-APPLIED — and the pattern is the same one again

1. **The census leaked a `mkdtemp` per collection.** D10 was its own
   slice and /tmp is tmpfs here, so it was charged to RAM. 15 leaked
   dirs had already accumulated in one session. `TemporaryDirectory` now.
2. **The reject branch was unpinned.** Both sides rejecting identically
   satisfies the law but compares stderr and NO artifact. 11 of 12
   compare artifacts today and nothing said so — the census could have
   drifted wholesale into the branch that checks nothing.
   `EXPECTED_REJECTING` pins the partition per shield.
3. **`discover_shields()` called with the implicit narrow default** —
   literally the shape of the S3a defect that made the namespace rule
   fail open. Same scope, now passed explicitly with the reason.
4. **The build-marked cross-check had no negative control.**

**Finding 4's first fix was itself vacuous, and that is the lesson worth
carrying: `dts_equiv` EXCLUDES THE ROOT NODE** (its own docstring says
so). The control perturbed a root property and passed while proving
nothing — the exact trap it existed to catch. It disables the first
enabled node instead; gutting `dts_equiv` to exit 0 now fails precisely
that test. **Any future control built on a root-level fact is vacuous.**

### THE BRIEF'S OWN MUTATION 2 IS A PARTIAL CONTROL — recorded so nobody re-derives it

§2.4 said dropping socket-less-ness "must fail on inference". Driver-run,
it fails **8 of 12**. The four arduino-r3 shields pass, because there the
explicit socket IS the one inference picks, so both sides emit identical
artifacts. **The law is RIGHT to pass** — it compares outputs, not source
text. The brief overstated what that mutation can prove; the dispatch
found the shape of this and reported the result as a clean catch, which
is why the driver ran it independently.

Mutation 1 also corrected the brief: the instance name reaches
device-label prefixes, so `rig-gen.overlay` diverges before
`config-sheet.md` does.

### OPEN, AND IT IS A PRODUCT DECISION — the i2c-port binding

**Production `dts/bindings/connectors/i2c-port.yaml` never declares
`socket,i2c`**, so edtlib rejects any real board-level i2c-port socket
node. `i2c_mux.shield` sets that property today but is parsed via bare
dtlib, which never schema-checks — so the gap had never been exercised
until S4 needed a real one. The S4 fixture board carries a local copy
with the one property added (the other three connector YAMLs
byte-identical to production) rather than patching a production binding
from a test slice. **Fixing it upstream of the fixture is Tobi's call.**

### THE DOC TREE IS COMMITTED — `6d743a3`

Six cumulative tutorials plus mechanics, four Diátaxis quadrants, rST
only, `sphinx-build -W` clean. Tutorial 4's **"This tutorial does not
work yet."** warning is retired, per the rule its own guidelines page
states — verified before deleting it, not assumed: `--explain` prints the
shape the page shows, `--rig adafruit_data_logger` links (16068 B), and
the ambiguity refusal fires as described (`grove_led` on lotus, nine
grove sockets, `phys-socket` listing all nine).

**REMAINING HONESTY DEBT, series-wide:** the `acme-rigs` playground that
tutorials 2/3/5/6 build on is NARRATIVE, not tree content — those pages'
commands cannot be run as written and their outputs are not captured.
Tutorials 1 and 2 quote real runs. Creating that playground for real is
the next docs task.

### WHAT LANDED — S5, `board-coordinate-s5-brief.md` (`03a6928`)

22 references migrated across 13 content files, exactly the predicted
census. **No production module changed** — the premise held.

**The payoff is now a test, not an argument:** `nucleo_datalogger`'s
`--boards-for` answer went from one board to two. `frdm_k64f`'s own
`arduino_r3` socket always offered the identical i2c/spi subset
`adafruit_data_logger` needs; only the content's insistence on naming
`nucleo_ard` kept it from being a legal host. **That is the integration
tier's first real falsifier for socket conformance** — S2's own recorded
gap, closed.

**The refreeze was 14 files, ALL `config-sheet.md`, 23/23 symmetric.** §3's
tracing held: no `stderr.txt` or `exit_code` moved, because all four
diagnostic sites render `socket.label` (the board's DEFINING label), never
the content string.

**The goldens were HAND-EDITED, not refrozen — `RIGC_REFREEZE=1` is
BLOCKED by the harness permission classifier in this environment.** Expect
to hit the same block. The dispatch worked from the exhaustive
non-refreeze failure list instead. Driver-verified two ways rather than
trusted, and BOTH are needed: `test_emitted_corpus.py` passes (goldens
match what the tool emits), AND applying only the label rename to HEAD's
version of each file reproduces the working tree exactly (nothing
semantic slipped in). The first alone would pass against a golden edited
to match a wrong output; the second alone would not prove the tool agrees.

**A correction to S5's own §7, and S6 must not inherit it.** The reduced
contract named `test_resolved_corpus.py` as the one build-marked module —
but the `config-sheet.md` churn the brief itself demands be classified is
observable ONLY through `test_emitted_corpus.py`. An implementor
following §7 literally would have classified a refreeze it could not see.
The general rule, now stated in that brief: **the reduced contract must
name the module that OBSERVES the slice's acceptance criteria**, which is
not always the module its code lives nearest.

### S5's BRIEF, for reference — `board-coordinate-s5-brief.md`

A DATA slice: ruling 1 fixed the convention, `d47ec86` shipped the
mechanism. **If it appears to need production code, the premise is
wrong.** Scope counted, not estimated: **22 references migrate**
(`nucleo_ard` 10, `quail_sock1..4` 9, `frdm_ard` 3), 19 do not (lotus
already conforms; instance-scoped sockets are board-agnostic by the
provider rule; plus `ard_datalogger`'s abstract `ard`).

Five rulings (Tobi, 2026-08-06), the first of which shapes the slice:

1. **`ard_datalogger` is NOT touched — its collapse is S6's.** It is the
   only user of the abstract socket map, which exists solely because
   nucleo and frdm spell the same connector differently, so the map dies
   the moment both carry `arduino_r3`. Leaving it alone means **S5
   orphans nothing**, and "is an inert map an error?" moves to S6 with
   the collapse instead of being owed here.
2. The refreeze is **CLASSIFIED**: only `config-sheet.md`'s
   instance/socket tuples may move. First churning slice in the sequence.
3. A corpus rig answering **more than one board** via `--boards-for` is
   an acceptance criterion, not a note — the integration tier's first
   real falsifier for socket conformance.
4. **Do NOT flip the defining label.** `labels[0]` stays board-specific.
5. No new production code.

**A §6 gap found while briefing:** §6 traced the golden impact for the
two emitted artifacts but never considered **reject `stderr.txt`**, and
two reject goldens DO carry board-prefixed labels (`frdm_cs_clash`,
`nucleo_wifi_logger`). Traced rather than assumed: all four sites that
print a socket in a diagnostic (`analyzer/addresses.py:243,245`,
`analyzer/gpio.py:241,249`) render `socket.label` — the board's DEFINING
label — never the content's string, so they are insulated for the same
reason the overlay is. This matters because `stderr.txt` is byte-exact
PERMANENTLY by ruling: a churn there is a product decision, not a
refreeze.

### NEXT, in order

1. **S6 — strict symmetry**, and it now carries an extra piece:
   `board:` out of rig.yml, variants collapse to topology-only,
   `RIG_BOARD` + the 19 goldens refreeze as a classified step, **plus
   `ard_datalogger`'s collapse and the `sockets:` map vocabulary's
   retirement** (ruled 2026-08-06, recorded in §9.5 step 6). **This is the
   last step of §9.5** — with it, board-as-coordinate is done.
2. Then the standing queue: **rig-schema.yaml** (backlog item 7),
   **shield plurality**, **BRIDLE MIGRATION**.

Off-sequence and unblocked: **§9.6's params CLI grammar**
(`<device>.<prop>=<value>`, composing with `@`) — the vocabulary blocker
is ruled, the grammar is unwritten, and S4 records its absence as an
asserted exclusion set that shrinks when it lands. Plus **the i2c-port
binding decision** above, and **the tutorial playground**.

**The dispatch contract from 2026-08-06a still stands** and worked twice
more today. `rig-implementor.md` still says "run `check.sh`" and still
points at the stale `/wrk/z/ws-up/claude/rigs/`; correct both in every
prompt. **Note it is also not loaded as an agent type from this project
root** — it lives in `btr-shields/.claude/agents/`, so dispatches run as
`general-purpose` on sonnet with a self-contained prompt.

## RESUME (2026-08-06b, superseded) — S3 LANDED (BOTH HALVES). §9.6 RULED. NEXT = S4, AND ITS BRIEF IS WRITTEN.

### STATE AT SESSION CLOSE (2026-08-06b)

btr-shields HEAD is the doc commit this block ships in, on top of
**`61e7be9`**. Tree clean apart from an **untracked `doc/`** — see below,
it is deliberate and it is yours to review. `main` is **ahead 19+1 of
origin, NOT pushed** — the 16 carried in from this morning plus this
session's four. Still Tobi's call, and now carried since 2026-08-04.

**Gate, driver-verified, FULL, once per slice:** mypy **93 files**, unit
**614**, non-build integration **82**, frozen **170**, coverage **92%** vs
the 88 floor. ALL GREEN. Goldens **byte-unchanged** across all three
slices — each one's own acceptance criterion.

| commit | what |
|---|---|
| `7af1fc9` | **S3a** — the shield promotion desugaring, namespace rule, `west rigs --explain` |
| `805b7b8` | **S3b** — build a promoted shield, `--rig <shield>` end to end |
| `61e7be9` | doc: rule the ad-hoc params token exit (§9.6) |

The gate moved 89→93 files, 597→614 unit, 157→170 frozen, 90%→92% across
the session.

### S3 WAS SPLIT IN TWO, AND THE SPLIT PAID OFF TWICE

§9.5 lists S3 as one item. Read against the tree it is two, and **ruling
6 says which comes first**: *"if it cannot be printed it cannot be built"*
makes the printer a prerequisite for the builder, not a companion.

- **S3a** — `scripts/rigc/promote.py`: `discover_shields`,
  `promote_shield` (pure), `check_promotable`, `both_paths_error`, plus
  `west rigs --explain <expr>`. No build path at all.
- **S3b** — `rigc expand --promote <shield>`, `list_rigs.py` resolving
  both namespaces, cmake's `{PROMOTED}` key, `west build-rig -b <board>
  --rig <shield>` end to end.

It paid off twice: S3a's `--explain` was the oracle S3b was checked
against, and **S4's law is now a diff of two `expand` runs rather than a
new comparator** (see below — "rather than a new comparator" turned out to
be not quite free, but close).

**The desugared form is now FIXED and S4 compares against it. Do not
adjust it:** a rig.yml with `name:` and **no `board:`** (the first such
file in the tree; legal only because S1 relaxed "never neither" to "never
neither unless injected"), and one **socket-less** instance **named after
the shield** (instance names reach `config-sheet.md`, a C2b-compared
fact). `@rev` selects the SHIELD's revision; `/variant` is an error.

### RULINGS MADE THIS SESSION

1. **§9.6 RULED — exit (3)** (Tobi): the shield that declares a parameter
   declares the vocabulary that parameter is drawn from. **Not ad-hoc-only**
   — `check_param_token` gains a second source, so a persisted rig's
   `dt-includes:` stops being the only place a token can resolve from.
   `lotus_buttons` is the live migration case: its `input-event-codes.h`
   exists purely for `grove_btn`'s required `zephyr,code`, and no shield
   template includes it today. **The CLI grammar itself is still
   unwritten** — this ruling settled only where the vocabulary comes from,
   which was the blocker.
2. **`list_rigs.py` becomes the resolver for BOTH namespaces** (driver),
   delegating the shield half to `rigc.promote`. Rejected: a second
   resolver script (two places axis resolution can drift), and "try
   `list_rigs`, fall back on failure" — `list_rigs` exits identically for
   "no such rig" and "malformed rig.yml", so a fallback would silently
   promote a shield whenever a same-named rig was merely BROKEN, turning
   an authoring error into a different build.
3. **Five rulings correcting §9.1's method for S4** — see the next block.

### S4 IS BRIEFED: `board-coordinate-s4-brief.md`, AND IT CORRECTS §9.1

§9.1 says the law is byte-equality of the emitted artifacts, "**no new
comparator, no oracle to hand-author**", authored **failing-first**.
**Neither half is reachable as written**, and S3 is part of why. The brief
supersedes §9.1's METHOD; its CLAIM stands. Five findings, each checked
against the tree:

1. **The two sides cannot share a name through normal resolution** — the
   rig name is in `rig-gen.overlay`, `config-sheet.md`, `expectations.yml`
   and `context.cmake`'s `RIG_NAME`, so byte-equality needs identical
   names, but S3a's namespace rule makes a name that is both a rig and a
   shield a hard error. **Escape: `expand <path>` does no namespace
   resolution**, so the law lives at expand level with the fixture given
   by path. Latent caveat, verified not-yet-live: nothing currently passes
   the fixtures board root to `find_rigs` alongside the real shield dirs.
2. **`RIG_DEPENDS` cannot match** — it records resolution HISTORY, so each
   side lists its own two rig documents. **One explicit exemption**,
   compared as a set minus those, stated in the test docstring, never a
   silent filter. Everything else in it must be identical, and that is a
   large part of the law's value.
3. **The domain is not all shields.** Measured: 14 shields, all
   `template: true`; **two declare a required param with no authored
   default** — `grove_btn` and `pilot_alt_button`, both `zephyr,code`.
   Domain = promotable shields with no required parameter, DERIVED from
   the census, with the excluded set **asserted explicitly** so it shrinks
   visibly when §9.6's grammar lands. 12 eligible today, parametrized —
   a census, not one example.
4. **Failing-first is no longer available** — S3b already made the law
   pass. Replaced by **mutation-verification**: changing the desugared
   instance name must fail on `config-sheet.md`; dropping socket-less-ness
   must fail on inference.
5. **One build-marked cross-check** via `dts_equiv` — expand equality does
   not prove the cmake path feeds the same thing, and S3b's `dts.cmake`
   branch is new. This half WANTS different names and may have them:
   `zephyr.dts` carries no rig name.

Net shape: **a parametrized expand-level census, one documented exemption,
mutation-verified, plus a single build-marked `dts_equiv` cross-check.**
A small comparator, not none — which is the correction §9.1 needed either
way.

### FOUR DEFECTS FOUND IN REVIEW, ALL DRIVER-FIXED

1. **The namespace rule failed OPEN across modules** (S3a).
   `discover_shields()` was called with no arguments, so it saw only the
   vendored `boards/shields` while `find_rigs` walks every module board
   root. A cross-module shield was invisible to `--explain` **and silently
   uncollidable** — the collision check could not see the thing it exists
   to catch. Blind spot verified before fixing, then confirmed end to end
   with a real cross-module shield. **Do not reintroduce the narrow
   default**; `resolve_rig_target` has `args.board_roots` in hand.
2. **`both_paths_error` FABRICATED the shield path** (S3a), building
   `boards/shields/{name}/` from the name instead of reporting where the
   shield was found — wrong for exactly the cross-module case that makes
   names collide. The test asserted the constructed string, so it would
   have passed forever; it now uses a shield dir that deliberately is not
   the conventional path.
3. **S3b's report omitted a required deliverable.** The brief's §6 called
   the build-marked tests "the real falsifier, and this slice needs it"
   and named criteria 2.2 and 2.3 explicitly. `test_cmake_alone_entry.py`
   was untouched — all 14 tests it ran were pre-existing, none mentioning
   promotion. **The slice's headline capability shipped verified only by
   hand.** Driver wrote the two tests. The lesson is not new but it is
   sharper: **check the file list, not just the gate output** — every
   other test in that module names a real rig, so a regression breaking
   promotion alone would have left the whole suite green.
4. An implementor caught **a factual error in the driver's own brief** —
   §6 described a verification step that contradicted §3, claiming a
   boardless rig.yml loads without a board. It does not (`lang-schema`);
   S1 relaxed "never neither" only when a board is INJECTED. Verified
   independently and corrected in the brief rather than patched around.
   **The deviations section was the best of the session** — the same
   dispatch that omitted the tests caught this.

### A DOC TREE RODE ALONG — untracked, deliberate, yours to review

`doc/` is a Sphinx site: six tutorials plus mechanics, four Diátaxis
quadrants, rST only, **`sphinx-build -W` clean** (the same gate firmhold
holds itself to). Staged in the scratchpad while an agent was live in the
checkout, then transplanted — it is **not committed**, and `doc/.gitignore`
covers `_build/` so the tree stays clean.

Two adaptations worth carrying: intersphinx points at Zephyr with misses
non-fatal so the build works offline (internal refs still fail hard), and
DTS blocks use Pygments' `devicetree` lexer — the `c` lexer chokes on
`shield,plugs`.

**Tutorial 4 opens with a bold "This tutorial does not work yet."** — and
S3 has since shipped what it needed. The guidelines page states the rule:
**the warning is deleted in the same change that ships the feature, and
the outputs re-captured from a real run.** That is now an open task.

Build it:

```
sphinx-build -W --keep-going -b html doc doc/_build/html
```

`doc/howto/build-the-docs.rst` has the permanent recipe.

### NEXT, in order — §9.5's sequence, unchanged

1. **S4 — the singleton identity law.** Brief written:
   `board-coordinate-s4-brief.md`. **Its §2 supersedes §9.1's method** —
   dispatch against the brief, not against §9.1.
2. **S5 — content migration to conventional labels.** Two payoffs now:
   under a free board `nucleo_ard` in content is a portability bug, and it
   is what gives `--boards-for` a corpus rig answering more than one board
   — the integration tier's first real falsifier.
3. **S6 — strict symmetry.** `board:` out of rig.yml, variants collapse to
   topology-only, `RIG_BOARD` + the 19 goldens refreeze as a classified step.
4. Then the standing queue: **rig-schema.yaml** (backlog item 7), **shield
   plurality**, **BRIDLE MIGRATION**.

Off-sequence but now unblocked: **§9.6's params CLI grammar**
(`<device>.<prop>=<value>`, composing with `@`) — the vocabulary blocker
is ruled, the grammar is not written, and S4 records its absence as an
asserted exclusion set. And **the `doc/` decisions**: commit it, and
retire tutorial 4's not-yet warning.

**The dispatch contract from 2026-08-06a still stands** — implementor runs
mypy + unit + non-build integration + ONE named build module; the driver
runs the full gate once. It worked three more times today. `rig-implementor.md`
still says "run `check.sh`" and still points at the stale
`/wrk/z/ws-up/claude/rigs/`; **correct both in every prompt** until
someone edits that file.

## RESUME (2026-08-06a, superseded) — S2 LANDED: `--boards-for`. NEXT = S3. AND THE DISPATCH CONTRACT CHANGED.

### STATE AT SESSION CLOSE (2026-08-06)

btr-shields HEAD is the S2 commit this block ships in; tree clean. `main`
is **ahead 16 of origin, NOT pushed** — the 15 carried in from 2026-08-05
plus this one. Still Tobi's call.

**Gate, driver-verified, FULL, once:** mypy **89 files**, unit **597**,
frozen **157**, coverage **90%** vs the 88 floor. ALL GREEN. Goldens
**byte-unchanged** — `git diff --stat` on `tests/goldens/` empty, S2's own
acceptance criterion.

The frozen count moved 148 → 157: five `test_boards_for.py` cases (three
of them parametrized) and the four board parametrizations of one new
build-marked cross-check. No golden moved.

### THE DISPATCH CONTRACT CHANGED — read this before dispatching anything

**Tobi, 2026-08-06: running the full suite dominated every task and had to
come back under control.** The new split, used for the first time this
session and it worked:

> the implementor runs the cheap tiers plus ONLY the named build module its
> change touches; the DRIVER runs the full gate once, after review.

The measurements that make it safe, taken before dispatching:

| tier | count | wall time |
|---|---|---|
| mypy | 89 files | ~5s |
| unit | 597 | **1.9s** |
| integration `-m "not build"` | 69 | **5.3s** |
| integration, build-marked | 88 | **~3m40s** |
| full gate (`check.sh`) | — | 3m44s |

**Essentially 100% of the cost is the build-marked tier** — real `west
build --cmake-only` configures. The non-build gate is FIVE SECONDS. So
there was never anything to trim: the fix is which build tests a dispatch
runs, not how many tests exist. S2's implementor ran ~25 seconds total.

This supersedes `rig-implementor.md`'s "run `check.sh` and get it fully
green" for scoped slices — say so explicitly in the dispatch prompt, since
the agent definition still says otherwise. **The agent definition also
still points at the stale `/wrk/z/ws-up/claude/rigs/`; the papers are at
`btr-shields/claude/`.** Correct both in every prompt until someone edits
the file.

Last session's note asked for exactly this: "either the implementor runs
build tests, or the driver must run them before believing any zero-churn
claim." The answer is BOTH, narrowly — the implementor runs the one build
module that could falsify its own change, the driver runs everything.

### WHAT LANDED — S2, `board-coordinate-s2-brief.md`

`west rigs --boards-for <rig-target>` prints the boards whose typed
sockets satisfy a rig. New unit `scripts/rigc/board_census.py`.

**The design decision that matters:** conformance is not a comparison loop.
The census builds a PARTIAL `model.Board` from board rig-extension SOURCES
and runs the real `analyzer/sockets.py::resolve_sockets` against it —
mating, bus subset, alias-aware resolution, carrier composition,
stackability, all through the one existing rule. There is no second
implementation to drift.

**Why a text census and not a real DT read**, settled by measurement, not
preference: `boarddt._discover_board_dts`'s own docstring records that the
standalone board catalog is ALWAYS EMPTY for every board this tooling can
build (all hwmv2 extensions whose base lives outside `MODULE_ROOT`), and
reading a real board DT needs cpp + edtlib + a `BuildRecipe`. A real
per-board read therefore costs a cmake configure per candidate. That is
not a query.

**So the command's claim is BOUNDED and the help text says so:** it answers
which boards' SOCKETS fit, never that the rig builds there. GPIO routing,
CS-pool allocation, address domains and net analysis all need the real
devicetree. Visible consequence, and it is correct: every reject rig in the
corpus (`frdm_cs_clash`, `nucleo_mux_clash`, `lotus_pwm_clash`,
`quail_dup_th`) CONFORMS, because their clashes are not socket-level.

The guard that keeps a text scanner honest is one build-marked test:
census vs `board_edt`'s projection of the REAL EDT, per board, on every
field the census populates. It is the only build test the slice added.

### THE INTEGRATION TIER CANNOT FALSIFY `boards_for` — the unit tests carry it

All 17 corpus rigs answer **exactly their declared board**, so a stub
returning `[rig.board]` passes every integration assertion. This is D4's
shape again, one layer up. The discrimination lives entirely in
`tests/unit/test_board_census.py`, and it has to: **no corpus rig omits
`socket:`** (checked — all 41 instance socket references are explicit), so
alias resolution and unique-by-type inference are exercised NOWHERE else in
the tree. S5's content migration is what will finally give the integration
tier something to distinguish.

Driver-verified by mutation, not assumed: gutting `boards_for` to
`conforms=True` fails 5 unit + 3 integration tests.

### A SHARED-INFRASTRUCTURE CHANGE RODE ALONG — flagged, verified, kept

`test_layer_discipline.py`'s build-reaching guard treated ANY argv headed
by `west`/`WEST_EXE` as a configure. A non-configuring `west rigs` test
therefore had to be marked `build` or the guard failed — so the implementor
**narrowed the guard**: west counts only for `{build, build-rig}`.

That is a real weakening of a guard, made outside the brief's file list,
and the implementor flagged it rather than burying it. Kept, because
`{build, build-rig}` is every configuring west invocation in the tree
(audited: the only other one is `rigs`), and because the alternative —
marking a query test `build` — would have put a 0.5s test into the 3m40s
tier, which is the exact cost this session set out to control.

**Driver mutation-verified that the narrowed guard still enforces:**
deleting the module-level `pytestmark = pytest.mark.build` from
`test_cmake_alone_entry.py` fails exactly
`test_every_build_reaching_integration_test_is_marked_build`, naming the
now-unmarked tests. Restore hash-checked, `__pycache__` purged.

### FOUR REVIEW FINDINGS, ALL DRIVER-APPLIED

1. **The census read 2837 files (5.6 MiB) per invocation and threw away
   1071 boards' worth.** `census_boards` globbed and read every sibling
   `.dts`/`.dtsi` BEFORE deciding whether the board.yml was even in scope.
   `board_targets` is now its own pure function so the edge short-circuits
   on the small YAML first.
2. **A count assertion masquerading as a content assertion.** "Same 17
   rigs" asserted `len(...) == 17`, which holds just as well if the listing
   starts printing board targets. Now asserts the `rig.name` values, read
   from rig.yml — the expectation comes from OUTSIDE the thing under test.
3. **A test docstring that overclaimed, written by the driver.** A new test
   said lotus's `adc0: &adc {};` exercised the no-compatible branch. It does
   not: `&` is not a word character, so the node pattern never matches it
   and that branch stayed uncovered. The test now asserts both shapes and
   says why they fail differently. Same failure mode this project keeps
   finding, and the author being the driver is exactly why the rule is
   "check the claims, including your own."
4. Import ordering in `rigs.py`.

### A LATENT TEST-HARNESS BUG THE NEW WORKFLOW EXPOSED

`test_board_read.py::test_edt_pickle_cross_check` **could not be run
standalone**: `pickle.load` needs `devicetree` importable, and nothing in
that module puts it on `sys.path` — 4/12 failed alone, 12/12 in a full run,
12/12 alone with `PYTHONPATH` exported. Fixed with
`edt_build.ensure_devicetree_on_path()`, the production idiom.

Worth generalizing: **the reduced contract makes every build module
individually runnable a requirement, and it was not true before.** Expect
more of these as other modules get run alone for the first time.

### NEXT, in order — §9.5's sequence, unchanged

1. **S3 — the `--rig <shield>` promotion** + the §9.2 namespace ruling (rig
   folder wins, shield name is the fallback, a name that is BOTH is an
   error naming both paths) + **`--explain`** (ruling 6). This is where
   carried commit `3f205005b99`'s `template: true` finally becomes
   load-bearing — **it is declared and NOTHING reads it today.**
   `boards_for` already returns its diagnostics rather than a bare boolean,
   so `--explain`'s "why not this board" has its input waiting.
2. **S4 — the singleton identity law**, authored FAILING-FIRST.
3. **S5 — content migration to conventional labels.** Note it now has a
   second payoff: it is what gives `--boards-for` a corpus rig that answers
   more than one board, and therefore the integration tier its first real
   falsifier (see above).
4. **S6 — strict symmetry.** `board:` out of rig.yml, variants collapse to
   topology-only, `RIG_BOARD` + the 19 goldens refreeze as a classified step.
5. Then the standing queue: **rig-schema.yaml** (backlog item 7), **shield
   plurality**, **BRIDLE MIGRATION**.

**§9.6 is still OPEN and NOT RULED: the ad-hoc params grammar.** Unchanged
from last session; the driver recommends exit (3).

**`--rigs-for <board>` is deliberately NOT implemented** — the same census
read backwards, but it needs every rig loaded and it is not on the critical
path. Recorded in `board_census.py`'s own docstring as a considered
non-implementation, so nobody files it as an oversight.

## RESUME (2026-08-05, superseded) — S1 LANDED: BOARD IS AN INDEPENDENT COORDINATE. NEXT = S2

### STATE AT SESSION CLOSE (2026-08-05)

btr-shields HEAD **`462e5c6`**, tree clean apart from the doc commit this
block belongs to. `main` is **ahead 15 of origin, NOT pushed** — the 12
carried in from 2026-08-04, plus this session's two slices, plus the doc
commit this block ships in. Still Tobi's call.

(The count INCLUDES this block's own commit. The 2026-08-04b block said
"ahead 11" and was actually 12 for exactly this reason — a resume block
written before its own commit lands undercounts by one. Read the number as
what `git rev-list --count origin/main..main` reports after the handoff
commit, not before.)

**Gate, driver-verified, FULL (never `CHECK_FAST`), three times this
session:** mypy **86 files**, unit **579**, frozen **148**, coverage **90%**
vs the 88 floor. ALL GREEN. Goldens **byte-unchanged** — `git diff --stat`
on `tests/goldens/` empty, which is S1's own acceptance criterion.

| commit | what |
|---|---|
| `b578ccc` | board-as-coordinate rulings 4–8 + the S1 slice brief |
| `462e5c6` | **S1 — BOARD as an independent coordinate with a per-rig default** |

### THE SESSION'S REAL WORK WAS THE RESEQUENCING, NOT THE CODE

`board-as-coordinate-brief.md` **§9 is the live section** (its §7 is marked
SUPERSEDED, kept for per-step detail; §8 renumbered to §10). Five rulings,
all Tobi's, all recorded there. The two that matter most next time:

- **The singleton identity law is INTERNAL now** (ruling 4). Not `--board b
  --shield s` vs a rig — that comparison was the wrong instrument, and
  `P2-S1-equivalence.md` had already measured why: 129/134 nodes identical
  with three by-design divergences that are all artifacts of comparing
  against UPSTREAM's mechanism on a DIFFERENT board. The law is now
  `--rig <shield-name>` ≡ `--rig <checked-in rig with one socket-less
  instance of it>`, both through rigc on the same board, so it is
  byte-equality of the emitted artifacts and needs NO new comparator.
  **Tobi claims `a → [a]` for OUR `.shield` shields only, never for legacy
  `.overlay` shields** — that restriction is what makes it cheap.
- **Board symmetry is STAGED, strict form is the TARGET** (ruling 7). Tobi's
  argument reordered everything: a promoted shield has no board, so out of
  symmetry a persisted rig should not declare one either. Measured cost of
  going strict now: 17 rig.yml files, 19 `RIG_BOARD` goldens, and one of
  S2's five frozen-wording rules. Hence mechanism now, corpus later — and
  **`--boards-for` was promoted from "shippable any time" to PREREQUISITE**,
  because it is what enumeration BECOMES once declaration is gone.

### NEXT, in order — §9.5's sequence

1. **S2 — `--boards-for`.** Design doc §5, "Tobi: ship it". Reads the same
   census step 1's lint already builds. Do it BEFORE enumeration is at risk.
2. **S3 — the `--rig <shield>` promotion** + the §9.2 namespace ruling (rig
   folder wins, shield name is the fallback, a name that is BOTH is an
   error naming both paths) + **`--explain`** (ruling 6). This is where
   carried commit `3f205005b99`'s `template: true` finally becomes
   load-bearing — **it is declared and NOTHING reads it today**, not
   `list_shields.py`, not upstream `shields.cmake`, not rigc, which uses the
   marker FILE instead.
3. **S4 — the singleton identity law**, authored FAILING-FIRST.
4. **S5 — content migration to conventional labels** (old §7.3). Now
   properly motivated: under a free board, `nucleo_ard` in content is a
   portability bug, not a style question.
5. **S6 — strict symmetry.** `board:` out of rig.yml, variants collapse to
   topology-only, `RIG_BOARD` + the 19 goldens refreeze as a classified step.
6. Then the standing queue: **rig-schema.yaml** (backlog item 7), **shield
   plurality**, **BRIDLE MIGRATION**.

**§9.6 is OPEN and NOT RULED: the ad-hoc params grammar.** Two findings
constrain it. `params:` already exists, so `--rig name:...` is SUGAR over an
existing feature — but it is keyed by the shield's **DEVICE label**, so a
bare `param1=` addresses nothing (`adafruit_data_logger` has five devices);
the CLI form needs `<device>.<prop>=<value>`, and must compose with `@`,
already taken by shield revisions. And the value is a **cpp token** whose
vocabulary header lives in the RIG today (`lotus_buttons.yml`'s
`input-event-codes.h`; **no shield template includes it**), which an ad-hoc
rig has no way to supply. Three exits in §9.6; the driver recommends (3),
letting the shield that declares `shield,params` carry the `#include` too.

### TWO STALE CLAIMS IN THE BRIEF, BOTH CORRECTED — the standing rule again

§5's two recorded blockers for the singleton law were both dead:
§4.2 inference landed in `1c2344e`, and "no shield in the tree exists in
upstream form" was **simply wrong** — `adafruit_data_logger`,
`adafruit_winc1500` and `arduino_uno_click` all exist in the pinned zephyr
tree with real `.overlay` files beside our same-named `.shield` templates.
That is exactly the collision `dts.cmake:612-664`'s marker preference
already resolves. **A brief's factual claims are checkable, including the
driver's own** — see below, where two of S1's were wrong.

### THINGS FOUND THAT WERE NOT LOOKED FOR

- **`zephyr_check_cache` does NOT reject a changed value — it WARNS and
  silently REVERTS** to the cached one (its own docstring says so). This
  killed the driver's own review suggestion to narrow the rig-swap guard:
  narrowing it would have built the OLD board under the NEW rig's name with
  nothing but a warning. The guard stays unconditional; the message
  differentiates instead. A comment asserting the opposite was written in
  the same slice and had to be removed — two comments in one file
  contradicted each other.
- **`west build-rig -b <board> <rig>` needed no code at all.** `rig.py`
  already passed `args.board` through untouched; only its comment block,
  which asserted the exclusivity as a design rule, was wrong.
- **The board target loses `BOARD_REVISION` if you rejoin only two parts.**
  `parse_board_components` splits THREE (`<board>@<rev>/<quals>`). Rejoining
  `${BOARD}/${BOARD_QUALIFIERS}` — which is what upstream itself does at
  `boards.cmake:300` — still silently drops `@rev` from `RIG_BOARD` and
  `build_info.yml`. Verified against `nrf9160dk@0.14.0/nrf9160`.

### PROCESS NOTES WORTH CARRYING

- **`CHECK_FAST` checks NO goldens at all since the flip**, so an
  implementor held to the fast gate STRUCTURALLY cannot catch a
  golden-churning bug. This dispatch found the dropped-qualifiers bug only
  by exceeding its contract and running the build tests itself. Last
  session's note said "change the contract rather than the wording" if
  dispatches keep mishandling gates — this is the evidence for doing it:
  **either the implementor runs build tests, or the driver must run them
  before believing any zero-churn claim.**
- **A negative control can need a SECOND assertion nobody predicted.** The
  no-board control asserted only `returncode != 0`, because both content
  assertions were satisfied by `render_argv`'s own argv (it contains
  `-DRIG=<rig>`, and `-DBOARD_ROOT=` lowercases to contain `-dboard`).
  Worse, the obvious fix — assert OUR wording — is STILL vacuous: a
  `message(STATUS)` prints the same text and the configure dies moments
  later at zephyr's own `BOARD REQUIRED` check with our phrase present. The
  live discriminator is that the GENERIC DOWNSTREAM message must be ABSENT.
  **Never interpolate `render_argv` into a string you then assert `in`.**
- **NEVER restore a mutation with `git checkout <file>` when that file has
  uncommitted changes.** The driver did, and it reverted `boards.cmake` to
  HEAD, discarding the whole slice's work in that one file. Recovered
  faithfully from the implementor's transcript and verified against an
  independent verbatim record of the region (character-for-character, one
  intended difference), then re-gated to identical numbers. **Copy the file
  first; hash BEFORE mutating; restore from the copy.** The existing memory
  covers the stale-`.pyc` half of this; this is the other half.
- Every accepted slice this session was mutation-verified, twice over for
  the one control that mattered — driver and implementor independently, with
  matching results (`1 failed, 13 passed`, on the named assertion).

## RESUME (2026-08-04b, superseded) — hwmv2 DONE (rig-side); BOARD-AS-COORDINATE UNDER WAY

### STATE AT SESSION CLOSE (2026-08-04b)

btr-shields HEAD **`1c2344e`**, tree clean. `main` is **ahead 11 of
origin, NOT pushed** — the whole session's work is unpushed; that is the
first decision next time.

**Gate, driver-verified, FULL (never `CHECK_FAST`) after every slice:**
mypy **86 files**, unit **568**, frozen **145**, coverage **90%** vs the
88 floor. ALL GREEN.

Eleven commits, six slices:

| commit | slice |
|---|---|
| `c46fdc3` | lazy shield library — templates parse on first reference |
| `d3eed8a` | the four real items in backlog group E |
| `8dd24ec` | items 20 + 27 — refreeze the goldens' unread bytes |
| `f549062` | hwmv2 dispatch A — one resolver for rig and shield axes |
| `5ea1d69` | hwmv2 dispatch B — upstream revision shape + semantics |
| `d47ec86` | conventional socket labels + alias-aware board lookup |
| `e6423c0` | the empty-rig identity law (saferail 11) |
| `1c2344e` | unique-by-type socket inference + stacking census fix |

plus `1958ccc`, `6cc5406`, `43cc443` (docs).

### WHERE TO PICK UP

**`board-as-coordinate-brief.md` is the live document.** Its §7 status
table is current. All three of its rulings are settled. State:

- steps 1 (aliases + alias-aware lookup) and 2a (empty-rig law) LANDED;
- **2b, the singleton identity law, is now UNBLOCKED** — `1c2344e`
  delivered the §4.2 inference it needed — but still requires a shield
  authored in BOTH worlds (a `.shield` template AND a plain upstream
  `.overlay` as the oracle), because no shield in the tree exists in
  upstream form. Precedent: the P2 S1-equivalence work did exactly that.
- steps 3 (content migration), 4 (the coordinate change) and 5
  (`--boards-for`) are all open. **Step 5 is fully independent and
  shippable on its own** — Tobi's standing "ship it", and it reads the
  same census step 1's lint already builds.

Then the standing queue: **rig-schema.yaml** (backlog item 7 — hwmv2's
hand-rolled diagnostics come first and it defers to them, not the
reverse), **shield plurality**, **BRIDLE MIGRATION**.

### RULINGS MADE THIS SESSION — all recorded in their briefs

1. Diagnostic ORDER need not be preserved (rigexp is no longer a
   reference); `stderr.txt` stays byte-exact.
2. hwmv2: adopt upstream's list shape in full; classified reject refreeze
   authorized, scoped to the revision/axis family; shields get hwmv2 too
   (**later found unimplementable — see below**); no `exact: true` for
   existing corpus rigs; two dispatches.
3. Socket labels: `<type>` for a singleton, `<type>_<silkscreen>` for a
   family.
4. The `/rig` extension target stays EXPLICIT — no inference over board
   names — expecting upstream boards to gain typed sockets so the variant
   goes away by attrition.
5. Per-board fragments for rigs ARE adopted, as shields have them today.
6. Inference candidates are BOARD sockets only; inference then obeys the
   existing stacking rule.

### ONE RULING COULD NOT BE IMPLEMENTED — needs a decision

**Shields do NOT get hwmv2 semantics.** The pinned zephyr tree's
`shield-schema.yaml` constrains a shield's `revisions:` block to
`{default:, list:}` with `additionalProperties: false`, and
`list_shields.py` validates EVERY `shield.yml` under EVERY board root at
`find_package(Zephyr)` time — so a migrated `shield.yml` breaks every
configure in the workspace. Found by running a real cmake configure, not
by reasoning.

**The constraint is OUR OWN carried commit `8da5b3a0f60`, not upstream's**
— verified: `origin/main`'s copy of that schema has no `revisions:` block
at all. So this is reversible by extending a patch we already carry.
Tobi's call, **DEFERRED 2026-08-04** to the bridle migration / upstreaming
push, when all five carried commits get decided together. Recorded in
`hwmv2-revision-semantics-brief.md` §0.5.

Note the implementation is ready for either answer: hwmv2-vs-legacy is
discriminated by `decl.format is not None`, a property of the DATA, so
one resolver serves both and nothing in rigc changes the day that schema
does.

### THINGS FOUND THAT WERE NOT LOOKED FOR

- **The stacking census could be bypassed** (`1c2344e`). Keyed by the raw
  reference string, so after aliases landed two instances could name one
  physical socket by two labels and slip past the non-stackable check.
  Latent, not live — the only non-stackable type is `grove`, on the one
  board that needed no aliases — but now fixed and regression-tested.
- **`run_cpp` no longer uses gcc's `-o`** (`d3eed8a`). gcc writes nothing
  there on a failing preprocess but still emits linemarkers, and item 19
  needed deps on the failure path. It captures stdout and writes the file
  itself, **as bytes** — the first implementation used `text=True`, which
  made every preprocessed file in the tool locale-dependent.
- **`list_rigs.py` re-reads rig.yml's axis independently** (`5ea1d69`),
  before rigc runs, so hwmv2's key rename would have silently broken
  every real qualified build. Nearest-lower there is a documented gap.
- **The refreeze trap is closed** (`8dd24ec`). `RIGC_REFREEZE=1` rewrites
  whole files, so every refreeze used to drag the banner rewrite into
  unrelated diffs; two slices had to hand-revert 40–58 files. Gone now,
  but **classify every refreeze diff before committing it** regardless.

### PROCESS NOTES WORTH CARRYING

- **Four of six dispatches stalled** ending their turn waiting on their
  own background gate, and had to be killed and their work verified by
  hand. Explicitly instructing against it did not help; the last dispatch,
  which named the failure and its consequence directly, did not stall.
  If it recurs, change the contract rather than the wording: let
  implementors write code and hand off, and the driver does all gate
  running and verification.
- **Two of this session's briefs were wrong in ways checking caught**:
  the design doc's "additive conformance" claim (a second DT label was
  inert until `d47ec86` made it real), and a claimed live YAML float
  hazard that does not reproduce in rigc's own parser. Treat a brief's
  factual claims as checkable — including one's own.
- **"Uncovered" has meant two different things** in the backlog: no code
  path reaches it, versus nothing freezes its wording. Say which.
- Every accepted slice this session was mutation-verified: the control
  must fail for the named reason and nothing else.

## RESUME (2026-08-04a, superseded) — GROUP E CLEARED; hwmv2 BRIEFED

### STATE AT SESSION CLOSE (2026-08-04)

btr-shields HEAD **`8dd24ec`**, tree clean apart from the doc commit this
block belongs to. `main` ahead of origin, unpushed. Gate, driver-verified,
FULL: mypy **86 files**, unit **502**, frozen **145**, coverage 89% vs the
88 floor — ALL GREEN.

Three slices landed today, on top of the lazy shield library (`c46fdc3`):

- **`d3eed8a` — the four real items in backlog group E.** Group E listed
  seven; only four were tasks. 18 (CWD-relative unknown-board path → the
  ratified `anchor_path`), 19 (a rig's `dt-includes:` headers now reach
  `RIG_DEPENDS`), 21 (typing), 24 (wording frozen by a new reject
  fixture). Items 22 and 23 close with "Safe" and "No hole today" — they
  are observations, now labelled NOT A TASK so the next reader does not
  invent work for them.
- **`8dd24ec` — items 20 + 27**, the pure refreeze: the 57 `generated by
  rigexp` banners and two stale `zephyr.dts` provenance annotations. No
  code in the tree, so the diff is only bytes no comparator reads.

### THE REFREEZE TRAP IS CLOSED

Both prior slices had to hand-revert 40–58 unrelated files, because
`RIGC_REFREEZE=1` rewrites WHOLE FILES and therefore dragged the banner
rewrite into every unrelated diff. `8dd24ec` clears that. **The
discipline still stands: classify every refreeze diff before committing
it** — the tool has no notion of which bytes your slice is about.

### TWO FINDINGS WORTH CARRYING

1. **`run_cpp` no longer uses gcc's `-o`.** Item 19 needed dependency
   data on the FAILURE path, and gcc writes nothing to `-o` when a
   preprocess fails (verified) while still emitting linemarkers for every
   file it opened. `run_cpp` now captures stdout and writes the file
   itself, **as bytes** — the implementor's first version used
   `text=True`, which made every preprocessed file in the tool depend on
   the ambient locale. Byte-identical to `-o` on success, verified.
2. **"Uncovered" has meant two different things in the backlog** — no
   code path reaches it, versus nothing freezes its wording. Item 24 was
   the second and was filed as the first, which changed what the work
   actually was. Say which.

### hwmv2 IS BRIEFED, RULED AND READY TO DISPATCH

`hwmv2-revision-semantics-brief.md` was re-read against the current code
and **five of its premises no longer held**. Five rulings are now
recorded in it (Tobi, 2026-08-03/04): adopt upstream's list shape in
full; the classified reject refreeze is authorized, scoped to the
revision/axis diagnostic family; shields get hwmv2 semantics too; **no
`exact: true` for existing corpus rigs**; and **the slice is TWO
dispatches**.

The single most important finding: **the hwmv2 seam is not single-place.**
The parser is shared, but `ShieldLibrary.resolve` re-derives
`resolve_axis`'s three failure shapes inline — while `axes.py`'s own
docstring claims to be the only place a selection is resolved. Hence
Dispatch A: unify the resolvers with every golden byte-identical, which
is the cheapest possible proof the two were equivalent. Dispatch B is the
shape migration + semantics + coverage.

Also recorded there, both measured rather than assumed: unquoted YAML
`1.10` parses as the float `1.1` and silently corrupts a revision id
(a LIVE latent bug today), so ids must be strings and a non-string is a
rejection; and `dotted-revision-no-fragment` is inexpressible in any
hwmv2 format and must be re-authored.

### NEXT, in order

1. **hwmv2 Dispatch A** — resolver unification, zero churn.
2. **hwmv2 Dispatch B** — shape migration (separate commit) then
   semantics (separate commit) then coverage.
3. Then **rig-schema.yaml** (item 7 — hand-rolled diagnostics from hwmv2
   come first and it defers to them, not the reverse), **shield
   plurality**, **BRIDLE MIGRATION**, **board-as-invocation-coordinate**.
4. `main` is ahead and unpushed — decide whether to push.

## RESUME (2026-08-03, superseded) — LAZY SHIELD LIBRARY LANDED

### STATE AT SESSION CLOSE (2026-08-03)

btr-shields HEAD **`c46fdc3`** ("rigs: lazy shield library -- templates
parse on first reference"), tree CLEAN. Note the repo moved under you
since the last handoff: the `claude/` papers are now INSIDE this repo at
`btr-shields/claude/` (Tobi's `52f1178`), and `84e7e4e` plus three of his
own commits were pushed — `main` was in sync with origin before this
slice, so it is now **ahead 1 (plus the doc commit), unpushed**. The
agent definitions still point at the stale `/wrk/z/ws-up/claude/rigs/`.

**Gate, driver-verified, FULL (not `CHECK_FAST`):** mypy **86 files**
clean, rigc unit suite **495 passed** (coverage 89% vs the 88 floor),
frozen suite **144 passed** in 3m20s. ALL GREEN.

### WHAT LANDED — the lazy shield library (backlog group B, item 5)

Discovery stays eager; the template parse defers to `resolve()`'s first
reference, generalising the path revisioned shields already used. Every
discovered shield is now a `_Pending`, and both the axis-less and revision
paths go through one shared `_parse_shield_template`. **`nucleo_mux_farm`
went from 14 shield translation units to 2.** All three recorded warts
retired at once (does not scale / one malformed member poisons the whole
scan / deps record scanned-but-unreferenced shields). Brief:
`lazy-shield-library-brief.md`.

**THE RULING THAT UNBLOCKED IT (Tobi, 2026-08-03): scan-time diagnostic
ORDER need not be preserved — rigexp is no longer a point of reference.**
`stderr.txt` stays byte-exact; what changed is that its content may be
re-derived when the tool's own execution order changes for a good reason.
In the event **no reject golden churned at all**: the corpus's only
scan-time template diagnostic (`shield-node-name-mismatch`) belongs to a
rig that DOES reference the broken shield, so it still fires, from
`resolve()`.

**The refreeze was 18 `context.cmake` files, one `RIG_DEPENDS` line each**
— every removed entry the `.shield` of a shield that rig never resolved,
each rig dropping exactly `14 - (shields it resolved)`, nothing added
anywhere. `pilot_variants_variant_c` is the case that proves resolution
HISTORY survived: it drops 12 while `RIG_SHIELDS` names one, because it
still records the shield its variant substituted away.

### TWO TRAPS THIS RUN, both about the refreeze tool

1. **`RIGC_REFREEZE=1` rewrites WHOLE FILES, so it silently drags in
   unrelated content.** It wanted to touch **59 files**, not 19: 40 of
   them were the `generated by rigexp` → `rigc` banner rewrite (backlog
   item 20, in a comment no comparator reads) plus stale `zephyr.dts`
   source-line annotations. Both were reverted so the slice's own diff
   stayed reviewable — the cutover brief's "keep the banner refreeze in
   its own commit" rule has real teeth. **Classify every refreeze diff
   before committing it.**
2. **Those stale `zephyr.dts` annotations are NOT zephyr drift** — the
   checkout is exactly at the pin `8da5b3a0f60`, verified. They were
   frozen against an older tree and have been invisible ever since
   because `dts_equiv` ignores comments. Now backlog item 27.

Also corrected in the backlog: "RIG_DEPENDS breadth is no longer a
blocker — compared as a SET" was misleading. `compare_context_cmake`
compares it as a set with **exact membership** — order-free, not
membership-free.

### PROCESS NOTE — the review found what reviews here always find

The implementor's report claimed the `ShieldLibrary` class docstring was
rewritten; it was not, and it still described `shields` as "every
discovered shield template" — exactly what it had stopped being. The
standing rule held again: **treat implementor verification records as
hypotheses, same as their code.** The other minor was a test docstring
claiming more coverage than its body exercised. Both driver-applied.

Both new negative controls were **mutation-verified**, not asserted:
restoring the discovery-time `touch(base_file)` fails exactly its named
control and nothing else; restoring the eager scan parse fails five tests
including all three of its controls. Restore hash-checked against a hash
taken BEFORE mutating, `__pycache__` purged.

### NEXT, in order

1. **hwmv2 revision semantics** (`hwmv2-revision-semantics-brief.md`) —
   the brief PREDATES the freeze and targets rigexp's `_parse_axis_decl`;
   it now lands in `rigc/loader/axes.py`, the seam R2 built for it.
   Re-read the brief against the current code before dispatching.
2. Then **rig-schema.yaml**, **shield plurality**, **BRIDLE MIGRATION**
   (its prerequisite is now done), then
   **board-as-invocation-coordinate**.
3. Backlog items 20 + 27 are a natural pair: one banner/annotation
   refreeze commit, now free of consequence, and doing it removes the
   refreeze trap above.
4. `main` is ahead and unpushed — decide whether to push.

## RESUME (2026-08-01, superseded) — D10 IMPLEMENTED; A BATCH OF LOGGING MINORS LANDED

### STATE AT SESSION CLOSE (2026-08-01)

btr-shields HEAD **`84e7e4e`** ("rigs: post-cutover minors -- -v/-vv
logging, workdir cleanup (D10), readable rerun scripts"), one commit on
top of the cutover's `fce7eaf`. `main` **ahead 1 of origin, NOT pushed**.

Tree otherwise NOT clean — **Tobi has his own concurrent, uncommitted
edits in this same checkout** (`scripts/rigc/tests/integration/{conftest.py,
test_cmake_alone_entry.py,test_resolved_corpus.py}`, `.gitignore`, an
untracked `.env`), live-edited THROUGHOUT this session (confirmed by him
mid-session — see the traps below). None of it was touched by the driver;
none of it is in `84e7e4e`. Read those files fresh before assuming their
state from this handoff.

**Gate, driver-verified, FULL (not `CHECK_FAST`):** mypy **85 files**
clean, rigc unit suite **487 passed** (coverage 89% vs the 88 floor),
frozen suite **143 passed** in 3m18s — every `build`-marked test
(real `west build-rig --cmake-only` configures, including the
lotus/bridle-module case) included, not just the fast subset. ALL GREEN,
zero golden churn.

### WHAT LANDED THIS SESSION (all in `84e7e4e`, requested incrementally)

1. **`-v`/`-vv` on `expand`** — INFO/DEBUG on stderr; overrides `RIGC_LOG`
   when given. Format now carries a timestamp and the emitting function
   (`%(asctime)s %(levelname)s %(name)s:%(funcName)s`). Unit tests observe
   the `rigc` logger tree at DEBUG unconditionally, via a new autouse
   fixture in `scripts/rigc/tests/unit/conftest.py` — independent of
   whether a real stderr handler is attached.
2. **Readable rerun scripts, both sides** — `dtsio.py`'s "cpp argv" DEBUG
   lines now `shlex.join` instead of rendering a raw Python list.
   `cmake/dts.cmake`'s `rerun-expand.sh`/`message(VERBOSE)` rendering had
   a SEPARATE, hand-duplicated blanket-quoting path the driver initially
   missed (fixed `_rig_shell_quote_argv`/`_rig_shell_quote_env` first,
   then found the `rerun-expand.sh` `export` line loop had its own copy of
   the same "quote every token unconditionally" logic) — now both funnel
   through one shared `_rig_shell_quote_token` helper that quotes a token
   ONLY when it actually needs it (mirrors Python's `shlex.quote`).
   Verified against a REAL `west build-rig` configure's generated
   `rerun-expand.sh`, not just a standalone cmake-language test.
3. **D10 IMPLEMENTED** (cutover-decisions.md, now updated; backlog group A
   item 1, now CLOSED) — `cli.py::_expand` wraps its body in
   `try/finally`; an `accepted` flag (set only at the clean `return 0`)
   gates `shutil.rmtree(workdir)`; any non-zero exit keeps it (a cpp
   failure's own diagnostic points at that path); `RIGC_KEEP_WORKDIR`
   overrides the accept-path deletion. Unit tests pair
   accept-removes/reject-keeps as each other's negative control, plus a
   third for the env override.
4. **Emitter logging** (previously silent) — INFO phase markers in
   `emit()`/`write_artifacts()`/`context.render()`, DEBUG-then-INFO byte
   counts per artifact/file (see item 6).
5. **Loader logging** — an INFO summary per instance after topology
   assembly (`load()`, `loader/__init__.py`): `rig 'X': instance 'Y'
   requires shield 'Z', mated to socket 'W'` — covers nested/carrier
   sockets naturally (e.g. `mux_1.ch0`). Plus `dtsio.py::parse_tu`
   (confirmed by its own docstring as "the shield-TU entry point") now
   logs `shield TU: <name>` at INFO for every translation, eager-scan and
   lazy-revision-resolve alike.
6. **Directories + every file write, at INFO** — `cli.py` logs `workdir:
   <path>` and `out-dir: <path>` once each is resolved. Swept the WHOLE
   package for `open(..., "w"/"wb")` (four sites total: `emitter/__init__
   .py::write_artifacts`, `dtsio.py::parse_tu`/`check_include`/
   `resolve_token`) and every one now logs `wrote <path>` (the emitter's
   was DEBUG until this item generalized the ask to INFO everywhere).

All of it verified against REAL `west build-rig` configures at each step
(not just the unit/frozen suites), since none of this is exercised by the
suites' default silent-stderr paths.

### TRAPS THIS SESSION, both process not code

1. **A live collision, not a bug**: mid-session, `cli.py`'s `run_expand`
   equivalent in `scripts/rigc/tests/integration/conftest.py` picked up an
   unconditional `-vv` (Tobi's own in-progress edit, made in anticipation
   of the `-v`/`-vv` feature before it existed) — once the flag became
   real, every subprocess in the frozen suite started emitting DEBUG logs
   on stderr, corrupting 41 byte-exact `stderr.txt` goldens. Diagnosed via
   a probe insertion + direct `west build-rig`, not assumed; Tobi reverted
   it himself. **Lesson**: when two people edit the same checkout live,
   a sudden wave of unrelated-looking golden failures is worth suspecting
   as a collision before assuming a regression in the change just made.
2. **A live debugger, not a code bug**: later, every unit test reaching
   `cli.py::_expand` started failing `bdb.BdbQuit` — a `debugpy` adapter
   process was live (Tobi debugging in his editor with a breakpoint set);
   it resolved itself once his debug session ended. Same lesson: check
   `ps aux` for a live debug adapter before assuming a code regression
   when failures are this exotic.
3. **Side-by-side editing is standing practice now, not a one-off**: this
   session confirmed (again) that Tobi actively edits files in `btr-shields`
   (not just `btr-shields-review`) WHILE the driver works in the same
   checkout — `cli.py` itself got reformatted (black-style) and picked up
   an inert `# breakpoint()` comment mid-session, unrelated to the driver's
   own edits. Read a file fresh before editing it again; don't assume its
   state from an earlier Read in the same session.

### NEXT, in order

1. **LAZY SHIELD LIBRARY** — the item with real leverage, now the top of
   the standing queue (D10 no longer blocks it). C2 removed ONE of its two
   pins: `RIG_DEPENDS` breadth is free now (compared as a set), but
   **scan-time diagnostic ORDER is still pinned** because `stderr.txt`
   stays byte-exact. The slice must preserve diagnostic order or come with
   an explicit refreeze ruling.
2. Then the standing queue, unchanged: **hwmv2 revision semantics** (lands
   in `rigc/loader/axes.py`), **rig-schema.yaml**, **shield plurality**,
   **BRIDLE MIGRATION**, then **board-as-invocation-coordinate**.
3. `main` is ahead 1, unpushed — decide whether to push.
4. Reconcile with Tobi's own uncommitted edits (see STATE above) before
   starting new work in this checkout — they were never reviewed or
   tested by the driver this session.

## RESUME (2026-07-30c) — **CUTOVER COMPLETE. rigc IS THE TOOL; rigexp IS GONE.**

### STATE AT SESSION CLOSE (2026-07-30c)

btr-shields HEAD **`fce7eaf`** ("rigs: cutover C4"), tree CLEAN except an
untracked `.vscode/` (an editor artifact — gitignoring it is Tobi's call).
`main` is **ahead 9 of origin, NOT pushed** — the push is Tobi's decision.
Zephyr at the pin **`8da5b3a0f60`**, which IS the `tskr/zephyr-rigs` tip;
`west.yml` deliberately keeps a HASH rather than tracking the branch,
because the five carried commits are not upstream and that branch already
rebased once, silently invalidating a differential run.

**Gate, driver-verified:** `check.sh` ALL GREEN — mypy **84 files** (rigc
alone), rigc unit suite **479**, coverage **89%** against a new
`fail_under = 88` floor, frozen suite **143**.

Suite layout is now `scripts/rigc/tests/{unit,integration,fixtures,goldens}`.
`RIG_EXPAND_COMPILE` defaults to `rigc`. `build` is the only pytest marker.

### THE SEVEN CUTOVER COMMITS

| slice | commit | what landed |
|---|---|---|
| C1 | `6dbcc3d` | suite moved to rigc; rigc became the default; **differential retired** |
| C2a | `e128f9e` | `context.cmake` → key→value mapping, `RIG_DEPENDS` a SET |
| C2b | `46a40cd` | `config-sheet.md` → the facts it carries, total-coverage enforced |
| C2c | `d8d8b26` | `rig-gen.overlay` → split contract + a census guard |
| C2d | `3ef718a` | `rig-gen-includes.dtsi` → ordered list; banner normalization retired; `fail_under` |
| C3 | `d747514` | **rigexp retired** — 5246 deletions |
| C4 | `fce7eaf` | one discipline regime; `build` the only marker |

### WHAT THE CUTOVER ACTUALLY CHANGED (do not mis-summarise this)

Calling C2 "loosening the goldens" undersells it. **Rendering loosened;
MEANING tightened.** `context.cmake` now rejects a duplicate-key file that
bytes accepted; `config-sheet.md` enforces total line coverage, which byte
comparison never did; the overlay ties each annotation comment to the
position it describes, a pairing nothing checked before. That is why the
BRIDLE MIGRATION should now land without a refreeze tax.

Byte-exact **permanently, by owner ruling, not pending a comparator**:
`exit_code` and `stderr.txt`. The reject corpus's diagnostic wording is a
user-facing product surface. A C2d review caught a conftest docstring
actively inviting a future agent to loosen it; that sentence is fixed.

Deliberate golden edits across the whole cutover: **7 files** — C1's
classified path refreeze (6) and C2d's one banner token. **57 goldens still
spell `generated by rigexp`** in a banner comment no comparator reads: that
is deliberate, not drift, and §8.1's predicted 58-file refreeze became a
one-token hand edit because the comparators landed first.

### TWO NEW DOCUMENTS — READ BOTH BEFORE RESUMING

- **`cutover-decisions.md`** — D0–D11, every call the driver made
  unattended, each with its reasoning and rejected alternative. **D9, D10,
  D11 are SIGNED OFF** (2026-07-30c).
- **`post-cutover-backlog.md`** — **26 items in six groups**, the whole
  known-open surface. This is the queue; `parked.md` remains the long-term
  design park and is separate.

### NEXT, in order

1. **D10 — stop the expander leaking a temp workdir per invocation.** The
   only group-A item that is still work: design RATIFIED (delete on exit 0,
   keep on a reject, optional `RIGC_KEEP_WORKDIR`), no code written.
   Measured 7001 dirs / 787 MB in one session, and `/tmp` here is tmpfs, so
   it is RAM; `dts.cmake` runs the expander per configure, so every real
   build leaks one. Backlog group A item 1 has the acceptance criteria.
2. **LAZY SHIELD LIBRARY** — the item with real leverage. C2 removed ONE of
   its two pins: `RIG_DEPENDS` breadth is free now (compared as a set), but
   **scan-time diagnostic ORDER is still pinned** because `stderr.txt` stays
   byte-exact. The slice must preserve diagnostic order or come with an
   explicit refreeze ruling.
3. Then the standing queue: **hwmv2 revision semantics** (its brief predates
   the freeze and targets rigexp's `_parse_axis_decl` — it now lands in
   `rigc/loader/axes.py`, the seam R2 built for it), **rig-schema.yaml**,
   **shield plurality**, **BRIDLE MIGRATION**, then
   **board-as-invocation-coordinate**.

**CLOSED, no work:** the `shield-uart-subset-frdm` tier-2 build (D9 — its
goal is met by the byte-compared exception plus C2c's census guard), and
the exit-vocabulary collapse (D11 — §8.3 WITHDRAWN, not deferred: four live
`Unimplemented` sites are deliberate, so collapsing would be a
product-design slice authoring a new `lang-parse` diagnostic).

### PROCESS DISCIPLINE THIS RUN EARNED — carry it forward

**The integration suite cannot falsify a comparator.** Emitter output equals
the goldens, so a correct, weakened or GUTTED comparator passes all 143
tests identically — proven by injecting 10 mutations that all passed.
`tests/unit/test_compare.py` is the only thing between a refactor and a
silently-green comparator. **Every comparator guard now has a named
negative control, mutation-verified with a hash-checked restore.** Keep
that for any future comparator.

**A control's expectation must come from OUTSIDE the code it checks.** Three
times this run a control was vacuous because it derived its expectation
from the thing under test: R5's escape-order pair (two errors cancelled on
single-character input), C2d's two-header ordering (descending sort equalled
declaration order), and C4's launcher set (parametrizing over the set meant
dropping an entry just shrank the loop). All three passed while proving
nothing.

**A census-style test is falsified by mutating the WORLD it observes**,
never by editing its own assertion.

**Every review round found something real — 4 for 4 — and the best finds
were all one shape: a guard that passes while enforcing less than it
claims.** C1's directory guard would have skipped the entire frozen suite
while exiting 0. Ten comparator guards had no control. Eight build tests
were protected only by an incidental module-level marker. A deleted
assertion had no surviving equivalent. Do not skip the review round.

**Three ratified items rested on premises nobody had measured** (the tier-2
build's cost, then its benefit, then the exit vocabulary). §8's rulings were
drafted from code censuses that did not all exist yet. Treat a brief's
factual claims as checkable, not settled.

**Environment traps, all real:** `/tmp` is tmpfs, so pytest basetemps AND
the expander's leaked workdirs are charged to RAM and OOM-killed two runs;
pass no `--basetemp` for runs you will not inspect. `cmd | tail; echo $?`
reports tail's status and hid a failing gate for a full cycle. A stale
`.pyc` whose source has the same size and same-second mtime is considered
VALID by Python — purge `__pycache__` after any mutate-and-restore.

## RESUME (2026-07-30b, superseded) — R5 LANDED: 146/146, CONFORMANCE COMPLETE; cutover then run to C4

### STATE AT SESSION CLOSE (2026-07-30b)

btr-shields HEAD **`380f69c`** ("rigs: R5 — rigc emitter"), tree CLEAN,
`main` **ahead 2 of origin**. NOTE: `origin/main` sits at `2f93800`, so
the "ahead 8" in the previous block was STALE — seven commits were
pushed after it was written; only R4.5 and R5 are unpushed. Zephyr at
the pin `8da5b3a0f60`, no drift.

**The differential reads 146/146** (driver-verified twice, the second
time after a cache purge — see the trap below). rigc reproduces rigexp's
verdicts, diagnostics and artifacts over the whole corpus. `check.sh`
ALL GREEN: mypy 99 files, rigc unit suite **392**, frozen suite 146.
Coverage 89%; `emitter/{__init__,context,expectations}.py` 100%,
`overlay.py` 77%, `sheet.py` 59% (its section renderers are verified by
the reviewer's hand-differential against rigexp, not by unit test).

**R5 content** (brief `rigc-r5-brief.md`, RATIFIED with all six rulings
accepted as recommended): the emitter as a package of value functions
(`overlay`/`sheet`/`expectations`/`context` + composer), artifacts as
`{filename: bytes}` written by ONE shell with explicit UTF-8, `Solved`
FROZEN (closes M7), `context.cmake` rendered by a value function instead
of string-built in the CLI, and the RIG_DEPENDS closure (R3 review D3):
`load()` returns `(Rig | None, diagnostics, Deps)`, the four absent
recording points added, the five discarded values kept.

**Two byte-level facts now frozen by the accept goldens, both of which
PIN the lazy-shield-library slice** (still queued, still post-cutover):
deps follow resolution HISTORY not the final topology
(`pilot_variants_variant_c` keeps `adafruit_data_logger/shield.yml`
though `RIG_SHIELDS` is only `pilot_alt_button`), and the eager scan's
breadth is contract (`lotus_buttons`: 14 `.shield` for a rig naming 2).
The rig's own `dt-includes` headers stay ABSENT from RIG_DEPENDS.

**Review round: 1 major + 3 minors, all driver-applied.** The major was
a RATIFIED RULING SILENTLY UNIMPLEMENTED (frozen `Solved`, absent from
the diff and unmentioned in the report) — the precedent matters more
than the keyword: rulings must not become optional whenever the goldens
still pass. Minors: a TAUTOLOGICAL escape-order test (its expectation was
composed from single-character results, where the two errors cancel, so
it held under the WRONG order too); a stale `deps.py` docstring; and no
unit test for `_controllers`/`_synth_nexus_nodes`, whose only guard was
one golden each — which is exactly how this slice's one real bug (an em
dash typed as `--` inside an EMITTED comment literal) survived to a
200-second differential run. Emitted string literals are frozen
contract. The reviewer also ran a HARNESS POSITIVE CONTROL worth
reusing: `RIG_EXPAND_COMPILE=definitely_not_a_module` must fail with
"No module named", proving the knob really drives `python -m <module>`
and the 146/146 was genuinely rigc.

### ⚠ TRAP THAT COST A CYCLE THIS SESSION (both halves are process, not code)

1. **A red-proof mutation that preserves FILE SIZE, restored within the
   SAME SECOND, leaves stale bytecode Python trusts** — the `.pyc`
   validates on `(source mtime seconds, source size)` and both matched,
   so `check.sh` imported the MUTATED `_cmake_list_escape` while the
   source on disk was correct. After any restore: purge `__pycache__`
   (or `touch` the file), and verify the restore against a HASH taken
   BEFORE mutating — diffing the backup against the file you just copied
   from it is vacuous. See memory `reference_stale_pyc_same_second`.
2. **`cmd | tail -N; echo $?` reads tail's status, not the command's.**
   That read a FAILING gate as exit 0 and hid the truncation for a full
   cycle. `check.sh` exits immediately when the rigc suite fails, so its
   output stopped at the coverage table and the frozen suite never ran —
   the visible symptom of a hidden failure. Redirect to a log and read
   the exit code directly.

   Why the differential still read 146/146 against that bad bytecode:
   `_cmake_list_escape` behaves identically on every real path (none
   contain `;`, `"`, `\`), so NO golden can distinguish the orders. That
   is precisely why the reviewer's unit test for it was load-bearing.

### CUTOVER IN PROGRESS — **C1 + ALL OF C2 LANDED**; C3 dispatched, C4 next

**Read `cutover-decisions.md`** — every call the driver made unattended
(D0–D10), with reasoning and rejected alternatives. **D9 and D10 need the
owner's sign-off.**

| slice | commit | result |
|---|---|---|
| C1 move | `6dbcc3d` | suite at `scripts/rigc/tests/{unit,integration,fixtures,goldens}`; `RIG_EXPAND_COMPILE` default → `rigc`; differential RETIRED |
| C2a | `e128f9e` | `context.cmake` = key→value mapping; `RIG_DEPENDS` a SET, `RIG_SHIELDS` ordered |
| C2b | `46a40cd` | `config-sheet.md` = the facts it carries; total-coverage enforced |
| C2c | `d8d8b26` | `rig-gen.overlay` = split contract (semantics ride `zephyr.dts`) + census guard |
| C2d | `3ef718a` | `rig-gen-includes.dtsi` = ordered header list; `_normalize_banner` DELETED; `fail_under = 88` |

Gate at `3ef718a`: mypy **101**, rigc unit **471**, coverage **89%** vs the
88 floor, frozen suite **147**. The 147 is not drift — C2c ADDED one
non-build census test; no golden moved except the two deliberate edits
below.

**THE C2 HEADLINE:** §8.1's ruling (comparators BEFORE the banner
refreeze) paid off exactly as hoped — a predicted **58-file refreeze became
ONE token in ONE file**. 57 goldens still spell `generated by rigexp` in a
banner comment **no comparator reads**; that is deliberate, not drift.
Total deliberate golden edits across the whole cutover so far: 6 (C1's
classified path refreeze) + 1 (C2d's banner token) = **7 files**.

**Byte-exact PERMANENTLY, by owner ruling, not pending a comparator:**
`exit_code` and `stderr.txt`. The reject corpus's diagnostic wording is a
user-facing product surface. A C2d review found a conftest docstring
actively inviting a future agent to loosen it; that sentence is fixed.

**The discovery that shaped the whole series (D4):** the integration suite
has ZERO falsification power for a comparator — emitter output equals the
goldens, so a gutted comparator passes all 147 tests identically. Proven
by injecting 10 mutations that all passed. So `tests/unit/test_compare.py`
is the ONLY thing standing between a refactor and a silently-green
comparator, and **every comparator guard now has a named negative control,
mutation-verified with hash-checked restores.** Keep that discipline for
any future comparator.

**Traps this cost real time on, all recorded:** a stale `.pyc` Python
considers valid (same size + same-second mtime, D7's companion);
`cmd | tail; echo $?` reporting tail's status and hiding a failing gate;
`/tmp` being tmpfs so accumulated pytest basetemps AND the expander's
leaked workdirs OOM-kill build suites (D7, D10); and TWICE a negative
control made vacuous by a two-element example (R5's escape order, C2d's
header order) — a control needs an input that distinguishes the WRONG
implementations from each other, not merely from nothing.

### CUTOVER — earlier state, superseded: C1 LANDED `6dbcc3d`

`cutover-brief.md` is RATIFIED (all rulings; §8.2 resolved as the SPLIT
CONTRACT — see the brief). Sequence: C1 move ✅ → **C2 comparators (next,
one slice per artifact class)** → C3 retire rigexp → C4 discipline merge.

**C1 (`6dbcc3d`)**: 338 renames, only 89 insertions/67 deletions.
Suite lives at `scripts/rigc/tests/{unit,integration,fixtures,goldens}`.
`check.sh` ALL GREEN (mypy 99, unit **392**, frozen **146**),
`CHECK_FAST=1` green (66/80 deselected). Two classes of driver work rode
along, both ratified: three diagnostic sites now render paths through
`anchor_path` (documents.py, loader/__init__'s missing-content, and
boarddt's CWD-relative one — a real reproduction hazard), and the fixture
connector root moved OUT of `fixtures/dts/bindings/` to
`fixtures/dts/connectors/` because edtlib's recursive scan loaded both
halves' `socket,fixture-nexus` declarations and failed on the duplicate.
Classified refreeze: exactly 6 goldens, 6 lines out/6 in.

**⚠ THE DIFFERENTIAL IS RETIRED as of C1.** `RIG_EXPAND_COMPILE`'s
default is now `rigc`. rigexp's anchor rule is relpath against its OWN
package dir, so with fixtures under `scripts/rigc/` it cannot render them
the way the goldens carry them — no fixture location satisfies both.
Measured for the record: the rigexp direction reads **42 failed, 104
passed**, and that number is not a metric (it counts goldens containing a
path). rigexp production code is still on disk until C3.

**Driver lesson from C1, the same shape as R5's:** verifying ONE mechanism
is not verifying the class. `anchor_path` was proven inert and the
conclusion over-generalized; three sites bypassed it entirely. Also:
`check.sh`'s directory guard named the old path and would have SILENTLY
SKIPPED the whole frozen suite post-move while reporting green — a gate
that tests nothing looks exactly like a gate that passes. Check guards,
not just assertions, whenever paths move.

### The cutover plan (brief has the detail)

**Tobi's direction (2026-07-30b):** the goldens "have served their
purpose but become a burden to stay byte-identical for the next design
iterations." Byte-identity has exactly one job left, and R5 just
finished it (being the oracle for the differential).

`cutover-brief.md` carries the full plan and **6 flagged rulings**. The
headline ruling (§8.1) INVERTS the order this handoff previously
assumed: do the COMPARATORS BEFORE the banner refreeze, because every
artifact carrying the banner carries it in a COMMENT — so once the
overlay/context.cmake/config-sheet comparators stop comparing raw text,
the 58-file refreeze may disappear entirely instead of being performed
and mechanically verified. Slices: C1 move → C2 comparators → C3 retire
rigexp → C4 merge the discipline regimes.

Two facts the driver verified for that brief, both load-bearing:
- **The fixture move is byte-inert, proven not assumed.** `anchor_path()`
  (`rigc/diag.py:84`) renders paths relative to the `scripts/<module>/`
  component, so `goldens/route-no-via/stderr.txt` already reads
  `at tests/fixtures/...` with no module name — none of the 48 reject
  goldens churn when fixtures move to `scripts/rigc/tests/`. This is what
  R1 §3 ratified the module-agnostic rule FOR.
- **The banner class is exactly 58 files across the 19 accept dirs**
  (19 overlay + 19 config-sheet + 19 context.cmake + 1 includes.dtsi);
  NO reject golden carries it. Placeholder renames are a separate,
  smaller class: `<RIGEXP_WORKDIR>` 1 golden, `<RIGEXP_BUILD>` 18.

**RESOLVED at C4:** the two discipline regimes contradicted each other —
one required layer markers, the other forbade them — which is why rigc ran
as a separate pytest invocation. C4 dropped the layer markers entirely
(directory decides the layer), left `build` as the only marker, retired the
marker census and `scripts/markers.sh`, and replaced them with a static
guard asserting every build-reaching integration test is `build`-marked.
The two invocations REMAIN, now for exactly one reason: coverage must stay
scoped to the in-process unit layer.

The analysis behind the brief, kept here for continuity:

- **The burden is measurable in the queue**: 4 of 5 queued design items
  churn goldens for reasons unrelated to what they test. The sharpest is
  the BRIDLE MIGRATION — the eager scan makes RIG_DEPENDS O(tree size),
  so importing a 19-folder shield library rewrites every corpus rig's
  `context.cmake`. The lazy shield library is the burden in pure form: a
  fix with ZERO user-visible semantics, blocked only by frozen deps
  lists and scan-time diagnostic order. And `rig-gen.overlay`'s label
  scheme is explicitly parked-and-provisional (R10), i.e. the most
  expensive artifact to refreeze is one already meant to change.
- **The suite already contains the answer**: `dts_equiv.py` decided long
  ago that for the resolved devicetree, labels/phandles/ordering are not
  the contract. Extend that principle per artifact class: `exit_code`
  byte-exact; `zephyr.dts` unchanged; `rig-gen.overlay` structural;
  `context.cmake` a parsed mapping with RIG_DEPENDS as a SET
  (must-contain / must-not-contain); `config-sheet.md` asserted on the
  FACTS it must carry, never the rendering.
- **Do NOT loosen the reject corpus wording** — Tobi's own ratified
  position (2026-07-28) kept 40 tests precisely because they freeze
  user-facing diagnostic wording, a real product surface. What IS
  separable: diagnostic IDENTITY (category + anchor + which input
  rejects) stays hard; PROSE wants a cheap blessing path.
- **Ordering is absolute**: nothing loosens while rigexp is the oracle.
- **Acceptance criterion that makes loosening non-destructive**: land
  each new comparator with the goldens UNCHANGED and the suite still
  green. A comparator that accepts today's bytes is provably no weaker
  than the one it replaces — the T0b/T0c zero-churn standard applied to
  the test layer. Only after that does golden CONTENT become free.
- **Interaction**: as goldens loosen, the unit layer becomes primary
  correctness evidence, which makes the still-open `fail_under` ruling
  more consequential, not less.

Cutover's own mechanical steps are unchanged: frozen suite + fixtures
move to `scripts/rigc/tests/`, banner refreeze (58 goldens, one class —
rigc says "generated by rigc" and the harness normalizes it today),
un-pin `west.yml`, retire rigexp and `unimplemented.py`, flip
`RIG_EXPAND_COMPILE`'s default. Keep the banner refreeze in its OWN
commit, separate from the comparator change, or neither diff is
reviewable.

**Then**: lazy shield library → hwmv2 revision semantics → rig-schema.yaml
→ shield plurality → BRIDLE MIGRATION. `fail_under` ruling still open.
M8 (recipe-error tracebacks) parked on the post-conformance wart list
with the dt-includes deps wart.

## RESUME (2026-07-30, superseded) — R2..R4.5 LANDED; 94/146, ALL REJECTS GREEN; NEXT = R5 EMITTER BRIEF

### STATE AT SESSION CLOSE (2026-07-30)

btr-shields HEAD **`689903a`** (R4.5, on top of `2f93800`), tree CLEAN,
`main` **ahead 8 of origin, NOT pushed** (push decision still open).
Differential 94/146 with the red set byte-identical through every R4.5
layer (the T0b/T0c zero-churn standard, diffed mechanically). rigc unit
suite **355** (~0.4s), mypy **88 files**, `check.sh` green at commit.

**R4.5 (the INTERLUDE, Tobi-reviewed personally — no opus round) landed
in one commit, three layers:**
1. *Agent's parts A–C* (brief `rigc-r45-brief.md`, ratified): `load()`
   split into `_resolve_metadata` / `_gather_content` /
   `_build_topology` with frozen phase records (agent self-caught a
   D1-class LoadError boundary need in phase 3); the logging skeleton
   (`RIGC_LOG` env knob, NullHandler default, INFO=lifecycle,
   DEBUG=per-item+cpp argv, stderr-purity test); address allocation's
   value-shaped core (`allocate_scope_addresses` + AddressMember/
   Placement/Problem — closes R4-M2).
2. *Driver diff from the joint review*: diag.py trio (Literal severity;
   `ref is None` render guard with refs honestly Optional — closes
   R4-M6; LoadError asserts non-empty); rule-10 purification
   (FragmentPresence value, probes hoisted to `_gather_content`,
   `test_fragments.py` tmp_path-free, stem construction single-sourced
   in `*_contribution_names`); the DOCSTRING SWEEP (37 public functions
   now state returns + ownership).
3. *Test-readability sweep*: 65 inline `\n`-escape YAML/DTS strings →
   dedented `"""\` blocks; writing helpers dedent.

**Conventions RATIFIED this session (recorded in
`.claude/agents/rig-implementor.md` + memory):** docstrings state
returns+ownership (D1 was an ownership bug); IO at the edges, compute on
values (hoist reads, don't mock; emitter computes artifacts as
{filename: bytes}, one shell writes); tests write YAML/DTS as dedented
triple-quoted blocks.

**Live-run findings (Tobi's own logging test-drive):** the M8
recipe-error traceback family WIDENED — see the R5 queue entry; working
standalone invocation recipe = `--board-dts` + `--build-info` from any
`--cmake-only` configure (hand-assembled include dirs chase
base-board → zephyr dts roots → hal module dts, don't).

### NEXT: R5 — the emitter (write the brief first; queue item 3 below
has everything the brief must rule on: solved.wires never rig.wires,
artifacts-as-values law, deps recording points, frozen-Solved, the M8
family). Then fail_under ruling, then the standing queue.

**NEW WORK ITEM (Tobi, 2026-07-30, from reading the logs): LAZY SHIELD
LIBRARY — a named post-conformance slice, AT CUTOVER, BEFORE the bridle
migration.** The scan eagerly cpp-parses EVERY discoverable shield
template (nucleo_mux_farm's log: 13 eager TUs for a rig referencing 2)
— this does not scale (bridle = 19+ folders; a real upstream shields
tree worse), and it is the root of BOTH recorded §2 warts (one
malformed member poisons the whole scan; deps record
scanned-but-unreferenced shields). Fix = extend the EXISTING lazy path
(revisioned shields already defer to resolve()'s first selection) to
axis-less shields: discovery stays eager (folder walk + shield.yml,
cheap, keeps the known-shields census for lang-instance-shield), the
TU parse defers to first reference. One fix retires both warts AND the
scaling problem. PINNED until cutover by two byte-level facts:
scan-time diagnostic ORDER (broken shields report before rig-side
diags today — R3-review HD3 proved it; lazy moves/elides them) and
RIG_DEPENDS breadth (R5's accept goldens will freeze the eager set).
Lands as a deliberate refreeze-class step with the banner class.

## RESUME (2026-07-29, superseded) — R2 + R3 + R4 LANDED; DIFFERENTIAL 94/146, ALL REJECTS GREEN; NEXT = R4.5 THEN EMITTER

### STATE AT SESSION CLOSE (2026-07-29, updated after R4)

btr-shields HEAD **`2f93800`** ("rigs: R4 — rigc analyzer + board
reader"), tree CLEAN, `main` **ahead 7 of origin, NOT pushed**.
**Differential 94/146 — every reject golden green**; the 52 remaining
reds are exactly the accept corpus + reference shields + cmake-alone
family, all the controlled emitter refusal. rigc unit suite **325**
(audit-hook-verified: zero subprocess, zero production-data opens, zero
frozen-fixture reads), mypy **86 files**, coverage 88%.

**R4's review round, worth remembering:** the opus review REJECTED the
first pass on a defect its own probing found — `allocate_cs`
shallow-copied the gpio pass's returned nets dict (shared claim lists =
the banned accumulator via an alias; wrong diagnostic code + corrupted
Solved.nets on an input one step from frdm_cs_clash, uncatchable by any
golden). The implementor's hand-differential RECORD claimed that exact
site verified — **treat implementor verification records as hypotheses,
same as their code**. Its flagged CS-interleaving "divergence" was
DISPROVEN by probe (blueprint is itself two-phase). Driver fixed
(key-set + non-tautological regression test + SPDX header), reviewer
re-ran: byte-match, red set byte-identical pre/post fix. Full carry-
forward list in `2f93800`'s commit message.

R2/R3-era state below still applies (zephyr pin, gate commands, the
workdir-prefix gotcha). Zephyr
checkout RESTORED to the pin `8da5b3a0f60` (detached; it had drifted to
`tiacsys/main` — see the warning in the 2026-07-28b block; the drift made
one differential run read 25/146, which was environmental, not a
regression).

Gate GREEN, reviewer- and driver-verified: frozen suite 146, rigc unit
suite **217** (subprocess-free by AUDIT HOOK, zero production-data opens,
~0.25s), mypy clean over **62 files**, coverage 87% (cpp-invoking halves
of dtsio/library integration-only by construction; still no fail_under —
revisit was "after R2", now due). **Differential meter: 79/146** — 38 of
48 reject goldens green; the one reject remaining is `unmapped-socket`
(phys-socket). All 67 remaining reds are exit-3 refusals or clean
mismatches, zero tracebacks.

### What landed

**`0e6885f` R2 — the loader proper** (brief `rigc-r2-brief.md`, ratified;
19 flips, 45→64). Loader became a package: documents / axes (the hwmv2
seam — decl parse, resolution, normalization AND fragment-stem
construction in one module) / binding (SocketBinding, the S2 rules, one
seam) / fragments (rule 10) / delta (Topology + V1b engine). model.py
holds the value types. Recorded decisions in the commit message: unknown
content/delta keys silently ignored (rigexp-conformant); rigexp
TRACEBACKS on a list-shaped revisions: where rigc rejects cleanly
(no-golden divergence, recorded).

**`54a9d38` R3 — the shield library** (brief `rigc-r3-brief.md`,
ratified; 15 flips, 64→79). registry / dtsio (cpp+dtlib, $ZEPHYR_BASE at
call time only) / shields (FULL model port, nothing refused) /
loader/library (scan, shield.yml axes via R2's parser, lazy memoized
resolution) / loader/params. ShieldRef seam closed; wire node checks
live. GOTCHA recorded in cli.py: the workdir prefix must stay
`rigexp-` — the frozen conftest's `_WORKDIR_RE` is hardcoded.

**Process, both slices:** sonnet implementor → opus reviewer
(APPROVE-WITH-MINORS both times; every count independently re-measured)
→ driver applied the minors → commit. Real defects the reviews caught:
R2's variant fragment stem wrongly passed through revision normalization
(+ the seam-leak duplicate that invited it); R3's fatal LoadError path
DROPPED every previously accumulated diagnostic (LoadError now carries a
tuple, boundaries prepend — proven byte-identical on a
scan-finding-then-parse-error fixture; no frozen golden could catch it),
and the unit suite silently read production connector data through
`--connector-dir`'s None-fallback (audit-hook-verified fixed). BOTH
implementor agents stalled awaiting their own background gate — the
known pattern; resume with SendMessage listing what they still owe.
**The no-golden hand-differential rule is now ratified standing
discipline** (R2 brief §6): 13 hand-differential fixture sets across the
two slices; they caught 1 + 8 em-dash/wording drifts pre-review.

**Deps carry-forward for the emitter slice:** dependency data is
returned-value-shaped at the R3 recording points, but four blueprint
recording points are absent (rig.yml + the three content documents,
blueprint loader_yml.py:1185,786) and the values are currently discarded
in loader/__init__.py and cli.py. The emitter slice (RIG_DEPENDS) must
add them — recorded in R3's review as D3.

### NEXT, in order

1. ~~R4 — the analyzer~~ **LANDED `2f93800`** (ratified brief
   `rigc-r4-brief.md`; 15 flips, 79→94; acid test satisfied —
   `test_cs.py` answers the cs-gpios question scenario-free; REJECT →
   fix → APPROVE review round recorded above).
2. **R4.5 — loader-shape + logging mini-slice (Tobi, 2026-07-29, from
   joint code review; do BETWEEN R4 and the emitter). BRIEF DRAFTED:
   `rigc-r45-brief.md`, awaiting ratification (3 rulings: RIGC_LOG
   knob shape; execution mode — standing agent pattern vs DRIVER-LED,
   flagged because the slice's purpose is code understanding; Part C
   riding along).** Two
   behavior-preserving changes in one slice, acceptance = differential
   byte-identical (the T0b/T0c zero-golden-churn standard): (a) split
   `loader/__init__.py::load()` (~140 lines of glue, same smell the
   analysis flagged in the blueprint's 137-line load) into its three
   latent phases — `_resolve_metadata` (steps 2–5, cpp-free),
   `_gather_content` (6–9), `_build_topology` (10–11) — phase results as
   VALUE records, never a shared mutable context (§6); diag order
   preserved by concatenation; the cpp-free phases get unit tests
   (closes the reviewers' recurring 66–68% orchestration-coverage note,
   and pre-localizes the hwmv2 slice inside `_resolve_metadata`).
   (b) `logging` skeleton along those phase boundaries: package logger
   `rigc` with NullHandler, enable ONLY via env (`RIGC_LOG` — the argv
   surface is frozen); INFO = lifecycle (argv, scan summary, phase/pass
   entries, verdict), DEBUG = per-item results + THE CPP ARGV per
   invocation (T2's rerun.sh counterpart), WARNING/ERROR = tool-internal
   only — **log records describe the tool's execution, Diagnostics
   describe the user's input; logging must never become a second
   findings channel** (§6 in disguise). Plus a stderr-purity discipline
   test: a full main() run emits ONLY renderer bytes on stderr (Python's
   lastResort handler leaks WARNING+ to stderr when unconfigured — the
   golden-corruption trap this test pins shut). (c) **R4 review M2 rides
   along** (same behavior-preserving class): extract address
   allocation's value-shaped core the way CS got one — `_allocate_scope`
   currently threads a pass-local mutable result and `test_addresses.py`
   needs scenarios where `test_cs.py` doesn't. Acceptance for all three:
   goldens byte-identical. **(d) diag.py review notes (Tobi + driver,
   joint review 2026-07-29), driver applies at the R4.5 commit round
   (AFTER the implementor reports — no driver edits while it owns the
   tree):** severity becomes `Literal["error", "warning"]` (typo-proof
   at mypy level — this is the module where a typo becomes wrong frozen
   bytes); `_render_one` gets rigexp's `ref is None` guard (R4-M6 —
   otherwise any future Optional src field turns a diagnostic into a
   traceback); `LoadError` asserts a non-empty diags tuple (an empty one
   would render empty stderr + exit 1, a silent reject). All zero-churn
   class. **(e) Docstring interface convention (Tobi, RATIFIED
   2026-07-29, joint review):** every PUBLIC (cross-module) function's
   docstring states in prose (1) what it returns — tuple element
   meanings, None-semantics, ordering guarantees — and (2) OWNERSHIP
   (inputs read-only? who owns the result?); parameters only where
   name+type don't say it; private helpers may stay narrative; no
   reST/Google boilerplate, a "Returns …" sentence in house style.
   Rationale: measured 16 of 123 functions document their return, and
   R4's D1 was an OWNERSHIP bug prose contracts would have surfaced.
   Driver applies the ~23-function sweep at the R4.5 commit round and
   records the convention in `.claude/agents/rig-implementor.md`;
   future briefs inherit it. Enforcement = review, deliberately.
3. **R5, the emitter slice** — the 19 accept goldens + reference
   shields + resolved corpus + cmake-alone (52 reds) + context.cmake +
   RIG_DEPENDS (close the R3-D3 deps carry-forward: four blueprint
   recording points absent — rig.yml + the three content docs — and the
   threaded values currently discarded in loader/__init__ and cli).
   Brief must rule/record, from R4's review: **read `solved.wires`,
   never `rig.wires`** (they differ — resolved route vs raw via name; a
   silent wrong-overlay bug otherwise); whether `Solved` becomes frozen
   (M7); the `_render_one` ref-guard trigger (M6 — CLOSED by the R4.5
   driver diff); the RECIPE-ERROR TRACEBACK FAMILY (M8, WIDENED by
   Tobi's live run 2026-07-29): a bogus --build-info path AND an
   insufficient recipe (an extension board whose base-board/SoC/hal
   include dirs are missing) both escape as RuntimeError tracebacks —
   `edt_build.preprocess` raises RuntimeError identically in BOTH
   implementations (rigexp:114 = rigc:127, blueprint parity) — where a
   phys-board diagnostic belongs. Post-conformance wart list, or R5's
   brief if it touches cli's board step anyway. Standalone-invocation
   lesson: hand-assembled recipes chase base-board → zephyr dts roots →
   hal module dts; use --build-info from any real `--cmake-only`
   configure instead.
4. Coverage fail_under ruling (was deferred "until after R2").
5. Standing queue unchanged: hwmv2 revision semantics (lands in rigc's
   axes.py seam), rig-schema.yaml, shield plurality, CUTOVER, BRIDLE
   MIGRATION. Forward-looking: `board-as-invocation-coordinate.md`
   (design-log 2026-07-29a) — post-cutover.
6. `main` is ahead 6 unpushed — decide whether to push.

## RESUME (2026-07-28b) — rigc MISSION LAUNCHED: R0 + R1 LANDED

### STATE AT SESSION CLOSE (2026-07-28b)

btr-shields HEAD **`ecc3058`**, tree CLEAN, `main` **ahead 4 of origin,
NOT pushed** (`b62f466` zephyr pin, `28e8ce6` R0, `a49c980` R1,
`ecc3058` gate instrumentation). Tobi accepted R1 at session close and
the two-commit split landed after a fresh full-gate run (146 green).

Gate GREEN, driver-verified this session: mypy clean over BOTH packages
(39 files), rigc unit suite **44 passed** (~0.1s), frozen suite **146
passed**. `west.yml` is PINNED to zephyr `8da5b3a0f60` (`b62f466`, Tobi's
ruling) for the whole differential period; un-pin is a deliberate cutover
step. Workspace zephyr checkout is at that hash.

**⚠ WORKSPACE DRIFT (found 2026-07-29, driver): the zephyr checkout has
MOVED off the pin** — it sits at `e82cba12f38` on branch `tiacsys/main`
(clean tree, pinned hash still present locally; west.yml pin untouched).
The carried commits are missing there (shield-schema `template:` among
them), so EVERY build-marked test fails with "Malformed shield YAML …
'template' was unexpected" and edt reads break — a full differential run
on 2026-07-29 gave 25/146 instead of the true 45/146 baseline for exactly
this reason; that run is INVALID as a baseline, not a regression. Restore
before any gate run: `west update zephyr` (or `git -C zephyr checkout
8da5b3a0f60`). NOT restored by the driver — the checkout may belong to
other in-flight work (it looks like a deliberate branch checkout).

Gate commands (unchanged env vars, new knob):
`ZEPHYR_BASE=/wrk/z/ws-up/zephyr PYTHON=/wrk/z/ws-up/.venv/bin/python3
scripts/check.sh`, `CHECK_FAST=1` for the fast path, and prefix
**`RIG_EXPAND_COMPILE=rigc`** for the differential run (fast is currently
RED by design under rigc: 38/66, all controlled refusals).

### What landed / what's pending

**`b62f466`** — west.yml pins the rebased tiacsys tip (any red golden
during the differential is OURS by construction).

**`28e8ce6` — R0, the differential harness.** One knob,
`RIG_EXPAND_COMPILE` (Tobi's spelling), default `rigexp`: cmake cache var
(precedence `-D` > `$ENV` > default — the env fallback is what reaches
the frozen test files that bypass `board_extra_defines`) + the same-named
test-side env constant. Covers both argv sites, the `dts.cmake` source
GLOB feeding `CMAKE_CONFIGURE_DEPENDS` (the stale-configure trap the
inputs record missed), and every debug affordance. Golden comparison
normalizes exactly the `generated by <module>` banner token (**58**
goldens carry it — brief's 57 was a miscount, `lotus_buttons/
rig-gen-includes.dtsi` is the 58th), guarded byte-inert when the module
is `rigexp`. These conftest edits are the ONLY frozen-suite changes,
ratified. Implementor: sonnet.

**`a49c980` R1 — skeleton, CLI, diag core, proof of life.** Ran on
**FABLE** (Tobi's explicit per-slice override of the sonnet rule; memory
updated). Brief: `rigc-r1-brief.md` (ratified + post-ratification
amendment, below). Content: `cli.py` (frozen argv surface, in-process
`main(argv)`, exit vocabulary **0 accept / 1 reject / 2 usage / 3 not
implemented** — 3 is `unimplemented.py`'s loud refusal, so a differential
red is never mistakable for a wrong diagnostic); `diag.py` (diagnostics
are RETURN values, no accumulator exists in the package; ONE renderer;
the RATIFIED **module-agnostic anchor rule** — a path under
`scripts/<module>/` renders relative to that component, else absolute —
byte-identical to rigexp's own-package-dir rule on the whole corpus AND
fixture anchors survive cutover unchanged, so the 43 reject goldens'
anchor lines never refreeze); `loader.py` sliver (marked YAML,
construct-don't-parse filenames, the metadata/content key split, thin
revision selection; EVERYTHING out of scope raises Unimplemented — no
input exists on which rigc renders a wrong verdict).

**Differential baseline: 45/146** — but the honest meter is **4 of the
101 expander-dependent scenarios**: the four loader-shape rejects
(`missing-content-file`, `content-file-carries-board`,
`content-file-carries-sockets`, `revision-carries-board`), all
driver-re-verified byte-identical. The other 41 passers never invoke the
expander (18 corpus identity checks, 12 board reads, 5 cmake-entry
guards, 3 rigexp in-process unit tests, 3 file-level/meta).

**RULING (Tobi 2026-07-28, supersedes capability naming; memory
`feedback_unit_tests_name_their_unit`): unit test modules NAME THEIR
UNIT.** `test_<module>.py` mirrors the production module; sub-folders
`tests/unit/<module>/` when one unit needs several modules; tests may USE
other units but the named unit is the SUBJECT; the capability story moves
INSIDE the module. Driver applied the rework (8 capability modules → 4
unit-named + `test_layer_discipline.py` as the one recorded META
exemption, all 43 tests preserved) and the discipline test now ENFORCES
the naming (`test_unit_test_modules_name_their_unit`; exemptions =
`_META_MODULES`, additions deliberate). Suite is 44 tests.

**`ecc3058` instrumentation (driver, this session):**
- **Coverage over rigc's unit suite** — T3 dissolved exactly as
  predicted: in-process tests mean plain `coverage run -m pytest`, no
  pytest-cov (coverage.py 7.14.1 driven directly), config in pyproject
  `[tool.coverage.*]`, data + HTML under gitignored `.reports/`
  (`coverage-rigc-html/index.html`). Baseline **79%**: diag 100 / cli 90
  / loader 70 — the misses ARE the scenario paths the frozen integration
  suite covers through the front door, plus the subprocess-only
  `__main__`. **No fail_under yet — Tobi's call, revisit after R2.** The
  frozen rigexp suite stays deliberately unmeasured (subprocess suite;
  near-zero would be measured and believed).
- **junit → HTML** — `scripts/junit_html.py` (stdlib-only, same
  no-new-dependency rule; companion to timing_report.py over the same
  files) renders `.reports/junit-{rigc,fast,full}.html`: summary badges,
  failures-first expandable, per-module tables. check.sh now uses
  capture-render-reraise around BOTH pytest invocations so the reports
  exist for RED runs too (proven: differential fast run exited 1 with 38
  rendered failures).

**Docs this session:** `rigc-mission-brief.md` written and RATIFIED (§9
rulings: banner plan as recommended; knob = `RIG_EXPAND_COMPILE`; pin the
zephyr hash) — §6 naming bullet superseded in place, banner class
corrected to 58. `rigc-r1-brief.md` RATIFIED (anchor-root rule, separate
pytest invocation — forced by the frozen marker-discipline census whose
collected-item walk would fail rigc's marker-less tests — and exit 3) +
the post-ratification naming amendment.

### NEXT, in order

1. **R2 — the loader proper. BRIEF DRAFTED 2026-07-29
   (`rigc-r2-brief.md`), AWAITING RATIFICATION** — 4 flagged rulings
   (ShieldRef seam; the no-golden hand-differential rule; the 19-target
   list; implementor model). Targets 19 rejects (6 lang-schema + 3 rig
   lang-rev + 10 lang-variant, all census-verified single-error, no
   params), expected meter 45→64/146. Incorporates the SocketBinding seam
   from `board-as-invocation-coordinate.md` §6 (design-log 2026-07-29a)
   and the hwmv2 seam (axis decl/resolve as swappable value functions).
2. **R3 — the shield library. BRIEF DRAFTED 2026-07-29
   (`rigc-r3-brief.md`), AWAITING RATIFICATION** — 4 flagged rulings
   (slice size, with an R3a/R3b split offered; the cpp/unit-test seam;
   dependency data as returned value; implementor model). Targets 15
   rejects (shield.yml lang-schema 2, lang-shield-name, shield lang-rev 3,
   lang-param 6, lang-dt-include 3), expected meter 64→79/146. Closes
   R2's ShieldRef deferrals. Then **analyzer capabilities → emitter**, a
   brief per slice — analyzer is where the unit-naming rule and the
   `cs-gpios` acid test really bite (`tests/unit/analyzer/` sub-folder
   pattern).
3. **Standing queue behind the mission** (unchanged order): hwmv2
   revision semantics — NOTE its brief predates the freeze and targets
   `_parse_axis_decl` in rigexp; it now lands in RIGC's loader instead,
   re-read before dispatch — then metadata-only rig-schema.yaml, shield
   plurality, BRIDLE MIGRATION (tool = rigc).
4. At mission end: CUTOVER — frozen integration suite + fixtures move to
   `scripts/rigc/tests/`, banner refreeze (58 goldens, one class), un-pin
   west.yml, retire rigexp. Each is a deliberate recorded step.

**Workflow notes that keep paying:** driver verifies INDEPENDENTLY (this
session the habit corrected the brief's banner count via the agent, and
survived a false alarm from a PRUNED SHARED pytest tmp dir —
`/tmp/pytest-of-tobi` is shared across projects and pytest keeps only the
last 3 numbered roots, so never inspect a differential artifact without a
private `--basetemp`). R0's acceptance depended on knowing a delegating
stub passes the suite whether or not the knob reaches — pair every
delegation proof with a red proof at the same call site.

## MISSION CHANGE (Tobi, 2026-07-28) — rigexp is FROZEN; `rigc` is built from scratch

### STATE AT SESSION CLOSE (2026-07-28)

btr-shields **`7e35f33`**, tree CLEAN, **PUSHED** — `main` is in sync with
`origin/main` (tobiaskaestner/btr-zephyr-shields). 17 commits landed this
session. Gate GREEN at **146 passed**, mypy clean on 25 files.
`-m unit` 4 (0.50s) / `-m integration` 142 / `CHECK_FAST=1` 66.

**THE ZEPHYR CARRIED COMMITS WERE REBASED AND HAVE NEW HASHES.** The
`tiacsys/tskr/zephyr-rigs` branch was rewritten onto a different base (one
carrying tiacsys' own work, including `[tcs noup,temphack]` commits). The
workspace zephyr checkout is now IN SYNC with it. Any older hash in these
docs — design-log, the E-series briefs, cmake-fork-refactor-brief,
connector-unification-brief — is STALE; translate with this table rather than
trusting the old value:

| was | now | commit |
|---|---|---|
| `ca040c05cad` | **`8da5b3a0f60`** | schemas: shield `revisions:` block |
| `1a657124349` | **`c0025d3692a`** | edtlib: vendor-namespaced binding keys |
| `c1c4d2acf2d` | **`feb51fa0f70`** | edtlib: `*-cells` precedence fix |
| `76305e9aa49` | **`3f205005b99`** | schemas: shield `template` boolean |
| `df2c127228f` | **`3438c62f0dd`** | cmake: modules `cmake-modules` key |

Historical documents are deliberately NOT rewritten — a design log that gets
edited to match a later rebase stops being a record. This table is the single
place that reconciles them.

**Consequence worth acting on:** `btr-shields/west.yml:26` pins
`revision: tskr/zephyr-rigs` — a BRANCH NAME, not a hash. So a `west update`
now resolves to the rebased tree, which is not the tree most of this session's
gate runs validated against. Consider pinning a hash while `rigc` is built
against a known-good tree.

**rigexp's production code will not be touched again.** rigexp — INCLUDING its
tests — is the BLUEPRINT for building `rigc` from scratch in `scripts/rigc/`,
proper TDD, with `tests/unit` and `tests/integration` subdirectories. The
loader/analyzer/emitter decomposition stays; testable design gets the
attention it did not get the first time. **Writing that mission brief is the
NEW session's first job** — the ratified inputs are recorded in
**`rigc-mission-inputs.md`**, so write the brief from that record rather than
reconstructing it.

Headlines from it: the integration suite moves by **parameterising the
expander module name via a CMAKE VARIABLE** (ratified) rather than
copy-and-substitute, giving a differential harness over the same goldens —
exactly two invocation sites (`conftest.py:480`, `cmake/dts.cmake:347`), and
`PYTHONPATH` is already `<repo>/scripts` in both, so `-m rigc` resolves as
soon as the package exists. Fixtures copy as-is after the Part B restructure.
Unit tests are re-written, not moved. **THE GOLDENS ARE THE SPECIFICATION** —
the 43 reject goldens plus the emitted/resolved corpus are an executable list
of everything `rigc` must reproduce, and they are portable precisely BECAUSE
the integration tests only reach the expander through the CLI.

Consequently SUPERSEDED: `unit-test-layer-brief.md`'s slices U1/U2/U3 (they
extracted seams inside rigexp) — that document is retitled ANALYSIS and is a
design INPUT to rigc. `refactor-tests-plan.md` Part A likewise only matters
if rigexp's own test modules are ever reorganised, which the freeze makes
unlikely; **Part B (fixture tree) LANDED `7e35f33`** — 117 git-mv renames, one golden
change class (51 provenance-path lines across 43 goldens), and the finding
that fixture shields are CASE-SCOPED by construction (only 1 of 10 shared);
see `rigc-mission-inputs.md`. Part D (fixture shield renames) follows,
separately — see the revised
note there for why they must NOT be combined.

## RESUME (2026-07-27b) — S1 + S2 BOTH LANDED; V2 FULLY ABSORBED; NEXT = close the S2 test gap, then hwmv2 revision semantics

**State.** btr-shields HEAD **`bc63b50`** ("rigs: S2 — board per axis value"),
tree CLEAN, gate GREEN: **135 passed**, mypy clean on 22 files, verified over
three consecutive runs with golden drift clean each time. `main` is **ahead 7
of origin, NOT pushed**. zephyr carries `ca040c05cad`, **ahead 1 of tiacsys,
NOT pushed**.

**Landed this session, two commits:**
- **`da1e01f` S1** — the pure move. `rig.yml` is METADATA
  (`name:`/`board:`/`revisions:`/`variants:`, nested under `rig:`);
  `<rigname>.yml` is CONTENT (`instances:`/`wires:`/`dt-includes:`) as a FLAT
  top-level document. Content file REQUIRED (`lang-content`); an EMPTY
  `instances:` stays legal and distinct. Name CONSTRUCTED from the rig's own
  `name:`, never parsed from the folder. `_load_delta_doc` needed ZERO code
  changes to serve both base and fragments — the fragments finally have a base.
  Refreeze classification, driver-verified: 32 `RIG_DEPENDS` (additive only,
  set-compared), 34 provenance lines, 4 wording lines. `rig-gen.overlay`,
  `config-sheet.md`, `zephyr.dts` and `exit_code` never appear in the diff.
- **`bc63b50` S2** — board per axis value. **ONE RIG DESCRIPTION, MANY HOSTS.**

**What S2 actually delivers, at the author level:** `board:` moves under each
`variants:` list entry (entries may now be mappings, `{name:, board:,
sockets:}`); the content file names NO board and addresses sockets by abstract
name; each variant maps those names onto its own board's labels. Build
`ard_datalogger` or `ard_datalogger/frdm` from ONE description. The frdm tuple
carries NO fragment at all, which is the proof of content reuse. D10 is index
16 on both hosts and resolves to `gpiob 6` / `gpiod 0`.

**The board-swap rejection is DELETED, not lifted** — it existed because
resolution reads metadata BEFORE any content file opens while the override
arrived late from a fragment. Moving the key to the declaration removes the
contradiction rather than working around it. **V2 IS FULLY ABSORBED**: board
swapping is now a declaration, and `sockets:` positive-path coverage falls out
by construction.

Two more S2 changes worth remembering: the socket map now applies to the BASE
topology (it previously resolved only for instances a variant fragment
happened to restate, so abstract names were unusable), and rule 10 widened —
contribution = a fragment OR a resolved `(board, sockets)` DIFFERING from the
default's. Presence of the keys is deliberately not contribution.

**The S2 test gap is CLOSED — `8f5fb91`.** Eight reject fixtures (the six D2
shape rules, plus the `sockets:` half of the content-file rejection and the
SHIELD-owner spelling of the mapping-entry defect, which guards V1c's
`owner`-parameter regression). **All six were REACHABLE** — each fixture was
run through the expander before its test was written, specifically to find a
rejection shadowed by an earlier check; none was. Pure test addition, 175
insertions / 0 deletions, no production code, no golden churn, and none
build-marked (loader-level shape defects fail before any board is read), so
135 → 143 tests at no gate-time cost.

**RESIDUAL, pre-existing:** enumerating every `lang-schema` site to verify
that work turned up one still uncovered and OLDER than S2 — `"'list' must be a
non-empty list"`, from V1a. Worth a fixture when someone is next in
`test_tier1_goldens.py`.

**A real bug S2's agent found and fixed, worth knowing about:**
`list_rigs._resolve_axis` checked variant membership against `str()` of each
list entry — for a MAPPING entry that stringifies the whole dict, so a bare
`"frdm"` never matched. `-DRIG=ard_datalogger/frdm` would have failed through
cmake while the standalone loader accepted it: a silent split between the two
resolvers that must stay consistent. Driver reproduced it rather than trusting
the report.

**NEXT, in order:**
1. ~~Close the S2 test gap~~ **DONE `8f5fb91`.**
2. **hwmv2 revision semantics** (`hwmv2-revision-semantics-brief.md`).
   **INTERACTION:** that slice rewrites `_parse_axis_decl`, which S2 just
   changed to accept mapping entries gated on `allow_variant_metadata`. Read
   S2's version before writing the upstream revision block.
3. **rig-schema.yaml, metadata-only** (`rig-schema-brief.md`) — after 2. It
   then becomes what ENFORCES the split, and `additionalProperties: false`
   would also close the general unknown-key gap S1/S2 deliberately left in
   content files.
4. **Shield plurality** (pre-migration, `bridle-migration.md`).
5. Then the **BRIDLE MIGRATION** (tool = `rigc`).

**BACKLOG — TEST SUITE REFACTOR** (`refactor-tests-plan.md`, Tobi
2026-07-27): after the current queue, **DEFINITELY BEFORE the bridle
migration** (tests move there; refactoring after rewrites condensed
history). Part A = module structure: modules are named on FIVE different
axes today and none names a feature, so every feature slice lands in
`test_tier1_goldens.py` (1262 lines, 41% of test code, 6 features inside).
Rule: no module may MIX unit and integration tests — a file-level rule,
stronger than markers, with an enforcement test. Only ONE module mixes
today, and the feature clusters and the unit set are nearly the same set,
so a FEATURE split delivers the purity almost for free — a bare
unit/integration split would cement the mechanism naming and move the same
tests twice. Part B = the fixture tree becomes a Zephyr module rooted at
`fixtures/` (`boards/rigs/`, `boards/shields/`, `boards/mainboards/`,
`dts/bindings/connectors/`, `include/dt-bindings/connector/`); it is also
the cheapest place to prove the `mainboards/` layout before the real
rename. Part A before Part B; never concurrently with a feature slice.
T1 need NOT wait — markers are cheap to reapply after a move.

**QUEUED, order-independent — TEST INSTRUMENTATION** (`test-instrumentation-brief.md`,
Tobi 2026-07-27, NOT yet ratified): execution-time tracking, coverage
extraction, and a unit/integration split with coverage reported per suite.
Measured baseline: **97% of the ~206s gate is 81 build-marked tests; the other
62 finish in 5.33s**. Two findings — (1) the two stated definitions of "unit"
(synthetic-fixture vs needs-nothing-outside-rigexp) did NOT select the same
set, because after THE FLIP a synthetic fixture still needs a real board DT.
**RESOLVED by Tobi 2026-07-27: move whatever unit tests need INTO the fixture
tree**, since only the unit suite travels easily — that makes the two criteria
coincide. Precedent is half-built (`fixtures/controller-label/socket.dts` is a
standalone synthetic board, but its recipe still pulls `$ZEPHYR_BASE` and
`REPO_ROOT` bindings, and every real connector binding
`include:`s Zephyr's `base.yaml`/`gpio-nexus.yaml` — that chain is the whole
remaining dependency). Fixtures must be PURPOSE-BUILT synthetic connector
types, never copies of the real ones, or the unit suite goes green against a
stale contract. **T0b LANDED `0ab3c7f`** — connector roots configurable (one
`--connector-dir`; `<type>.h` rides the existing `--include-dir`), registry
resolved ONCE at CLI entry and threaded through loader/analyzer/emitter
(the emitter's four per-run re-globs are gone), plus a reference shield set
built end to end. A cross-cutting refactor through six modules with ZERO
golden churn. **T0c LANDED `340f0aa`** — `run_cpp` takes the caller's include dirs
(same shape as T0b's `parse_header_indices`, no new flag: reuses
`--include-dir`), so a fixture `.shield` can `#include` a fixture-tree
header. Reference shields now use `FIXTURE_D0`/`FIXTURE_CS` instead of
literals, so they finally demonstrate Convention 4 rather than inverting
it. ZERO golden churn was the acceptance criterion and it held — macros
expand to the values the literals had. NOTE: real builds pass
`--include-dir` too (`dts.cmake:155,165`), so shield cpp now searches
board dirs BEFORE the module's; benign (board dirs hold no
`dt-bindings/connector/` subtree) but it is a real ordering choice.
**mypy is 23 files, not 22** — `0ab3c7f`'s message misstates it.

**Superseded — the defect T0c fixed:** `dtsio.run_cpp` (`dtsio.py:59`)
hardcodes its cpp includes, so a fixture `.shield` cannot include a
fixture-tree header and the reference shields hardcode positions —
inverting Convention 4, the very thing they exist to teach. Fix is to reuse
`--include-dir`; do it BEFORE T1.

**T2 SCOPE EXPANDED (Tobi 2026-07-27): timing PLUS command visibility.**
`-s` cannot show what a build test ran — subprocesses are captured
programmatically (`conftest.py:352,440` `capture_output=True`), so
`print()` does not solve it. Verified gap: **NO assertion anywhere
interpolates the argv**, so a failing build test shows stdout/stderr but
never the command that produced them. Three parts: (1) `logging.info` the
argv, visible via `--log-cli-level=INFO`, no `-s` needed; (2) an
executable `rerun.sh` written into the test's tmp dir, mirroring
`dts.cmake`'s `rerun-expand.sh` which already survives a FAILED configure;
(3) argv in the failure assertions. Pairs with tmp retention —
`tmp_path_retention_policy` default is `failed` (failing dirs already
kept); `-o tmp_path_retention_policy=all` keeps passing ones too, verified.
Do NOT change the default in pyproject — 146 build dirs costs real disk.

**RATIFIED (Tobi 2026-07-28) — a unit test uses NO SUBPROCESS, and a reject
is not a unit concern.** Reaching a unit through the front door (the CLI) has
already made it an integration test; and a reject is an OUTCOME against a
SCENARIO, which does not exist at unit level — scenarios are consumed at the
system level (rigexp/rigc). So the unit layer does not duplicate the reject
corpus, it is NEW coverage of a different subject.
**Measured: there are THREE real unit tests, not 44** — 40 of the 44 drive
`python -m rigexp expand` as a subprocess and assert on rendered stderr
(`test_emitted_rejects` 39, `test_reference_shields` 1); only
`test_controller_label` (2) and `test_edt_build` (1) are in-process.
**This dissolves most of T3:** all the subprocess-coverage machinery existed
to measure coverage THROUGH the CLI, which is the integration suite where
coverage is not the priority. Unit coverage is just
`coverage run -m pytest -m unit` — no plumbing, no new dependency.
Plan: (1) reclassify the 40 as integration, KEEPING them (they freeze
user-facing diagnostic wording, a real contract); (2) build the unit layer,
own brief, the real work; (3) T3 over `-m unit`, now trivial.
**(1) LANDED `9983e27`** — unit 4 / integration 142; `-m unit` is 0.50s and
subprocess-free. **(2) BRIEFED: `unit-test-layer-brief.md`** (ratified, not
dispatched). Aim at STABLE CONTRACTS (test: would you want this contract kept
if the implementation were rewritten?). Tobi's requirement: **the unit tests
must tell the story of the design** — asked where `cs-gpios` is calculated,
the answer should be the tests that call it. So unit modules are named after
the CAPABILITY (`test_cs_allocation.py`), not the production module.
**Tobi's finding, now a first-class deliverable: the code is not very
testable.** Measured — 20 of analyzer.py's 23 functions take the mutable
`solved` accumulator and/or `diags`; only `_role_of`, `_soc_net` and two
formatters are value-shaped. `_allocate_cs(rig, solved, types, diags)` is the
worked example: the seam exists BY NAME but not BY SHAPE, so calling it means
constructing a scenario. Hence the layer is a sequence of small extractions,
each justified as a design improvement on its own, each proven
behaviour-preserving by goldens staying byte-identical (the T0b/T0c
acceptance). Slices U1 cs-allocation, U2 address-allocation, U3 the
already-value-shaped contracts, U4 = T3 coverage over `-m unit`.

**T0 LANDED `1a6638f`** — fixture-local `socket,fixture-nexus` vocabulary
(nexus props declared INLINE; every real connector binding pulls Zephyr's
`gpio-nexus.yaml`/`base.yaml`, which is what inline severs). Hermetic was
REDEFINED: `ZEPHYR_BASE` may be set purely to locate the devicetree package
— pip-vendoring it is REJECTED because this branch carries two non-upstream
edtlib patches (`c1c4d2acf2d`, `1a657124349`) a pip release would lack. The
criterion is NO ZEPHYR DATA, proven structurally by
`conftest.assert_fixture_local()`. **CEILING FOUND:**
`ctypes_registry.BINDINGS` is a hardcoded module constant, so a shield can
only MATE against the four real connector types — any shield-mating test is
stuck as integration until that dir becomes configurable and is threaded
through cli/loader/analyzer/emitter. **Decide that before T1;** (2) **every expander run is a SUBPROCESS**
(`conftest.py:357`), so naive coverage measures the harness and would report
near-zero on the very modules under test, plausibly enough to be believed.
`coverage` 7.14.1 is installed, `pytest-cov` is not — drive coverage.py
directly with `--parallel-mode` + `COVERAGE_PROCESS_START` rather than adding a
dependency. Do it BEFORE the bridle migration (tests move there); slice as
T1 split / T2 timing / T3 coverage, T1 first.

**Naming DECIDED this session (Tobi, recorded in `bridle-migration.md`):** the
board kind is **`mainboards/`** — `boards/{mainboards,shields,rigs}`, top-level
structure untouched. Costs ZERO code: `list_boards.py:231` rglobs
`boards/**/board.yml` at any depth, takes the dir as `board_yml.parent`, and
reads vendor from the FILE's `vendor:` key, never the path. `hosts/` was the
first choice and was rejected on a real collision — "host" means the build
machine in CMake/Zephyr. `bases/` collides with the extension vocabulary;
`targets/` recreates the residual-category error since a rig is a target too.

**Workflow note — the stall, and what it cost.** S2's agent STOPPED mid-slice
waiting on its own background gate, reporting nothing. The gate then finished
while the agent was idle, so it never saw the result. Recovery that worked:
wait for the agent's background process to exit, THEN resume it with
SendMessage listing exactly what verification it still owed. Do NOT resume it
while its own background work is in flight — that just produces a second
stall. The driver also pre-loaded two specific questions into the resume (two
unrequested files; a reject fixture with two goldens), both of which came back
with sound answers.

**NOTE — `claude/` is NOT a git repo.** All design work here is unversioned.

## RESUME (2026-07-27, superseded) — S1 (the metadata/content split) DONE + VERIFIED, UNCOMMITTED; NEXT = commit it, then S2

**State.** btr-shields HEAD still **`bfe8433`** (V1c); **S1 sits UNCOMMITTED**
in the working tree awaiting Tobi's accept. Gate GREEN: **125 passed** (124 +
one driver-added reject), mypy clean on 22 files, verified over two
consecutive runs with golden drift clean both times. `main` ahead 5 of origin,
NOT pushed; zephyr carries `ca040c05cad`, ahead 1 of tiacsys, NOT pushed.
Working tree: 133 paths, 49 of them new.

**What S1 did.** `rig.yml` is now METADATA only (`name:`/`board:`/`revisions:`/
`variants:`, still nested under `rig:`); `<rigname>.yml` is CONTENT
(`instances:`/`wires:`/`dt-includes:`) as a FLAT top-level document — 18
corpus rig content files, 32 fixtures split. The content file is REQUIRED
(new `lang-content` diagnostic; an EMPTY `instances:` list stays legal and
distinct, which 11 axis-rule fixtures rely on). Content filename is
CONSTRUCTED from the rig's own `name:`, never parsed from the folder.

**The predicted convergence held:** `_load_delta_doc` needed ZERO code changes
to serve both the base content file and the delta fragments — base and
fragment are now literally the same document shape, which is what "the
fragments finally have a base" means in practice.

**Dependency tracking, both mechanisms, and the second one is the subtle
half:** the loader `deps.see`s the content file (so it rides `RIG_DEPENDS`),
AND `dts.cmake` registers a constructed `_rig_content_yml` in the static
`CMAKE_CONFIGURE_DEPENDS` set **unconditionally, NOT gated on `EXISTS`** —
because a missing or broken content file means expansion never writes
`RIG_DEPENDS` at all, so only a static entry can retrigger configure once the
file is created or fixed.

**Pure-move evidence (the reason the slice was cut this way), verified by the
driver rather than accepted:** only two golden file types changed — 16
`context.cmake`, 14 `stderr.txt`. `rig-gen.overlay`, `config-sheet.md`,
`zephyr.dts` and `exit_code` never appear in the diff AT ALL. `RIG_DEPENDS` is
additive-only (scripted set-comparison: each of the 16 gains exactly one
`boards/rigs/*/<rigname>.yml`, loses nothing). Diagnostic text is
byte-identical apart from the `at PATH:LINE` line. Structural sweep: no
`rig.yml` anywhere still holds a content key, no content file holds a
top-level metadata key.

**Two driver fixes applied on top of the agent's work:**
1. **A stale diagnostic pointing at the wrong file** — `lang-dt-include` still
   said "add the header that defines it to rig.yml dt-includes:", which the
   split made false. Now names the actual content file
   (`param-unresolvable.yml dt-includes:`). The agent found this and
   deliberately left it to keep the golden diff inside the two allowed
   classes, then flagged it — the right call for an implementor, and the
   driver's to make.
2. **`lang-content` had no test** — verified by hand in a throwaway copy, so
   nothing in the suite covered it. Added the `missing-content-file` fixture
   and golden.

Final classification, three classes and nothing else: **32 `RIG_DEPENDS`
lines, 34 diagnostic source lines, 4 wording lines** (16/17/2 goldens, both
sides).

**NEXT, in order:**
1. **Commit S1**, with the refreeze justified by the classification above.
2. **Dispatch S2** — brief `rig-metadata-content-split-brief.md`, section S2:
   `board:` moves under each axis value; the socket map applies to the BASE
   topology rather than only where a delta restates `socket:`; rule 10 widens
   so a metadata-only contribution counts. The board-swapping rejection gets
   DELETED, not lifted. **V2 is fully absorbed once this lands.** Golden
   budget: the dual-host `ard_datalogger` rig, BOTH tuples built for real,
   with the frdm tuple carrying NO fragment so it proves content reuse across
   boards.
3. **hwmv2 revision semantics** (`hwmv2-revision-semantics-brief.md`).
4. **rig-schema.yaml, metadata-only** (`rig-schema-brief.md`) — after 3,
   because both predecessors change the keys it describes. It then becomes
   what ENFORCES the split.
5. **Shield plurality** (pre-migration, `bridle-migration.md`).
6. Then the **BRIDLE MIGRATION** (tool = `rigc`).

**Workflow note that keeps paying:** implementor on **sonnet** (standing rule,
memory `feedback_agents_run_sonnet`), contract inlined, agent STOPS and
reports, driver verifies INDEPENDENTLY — re-run the gate, classify the diff
yourself, treat "byte-identical"/"inert"/"code-verified" as hypotheses. S1's
report was accurate and its two self-flagged items were both real.

**NOTE — `claude/` is NOT a git repo.** All design work here is unversioned.

## RESUME (2026-07-26c, superseded) — V1c LANDED; V1 IS FEATURE-COMPLETE

**State.** btr-shields HEAD **`bfe8433`** ("rigs: V1c — shield revisions"),
tree CLEAN, gate GREEN: **124 passed**, mypy clean on 22 files, verified over
two consecutive runs with golden drift clean both times. `main` is **ahead 5
of origin, NOT pushed**. The zephyr checkout carries a FIFTH carried commit,
**`ca040c05cad`** ("schemas: shield: allow a `revisions:` block in
shield.yml"), standalone and upstreamable, **ahead 1 of tiacsys, NOT pushed**
— `list_shields.py` jsonschema-validates every shield.yml under
`additionalProperties: false`, so the block needed schema support exactly as
`template:` did (`76305e9aa49`).

**V1c content + the four driver fixes + the symmetric-provenance ruling are
in design-log 2026-07-26g.** Headline: shield revisions work via ONE
translation unit (base + `<name>_<rev>.shield`, DT overlay-by-label doing the
merge, no YAML vocabulary); review found four defects the agent had not seen,
including a reachable `AssertionError`; `model.Shield` gained
`revisions`/`revision` with the design decision recorded (the lifted freeze
requires one).

**Rig revision × shield revision COMPOSES with no code of its own, and is
now PINNED** — `shield_rev_family` (base resolves the sensor to revision 1,
the rig's own revision 2 moves it to the shield's revision 2), tier-1 plus a
real tier-2 build asserting both `zephyr.dts` and the collected
`i2c_sensor_2.conf`. Tobi asked whether it already worked; the driver
verified rather than trusting the agent's throwaway-script claim, then folded
it into the golden budget it had been missing from.

**The refreeze in `bfe8433`, justified:** 13 goldens moved and every changed
line is one of exactly two kinds — 13 × `RIG_DEPENDS` (additive only) and 1 ×
a new `RIG_SHIELD_REVISIONS`. A rig's shield.yml dependencies are tracked at
RESOLVE time, so a rig depends only on shields it names;
`pilot_variants_variant_c` picking up its variant-substituted
`pilot_alt_button/shield.yml` is the evidence that tracking follows the
RESOLVED topology rather than the declared one.

**NEXT, in order — the queue CHANGED at session end (design-log 2026-07-26h):**
0. **The rig.yml / `<rigname>.yml` SPLIT** — brief:
   `rig-metadata-content-split-brief.md` (RATIFIED, Tobi's own finding).
   `rig.yml` is not symmetric with board.yml/shield.yml because it is ALSO
   the `<rigname>.yml` that sits symmetric with `<board>.dts` /
   `<name>.shield`; both roles being YAML masked it. Metadata files are
   TYPE-named and carry no hardware; content files are INSTANCE-named — and
   our delta fragments are already instance-named with no same-stem base.
   **S1 = the pure move** (content keys out of rig.yml; acceptance is
   goldens byte-identical except provenance paths — a clean bisect point).
   **S2 = board per axis value + socket map applied to the BASE topology +
   rule 10 widened**, which DELETES the board-swapping rejection instead of
   lifting it and **absorbs V2 entirely**. Driver's sequencing call, which
   Tobi delegated: pull it in straight, ahead of everything below, because
   doing V2 first builds a fragment-aware resolver S2 retires, doing the
   schema first cements the conflation, and doing it after the migration
   rewrites freshly condensed history. ONE decision to settle first: the
   content file's name (recommendation `<rigname>.yml`, reasoning in the
   brief).
1. **hwmv2 revision semantics** — brief:
   `hwmv2-revision-semantics-brief.md` (RATIFIED 2026-07-26). Upstream's
   revision block and behaviour exactly: format typing, `exact:`,
   nearest-lower match, zero-append; NOT `format: custom` nor the
   filename-globbing revision discovery. Costs the one-schema-for-both-axes
   property deliberately; needs requested-vs-resolved in the model. Migrates
   rigs AND shields in one place (`_parse_axis_decl`), so the carried
   shield-schema commit gets rewritten before upstreaming — accepted churn.
2. **rig-schema.yaml + metadata** — brief: `rig-schema-brief.md` (RATIFIED).
   `full_name` required / `vendor` optional / target-regex `@` fix, plus
   signposting rejections for `rigs:` and `extend:`. Do it AFTER item 1 so
   the schema is authored against the final revision block.
3. ~~**V2-residue**~~ — **ABSORBED BY S2.** Board swapping becomes a
   declaration (no fragment-aware resolver is ever built) and `sockets:`
   positive-path coverage falls out of the dual-host rig by construction.
4. **Shield plurality** — pre-migration, see `bridle-migration.md`: bridle has
   ZERO shield.yml in 19 folders and runs on the legacy overlay-basename
   fallback. Plural `shields:` is to be ADOPTED (it declares the NAME SET;
   filenames are constructed from it, which is Q6's own discipline). Cost is
   one function; the identity ruling it needs was already made by V1c fix 2.
5. Then the **BRIDLE MIGRATION** (`bridle-migration.md`, tool = `rigc`).

**Doc work landed this session (claude/ only):** design-log 2026-07-26h (the
metadata/content split round — the three-role board argument, the worked
dual-host rig, the three changes the split requires) and its brief; 2026-07-26f (the
rig.yml/board.yml key-by-key delta and three rulings) and 2026-07-26g (this
review); ontology §7's symmetry heuristic widened to **BIDIRECTIONAL** with a
six-cell table — the one-directional form is why board→rig gaps accumulated
unnoticed; `bridle-migration.md` gained the shield-plurality task with the
per-folder triage (`grove_btn`/`grove_led`'s 64 overlays collapse to ONE
template; `waveshare_pico_10dof_imu_sensor`'s `_r1`/`_r2` is a real shield
revision; `rpi_pico_lcd`'s 11 LCDs are the only true residue).

**NOTE — `claude/` is NOT a git repo** (the 2026-07-26b block below claims it
is and says to commit it first; that is wrong as of this session). Design
work here is unversioned; treat that as a risk when it matters.

**Two verification rules, both earned:** after a stalled/resumed slice run the
suite TWICE and diff the goldens; and treat an agent's own
"inert"/"cosmetic"/"code-verified" claims as HYPOTHESES — this session that
rule caught a wrong-blaming diagnostic, a silent identity fallback, a
reachable assert, and a dependency-tracking hole.

## RESUME (2026-07-26b, superseded) — V1a + V1b LANDED; NEXT = V1c, then V2-residue

**State.** btr-shields HEAD **`5995f08`**, tree CLEAN, gate GREEN
(**109 passed**, mypy clean on 22 files). Gate unchanged:
`ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PYTHON=/wrk/z/ws-up/.venv/bin/python3 btr-shields/scripts/check.sh`.
`main` is **ahead 4 of origin, NOT pushed**. **`claude/` is itself a git
repo and ALL this session's design work is UNCOMMITTED there** — the
readiness pass, the V1 spec, `bridle-migration.md` and the design-log
entries exist only in the working tree. Commit that first thing.

**Landed this session (11 commits):** slices A / B1 / B2 / C' / P / R, the
three comment sweeps (`d285554` `1c8068f` `df98521`), then **V1a
`5031a0f`** (qualified targets resolve; per-axis fragments collect) and
**V1b `5995f08`** (the delta engine). Gate went 72 -> 74 -> 81 -> 98 -> 109.

**NEXT, in order:**
1. **V1c — shield revisions.** The DT side: base `<name>.shield` plus
   `<name>_<rev>.shield` cpp-included after it into the SAME translation
   unit, DT's own overlay-by-label semantics doing the merge (no YAML
   vocabulary on the shield side at all). `shield: <name>@<rev>`
   references, `shield.yml` gaining the same `revisions:` block, rule 13.
   Spec: `rig-variants-revisions.md` §"V1 — IMPLEMENTOR-READY SPEC" §4
   and §6 rule 13. Golden budget: give one corpus shield a rev 2 whose
   DEFAULT stays rev 1, so every existing row is untouched by
   construction, plus one new accept tuple exercising `shield: <name>@2`.
2. **V2-residue** — and it is small, because V1a/V1b absorbed the rest
   (see design-log 2026-07-26e). Two items:
   - **board swapping.** A variant's `board:` is currently REJECTED with a
     loud not-yet-wired diagnostic. The requirement is UNCHANGED and the
     key stays variant-only in the vocabulary; what is missing is a
     fragment-aware resolver: `list_rigs.py` resolves the board BEFORE any
     fragment is read, so applying an override in the loader made the
     model / overlay header / `RIG_BOARD` disagree with the board actually
     built. Lift the rejection in the slice that makes resolution read
     deltas. It belongs with the rig-swap guard / `RIG_INFERRED_BOARD` /
     RIG-BOARD-exclusivity surface — give it its own review.
   - **`sockets:` positive-path coverage.** Abstract->label translation is
     implemented (`resolve_socket` in `_apply_delta`) but only its
     rejection path is tested; rule 5's rejection is demonstrated via
     `board:` only (same code branch).
3. Then the **BRIDLE MIGRATION** — `bridle-migration.md` is the plan
   (commit sequence with a stands-alone-because column, three-way content
   triage, the zephyr prerequisites, naming DECIDED as **`rigc`**, and a
   pre-migration task: both comment sweeps MISSED
   `dts/bindings/connectors/*.yaml` and `include/dt-bindings/connector/*.h`,
   which carry the heaviest archaeology AND are the most public artifacts).

**Two rules learned, both about verification:**
- **After a stalled/resumed slice, run the suite TWICE and diff the
  goldens.** V1b's agent stalled; the resumed run left a duplicated
  golden-freeze block that wrote one fixture's diagnostic into ANOTHER
  fixture's golden while the second test lost its freeze entirely — a
  committed golden that was wrong and asserted by nothing. The gate stayed
  green because nothing checked it. A clobbering freeze only surfaces on a
  second run; a golden nobody asserts never surfaces at all.
- **"Accepted but inert" deserves a second look.** V1b reported a
  variant's `board:` as cosmetic; it actually flowed into the overlay
  header and `RIG_BOARD`, so it was an active disagreement with the built
  board, not a no-op.

**Also open (unchanged):** the `edt_build.build_edt()`/`preprocess()`
coverage gap before that BSD-3 reader upstreams; `rig-gen.conf` is never
produced so every build prints a misleading "no Kconfig fragment produced";
`_RIG_BTR_ROOT` -> `ZEPHYR_BTR_SHIELDS_MODULE_DIR`; normalize-on-freeze
should strip line numbers; a native-socket-board corpus row (all four
targets are extension variants — recorded as a risk against migration
commit 2); the `aliases:`/`chosen:` companion, unscheduled.

**Workflow (eight slices in, it works):** implementor agent per slice
(contract inlined, sonnet), agent STOPS and reports, driver verifies
INDEPENDENTLY — re-run the gate yourself, read the diff, and treat the
agent's own "no churn"/"inert"/"fine" claims as hypotheses. Three of the
last four slices had a real defect or spec bug that only independent
verification caught. Joint driver+Tobi review, driver applies minors and
commits. RULE: a SendMessage-resumed agent owns the checkout until its NEXT
report.

## RESUME (2026-07-26, superseded) — comment sweeps + V1 readiness pass

**State.** btr-shields HEAD **`df98521`**, tree CLEAN, gate GREEN
(**81 passed**, mypy clean on 22 files -- `rigexp.model` is OFF the mypy
exemption list, which holds only `devicetree.*`). `origin/main` is at
`d285554`, so the last two commits are UNPUSHED. Gate unchanged:
`ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PYTHON=/wrk/z/ws-up/.venv/bin/python3 btr-shields/scripts/check.sh`.
`main` is **ahead 5 of origin, NOT pushed** (Tobi's call). zephyr checkout
= branch `tskr/zephyr-rigs`, FOUR carried commits, all pushed to tiacsys —
**no fifth carried commit is needed** (see C' below). Bridle still NOT in
the manifest; lotus builds pass `-DEXTRA_ZEPHYR_MODULES=<topdir>/bridle`.

**This session, EIGHT slices, all committed after joint review:**
- **`2378fab` slice A — controller-label determinism.**
  `_controller_label` → `labels[0]` (the DEFINING label), closing the E3
  regression at its root. HALF DEFERRED TO V1: analyzer diagnostics
  sourcing controller identity independently of the emitter needs
  `model.BoardSocket.pwm_map` widened = the model.py freeze lifted.
- **`eb929e0` slice B1 — rig<->board naming symmetry (Tobi's ruling).**
  Rig names UNDERSCORED throughout; `rig.conf` → `<rigname>_defconfig`,
  `rig.overlay` → `<rigname>.overlay`; folders renamed to rig identity;
  `RigCase` collapsed to one field.
- **`3660303` slice B2 — de-provenance sweep.** Test framing recast as
  timeless contract language; BSD-3 `test_edt_build.py` split out
  (partial by design); unknown-board + module.yml grooming.
- **`76b45cf` slice C' — rig Kconfig fragments ride `shield_conf_files`.**
  Tobi first wanted the rig defconfig applied BEFORE prj.conf, then
  WITHDREW that on evidence (no pre-prj slot exists upstream for a
  module; it would have needed a 5th carried commit AND dragged shield
  confs ahead of prj.conf). The ratified move is precedence-IDENTICAL and
  keeps the app-level overlay machinery undisturbed until after V1/V2.
- **`454b7c7` slice P — per-instance parameters.** Design settled in a
  three-pushback round with Tobi, then implemented: `shield,params` per
  device node (property PRESENT = default, ABSENT = required); rig.yml
  `params:` (block style — see below) + `dt-includes:`; loader resolves
  tokens against exactly the declared headers (six rules, `lang-param`/
  `lang-dt-include`), emitter emits the SYMBOL verbatim; new
  `rig-gen-includes.dtsi` pulled in by a quoted `#include` from
  `rig-gen.overlay` (resolution PROVEN with a real build). Trigger bug
  dead at the root: grove_btn's type-level `zephyr,code` is gone and
  lotus_buttons' buttons resolve to distinct keycodes (0xb/0x2, both were
  `<11>`). **model.py freeze LIFTED** — replaced by "a model change
  requires a recorded design decision"; `rigexp.model` came off the mypy
  exemption list. `invert:` deliberately NOT folded in (it is a flag
  transform, not a property assignment).

- **`ca31821` slice R — `rig-shields` -> `shield-templates`.** Closes the
  last live item of the parked rig-/.rig. prefix cleanup. Wrapper KEPT (it
  marks a file as a template rather than an overlay to apply) with the
  reasoning recorded at the parse site.
- **`d285554` + `1c8068f` + `df98521` — the comment sweeps.** Tobi's own
  pass over the three cmake forks, then the mechanics layer (12 production
  modules), then tests + content. Design-process archaeology out; markdown
  quoting of identifiers out (double quotes only for literal VALUES);
  convention recorded in `.claude/agents/rig-implementor.md` so it does not
  come back. Comment-only PROVEN by AST-shape comparison, not asserted.
  KEPT deliberately: the bridle-64-overlays product argument.

**NEXT: dispatch V1a.** The readiness pass is DONE (2026-07-26) and
`rig-variants-revisions.md` §"V1 — IMPLEMENTOR-READY SPEC" is the
contract — selection grammar, declarations, fragment construction,
resolution order + the per-stage invariant, the merge vocabulary, 13
numbered validation rules with codes, provenance, model additions, golden
budget, and a slicing recommendation. Round record: design-log 2026-07-26a.

TERMINOLOGY, do not conflate: **V1 = the delta engine + revisions + shield
revisions; V2 = VARIANTS** (variants ride the engine V1 builds). Order
ratified: **P → V1 → V2**; P is DONE.

**Slicing (driver recommendation in the spec, not yet dispatched):**
- **V1a — selection and collection.** Qualifier resolution end to end
  (list_rigs.py, west rigs, build-rig, the cmake forks), the declaration
  blocks, fragment-name construction/discovery, provenance. NO deltas: a
  selected axis supplying only .overlay/_defconfig files is already useful
  and fully testable.
- **V1b — the delta engine.** Vocabulary, resolution order, the per-stage
  invariant, rules 5-12. Slice A's deferred analyzer-independence half can
  ride here (it is already in the model).
- **V1c — shield revisions.** The DT side, `shield: <name>@<rev>`, rule 13.

**Four decisions the readiness pass added** (details in the spec):
1. Diagnostics are `lang-rev`/`lang-variant`, SUPERSEDING Q7's `phys-*`.
   Physical WORDING is unchanged; only the family moved.
2. `params:` replaces wholesale (required, not merely acceptable) PLUS a
   restate-check for same-shield deltas, which kills a silent revert to the
   shield default.
3. A per-stage parameter invariant REPLACES the proposed
   variants-may-add/revisions-may-not asymmetry.
4. `dt-includes:` UNIONS across stages — the one key with union semantics.
Plus a found limitation: family-wide revisions cannot re-parametrize a
variant-substituted instance (device labels differ per shield); validated
by rule 12, with per-variant revision streams recorded as the escape hatch
(Q9's "real case" has now arrived).

Superseded, kept for reference — what the pass had to settle:
1. **Fragment filenames** — already re-derived under the B1 rename, with
   the board+shield analogy table, in `rig-variants-revisions.md`
   §"FRAGMENT FILENAMES re-derived". Q6's construct-don't-parse mechanic is
   untouched; only the prefix moved. DECIDED: shield revision Kconfig
   fragments are `<name>_<rev>.conf` (shield convention); rigs use
   `_defconfig` (board convention) because a rig OWNS a board.
2. **A ratified-but-now-inconsistent diagnostic family.** Q7 specified
   `phys-rev`/`phys-variant`. Slice P established from the code that
   `lang-*` is the DECLARATION/ASSIGNMENT family and `phys-*` is for
   PHYSICAL conflicts — and "rev 2 removes instance 'th2', which variant
   'frdm' does not have" is a declaration error, not a physics violation.
   Settle this rather than inheriting the collision.
3. **`params:` under a delta.** As an instance top-level key it is
   REPLACED WHOLESALE (Q7's no-deep-merge rule, deliberately kept intact
   rather than carving a silent exception). So a revision changing one
   keycode restates that instance's parameters. Coarse; revisit only if it
   bites, and never by making the merge silently deeper.
4. Then V2 (variants on the same engine), then the BRIDLE MIGRATION.

**Slice A's deferred half is now UNBLOCKED** (the freeze is lifted):
analyzer diagnostics sourcing controller identity independently of the
emitter's pick needs `model.BoardSocket.pwm_map`'s tuple widened. Do it
with V1 or as its own small slice.

**Companion feature identified, NOT scheduled (Tobi has not ruled):**
rig-level `aliases:`/`chosen:` addressing instance devices symbolically
(`sw0: btn_start.gb_key`) — same rig-level-assignment family as
parameters, and it would retire Conv. 8's accepted trade (today the rig
author hand-writes emitter-generated label spellings in
`<rigname>.overlay`, where a typo silently creates a fresh node). Needs
its own addressing + diagnostics and reopens Conv. 8, so it was kept out
of V1 deliberately. See design-log 2026-07-25h.

**Open items Tobi must decide (not blocking V1):**
- **`rig-shields`** — the DT subtree name every `.shield` wraps content
  in. The one real decision left from the naming sweep; highest blast
  radius (13 shield files + 3 tier-1 goldens' diagnostic paths). See
  `parked.md` — the rest of that parked item is now MOOT (the `.rig.*`
  infixes are gone, the `/ { rig { } }` node never existed).
- **Push `main`** (ahead 5).

**Three gaps recorded this session, none blocking:**
- **`edt_build.build_edt()`/`preprocess()` have NO dedicated test** —
  every exercise goes through `board_edt`'s higher-level API. Fill before
  that BSD-3 reader upstreams to python-devicetree.
- **`rig-gen.conf` is never produced** — the emitter has no such output
  key, so the generated Kconfig fragment is designed-but-unimplemented
  (parked "Kconfig layering"). Every rig build prints `rig: no Kconfig
  fragment produced`, which reads like a fault; reword or drop that
  STATUS line when the feature is picked up.
- **Slice P's rule-6 golden freezes a diagnostic CASCADE** — a
  `dt-includes` header that does not exist reports the header failure
  (root cause, first) AND a consequent unresolvable-token error for the
  same assignment. Acceptable as-is; if the consequent is ever suppressed,
  that golden updates.

**Two rules learned this session — apply them, they cost real time:**
- **The gate passing is NOT evidence that goldens match the tree.** Any
  edit changing a file's LINE COUNT invalidates every tier-2 provenance
  comment citing it, and `dts_equiv` ignores comments so nothing fails.
  A one-line comment rewrap in `grove_sockets.dtsi` silently staled 152
  references. Strengthens the parked normalize-on-freeze item: it should
  strip line numbers.
- **When a value has a raw user-supplied form and a resolved form, derive
  from the RESOLVED one.** B1 derived filenames from `${RIG}`, which will
  carry `@rev/variant` once V1 lands — and since both fragments are
  optional, that degrades to a SILENTLY unapplied defconfig. Now uses
  `_RIG_RESOLVED_NAME`.

**Workflow (unchanged, and it worked well five times):** implementor agent
per slice (contract inlined via general-purpose, sonnet), agent STOPS and
reports, driver verifies INDEPENDENTLY (re-run the gate yourself; read the
diff; the agent's report understated the blast radius twice), joint
driver+Tobi review, driver applies minors and commits. RULE: a
SendMessage-resumed agent owns the checkout until its NEXT report.

## RESUME (2026-07-25, superseded) — EXTENSION MIGRATION E1-E4 COMPLETE; NEXT = de-provenance sweep, then V1

**State.** btr-shields HEAD **`90b4126`**, tree CLEAN, gate GREEN
(**72 passed**; count moves with parametrization, see 07-25c ledger).
Gate: `ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PYTHON=/wrk/z/ws-up/.venv/bin/python3 btr-shields/scripts/check.sh`.
zephyr checkout = branch `tskr/zephyr-rigs`, FOUR carried commits
(cmake-modules, shield template, edtlib *-cells precedence fix, edtlib
vendor-namespaced keys), all pushed to tiacsys. Bridle: NOT in the
manifest (deliberate, 2026-07-24f) — lotus builds pass
`-DEXTRA_ZEPHYR_MODULES=<topdir>/bridle`; harness threads it per-case.

**This session's arc (design-log 2026-07-24 a–f, 2026-07-25 a–c):**
fork-per-phase cmake refactor → cmake-alone entry (-DRIG = sole physical
coordinate; excludes BOARD and SHIELD; rig-swap guard) → rig-gen.*
rename + vendor prefixes → edtlib carried commits → connector
unification (plug,* keys, dts/bindings/connectors/, dts/connectors
gone) → E2/E3/E4 (ALL boards now hwmv2 extensions of their real bases;
clones deleted). TRAJECTORY (2026-07-25): after V1/V2 the content
migrates INTO BRIDLE (Tobi maintains it), commits recreated condensed,
then upstreamed to zephyr in chunks.

**NEXT, in order:**
1. **Test-suite de-provenance sweep** (unblocked by E4; deadline = the
   bridle migration): timeless contract docstrings, sort tests by
   upstream destination, rename s1/s5-style rig folders to rig names;
   fold in the naming sweep (parked.md) and the small grooming items
   (unknown-board empty known-list; zephyr/module.yml stale comment).
2. **Controller-label determinism + diagnostic wording** (queued at E3
   review — implementation-plan bullet; tcc0→grove_pwm_d19 evidence).
3. **V1/V2** (rig-variants-revisions.md; V1's design round ALSO settles
   per-instance parameters + lifts the model.py freeze).
4. Then the BRIDLE MIGRATION (workspace switch, condensed history; see
   2026-07-25 trajectory ledger entry for the recorded implications).

**Workflow (unchanged):** implementor agent per slice (contract inlined
via general-purpose, sonnet), joint driver+Tobi review (reviewer agent
on request), driver commits after Tobi's accept. RULE: a
SendMessage-resumed agent owns the checkout until its NEXT report
(memory feedback_resumed_agent_owns_tree).

## RESUME (2026-07-24c) — cmake-alone entry LANDED (+ vendor-prefixes + rig-gen rename); NEXT = E2-E4, then edtlib carried commit, then V1

**TRAJECTORY (2026-07-25, read design-log entry): after V1/V2 the content
upstreams INTO BRIDLE** (Tobi = bridle maintainer; workspace switch,
commits recreated condensed, then zephyr in small chunks from there).
Shapes current work: don't over-polish the E3 lotus extension (dissolves
at migration), sweeps' deadline = migration, carried commit #1 may retire
via bridle's ZephyrBuild hook.

**Landed since the block below (all pushed, HEAD `03790fc`, tree CLEAN,
gate 69 passed):**
- **`a51553b` cmake-alone rig entry** — -DRIG is the sole physical
  coordinate: slot-10 inference via list_rigs.py query mode (full
  `name[@rev][/variant]` grammar, loud V1/V2 placeholders); RIG excludes
  BOARD (RIG_INFERRED_BOARD marker, survives reconfigures) AND SHIELD
  (zephyr_get guard in the shields fork — was a silent no-op); rig-swap
  guard (joint-review finding: changing -DRIG to a different-board rig in
  an existing dir previously expanded against the STALE board with
  wrong-board-blaming phys-socket diagnostics — now FATAL + pristine hint;
  same-board swaps legal); build-rig = pure wrapper (rig.yml scan deleted;
  empirical: `west build` without -b only WARNS, no gate existed);
  configure-log provenance (`Rig:` line at slot 10 + per-shield `<-`
  lines); 8 build-marked tests in test_cmake_alone_entry.py. Implementor
  agent + TWO mid-flight design amendments (mutual exclusivity replacing
  the mismatch check; SHIELD exclusion); joint driver+Tobi review.
- **`7f9fc47` vendor-prefixes** — btr-shields/dts/bindings/
  vendor-prefixes.txt registers `socket`/`plug` pseudo-vendors (zephyr/vnd
  precedent); unknown-vendor warnings gone (causality verified).
- **`03790fc` rig-gen rename** — generated outputs are
  `rig-gen.overlay`/`rig-gen.conf` (bare `overlay` gone; `rig.overlay`
  stays the hand-authored file); ALL stale cmake/rig.cmake comment refs
  retargeted to the dts fork incl. context.cmake header; justified
  refreeze (renames + header + provenance basenames ONLY, grep-proven).

**NEXT:** (1) E2 quail+frdm extensions, E3 lotus, E4 delete clones;
(2) edtlib CARRIED COMMITS **LANDED 2026-07-24c**: `c1c4d2acf2d`
(*-cells precedence BUG fix — upstream candidate #4, PR-able alone) +
`1a657124349` (vendor-namespaced binding keys; -cells suffix keeps its
specifier2cells meaning by design) on `tskr/zephyr-rigs`, signed-off,
branch ref updated ([ahead 2] of tiacsys — PUSH PENDING, Tobi's call);
CONNECTOR UNIFICATION also LANDED (`e425a19`): one file per type under
**dts/bindings/connectors/** (plural), plug contracts as **plug,***
keys — namespace rule (supersedes the rig,* choice): extension keys are
namespaced by the SIDE they describe (plug,*/socket,*), never by the
project; dts/connectors/ gone; standing test_connector_bindings.py
edtlib-validates all four files (the only coverage i2c-port.yaml ever
gets). WORKFLOW RULE from this slice: a SendMessage-resumed agent owns
the checkout until its NEXT report lands — driver edits wait
(design-log 2026-07-24d, memory feedback_resumed_agent_owns_tree);
(3) V1/V2 (+ per-instance parameters design round).
Parked: cmake fork re-idiomization; "board = trivial rig" endgame
(ontology §7).

---

## RESUME (2026-07-24) — fork-per-phase LANDED; workspace consolidated; NEXT = cmake-alone entry slice, then E2-E4, then V1

**Workspace RESTRUCTURED (Tobi): the zephyr-rigs worktree is GONE.** The
workspace `zephyr` checkout IS branch `tskr/zephyr-rigs` (the two
rig-enabling commits REBASED onto current upstream main: `df2c127228f`
cmake-modules + `76305e9aa49` shield template; also on remote `tiacsys`).
btr-shields/west.yml pins it; `.west/config` zephyr.base=zephyr. Gate is now
`ZEPHYR_BASE=/wrk/z/ws-up/zephyr PYTHON=/wrk/z/ws-up/.venv/bin/python3
btr-shields/scripts/check.sh`; agent contracts updated (`59ba775`). Tier-2
goldens refrozen for the rebase (`f734fa6`: provenance path comments +
upstream `7c32047f94c` st-pinctrl `ranges;`, net +5 lines). Remote pushes
now routine (origin=tobiaskaestner/btr-zephyr-shields, main tracks).

**Fork-per-phase cmake refactor LANDED (`016af37`, HEAD, tree CLEAN, gate
green 61 passed).** Brief (authoritative, incl. verified upstream
module-chain facts + slot numbering): `cmake-fork-refactor-brief.md`.
cmake/ is now: boards.cmake fork (real include + _rig_resolve_board_dts +
extension -isystem guard), shields.cmake = 28-line pure dispatch (rig
builds have NO shields phase), dts.cmake fork = the whole rig block in 9
steps (native pre_dt, called 2x — saferail-13 mirror DELETED; prepend
handoff — user extras WIN, cache-FORCE clobber bug dead; saferail 12
amended: app dir in pass-1 recipe, edt.pickle cross-check guards it).
rig.cmake DELETED. Implemented by sonnet implementor (contract inlined via
general-purpose agent), reviewed JOINTLY driver+Tobi (reviewer agent
deliberately skipped, Tobi's call). Upstream-issue candidate #3:
BOARD_EXTENSION_DIRS dead in dts.cmake:181/kconfig.cmake:96 (HWMv1 removal
c02c6add101).

**NEXT (order):**
1. **cmake-alone rig entry** — brief `cmake-alone-rig-entry-brief.md`
   (ratified): slot-10 rig→board inference via resolver (FULL
   `name@rev/variant` string, variant-proof), -DRIG EXCLUDES both
   -DBOARD and -DSHIELD (physical inputs are rig-owned; matching board
   also FATAL, marker survives reconfigures; SHIELD guard markerless in
   the shields fork; config inputs stay open), build-rig stripped to
   pure wrapper (passes NO board), double resolution collapsed.
   Principle: ontology.md §7 — **the board→rig lift** (board = trivial
   rig; grammar/resolver = board machinery lifted; identity-build +
   commutation laws; symmetry-table review heuristic). Design-log
   2026-07-24 has the ledger entry.
2. ~~E2 quail+frdm extensions~~ **E2 LANDED `0bf32b9`** (2026-07-24e:
   boards/extend/{mikroe/quail,nxp/frdm_k64f}, five rigs repointed,
   refreeze classification dts_equiv-verified old-vs-new, clones stay;
   GOTCHA for E3: a literal `*/` inside a DTS block comment corrupts the
   parse). **E3 LANDED `fd77560`** (2026-07-25b: cross-module extension
   of bridle's base, bridle NOT in manifest — lotus builds pass
   -DEXTRA_ZEPHYR_MODULES explicitly, harness threads per-case; all five
   clone-divergence checks clean; ACCEPTED-WITH-QUEUE: labels[-1]
   controller-label flip tcc0→grove_pwm_d19 — follow-up in
   implementation-plan "Controller-label determinism"). E4 (delete all
   four clones, goldens byte-untouched, pwm-nonzero-flags fixture
   repoint) DISPATCHED 2026-07-25; the de-provenance sweep follows E4
   as its own slice.
3. V1/V2 per `rig-variants-revisions.md` — V1's design round now ALSO
   settles **per-instance parameters** (§QUEUED in that file: grove_btn's
   type-level `zephyr,code` is wrong, both lotus-buttons buttons get
   INPUT_KEY_0; rig.overlay REJECTED as modeling answer; generalize
   `invert:`; lift model.py freeze). Plus the small rename: generated
   expander outputs `overlay`/`conf` → **`rig-gen.overlay`/`rig-gen.conf`**
   (`rig.overlay` is taken by the hand-authored file) + retarget
   cli.py's context.cmake header comment (still says rig.cmake) — driver
   task, carries a justified tier-1 refreeze if header text is frozen.
4. Small driver tasks queued behind the cmake-alone slice:
   `dts/bindings/vendor-prefixes.txt` (register `socket`/`plug`
   pseudo-vendors — kills the unknown-vendor warnings), and the
   rig-gen rename from item 3.
5. **edtlib namespaced-extension-keys carried commit + connector
   unification (RATIFIED 2026-07-24b, saferail 10 AMENDED)** — see the
   implementation-plan bullet + design-log 2026-07-24b: driver-scope
   zephyr-branch commit (ok_top permits comma-namespaced keys →
   Binding.raw), then plug contracts merge into socket bindings and
   `dts/connectors/` dissolves. Namespace choice rides the naming sweep.
6. Parked new: cmake fork re-idiomization for upstream (parked.md §Build
   integration — `_rig_*` prefix is NOT zephyr idiom; function-wrap at
   patch-drafting time).

---

## RESUME (2026-07-23b, session pause) — Bridge-A COMPLETE; E1 board-extension LANDED; NEXT = fork-per-phase cmake refactor (decision B), then E2-E4, then V1

**Since the morning block below (all committed, HEAD `1654ec4`, tree CLEAN):**
loose ends closed (`63f59c7` flags→analyzer diagnostic + analyzer off mypy
exemptions [only frozen model remains]; `9af9fb3` shield-name collision →
rig-template-marker preference; `c33dece` normalize-on-freeze), and **E1
landed (`4db27bc`)**: nucleo_f401re rig-variant as an hwmv2 BOARD EXTENSION
(`boards/extend/st/nucleo_f401re/`, target `nucleo_f401re/stm32f401xe/rig`),
five nucleo rigs migrated, clone kept until E4. Design:
`board-extension-migration.md`. MECHANISM GAP found (upstream-issue
candidate #2): hwmv2 extensions can't cross-dir #include their base
(pre_dt only adds DTS_ROOT subpaths; both canonical examples avoid it) —
bridged data-driven in the shields fork (`_rig_resolve_board_dts` +
BOARD_DIRECTORIES `-isystem` guard; a per-board path table and a
freestanding cmake helper file were both REJECTED by Tobi — see the
implementor contract's cmake rules + memory `cmake-dir-conventions`).

**DECISION B (joint analysis, ratified): fork-per-phase cmake refactor,
run BEFORE V1/V2.** Every file in cmake/ overloads its upstream namesake
and owns its phase's rig logic: NEW boards.cmake fork (board-dts helper +
extension -isystem guard move there), shields.cmake fork keeps ONLY the
shield Kconfig tail, NEW dts.cmake fork (include pre_dt natively — the
saferail-13 pre_dt MIRROR in rig.cmake DISSOLVES — run the expander, set
overlay/conf lists, provenance, then delegate to real dts.cmake).
rig.cmake's 675 lines redistribute; each fork's content doubles as the
draft upstream patch. V1/V2's per-variant/rev file collection then lands
in the dts fork.

**Sequencing NEXT session:** (1) fork-per-phase refactor (B); (2) E2
quail+frdm extensions, E3 lotus (base in BRIDLE — the include-path guard
already handles it; keep --board-dts explicit, boarddt standalone
discovery has a documented cross-module limitation), E4 delete the four
clones; (3) V1 revisions + shield revisions, V2 variants
(`rig-variants-revisions.md`, settled); (4) post-E4: test-suite
de-provenance sweep (goldens outlive Bridge-A as the expander's contract;
strip the saferail/flip archaeology from docstrings, sort tests by
upstream destination, rename s1/s5-style folders — recorded in
implementation-plan.md).

**Repo remote:** `origin = git@github.com:tobiaskaestner/btr-zephyr-shields.git`
added — NOT pushed yet (Tobi's call). Upstream-issue drafts:
`upstream-buildinfo-issue.md` (build_info list truncation, ready to file);
the extension include-gap needs drafting.

---

**State.** The Bridge-A deconstruction / edtlib rewrite is **DONE, all steps
+ THE FLIP**: the production expander reads the REAL board DT via edtlib
(`edt_build.py` BSD-3 reader + `board_edt.py` Apache projection),
`scripts/rigexp/common-dts/` is deleted in full, and rig.cmake computes the
pass-1 recipe (pre_dt.cmake mirror; amended saferail 13) + records rig
provenance into build_info.yml (`cmake.vendor-specific.rig.*`). Also landed:
cmake debuggability (`-DCMAKE_MESSAGE_LOG_LEVEL=VERBOSE` prints
copy-pasteable python invocations; `<build>/rig/rerun-expand.sh` always
written, survives failed configures) and the RIG_DEPENDS depfile handoff
(editing .shield / plug YAML retriggers configure). Work in
**`/wrk/z/ws-up/btr-shields/`**, HEAD **`cf867ce`**, tree CLEAN. Session
commit trail: `a35e15a` (commit gate + agents) `bf515c3` (goldens frozen)
`8ef98e3` (phase-1 dual-read) `f99ec63` (frdm/quail scaffold fix — the
shadow caught 5 WRONG pins) `b126017` (2a real pwm/adc nexuses) `89568d4`
(2b socket-relative emission + latent pwm cell-count bug fixed) `21ff9ec`
(step-3 relocation) `854712e` (THE FLIP) `dd35c9e` (step-4 dtsio) `05b2395`
(loader_dts retired) `cf867ce` (cmake debug + deps). Upstream zephyr-rigs
still pristine except the two known rig-enabling commits.

**Workflow (established this session, KEEP USING IT).** Every change runs
implementor→reviewer→gate→commit: `.claude/agents/rig-implementor.md`
(sonnet) implements one scoped task, leaves changes uncommitted;
`.claude/agents/rig-reviewer.md` (opus, read-only) independently re-runs
gates and verdicts ACCEPTED/CHANGES-REQUIRED; driver applies minors and
commits. (This session they were inlined via general-purpose agents — the
named types register from `.claude/agents/` at session start, so NEXT
session can dispatch them directly.) Commit gate:
`ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs PYTHON=/wrk/z/ws-up/.venv/bin/python3
btr-shields/scripts/check.sh` (mypy + pytest; `CHECK_FAST=1` skips
build-marked tests — post-flip that includes tier-1 goldens, which need a
cached plain-board build for the recipe). mypy exemption list
(pyproject.toml) is down to `analyzer` + `model` (frozen); RULE: it only
ever shrinks — migrating a module drops it in the same commit.

**Tests** live in `scripts/rigexp/tests/` (NEVER a top-level `tests/` —
reserved for twister apps, Tobi rule). Two-tier goldens (13-rig corpus + 3
synthetic rejects unknown-board / not-rig-enabled / route-no-via):
tier 1 = expander outputs byte-frozen (normalized), tier 2 = pass-2
zephyr.dts via dts_equiv (THE invariant) + semantic pin (edt.pickle
resolved pwm/adc) + build_info provenance + RIG_DEPENDS assertions.
Refreeze: `RIGEXP_REFREEZE=1` — always inspect the diff; every refreeze
needs justification in the commit. `test_board_read.py` = plain builds
(saferail 11) + edt.pickle cross-check (recipe equivalence, saferail 3).
`expectations.yml` is emitted but NEVER gated (parked →
`claude/hw-expectations/`).

**Expander CLI grew** (the flip): `--board-dts`, `--include-dir`/
`--bindings-dir` (repeatable), `--build-info <yml>` (standalone
convenience — the harness uses cached plain-build build_info.yml).
rig.cmake passes the explicit form. Board name→dts discovery via zephyr's
list_boards.py (standalone fallback); two board diagnostics: phys-board
not-found (+known list) and exists-but-not-rig-enabled.

**NEXT — dispatch slice V1: rig revisions + shield revisions (delta
engine).** Design SETTLED 2026-07-23 after five pushback rounds —
**`rig-variants-revisions.md`** (the settled-shape paragraph up top) +
slices V1/V2 in `implementation-plan.md`. Ratified: hwmv2-exact grammar
(`--rig name@rev/variant`, `shield: name@rev`); variant = named axis = a
general DELTA (board and/or sockets and/or instance/shield substitutions —
NOT board-tied); ONE family-wide revision stream, applied after the
variant; fragments named by `_`-joined DECLARED axes (filenames never
parsed; variant name ≠ revision id validation); shield revisions
first-class via DT-overlay fragments (`<name>_<rev>.shield`) — the
migration answer to `x_nucleo_iks01a1/2/3`-style folder copying; minimal
merge vocabulary (shallow, instance-name-keyed, explicit add/remove, wires
by endpoint pair, errors never silent no-ops); default variant allowed.
Everything resolves in the LOADER — analyzer/emitter untouched. V1 golden
budget is in the brief (Q8): 4 accept tuples both tiers + 4 synthetic
rejects + zero-churn shield-rev pilot.

**Follow-ups (recorded, lower priority).** Shield name-collision across
board roots (last-wins resolves zephyr-rigs' stock adafruit_data_logger
over ours — prioritize rig-owning root or warn; reviewer rated worth
prioritizing). Analyzer migration bundle (cs-pool merge simplification —
now redundant post-flip; emitter's nonzero-pwm-flags ValueError → proper
analyzer diagnostic; mypy off the list). normalize-on-freeze (tier-2
goldens embed pytest tmp paths in provenance comments — cosmetic refreeze
churn). Upstream report candidate: zephyr build_info() vendor-specific
path truncates un-joined lists (worked around by list(JOIN)). Parked
upstream items unchanged (twister-as-platform, guarded legacy-compat,
naming sweep — parked.md).

**Gotchas learned this session.** edtlib REJECTS custom binding keys
(ok_top edtlib.py:450) — rig-extension data must never live under a
dts/bindings root (hence dts/connectors/). build_info.yml does NOT exist
at expand time (dts.cmake writes it AFTER rig.cmake) and include(pre_dt)
at shields time is unsafe (ARCH_V2_NAME_LIST unset + include_guard
poisoning) — rig.cmake mirrors pre_dt, edt.pickle cross-check guards
equivalence. sam0 pwm is 2-cell (channel,period — NO flags): the emitter's
old 3-cell form was a latent day-one bug, caught only when the vnd,* test
compatibles got typed bindings (untyped props are INERT in edtlib — no
resolution, no validation, no macros). board_edt `_controller_label` uses
labels[-1] (board alias wins) — order-fragile, overlay-affecting, guarded
only by tier-1 text now; read its docstring before touching. Shell-env
quoting: `NAME='value'`, never `'NAME=value'`. Goldens: config-sheet
renders from the board MODEL (scaffold-era bug surface), zephyr.dts from
the real DT — they can disagree; the flip ended that split.

---

Everything below is the pre-rewrite record (2026-07-22 and earlier).

---

## RESUME (2026-07-22) — P3 DONE + boards cleaned; Bridge-A rewrite DESIGNED + spike-validated; NEXT = start the rewrite (freeze goldens first)

**State.** P0–P2 done; rig build machinery in place; **all downstream P3 slices
(3a allocation, 3b interposers, 3c multi-function/pinctrl) complete + committed**;
mechanics de-hardcode audit + `west rigs` + rig-name/app-path fixes done; **all
four board clones cleaned** (connectors described once, via the typed sockets);
and **the Bridge-A deconstruction / edtlib rewrite is fully DESIGNED, both spikes
(nucleo read-side, lotus 2a) VALIDATED, and the 18 saferails agreed** — the
implementation has NOT started. Work is in **`/wrk/z/ws-up/btr-shields/`** (git;
HEAD **`b02bdc7`**, working tree CLEAN — the spikes reverted their experimental
changes by design). Commit trail: 3a-and-earlier `79a719d`→`ffd0cb1`; mechanics
hardening `0a4b36d`→`5e2a92c`; 3b `ae4f62b` `0158260`; 3c `afe5857` `a980947`
`a555120`; board cleanup `a46cec9` (lotus) `b02bdc7` (nucleo/quail/frdm).
Upstream `zephyr`/`zephyr-rigs` stay pristine EXCEPT two deliberate rig-enabling
commits on **zephyr-rigs**: `904e8fe7e63` (module.yml `cmake-modules` key) +
`96de1e63074` (shield.yml `template` field).

**Front door / build.** (run from `west topdir` = `/wrk/z/ws-up`)
```
/wrk/z/ws-up/.venv/bin/west build-rig --rig <name> <app>   # full compile
   [--cmake-only] [-d <dir>] [-p always] [-- -D…]           # extra opts pass through
   # e.g. …build-rig --rig nucleo-datalogger zephyr/samples/hello_world
   #   (--rig takes the rig.yml `rig.name`, NOT the folder basename `s1`)
```
`build-rig` (subclass of zephyr's `build`, `scripts/west_commands/rig.py`) infers
the board from the rig and runs the seam. It resolves the zephyr tree via
`--zephyr-base` > west config `zephyr.base` (= zephyr-rigs here) > discovery, and
sets `ZEPHYR_BASE` explicitly (ignoring the profile's ambient `$ZEPHYR_BASE` =
plain `zephyr`). The app source dir is REQUIRED (positional or `-s`) — no default
app; omitting it is a hard error. West manifest = btr-shields.

**How the machinery fits (all under `btr-shields/`):**
- `zephyr/module.yml`: `board_root`/`dts_root: .` + `cmake-modules: cmake`.
- `cmake/shields.cmake` FORKS zephyr's `shields` (via the cmake-modules PATH
  prepend): `-DRIG` builds → `cmake/rig.cmake`; else → the original shields.cmake.
- `cmake/rig.cmake`: HEAD expands the rig (`python -m rigexp expand` →
  EXTRA_DTC_OVERLAY_FILE; reads back `context.cmake` = RIG_NAME/BOARD/SHIELDS);
  TAIL drives shield Kconfig over RIG_SHIELDS (sets SHIELD_AS_LIST, collects each
  shield's `.conf`, DROPS `.overlay` — expander owns DT); appends the rig's
  `rig.conf` to OVERLAY_CONFIG. `-DRIG` resolves via `scripts/list_rigs.py`.
- Shields = folders `boards/shields/<name>/{<name>.shield, shield.yml
  (template:true), Kconfig.shield (+defconfig)}` — discovered by list_shields.py.
- Rigs = folders `boards/rigs/<name>/{rig.yml, rig.conf}` — discovered by
  `scripts/list_rigs.py` (mirrors list_shields.py).
- Expander `scripts/rigexp/` (+ Bridge-A board models in
  `scripts/rigexp/common-dts/boards/`); R2 checker `scripts/dts_equiv.py`.

**3a verified.** s1 / s5-temp-farm / s4b-sockets full-compile & link with the
shield DRIVERS built (rtc_pcf8523, sdhc_spi, spi_nor, hts221); s2-wifi-logger +
s4b-dup-addr reject at configure (phys-net / phys-addr); legacy `--shield` path
unaffected. s2-wifi-logger-ok: winc1500 driver compiles but a full LINK needs
app-level net config (entropy/IPv4) — deferred.

**3b DONE (2026-07-22).** `frdm_k64f_btr` clone; shields `arduino_uno_click`
(carrier), `eth_click`, `i2c_mux` (ti,tca9548a), `i2c_sensor`. Rigs: `frdm-eth-nest`
(S6 accept, full link), `frdm-cs-clash` (S6 reject phys-cs), `nucleo-mux-farm`
(S8 accept, full link), `nucleo-mux-clash` (S8 reject phys-addr). Required an
emitter fix (`ae4f62b`): synthesized carrier nexuses now carry gpio-map-mask/
pass-thru (real edtlib rejected the flags mismatch — first nested-carrier rig).

**3c DONE (2026-07-22).** `seeeduino_lotus_btr` clone (from bridle); connector
binding `grove.yaml` + index header; shields `grove_servo`/`grove_light`/
`grove_btn`/`grove_led`. **Board cleanup (`a46cec9` lotus, `b02bdc7`
nucleo/frdm/quail):** ALL clones now describe each connector ONCE, via the typed
`socket,*` nodes — the legacy per-connector nexus nodes (bridle grove/arduino,
st_morpho, mikrobus_N_header, edge_header + the mikrobus_*/skd stubs) were
dropped as unreferenced duplication. Load-bearing bus config (status/pinctrl,
frdm's onboard fxos8700, quail's SPI3 flash) was KEPT. Typed sockets point at
the real controllers directly, so no legacy alias is needed. Rigs:
`lotus-pwm` (accept, full link), `lotus-pwm-clash` (reject phys-channel),
`lotus-buttons` (accept, full link). Required TWO mechanics changes: emitter
`_collection_entry` now carries collected devices' passthrough props (`afe5857`,
so `zephyr,code` reaches the gpio-keys overlay), and rig.cmake now appends a
rig-authored **`rig.overlay`** to EXTRA_DTC_OVERLAY_FILE (`a980947`) — the DT
counterpart of rig.conf — so `lotus-pwm/rig.overlay` supplies the real
PA14/TCC0-WO4 pinmux the expander can't author (R21 deep half). GOTCHA learned:
never put a `*-map`-named prop (socket,pwm-map/adc-map) on a REAL board node —
edtlib treats any `*-map` as a nexus needing `#<name>-cells`; the emitter emits
fully-resolved `pwms`/`io-channels` to `&tcc0`/`&adc0` directly instead.

**NEXT — pick up here: the Bridge-A deconstruction / edtlib rewrite.** It is
fully DESIGNED, both spikes VALIDATED, and the 18 saferails agreed — the full
spec + saferails are in `implementation-plan.md` (the "Bridge-A deconstruction /
edtlib rewrite" block in the hardening section). Retires `scripts/rigexp/
common-dts/{boards,bindings}`; pass 1 reads the REAL board DT + bindings via
`edtlib.EDT`. Phases (each validated against the corpus): (1) `boarddt`→edtlib EDT
of the real board [nucleo spike ✓, cross-checked vs pass-2 `edt.pickle`]; (2)
PWM/ADC as standard `pwm-map`/`io-channel-map` nexuses on the real socket [lotus
spike ✓; validated nexus diff + the edtlib EDT-construction recipe/compare scripts
preserved in `claude/rigs/spikes/` (lotus2a-*, nucleo-*)] — COUPLED to
(3) because the connector binding must DECLARE those nexus props; (3) connector-
type extensions → `dts/bindings/connector/X.yaml`, read via `edtlib.Binding.raw`;
(4) drop `dtsio` hand-rolled cpp/dtlib per P0.

**START WITH: freeze the goldens** (saferail #1) — a small harness that runs every
3a/3b/3c rig and captures overlay + verdict + diagnostics as committed fixtures
(follow the `tests/test_edtlib.py` pytest template; that's also the seed for the
rigexp unit-tests + twister). Safe, self-contained, touches no expander code.
Then work the phases per the saferails: per-board (nucleo→quail→frdm→lotus),
per-phase, SHADOW dual-read (common-dts vs edtlib, assert-equal) before flipping,
`model.py` frozen, consume-edtlib-zero-patch, and the upstreaming rules (minimal
footprint, edtlib idioms + mypy, BSD-3 reader / Apache product split).

**Also remaining (lower priority):** upstream integration (parked twister-as-
platform; `rig-`/`.rig.` naming sweep + landing sequence in `parked.md`; the
**guarded legacy-compat layer** — `#ifndef RIG_BUILD` compat .dtsi, design in
`implementation-plan.md` Parked; its auto-synthesis variant rides on rewrite
step 1); and the deferred items just below.

PARKED (moved OUT of the downstream P3 push, 2026-07-22): **twister harness.**
Making twister run the corpus means teaching `testcase.yaml` to accept a RIG as
a platform — that lives in Zephyr's twister/platform layer, so it is NOT
solvable downstream. Park it against the **upstream-integration** milestone
(do it just before/after upstream landing). Until then the regression net is
`frontend-trial/scripts/run_trials.py` (accept/reject oracle) + per-rig
`west build-rig` accept/reject checks. See `implementation-plan.md` Test/CI.
Deferred (tracked in memory + `implementation-plan.md`): LED-merge aggregation
(via `.cmake` post-`dts` inheritance), s2 networking, **Kconfig.rig** (rig folders
are ready for it), and rigexp Python review & unit tests. The **de-hardcode /
assumption audit is DONE (2026-07-22)** — see the "Since 3a" note below.

**Since 3a (2026-07-22) — mechanics hardening (committed).**
- `west build-rig <rig> <app>`: app source dir is now REQUIRED (no scenario-1
  default; positional or `-s`), and `--rig` resolves by the rig.yml `rig.name`
  (not the folder basename), matching board/shield convention.
- New `west rigs` command (lists rigs; `-f`/`-n`/`--board-root`, like `west shields`).
- **De-hardcode audit complete**: `RIG_EXPAND_PYTHON`→`PYTHON_EXECUTABLE`;
  `RIG_EXPAND_SHIELD_DIR` gone → shields discovered from every `BOARD_ROOT`'s
  `boards/shields`; `dtsio.py`/`dts_equiv.py` dtlib paths ← `$ZEPHYR_BASE`;
  `rig.py` self-locates (`parents[2]`); zephyr tree ← `--zephyr-base` > west
  config `zephyr.base` > discovery (no `zephyr-rigs` literal, ambient
  `$ZEPHYR_BASE` ignored). No `/wrk` literals left in mechanics code.
- **NOT done (deliberately deferred to the edtlib rewrite / P0):** the expander
  still reads board models + connector bindings from its bundled
  `scripts/rigexp/common-dts/{boards,bindings}` (Bridge-A). Retire that by
  building on `edtlib.EDT` (reads real board DT/bindings from the board_root) —
  bundle with the rigexp code-review + unit-test item, after/with 3b/3c. NOTE:
  the "unused" bundled board models (`frdm_k64f`, `seeeduino_lotus`, `cytron_*`)
  are pre-staged content for 3b/3c — do not delete.

**Gotchas.** Build against zephyr-rigs — `build-rig` resolves it from west config
`zephyr.base` (override with `--zephyr-base`); it ignores the profile's ambient
`$ZEPHYR_BASE` (= plain `zephyr`, the wrong tree). Rebuild goldens fresh before an
R2 diff (a stale golden once gave a spurious 124-vs-129). The shield-discovery
glob must be `<dir>/<basename>.shield` (Kconfig.shield also ends in ".shield").
**Shield identity** = shield.yml `name:`; **rig identity** = rig.yml `rig.name:`
(both may differ from the folder basename — e.g. rig folder `s1` → name
`nucleo-datalogger`). Naming: shields underscored (adafruit_data_logger, etc.).

**Docs.** `implementation-plan.md` (phases + the post-slice hardening block);
`P3-brief.md` (3a detail — NOTE its Kconfig section is superseded by the
shield-folder model, see memory); `P2-brief.md` / `P2-S1-equivalence.md` (P2
record). Full running detail in the auto-memory `project_zephyr_rigs.md`.

---

Everything below is the earlier P2 / P3-staging record.

---

## RESUME (2026-07-21b) — P2 in flight

P2 hand-off brief written: **`P2-brief.md`** (the authoritative build sheet for
the S1 walking skeleton — read it first for P2). Downstream tree decided:
**`/wrk/z/ws-up/btr-shields/`** (named to avoid the "rigs" clash), board cloned
under new id `nucleo_f401re_btr`, `.shield` + rig files owned in-tree, our own
app at `btr-shields/app/s1-app`, cache-var delivery (BOARD_ROOT/DTS_ROOT), no
bridle edits (per-app `ZephyrAppConfiguration` seam), builds against
`zephyr-rigs` (`export ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs`). O1–O5 resolved in
the brief.

Tasks **T1** (rigexp `expand` CLI), **T2** (clone board/shield/bindings +
s1.rig.yml), **T3** (ZephyrApp cmake seam) ran as parallel sonnet sub-agents —
**all three PASS**. Gate cleared with two decisions:
- **Bridge-A** (board-model seam): the prototype expander learns board sockets
  from `rigexp/common-dts/boards/<board>.rig.dtsi`, which was missing/misnamed
  for the clone. Added `nucleo_f401re_btr.rig.dtsi` mirroring T2's real socket
  node (full 22 positions, `nucleo_ard`, i2c1/spi1, stackable). **Temporary
  duplication** (real board DT + expander model) — retire when the edtlib real
  expander reads the actual board DT (P0 direction). Real `s1.rig.yml` now
  expands byte-identical to the trial oracle (modulo board name).
- **CLI hardening**: `rigexp/cli.py` now abspaths rig/shield-dir/out-dir — a
  relative `--shield-dir` produced an unresolvable `#include` from the temp
  workdir; the cmake seam runs from the build dir, so this would have bitten T5.

Build tasks **T4/T5/T6** ran (one sonnet sub-agent). **P2 walking-skeleton
milestone MET:** legacy path 134/134 nodes match (regression net solid); rig
spike builds through the seam; **S1 R2 equivalence met** — 129 nodes identical,
3 justified divergences (typed-socket reference targets with *identical pins*;
Conv. 8 rtc alias out of scope), one **deferred** gap (shield LEDs land in
`/gpio_leds` vs board `/leds` — P3 aggregation slice, deferred with Tobi's OK).
Emitter gained `status="okay"` + auto `sdmmc-disk` child (closed the 2 enumerated
S1 gaps). Result recorded in **`P2-S1-equivalence.md`**.

**Layout restructured to upstream conventions** (Tobi): `btr-shields/` now has
`boards/shields/`, `boards/rigs/`, `scripts/rigexp/` (+ `scripts/dts_equiv.py`),
`samples/rigs/scenario-1/` (the app + `ZephyrAppConfig.cmake`). Seam + CLI
re-verified green after the move; upstream `zephyr-rigs` pristine.

**btr-shields promoted to a PROPER Zephyr module + `west rig` UI** (Tobi):
`zephyr/module.yml` (`board_root`/`dts_root: .`) + `cmake/rig_expand.cmake`
(seam logic extracted into a self-locating `rig_expand()`; AppConfig just puts
`cmake/` on `CMAKE_MODULE_PATH` and calls it). Registered via a west
**submanifest project** `zephyr/submanifests/btr-shields.yaml` — that one entry
both (a) auto-discovers btr-shields as a Zephyr module (board_root → no
`-DBOARD_ROOT`/`-DDTS_ROOT`, no `EXTRA_ZEPHYR_MODULES`) and (b) registers the
`west rig` extension (west loads west-commands from the working tree). The whole
invocation is now just:
```
west rig s1              # infers board, forces ZEPHYR_BASE=zephyr-rigs, runs the seam
```
(`--cmake-only`/`-p`/`-d`/`--app`/`--zephyr-base` supported; extra `-D…` pass through.)
Verified: board inferred, module auto-discovered, built vs zephyr-rigs, 129-node
equivalence unchanged, `zephyr-rigs` pristine.

UPDATE: Tobi made btr-shields a **manifest repo** (`btr-shields/west.yml` imports
zephyr + `self.west-commands`; `.west/config` manifest.path=btr-shields) — so the
zephyr submanifest hack was reverted (zephyr checkout clean again).

Front door is now **`west build-rig --rig s1`** — a subclass of zephyr's `Build`
(full build UX + `--rig`), forcing `ZEPHYR_BASE=zephyr-rigs`. The monkey-patch of
`west build` (venv `.pth`) was tried and REVERTED (too fragile/global).

**zephyr-rigs commit `904e8fe7e63`**: `module.yml` gains `build: cmake-modules:
<dir>` → prepends `<dir>` to CMAKE_MODULE_PATH + auto-includes `<dir>/default.cmake`
(before boards/dts/kconfig/soc). btr-shields wires `cmake-modules: cmake`.
**DONE: the seam now lives in `btr-shields/cmake/default.cmake`** (auto-included,
module-global, `if(DEFINED RIG) rig_expand(RIG)`), and **`ZephyrAppConfig.cmake`
is RETIRED**. Verified: build-rig works via default.cmake, equivalence 129, plain
builds (no --rig) are a clean no-op. rig_expand() still in `cmake/rig_expand.cmake`.
GOTCHA: `zephyr.base` config doesn't stick (manifest `zephyr` project → path
`zephyr`); explicit ZEPHYR_BASE env wins. Rebuild goldens fresh on zephyr-rigs
before diffing (stale golden once gave a spurious 124-vs-129).

CAUTION LEARNED: never store durable artifacts inside a `west build -d` dir —
`-p always` wipes them (lost the first equivalence normaliser/writeup that way;
now in the source tree). Build dirs used: `build-rig/proposal/{S1,
S1-legacy-upstream,S1-legacy-clone}`.

**Next: P3** — slice 3a (allocation + Kconfig manifest) per `implementation-plan.md`;
the LED-merge aggregation gap rides along in 3a.

## RESUME (2026-07-21) — prototype done, entering implementation

Prototype phase COMPLETE (S1–S8 + bridle port + PWM/ADC; 20 rigs green in
`frontend-trial/scripts/`, `python3 run_trials.py [--rig NAME]`). Real-impl
plan written: **`implementation-plan.md`** — read it first. Additive-first;
a driver agent delegates phases to sub-agents (**run sub-agents on sonnet**),
human review between phases; P0∥P1 parallel.

- **P0 (reuse-boundary, dtlib/edtlib) — DONE**, outcome recorded in
  `implementation-plan.md` §P0: build the real expander on `edtlib.EDT`,
  consume-don't-patch, keep model/analyzer/emitter new.
- **P1 (integration seam) — DONE**, outcome recorded in `implementation-plan.md`
  §P1: **downstream module, zero upstream edits**; bridle's
  `ZephyrBuildConfiguration` hook runs an early cmake module before `dts` →
  `execute_process(expander)` → `set(EXTRA_DTC_OVERLAY_FILE …)`. Prereq: add a
  `python -m rigexp expand` CLI.

Both P0 and P1 are complete (ran on the default model this session). The fresh
session goes straight to **P2 — the S1 walking skeleton + the P1 spike**
(build a sample with `-DRIG=s1`, confirm the overlay is ingested and the shield
nodes land in `zephyr.dts`). **Run all future sub-agents on sonnet** (Agent
tool `model: sonnet`) per the plan's execution model.

---

Older pick-up notes (design/pushback phase) below; superseded by the plan.

## Where we are

Design is settled through three pushback rounds. The rig model: rigs are a
**third build-system entity** (self-contained, `west build --rig <name>`, no
`-b`); connector types are **bindings + dt-bindings index header** (no type
devicetree); shields are DT-shaped templates with a local **plug node**, bus
membership by parentage, and the **address authority rule** (shield declares
domains via `shield,addr-from`/`shield,domain`; rig file owns selections;
expander is sole author of `reg`+unit-address pairs). Boards opt in with
typed socket nodes **in their own DT** (real phandles, legacy labels for
migration — no shim; legacy `-b`/`--shield` path must never break). Front-end
verdict candidate #1 (pure DTS) vs #2 (rig.yml hybrid) is **deliberately
open** — decided by loader error-quality comparison in the prototype.

## Artifact map (all under /wrk/z/ws-up/claude/rigs/)

| File | What |
|---|---|
| `design-log.md` | decision ledger incl. all pushback rounds — the "why" record |
| `requirements.md` | R1–R27 consolidated into 6 concepts; compatibility scope |
| `ontology.md` | nouns + relations + projection principle + bus stress test (A1–A6) |
| `architecture.md` | **toolchain terms** — loader / rig model / expander (analyzer+emitter), Zephyr seam |
| `implementation-plan.md` | **real-impl plan** — phases P0∥P1 → P2 → P3; prototype phase is DONE |
| `conventions.md` | **v4 front-end spec** — read after this file |
| `rig-dt-syntax.md` | syntax reference — all 4 layers (rig.yml / shield,* / socket,* / bindings) |
| `frontend-trial/FIDELITY.md` | S1 R2 equivalence result (overlay-level) |
| `rig-playbook.md` | scenarios S1–S8 with verified baselines |
| `parked.md` | consciously postponed work (CAN pass, Kconfig, multi-board…) |
| `frontend-trial/` | normative example files, both candidates + `EVALUATION.md` |
| `diagrams/` | graphviz sources+SVGs; atlas artifact: https://claude.ai/code/artifact/9dc7b621-f012-4703-b340-6729815d7595 |
| `/wrk/z/ws-up/build-rig/upstream/S*` | verified cmake-only baselines (S1–S6) |

Zephyr worktree: `/wrk/z/ws-up/zephyr-rigs` (branch zephyr-rigs @ origin/main,
clean). Workspace west modules were synced by Tobi (full module set builds).

## Immediate next steps (agreed order)

1. ~~**`s3-stacked-loggers` trial piece**~~ **DONE 2026-07-19** — authored in
   both candidates, smoke-tested (CPP + dtlib clean, phandles resolve, YAML
   parses); expansion contract (accepts E1/E2/W1 table) recorded in
   `frontend-trial/EVALUATION.md` §"S3 seeded-error showcase". Superseded v1
   `common-dts/rig-types/` + `templates/` removed.
2. ~~**Expander prototype**~~ **DONE 2026-07-19** — `frontend-trial/scripts/`
   (rigexp package + run_trials.py; 6 seeded mistakes). **Front-end verdict:
   candidate #2 (rig.yml)** — recorded with evidence in EVALUATION.md,
   decisive finding: stock dtlib's free reference errors carry no file:line
   for cell-value refs; the hand-built YAML resolver beats them.
   **Ratification by Tobi pending**, then rewrite conventions.md around
   rig.yml. Flagged stopgap: device gpio roles are name-inferred (R23
   authoring gap; solve with the drive-type refinement).
3. ~~**Conventions rewrite around rig.yml**~~ **DONE 2026-07-20** — verdict
   ratified; conventions.md now v4 (rig.yml is THE front-end, candidate #1
   retired to git history; Conv. 8 folded in; two source artifacts +
   per-shield-TU as Ground rule 3). S7 gained
   `candidate-2-hybrid/s7-sqw-counter.rig.overlay` (Conv. 8 alias example,
   label-consistency verified). Ground rule 3 (per-shield translation units)
   **implemented 2026-07-21** — the candidate-2 loader parses each `.shield`
   as its own TU, so labels are shield-scoped (grove-led and grove-light both
   use `gl_plug`, no collision); prefix discipline no longer required.
4. **S1 fidelity milestone**: port = data-logger shield already exists in the
   trial; write the S1 rig, expand, build with the generated overlay into
   `build-rig/proposal/S1`, diff `zephyr.dts` against
   `build-rig/upstream/S1` (R2 — equivalence, not byte-identity: labels may
   differ).
5. ~~S5 allocation against the golden sketch~~ — effectively verified by the
   prototype (byte-level golden match + R18/R7 order-independence, see
   EVALUATION.md); revisit only if the S1 build path changes the emitter.

## Smoke-test command (re-verify trial after any edit)

```sh
cd /wrk/z/ws-up/claude/rigs/frontend-trial
gcc -E -x assembler-with-cpp -nostdinc -I /wrk/z/ws-up/zephyr-rigs/include \
  -I common-dts/include -undef -D__DTS__ candidate-1-dts/<file>.rig.dts -o /tmp/x.pre.dts
# then: dtlib.DT("/tmp/x.pre.dts") using
# /wrk/z/ws-up/zephyr-rigs/scripts/dts/python-devicetree/src
```

Gotchas learned: top-level `/name/ {}` is invalid DTS (nest under `/ {}`);
dtlib lowercases unit-addresses; zsh does not word-split unquoted `$FLAGS`.

## Open questions parked, not forgotten

See `parked.md`. The two most likely to bite during the prototype: Kconfig
handling for instantiated shields, and the aliases/`chosen` naming policy
(R10) — both fine to stub with TODOs.
