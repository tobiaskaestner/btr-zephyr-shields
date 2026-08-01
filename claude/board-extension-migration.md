# Board clones → hwmv2 board extensions (design note, 2026-07-23)

**Status: IDEA RATIFIED IN PRINCIPLE (Tobi), spike NOT run.** Replace the
four wholesale `_btr` board clones with hwmv2 **board extensions**: an
out-of-tree `board.yml` `extend: <board>` adding a **`rig` variant**, whose
variant `.dts` includes the REAL upstream board dts + our typed-socket
dtsi. Canonical mechanism example:
`zephyr-rigs/tests/cmake/hwm/board_extend/oot_root/boards/native/
native_sim_extend/` (`board.yml`: `extend` + `variants: [{name,
qualifier}]`; files `<board>_<qualifier>_<variant>.dts/.yaml/_defconfig`).
Target name becomes e.g. `nucleo_f401re/stm32f401xe/rig`.

## Why this wins

1. **Clone drift becomes impossible.** The frdm five-wrong-pins bug
   (f99ec63) was clone drift; with extensions the base board content comes
   from upstream at build time — we maintain ONLY the socket layer.
2. **The parked legacy-compat item dissolves.** Plain `nucleo_f401re`
   stays untouched for `-b`/`--shield` users; the rig variant is purely
   additive opt-in. No `#ifndef RIG_BUILD` guards, no auto-synthesis
   spike needed (parked.md item superseded if this lands).
3. **THE upstream adoption pattern.** Any module rig-enables any existing
   board without forking it — this is the story the upstream-landing
   milestone wants to tell.
4. **Grammar convergence** with the rig variants/revisions design (board
   target qualifiers and rig qualifiers are the same hwmv2 language).

## Spike to run (before any migration)

Extend `nucleo_f401re` with a `rig` variant in btr-shields; verify:
(i) plain base board builds untouched; (ii) the variant target
cmake-builds with the socket nodes visible in zephyr.dts; (iii) pass-1
reads the VARIANT dts standalone — the variant dts `#include`s the base,
so the recipe's include path must reach the base board dir (check how
dts.cmake resolves DTS_SOURCE for extension variants and whether our
pre_dt mirror + edt.pickle cross-check hold as-is); (iv) an s1-equivalent
rig against `nucleo_f401re/stm32f401xe/rig` expands + builds R2-equivalent
to today's `nucleo_f401re_btr` golden; (v) same for a bridle-based board
(lotus) — extension across module boundaries; (vi) what the per-variant
Kconfig/defconfig/yaml minimally need.

## Migration shape (post-spike)

Additive: extensions land next to the clones (new board targets), corpus
rigs migrate `board:` per rig with per-rig golden refreezes (board name
appears in context.cmake/config-sheet/zephyr.dts — a justified,
mechanical migration), clones deleted last (one commit, saferail-8
style). Sequencing vs V1/V2: independent axes (V1 = loader delta engine;
this = board layer) — either order works; the spike should come early
since its outcome shapes the upstream story.

## Resolution mechanics (Tobi, 2026-07-23 — RE-USE, never mirror)

For locating the extension variant's dts in pass 1: rig.cmake consumes
boards.cmake's already-computed outputs (it runs before shields.cmake) +
zephyr's own `zephyr_build_string()` helper — the same call dts.cmake
makes. No hand-mirrored resolution logic; the edt.pickle cross-check
stays the equivalence guard.

**Endgame option (recorded, not for E1): fork the `dts` module.** Our
`cmake-modules:` PATH-prepend already makes `include(shields)` resolve to
our fork — the same trick can fork `dts`: compute exactly what the real
dts.cmake computes (at dts-time even `include(pre_dt)` is safe —
ARCH_V2_NAME_LIST exists), run the expander, then delegate to the real
module. That would dissolve BOTH remaining mirrors (the pre_dt include-dir
derivation in rig.cmake AND any dts-file resolution) in one move.
Candidate for a post-E4 refactor once the extension migration proves out.

## Open questions

- Variant naming: `rig` (recommended — reads as intent) vs `btr`.
- Do the extension variants KEEP the base board's legacy connector nexus
  nodes (they come along via the base include — harmless, and closer to
  what a converted upstream board looks like) — presumably yes, ending
  the lean-clone deletion approach of a46cec9/b02bdc7 for extensions.
- rig.yml `board:` strings grow qualifiers — decide whether rigs must
  name the FULL target (`nucleo_f401re/stm32f401xe/rig`) or the expander
  appends the rig variant automatically (sugar; leaning full-and-explicit
  first).
- Tests' BOARD_DTS map + plain-build fixtures per-variant targets.
