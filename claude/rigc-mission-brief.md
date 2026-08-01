# Mission brief — `rigc`

Ratified by Tobi 2026-07-28 (inputs record: `rigc-mission-inputs.md`; this
brief is written from that record plus fresh verification against btr-shields
HEAD `ae7b92b`). All three open items were RULED by Tobi 2026-07-28 (§9);
the brief is fully settled and R0 is dispatchable.

**State delta since the inputs were captured:** HEAD moved past `7e35f33` —
`ae7b92b` ("rigs: adopt the rebased tiacsys zephyr — refreeze the two quail
resolved goldens") already landed, so the current gate validates against the
REBASED tiacsys tree. The two-quail-goldens episode the inputs record predicts
has already been handled once, by exactly the classification discipline §8
prescribes.

## 1. The mission

- **rigexp's production code is FROZEN.** It is not touched again — it is the
  BLUEPRINT, together with its tests, for building **`rigc`** from scratch.
- `rigc` lives at **`scripts/rigc/`**, with **`tests/unit/` and
  `tests/integration/` subdirectories** — the layer split is expressed as
  DIRECTORIES, stronger than markers.
- The **loader / analyzer / emitter** decomposition stays. What changes is
  that **testable design gets the attention it did not get the first time**
  (§6 is the enforceable form of that sentence).
- Proper TDD: tests precede code, and the conformance tests already exist
  (§2).
- The name is `rigc` by analogy to `dtc` (ratified 2026-07-26,
  `bridle-migration.md`): it REJECTS invalid input and emits several
  artifacts, both of which a converter-shaped name would hide.

**Scope of the freeze, stated precisely because R0 edits test files:** the
freeze binds rigexp's PRODUCTION code absolutely. The frozen integration
suite accepts exactly the differential-harness edits (the module knob and the
banner normalization, §3) and NOTHING else — it must remain the suite that
validated rigexp, or it stops being an oracle.

## 2. Conformance criterion: THE GOLDENS ARE THE SPECIFICATION

The 43 reject goldens plus the emitted/resolved corpus goldens are an
**executable list of every diagnostic and every artifact `rigc` must
reproduce**. The TDD loop does not start from prose — it starts from bytes
that already exist and are known correct.

This portability is a direct consequence of the subprocess policy: the
integration tests reach the expander only through the CLI front door, so they
are coupled to the CONTRACT, not the implementation. The CLI contract `rigc`
must implement is therefore fixed by the suite itself: `expand <rig_yml>`
with `--shield-dir` (repeatable), `--board-dts`, `--build-info`,
`--bindings-dir` (repeatable), `--include-dir` (repeatable),
`--connector-dir` (repeatable), `--revision`, `--variant`, `--out-dir`
(`conftest.py:480-496`, `dts.cmake:347-372`), producing the same artifact set
(`rig-gen.overlay`, `rig-gen-includes.dtsi`, `context.cmake`,
`config-sheet.md`) and the same rendered stderr.

Two consequences worth stating up front:

- **Diagnostic WORDING is part of the spec.** The 39 CLI-driven reject tests
  freeze rendered stderr byte for byte. `rigc` reproduces the wording; it
  does not improve it. Wording improvements are golden-changing slices AFTER
  conformance, if ever.
- **Behavioural warts are reproduced first, fixed after.** The inputs record
  flags two inherited forces worth revisiting (a library scan that
  hard-errors on any malformed member; `RIG_DEPENDS` listing
  scanned-but-unreferenced shields). Both are OBSERVABLE in goldens, so
  `rigc` must first reproduce them exactly. Revisiting either is a deliberate
  post-green, golden-changing decision — never something that happens en
  route.

## 3. R0 — the differential harness (first slice, implementor-ready)

**Parameterise the expander module name; do not copy-and-substitute.**
RATIFIED: a cmake variable for the module name (default `rigexp`) plus the
equivalent constant on the test side. The frozen suite then runs against
`rigc` by flipping one value — the same goldens, byte for byte, over both
implementations, diffable at every step. Copy-then-substitute is rejected
because two suites drift silently while `rigc` is incomplete. `rigc`'s
`tests/integration/` becomes its own (moved, not copied) only once it passes
green.

### The substitution surface, verified at `ae7b92b`

| site | reaches | class |
|---|---|---|
| `scripts/rigexp/tests/conftest.py:480` — `[sys.executable, "-m", "rigexp", "expand", …]` | the direct expander tests | argv |
| `cmake/dts.cmake:347` — `"${PYTHON_EXECUTABLE}" -m rigexp expand …` | ALL build-marked tests | argv |
| `cmake/dts.cmake:439` — `file(GLOB … "scripts/rigexp/*.py")` → `CMAKE_CONFIGURE_DEPENDS` | configure-retrigger on source edits | **correctness** |
| `dts.cmake:336,379,386`, `conftest.py:252` — debug-hint strings | rerun scripts, VERBOSE render | honesty |

The third row is a finding NOT in the inputs record and it is the trap: if
the source glob stays pinned to `scripts/rigexp/`, then under `module=rigc`
an edit to `rigc`'s sources does NOT retrigger configure, and every
build-marked test in the TDD loop silently runs the STALE expander output.
That failure mode produces exactly the confusing "my fix changed nothing"
sessions TDD is supposed to prevent. The glob must derive from the module
variable. The fourth row is cosmetic in the same spirit as T2: a `rerun.sh`
or debug hint naming the wrong module is worse than none.

The plumbing already fits: `PYTHONPATH` is `<repo>/scripts` in both places
(`conftest.py:478`, `dts.cmake:131`), so `-m rigc` resolves the moment
`scripts/rigc/` exists. No new path wiring.

### Interaction with the existing knob

`RIG_EXPAND_COMMAND` (`dts.cmake:133`) already exists and replaces the WHOLE
command — it is the stub/probe escape hatch and stays untouched. The new
variable is **`RIG_EXPAND_COMPILE`** (Tobi's ruling 2026-07-28, superseding
the driver's `RIG_EXPAND_MODULE` recommendation; it joins the
`RIG_EXPAND_*` family; default `rigexp`; the VALUE is still a Python module
name). It feeds the default command
construction in the `else()` branch AND the source glob. Note the parallel
pre-existing gap: `RIG_EXPAND_COMMAND` never retargeted the glob either —
acceptable for a stub, not for a real second implementation.

### Threading, test side

One constant, read once in `conftest.py` from the environment (same name,
`RIG_EXPAND_COMPILE`, default `rigexp`), used (a) in the `:480` argv and (b)
appended as `-DRIG_EXPAND_COMPILE=<value>` to every cmake-reaching build path
— the natural seam is the same one `board_extra_defines`
(`conftest.py:129`) already uses to thread `-DEXTRA_ZEPHYR_MODULES` through
plain builds, `west build-rig`, and cmake-alone alike. Running the
differential is then: `RIG_EXPAND_COMPILE=rigc pytest …`.

### The banner finding (verified; must be settled in R0)

**63 golden files embed the string `rigexp`, in two classes:**

1. **Fixture paths** (`scripts/rigexp/tests/fixtures/…` inside `RIG_DEPENDS`
   lines and diagnostic source lines) — NOT a problem. They name where the
   frozen suite's fixtures LIVE, which does not change when a different
   module runs against them. No action.
2. **The provenance banner** — 58 goldens carry `generated by rigexp` in
   exactly three comment forms (`/* … */` in `rig-gen.overlay` AND in one
   `rig-gen-includes.dtsi`, `<!-- … -->` in `config-sheet.md`, `# …` in
   `context.cmake`; the driver's original count of 57 missed the dtsi —
   corrected by R0's implementor). Zero argparse usage text
   leaks into any golden (verified: no `usage:` anywhere). This is the ONLY
   tool-identity leak, and it breaks byte-identical differential comparison.

**Resolution (RATIFIED, Tobi 2026-07-28):** `rigc` banners itself
honestly (`generated by rigc`); the golden COMPARISON normalizes exactly the
banner token, only when the module under test is not `rigexp` — the goldens
themselves stay frozen bytes. When `rigc` becomes THE tool, one justified
refreeze rewrites the banner class (58 goldens, one wording class, nothing
else). Rejected alternatives: `rigc` emitting `rigexp` in its banner (a
generated file lying about its generator, forever); refreezing the goldens
during the differential period (destroys the oracle rigexp validated
against).

### R0 acceptance

- Gate green with the knob unset AND with `RIG_EXPAND_COMPILE=rigexp` set
  explicitly — byte-identical goldens, no churn, proving the default path is
  unchanged.
- With a stub `scripts/rigc/` package that exits non-zero: the suite under
  `RIG_EXPAND_COMPILE=rigc` goes RED in BOTH halves — direct expander tests
  AND build-marked tests — proving the knob reaches both invocation sites.
- Touch a `scripts/rigc/*.py` file between two build-test runs under
  `module=rigc` and observe configure retrigger — proving the glob followed.
- `rerun.sh` and the VERBOSE render name the module actually run.

## 4. The TDD arc after R0 (shape ratified; slices get their own briefs)

The loop, per capability: pick red goldens → write the capability's unit
tests (they define the value-shaped contract, §6) → implement → the goldens
flip green under `module=rigc` → diff both implementations' output when
anything is surprising. The progress metric is the frozen suite's pass count
under `rigc`; the 43 rejects are an executable checklist.

Recommended slice order follows the data flow — CLI/diag rendering skeleton,
loader (document shapes, axis declarations, revision resolution), shield
library, analyzer capabilities (controller identity, CS allocation, address
allocation, net identity, params), emitter artifacts — but each slice is
briefed separately when dispatched; this brief deliberately does not
pre-specify their contents.

## 5. Definitions that carry over (ratified 2026-07-28)

- **A unit test uses NO subprocess.** Reaching code through the CLI front
  door makes a test integration by definition.
- **A reject is not a unit concern.** A reject is an outcome against a
  SCENARIO; scenarios do not exist at unit level. Rejects live in
  `tests/integration/`, always. The unit layer is NEW coverage of a
  different subject, not a duplicate of the reject corpus.
- **Hermetic-and-fast is the COST axis, not the unit boundary.** rigexp's 39
  fixture-only rejects are hermetic AND integration, simultaneously.
- Benchmark: rigexp's `-m unit` is 4 tests in 0.50s, subprocess-free.
  `rigc`'s unit suite stays in that regime as it grows.

## 6. Testable design — the enforceable form

`unit-test-layer-brief.md` (retitled ANALYSIS) is the direct input. Its
measured evidence: 20 of rigexp analyzer.py's 23 functions take the mutable
`solved` accumulator and/or `diags`; only four are value-shaped.

**Three unit-test-hostile shapes, banned in `rigc`:**

1. a mutable accumulator threaded in and written to (`solved`);
2. whole-model inputs (`rig`) where a value would do;
3. diagnostics as a side channel (`diags`) rather than part of the return.

Diagnostics are RETURN values composed upward, not a channel written into.

**The `cs-gpios` acid test:** "where and how is the final `cs-gpios`
property calculated?" must be answerable by reading the tests. The worked
example of the contract hiding inside rigexp's `_allocate_cs(rig, solved,
types, diags)`: *given an ordered pool, the taken positions, and the members
of one SPI scope (some copper-fixed), assign a position to each, or report
the pool exhausted.* That is a value-shaped function signature; `rigc`
writes it that way from the start.

**Unit test modules NAME THEIR UNIT** (Tobi's ruling 2026-07-28, made
reviewing R1 — SUPERSEDES the earlier capability-naming rule from the
unit-test-layer analysis): `test_<module>.py` mirrors the production
module, so a human reviewer relates test code to code under test by NAME
(`test_loader.py` ↔ `loader.py`). When one unit needs several test
modules, they live in a sub-folder `tests/unit/<module>/` that itself
names the unit. Tests may USE other units, but the named unit must be the
SUBJECT. The capability story moves INSIDE the module — docstrings,
section headers, test names — so the `cs-gpios` acid test is still met:
the answer to "where is X computed" is the section of `test_analyzer.py`
(or the module in `tests/unit/analyzer/`) that names X. Enforced
structurally by rigc's layer-discipline test.

**The stable-contract test** decides what gets a unit test: would you want
this contract preserved if the implementation were rewritten? Qualifies —
revision normalization, position indices, build recipe, controller
identity, CS allocation, address allocation, net identity. Does not — a
rejection branch structure, a delta key dispatch, diagnostic wording (that
belongs to the emitted goldens).

## 7. Constraints and machinery

### edtlib access

`devicetree` is NOT a pip package here — it lives at
`zephyr/scripts/dts/python-devicetree/src`, located via `$ZEPHYR_BASE`.
**Pip-vendoring is REJECTED, durably:** the workspace zephyr carries two
non-upstream edtlib patches (`feb51fa0f70` *-cells precedence,
`c0025d3692a` vendor-namespaced binding keys) a pip release would lack.
Revisit only once both land upstream AND appear in a release.

So for `tests/unit/`: **hermetic means no Zephyr DATA** (no real board
`.dts`, no production bindings, no build), NOT "no `$ZEPHYR_BASE`". Prove it
structurally — `rigc`'s equivalent of `conftest.assert_fixture_local()`
checking the paths handed to edtlib — never by the variable's absence. And
keep `$ZEPHYR_BASE` lookups OUT of module scope: pytest imports every module
before `-m` deselects, so a module-scope lookup breaks collection for
selections that would never run it (rigexp has this at `dtsio.py:27`; it is
why rigexp's `-m unit` still cannot run without a Zephyr tree — design it
out, do not inherit it).

### Fixtures

**Copy as-is** from the landed `7e35f33` tree (`fixtures/boards/{mainboards,
shields,rigs/<case>}`, `fixtures/dts/bindings/connectors/`,
`fixtures/include/dt-bindings/connector/`) — copy, not share: the frozen
suite must keep its own fixtures untouched to stay an oracle, and the
finding below makes cross-suite sharing structurally unsafe anyway.

**Fixture shields are CASE-SCOPED by construction** — only 1 of 10 is
genuinely shared. Two independent forces pin the rest: `load_shield_library`
reports malformed members at scan time unconditionally (so one deliberately
broken fixture poisons every test scanning its root), and `RIG_DEPENDS`
lists every SCANNED shield (so a sibling pollutes accept goldens). `rigc`
expects per-case shield roots as the NORM, expressed by LOCATION
(`boards/rigs/<case>/shields/<name>/`), never by a directory-name suffix.
Both forces are §2 "reproduce first, revisit after" items.

### Machinery to inherit rather than reinvent

- **`dts_equiv` as the refreeze oracle** — the RESOLVED tree licenses
  re-freezing an EMITTED golden; keep the `emitted`/`resolved` naming.
- **`assert_fixture_local()`** — structural hermeticity proof. The directory
  split is stronger than a marker, but the enforcement must still exist or
  the boundary decays exactly as it did in rigexp.
- **Marker/layer discipline enforcement** (`test_marker_discipline.py`) —
  from a pre-deselection census so `-m unit` cannot hide a violation; in
  `rigc` it additionally asserts the DIRECTORY split (no unit test outside
  `tests/unit/`, nothing subprocess-driven inside it).
- **`rerun.sh` per invocation + argv logging** (T2) — what makes a
  subprocess-driven suite debuggable.
- **`markers.sh` / `--markers-report`** and `timing_report.py`'s
  share-of-total baseline (rigexp's: 97% of ~206s is the 81 build-marked
  tests).

## 8. Target zephyr

`rigc` targets **`tiacsys/tskr/zephyr-rigs`**. For the duration of the rigc
build, `btr-shields/west.yml` is PINNED to that branch's 2026-07-28 tip,
**`8da5b3a0f60f7e8e06aa7b99bde818bb1affe2bd`** (Tobi's ruling, §9.3 — any
red golden during the differential period is then OURS by construction).
Un-pinning back to the branch name is a deliberate step at cutover; the
long-term intent is unchanged — the tiacsys base is what we want, not a
frozen snapshot.

The consequence has now bitten AND been handled once (`ae7b92b`): the branch
gets rebased, and an upstream SoC/board change legitimately reddens resolved
goldens with no local change. **A red resolved golden after a zephyr update
is the EXPECTED shape of upstream churn, not a regression.** Diagnose by
classifying the `dts_equiv` diff first: every changed node SoC/board-owned
and nothing rig-owned moved → justified refreeze; any socket, shield,
instance or generated node moved → it is not. This is also why resolved
goldens stay STRUCTURAL (`dts_equiv`, never a byte diff).

## 9. Decisions — all RULED by Tobi, 2026-07-28

1. **The banner plan — RATIFIED as recommended.** `rigc` banners itself
   (`generated by rigc`); comparison-time normalization of exactly that
   token during the differential period; one justified banner refreeze
   (58 goldens, one wording class) at cutover.
2. **Knob name — `RIG_EXPAND_COMPILE`** (Tobi's spelling, superseding the
   driver's `RIG_EXPAND_MODULE`). Same name as cmake cache variable and
   test-side env var; default `rigexp`; the value is a Python module name.
3. **Pin the zephyr hash — YES, pinned.** `west.yml` pins
   `8da5b3a0f60f7e8e06aa7b99bde818bb1affe2bd` (the 2026-07-28
   `tskr/zephyr-rigs` tip the current gate validated against) for the
   differential period. Un-pin at cutover, as a deliberate step. The trade
   accepted: a frozen substrate for the whole build; upstream currency
   resumes after.
