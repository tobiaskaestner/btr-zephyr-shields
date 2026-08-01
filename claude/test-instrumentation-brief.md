# Slice brief — test suite instrumentation: timing, coverage, unit/integration split

Requested by Tobi 2026-07-27. Three asks, one slice family: track test execution
times, extract coverage information, and split the suite cleanly into UNIT
(synthetic fixtures, nothing outside `scripts/rigexp/` bar edtlib/dtlib) and
INTEGRATION (uses `btr-shields/boards/rigs`), with coverage reported against
the two suites INDEPENDENTLY.

## Measured baseline — real numbers, not estimates

Taken at HEAD `bc63b50` (S2 landed), with the S2 test-gap fixtures partly in
flight, so counts drift upward slightly:

| | tests | wall time |
|---|---|---|
| full gate | 135 | ~206 s |
| `-m build` | 81 | ~200 s |
| `-m "not build"` | 62 | **5.33 s** |

**97% of gate wall-clock sits in 81 tests.** The slowest non-build test is
0.26 s; the non-build suite as a whole is under six seconds. Per-file
build-marked collection: `test_board_read` 12, `test_cmake_alone_entry` 11,
`test_tier1_goldens` 27, `test_tier2_goldens` 31.

So a fast inner loop already exists in practice (`CHECK_FAST=1`). What it does
NOT have is a principled definition, per-suite attribution, or any guard
against a "fast" test quietly acquiring a board dependency. That last one is
the real prize — see the enforcement criterion below.

## DECISION 1 — RESOLVED by Tobi 2026-07-27: move what unit tests need INTO the fixture tree

Tobi's ruling supersedes the analysis below rather than picking a side in it:
**whatever a unit test needs gets moved into the in-tree fixture**, because
eventually only the unit tests travel easily. That dissolves the conflict —
once the board dependency lives in the fixture tree, "synthetic fixture" and
"needs nothing outside rigexp" select the SAME set.

It also matches the migration's own content triage, which already designates
synthetic fixtures as the category that travels while the corpus rigs do not,
and it is what makes the BSD-3 `edt_build.py` reader upstreamable to
python-devicetree WITH its tests.

**The precedent already exists and is half-built.**
`fixtures/controller-label/socket.dts` is a standalone synthetic board with a
typed socket node and a shared controller, driven by `test_controller_label.py`
with no build at all. But it is fast, NOT hermetic: its recipe pulls bindings
from `$ZEPHYR_BASE/dts/bindings` AND `REPO_ROOT/dts/bindings`, and its DTS
`#include`s `<dt-bindings/connector/grove.h>` from `REPO_ROOT/include`.

So the board half is solved and the vocabulary half is not. Closing it needs
three things in the fixture tree:

1. A **synthetic board `.dts`** referencing only fixture-local compatibles
   (`socketless_board.dts` and `socket.dts` are the two working models).
2. A **synthetic connector-type binding**, which must NOT `include:` Zephyr's
   `base.yaml`/`gpio-nexus.yaml` — every real connector binding does
   (`arduino-r3`, `mikrobus`, `grove`: `[gpio-nexus.yaml, base.yaml]`;
   `i2c-port`: `[base.yaml]`), and that include chain is the whole remaining
   dependency on the Zephyr tree. Declaring the nexus properties INLINE is
   already proven in-repo: `grove.yaml` had to do exactly that for
   `pwm-map`/`io-channel-map`, because dtschema `include:` cannot downgrade an
   included property's `required: true`.
3. A **fixture-local index header** for the synthetic connector's positions.

**THE HAZARD, and the ruling that avoids it: fixtures must NOT be copies of
the real connector types.** A copied `grove.yaml` in the fixture tree can
drift from the real one, and then the unit suite passes green against a stale
contract — worse than no coverage, because it reads as coverage. Author
PURPOSE-BUILT synthetic connector types instead (`socket,fixture-*`). Unit
tests then exercise expander LOGIC against a synthetic vocabulary, and the
real connector definitions keep their own coverage in
`test_connector_bindings.py`, which edtlib-validates all four real files and
is the only coverage `i2c-port.yaml` ever gets. Separate concerns, no
duplication, nothing to drift.

**What moves and what does not — the move set is SMALL.** Of the 27
build-marked tier-1 tests, **17 are `test_tier1_golden[case]` (corpus
parametrization) and 6 more are corpus rigs** (`pilot_variant_*`,
`pilot_revision_2`, `shield_rev_family_revision_2`, `ard_datalogger_frdm`).
All 23 STAY: they exist to prove real boards work, and a synthetic board would
delete their purpose. (An earlier note in this brief said "~27 tests become
integration" — that overstated it by counting the corpus parametrization.)

Only FOUR are fixture-based, plus two already-synthetic:
`test_controller_label` (2, synthetic board already — only its bindings are
non-hermetic, so it is the cheapest proof of concept), `unmapped_socket`,
`pwm_nonzero_flags`, and the two `shield_uart_subset` halves.

**The governing rule is per-test, not blanket: move a test only where the real
board is INCIDENTAL to what it proves.** `shield-uart-subset` is expected to
STAY on that rule — its point is that two REAL hosts differ (`nucleo_ard`
exposes no `socket,uart`, `frdm_ard` has `uart3`), and a synthetic pair would
drop precisely the evidence it exists to freeze.

**Cost:** a synthetic board + connector binding + header, four-ish tests
re-pointed, and their goldens regenerated — a justified refreeze, since
resolved pins move from real controllers to synthetic ones.

**One obstacle:** `conftest.normalize()` calls `zephyr_base()`, which raises
when `ZEPHYR_BASE` is unset, so every golden-comparing test needs the variable
even when nothing else does. It is called lazily, so collection is fine;
`normalize` just needs to skip that one substitution when the variable is
absent.

**A benefit worth having independently of travel:** today a fixture reject's
golden embeds `nucleo_ard`, `&gpiob 6`, and paths into
`boards/extend/st/nucleo_f401re/`, so editing the nucleo extension can churn
goldens of tests that have nothing to do with nucleo. That is the same
coupling that once silently staled 152 tier-2 provenance references from a
single comment rewrap. A synthetic board decouples them permanently.

## Superseded analysis — why the decision was needed at all

The request gives two definitions of UNIT, and they disagree:

- **(a) by data source** — synthetic fixtures are unit, `boards/rigs` is
  integration.
- **(b) by dependency** — "requires nothing outside of the rigexp folder (with
  the exception of the edtlib/dtlib code)".

They diverge because of THE FLIP. Since the expander reads the REAL board DT
via edtlib, a test can run on a purely synthetic fixture and STILL need
`boards/extend/*`, `dts/bindings/connectors/*`, and a cached configured board
build — that is exactly what the 27 build-marked tests in `test_tier1_goldens`
are. Under (a) they are unit; under (b) they cannot be.

The reverse case is harmless: `test_corpus_rig_identity` reads `boards/rigs`
and needs nothing else, and is integration under both readings.

Earlier recommendation, NOT taken: make (b) primary and let the ~27
synthetic-fixture tier-1 golden tests become integration. Tobi's ruling above
is better — it removes the dependency instead of reclassifying the tests
around it, and it buys portability that reclassification would not.

## OPEN DECISION 2 — two markers on one axis, or keep `build` as a second axis

`build` already exists and `CHECK_FAST=1` depends on it. It encodes "runs
west/cmake", which is NOT the same question as "is hermetic".

**Recommendation: keep both, on separate axes.** Add `unit` / `integration` as
the dependency axis; leave `build` as the orthogonal "spawns a real build"
axis. Then `-m "integration and not build"` stays expressible, `CHECK_FAST`
keeps working unchanged, and the two concepts never have to be reconciled into
one ordering.

## The coverage blocker — read this before estimating the slice

**Every expander invocation is a SUBPROCESS.** `conftest.py:357` builds
`[sys.executable, "-m", "rigexp", "expand", ...]` and runs it at `:371`; the
cmake-driven path at `:302` adds a second layer through west and cmake. This
is deliberate (the harness runs the expander exactly as `dts.cmake` does), and
it is not going to change.

Consequence: **in-process coverage measures the test harness, not the
expander.** A naive `coverage run -m pytest` would report near-zero on
`loader_yml`, `analyzer`, `emitter` — the modules the suite exists to exercise
— and the number would look plausible enough to believe. Any coverage work
that does not solve this produces confidently wrong data, which is worse than
no data.

What it takes:

- `coverage run --parallel-mode`, so each process writes its own data file.
- `COVERAGE_PROCESS_START=<rcfile>` exported into the subprocess environment
  (`conftest.py` already builds an explicit `env` for both runners, so this
  threads through naturally).
- `coverage.process_startup()` called at interpreter start in the child. The
  usual mechanism is a `.pth` in site-packages — **that mutates the shared
  venv and should be avoided**. Prefer a repo-local `sitecustomize.py` placed
  on the child's `PYTHONPATH` by conftest: same effect, reversible, and
  visible in the repo.
- `coverage combine` per suite before reporting.

**Acceptance must PROVE instrumentation works, not assume it:** introduce a
deliberately unreachable branch in an expander module and confirm it shows as
uncovered, and confirm the expander's own modules report non-trivial
coverage. A coverage run that silently measured only the harness is the
failure mode to design against.

## Tooling — no new dependency needed

`coverage` 7.14.1 is installed in the workspace venv; **`pytest-cov` is NOT**.
Drive `coverage` directly (`coverage run -m pytest ...`) rather than adding
pytest-cov: it keeps the pinned venv untouched, and `--parallel-mode` +
`combine` is the supported path for subprocess coverage anyway.

Per-suite separation via distinct data files:

```
coverage run --parallel-mode --data-file=.coverage.unit        -m pytest -m unit
coverage combine --data-file=.coverage.unit        .coverage.unit.*
coverage report --data-file=.coverage.unit
# and the same for integration
```

## T2 also carries COMMAND VISIBILITY (Tobi, 2026-07-27)

Paired into T2 because both are harness instrumentation and both touch the
same runner functions in `conftest.py`.

**The problem.** `-s` cannot show you what a build test actually ran. The
harness captures subprocesses programmatically —
`subprocess.run(..., capture_output=True)` at `conftest.py:352` and `:440` —
because assertions inspect `result.stdout`. `-s` only stops PYTEST capturing
the test process's own stdout; it has no effect on output a subprocess handed
back as a string. So `print()` alone does not solve this.

**Verified gap, and it is worse than the ergonomics issue:** NO assertion
anywhere in the suite interpolates the argv. A failing build test shows
stdout and stderr but never the command that produced them. Fix that
regardless of the rest.

Three parts, all ratified:

1. **`logging.info` the argv** at each invocation point. Visible with
   `--log-cli-level=INFO`, silent otherwise, and needs no `-s` — which
   matters because `-s` is exactly what a person forgets.
2. **Write an executable `rerun.sh` into the test's tmp dir**, mirroring the
   in-repo precedent: `cmake/dts.cmake` already writes
   `<build>/rig/rerun-expand.sh` on every configure and deliberately keeps it
   after a FAILED configure, so the expander can be replayed alone. Same idea
   one level up. This beats printing because the result is something you RUN,
   not something you read and retype with the right quoting.
3. **Put the argv in the failure assertions**, alongside the stdout/stderr
   they already interpolate.

**Composes with tmp-dir retention**, which is the other half of the ask.
pytest 9 has `tmp_path_retention_policy` (`all`/`failed`/`none`, default
**`failed`** — so failing tests' dirs are ALREADY kept) and
`tmp_path_retention_count` (default 3 sessions). Verified that
`-o tmp_path_retention_policy=all` keeps a passing test's dir. Recommend NOT
changing the default in `pyproject.toml` — keeping every build dir from a
146-test run costs real disk — and using `-o` ad hoc instead, documented
next to the `rerun.sh` feature since the two are used together:

```
pytest <nodeid> -o tmp_path_retention_policy=all
# then run <tmpdir>/rerun.sh
```

`--basetemp=<dir>` pins the location, but note its own warning: that
directory is DELETED at startup, so never aim it at anything that matters.

## T2 also carries: make `--markers-report` filter-aware

`scripts/markers.sh` / `--markers-report` scope correctly by PATH (file,
directory, node id) but **silently ignore `-k` and `-m`** — both are accepted
and then discarded, returning all 146 rows. Measured:

| scoping | rows |
|---|---|
| file path | 1 |
| node id | 1 |
| `-k dual_host` | 146 |
| `-m unit` | 146 |

Cause: `-k` and `-m` deselect inside `pytest_collection_modifyitems`, and the
report is emitted from a `tryfirst` hook that deliberately runs AHEAD of that
deselection. That is the same property `test_marker_discipline.py` depends on
— it is what stops `pytest -m unit` hiding a module that mixes markers — so
the pre-filter census must NOT be filtered.

The script's usage comment claimed `-k` worked; corrected in the commit that
records this, together with why.

**The fix for T2: two consumers, two lists.** Keep the census pre-deselection
for the enforcement test, and emit the REPORT from the post-deselection item
list. Silently ignoring a flag you accepted is the worse failure mode — a
reader concludes `-k` matched nothing rather than that it was discarded.

## RATIFIED (Tobi, 2026-07-28) — what a unit test is, and what T3 therefore needs

**A unit test uses NO subprocess.** Two reasons, and the second is the
governing one: debugging into a subprocess is fragile to set up, and reaching a
unit through the FRONT DOOR (the CLI) has already made it an integration test.

**A reject is not a unit concern at all.** A reject is an OUTCOME against a
specific SCENARIO, and scenarios do not exist at the unit level — they are
consumed at the system level (`rigexp`, later `rigc`). So the unit layer does
NOT duplicate the reject corpus; it is new coverage of a different subject.

**Coverage interest is UNIT coverage:** that every code path has executed and
each unit meets its specification. Integration tests then rely on those
guarantees and cover workflows and scenarios.

### Measured consequence: there are THREE unit tests, not 44

| module | unit-marked | reaches code via |
|---|---|---|
| `test_emitted_rejects` | 39 | 40 × CLI subprocess, ZERO in-process imports |
| `test_reference_shields` | 1 | 2 × CLI subprocess |
| `test_controller_label` | 2 | in-process (`board_edt`) — a real unit test |
| `test_edt_build` | 1 | in-process (`edt_build`) — a real unit test |
| `test_marker_discipline` | 1 | tests the harness, not the product |

Forty of the 44 drive `python -m rigexp expand` and assert on rendered stderr:
the whole CLI/loader/analyzer/emitter pipeline, which is a workflow.

### This dissolves most of T3

The elaborate subprocess-coverage design (`--parallel-mode`,
`COVERAGE_PROCESS_START`, a repo-local `sitecustomize.py`, `coverage combine`,
and the `pytest-cov`-versus-hand-rolled question) existed ONLY to measure
coverage through the CLI. Under this ruling that is the integration suite,
where coverage is not the priority. Unit coverage is then just:

```
coverage run -m pytest -m unit && coverage report
```

No subprocess plumbing, no new dependency, nothing vendored.

### Revised plan

1. **Reclassify** `test_emitted_rejects` and `test_reference_shields` as
   INTEGRATION. Cheap — module-level `pytestmark`. `-m unit` becomes genuinely
   subprocess-free and debuggable, and honestly reports 3 tests.
   **Keep them, do not delete:** they freeze user-facing diagnostic WORDING,
   a real contract and a different property from "the rule fired".
2. **Build the unit layer** — its own brief, the real work. In-process tests of
   function contracts.
3. **T3 measuring `-m unit`**, now nearly trivial.

### OPEN DESIGN QUESTION for step 2: what is the unit?

Not settled. Two candidate boundaries:

- **(a) the module's public entry point** — `loader_yml.load()`,
  `analyzer.analyze()`, `emitter.emit()`. Robust against refactoring, but
  `load()` already resolves shields and mates connector types, so it is
  coarse enough to be scenario-shaped — arguably the thing this ruling says is
  NOT a unit.
- **(b) the smallest function with a stateable contract**, including private
  helpers: `_normalize_revision`, `_check_axis_collision`, `_parse_axis_decl`,
  `_resolve_board`, `_load_delta_doc`, `_apply_delta`,
  `parse_header_indices`, `recipe_from_build_info`, `_controller_label`.
  Data in, data out; reachable without a board or a build.

Recommendation: **(b)**, since it is what "every code path executed" actually
requires, and the two existing real unit tests are already at that grain
(`_controller_label`, `recipe_from_build_info`). Cost to accept: unit tests
then couple to internals, so a refactor legitimately updates them — mitigate by
asserting the CONTRACT, not the implementation. Some helpers take `diags` and
`_Val` wrappers, so a little test scaffolding is needed; that is normal.

## Timing

pytest already has `--durations`; what is missing is persistence.

- Print `--durations=25` on every gate run — free, immediately useful.
- Write `--junitxml` per suite for the machine-readable per-test wall times.
- A small script to diff a run against a stored baseline and flag regressions
  past a threshold.

**Constraint, learned the hard way:** never write reports into a build `-d`
directory — `-p always` wipes them (memory `feedback_build_dir_not_durable`).
Put them under a gitignored repo-local report dir.

**Baselines are machine-dependent.** A committed absolute-seconds baseline
would be noise across machines. Prefer relative signals — share of suite
total, and the slowest-N table — or keep the baseline file local and
gitignored.

## Enforcement — the criterion that makes the split real

A marker alone decays. Today nothing stops a new test marked `unit` from
calling `plain_build_for` and quietly costing three minutes.

Add a test that FAILS if any `unit`-marked test reaches a board or build
helper.

**SUPERSEDED — the `ZEPHYR_BASE`-unset criterion this section originally
proposed is unachievable, and T1 shipped a better one.** It was: "`-m unit`
green with `ZEPHYR_BASE` unset". That cannot hold, for two independent
reasons:

1. Some unit tests BUILD AN EDT (`test_controller_label`,
   `test_reference_shields`), and `devicetree` is not a pip package — it lives
   only in the Zephyr tree, so `ZEPHYR_BASE` locates the very library the
   hermeticity rule exempts. See DECISION 1 and the T0 outcome.
2. Even for tests that do not, pytest must IMPORT every test module to
   discover its markers before `-m` can deselect anything. Three
   integration-only modules (`test_board_read`, `test_connector_bindings`,
   `test_controller_label`) import `rigexp.board_edt`/`rigexp.dtsio` at module
   scope, and `board_edt.py:28` calls `ensure_devicetree_on_path()` eagerly at
   import. So `-m unit` with `ZEPHYR_BASE` unset dies at COLLECTION, in
   modules that `-m unit` was never going to run.

**What T1 shipped instead, and it is stronger:** `test_marker_discipline.py`
asserts (a) no module yields both markers and (b) every test carries exactly
one, reading a pre-deselection census from a `tryfirst` collection hook so
`pytest -m unit` cannot hide a violation. Hermeticity itself is proved
structurally per test by `conftest.assert_fixture_local()`, which checks the
paths a test actually hands to edtlib — a property of what it READS rather
than of how it was invoked.

Worth a small cleanup regardless (NOT a blocker): reason 2's eager import
means a missing `ZEPHYR_BASE` surfaces as a collection explosion rather than a
clear error from the tests that genuinely need it. Deferring
`ensure_devicetree_on_path()` out of `board_edt`'s module scope — the same move
T0c made in `edt_build` — would turn that into a runtime failure in exactly
the tests that need the library, which is the honest signal.

## Slicing recommendation

- **T0 — the hermetic fixture vocabulary. LANDED `1a6638f`.** See "T0 outcome"
  below: the vocabulary exists, two tests moved, and the slice found a hard
  ceiling that reshapes T1.
- **T0b — configurable connector roots + a reference shield set.** RATIFIED
  by Tobi 2026-07-27, sequenced BEFORE T1 so the split is marked where we want
  the line, not where today's hardcoding forces it. Two halves:
  1. **Plumbing.** `ctypes_registry.BINDINGS` and the header root in
     `dtsio.parse_header_indices` become configurable. **Ratified design:** ONE
     new repeatable `--connector-dir` for the type YAMLs; the `<type>.h`
     headers resolve against the EXISTING `--include-dir` list, first match
     wins, exactly as cpp resolves `#include <dt-bindings/connector/x.h>` —
     no second new flag, and it reuses plumbing the CLI already has. Resolve
     the registry ONCE at CLI entry and pass it down; `shields.py` already
     takes `types` as a parameter and is the pattern to follow. Six call sites
     (`loader_yml:354`, `analyzer:80`, `emitter:92/419/429/449`) — and the
     emitter's four re-globs of the whole connector tree per run go away as a
     side effect.
  2. **The reference set.** Today's nine fixture shields are ANTI-examples,
     named for the defect they trigger. Add exemplary ACCEPT material a real
     shield author can copy: a registry-complete synthetic connector type
     (`plug,positions`, `plug,bus-proxies`, socket facts, plus its header) and
     two or three shields covering the main patterns — fixed-address bus
     device, CS-position device, GPIO collection, parameterized device. They
     must be built END TO END, because a reference implementation that is not
     exercised is documentation, and documentation drifts.

  **Honest limit to record with them:** a synthetic reference proves the SHAPE
  is right, never that real silicon agrees — it could not have caught the sam0
  two-cell PWM bug, which only surfaced against a real binding. The corpus
  rigs remain the proof that real hardware works.

- **T0c — `run_cpp` include path (NEW, blocks the reference set's purpose).**
  `dtsio.run_cpp` (`dtsio.py:59`) hardcodes `-I ZEPHYR_INC -I MODULE_INC`
  when preprocessing a `.shield`, entirely separate from the CLI's
  `--include-dir`. So a fixture `.shield` cannot `#include` a fixture-tree
  connector header, and T0b's reference shields had to hardcode positions
  (`<&fb_plug 2 0>`, `shield,cs-position = <4>`) with the macro name in a
  comment. That INVERTS Convention 4 — a real shield writes
  `ARDUINO_HEADER_R3_D7`, and the header being the position-index single
  source of truth is the entire point. A reference implementation that
  teaches the wrong idiom is worse than none. **Fix: `run_cpp` takes the
  same `--include-dir` list the connector-header resolver already uses** —
  consistency with T0b's own ratified decision, not new surface. Small,
  and it is what makes the reference set and refactor Part D worth having.
- **T1 — the split.** Add `unit`/`integration` markers, classify every test,
  keep `build` orthogonal, add the enforcement criterion. NO coverage, NO
  timing. Provable by collection counts plus `-m unit` passing with
  `ZEPHYR_BASE` unset; a clean bisect point before any tooling lands.
- **T2 — timing.** `--durations` always on, junitxml per suite into a
  gitignored report dir, the baseline-diff script.
- **T3 — coverage.** The subprocess work above, per-suite data files, and the
  proof-of-instrumentation acceptance. Depends on T1 for the suite names.

T0 then T1: T3 cannot report "per suite" until the suites exist, T1 cannot
classify honestly until T0 has removed the dependency, and T0 has standalone
value (decoupled goldens, a portable fixture tree) even if the rest slips.

## Sequencing against the rig queue

Independent of the feature queue; it can run at any point. Two soft
constraints:

- **Before the bridle migration** — the tests move there, and a split done
  afterwards rewrites freshly condensed history (the same argument that put
  the metadata/content split ahead of the migration).
- **Ideally before hwmv2 revision semantics**, so that slice gets per-suite
  coverage feedback while touching `_parse_axis_decl` — but this is
  preference, not a dependency.

No conflict with `conftest.py`'s recent S2 changes now that S2 has landed.

## T0 outcome (LANDED `1a6638f`) — and the ceiling that reshapes T1

**Built:** `tests/fixtures/connectors/{bindings,include}` — a purpose-built
`socket,fixture-nexus` binding with every nexus property declared INLINE and
no `include:` at all, plus its own position header. Inline is what severs the
last Zephyr tie, since every real connector binding pulls
`gpio-nexus.yaml`/`base.yaml` from there.

**"Hermetic" was REDEFINED mid-slice, and the correction matters.** The
original criterion — passes with `ZEPHYR_BASE` unset — is unattainable for any
test that builds an EDT: `devicetree` is not a pip package, it lives only in
the Zephyr tree, so `ZEPHYR_BASE` is the sole locator for the very library the
rule exempts. **Pip-vendoring it is REJECTED on evidence:** this workspace's
zephyr branch carries two edtlib patches that are not upstream
(`feb51fa0f70`, `c0025d3692a`), so a pip package would silently diverge from
what production runs. Revisit only once both land upstream AND appear in a
release — at which point the unit suite could become genuinely standalone.

The working criterion is **NO ZEPHYR DATA** (no Zephyr bindings/includes, no
real board `.dts`, no cmake/west build, no repo-production devicetree
content); `ZEPHYR_BASE` may be set purely as the library locator. Proven
structurally by `conftest.assert_fixture_local()`, which checks that every
path a test hands to edtlib resolves under the fixture tree — a property of
what the test READS, not of how it was invoked. Verified to reject a Zephyr
path and accept a fixture one.

**Moved:** `controller-label` (synthetic bindings + header) and
`unmapped-socket`, which drops `@pytest.mark.build` entirely. One golden
changed, one class. `test_edt_build.py` now passes with `ZEPHYR_BASE`
literally unset; `test_controller_label.py` still needs it at collection,
because it builds an EDT — that is the honest boundary the corrected
criterion draws.

**THE CEILING — `ctypes_registry.BINDINGS` is hardcoded.** It is a
module-level constant pointing at `dts/bindings/connectors`, and
`load_types()` globs it with no override, so a shield can only MATE against
one of the four real connector types. Any test whose shield must mate cannot
go hermetic: a synthetic type is rejected as an unknown connector type, and
reusing a real one drags `gpio-nexus.yaml`/`base.yaml` back in. This blocks
`pwm_nonzero_flags` and any synthetic twin of `shield_uart_subset`.

**Consequence for T1:** the unit suite's reachable extent is "tests that do
not mate a shield" until `ctypes_registry`'s bindings directory becomes
configurable and is threaded through `cli`/`loader_yml`/`analyzer`/`emitter`.
That is a cross-cutting production change, deliberately NOT done in T0.
Decide before T1 whether to do it first (raising the ceiling, and worth it if
the unit suite is meant to carry real expander coverage) or to mark the split
at today's line and accept that shield-mating tests are all integration.

## Still unresolved, non-blocking

`test_connector_bindings.py` edtlib-validates the four real
`dts/bindings/connectors/*` files and is the only coverage `i2c-port.yaml`
ever gets. Under decision 1 it is unambiguously INTEGRATION — it exists to
check real repo content, and that is now exactly the job the unit suite hands
off to it. Recording it here only because it looks like a unit test by speed
(sub-second, no build); it is not one by purpose.

`test_edt_build.py` (the BSD-3 reader, the upstream candidate for
python-devicetree) is the one genuine boundary case left. It should be UNIT if
anything is, since it is the piece most likely to travel on its own — but it
currently reads outside `scripts/rigexp/`. T0 should pull whatever it needs
into the fixture tree along with the rest, and if that turns out to be
expensive, that cost is itself the answer to whether the reader is really
separable. One ruling needed; nothing else depends on it.
