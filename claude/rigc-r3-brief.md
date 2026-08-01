# Slice brief — R3: the shield library (registry, translation units, shield model, params)

Drafted 2026-07-29 by the driver, from `rigc-mission-brief.md` (§2, §4,
§5-§7), the golden census at `ecc3058`, and the blueprint surfaces
verified in `rigexp/loader_yml.py:97-410` (ShieldLibrary +
load_shield_library), `shields.py`, `ctypes_registry.py`, `dtsio.py`.
**RATIFIED by Tobi 2026-07-29** — all four flagged rulings accepted as
written (single slice, no R3a/R3b split; the cpp/unit-test seam;
dependency data as returned value; implementor on sonnet, reviewer on
opus). Depends on R2 (axis machinery, delta engine, ShieldRef seam);
dispatch after R2 lands.

## Goal

By slice end, rigc discovers, parses and resolves shield templates — the
connector-type registry, `.shield` translation units through cpp+dtlib,
shield.yml revision axes, lazy revision resolution — and wires the
param/pin/dt-include machinery that hangs off parsed shields. **15 named
reject goldens flip green** under `RIG_EXPAND_COMPILE=rigc`, taking the
differential meter from 64/146 (R2) to an expected **79/146** (38 of 48
rejects). R2's ShieldRef deferrals close: shield references resolve for
real, wire endpoints get their node-name validation back.

## 0. The target set, from the census

| family | fixtures | blueprint site |
|---|---|---|
| lang-schema, shield.yml (2) | `shield-bad-revisions-block`, `shield-revisions-mapping-entry` | `_load_shield_revisions:278` via the R2 axis parser |
| lang-shield-name (1) | `shield-node-name-mismatch` | `_pick_shield:248` |
| lang-rev, shield side (3) | `shield-no-revisions-declared`, `shield-undeclared-revision`, `shield-missing-fragment` | `ShieldLibrary.resolve:135` + `_resolve_revision:203` |
| lang-param (6) | `param-required`, `param-undeclared`, `param-unknown-device`, `restate-check`, `revision-crosses-variant`, `shield-revision-param-invariant` | `_check_param_invariant:836`, `_apply_params_block:868`, `_check_restate:952` |
| lang-dt-include (3) | `param-no-vocabulary`, `param-missing-header`, `param-unresolvable` | `_check_param_token:1341`, `_check_dt_includes:1367` |

The 23 R2-era greens (4 R1 + 19 R2) must survive. Still red after R3, by
design: phys-* (10, need board reading / analyzer) and all 19 accepts
(need the emitter).

## 1. Connector-type registry

Port `ctypes_registry.load_types`: connector-type facts read from binding
YAML under each `--connector-dir` root plus the `<type>.h` position-index
headers found via `--include-dir` (T0b landed this exact threading —
resolve the registry ONCE at CLI entry, pass it down as a value; the
hardcoded-BINDINGS default is rigexp's fallback for direct API use only).
The registry is a prerequisite, not a nicety: `parse_shields` checks every
plug against it (`shields.py:58` lang-shield-type), so an empty or stubbed
registry would emit errors on perfectly valid fixture shields and corrupt
every R3 golden's bytes.

## 2. Translation units — rigc's dtsio layer

Port the subset the shield side needs from `dtsio.py`: `run_cpp` (caller
include dirs, the T0c shape, on top of the ZEPHYR_INC/MODULE_INC
constants), `parse_tu` (base `.shield` + optional revision fragment
cpp-included into ONE unit — V1c's no-YAML-merge design), `src_of`,
`words`, `source_files` (workdir-excluded — feeds dependency data),
`parse_header_indices` (the registry's header half), `check_include` +
`resolve_token` + `is_int_literal` (the dt-includes vocabulary,  §5).

Constraints carried from the mission brief §7, non-negotiable:

- `devicetree.dtlib` located via `$ZEPHYR_BASE` at CALL time — **no
  module-scope lookup** (rigexp's `dtsio.py:27` trap, designed out; R1's
  discipline test already enforces it, keep it passing).
- **cpp is a subprocess, so nothing that invokes it is unit-testable.**
  The seam: shield-model parsing (§3) operates on a `dtlib.DT`, which is
  pure Python — unit tests build DTs from synthetic, cpp-free `.dts` text
  in tmp dirs and never call `run_cpp`. The cpp paths get their coverage
  through the frozen suite's front door, like everything else
  subprocess-shaped.
- Hermetic means no Zephyr DATA: unit fixtures are purpose-built
  synthetic connector types and shields, never copies of the real ones
  (T0's rule); `assert_fixture_local` proves it structurally.

## 3. The shield model — `parse_shields` and its node walk

Port the model `shields.py` builds: Shield (node-name identity), Device
(bus membership by parentage, `declared_params` from `shield,params`,
`extra_props` defaults, addr-from), plugs + position references, exposed
sockets, pads, straps, jumpers, `by_name`/`names()` lookup.

Two disciplines govern how much to port:

- **Everything the corpus fixture shields actually contain must parse
  correctly** — a silently skipped `shield,params` would flip
  param-required/param-undeclared with WRONG bytes (the differential
  catches this, but only when it runs; do not rely on luck). Census the
  constructs used by the target fixtures' shields FIRST, port those
  fully.
- **Shield-side validation diagnostics have zero frozen goldens**
  (lang-shield-type/-plug/-proxy/-addr-from/-addr-authority/-unit-addr/
  -prop/-pos-ref/-position/-exposed/-pad-role). Every one implemented
  falls under the R2 hand-differential rule (throwaway fixture, byte-
  compare rigexp vs rigc stderr, record it); any one not implemented is a
  loud Unimplemented, never a silent skip.

## 4. The library — scan, axes, lazy resolution

Port `load_shield_library` + `ShieldLibrary`:

- **Discovery**: per folder, exactly `<dir>/<basename>.shield` — never a
  `*.shield` glob (`Kconfig.shield` ends in the literal substring and
  would be mis-globbed; the blueprint docstring records this trap). The
  presence check is also the self-filter that skips legacy overlay-only
  shields. Multiple roots union into one library.
- **shield.yml**: supplies ONLY the `revisions:` axis (never identity),
  parsed by R2's axis machinery — same `{default:, list:}` shape under a
  `shield:` wrapper key. This is where the two lang-schema flips come
  from, for free, if R2's parser is reused rather than re-implemented.
- **Eager vs lazy**: no declared axis → base template parses at scan
  time; declared axis → parse deferred to `resolve()`'s first selection
  of each revision (the RIG_DEPENDS-breadth rationale is in the blueprint
  docstring `:112-124`). `resolve()` mirrors `_resolve_axis`'s three
  failure shapes plus `lang-instance-shield` for an unknown name (no
  frozen golden — hand-differential rule).
- **Rule 10's shield analogue**: a selected non-default revision that
  contributes neither `<name>_<rev>.shield` nor `<name>_<rev>.conf` is
  the `shield-missing-fragment` reject; the default is exempt.
- **Ordering**: the scan runs BEFORE rig.yml opens (blueprint
  `load():1186`), so scan-time diagnostics precede every rig-side one —
  `shield-node-name-mismatch`'s stderr depends on this. R2 skipped the
  library entirely; R3 restores the blueprint's stage order.
- **Reproduce-first warts** (mission brief §2, both observable): a
  malformed member hard-errors the whole scan; dependency recording sees
  every SCANNED base template, not just referenced ones. Both get
  revisited only post-green, as golden-changing decisions.
- **Dependency data is a RETURN/threaded value, not a side channel** —
  rigexp's `Depends` object is a mutable accumulator (`deps.see`), which
  is exactly §6's banned shape. rigc models "files this load touched" as
  data composed upward; nothing asserts it until the emitter slice writes
  `RIG_DEPENDS`, but the shape is decided HERE, where the recording
  points are.

## 5. Params, pins, vocabulary — closing R2's deferrals

With real Shield values behind the ShieldRef seam:

- `_apply_params_block` (rules 1/3/4/5): unknown device
  (`param-unknown-device`), undeclared parameter (`param-undeclared`),
  token resolution against the declared vocabulary (`param-unresolvable`,
  `param-no-vocabulary` — note the two distinct wordings at blueprint
  `:1349-1364`, empty-vocabulary vs non-resolving).
- `_check_param_invariant` (rule 2, per-stage): required-but-unassigned
  (`param-required`); re-checked fresh after every delta stage
  (`shield-revision-param-invariant`).
- `_check_restate` (rule 11): wholesale-replace restate guard
  (`restate-check`).
- Rule 12's variant-context wording in the unknown-device message
  (`revision-crosses-variant` — the `unknown_device_context` parameter).
- `_check_dt_includes` (rule 6): every declared header must exist and
  preprocess (`param-missing-header`), replacing R2's Unimplemented guard.
- `_apply_pin_block` / straps / jumpers: port with the model (`lang-pin`
  has no frozen golden — hand-differential rule).
- Wire endpoints: `_resolve_dotted`'s node-existence and ambiguity checks
  come alive via `Shield.by_name` (no frozen golden for either wording —
  hand-differential rule). This closes the R2 ruling's recorded
  divergence.

## 6. Unit tests

Value-shaped contracts that qualify (stable under rewrite):

- registry: socket facts from a synthetic binding (+ header indices).
- `_pick_shield`: folder-name vs node-name agreement as a pure decision.
- `resolve()`: the three failure shapes + lazy-parse memoization,
  exercised against a synthetic library value (no filesystem scan).
- revision → constructed fragment stems (shield side, normalization).
- the param invariant as a value function: (declared params, authored
  defaults, assignments) → findings.
- restate: (previously-assigned set, delta-restated set) → findings.
- token classification (`is_int_literal`) and vocabulary-lookup logic
  around `resolve_token` (the cpp invocation itself stays out, §2).
- shield-model parse over cpp-free synthetic DTs (devices by parentage,
  declared_params, by_name).

Module naming per the standing rule — production modules decide test
module names; if the shield side lands as several modules
(`registry.py`, `dtsio.py`, `shields.py`, library inside `loader/`),
each gets its `test_<module>.py` or a `tests/unit/<module>/` folder;
discipline-test expectations update deliberately.

## 7. Acceptance

A. Default gate (knob unset): frozen suite 146 green, rigc unit suite
   green, mypy clean over both packages, one `check.sh` run.
B. `RIG_EXPAND_COMPILE=rigc`: the 15 targets pass AND all 23 prior flips
   still pass (38 reject goldens green, expected meter 79/146). Every
   non-flip explained. Every other red is exit-3 or a clean diagnostic
   mismatch, never a traceback.
C. Zero edits outside `scripts/rigc/**`.
D. Unit suite subprocess-free and fast (discipline test proves the
   former; runtime reported). Coverage re-measured and reported.
E. Hand-differential evidence for every no-golden diagnostic implemented
   (the R2 rule), listed in the report.
F. STOP and report before any commit: files/modules, the 15 flips with
   evidence, which shield constructs were ported vs refused, the closed
   R2 deferrals, deviations flagged.

## Out of scope, deliberately

- Board DT reading (`boarddt`/`board_edt`/`edt_build`) and every phys-*
  reject — the analyzer slices.
- The emitter, accept artifacts, context.cmake, RIG_DEPENDS assertions
  (the dependency-data SHAPE is in scope, §4; its serialization is not).
- Revisiting the two scan warts; any wording improvement; any refreeze.
- hwmv2 revision semantics (lands later in the R2 axis seam, covering
  shields automatically — that is the point of reusing the axis parser).

## Needs Tobi's ratification

1. **Slice size**: registry + dtsio layer + shield model + library +
   params in ONE slice. Coherent (it is exactly "the shield library" from
   the mission arc, and the 15 targets interlock), but it is the largest
   R-slice so far. Alternative split if preferred: R3a
   registry/dtsio/model/library (7 flips), R3b params/pins/vocabulary
   (8 flips).
2. **The cpp/unit-test seam** (§2): dtlib-level parsing is unit-tested
   in-process on cpp-free synthetic input; every cpp-invoking path is
   integration-only by construction.
3. **Dependency data as returned value** (§4) — a deliberate §6-driven
   divergence from the blueprint's `Depends` accumulator, decided here
   because R3 creates the recording points.
4. Implementor model: sonnet per the standing rule, or a per-slice bump
   (this slice carries the most new machinery).
