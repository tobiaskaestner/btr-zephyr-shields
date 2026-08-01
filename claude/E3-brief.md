# E3 — lotus board extension, the cross-module case (slice brief)

Status: sequenced (E3 of E1–E4); prereq DECIDED 2026-07-24f (design-log):
**bridle stays OUT of the west manifest.** Lotus builds pass
`-DEXTRA_ZEPHYR_MODULES=<west-topdir>/bridle` explicitly — deliberately
the stronger test: module membership from a bare cmake cache variable,
nothing tied to west. E4 (delete all four clones) is NOT this slice.

## Target

| clone | base (BRIDLE module, `/wrk/z/ws-up/bridle`) | extension dir | rigs |
|---|---|---|---|
| `seeeduino_lotus_btr` | `boards/seeed/seeeduino_lotus/` (board `seeeduino_lotus`, soc `samd21g18a`, no variants) | `boards/extend/seeed/seeeduino_lotus/` | lotus-pwm, lotus-buttons, lotus-pwm-clash |

New target: `seeeduino_lotus/samd21g18a/rig`. E1/E2 are the templates
(`boards/extend/st/nucleo_f401re/`, `boards/extend/mikroe/quail/`).

## E3-specific check items (the clone is NOT a base-include like E1/E2's)

The lotus clone is a STANDALONE dts rewrite, so porting is not purely
mechanical. Before authoring, establish for each of these whether the
extension needs to carry anything:
1. **Socket layer**: `grove_sockets_btr.dtsi` ports to the extension
   (same labels/wiring) — the straightforward part.
2. **Pinctrl**: diff the clone's `seeeduino_lotus_btr-pinctrl.dtsi`
   against bridle's `seeeduino_lotus-pinctrl.dtsi`. If identical, the
   extension carries nothing (base provides it). If the clone ADDED
   entries the sockets/rigs need, only the additions move. Report the
   diff result either way.
3. **`pre_dt_board.cmake`** in the clone (the other clones have none):
   read it, determine whether it is load-bearing for rig builds, and
   whether bridle's base board has its own. An extension dir is part of
   BOARD_DIRECTORIES, but zephyr_default includes `${BOARD_DIR}/
   pre_dt_board.cmake` — BOARD_DIR only (directories[0] = the BASE dir).
   If the clone's hook matters, that is a finding to report, not
   something to hack around.
4. **Kconfig**: the clone has `Kconfig.seeeduino_lotus_btr` +
   `Kconfig.defconfig`. hwm_v2's kconfig_gen globs ALL of
   BOARD_DIRECTORIES, so an extension MAY carry Kconfig fragments —
   determine whether the clone's content is (a) copied base content
   (base provides it — carry nothing), or (b) clone-specific and
   load-bearing (port the delta). Report which.
5. **Clone identity divergences** (uartcons compatible/model strings, any
   deliberate content edits vs bridle's base): these REVERT to the
   base's — expected golden churn, class 2.

## Harness changes (thread the module flag, self-located)

- conftest gains the bridle root SELF-LOCATED as `WEST_TOPDIR / "bridle"`
  (no /wrk literals; fail with a clear message if absent).
- Lotus corpus cases must pass `-DEXTRA_ZEPHYR_MODULES=<that path>`
  through EVERY build path: tier-2 `_run_build` (west build-rig), the
  plain-build harness (test_board_read / cached recipes), and any
  cmake-alone invocation. Case-level mechanism (e.g. a RigCase/board
  keyed extra-defines table), not a global flag — non-lotus builds must
  NOT get the module (their goldens must stay byte-identical, proving
  the no-flavor-leak property).
- Pass-1 recipe: the extension dts `#include "seeeduino_lotus.dts"`
  resolves via BOARD_DIRECTORIES (in-build: the boards-fork guard +
  the dts fork's --include-dir loop; standalone tier-1: whatever
  mechanism E1/E2 already use for the base-dir include — follow that
  precedent, verify it copes with the base dir living under bridle).

## Golden churn classes (a refreeze IS expected, lotus rigs only)

1. context.cmake: RIG_BOARD + board-dts path (+ bridle-side dep paths —
   the base dts and anything it includes are real pass-1 reads; they
   normalize under <WEST_TOPDIR>).
2. tier-2 zephyr.dts: re-inherited bridle base content the clone dropped
   (EXPECT A BIG +N: the base pulls 13 grove/arduino legacy connector
   dtsis) + identity strings reverting + provenance paths. Verify with
   dts_equiv old-vs-new: shared nodes byte-identical, zero removed —
   anything else STOP and report (a shared-node property diff means the
   clone deliberately diverged somewhere check-item 2/4/5 missed).
3. tier-1: board-name header lines; socket content byte-identical.
Non-lotus goldens: byte-untouched.

## Acceptance criteria

1. Full gate green post-refreeze (classification in the report); mypy
   clean; exemptions only shrink.
2. lotus-pwm + lotus-buttons full-link on the new target (west build-rig
   with the module define); lotus-pwm-clash rejects with intact
   phys-channel.
3. cmake-alone, west-free: `cmake -DRIG=lotus-pwm
   -DEXTRA_ZEPHYR_MODULES=<topdir>/bridle` (+Python3_EXECUTABLE, PATH
   stripped of west) configures; slot-10 inference resolves the new
   target.
4. The DOCUMENTED failure mode: `cmake -DRIG=lotus-pwm` WITHOUT the
   module define fails (no board `seeeduino_lotus`) — capture the actual
   diagnostic in the report; it is the accepted cost of the
   no-manifest-entry decision, not something to fix.
5. Plain `-b seeeduino_lotus` (with the define) is upstream-bridle-pure
   (grep-clean of socket/btr content); the clone still builds WITHOUT
   any define, unchanged.
6. Gotcha guard: no literal `*/` inside any DTS block comment in new
   files (E2's parse trap).
