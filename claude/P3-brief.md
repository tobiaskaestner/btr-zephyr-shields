# P3 — Widen the requirement slices (staging brief)

P2 delivered one rig (S1) end-to-end on real hardware. P3 grows the pipeline one
**requirement subset** at a time, each slice end-to-end (rig.yml → `west build-rig`
→ real build → accept or the expected rejection), each with tests. This brief
sets up the phase and details the first slice (**3a Allocation**). Read after
`implementation-plan.md` §P3 and `NEXT-SESSION.md`.

## What P2 leaves in place (the P3 substrate)

- **Downstream module `btr-shields/`** (git repo, manifest repo). Add boards
  under `boards/`, shields under `boards/shields/*.shield`, rigs under
  `boards/rigs/*.rig.yml`, connector bindings under `dts/bindings/connector/`.
- **Front door `west build-rig --rig <name> <app>`** — infers the board from the
  rig; the app source dir is required (positional or `-s`, no default). Forces
  `ZEPHYR_BASE=zephyr-rigs`, runs the seam. Accept = configure-clean + expected
  nodes; **reject = configure FATAL_ERROR carrying the expander's `phys-*`
  diagnostic** (the seam surfaces it) — that IS the real-build rejection signal.
- **The seam** = `btr-shields/cmake/default.cmake` → `rig_expand()` → the real
  `rigexp` expander. Rides the committed `cmake-modules` feature.
- **`.cmake` inheritance capability** (from the zephyr-rigs `cmake-modules`
  commit): dropping `btr-shields/cmake/<module>.cmake` (e.g. `dts.cmake`) that
  `include()`s Zephyr's original then adjusts lets us intercept **after** a
  standard module runs — the intended tool for post-`dts` **aggregation**.
- **R2 checker** `btr-shields/scripts/dts_equiv.py` (structural, path-keyed).
- **Accept/reject oracle**: `frontend-trial/scripts/run_trials.py` `TRIALS` map +
  `EVALUATION.md` — the prototype verdict each rig must reproduce on a real build.

## Slices (from implementation-plan.md §P3)

- **3a Allocation** — S2, S5 (+ S4b): CS pools, address straps, routing jumpers,
  and the **Kconfig activation manifest** (the 4th emitter output). Folds in the
  deferred **LED-merge aggregation** gap.
- **3b Interposers** — S6, S8: nested carriers (pass-through) + scope-creating
  muxes; scope-aware checks on a real build.
- **3c Multi-function + pinctrl** — lotus PWM/ADC positions and **pinctrl
  fragment application** (R21 deep half); DAC/UART emission as needed.

Each slice: its rigs build (or reject) on real hardware exactly as the oracle
says; its twister tests pass.

## 3a — Allocation (first slice, detailed)

**Rigs to port** (from `frontend-trial/candidate-2-hybrid/`, with their oracle
verdict):

| rig | board | shields | verdict | exercises |
|---|---|---|---|---|
| `s2-wifi-logger-ok` | nucleo_f401re_btr | data-logger + winc1500 (stacked) | **accept** | stacked mating, CS allocation, IRQ jumper @D2 (R6) |
| `s2-wifi-logger` | nucleo_f401re_btr | data-logger + winc1500 | **reject** | IRQ jumper left @D7 → `phys-net` |
| `s5-temp-farm` | **mikroe_quail** (new) | flash-click ×2 + temp-click | **accept** | CS pool, address straps, mikrobus sockets |
| `s4b-sockets` | (per trial) | — | **accept** | socket selection picks the controller (R14/R15) |
| `s4b-dup-addr` | (per trial) | — | **reject** | two fixed 0x5f on shared i2c1 → `phys-addr` (R9) |

**Porting work.**
1. **Board**: clone `mikroe_quail` into `boards/` (as we did nucleo), with its
   typed mikrobus socket nodes (Conv. 4). S2 reuses `nucleo_f401re_btr`.
2. **Shields**: port `winc1500`, `flash-click`, `temp-click` (and any S4b
   shields) from `frontend-trial/common-dts/shields/` into `boards/shields/`.
   Author the `mikrobus` connector-type binding for real.
3. **Rigs**: port the five `.rig.yml` into `boards/rigs/` (adjust board ids).
4. **Kconfig activation manifest (4th output)** — the real deliverable of 3a.
   **Design DECIDED (see O-3a.1):** drivers self-enable from DT
   (`DT_HAS_*_ENABLED`) — the rig emits nothing for driver enable. Only the
   *residual* (subsystem/feature configs DT can't imply) is declared, via a
   **companion `.conf` per shield** — `boards/shields/<shield>.conf` alongside
   `<shield>.shield` (upstream-aligned). The emitter concatenates the companion
   `.conf` of every instantiated shield (union + dedup) into the rig's `conf`
   output; `rig_expand` already wires `OVERLAY_CONFIG` from `<out_dir>/conf`
   (no-op when absent). Residual content is derived EMPIRICALLY (below), not
   guessed. FUTURE (not 3a): defconfig-style *defaults* (`Kconfig.defconfig`,
   overridable, gated on presence) — noted per Tobi; the `.conf` route is the
   hard-assignment path for now.
   **Sequence:** this is held until the porting sub-agent lands the shields;
   then (i) full-compile `s2-wifi-logger-ok` (drop `--cmake-only`) to read off
   which `CONFIG_*` are auto-on from DT vs missing, (ii) author the per-shield
   `.conf` residual from that evidence, (iii) add the emitter concatenation.
5. **LED-merge aggregation** (deferred from P2): shield collection nodes
   (`/gpio_leds`) should merge into a board-provided collection (`/leds`).
   Approach TBD — a `compatible`→node-name convention, or post-`dts`
   interception via a `btr-shields/cmake/dts.cmake` that adjusts the merged tree.

**Exit for 3a.** All five rigs build/reject on real hardware matching the oracle;
CS-pool and address-strap allocation verified in `zephyr.dts`; the Kconfig
fragment enables the right drivers; LED-merge resolved; twister tests green.

## Cross-cutting — Test / CI (start in 3a, grow through P3)

Port the corpus to **twister**: for each rig, a testcase that builds it and
asserts **configure-clean** (accept) or **the expected `phys-*` rejection**
(reject). ~~Drive the **expectations** artifact (A6) for runtime checks where a
board runs.~~ (A6 moved to its own project `claude/hw-expectations/`,
2026-07-23 — emitted but nothing gates on it.) The `TRIALS` map is the
accept/reject truth table to encode.
Preserve **diagnostic parity** — the physically-worded `phys-*` messages must
survive west/CMake to the user.

## Execution model

Same as P2: a driver delegates each unit to a **sonnet** sub-agent with a
self-contained brief; human-review gates between units; port-then-build-then-test
per rig. Suggested 3a order: (1) S2 pair (reuses existing board — fastest
end-to-end loop, exercises the reject path), (2) Kconfig manifest, (3) S5 +
mikroe_quail board, (4) S4b pair, (5) LED-merge, (6) twister harness.

## Open questions to settle at 3a kickoff

- **O-3a.1 Kconfig source — RESOLVED (2026-07-21).** Hybrid: drivers auto-enable
  from DT (`DT_HAS_*_ENABLED`, no rig action); the *residual* (WIFI, FILE_SYSTEM,
  …) is declared per shield in a **companion `boards/shields/<shield>.conf`**
  (option b — upstream conventions; leaves room for a future `Kconfig.defconfig`
  defaults path). Emitter unions the instantiated shields' companion `.conf` →
  rig `conf` → `OVERLAY_CONFIG` (already wired). Residual derived empirically via
  a full-compile of s2-wifi-logger-ok. Held until the porting agent lands the
  shields.
- **O-3a.2 LED-merge mechanism**: convention table vs post-`dts` `.cmake`
  interception vs emitter-level merge into a board-declared collection.
- **O-3a.3 Reject-at-build ergonomics**: confirm a rejected rig fails
  `west build-rig` with the `phys-*` text intact, and decide how twister asserts
  it (expected-build-failure + message grep).
- **O-3a.4 mikroe_quail**: clone-and-own like nucleo (new board id), or is there
  a lighter path for a board we only need for socket structure?
