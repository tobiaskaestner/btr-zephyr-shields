# Slice brief — R5: the emitter (artifacts, context.cmake, RIG_DEPENDS)

Drafted 2026-07-30 by the driver, from `rigc-mission-brief.md` (§4 arc,
§6 design rules), the R3 review's D3 deps carry-forward, the R4 review's
M6/M7/M8 carry-forward, the R4.5 ratified conventions (docstrings state
returns+ownership; IO at the edges, compute on values; artifacts as
values written by one shell), Tobi's live-run findings 2026-07-30, and a
FRESH differential census the driver ran at btr-shields `689903a`:
**52 failed, 94 passed in 103s** — the handoff's 94/146 confirmed
independently, red list enumerated in §0. Blueprint surfaces:
`rigexp/emitter.py` (514 lines) and `rigexp/cli.py:169-234` (the
context.cmake block, deliberately outside `emit()`).

Depends on R2+R3+R4+R4.5 (landed `0e6885f`, `54a9d38`, `2f93800`,
`689903a`). **This is the LAST conformance slice**: at its acceptance the
differential reads 146/146 and rigc reproduces rigexp on the whole
corpus. Everything after it is cutover, warts, and the standing queue.

## Goal

The accept path exists: a clean analysis produces the rig artifacts and
the build-glue handoff, `main()` returns 0, and **all 52 remaining
frozen tests flip green** under `RIG_EXPAND_COMPILE=rigc` — meter
94/146 → **146/146**. `unimplemented.py` becomes dead code on every
input the corpus contains (keep the module; retiring it is a cutover
step, not this slice's).

## 0. The target set — the driver's own census (2026-07-30 at `689903a`)

52 reds, four modules. Every one needs artifacts; nothing else is left.

| module | count | what |
|---|---|---|
| `test_emitted_corpus.py` | **19** | 12 × `test_emitted_golden[<accept rig>]` (ard_datalogger, frdm_eth_nest, lotus_buttons, lotus_pwm, nucleo_datalogger, nucleo_mux_farm, nucleo_wifi_logger_ok, pilot_variants, quail_sockets, quail_temp_farm, shield_rev_family, shield_rev_pilot) + 7 named (`test_ard_datalogger_frdm_golden`, `test_pilot_revision_2_golden`, `test_pilot_variant_b_golden`, `test_pilot_variant_b_revision_2_golden`, `test_pilot_variant_c_golden`, `test_shield_rev_family_revision_2_golden`, `test_shield_uart_subset_accept_on_frdm_golden`) |
| `test_resolved_corpus.py` | **26** | 12 × `test_resolved_accept_zephyr_dts[…]` (same rigs) + 14 named, incl. `test_resolved_rig_depends_provenance`, `test_resolved_build_info_rig_provenance`, `test_resolved_build_info_shield_dir_collision`, `test_resolved_user_extra_conf_wins_over_rig`, `test_resolved_lotus_pwm_semantic_pin`, `test_resolved_shield_revision_conf_collected`, `test_resolved_ard_datalogger_dual_host_d10` |
| `test_cmake_alone_entry.py` | **6** | the cmake-alone entry family (equivalence, qualified target, reconfigure, rig swap × 2, lotus+bridle module) |
| `test_reference_shields.py` | **1** | `test_reference_shields_accept` |

**19 golden directories** carry the accept artifact set (`rig-gen.overlay`,
`config-sheet.md`, `context.cmake`, `exit_code`, `stderr.txt`; plus
`rig-gen-includes.dtsi` for `lotus_buttons` alone, plus `zephyr.dts` for
the 18 with a tier-2 build). `EMITTED_FILES` also lists `rig-gen.conf` —
**never produced**; `assert_absent_or_refreeze` proves its absence in
every golden dir, so emitting one would FAIL the suite. `expectations.yml`
is emitted and deliberately **never gated** (`test_emitted_corpus.py`
docstring) — write it, no golden asserts it.

All 94 current passes must survive. Zero reject golden may move.

## 1. The emitter — artifacts as values

Port `rigexp/emitter.py` whole. Nothing in it is refused, nothing is
redesigned: it is already the closest thing in the blueprint to a pure
value layer ("never decides anything, never fails on an analyzer-accepted
rig"), and its output is frozen to the byte. What changes is the SHAPE at
the boundaries, per the ratified conventions:

- **`{filename: bytes}`, one writer.** `emit()` computes artifacts as a
  mapping of filename to BYTES (the ratified wording, taken literally —
  explicit UTF-8 encode; `config-sheet.md` carries `→` and em dashes, so
  the encoding is a real decision, not a formality). ONE shell function
  performs every write, binary mode. The blueprint's `dict[str, str]` +
  per-file `open(..., "w")` in `cli.py` is exactly the interleaving the
  convention bans. Byte-identity is unaffected under a UTF-8 locale, and
  an explicit encode removes the blueprint's silent dependence on one.
- **Suggested decomposition** (implementor names the final split;
  `tests/unit/emitter/` mirrors it): `overlay.py` (nexus synthesis,
  I2C scopes + mux nesting, SPI/cs-gpios, collections, plain groups,
  controllers, the device-node renderer), `sheet.py` (config-sheet.md +
  the params table's token resolution), `expectations.py`, `context.py`
  (§2), `__init__.py` composing `emit()`, and the writer.
- **Read `solved.wires`, NEVER `rig.wires`** — the R4 review's ruling,
  and the one silent-wrong-overlay trap in this slice. They differ: the
  loader's `rig.wires` carries the RAW `via <name>` route string;
  `analyzer/wires.py::check_wires` returns NEW Wire values with the route
  resolved to a connector-type position INDEX, and only `Solved.wires`
  holds those (the blueprint mutates `wire.route` in place, which is why
  it can read `s.rig.wires` and rigc cannot). Both the config sheet's
  Wires section and `expectations.yml` consume it. A unit test must pin
  this by construction: a Solved whose `wires` differ from the rig's, with
  the rendered sheet asserted to show the RESOLVED route.
- **`WireEnd` differs from the blueprint by design**: rigc's holds
  `instance_name: str`, rigexp's holds an `Instance`. Every `w.frm.
  instance.name` in the blueprint becomes `w.frm.instance_name`. Same
  bytes, one less object graph.
- **Keep the two invariant guards** the blueprint documents rather than
  re-deriving: the nonzero-PWM-flags `raise AssertionError` (NOT `assert`
  — it must survive `python -O`; the analyzer's `phys-function` rejection
  is what makes it unreachable) and the `zephyr,sdhc-spi-slot` sdmmc child
  node. Both carry their reasoning, not their history.
- **Determinism is the contract**: every output sorted by stable keys,
  never rig-file declaration order (R7/R18). The 19 goldens are the oracle.

## 2. context.cmake and RIG_DEPENDS — closing R3's D3

The build-glue handoff (`rigexp/cli.py:174-230`): `RIG_NAME`, `RIG_BOARD`,
`RIG_SHIELDS` (distinct, rig order), `RIG_SHIELD_REVISIONS`
(`<name>@<rev>`, only for shields declaring the axis), `RIG_REVISION` /
`RIG_VARIANT` (only when the rig declares that axis — the "no
declaration, no artifact" rule that keeps axis-less rigs' goldens
byte-identical), `RIG_DEPENDS` (sorted, absolute, `;`-joined, each
element escaped for a CMake list literal — port `_cmake_list_escape`
verbatim, comment and reasoning intact).

**Structural ruling (driver, §8.3):** context.cmake is rendered by a
`context.py` VALUE function, not built with string concatenation in
`cli.py`. The blueprint keeps it out of `emit()` to preserve a real
semantic boundary — rig artifacts vs build glue — and that boundary
survives as a module boundary: `emit()` returns the rig artifacts,
`context.render(...)` returns the context.cmake bytes, `cli` merges the
two mappings and hands ONE mapping to the ONE writer. `cli.py` builds no
strings.

**The deps closure — the actual work.** rigc's `deps.py` value shape is
in place and five call sites already return Deps; the values are then
DISCARDED and four recording points are missing. Every one, exhaustively:

| where | today | R5 |
|---|---|---|
| `cli.py:163` | `types, _deps = load_types(...)` | keep the value |
| `cli.py:196` | `board, board_diags, _bdeps = load_board(...)` | keep the value |
| `loader/__init__.py:354` | `lib, diags, _deps = load_shield_library(...)` | keep the value |
| `loader/__init__.py:357` | `parse_marked(rig_path)` — **no dep** | record rig.yml (blueprint `loader_yml.py:1185`) |
| `loader/__init__.py:196` | content file `parse_marked` — **no dep** | record it (blueprint `:786`) |
| `loader/__init__.py:203,209` | the two fragments — **no dep** | record both (same blueprint site) |
| `_build_topology:283,301,313` | `_idep` from `parse_instance` / both `apply_delta` stages | union all three |

`load()` therefore returns a TRIPLE — `(Rig | None, diagnostics, Deps)` —
which its own docstring already anticipates ("computed internally as a
value but not yet returned"). `_gather_content` / `_build_topology` grow
their own Deps return element the same way. Phase 1 (`_resolve_metadata`)
does not: it opens nothing (rig.yml is parsed by `load()` itself).

**Two byte-level facts the implementor must not "improve":**

1. **The eager scan's breadth is the contract.** `lotus_buttons`'
   RIG_DEPENDS lists EVERY discoverable `.shield` (14 of them, for a rig
   naming 2) and `shield.yml` only for the two it resolves. That is the
   §2 wart the LAZY SHIELD LIBRARY item exists to fix — **after** cutover,
   as a deliberate refreeze-class step. R5 freezes the eager set; do not
   narrow it.
2. **Resolution HISTORY, not the final topology.** `pilot_variants_variant_c`
   lists `adafruit_data_logger/shield.yml` although `RIG_SHIELDS` is only
   `pilot_alt_button` — the base stage resolved the data logger before the
   variant delta substituted it away. So deps must be unioned from the
   `_idep` values of stage 0 AND both delta stages; recomputing them from
   the final instance list would silently drop it, and no reject golden
   would notice. Union at each site, never derive.

Also deliberate, and NOT to be fixed here: the rig's own `dt-includes:`
headers are absent from RIG_DEPENDS (`lotus_buttons` declares
`zephyr/dt-bindings/input/input-event-codes.h`; it does not appear).
`dtsio.check_include` and the sheet's `resolve_token` record nothing —
reproduce that. Wart list, post-conformance.

## 3. The accept path in `cli.py`

Replace the `raise Unimplemented(...)` with: emit → merge context →
write once → **warnings-only render to stderr** (`if diags:` after the
error gate — accepts DO print warnings, `test_emitted_corpus` freezes
them) → `return 0`. The verdict log line (`log.info`) joins `_reject`'s
symmetry: one accept site, one reject site, exit code and log line
inseparable. `out_dir` is absolutized like every other path input and
created with `makedirs(exist_ok=True)`.

## 4. Unit tests — `tests/unit/emitter/`

The emitter is the most testable layer in the system (pure, value-in
value-out) and the frozen suite already covers it end to end, so the unit
layer aims at CONTRACTS THAT SURVIVE A REWRITE, not at coverage:

- The `solved.wires` contract (§1) — the trap, pinned by construction.
- Artifact SET as a function of input: `rig-gen-includes.dtsi` iff
  `dt_includes` is non-empty; `rig-gen.conf` never; `expectations.yml`
  always. (`assert_absent_or_refreeze` makes over-emission a suite
  failure — pin it at unit level too.)
- Determinism: same Solved, shuffled input ordering (instance list,
  scopes, groups) → identical bytes.
- `context.render`: the conditional keys (RIG_REVISION / RIG_VARIANT /
  RIG_SHIELD_REVISIONS present iff declared), `RIG_SHIELDS` distinct-in-
  rig-order, RIG_DEPENDS sorted, and `_cmake_list_escape` over a path
  containing `;`, `"`, `\` (the case real paths never produce and no
  golden can cover — hand-differential territory made a unit test).
- Deps composition as a value: a synthetic phase result set unions to the
  expected path set, and the "substituted-away shield stays in deps"
  property of §2.2 as its own named test.
- The device-node renderer over a synthetic Solved: gpio/pwm/adc idioms,
  `inst.invert` flag flip, params substitution (replace vs add), the
  sdmmc child, the PWM-flags AssertionError.

Subprocess-free (audit hook), fixture-local (`assert_fixture_local`), no
production data. Wording is not asserted; structure and bytes are.

## 5. Diagnostics

R5 adds no new diagnostic category. The `_render_one` `ref is None` guard
(R4-M6) is already CLOSED by the R4.5 driver diff — nothing to do. If the
port surfaces a no-golden wording anywhere, the standing
hand-differential rule applies (throwaway fixture, byte-compare against
rigexp, recorded in the report).

## 6. Acceptance

A. Default gate green in ONE `check.sh` run: frozen 146, rigc unit suite
   green, mypy clean over both packages.
B. `RIG_EXPAND_COMPILE=rigc` full differential: **146/146**. All 52
   targets flip AND all 94 current passes survive. Run the FULL suite,
   not a module subset — 32 of the 52 are build-marked.
C. Zero edits outside `scripts/rigc/**`. No golden is touched, and
   `git status` on `scripts/rigexp/tests/goldens/` is empty. **Never set
   `RIGEXP_REFREEZE`** — a refreeze during this slice would rewrite the
   oracle with rigc's own output and silently destroy the differential.
D. Unit suite subprocess-free and fast; runtime + coverage reported.
E. The report states, per §2, which of the 19 accept goldens' RIG_DEPENDS
   lines were compared and that they matched byte-for-byte — the deps set
   is the one part of this slice a wrong implementation can get *nearly*
   right, and the two facts in §2 are where it goes wrong.
F. STOP and report before any commit: files/modules, the 52 flips with
   evidence, deviations flagged. Leave everything uncommitted.

## 7. Out of scope, deliberately

- **M8, the recipe-error traceback family** (see §8.1) — bogus
  `--build-info` path (`FileNotFoundError`/`KeyError` in
  `recipe_from_build_info`) and an insufficient recipe (`RuntimeError`
  from `edt_build.preprocess`, `rigc:127` = `rigexp:114`, byte-parity).
- **The LAZY SHIELD LIBRARY** and the two §2 warts it retires — pinned
  until after cutover by the facts in §2.
- The dt-includes deps wart (§2), any other blueprint wart, wording
  changes, refreezes, `unimplemented.py`'s retirement.
- The coverage `fail_under` ruling (due, separate, Tobi's call).

## 8. Rulings — RATIFIED by Tobi 2026-07-30

All six accepted as recommended. Recorded with their reasoning, since
each is a standing precedent the cutover and the wart slices inherit.

1. **M8: PARKED** to the post-conformance wart list. Reasoning: rigexp TRACEBACKS on both inputs, so fixing it
   makes rigc DIVERGE from the blueprint on a path no golden covers —
   during the one slice that must flip 52 accept goldens, where a wrong
   `phys-board` diagnostic would be invisible to the oracle. It is
   cleanly separable (a diagnostic + a fixture, no shared code with the
   emitter) and costs nothing to defer. Against parking: Tobi hit it in a
   live run, so it is a real usability defect with a known fix site.
2. **`Solved` becomes frozen (M7): YES** —
   `@dataclass(frozen=True)`. It is built exactly once, in
   `analyzer.analyze`'s final assembly, and R5 is its only consumer; the
   freeze costs nothing and states the ownership the docstring convention
   now requires. (Field dicts stay mutable objects — the freeze pins
   rebinding, which is the accumulator shape being banned.)
3. **context.cmake IS a value module** (§2), not the blueprint's
   in-`cli.py` string building. Behavior-identical, structurally a
   divergence, and the one place this slice does not simply port.
4. **Artifacts ARE `{filename: bytes}`** with explicit UTF-8 (§1) — the
   ratified convention read literally, not the blueprint's `str` + text
   mode.
5. **Slice size: ONE slice**, on this evidence: a
   split has no observable acceptance boundary, because
   `test_emitted_golden` compares `rig-gen.overlay` AND `context.cmake`
   in the SAME test — an "artifacts first, context.cmake second" split
   flips ZERO goldens in its first half. The only honest split would be
   by RIG (emit for axis-less rigs first), which is not a design boundary
   at all. Cost of one slice: it is the second-largest port (514
   blueprint lines + the deps closure through six modules) and it lands
   the whole remaining meter at once.
6. **Implementor sonnet, reviewer opus**, then a driver round and the
   commit (Tobi's direction for this slice).
