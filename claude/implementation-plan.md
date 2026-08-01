# Rigs — Real-Implementation Plan

The prototype phase is complete: the model (R1–R27 bar the build-level R2), the
front-end (`rig.yml`), and the conventions are validated across the S1–S8 sweep
plus the bridle real-hardware port (20 rigs, all green, R7 throughout). The
**spec** is the doc set — `conventions.md` (v4), `ontology.md`, `requirements.md`,
`architecture.md`, `rig-dt-syntax.md` — with `frontend-trial/` as the executable
oracle. This plan turns the prototype into a real Zephyr feature.

## Guiding principle — additive-first

Every choice defaults to *adding* over *editing*: new files/modules over
touching existing ones; **consume** dtlib/edtlib as libraries rather than patch
them; a **downstream** Zephyr module before upstream integration. This is also
the upstream-landability strategy — the less we touch, the more landable.

## Execution model

One **driver** drives the plan and delegates each phase to a **sub-agent** with
a self-contained brief (inputs / deliverable / exit criteria below). Human
review gates between phases (the rhythm the prototype was built on) — this is
*not* a fire-and-forget mega-run. **P0 and P1 run in parallel** (independent);
everything else is sequential on their outputs.

## Proven vs unproven

- **Proven (prototype):** the rig model + analyzer + emitter; loader over
  `rig.yml` + per-shield `.shield` TUs; overlay / config-sheet / expectations
  emission; nets, allocation, scopes/nesting, multi-function positions,
  collections; R2 *at the overlay level*.
- **Unproven / deferred:** build-system integration; a real dtc/edtlib
  round-trip (only overlay-level fidelity shown); the Kconfig activation
  manifest; pinctrl fragment application; device sub-nodes / `status="okay"`.

---

## P0 — Reuse-boundary analysis (∥ P1)   [desk]

**Goal.** Ensure the real expander only *adds* functionality — consuming
dtlib/edtlib for everything they already do.
**Inputs.** `frontend-trial/scripts/rigexp/*.py`; dtlib + edtlib
(`zephyr-rigs/scripts/dts/python-devicetree/src/devicetree/`).
**Deliverable.** A mapping table: each rigexp component that touches DT
mechanics → dtlib/edtlib equivalent → *reuse* or *keep-new*. Flag the
hand-rolled bits to replace (gpio-map parsing in `boarddt.py`, property
rendering in `dtsio.py`, phandle/nexus resolution) and name the genuinely-new
layer (rig model / analyzer / emitter — no edtlib equivalent).
**Exit.** A "consume, don't patch" boundary the real expander respects.

**Outcome (2026-07-21, P0 done).** Decision: the real expander is built on
**`edtlib.EDT`**, not raw dtlib. edtlib already provides — spec-correctly —
everything the prototype hand-rolled: `Node.maps` (→ `MapEntry`) for any
`*-map` incl. our `socket,pwm-map`/`socket,adc-map`; `ControllerAndData` (with
the multi-level gpio-map chain already chased, and named cells) for consumed
gpio/pwm/io-channel refs; `Property.val` typing; `Register` for `reg`;
`str(prop)` for faithful rendering *including phandles*. So **replace**:
`boarddt._map_entries`/`_gpio_map_entries`, `shields._parse_pos_ref` +
`_ncells` (cell-count guessing), `dtsio.render_prop` (its phandle gap → use
`str(prop)`), `dtsio.words` (→ `to_nums`). Note: the prototype's rigid 5-cell
nexus rows are a genuine *simplification* (real row width depends on `#*-cells`)
that edtlib gets right — a correctness upgrade, not just dedup. **Keep-new**
(no edtlib equivalent): `model` / `analyzer` / `emitter` / `diag` — the actual
product, layered on edtlib's data structures via a ~small adapter
(`ControllerAndData`/`MapEntry` → rig `GpioRef`/`gpio_map`). Connector-type
bindings parse via `edtlib.Binding`, with rig extensions (plug pairing,
positions, cs-pool default, stackable) read off `Binding.raw`. Zero edits to
dtlib/edtlib. The `dt_*` Kconfig helpers are Kconfig-time, out of scope for
overlay generation. `parse_header_indices` (C-macro header) + CPP invocation
stay (build-harness, not DT mechanics).

## P1 — Integration seam: decide + spike (∥ P0)   [the gating unknown]

**Goal.** Decide how a rig becomes a build, downstream-module-first.
**Inputs.** Zephyr build extension points (`cmake/modules/{dts,shields,
kconfig}.cmake`, `module.yml` build hooks, `pre_dt` hooks,
`EXTRA_DTC_OVERLAY_FILE`, snippets, sysbuild); **bridle as role model**
(`bridle/module.yml`, `bridle/cmake/modules/*` — what it extends vs merely
provides as data).
**Deliverable.** (a) An extension-point inventory; (b) a decision —
downstream-module-feasible (preferred, additive) vs upstream-integration-
required — for each of: a `--rig` build entry, running the expander at
configure time *before* DT processing, feeding the generated overlay + Kconfig
fragment; (c) the **spike**: a downstream module that runs the expander and
feeds a generated S1 overlay into a real build.
**Exit.** A working seam + a decision, with the code location that follows from
it (own module package if downstream; new `scripts/` package if upstream).

**Outcome (2026-07-21, P1 done).** Decision: **downstream module, zero upstream
edits** — bridle is the working template. Mechanism: ship a
`ZephyrBuildConfiguration`/`ZephyrBuild` package (as bridle does) that
`list(APPEND zephyr_cmake_modules rig/expand)`; `zephyr_default.cmake` includes
it **before `dts`**, so `rig/expand.cmake` can `execute_process(<expander>)` →
write `${CMAKE_BINARY_DIR}/rig/<rig>.overlay` (+ `.conf`) → `set(EXTRA_DTC_OVERLAY_FILE …)` /
`set(OVERLAY_CONFIG …)` + register `CMAKE_CONFIGURE_DEPENDS` on the rig file and
`rigexp/*.py`. `--rig` entry: a **west extension command** (`west-commands.yml`,
like bridle's `bridle-export`) and/or a plain `-DRIG=<name>` cache var — a snippet
`-S <rig>` is a data-only third option. All four needs (build entry, generate
pre-DTS, feed overlay, feed Kconfig) are downstream-feasible. **Caveat:** the
`ZephyrBuild` slot is a workspace singleton (bridle claims it in a bridle
workspace) — to coexist, append to bridle's `zephyr_cmake_modules` instead of
shipping a second package. **Prereq for the spike:** add a `python -m rigexp
expand <rig.yml> --out-dir <dir>` CLI (today only `run_trials.py:investigate`
dumps `emitter.emit()`'s `{filename: content}` dict). Spike = build a sample on
`native_sim`/`qemu_cortex_m3` with `-DRIG=s1`; success = the generated overlay
is picked up (`dts.cmake` "Found devicetree overlay") and the shield nodes
appear in `build/zephyr/zephyr.dts`, and editing the rig re-triggers configure.

## P2 — Walking skeleton: S1 end-to-end for real

**Goal.** One full pipeline on real hardware — the build diff we deferred.
**Inputs.** P0 boundary + P1 seam; the S1 trial (`s1-datalogger.rig.yml`,
`FIDELITY.md`); `build-rig/upstream/S1`.
**Work.** Convert one board (real `nucleo_f401re`: socket node + legacy
aliases, Conv. 4), author the `arduino-r3` connector-type bindings for real,
convert `adafruit_data_logger` to a `.shield`; run the real expander through
the seam; `west build`; **diff `zephyr.dts` against `upstream/S1`** (real R2).
Close the enumerated S1 gaps (`status="okay"`, `sdmmc` device sub-node) to
reach equivalence.
**Guarantee (named track): legacy-path regression.** Prove `west build -b
<board> --shield <shield>` is byte-identical before/after the board conversion
— the safety net for converting boards.
**Exit.** Real R2 pass on S1; legacy path provably unchanged; P0/P1 validated
on a real build.

## P3 — Widen the requirement slices — ALL DOWNSTREAM SLICES DONE (2026-07-22)

**Goal.** Grow the pipeline one requirement subset at a time, each end-to-end
(rig.yml → expander → real build → runs), each with tests (see Test/CI).
Sub-slices, in order — **each includes its config outputs** (the Kconfig
activation manifest and, where relevant, pinctrl fragment application) and the
model-gap backlog items it needs:

- **3a Allocation — DONE.** S2/S5: CS pools, address straps, routing jumpers, the
  Kconfig activation manifest (4th output). Rigs quail-sockets/quail-temp-farm/
  quail-dup-th/nucleo-wifi-logger(-ok).
- **3b Interposers — DONE (`0158260`, + emitter fix `ae4f62b`).** S6 nested
  carriers (frdm-eth-nest accept, frdm-cs-clash reject phys-cs) + S8 scope-creating
  mux (nucleo-mux-farm accept, nucleo-mux-clash reject phys-addr), on real builds.
  Emitter fix: synthesized carrier nexuses now carry gpio-map-mask/pass-thru.
- **3c Multi-function + pinctrl — DONE (`a555120`, + mechanics `afe5857`/`a980947`).**
  PWM/ADC positions (lotus-pwm accept, lotus-pwm-clash reject phys-channel) +
  gpio-keys/leds (lotus-buttons accept). **R21 pinctrl fragment application** is
  implemented as a rig-authored **`rig.overlay`** (DT counterpart of rig.conf,
  appended to EXTRA_DTC_OVERLAY_FILE) carrying the real board pinmux the expander
  does not author. Emitter also now carries collected devices' passthrough props.
  DAC/UART emission: not needed by the corpus; deferred until a rig wants it.

**Exit per slice.** The slice's rigs build (or reject) on real hardware exactly
as the prototype oracle says (verified via `run_trials.py` + per-rig
`west build-rig` accept/reject — see Test/CI).

## Cross-cutting — Test / CI

**Goal.** Regression safety as the slices grow.

**Downstream (now):** the accept/reject oracle is `frontend-trial/scripts/
run_trials.py` + `SCENARIOS.md`, cross-checked by building each ported rig with
`west build-rig` and asserting configure-clean or the expected rejection.
Preserve **diagnostic parity** — the physically-worded `phys-*` messages must
survive the trip through west/CMake, and loader diagnostics must surface
cleanly.

**twister — PARKED, upstream-coupled (2026-07-22).** Running the corpus under
twister requires `testcase.yaml` to accept a RIG as a *platform*, which lives
in Zephyr's twister/platform machinery — NOT solvable in the downstream module.
It is its own work item, tied to the **upstream-integration** milestone (do it
just before/after upstream landing), so it is moved OUT of the downstream P3
push. The **expectations** artifact (A6) is no longer tied to this milestone —
it moved to its own project, `claude/hw-expectations/` (2026-07-23): the stub
keeps being emitted but nothing gates on it. Until then, the two
downstream checks above are the regression net.

## Post-slice hardening, rig-structure & code review (once the slices are functional)

Deferred until the pipeline works end-to-end (fast iteration first, polish after):

- **De-hardcode / assumption audit. — DONE (2026-07-22).** Stripped the
  hard-wired paths and environment-specific assumptions so the module is
  relocatable. Resolved: `rig.cmake` `RIG_EXPAND_PYTHON` → `PYTHON_EXECUTABLE`;
  `RIG_EXPAND_SHIELD_DIR` → discovered from every `BOARD_ROOT`'s `boards/shields`
  (shields are content in any module, not pinned to btr-shields); `rigexp/dtsio.py`
  + `dts_equiv.py` absolute dtlib/include paths → derived from `$ZEPHYR_BASE`
  (rig.cmake passes it to the expander); `rig.py` self-locates its module root
  (`parents[2]`, no `'btr-shields'` literal); the `zephyr-rigs` worktree name is
  no longer hardcoded — `build-rig` resolves the tree via `--zephyr-base` > west
  config `zephyr.base` > discovery, ignoring the profile's `$ZEPHYR_BASE` (plain
  `zephyr`, the wrong tree). No `/wrk/z/ws-up` literals remain in the mechanics
  code (only a comment example in `zephyr/module.yml`). **NOT covered** (it is a
  rewrite, not a path fix — see P0): the expander still reads board socket models
  and connector bindings from its bundled `scripts/rigexp/common-dts/{boards,
  bindings}` (the Bridge-A scaffold). Unbundling those = building the expander on
  `edtlib.EDT` so it reads the real board DT / bindings from the board_root; do it
  with the edtlib migration + the Python-review/unit-test item below, not here.

- **Bridge-A deconstruction / edtlib rewrite — DESIGN SETTLED (2026-07-22),
  spike in flight.** Retire `scripts/rigexp/common-dts/{boards,bindings}`; pass 1
  (the rigexp projection) reads the REAL board DT + bindings via `edtlib.EDT`.
  Given: the two-pass projection is intended architecture — pass 1 (enriched
  rig-DT → standard-DT overlay) legitimately runs its OWN edtlib pass; pass 2 is
  the normal Zephyr toolchain. Phased plan, each step validated against the
  3a/3b/3c corpus (same accept/reject + overlay per rig):
  1. **`boarddt` → edtlib EDT of the real board. — SPIKE VALIDATED (nucleo,
     2026-07-22).** A standalone `edtlib.EDT` over the real `nucleo_f401re_btr.dts`
     reproduces `boarddt.load_board`'s model exactly (all 22 gpio-map positions,
     bus labels), cross-checked byte-identical against pass-2's own `edt.pickle`.
     `model.py` needs NO changes (edtlib values slot into the existing dataclasses
     — safe incremental swap). Recipe: cpp the board `.dts` (include dirs are
     recorded in a real build's `build_info.yml` devicetree.include-dirs — factor
     a shared helper, dtsio.py has half of it) → `edtlib.EDT(pre, [bindings dirs],
     default_prop_types=True, infer_binding_for_paths=["/zephyr,user","/cpus"])`;
     read `node.maps["gpio"]` (MapEntry → position/pin), `node.props["socket,i2c"]`
     (typed phandle), `node.binding.raw[...]` (type-level defaults). FRICTION FOUND
     + RESOLVED: edtlib's typed API can't distinguish authored-vs-defaulted (it
     back-fills binding defaults), which boarddt's `cs_pool None-if-absent` relied
     on. But the analyzer only uses that as `socket.cs_pool if not None else
     ctype.cs_pool` (analyzer.py:533) = exactly edtlib's binding-default merge — so
     once step 3 moves the default INTO the binding, `node.props[...].val` gives the
     effective value directly (no private `_node.props`, and the manual merge
     simplifies). The two decisions converge.
  2. **PWM/ADC via real nexuses (2a) — SPIKE VALIDATED (lotus, 2026-07-22).**
     Standard `pwm-map`/`io-channel-map` nexuses on the real grove socket are
     accepted by pass-2 (plain board build + lotus rigs), and `Node.maps["pwm"]/
     ["io-channel"]` reproduces the common-dts routing exactly incl. the D2/D4→
     tcc0-ch0 clash; reject rig unaffected. Diff saved (scratchpad/spike-2a). KEY
     FINDING: edtlib rejects ANY undeclared property, so the CONNECTOR BINDING must
     declare `pwm-map`/`io-channel-map` (+ `#pwm-cells`/`#io-channel-cells`/mask/
     pass-thru). Upstream `pwm-nexus.yaml`/`io-channel-nexus.yaml` exist (gpio-nexus
     analogues) but their maps are `required:true` and dtschema `include:` can't
     downgrade to optional; not every socket is PWM/ADC-capable → declare the props
     INLINE in the connector binding. So **step 2 COUPLES to step 3** (binding
     enrichment is the prerequisite). Cells: `#pwm-cells=2` (channel+period, via the
     board's `atmel,sam0-tcc-pwm` override); `#io-channel-cells=1` (no pass-thru).
     Original design rationale follows:
     routing as STANDARD-named `pwm-map` / `io-channel-map` nexuses ON the real
     socket node (`#pwm-cells`/`#io-channel-cells` + `*-map-mask`/`*-map-pass-thru`),
     parallel to `gpio-map`. edtlib resolves any `*-map` generically
     (edtlib.py:1520 — strips `-map`, needs `#<space>-cells`), so this reads
     natively as `MapEntry`. Retires the common-dts pwm/adc metadata AND unifies
     the emitter (pwm/adc emit `<&socket POS …>` and dtc chases, like gpio — no
     more resolve-directly special case). NOTE: the 3c `*-map` gotcha was ONLY
     the `socket,`-prefixed name (→ `#socket,pwm-cells`); standard `pwm-map` is
     fine. Detail to work out: the 3-cell pwm nexus layout (POSITION+period+flags
     → channel, period/flags passed through).
     **NEXT SPIKE (last unknown before the full rewrite):** implement 2a on the
     lotus grove socket — add `pwm-map`/`io-channel-map` nexuses to
     `grove_sockets_btr.dtsi`, then verify (i) the board still builds in pass 2,
     (ii) `edtlib Node.maps["pwm"]/["adc"]` reads them standalone, (iii) lotus-pwm /
     lotus-pwm-clash still expand to the same overlay/verdict. The nucleo spike
     deliberately covered gpio/bus only.
  3. **Connector types → binding YAML (decided; MECHANISM AMENDED 2026-07-23).**
     REVIEW FINDING: custom top-level/per-property keys in a real binding are
     IMPOSSIBLE — edtlib validates every loaded binding against a closed
     allowlist (`ok_top`, edtlib.py:450, hard error :468; per-prop keys :507),
     and pass 2 loads `connector/X.yaml` because the socket compatible is in
     the board DT — custom keys there break every regular build. Split instead:
     SOCKET-side type facts are already schema'd properties with defaults in
     the real binding (cs-pool default / stackable — done, idiomatic); PLUG-side
     facts (positions/functions/optional, bus-proxies) never reach pass 2 and
     stay in a pass-1-only YAML that must NOT live under any `dts/bindings`
     root (edtlib globs + bindings CI lint those wholesale) — location TBD,
     e.g. `dts/connectors/plug,X.yaml`. This REDUCES the step-2 coupling: what
     step 2 needs from step 3 is only the standard property declarations
     (pwm-map/#pwm-cells/mask/pass-thru) in the real binding — spike-validated.
     NOTE: shields synthesize sockets too (arduino_uno_click, i2c_mux) and are
     dtlib-parsed templates — ctypes_registry keeps serving type defaults for
     those regardless; only its data source moves. Original (superseded in
     mechanism, kept for intent): fold the common-dts
     `plug,X`/`socket,X` rig-extension fields (positions, cs-pool default,
     stackable, allowed bus proxies) INTO the real `dts/bindings/connector/X.yaml`
     as custom keys; `ctypes_registry` reads them via `edtlib.Binding.raw`. The
     `dt-bindings/connector/X.h` position-index headers STAY (build-harness, used
     by both the real gpio-map and the expander). Plug↔socket pairing by naming
     convention (`plug,X` mates `socket,X`).
  4. **Drop `dtsio`'s hand-rolled cpp/dtlib + `render_prop`/`words`** per P0 (use
     edtlib `str(prop)` / `to_nums`); keep `parse_header_indices` + the cpp step.
     CAUTION (review 2026-07-23): render_prop's None-for-phandles policy
     (dtsio.py:100) is load-bearing — dtlib's `str(prop)` renders phandles via
     labels and would leak shield-local labels into the overlay as dangling
     refs. Scope this step to replacing hand-rolled value DECODING; keep the
     phandle policy.
  Bonus: step 1's capability (edtlib-read the real socket) is also what enables
  auto-synthesizing the guarded legacy-compat layer from the typed socket.

  **SAFERAILS for this rewrite (agreed 2026-07-22; (1)/(2)/(13) amended after
  the honest review 2026-07-23).**
  Oracle & harness: (1) freeze GOLDENS for every 3a/3b/3c rig first, in TWO
  TIERS (amended: dts_equiv.py cannot parse a bare overlay — unresolved &refs —
  and step 2 INTENTIONALLY changes the overlay, so the overlay can't be the
  invariant). Tier 1 (fast, every rig): expander-level fixtures — normalized
  overlay text + verdict + rendered diagnostics (incl. warnings on accepts) +
  context.cmake + conf + config-sheet.md; expectations.yml is EXCLUDED (parked
  to claude/hw-expectations — emitted, never gated). Tier 2 (per accept rig,
  @pytest.mark.build): cmake-only `west build-rig` → zephyr.dts, compared via
  dts_equiv.py — THE invariant that must hold across ALL phases; when a phase
  legitimately changes tier 1 (step 2), tier 2 is the oracle and tier 1 is
  re-frozen with a justification note. Reject rigs also get a build-level
  configure-fails check. Plus synthetic reject fixtures for rewrite-touched
  paths the corpus misses (unknown board / phys-board). (2) SHADOW period:
  boarddt reads BOTH common-dts and the real board (edtlib) and asserts equal
  Board models — comparing EFFECTIVE values (e.g. cs-pool after the
  ctype-default merge, analyzer.py:533): edtlib back-fills binding defaults
  where common-dts yields None-if-absent, and the real nucleo/frdm sockets do
  not author socket,cs-pool. Flip to
  edtlib-only + delete common-dts only after the whole corpus passes dual-read.
  (3) edt.pickle cross-check: pass-1 edtlib read == pass-2 edt.pickle per board
  (the nucleo spike's check). (4) Diagnostic parity, expecting src provenance to
  move from common-dts/* to the real board files.
  Sequencing: (5) per-board, never big-bang (nucleo→quail→frdm→lotus). (6)
  per-phase, never combined. (7) binding enrichment (step 3) lands before/with the
  cs-pool switch — the authored-vs-defaulted dissolution depends on it. (8) retire
  common-dts in one final deletion commit.
  Invariants: (9) model.py FROZEN — input-side only (spike-confirmed). (10)
  consume edtlib, ZERO patches (P0); missing capability → downstream or upstream
  ask, never fork. (11) board DT changes valid for ALL consumers — verify plain/
  legacy board builds, not just rigs. (12) two-pass boundary clean — pass-1 needs
  no app/overlay context. (13) AMENDED (2026-07-23 — chicken-and-egg found):
  build_info.yml's devicetree section is written by dts.cmake AFTER rig.cmake
  ran the expander (dts_build_info_output, dts.cmake:439), so it does NOT exist
  at expand time in a fresh build dir; and include(pre_dt) from rig.cmake is
  unsafe twice over (needs ARCH_V2_NAME_LIST from hwm_v2@97 > shields@95, and
  its include_guard(GLOBAL) would no-op dts.cmake's own later include with the
  incomplete result). Therefore: rig.cmake COMPUTES the include/bindings dirs
  itself (deliberate ~30-line mirror of pre_dt.cmake; arch dirs by glob) and
  passes them + BOARD_DIR/board-dts + the preprocessor to the expander as
  arguments; saferail (3)'s edt.pickle cross-check is the guard that this
  mirrored recipe stays equivalent to pass 2's real one. Keep
  APPLICATION_SOURCE_DIR OUT of pass-1's dirs (saferail 12). The test
  harness/standalone CLI may instead read a cached plain-board build's
  build_info.yml (the spike's approach).
  Upstreaming (edtlib is the destination for the reader layer): (14) goldens +
  dual-read harness become committed test fixtures (seed the rigexp unit-tests +
  twister). (15) MINIMAL downstream footprint — use edtlib wherever it has an
  equivalent; net-new code is only the product layer (model/analyzer/emitter/diag);
  the rewrite deletes more than it adds. (16) edtlib IDIOM conformance — full type
  annotations + mypy-clean (add mypy to rigexp), `"""` structured docstrings,
  Optional/Union not `X|None`, snake_case/_private/@property. (17) LICENSE
  separation — the board/binding READER layer stays BSD-3-Clause-ready and
  decoupled from the Apache-2.0 product layer (edtlib/dtlib are BSD-3-Clause;
  the reader is the upstream-into-python-devicetree candidate). (18) TESTS follow
  the tests/test_edtlib.py template — pytest module-level test_*, fixture .dts +
  binding-YAML dirs alongside the tests (LOCATION, decided 2026-07-23:
  `scripts/rigexp/tests/`, never a top-level tests/ — that is twister-app
  territory in a Zephyr module), build via edtlib.EDT(fixture, [bindings]), assert
  via object equality/__repr__/caplog, mypy-checked. `test_edtlib.test_maps()` is
  the reference for the node.maps["gpio"/"pwm"/"io-channel"] assertions.

- **cmake-alone rig entry — RATIFIED 2026-07-24, NOT started.** Brief:
  `cmake-alone-rig-entry-brief.md`; principle: ontology.md §7 (the
  board→rig lift). Slot-10 rig→board inference in the boards fork via the
  resolver (full `name@rev/variant` target string, variant-proof);
  -DRIG excludes BOTH -DBOARD and -DSHIELD (2026-07-24 amendments — the
  rig owns all physical inputs; even a matching board is FATAL;
  marker-based BOARD enforcement survives reconfigures, SHIELD guard is
  markerless in the shields fork; no canonicalization anywhere; config
  inputs SNIPPET/EXTRA_* stay open); `west build-rig` stripped of ALL rig
  parsing AND passes no board (pure cmake wrapper); double rig resolution
  collapsed. Small
  slice, independent of E2–E4; unblocks twister-as-platform eventually.

- **edtlib namespaced-extension-keys + connector-contract unification —
  RATIFIED 2026-07-24 (Tobi: willing to carry the commit), NOT started.**
  Two parts, run after cmake-alone: (1) CARRIED COMMIT on the zephyr rig
  branch (DRIVER/Tobi scope — NOT implementor-agent work; agents keep the
  zero-patch rule): Binding._check's ok_top loop (edtlib.py:462-468)
  additionally permits vendor-namespaced top-level keys (contain a comma,
  e.g. `rig,positions`), preserved opaquely in Binding.raw; + docstring +
  test_edtlib.py case; upstream-RFC-shaped like the two existing carried
  commits. Lands in python-devicetree (BSD-3, synced out) — slightly more
  sensitive than the build-metadata schema commits; ok_top region stable
  for years. **SAFERAIL 10 AMENDED**: "zero edtlib patches" binds the
  expander and the agents; a deliberate upstream-shaped carried commit on
  the rig branch is a distinct, driver-ratified instrument. NAMESPACE
  CHOSEN (Tobi, 2026-07-24c): **`rig,*`** extension keys. PART (1) DONE
  2026-07-24c — carried commits `c1c4d2acf2d` (precedence bug fix) +
  `1a657124349` (vendor-namespaced keys; -cells suffix deliberately keeps
  its specifier2cells meaning — enables vendor-defined *-map nexuses) on
  `tskr/zephyr-rigs`, both signed-off; branch ref updated ([ahead 2],
  push = Tobi's call). Preparing it exposed
  **upstream-issue candidate #4 — a real BUG, PR-able independently of
  rigs**: edtlib's *-cells validation (edtlib.py ~505) has an
  operator-precedence defect, `(A and B) or C`, iterating EVERY top-level
  value; the first non-iterable value crashes with TypeError instead of
  validating anything. Fixed + regression-covered in the same prepared
  patch; SPLIT into its own commit when carrying (each upstreams
  independently). (2) DOWNSTREAM
  slice: merge plug contracts into the socket bindings (one file per
  connector type under dts/bindings/connector/), loader reads
  Binding.raw, `dts/connectors/` + its README dissolve; goldens must be
  output-stable. Motivation strengthened by the binding-scan fast path
  (edtlib validates a dts/bindings file only if its TEXT matches a
  dt compatible — validation is content/build-nondeterministic; the
  current dts/connectors boundary is correct but subtle). Choose the
  extension-key namespace together with the naming sweep + the
  vendor-prefixes registry entry (one namespace decision, made once).

- **Rig variants & revisions + shield revisions — DESIGN SETTLED
  (2026-07-23), implementation NOT started.** Full spec:
  `rig-variants-revisions.md` (five pushback rounds, Q4–Q9 ratified).
  Slicing (each through the implementor/reviewer/gate loop):
  1. **Slice V1 — the delta engine + revisions + shield revisions.**
     Loader-side qualifier parsing (`name@rev`, hwmv2-exact), rig.yml
     `revisions:` block, `rig_<rev>.yml` fragments with the minimal merge
     vocabulary (shallow instance-name-keyed replace, explicit
     add/remove-instances, wires by endpoint pair, no deep merge, errors
     never silent no-ops), shield.yml `revisions:` +
     `<name>_<rev>.shield` DT-overlay fragments + `shield: name@rev`
     references, `list_rigs`/`west rigs`/build-rig qualifier support,
     selected rev into context.cmake + build_info provenance. Pilot rig
     family + goldens per the Q8 budget (4 accept tuples both tiers, 4
     synthetic rejects; shield-rev pilot at zero churn to existing rows).
     PLUS **per-instance parameters — DESIGN NOW SETTLED (2026-07-25,
     two pushback rounds; `rig-variants-revisions.md` §"PER-INSTANCE
     PARAMETERS — DESIGN SETTLED", round record in design-log
     2026-07-25h).** Shield declares per device node with
     `shield,params` (string list); the property's PRESENCE is its
     default, its ABSENCE means the rig MUST assign it. Rig assigns under
     `params: {<device>: {<property>: value}}` and declares its token
     vocabularies in `dt-includes:` (NOT `includes:` — that would read as
     fragment inclusion). Loader RESOLVES against exactly those headers
     (validation + the config sheet's number); emitter EMITS THE SYMBOL
     verbatim. Fourth generated artifact `rig-gen-includes.dtsi`
     (Tobi's call over a `.overlay`) carries the declared `#include`
     lines and is pulled in by a QUOTED `#include` at the top of
     `rig-gen.overlay` — no overlay-list entry, no ordering constraint,
     no cmake guard, no build_info key. Vocabulary still reaches the
     hand-authored overlay and app overlays because
     `zephyr_dt_preprocess` cpp's every overlay in ONE TU
     (`extensions.cmake:4910-4911`). Emitted only when
     `dt-includes` is non-empty, so the other 12 corpus rigs see zero
     churn. Diagnostics take the `lang-*` family (declaration errors, not
     physics): `lang-param`, `lang-dt-include`, six loud rules.
     `shield,params` joins `_MODEL_PROPS` (`shields.py:24`) so it is
     stripped from emission. Fixes grove_btn's type-level `zephyr,code`
     AND its stale "currently INERT" comment. `invert:` deliberately
     stays a separate flag transform, NOT the mechanism's first client.
     Requires the model.py freeze lift (below). OUT OF SCOPE by Tobi's
     call: per-parameter vocabulary/range checking.
  2. **Slice V2 — variants on the same engine.** `variants:` block
     (default allowed), `rig_<variant>.yml` fragments (board/sockets keys
     legal here only), abstract socket names + per-variant maps,
     `rig_<variant>.overlay/.conf` collection, `/variant` qualifier,
     variant-name≠revision-id validation, `phys-variant` diagnostics,
     variant tuples into the pilot goldens.
  Everything resolves in the LOADER — analyzer/emitter stay untouched.

- **Controller-label determinism + diagnostic wording — LANDED
  `2378fab` (2026-07-25), ONE HALF DEFERRED TO V1.** Fix (a) done: the
  emitter's label choice is `labels[0]`, the defining label. Fix (b)
  — analyzer diagnostics sourcing controller identity INDEPENDENTLY of
  the emitter's pick — is deferred: there is exactly one
  controller-identity rendering (`phys-channel` via `_net_descr`'s
  "chan" branch) and it reads the same `board_edt` pwm_map/adc_map value
  the emitter does, so independence requires widening
  `model.BoardSocket.pwm_map`'s tuple, i.e. the model.py freeze lifted.
  Invariant recorded at `analyzer.py:363`; do it in V1, which lifts the
  freeze anyway. Original problem statement below for reference.

  **Controller-label determinism + diagnostic wording (QUEUED at E3
  review, 2026-07-25).** `board_edt._controller_label`'s `labels[-1]`
  ("board alias wins") is content-order-fragile ACROSS MODULES — E3
  proved it: re-inheriting bridle's legacy grove aliases flipped the
  emitted enable-line AND the phys-channel diagnostic from `tcc0` to
  `grove_pwm_d19`, so a d2/d4 servo conflict message names an unrelated
  pin's alias (functionally cosmetic — semantic pin + dts_equiv prove
  it — but a diagnostics-quality regression; accepted-with-queue at
  review). Two separable fixes, decided together in one slice: (a) the
  EMITTER's overlay-reference label choice — `labels[0]` (the SoC
  dtsi's defining label) is stable against module composition forever,
  at the cost of one broad final tier-1 refreeze; (b) the ANALYZER's
  diagnostics name controllers by defining label or node path
  regardless of the emitter's pick. Read board_edt's docstring first
  ("treat any change here as overlay-affecting, never cosmetic").

- **Rigs as folder entities.** Promote flat `boards/rigs/<name>.rig.yml` to a
  per-rig folder mirroring the shield-folder model: `rigs/<rigname>/{rig.yml,
  Kconfig.rig, …}`, so a rig becomes first-class with its own Kconfig/config
  alongside its topology (parallel to `shields/<name>/{…, shield.yml,
  Kconfig.shield}`). Update the `-DRIG=<name>` resolution and the expander's rig
  discovery; decide the rigs root location (`boards/rigs/` vs a top-level `rigs/`).

- **Python code review + unit tests.** Thorough review of the `rigexp` package
  (`loader_yml` / `analyzer` / `emitter` / `model` / `shields` / `boarddt` /
  `dtsio` / `diag`) and add **unit tests** at the function level — complementing
  the twister *integration* corpus and the `run_trials.py` accept/reject oracle,
  which are the only tests today.

- **Test-suite de-provenance & upstream sorting — LANDED `3660303`
  (2026-07-25), with one gap RECORDED.** Docstrings recast as timeless
  contract language (rule applied: why the test must exist = keep, who
  found it and when = go; a verifiable upstream fact is a constraint, not
  archaeology). Rig-folder renames landed separately in `eb929e0` as part
  of the underscore sweep. Upstream sorting is a deliberate PARTIAL: only
  `test_recipe_from_build_info` was cleanly separable into a BSD-3
  `test_edt_build.py`; everything else reaches `edt_build` through
  `board_edt.load_board`, which is product layer. **GAP TO FILL BEFORE
  THAT READER UPSTREAMS: `edt_build.build_edt()`/`preprocess()` have no
  dedicated test** — every exercise goes through `board_edt`'s
  higher-level API. Grooming done in the same slice: unknown-board's
  empty known-list, `zephyr/module.yml`'s stale header. Original scope
  below for reference.

  **Test-suite de-provenance & upstream sorting (decided 2026-07-23, run
  AFTER E4).** The golden/corpus tests OUTLIVE Bridge-A (they are the
  expander's executable contract and the active net for the extension
  migration + V1/V2) — but their FRAMING must be recast for upstreaming:
  strip the Bridge-A/saferail/review-finding archaeology from every test
  docstring in favor of timeless contract language; sort tests by upstream
  destination (edt_build gets python-devicetree-idiom BSD-3 unit tests
  that travel with it; the corpus suite stays product-layer); rename the
  scenario-numbered rig folders (s1, s5-temp-farm, …) to their rig names
  (goldens key on rig NAME — corpus-table churn only). Fold into the
  parked `rig-`/`.rig.` naming sweep; do NOT run mid-migration (E1–E4
  rewrite what the corpus is; one sweep after).

## Parked — until the downstream module proves out

- **Upstream landing sequence** — which pieces upstream independently and how
  (connector-types-as-bindings; per-socket nexus nodes; the expander as an
  opt-in west extension) + the **`rig-`/`.rig.` naming sweep**. Revisit once
  P1–P2 tell us what the downstream module can and can't do. (See `parked.md`.)

- **Guarded legacy-compat layer (the migration pattern).** DESIGN RECORDED,
  deferred to upstream (decided 2026-07-22). When the btr clones had their legacy
  connector nexuses stripped (`a46cec9`/`b02bdc7`) they can no longer serve
  traditional `-b/--shield` builds. The clean way to have BOTH — lean rig builds
  AND legacy shield compat — is a per-board `<board>_legacy_compat.dtsi` (the
  removed nexus nodes, recoverable from git `b02bdc7~1` / lotus `a46cec9~1`),
  `#ifndef RIG_BUILD`-guarded in the board `.dts`. Mechanism (verified feasible):
  `rig.cmake` runs only on rig builds (before `dts`), so it injects the guard —
  `set(DTS_EXTRA_CPPFLAGS "${DTS_EXTRA_CPPFLAGS} -DRIG_BUILD" CACHE STRING "" FORCE)`
  (dts.cmake feeds DTS_EXTRA_CPPFLAGS to the board-DTS cpp). Rig build → RIG_BUILD
  defined → compat skipped; legacy build → rig.cmake never runs → compat loads.
  This is exactly the pattern a REAL upstream board needs to add typed rig sockets
  without breaking existing shield users — hence it belongs here, not downstream.
  Costs to budget: it validates a legacy `--shield` path never built on these
  clones (real test surface); frdm's split is awkward (its arduino_header was
  inline, arduino_i2c/spi are load-bearing and kept); and an elegant variant is
  to AUTO-SYNTHESIZE the legacy nexus from the typed socket (single source of
  truth) rather than hand-restore — a generator spike.

## Backlog (slotted into P3 slices, not phases)

Kconfig manifest [3a], pinctrl application [3c], `status="okay"` + device
sub-nodes [P2], DAC/UART emission [3c], aggregation refinements (explicit
collection names, merge into board-provided collections), the parked lints,
auto-routing of free non-CS positions. Full context in `parked.md`.
