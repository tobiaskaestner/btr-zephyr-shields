# 3-cell PWM controllers — backlog item 34

**Status:** briefed 2026-08-14, ready to dispatch. Backlog item 34.
**Blocks item 36 (L4-PWM)**, which cannot start until this lands.

## 1. Why this is not an edge case

`rigc/board_edt.py::_project_channel_map` supports exactly one PWM nexus
shape: a 2-cell `(channel, period)` parent. Since `88e53fc` anything else
is a loud `phys-board` diagnostic instead of a `ValueError` traceback —
but a diagnostic is still a refusal.

A survey of upstream Zephyr's PWM bindings:

- **55 of 75 declare THREE `pwm-cells`** — `(channel, period, flags)`.
- Only **7 declare two**, and `seeeduino_lotus`'s `atmel,sam0-tcc-pwm` is
  one of the 7.

lotus is the tree's only PWM-capable board, so the 2-cell assumption has
never been tested against the norm. **Both twister platforms are 3-cell**
(`st,stm32-pwm`, `nxp,ftm-pwm`), which is exactly why item 36 is blocked.

ADC needs nothing here: 107 of 108 `io-channel-cells` declarations are a
single cell, both twister boards included. **Do not widen ADC.** Keep its
checked read exactly as strict as it is.

## 2. What is ALREADY done — verify, do not rewrite

Three pieces of `88e53fc` were built general and are believed
3-cell-ready. **Confirm each by reading and by test, and say so.** If one
turns out not to be, that is a finding, not a failure.

- `rigc/emitter/overlay.py::_channel_nexus_block` already derives
  mask/pass-thru/row shape from an arbitrary `cells` — "cell 0 matched,
  cells 1..N-1 passed through". A carrier's synthesized nexus should
  already render correctly at 3.
- `rigc/model.py::BoardSocket.pwm_cells` already exists and is already
  carried through `rigc/analyzer/sockets.py::_compose_channel_map`'s
  require-and-check.
- The SHIELD side already speaks 3 cells: `grove_servo` and
  `grove_pwm_led` both declare `#pwm-cells = <3>` on their plug and write
  `pwms = <&plug SIG0 20000000 PWM_POLARITY_NORMAL>`, and `GpioRef`
  already carries `period` and `flags` separately. No shield-side change
  is expected. **Determine whether the plug's own declared count is read
  anywhere** (`rigc/shields.py::_parse_pos_ref`) and report what you find
  — this brief does not know.

So the slice is narrower than it sounds: the board read, the emitted ref,
and one conditional refusal.

## 3. What to change

**a. `rigc/board_edt.py` — accept 2 or 3 for PWM.** `_CHANNEL_FN`'s
single `supported` count becomes a supported SET per function: `{2, 3}`
for pwm, `{1}` for adc. `_project_channel_map` records the ACTUAL count
in `BoardSocket.pwm_cells` rather than a constant. An unsupported count
keeps today's `LoadError`/`phys-board` shape and wording (it is good) —
only the accepted set widens.

**RULED: child and parent counts must be EQUAL.** A nexus can in
principle translate between specifier widths, but the mask/pass-thru
idiom every real socket uses requires them aligned, and nothing in
upstream or bridle does otherwise. Refuse a disagreement loudly with both
numbers named, the same way the carrier's own require-and-check does.

**b. `rigc/emitter/overlay.py::_render_ref` — emit the socket's count.**
Today the pwm branch renders `<&nexus pos period>` unconditionally and
`raise AssertionError` on nonzero flags, with a long comment explaining
that a third cell would be parsed as a bogus trailing phandle-array
element. That comment is correct FOR A 2-CELL SOCKET and becomes wrong
for a 3-cell one — rewrite it, do not leave it contradicting the code.
A 3-cell socket renders `<&nexus pos period flags>`.

If a shield's plug declares fewer cells than the socket (no shield does
today), emit `0` for the missing trailing cells rather than crashing.
Say in the report whether that path is reachable.

**c. `rigc/analyzer/gpio.py::_collect_channel` — the flags refusal
becomes CONDITIONAL.** It currently refuses ANY nonzero PWM flags with
"the expander's PWM emission carries only (position, period) — there is
no cell for flags". That sentence is a statement about the expander; it
must become a statement about THIS SOCKET: refuse on a 2-cell socket
(there is genuinely nowhere to put it), carry on a 3-cell one. Name the
socket and its cell count in the refusal.

**This moves a golden.** `scripts/rigc/tests/fixtures/boards/rigs/pwm-nonzero-flags/`
is a reject fixture on a real 2-cell Grove socket; it must still be
refused, but its message changes. Hand-edit
(`RIGC_REFREEZE=1` is BLOCKED) and verify BOTH ways: failing before,
passing after. Check whether any OTHER golden quotes the old sentence.

## 4. `invert:` — recommended, flagged for veto

`_render_ref`'s gpio branch applies `inst.invert` as an XOR on the
active-level flag bit, and its comment states plainly that invert is
GPIO-only and a pwm/adc ref's own value "means something else entirely".
Once a flags cell can actually be carried, a reader will ask whether
`invert: true` on a PWM instance should flip `PWM_POLARITY`.

**Recommended: NO — keep `invert:` GPIO-only.** It is bridle's `_inv`
axis for the active level of a digital line; PWM polarity is a different
property, authored by the shield in its own ref, and silently coupling
them would make one rig key mean two unrelated things depending on the
device's function. Keep the behaviour, and UPDATE the comment to say the
restriction is now deliberate rather than forced — today a reader could
reasonably conclude invert is excluded only because there was no cell.

**Flagged for veto.** If you disagree, do not just implement the other
choice — say so in the report with the reason.

## 5. The witness

A 3-cell PWM board that this repo controls. **Author a NEW fixture
board**, following `scripts/rigc/tests/fixtures/boards/mainboards/carrier_analog_board.dts`'s
fresh precedent.

**Do NOT add a 3-cell socket to
`scripts/rigc/tests/fixtures/boards/fixture_board.dts`.** Its
`#pwm-cells = <2>` sockets are used by many rigs, and `zephyr.dts`
goldens contain the whole board — adding a node there would move every
golden for every rig on that board, for no reason connected to this
slice. This is the trap in this brief; do not walk into it.

Cover, with real emitted overlays rather than reasoning:

1. A plain shield (`grove_servo`-shaped) on a 3-cell board socket,
   emitting `pwms = <&socket pos period flags>` — four words, flags
   present.
2. The same through a CARRIER-exposed socket, proving §2's claim that
   `_channel_nexus_block` already generalizes: the synthesized nexus
   declares `#pwm-cells = <3>`, mask `<0xffffffff 0 0>`, pass-thru
   `<0 0xffffffff 0xffffffff>`, rows of 7 words.
3. A NONZERO flags ref accepted on the 3-cell socket and still refused on
   a 2-cell one — the pair is the whole point of §3c, and one without the
   other proves nothing.
4. §3a's child/parent mismatch refused.
5. A 4-cell (or other unsupported) PWM parent still refused with the
   existing `phys-board` wording.

## 6. Acceptance criteria

1. A 3-cell PWM controller resolves end to end, proven by an emitted
   overlay containing a four-word `pwms` property.
2. The same works through a carrier, with the synthesized nexus at
   `#pwm-cells = <3>`. State whether `_channel_nexus_block` needed any
   change (§2) — either answer is fine, an unstated one is not.
3. Nonzero PWM flags: carried on a 3-cell socket, refused on a 2-cell
   one, refusal naming the socket and its count.
4. `pwm-nonzero-flags`'s golden hand-edited and verified both ways; every
   OTHER golden byte-unchanged — `lotus_pwm`'s and `lotus_pwm_led`'s
   especially, since lotus is 2-cell and nothing about it may change.
   State as a checked result.
5. ADC untouched and still strict at exactly 1 cell (§1).
6. §4 answered explicitly, whichever way.
7. `dts/bindings/connectors/arduino-r3.yaml` and both
   `arduino_r3_socket.dtsi` untouched — that is item 36's work, not
   this slice's. `git status` proves it.
8. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **749**, integration **277**, coverage **93%** (2026-08-14, `88e53fc`).
   Re-derive rather than carry.

## 7. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criterion 4). Confirm
its `@pytest.mark.build` marking before claiming it. The driver runs the
full gate once, after review.

Brief the reviewer to MUTATION-CHECK: hardcode `_render_ref`'s pwm branch
back to two cells — criterion 1's test must fail on the EMITTED CELL
COUNT, not merely somewhere; make the flags refusal unconditional again —
criterion 3's accept case must fail; make it never fire — criterion 3's
2-cell reject must fail on its SENTENCE; widen ADC to accept 2 cells —
criterion 5's test must fail.

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
line numbers and file lists are PREDICTIONS — re-derive them. Trace every
reader by grep AND run. Run negative controls IN-TREE. Purge
`__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. When you name a function
in your report, qualify it as `path/to/module.py::function_name`.
Dispatch as `general-purpose` on **sonnet** from a session rooted at
`/wrk/z/ws-up`.
