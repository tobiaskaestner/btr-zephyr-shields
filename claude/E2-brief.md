# E2 — quail + frdm board extensions (slice brief)

Status: sequenced in NEXT-SESSION (E2 of E1–E4). E1 is the LIVE TEMPLATE:
`boards/extend/st/nucleo_f401re/` (landed `4db27bc`) + the design record
`board-extension-migration.md`. E2 repeats that pattern for the two
remaining zephyr-based clones. E3 (lotus, base in bridle) and E4 (delete
all four clones) are NOT this slice — the clones stay.

## Targets

| clone (btr-shields) | base (zephyr tree) | extension dir | rigs to migrate |
|---|---|---|---|
| `mikroe_quail_btr` | `boards/mikroe/quail/` (board name `mikroe_quail`) | `boards/extend/mikroe/quail/` | quail-temp-farm (s5), quail-sockets (s4b-sockets), s4b-dup-addr's reject rig |
| `frdm_k64f_btr` | `boards/nxp/frdm_k64f/` | `boards/extend/nxp/frdm_k64f/` | frdm-eth-nest (s6-eth-click), frdm-cs-clash (s6-cross-layer) |

Per extension, mirror E1's file set exactly: `board.yml` (`extend:` +
`rig` variant under the base's soc qualifier — read the BASE board.yml
for the qualifier, don't guess), `<board>_<qualifiers>_rig.dts`
(#include the base board's own .dts — the boards-fork -isystem guard
makes the sibling-dir include resolve, for rig AND plain builds),
`<...>_rig.yaml` (twister metadata, E1-shaped), `<...>_rig_defconfig`,
and a socket dtsi carrying the typed `socket,*` nodes PORTED from the
clone (same labels, same wiring — the clone is the reference; keep its
load-bearing bus config facts in mind: the QUAIL clone's SPI3 flash and
any status/pinctrl the sockets depend on come from the BASE now, verify
they're actually there upstream, report if not).

Then repoint the five rig.yml `board:` lines to the new targets
(`mikroe_quail/<soc>/rig`, `frdm_k64f/<soc>/rig`).

## Goldens — a REFREEZE IS EXPECTED (unlike the last two slices)

Switching a rig's board from the cleaned clone to base+extension changes
real content: the extension INHERITS the upstream base (including legacy
connector nexus nodes the clone had deliberately removed) and ADDS the
typed sockets. E1 set the precedent. Expected churn classes for the five
migrated rigs' goldens:
1. `context.cmake`: RIG_BOARD string + the board-dts path in RIG_DEPENDS.
2. tier-2 `zephyr.dts`: re-inherited upstream base content (legacy
   nexuses, anything else the clone diverged on — e.g. the clone's own
   model/compatible strings like `mikroe,stm32-e427-btr` revert to the
   base's), plus provenance path comments.
3. tier-1 `rig-gen.overlay` / `config-sheet.md`: should be STABLE if the
   extension's socket nodes replicate the clone's labels exactly; if they
   move, the diff must be explainable by the board switch alone.
Run `RIGEXP_REFREEZE=1`, then CLASSIFY the diff into those classes and
include the classification in your report. Anything outside them → STOP
and report. Goldens of non-migrated rigs (nucleo, lotus) must be
byte-untouched.

## Acceptance criteria

1. Full gate green after the refreeze; mypy clean; exemption list only
   shrinks.
2. Accept rigs full-link on the new targets (`west build-rig`
   quail-temp-farm + frdm-eth-nest); both reject rigs still reject at
   configure with their exact phys-* diagnostics (phys-addr for
   s4b-dup-addr, phys-cs for frdm-cs-clash).
3. cmake-alone entry works for one migrated rig (bare `cmake
   -DRIG=quail-temp-farm`, no -DBOARD — the slot-10 inference must
   resolve the new extension target).
4. Plain builds unaffected: `west build -b mikroe_quail` and
   `-b frdm_k64f/mk64f12` (base targets, no rig) configure exactly as
   upstream; the clones (`mikroe_quail_btr`, `frdm_k64f_btr`) still
   build as before (E4 deletes them, not E2).
5. Golden-diff classification per above, in the report.
