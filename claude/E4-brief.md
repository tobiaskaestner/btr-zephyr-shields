# E4 — delete the four board clones (slice brief)

Status: final step of the E1–E3 extension migration. Precondition: E3
landed (lotus on `seeeduino_lotus/samd21g18a/rig`). The test-suite
de-provenance sweep is NOT this slice (it follows as its own, text-only
slice — two cleanly reviewable commits, not one).

## What goes

The four clone board directories, in full (locate them under `boards/`
by their `_btr` names; each carries board.yml, dts, pinctrl, Kconfig,
defconfig, yaml, doc/, support/, etc.):
`nucleo_f401re_btr`, `mikroe_quail_btr`, `frdm_k64f_btr`,
`seeeduino_lotus_btr`.

## The one non-deletion item

The `pwm-nonzero-flags` fixture (scripts/rigexp/tests/fixtures/) still
reads `seeeduino_lotus_btr` directly, and conftest's BOARD_DTS kept the
clone entry for it (E3 report). Repoint it to the extension target
(`seeeduino_lotus/samd21g18a/rig` + its extension dts) — the lotus
tier-1 path already threads bridle via `board_extra_defines`/the E3
harness mechanism, so this is consistency, not new machinery. If the
fixture's expander invocation turns out to need anything the harness
doesn't already provide for lotus, STOP and report rather than
inventing a mechanism.

## Acceptance criteria

1. **Goldens byte-untouched — ZERO refreeze.** No corpus rig references
   a clone; if any golden moves, something is wrong: STOP and report.
   (E4 is the inversion of E2/E3: big diff, no behavior change.)
2. Full gate green; mypy clean; exemptions only shrink.
3. Grep-clean: no `_btr` reference remains in boards/, scripts/,
   cmake/, dts/, include/ (goldens/ and rig-folder comments referencing
   history are fine if factual; update stale ones that claim the clones
   still exist).
4. All four extension targets still configure (`west build --cmake-only`
   each; lotus with the bridle define); one accept rig per board family
   full-links (nucleo-datalogger, quail-temp-farm, frdm-eth-nest,
   lotus-pwm); one reject intact (any).
5. `west boards` (with btr-shields root) no longer lists any `_btr`
   board.
