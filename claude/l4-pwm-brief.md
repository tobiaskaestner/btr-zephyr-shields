# L4-PWM — a PWM nexus on the Arduino R3 connector and both boards

**Status:** briefed 2026-08-14, ready to dispatch. Backlog item 36, the
last of the L4 pair. Unblocked by item 34 (`0373cd2`): both boards'
controllers are 3-cell (`st,stm32-pwm`, `nxp,ftm-pwm`) and rigc now
supports that shape.

Sequenced AFTER item 35 deliberately, and 35's landed work is the
template for this one — read its diff before starting.

## 1. Scope

1. `dts/bindings/connectors/arduino-r3.yaml` gains `pwm-map`,
   `pwm-map-mask`, `pwm-map-pass-thru` and `#pwm-cells`, alongside the
   ADC nexus properties item 35 just added. Copy
   `dts/bindings/connectors/grove.yaml`'s shape; do not invent one.
2. `boards/extend/st/nucleo_f401re/arduino_r3_socket.dtsi` and
   `boards/extend/nxp/frdm_k64f/arduino_r3_socket.dtsi` each gain a real
   `pwm-map` over the digital positions their SoC can actually drive with
   a timer.
3. A corpus rig and a twister suite proving `grove_pwm_led` resolves
   through a carrier-exposed Grove socket on a real board.

**This is the harder half of L4, and the difficulty is entirely in the
board facts** — the rigc side is done.

## 2. Read item 35's diff first

Item 35 solved the same problem one function narrower: same two binding
files, same two board sockets, same corpus-wide golden movement, same
hand-regeneration method. **Its landed diff is your template.** Anything
this brief describes that contradicts what 35 actually did, 35 wins —
say so in the report.

In particular, §2 of `claude/l4-adc-brief.md` on golden regeneration
applies here verbatim and is not repeated in full: `RIGC_REFREEZE=1` is
BLOCKED; regenerate by hand using the harness's own `normalize()` /
`normalize_dts_provenance()` under pytest's DEFAULT basetemp; grep every
regenerated file for `pytest-of` and for your own scratch path, because
`dts_equiv` ignores comments and would not catch a leaked path. **The
diff review is the deliverable**: every moved golden shows only the PWM
nexus addition.

## 3. The board facts

**Verified by reading upstream** (`zephyr/boards/st/nucleo_f401re/arduino_r3_connector.dtsi`,
`zephyr/boards/nxp/frdm_k64f/frdm_k64f.dts`) — these pin assignments are
facts:

| position | nucleo_f401re | frdm_k64f |
|---|---|---|
| D2 | PA10 | PTB9 |
| D3 | PB3 | PTA1 |
| D4 | PB5 | PTB23 |
| D5 | PB4 | PTA2 |
| D6 | PB10 | PTC2 |
| D7 | PA8 | PTC3 |
| D8 | PA9 | PTC12 *(HW Rev E+)* |
| D9 | PC7 | PTC4 |
| D10 | PB6 | PTD0 |
| D11 | PA7 | PTD2 |
| D12 | PA6 | PTD3 |
| D13 | PA5 | PTD1 |

**NOT given, and this is the slice's real research**: which timer and
which channel each pin reaches, and whether a given pin is
timer-capable at all. Derive from the SoC's own sources — the STM32
`tim<N>_ch<M>_p<x><n>` pinctrl definitions, the Kinetis
`FTM<n>_CH<m>_PT<x><n>` pinmux macros. **Never from this table, never
from memory, and never by analogy with another board in the same
family.** Name your source for every channel in the report.

**Declare only the positions you can source.** A socket exposes the
subset it wires, declared by absence — the rule
`arduino_r3_socket.dtsi` already applies to `socket,uart`. A partial
`pwm-map` is correct and expected; several Arduino digital positions on
either board will not be timer-capable, and inventing a channel to fill
the table is the failure mode this paragraph exists to prevent.

**Expect multiple parents.** Different positions will reach different
timers (`&tim1`/`&tim2`/`&tim3` on nucleo; `&ftm0`/`&ftm3` on k64f).
Each `pwm-map` row carries its own phandle and
`rigc/board_edt.py::_project_channel_map` reads `entry.parent` per
entry, so this works — item 35 should have already proven the
multi-parent case for ADC. Confirm it holds for PWM too rather than
assuming the ADC result transfers.

**Cell count**: both boards' controllers declare THREE `pwm-cells`
(`st,stm32-pwm`, `nxp,ftm-pwm` — verified). So each socket nexus
declares `#pwm-cells = <3>`, mask `<0xffffffff 0x00000000 0x00000000>`,
pass-thru `<0x00000000 0xffffffff 0xffffffff>`, and rows of seven words.
`rigc/analyzer/gpio.py::_collect_channel` will now CARRY a nonzero flags
cell on these sockets rather than refuse it — that is item 34's whole
point, and it is worth one test here on a real board rather than only on
the fixture.

## 4. Pin-mux is board-provided and stays stubbed

Same ruling as item 35 §4. rigc treats pin-mux as the board's business
and emits a config-sheet note saying so. **Do not author pinctrl groups
for the timer pins.** A `--build-only` twister run does not need them,
and inventing them is board work with no upstream fact behind it — the
reasoning that kept a NanoC6 `pwm-map` out of the `grove_pwm_led` slice
and analog pinctrl out of item 35. Note the limitation in the rig's own
comment.

## 5. The witness

`grove_pwm_led` through a carrier-exposed Grove socket, on a real board.
This is the first time that shield runs anywhere but `seeeduino_lotus`,
which is not a twister platform — so this slice is what finally gives it
CI coverage.

Pick a carrier Grove connector whose SIG0 lands on a timer-capable
position (§3 decides which). Say which you picked and why; if no Grove
connector on either carrier reaches a timer-capable pin, **stop and
report that** — it would mean the payoff needs a different carrier
connector or a different shield, and it is a finding, not something to
engineer around.

Plus a twister suite, `--build-only`, on whichever platforms end up with
a usable PWM position. `tests/rigs/nucleo_grove_farm/` is the pattern.

## 6. Acceptance criteria

1. `arduino-r3.yaml` declares the PWM nexus properties, shaped like
   `grove.yaml`'s, alongside item 35's ADC ones.
2. Both board sockets declare a real `pwm-map` where the SoC supports
   one; every timer and channel sourced, and the source named.
3. `grove_pwm_led` resolves through a carrier-exposed Grove socket on a
   real board, proven by an emitted overlay with a four-word `pwms` and
   `&tim… { status = "okay"; };` (or the FTM equivalent).
4. A twister suite building clean (`--build-only`), run and reported.
5. A nonzero PWM flags value carried on one of these real 3-cell
   sockets — item 34's capability, exercised on real hardware
   definitions rather than only a fixture.
6. **Every moved golden accounted for**, only the PWM nexus changed in
   each, no `pytest-of` or scratch path anywhere (§2).
7. Item 35's ADC nexus still present and working — this slice adds to
   the same nodes and must not disturb it. State as a checked result.
8. Full gate green, driver-run. Re-derive the baseline from the tree
   rather than carrying a number from this brief.

## 7. Reduced verification contract

Implementor: mypy + unit + non-build integration + **`test_emitted_corpus.py`
AND `test_resolved_corpus.py`** — both, as in item 35, because this
slice moves goldens corpus-wide. Confirm their `@pytest.mark.build`
marking. The driver runs the full gate.

Brief the reviewer to MUTATION-CHECK: change one channel number in a
board socket's `pwm-map` — a golden must fail on the RESOLVED channel,
not merely somewhere; set one socket's `#pwm-cells` to `<2>` while its
controller stays 3-cell — item 34's equality check must refuse it,
naming both counts; drop the PWM properties from `arduino-r3.yaml` — the
board load must fail loudly (an undeclared property on a bound node is a
hard EDTError).

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
pin table is verified; its channel numbers are deliberately absent and
its golden list is a PREDICTION — re-derive them. Run negative controls
IN-TREE. Purge `__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. When you name a function
in your report, qualify it as `path/to/module.py::function_name`.
Dispatch as `general-purpose` on **sonnet** from a session rooted at
`/wrk/z/ws-up`.
