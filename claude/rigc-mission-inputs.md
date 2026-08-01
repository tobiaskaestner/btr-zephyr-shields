# `rigc` mission — ratified inputs

Captured 2026-07-28, at the end of the session that froze rigexp. **This is
NOT the mission brief.** It is the record of what was already decided, so the
brief can be written from evidence rather than reconstructed from a
conversation. Writing the brief is the new session's first job.

## The mission, as ratified

- **rigexp's production code is FROZEN.** It will not be touched again.
- rigexp — **including its tests** — is the **BLUEPRINT** for building `rigc`
  from scratch, in **proper TDD style**.
- `rigc` lives in **its own `scripts/` subfolder** (`scripts/rigc/`), with
  **`tests/unit` and `tests/integration` subdirectories**.
- The **loader / analyzer / emitter** decomposition stays. What changes is that
  **testable design gets the attention it did not get the first time**.

## First steps, ratified

1. **Parameterise the expander module name, do not copy-and-substitute.**
   RATIFIED: a **cmake variable** for the module name (default `rigexp`), plus
   the equivalent constant on the test side. Then the existing frozen
   integration suite runs against `rigc` by flipping one value.

   Why this rather than copying first: it gives a **differential harness**
   during development — the same goldens, byte for byte, over both
   implementations, with the ability to diff them. Copy-then-substitute yields
   two suites that drift silently while `rigc` is still incomplete. `rigc`'s
   `tests/integration` becomes its own only once it passes green.

   **The substitution surface is exactly two sites**, and one is production
   cmake:

   | site | reaches |
   |---|---|
   | `conftest.py:480` — `[sys.executable, "-m", "rigexp", "expand", …]` | the direct expander tests |
   | `cmake/dts.cmake:347` — `"${PYTHON_EXECUTABLE}" -m rigexp expand …` | ALL 80 build-marked tests |

   The build tests have no test-side argv to swap; they reach the expander
   through cmake. Also `dts.cmake:336,379,386` and `conftest.py:252` carry the
   module name in debug-hint strings.

   **The plumbing already fits:** `PYTHONPATH` is `<repo>/scripts` in both
   places (`conftest.py:478`, `dts.cmake:130`), so `-m rigc` resolves the
   moment `scripts/rigc/` exists. No new path wiring.

2. **Fixtures copy as-is.** The canonical restructure LANDED as `7e35f33`:

   ```
   fixtures/
   ├── boards/
   │   ├── mainboards/      4 synthetic board .dts
   │   ├── shields/         shared fixture shields
   │   └── rigs/<case>/     44 case dirs, plus a case-local shields/
   ├── dts/bindings/connectors/
   └── include/dt-bindings/connector/
   ```

   The kind level is mirrored and nothing below it: real boards live at
   `boards/<vendor>/<board>/` with a `board.yml`, but fixture boards are passed
   via `--board-dts` and are not discoverable, so a flat
   `boards/mainboards/<name>.dts` is honest rather than inventing `board.yml`
   files nothing reads. Rigs DO match the real convention, one directory each.

   **FINDING worth designing around, not rediscovering: fixture shields are
   CASE-SCOPED by construction.** Only ONE of ten is genuinely shared
   (`restate_fixture`). The other nine are pinned to a single case by two
   independent forces:

   - three are DELIBERATELY malformed (`badyml_fixture`, `mapentry_fixture`,
     `misnamed_fixture`) and `load_shield_library` reports their defects at
     library-SCAN time, unconditionally, for every folder in `shield_dirs` — so
     a shared root poisons every other test that scans it;
   - `uart_probe`'s accept test freezes `RIG_DEPENDS` in `context.cmake`, which
     lists every SCANNED shield path whether or not the rig references it, so
     any sibling in the same root pollutes that golden.

   So `rigc` should expect per-case shield roots as the NORM and a shared
   library as the exception, and should express the scope by LOCATION
   (`boards/rigs/<case>/shields/<name>/`) rather than by a directory-name
   suffix. An earlier attempt encoded it as an `_only` suffix and produced two
   conventions in one directory.

   Both forces are worth revisiting in `rigc` rather than inheriting: a
   library scan that hard-errors on any malformed member makes isolation
   mandatory, and a dependency list that records scanned-but-unreferenced
   shields is arguably over-broad. Neither is a law of nature.

3. **Integration tests move mechanically** (per step 1). **Unit tests stay
   where they are and get RE-WRITTEN for `rigc`** — rigexp's four are not
   portable, because they test rigexp's internals.

## THE GOLDENS ARE THE SPECIFICATION

State this as the mission's primary conformance criterion rather than
discovering it later. The 43 reject goldens plus the emitted/resolved corpus
goldens are an **executable list of every diagnostic and every artifact `rigc`
must reproduce**. The TDD loop does not start from prose — it starts from bytes
that already exist and are known correct.

This works precisely BECAUSE of the subprocess policy that looked like a cost
earlier in the session: the integration tests only ever reach the expander
through the CLI front door, so they are coupled to the CONTRACT and not to the
implementation. That is what makes them portable to a different implementation
at all.

## Constraint `rigc` will hit early: how its tests reach edtlib

`devicetree` is NOT a pip package here — it exists only inside the Zephyr tree
at `scripts/dts/python-devicetree/src`, located via `$ZEPHYR_BASE`. So even a
hermetic unit test that builds an EDT needs that variable set, purely as the
library locator.

**Pip-vendoring it is REJECTED, and the reason is durable:** this workspace's
zephyr branch carries edtlib patches that are not upstream — currently
`feb51fa0f70` (`*-cells` binding-validation operator precedence) and
`c0025d3692a` (vendor-namespaced top-level binding keys). A pip release would
lack both, so tests would silently run against different edtlib behaviour than
production. Revisit only once both land upstream AND appear in a release.

Consequence for `rigc`'s `tests/unit`: hermetic means **no Zephyr DATA** (no
real board `.dts`, no production bindings or includes, no build), NOT "no
`$ZEPHYR_BASE`". Prove it structurally — the equivalent of
`conftest.assert_fixture_local()`, checking the paths a test hands to edtlib —
rather than by the variable being absent.

Related trap, worth designing out rather than inheriting: pytest imports every
test module to discover markers BEFORE `-m` deselects anything, so a
module-scope `$ZEPHYR_BASE` requirement breaks collection for selections that
would never have run it. rigexp has this at `dtsio.py:27` and it is why
`-m unit` there still cannot run without a Zephyr tree. Keep such lookups out
of module scope in `rigc`.

## Machinery to inherit rather than reinvent

- **`dts_equiv` as the refreeze oracle.** The two-tier relationship — the
  RESOLVED tree licenses re-freezing an EMITTED golden — is what made every
  refactor in this session safe. Keep the concept and the naming
  (`emitted`/`resolved`, which replaced the meaningless tier-1/tier-2).
- **`conftest.assert_fixture_local()`** — structural proof that a test reads
  only fixture-tree paths. `rigc` gets `tests/unit` as a DIRECTORY, which is
  stronger than a marker, but the enforcement still has to exist or the
  boundary decays the same way it did here.
- **Marker discipline enforcement** (`test_marker_discipline.py`) — asserts no
  module mixes unit and integration AND every test carries exactly one, from a
  pre-deselection census so `-m unit` cannot hide a violation.
- **`rerun.sh` per invocation** and argv logging (T2) — the debugging
  affordance that makes a subprocess-driven suite workable.
- **`markers.sh` / `--markers-report`**, and `timing_report.py`'s
  share-of-total baseline.

## Design inputs for the testable-design goal

`unit-test-layer-brief.md` is retitled as ANALYSIS and is the direct input
here. Its load-bearing content:

- **Three unit-test-hostile shapes, measured in rigexp — `rigc` should be built
  so none of them appear:** a mutable accumulator threaded in and written to
  (`solved`); whole-model inputs (`rig`) where a value would do; diagnostics as
  a side channel (`diags`) rather than part of the return. Evidence: **20 of
  analyzer.py's 23 functions** take `solved` and/or `diags`; only `_role_of`,
  `_soc_net` and two string formatters are value-shaped.
- **The `cs-gpios` acid test.** "Where and how is the final `cs-gpios` property
  calculated?" must be answerable by reading the tests. In rigexp the answer
  spans six sites in five modules, and `_allocate_cs(rig, solved, types,
  diags)` is a seam that exists BY NAME but not BY SHAPE. The value-shaped
  contract hiding inside it: *given an ordered pool, the taken positions, and
  the members of one SPI scope (some copper-fixed), assign a position to each,
  or report the pool exhausted.*
- **Unit test modules are named after the CAPABILITY**, not the production
  module: `test_cs_allocation.py`, not `test_analyzer.py`. "Where is X
  computed" is then answered by finding the module named for X.
- **The stable-contract test:** would you want this contract preserved if the
  implementation were rewritten? Qualifies — revision normalization, position
  indices, build recipe, controller identity, CS allocation, address
  allocation, net identity. Does not — a rejection branch structure, a delta
  key dispatch, diagnostic WORDING (that belongs to the emitted goldens).

## Definitions that carry over

- **A unit test uses NO subprocess.** Reaching code through the CLI front door
  makes a test integration by definition.
- **A reject is not a unit concern.** A reject is an outcome against a
  SCENARIO; scenarios do not exist at unit level, they are consumed by the
  system. So rejects live in `tests/integration`, always.
- **Hermetic and fast is the COST axis, not the unit boundary.** rigexp's 39
  fixture-only rejects are hermetic AND integration, simultaneously.

## Target zephyr: the tiacsys branch (Tobi, 2026-07-28)

`rigc` targets **`tiacsys/tskr/zephyr-rigs`**, and `btr-shields/west.yml`
tracks it by BRANCH NAME (`revision: tskr/zephyr-rigs`), deliberately — the
tiacsys base is what we want, not a frozen snapshot of it.

**Know the consequence, because it already bit once.** That branch gets
REBASED. When it did on 2026-07-28 it brought in upstream STM32 devicetree
changes — `82c668938df` ("dts: arm: st: *: sai: use empty ranges") plus a new
`ptp-clock` node — which legitimately altered the RESOLVED devicetree for the
quail board and turned two `test_resolved_accept_zephyr_dts` goldens red
without a single line of our own changing. The carried commits also got new
hashes (mapping table in `NEXT-SESSION.md`).

So for `rigc`: a red resolved-golden after a zephyr update is the EXPECTED
shape of an upstream SoC change, not a regression. Diagnose by classifying
the dts_equiv diff before touching anything — if every changed node is SoC or
board content and nothing rig-owned moved, it is a justified refreeze. If a
socket, shield, instance or generated node moved, it is not.

This is also why the resolved goldens must stay STRUCTURAL (`dts_equiv`,
never a byte diff): they have to tolerate upstream churn in nodes the rig
does not own, while still catching change in nodes it does.

## Naming

The tool is **`rigc`** (`bridle-migration.md`, ratified 2026-07-26), by analogy
to `dtc`: it REJECTS invalid input and emits several artifacts, both of which a
converter-shaped name would hide.
