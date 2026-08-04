# Rigs — Parked Work

Single parking lot for consciously postponed topics. Each entry: what, why
parked, where the context lives. Newest first within sections.

## Scenario passes (extend the playbook)

- **CAN rig scenario** *(parked 2026-07-17)* — richest single follow-up: would
  concretize ontology amendments A1–A6 in one rig (termination jumpers →
  bus-level constraints + config sheet; bitrate → bus-wide parameter
  agreement; transceiver → in-path device; differential pair → grouped nets).
  Context: `ontology.md` §4-CAN. In-tree starting point: `canis_canpico`
  shield, `can-transceiver` bindings.
- **Kconfig layering** *(settled 2026-07-21; implementation parked)* — the
  layering is decided: (1) **type-level** Kconfig + defconfig from both shield
  templates and rigs (rigs are board-like build entities); (2) **no
  per-instance Kconfig** — symbols are global, so per-device config lives in
  DT and driver auto-enable follows the generated overlay via
  `dt_compat_enabled`/`dt_nodelabel_enabled`; (3) the emitter's **fourth
  output** is a per-rig **Kconfig fragment / activation manifest** (which
  shield types + board are instantiated, so their type-level defconfig apply —
  the rig.yml replaces the `--shield` CLI — plus rig defaults); (4) the app
  `prj.conf` composes on top and overrides. Still open: exact file format of
  the manifest and how the build merges it (ties to "where the expander runs"
  below), and any genuinely multiplicity-derived symbol (rare; usually
  DT-derived via `DT_NUM_INST`). Context: `architecture.md` (emitter),
  conventions.md Conv. 7, `requirements.md` open question 1.
- **Multi-board rigs** — inter-board links; one DT projection per firmware
  image (incl. multi-image boards like nRF5340). Context: `ontology.md`
  PCBA/refinement 5, `requirements.md` open question 6.

## Model extensions

- **Auto-routing of free non-CS positions** *(scoped out 2026-07-20)* — the
  routing jumper (R6) landed for the *pinned* case: a non-CS routing jumper
  must be explicitly selected by the rig. Letting the allocator auto-pick a
  free non-CS position (as it does for the fungible CS pool) was deliberately
  excluded as too aggressive/surprising; revisit if a scenario wants it.
  Context: conventions.md Conv. 2 "Position selection", `SCENARIOS.md` §S2.

- **Power/ground modeling** — voltage domains (3V3/5V/IOREF), current budgets
  as realizability inputs. Nets exist in the model; checks deferred.
  Context: `ontology.md` §5.
- **Differential signaling details** — beyond amendment A1's grouped nets:
  impedance, pair-matching constraints. Context: `ontology.md` §4/A1.
- **Mechanical constraints** — stacking height, footprint conflicts, keep-outs.
- **Test-expectations artifact (A6) — MOVED to its own project
  `claude/hw-expectations/` (2026-07-23).** The generalization that earned the
  promotion: board-level facts (a bare board = the trivial rig, e.g. frdm's
  onboard fxos8700) belong in it too, so the producer can't live solely in the
  rig expander. In THIS project: the emitter keeps writing the
  `expectations.yml` stub unchanged, but nothing gates on it (no consumer, not
  a goldens gate, schema unfrozen). Context: `ontology.md` A6,
  `requirements.md` open question 6, `claude/hw-expectations/README.md`.
- **Runtime instance identity** — device names/labels for N instances at
  runtime; touches Zephyr driver model beyond DT. Context: `requirements.md`
  open question 4.

## Lints (agreed 2026-07-19, deliberately later)

- **rig.overlay ownership lint** — expander superficially parses
  `rig.overlay` and warns on writes into analyzer-owned output (bus
  children, `reg`, `cs-gpios`). Until then the ownership rule is documented
  only (conventions.md Conv. 8: undefined behavior).
- **rig.overlay reference/alias lint in the loader** — validate alias names
  (DT spec: `[a-z0-9-]`, no underscores) and generated-label references at
  expansion time, instead of falling back to dtc's build-time
  undefined-label error. Context: Conv. 8 "accepted trade".

## Build integration

- **`--shield` with inline socket placement, desugaring to an in-memory rig**
  *(parked 2026-08-04, Tobi's idea; the in-memory-rig half is what we will
  definitely return to)* — extend upstream's `--shield` so a shield can name
  WHICH typed socket it mates. Solves a real upstream problem with no answer
  today ("place this shield on connector 3 of 4"), and is a far more
  digestible upstream contribution than the whole rig ontology: a bridge that
  makes typed sockets useful to people who never adopt rigs. Prior art to
  read first — upstream RFC #82889 / PR #82825 (shield options,
  `shield@index:opt=val`), closed unmerged 2026-02-27.

  Three findings from when this was floated, recorded so they are not
  rediscovered:

  1. **`;` cannot be the separator.** `SHIELD` is already list-valued —
     `zephyr/cmake/modules/shields.cmake:44` is
     `string(REPLACE " " ";" SHIELD_AS_LIST "...")` — so space AND semicolon
     already separate shield NAMES. A `-DSHIELD=name;sockets=...` form
     reaches cmake as a two-element list whose second element fails as an
     unknown shield. Upstream's own RFC used `@` and `:` for exactly this
     reason.
  2. **It must DESUGAR to a rig, never reimplement placement.** rig.yml is
     THE front end (conventions v4). Growing a second socket-binding
     mechanism in cmake means two semantics in two languages that will
     drift. Constructing a synthetic one-instance rig in memory and running
     the ordinary pipeline makes this shorthand rather than a second front
     end — and that in-memory-rig mechanism is reusable well beyond this
     feature.
  3. **It does NOT unblock the singleton identity law**, and must not be
     justified that way. That law is `--shield s` ≡ a DEFAULT-placed
     singleton rig; an explicit socket is the opposite direction. Worse, if
     our extended `--shield` desugars to a rig, comparing it against a rig
     is true by construction and tests nothing — the law's oracle must stay
     upstream's REAL `--shield`, because its whole value is that two
     INDEPENDENT mechanisms agree.

  Cost not yet paid: `cmake/shields.cmake` is currently pure dispatch and
  promises non-rig builds "behave exactly as upstream". This retires that
  promise, and the SHIELD/RIG exclusivity FATAL needs rethinking, since the
  extended form wants the rig path.

- **Application rig-specific overlays** *(2026-07-21)* — extend Zephyr's app
  `boards/<board>.overlay` auto-discovery to rigs: board-keyed overlays keep
  firing on the rig's board (unchanged), plus a new rig-keyed overlay
  (`<rig>` in place of `<board>`) for finer per-rig app customization. Applied
  late in the overlay chain (after the generated overlay + `rig.overlay`),
  most-specific-wins. Open fork: the app path convention (new `rigs/` dir vs
  reuse `boards/` with the rig name). Pure overlay discovery/ordering — no
  model involvement. Overlay chain: board.dts → generated overlay → shield
  `boards/<board>.overlay` → `rig.overlay` → app board/rig overlays →
  `EXTRA_DTC_OVERLAY_FILE`.
- **`rig-`/`.rig.` prefix cleanup** *(2026-07-21; INVENTORIED 2026-07-25,
  MOSTLY MOOT — one decision left for Tobi)* — Tobi flagged the `rig-`
  prefix (`rig-shields`, `.rig.yml`/`.rig.dtsi`/`.rig.overlay` infixes, the
  `/ { rig { } }` node) as adding little value and hard to land upstream.
  Inventory taken during the de-provenance sweep (design-log 2026-07-25f):
  - **`rig-shields` — THE ONE REAL DECISION LEFT, awaiting Tobi.** The DT
    subtree every `.shield` template wraps its content in, parsed at
    `shields.py:31`. Present in all 13 shield source files and rendered
    into diagnostic `SrcRef` paths in 3 tier-1 goldens. Highest blast
    radius of anything in this sweep: a rename touches every shield file
    plus any golden whose diagnostic path crosses it.
  - **The `.rig.*` infixes are GONE** as of the B1 rename (`eb929e0`):
    every real file is a bare `rig.yml` / `<rigname>.overlay` /
    `<rigname>_defconfig`. Two stale doc mentions survive (`cli.py:163`
    help text, `dts.cmake:476` comment) — housekeeping, not a decision.
  - **The `/ { rig { } }` node never existed** in the real tree; rig
    topology lives in YAML, never DT. Nothing to decide.
  - `_rig_*` cmake prefixes are tracked separately below
    (cmake fork re-idiomization). `rig-gen.*` was deliberately chosen in
    the B1 rename and is NOT up for review. The `build_info` provenance
    keys were fixed in `76b45cf` (`rig-yml`/`rig-conf`/`rig-overlay` →
    `yml`/`defconfig`/`overlay`).
- **cmake fork re-idiomization for upstream** *(2026-07-24)* — the `_rig_*`
  variable prefix in the cmake forks is general-CMake internal-var
  convention, NOT the zephyr-modules house style (they use plain leaked
  locals, occasional `unset()` cleanup, or — the modern trend — a
  function-wrapped module body with explicit `PARENT_SCOPE` exports:
  pre_dt's `pre_dt_module_run()`, snippets' `zephyr_process_snippets()`,
  dts.cmake's functions + `dts_init`). Keep `_rig_*` downstream (it is
  collision armor for a block forced to run at the shared file scope);
  when drafting the ACTUAL upstream patches from the forks, re-shape the
  dts fork's rig block into a `rig_module_run()`-style function with
  plain-named locals and explicit exports (~6 output vars). Mechanical;
  do it at patch-drafting time, alongside the naming sweep above.
- **Where the expander runs** *(parked 2026-07-19)* — west extension vs.
  CMake module; prototype is a standalone tool until the S1 fidelity
  milestone passes. Context: `architecture.md` §Deliberately undefined.
- **Rig discovery** *(parked 2026-07-19)* — scanning a `rigs/` root
  (hwmv2-style, `rig.yml`): loader concern or fourth component? Irrelevant
  until there are rigs to discover. Context: `architecture.md`.

## Ecosystem / governance

- **Connector-type registry** — who authors and maintains grove/mikrobus/
  arduino-r3 type definitions; analogous to `dts/bindings`. Context:
  `requirements.md` open question 5.
- **Front-end syntax sugar layer** — revisit a nicer authoring syntax only
  after 2–3 real rig descriptions exist in valid-DTS conventions; R24
  (instance-qualified references) is the acid test. Context: `design-log.md`
  2026-07-17 decision, `requirements.md` open question 2.

## Evidence chores

- ~~**Aliases/`chosen` naming policy** (R10)~~ **RESOLVED 2026-07-19** —
  conventions.md Conv. 8: labels are compositions
  (`<instance>_<shield-local label>`, the public API); aliases/`chosen` are
  rig-owned selections authored natively in `rig.overlay`; shields banned
  from `/aliases`+`/chosen`; no counter-based auto-numbering (R18).
  Remaining sub-detail (board-`chosen` collision policy) waits for a
  scenario.

## Aggregation follow-ups (from gap #4, 2026-07-21)

- **Explicit collection names** — device collections (Conv. 9) currently
  aggregate by compatible (all gpio-keys entries → one node). A rig that wants
  two separate gpio-keys collections would need an explicit collection key.
  Deferred until a scenario needs it.
- **Merge into a board-provided collection** — if the target board already
  has a `gpio-keys` node, the rig's entries should be able to join it rather
  than creating a second collection. Needs the expander to find the board
  node by compatible (like Conv. 4 socket discovery). Context: Conv. 9.
