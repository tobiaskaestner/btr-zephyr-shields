# Slice brief — R4: the analyzer (board reading, sockets, nets, addresses, CS)

Drafted 2026-07-29 by the driver, from `rigc-mission-brief.md` (§4 arc,
§6 design rules — this is the slice they were written FOR), the retitled
ANALYSIS `unit-test-layer-brief.md` (the testability diagnosis and the
`cs-gpios` worked example are direct inputs), a fresh differential census
at btr-shields `54a9d38` (79/146), and the blueprint surfaces
`rigexp/analyzer.py` (667 lines), `boarddt.py`, `board_edt.py`,
`edt_build.py`. **RATIFIED by Tobi 2026-07-29** — all four flagged
rulings accepted: ONE slice (no R4a/R4b split — the boundary was
examined and the split rejected because it cuts the solved-model
contract in half and doesn't divide the hard part); the BSD-3 reader
boundary; the solved-model contract as R5's input; implementor on
sonnet, reviewer on opus. Depends on R2+R3 (landed `0e6885f`,
`54a9d38`).

## Goal

By slice end, rigc reads the real board devicetree and analyzes the
loaded rig — mating and socket resolution (including carrier/mux
composition), net identity and conflicts, address allocation, CS-pool
allocation, wires, labels — and **15 frozen tests flip green** under
`RIG_EXPAND_COMPILE=rigc`, taking the meter from 79/146 to an expected
**94/146**. Every reject golden is then green; what remains red is
exactly the accept corpus and the cmake-entry family — the emitter
slice's territory. The unit layer built here is the mission's
centerpiece: the `cs-gpios` acid test must pass — "where and how is the
final `cs-gpios` property calculated?" is answered by reading
`tests/unit/analyzer/`.

## 0. The target set, from the census (2026-07-29 at `54a9d38`)

| family | frozen test | golden |
|---|---|---|
| phys-socket | `test_emitted_rejects::test_unmapped_socket_golden` | `unmapped-socket` |
| phys-board ×2 | `test_emitted_corpus::test_unknown_board_golden`, `::test_not_rig_enabled_golden` | `unknown-board`, `not-rig-enabled` |
| phys-subset | `test_emitted_corpus::test_shield_uart_subset_reject_on_nucleo_golden` | `shield-uart-subset-nucleo` |
| phys-function | `test_emitted_corpus::test_pwm_nonzero_flags_golden` | `pwm-nonzero-flags` |
| phys-cs | `test_emitted_corpus::test_emitted_golden[frdm_cs_clash]` | `frdm_cs_clash` |
| phys-channel | `test_emitted_corpus::test_emitted_golden[lotus_pwm_clash]` | `lotus_pwm_clash` |
| phys-addr ×2 | `test_emitted_corpus::test_emitted_golden[nucleo_mux_clash]`, `[quail_dup_th]` | `nucleo_mux_clash`, `quail_dup_th` |
| phys-net | `test_emitted_corpus::test_emitted_golden[nucleo_wifi_logger]` | `nucleo_wifi_logger` |
| tier-2 builds ×5 | `test_resolved_corpus::test_resolved_reject_configure_fails[frdm_cs_clash / lotus_pwm_clash / nucleo_mux_clash / nucleo_wifi_logger / quail_dup_th]` | same stderr through cmake |

All ten reject goldens are single-error (census-verified). The five
tier-2 flips prove the cmake path end to end: dts.cmake invokes rigc
with `--board-dts`/`--build-info`/the full argv, and the configure FATAL
carries the rendered phys text. The 23+15 prior flips must survive.

NOT R4: the 19 emitted accept goldens, `test_reference_shields_accept`,
all resolved-corpus accepts/builds, the 6 `test_cmake_alone_entry` tests
(they need artifacts and context.cmake) → the emitter slice.

## 1. Board reading — the BSD-3-ready reader layer

Port the three-module stack, keeping its boundary:

- **`edt_build`** (blueprint `edt_build.py`): `BuildRecipe` (cpp include
  dirs + edtlib bindings dirs), `recipe_from_build_info` (an existing
  unit-tested contract — the blueprint's own `test_recipe_from_build_info`
  is the model), `preprocess`, `build_edt`. `devicetree` (dtlib/edtlib)
  comes from `$ZEPHYR_BASE` at CALL time (rigc already has this
  discipline; keep it). **License boundary carried over**: the board/
  binding READER layer in rigexp is deliberately BSD-3-Clause-ready and
  decoupled from the Apache-2.0 product layer (it is the
  upstream-into-python-devicetree candidate; edtlib idioms — full
  annotations, mypy-clean, `Optional[X]` not `X | None`). rigc preserves
  that: reader modules carry the same license header split as their
  blueprints and import nothing from the product layer.
- **`board_edt`**: `project_edt` — every `socket,*`-compatible node
  projects to a `BoardSocket` (label, gpio_map, buses, cs_pool with the
  binding-default merge, pwm_map/adc_map); `_controller_label` = the
  DEFINING label, `labels[0]` (slice A's ruling; the blueprint's
  `test_controller_label` pair is the contract to keep).
- **`boarddt`**: board RESOLUTION and the two phys-board diagnostics,
  both golden-covered: `--board-dts` explicit (the in-build path; also a
  missing file), the standalone discovery fallback via zephyr's OWN
  `list_boards.py` (consumed, not forked — including the KNOWN-GAP
  wording of `unknown-board`, which honestly reports that the
  MODULE_ROOT-only catalog is empty; reproduce the wording, gap and all),
  the no-recipe diagnostic, and "exists but declares no socket,* node"
  (`not-rig-enabled`). Board-dts dependency recording joins the R3
  returned-value deps shape.

## 2. The analyzer — where §6 either pays off or the mission failed

The blueprint's shape is the counterexample the mission brief §6 was
written against: `Solved` is a mutable accumulator threaded through
seven passes (`analyze`, `analyzer.py:73-100`), 20 of 23 functions take
`solved` and/or `diags`, and the worked acid test hides inside
`_allocate_cs(rig, solved, types, diags)`. rigc reproduces the
BEHAVIOR (goldens) with the OPPOSITE shape:

- **Passes are value functions.** Each takes exactly the prior pieces it
  needs (never the whole model where a value would do) and returns
  `(its piece, diagnostics)`. One composing function assembles the
  solved model — a frozen-ish value the emitter will consume — in the
  blueprint's pass order: sockets → gpio nets → addresses → CS → wires →
  net conflicts → labels. The blueprint's skip-don't-abort behavior
  (an instance whose mating failed is absent from the socket map; later
  passes skip it individually) is part of the observable contract —
  reproduce it.
- **The solved model is R5's input contract.** Define it as data
  (today's `Solved` fields minus `rig`/mutability: sockets, addr,
  straps, cs, cs_gpios, bus_label, nets, positions, jumpers_set,
  channels, controllers, scopes — blueprint `analyzer.py:50-65`), with
  the emitter's consumption in mind but WITHOUT building any emission.
- **Allocation order is a stable contract**: `_key` — `(socket,
  instance name, device name)`, R18, never rig-file declaration order
  (`analyzer.py:68-70`). Unit-test it by name.
- **The `cs-gpios` acid test** (mission brief §6, the ANALYSIS §"Worked
  example"): the position-choosing contract is written value-shaped from
  the start — *given an ordered pool, the already-taken positions, and
  the members of one SPI scope (some copper-fixed), assign each a
  position or report the pool exhausted* — separated from the four
  upstream pool sources (type default, board-socket override, shield
  synthesis, the `socket.cs_pool if not None else ctype.cs_pool` merge).
  Acceptance: `tests/unit/analyzer/test_cs.py` (or the module the
  implementor names for the unit) answers Tobi's question —
  copper-fixed precedence, pool ordering, first-free selection,
  exhaustion, pool-merge fallback, each named and asserted without a
  scenario.
- **Address allocation gets the same treatment** (`_allocate_addresses`
  / `_allocate_scope`, 73 lines each in the blueprint): fixed/pinned
  (R18 `pin:` strap) vs free allocation, per-scope uniqueness (R26 —
  a mux channel is a NEW scope), strap recording for the config sheet.

## 3. Socket resolution and composition

`_check_matings` / `_resolve_socket` / `_compose_socket`
(`analyzer.py:105-236`): plug-type vs socket-type mating (R19/R20),
subset exposure typed and checked (`phys-subset` — a socket offering no
`socket,uart` rejects a uart-needing plug; the frdm accept twin stays an
emitter-slice flip), unknown socket label (`phys-socket`,
`unmapped-socket`), and the recursive composition for instance-provided
sockets — a carrier's exposed socket and a mux channel compose the
parent's socket with the child's exposure, `stack`-guarded, producing
synthesized sockets and scope entries (R26/R27; `nucleo_mux_clash`
allocates THROUGH this, so composition is load-bearing for a target,
not accept-path-only). Socket references arrive already
binding-resolved from the loader (R2's SocketBinding) — the analyzer
never sees an abstract name.

## 4. Nets, channels, positions

`_collect_gpio_nets` / `_collect_gpio` / `_collect_channel` /
`_resolve_jumper` / `_check_nets` / `_exclusive_conflict`
(`analyzer.py:263-440`): net identity IS sharing (`_soc_net` — position
→ (controller, pin) through the board gpio_map; ontology §1), claims
with roles (driver/listener/dedicated), pwm/adc channel resolution
through the multi-function maps (`phys-channel`, `lotus_pwm_clash`),
the nonzero-PWM-flags rejection (`phys-function`, `pwm-nonzero-flags`),
jumper-deferred positions, and the conflict report composed from claim
lines (`phys-net`, `nucleo_wifi_logger` — the message enumerates
claims; reproduce composition order exactly).

## 5. Wires and labels

`_check_wires` (`analyzer.py:615-650`): wire endpoints against resolved
sockets/positions, route validation (phys-wire family — no frozen
golden, hand-differential rule). `_check_labels` (`:654`): emission
feasibility (phys-label — same). These close out the analyzer's pass
list so the emitter slice starts from a complete solved model.

## 6. Unit tests — `tests/unit/analyzer/`

The sub-folder pattern ratified with the naming rule: production
analyzer modules (implementor's decomposition — e.g. `analyzer/` as a
package mirroring the pass structure) get `tests/unit/analyzer/<module>`
mirrors; the capability story lives INSIDE modules via section headers
and test names. Contracts that qualify (stable under rewrite):

- CS position allocation (the acid test, §2) and the pool-merge rule.
- Address allocation per scope: fixed/pinned/free, collision, exhaustion.
- Net identity (`_soc_net`) and `_role_of`.
- Allocation ordering (`_key`, R18).
- Controller label = defining label (carry the blueprint's two tests).
- `recipe_from_build_info` (carry the blueprint's test).
- Mating/subset decision as a value function (plug needs vs socket
  offers).
- Socket composition: (parent socket, exposure) → synthesized socket +
  scope entry, stack-guarded.
- Board projection over a SYNTHETIC, cpp-free board DT (in-process
  edtlib — the blueprint's own `test_controller_label`/`test_edt_build`
  are the precedent). Purpose-built fixture data in rigc's own tree,
  NEVER read from the frozen suite's fixtures; `assert_fixture_local`
  applied (R3 review D2's lesson: enforcement, not intention).

Wording stays out of unit tests; diagnostics are asserted by code,
anchor, ordering, structure. No subprocess anywhere under `tests/unit/`
(audit-hook standard from R3 applies at review).

## 7. Diagnostics: ordering and the no-golden census

- Pass order defines diagnostic order; within a pass, blueprint
  traversal order. The five tier-2 targets render through cmake — the
  harness normalizations (workdir, banner) already handle the rest.
- **No-golden phys wordings needing the hand-differential rule** (census
  of the blueprint's 25 analyzer sites + 7 boarddt sites vs the 10
  covered goldens): phys-mating (2 sites), the other phys-socket shapes
  (3 of 4 sites), phys-position (2), phys-pin, phys-wire (3),
  phys-label, the second phys-addr site, the second phys-cs site, the
  second phys-net/subset sites, boarddt's no-recipe and missing-file
  shapes. Every one implemented gets a throwaway-fixture byte-compare
  against rigexp, recorded (watch the em-dash/`--` mix — R3 found 8
  drifted sites this way).

## 8. Acceptance

A. Default gate: frozen 146, rigc unit suite green, mypy clean both
   packages, one `check.sh` run.
B. `RIG_EXPAND_COMPILE=rigc`: the 15 targets pass AND all 38 prior
   flips survive (meter expected **94/146** — every reject golden
   green). Every remaining red is exit-3 or clean, zero tracebacks.
   Note the tier-2 targets are build-marked: run the full differential,
   not just the reject module.
C. Zero edits outside `scripts/rigc/**`.
D. Unit suite subprocess-free and fast; runtime + coverage reported.
   The `cs-gpios` acid test explicitly demonstrated in the report:
   quote the test names that answer the question.
E. Hand-differential records for every no-golden phys/board wording
   implemented (§7).
F. STOP and report before any commit: files/modules, the 15 flips with
   evidence, the solved-model contract as delivered (R5's input),
   deviations flagged.

## Out of scope, deliberately

- The emitter: rig-gen.overlay, rig-gen-includes.dtsi, config-sheet.md,
  context.cmake, RIG_DEPENDS serialization (the deps carry-forward from
  R3 review D3 lands THERE), the 19 accepts, reference-shields accept,
  cmake-alone tests.
- Fixing blueprint warts; wording changes; refreezes.
- The fail_under ruling (due, but Tobi's standing call — separate).

## Needs Tobi's ratification

1. **Slice size**: board reading + the whole analyzer in ONE slice.
   Coherent (every allocation target needs the pipeline up to its pass,
   and composition is load-bearing for `nucleo_mux_clash`), but it is
   the largest port yet (667 blueprint lines + the reader stack) AND
   carries the mission's centerpiece unit layer. Offered split: R4a =
   reader + matings/sockets/subset (4 flips: the two phys-board,
   `unmapped-socket`, `shield-uart-subset-nucleo`), R4b =
   nets/channels/addresses/CS/wires (11 flips: the remaining 6 tier-1
   rejects + the 5 tier-2 builds). The driver's recommendation is ONE
   slice — the split point cuts through the solved-model contract R5
   needs whole.
2. **The reader license boundary** (§1): BSD-3-ready reader modules,
   product-layer imports banned — carried from rigexp's design record.
3. **The solved-model contract as R5's input** (§2) — defined in this
   slice, consumed unchanged by the emitter brief.
4. Implementor model: sonnet per the standing rule, opus reviewer, or a
   bump — this slice is where the design judgment (value-shaping a
   667-line accumulator pipeline) is heaviest.
