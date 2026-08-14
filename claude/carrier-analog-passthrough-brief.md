# PWM and ADC through a carrier — the L1–L3 model sweep

**Status:** briefed 2026-08-14, ready to dispatch. Closes the model half
of backlog item 33, found by the grove base-carrier slice (`d16fb7c`).
The enablement half (L4 — `arduino-r3.yaml` and the two board sockets)
is explicitly NOT in this slice; see §7.

## 1. The gap, in one sentence

A carrier can pass GPIO and buses through an exposed socket, but not PWM
or ADC — so a shield that needs either works on a real board socket and
is refused on a carrier-exposed one, with no code path in between.

Reproduce the refusal: put `grove_light` on
`nucleo_grove_farm`'s `grove_1.grove_a0` and you get

```
error[phys-function]: 'light_a/light: io-channels' uses position SIG0 as
ADC, but socket 'grove_1.grove_a0' offers no adc on it (no
socket,adc-map entry)
```

The positive control is already frozen in the corpus:
`scripts/rigc/tests/goldens/lotus_pwm/rig-gen.overlay:9` emits
`io-channels = <&grove_a0 0>;` for the same shield on `seeeduino_lotus`'s
REAL `grove_a0`. Same shield, same function, working. The gap is the
composition path and nothing else.

## 2. Three layers, all in one sweep — this is ruled, not open

| L | Where | Today |
|---|---|---|
| L1 | `rigc/shields.py::_parse_exposed`, `rigc/model.py::ExposedSocket` | Reads only `gpio-map`, `socket,<bus>`, `socket,cs-pool`, `shield,channel`. No field could hold a map. |
| L2 | `rigc/analyzer/sockets.py::compose_socket` | Builds `gpio_map`, `buses`, `nexus_rows`. Never writes `pwm_map`/`adc_map`. |
| L3 | `rigc/emitter/overlay.py`, the synthesized-nexus block (~line 400-430) | Emits a gpio-only nexus: hardcoded `#gpio-cells = <2>` and rows `<child 0 &parent ppos 0>`. |

**PWM and ADC go together, in one slice.** They are already unified
everywhere downstream, so splitting them means writing the same diff
twice against the same three functions:

- `rigc/model.py::BoardSocket.pwm_map` and `.adc_map` are the same type.
- `rigc/board_edt.py::_project_socket` fills both in adjacent,
  near-identical loops.
- `rigc/analyzer/gpio.py::_collect_channel` already collapses them to one
  line: `fmap = socket.pwm_map if fn == "pwm" else socket.adc_map`.
- `rigc/emitter/overlay.py::_render_ref` already branches gpio/pwm/adc in
  exactly one place (landed `b16c314`).

And the decisive reason: doing one without the other leaves
`compose_socket` with a branch for one function and a silent hole for the
other. That is the exact shape of the bug `b16c314` fixed, where
`_device_node` had the `ref.function` branch and `_collection_entry`
did not, and the result was a silently-valid zero-period PWM rather than
an error. Do not recreate it.

## 3. THE CELL-COUNT QUESTION — read this before designing anything

Three different things are spelled `#pwm-cells`, at three layers, and
confusing them is the main way this slice can go wrong.

**a. The controller.** Zephyr's generic PWM consumer form is THREE cells
— (channel, period, flags). But `seeeduino_lotus`'s `&tcc0` overrides to
TWO (channel, period; no flags) via `atmel,sam0-tcc-pwm`. That is an
SoC fact, not ours, and it varies per board.

**b. The board socket nexus.** `boards/extend/seeed/seeeduino_lotus/grove_sockets.dtsi`:

```dts
grove_d2: connector_grove_d2 {
	#pwm-cells = <2>;
	pwm-map-mask      = <0xffffffff 0x00000000>;
	pwm-map-pass-thru = <0x00000000 0xffffffff>;
	pwm-map = <GROVE_SIG0 0 &tcc0 0 0>, <GROVE_SIG1 0 &tcc0 1 0>;
};
```

It matches its parent's count. The mask/pass-thru pair is the whole
trick: **cell 1 (position) is matched, cell 2 (period) is passed through
untouched.** The socket says "address me by position; whatever period you
name rides through to the controller." ADC is the same idea one cell
narrower — `#io-channel-cells = <1>`, mask `<0xffffffff>`, pass-thru
`<0x00000000>`, nothing to carry.

**c. The shield plug.** `boards/shields/grove_led/grove_pwm_led.shield`
declares `#pwm-cells = <3>` on `gpl_plug` and writes
`pwms = <&gpl_plug GROVE_SIG0 20000000 PWM_POLARITY_NORMAL>`. **This is
not a DT node dtc ever sees** — a plug is a template placeholder. It is
the shield author's dialect: the generic 3-cell consumer form.

**So it is not one property with two values. It is two vocabularies
meeting, and `rigc` is the translator.**
`rigc/shields.py::_parse_pos_ref` reads the 3-cell shield form into
`GpioRef(position, period, flags)`;
`rigc/emitter/overlay.py::_render_ref` writes the socket's form —
`<&nexus pos period>` — and refuses a nonzero flags cell (the analyzer
already rejects those upstream as `phys-function`).

**Where the real defect is.** Because lotus is the only PWM-capable board
in the tree, "the socket's form" has only ever been 2 cells, and that
assumption lives in one destructuring line in
`rigc/board_edt.py::_project_socket`:

```python
pos, _pos_period = entry.child_specifiers
channel, _channel_period = entry.parent_specifiers
```

A board whose PWM controller uses Zephyr's standard THREE cells makes
that raise `ValueError: too many values to unpack` — a traceback, not a
diagnostic. ADC has the same shape one cell narrower:
`(pos,) = entry.child_specifiers`.

**Consequence for this slice, and it is the load-bearing one: a carrier
does not get to choose its cell count.** The synthesized nexus's
`pwm-map` parent specifiers must match the parent nexus's own
`#pwm-cells`, and a pass-through wants the child form to match too. The
carrier INHERITS the count from whatever board it lands on.

And `rigc/model.py::BoardSocket` **cannot express that today** — the
period cell is discarded in `_project_socket` (`_pos_period`,
`_channel_period`), so nothing downstream knows whether the parent was
2-cell or 3-cell. L2 therefore has to KEEP the parent's cell count, not
just the map. That is a `BoardSocket` field this slice must add, and it
is the piece most likely to be missed.

## 4. Rulings

1. **PWM and ADC in one slice** (§2). Not negotiable — a half-done branch
   here is the `b16c314` bug again.
2. **A PWM/ADC row whose parent does not route it is an ERROR, not a
   silent drop** (Tobi, 2026-08-14). `compose_socket`'s gpio branch
   currently drops such a row — "parent fragment doesn't route it ->
   stays socket-local (net key)" — and for GPIO that is correct, because
   a socket-local net is a meaningful thing. For an analog position it is
   not: a pin with no controller behind it is not a net, it is a mistake.
   Use `phys-subset` if its sentence fits (it already covers "the parent
   offers no socket,i2c"); introduce a new code only if it does not, and
   say which you chose and why.
3. **The 3-cell parent is OUT OF SCOPE but must not stay a traceback.**
   Do not build 3-cell support. Do convert `_project_socket`'s two
   destructuring lines into a checked read that emits a diagnostic naming
   the socket and its cell count. A `ValueError` traceback is the M8
   family of defect (`post-cutover-backlog.md` item 3) and this slice is
   where it becomes visible.

## 5. What to change

**L1 — parse and model.**
`rigc/model.py::ExposedSocket` gains map fields for pwm and adc, shaped
like `gpio_map`'s `Dict[int, Tuple[str, int, int]]` (position -> slot,
parent position, ...) — pick the shape that mirrors the gpio field
rather than inventing a third convention.
`rigc/shields.py::_parse_exposed` learns to read `pwm-map` and
`io-channel-map` exactly as it already reads `gpio-map`, including the
same "parent must be one of the carrier's plugs" check (`lang-exposed`).
**Note the stride differs**: with `#pwm-cells = <2>` a row is 5 words
(2 child + phandle + 2 parent); with `#io-channel-cells = <1>` it is 3.
Derive the stride from the declared cell counts; do not hardcode 5 and 3.

**RULED (Tobi, 2026-08-14): REQUIRE AND CHECK.** The
`#pwm-cells`/`#io-channel-cells` a carrier author writes in the `.shield`
file is mandatory alongside the corresponding map, and the analyzer
refuses a mismatch against the resolved parent's own count. This is
`shield,plugs`'s shape: the shield states a claim, the board carries the
fact, and a disagreement is a loud error rather than one side silently
winning.

Concretely, three things follow, and all three are in scope:

- An exposed node with `pwm-map` but no `#pwm-cells` (or `io-channel-map`
  without `#io-channel-cells`) is a parse-time error — `lang-exposed`
  fits, since it already covers malformed exposed nodes. So is the
  reverse pairing if it is cheap to detect.
- `ExposedSocket` gains the declared count per function; it is what §5's
  stride is derived from, so the parse does not need to guess.
- At composition, a declared count that differs from the resolved
  parent's is refused with a sentence naming BOTH numbers and both
  sides — the carrier's shield name and the parent socket's label. A
  reader must be able to tell which one to change without opening either
  file. `phys-subset` is the likely code (it already carries "the parent
  does not offer what the carrier claims"); confirm its sentence fits or
  introduce a new one, and say which you chose.

The grove carriers already write `#io-channel-cells = <1>` on their
`grove_a*` nodes (`boards/shields/grove/seeed_grove_base_v{1,2}.shield`),
so they satisfy the new requirement as authored — verify that rather
than assuming it, and if they do not, fix them here.

**L2 — compose.**
`rigc/analyzer/sockets.py::compose_socket` gains a pass-through branch
per function, mirroring the existing `gpio_map` loop (lines ~105-112),
NOT the bus loop — PWM/ADC pass-through is BY POSITION, like gpio, not
by kind, like i2c/spi/uart. It must produce both the composed
`pwm_map`/`adc_map` on the new `BoardSocket` AND the per-function nexus
rows L3 needs, and it must carry the parent's cell count (§3).

Watch: the multi-bus slice's CS-pool regression, where a pass-through
branch leaked the parent's pool into a composed socket of a different
type, is the standing warning that these branches carry non-obvious
state. Do not copy a branch you have not read end to end.

**L3 — emit.**
The synthesized-nexus block in `rigc/emitter/overlay.py` currently emits
one gpio nexus per carrier-exported socket. It must additionally emit
`pwm-map`/`io-channel-map` (with the matching `#pwm-cells`/
`#io-channel-cells` and mask/pass-thru arrays, §3b) on the SAME
synthesized node when the socket carries them, because
`rigc/emitter/overlay.py::_render_ref` already points PWM and ADC refs at
`_nexus(socket)`. Without L3 those refs name a node with no matching map
— a hard EDTError at best.

Its `visit()` skips a socket with no `nexus_rows`; a socket that is
analog-only (rows for adc, none for gpio) must NOT be skipped. Check
that guard.

**The wart, fold it in.** `rigc/analyzer/gpio.py:181` renders
`no socket,{fn}-map entry`, producing `socket,adc-map` / `socket,pwm-map`.
Neither property exists — the real DTS spellings are `io-channel-map`
and `pwm-map`. The diagnostic currently tells the user to add a property
that is not a thing. This moves a reject golden if one quotes it; check,
hand-edit, verify both ways.

## 6. Tests

- **The end-to-end witness**: `grove_light` on a carrier-exposed
  `grove_a*`, emitting resolved `io-channels` through the synthesized
  nexus. This cannot be `nucleo_grove_farm` on `nucleo_f401re` until L4
  lands (§7) — so build it on a FIXTURE board that declares an ADC nexus
  on the connector the carrier plugs.
  `scripts/rigc/tests/fixtures/boards/fixture_board.dts:85-87` already has
  `io-channel-map` on a socket, and
  `scripts/rigc/tests/fixtures/boards/mainboards/singleton_law_board.dts:173-175`
  has one on a grove socket. Use them rather than authoring a new board.
- **The PWM twin of the same witness.** Both functions, both proven.
- **Ruling 2's refusal**: a carrier row whose parent does not route the
  position, refused with its sentence.
- **Ruling 3's diagnostic**: a 3-cell PWM parent produces a diagnostic,
  not a traceback. A synthetic fixture socket is the cheapest witness.
- **Mixed socket**: an exposed socket carrying gpio AND adc rows emits
  one synthesized node with both maps — not two nodes, not one map
  silently winning.

## 7. Explicitly OUT of scope

**L4, the enablement.** `dts/bindings/connectors/arduino-r3.yaml` gaining
`pwm-map`/`io-channel-map`, and `frdm_k64f`'s and `nucleo_f401re`'s own
`arduino_r3_socket.dtsi` gaining a real ADC/PWM nexus, are what finally
let `grove_light`/`grove_pwm_led` resolve through a carrier on a twister
platform. They are TWO further slices, ADC first (a straight
`io-channel-map` from A0-A5, with `grove_light` as an immediate witness)
then PWM (timer-channel selection plus pinctrl alternate-function work,
per SoC: STM32F401 TIM against K64F FTM — different research, different
risk). Ruled separate 2026-08-14.

Do not touch `arduino-r3.yaml` or either board socket in this slice. Its
witnesses are fixture boards (§6).

## 8. Acceptance criteria

1. A carrier's `pwm-map` and `io-channel-map` are parsed, composed, and
   emitted; a shield needing either resolves through a carrier-exposed
   socket, proven by an emitted overlay, not reasoned about.
2. The synthesized nexus carries the PARENT's cell count, not a
   hardcoded one, and `BoardSocket` can express it (§3).
3. Ruling 2's error fires, with its sentence.
4. Ruling 3: a 3-cell PWM parent yields a diagnostic, not a traceback.
4b. Require-and-check (§5): a missing `#pwm-cells`/`#io-channel-cells`
   beside a map is refused at parse; a declared count disagreeing with
   the resolved parent's is refused at composition, with both numbers in
   the sentence. Both proven by tests, and the grove carriers checked
   against the new requirement.
5. The §5 wart fixed; any golden it moves hand-edited and verified BOTH
   ways (`RIGC_REFREEZE=1` is BLOCKED).
6. **Every other golden byte-unchanged** — this slice adds a capability,
   it does not change any existing rig. `lotus_pwm`'s golden in
   particular must not move: it is the positive control. State as a
   checked result.
7. `arduino-r3.yaml` and both `arduino_r3_socket.dtsi` untouched (§7).
   `git status` proves it.
8. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **722**, integration **273**, coverage **93%** (2026-08-14, `d16fb7c`).
   Re-derive rather than carry.

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criterion 6). Confirm
its `@pytest.mark.build` marking before claiming it. The driver runs the
full gate once, after review.

Brief the reviewer to MUTATION-CHECK: delete the adc branch from
`compose_socket` and leave pwm — criterion 1's adc witness must fail;
hardcode the synthesized nexus's cell count to 2 — criterion 2's test
must fail on the CELL COUNT, not merely somewhere; restore the silent
drop in ruling 2's branch — its test must fail on the SENTENCE; make the
require-and-check comparison always succeed — criterion 4b's mismatch
test must fail, and it must fail on the mismatch, not on a later
symptom.

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
line numbers and file lists are PREDICTIONS — re-derive them. Trace every
reader by grep AND run. Run negative controls IN-TREE. Purge
`__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. When you name a function
in your report, qualify it as `path/to/module.py::function`. Dispatch as
`general-purpose` on **sonnet** from a session rooted at `/wrk/z/ws-up`.
