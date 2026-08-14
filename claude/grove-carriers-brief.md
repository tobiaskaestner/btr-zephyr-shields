# The Grove base carriers — bridle's `grove/` folder

**Status:** briefed 2026-08-14, ready to dispatch. Third and last
grove-completion slice (`grove_sens` landed `3c6eb98`/`ad5092a`,
`grove_pwm_led` landed `b16c314`/`5e8ded6`). Sequenced AFTER item 30,
which labelled every exposed-socket node — carriers are precisely what
create that surface, and this slice adds ~31 more of them.

Bridle's `boards/shields/grove/` is **193 files** — 98 overlays, 61
dtsi — declaring four carrier variants. Each is a board that plugs a
host header and re-exports N typed Grove sockets. This is
`arduino_uno_click`'s shape at much larger N.

## 1. Rulings (Tobi, 2026-08-14)

1. **One folder**, all variants, plurality-style (`arduino_lcd`,
   `grove_sens`, `grove_led` precedents).
2. **SPI and UART connectors are OUT.** Focus on **I²C and digital
   I/O**. Recorded as deliberate deferrals — backlog item 31, already
   written — never silently skipped.
3. **ADC (`a0..a4`) is IN, and breakage is accepted.** §7 now predicts
   exactly what will break and why; do not treat that prediction as
   permission to descope. Author the ADC connectors, hit the wall,
   report the wall precisely. That report is the next slice's brief.
4. **`seeed_grove_base_v1` and `_v2` only** — backlog item 32 holds the
   other two, blocked on host connector types (§2).

## 2. Only two of the four are dispatchable — and why

The carrier's `shield,plugs` is the HOST header's connector type. Two of
the four name a host type this project does not have:

| variant | host header | our connector type | in scope? |
|---|---|---|---|
| `seeed_grove_base_v1` | `&arduino_header` | `arduino-r3` ✅ | **yes** |
| `seeed_grove_base_v2` | `&arduino_header` | `arduino-r3` ✅ | **yes** |
| `seeed_grove_rpipico_v1` | `&rpipico_header` | **none** ❌ | backlog 32 |
| `seeed_grove_xiao_v1` | `&xiao_d` | **none** ❌ | backlog 32 |

`dts/bindings/connectors/` holds exactly four types: `arduino-r3`,
`grove`, `i2c-port`, `mikrobus`. A Pi Pico header and a XIAO header are
each a **Convention 1 job of their own** — a binding plus a
`dt-bindings/connector/<name>.h` position header, the single source of
truth for position indices — before a carrier can plug one.

**The folder is still authored to hold all four** (ruling 1), so both
drop in when those types exist. Do NOT shape it around exactly two.

## 3. Scope in sockets, after ruling 2

| variant | declared | dropped (SPI/UART) | **in scope** |
|---|---|---|---|
| v1 | 21 | `grove_spi`, `grove_d0_uart` | **19** |
| v2 | 13 | `grove_d0_uart` | **12** |

v1 in scope: `grove_i2c`, `grove_a0..a4`, `grove_d1..d13`.
v2 in scope: `grove_i2c`, `grove_a0..a3`, `grove_d2..d8`.

Re-derive from `bridle/boards/shields/grove/seeed_grove_base_v{1,2}.overlay`'s
own `#include` lists before authoring — this table is a prediction.

## 4. Shape

Per `arduino_uno_click`, one exposed node per connector:

```dts
grove_base_v2: grove_base_v2 {
	shield,plugs = "arduino-r3";
	gbv2_plug: plug { #gpio-cells = <2>; };

	grove_d2: grove_d2 {
		compatible = "socket,grove";
		#gpio-cells = <2>;
		gpio-map = <GROVE_SIG0 0 &gbv2_plug ARDUINO_HEADER_R3_D2 0>,
			   <GROVE_SIG1 0 &gbv2_plug ARDUINO_HEADER_R3_D3 0>;
	};
	grove_i2c: grove_i2c {
		compatible = "socket,grove";
		#gpio-cells = <2>;
		gpio-map = <GROVE_SIG0 0 &gbv2_plug ARDUINO_HEADER_R3_A5 0>,
			   <GROVE_SIG1 0 &gbv2_plug ARDUINO_HEADER_R3_A4 0>;
		socket,i2c = <&gbv2_plug>;
	};
};
```

**Every exposed node carries a LABEL** — item 30 (`_require_label` now
serves exposed sockets) makes an unlabeled one a loud
`lang-shield-label` error, and the label is what a rig's
`socket: <carrier>.<exposed>` names.

The per-connector `gpio-map` targets come from bridle's own
`seeed_grove_base/grove_*_connector.dtsi`, which map into
`&arduino_header` positions directly — e.g. `grove_d2` is
`<0 0 &arduino_header 8 0>, <1 0 &arduino_header 9 0>`. Those indices
are ARDUINO_HEADER_R3_* positions; translate, do not re-derive from a
schematic.

**SIG0=SCL, SIG1=SDA** on the I²C connector, matching bridle
(`grove_i2c_connector.dtsi`: position 0 = A5/SCL, position 1 = A4/SDA)
and the NanoC6 socket landed in `3c6eb98`.

## 5. What disappears, and why this slice is worth its size

Bridle's real cost is not the four overlays — it is the **98 board
overlays and 61 dtsi under `grove/boards/`**, per-board × per-variant
glue binding those connectors to each specific host
(`arduino_to_grove_if.dtsi` is three alias lines; `nucleo_f746zg_bbe.overlay`
and 97 siblings exist to bind that glue to one board). A carrier that
maps into its OWN plug needs none of it: the host board's `arduino-r3`
socket already carries the pin facts.

Payoff beyond file count, stated precisely (see §7 for the limit):
`frdm_k64f` and `nucleo_f401re` both have `arduino_r3_socket.dtsi` with
`socket,i2c` (checked: `&i2c0` and `&i2c1`). So one carrier makes the
**I²C and digital** grove shields buildable on the two platforms
twister already runs — including `grove_sens`, whose only host today is
the NanoC6. It does **not** reach `grove_light` or `grove_pwm_led`.

## 6. Expected breakage — predicted, not merely anticipated (ruling 3)

The earlier draft called ADC-through-a-carrier "unproven" and pointed at
`compose_socket`. That was too vague, and checking made it sharp:

**`dts/bindings/connectors/arduino-r3.yaml` declares no `io-channel-map`
and no `pwm-map`.** It declares `gpio-map`, `socket,i2c`, `socket,spi`,
`socket,uart`, `socket,stackable`, `socket,cs-pool` — nothing else.
Neither `frdm_k64f`'s nor `nucleo_f401re`'s socket carries an ADC nexus
either (checked both files).

So the failure is NOT a composition mystery two levels down. It is a
missing declaration two levels UP:

- A carrier's `grove_a0` needs `io-channel-map` targeting its own plug.
- The plug is `arduino-r3`, which has no ADC nexus to pass through to.
- Therefore `grove_light` (`io-channels = <&gl_plug GROVE_SIG0>`) cannot
  resolve through any carrier on either twister board.
- The same holds for PWM and `grove_pwm_led`, for the same reason.

**What the implementor must do**: author the `grove_a*` connectors
anyway (ruling 3), then determine and REPORT which of these three it
actually is:

1. `arduino-r3.yaml` simply lacks the property → a binding-level fix,
   plus a board-level `io-channel-map` on each socket. Cheap, and the
   next slice.
2. `compose_socket` cannot pass an ADC nexus through an exposed socket
   at all, independent of the binding → a model gap, bigger.
3. Something else entirely.

Distinguish them by evidence (the actual diagnostic, the actual code
path), not by reasoning from this brief. The multi-bus slice's CS-pool
regression — where the pass-through branch leaked the parent's pool
into a composed socket of a different type — is the standing warning
that these branches carry non-obvious state.

Also worth stating: a carrier exposing 19 sockets is ~10×
`arduino_uno_click`'s two. Nothing suggests a scaling limit; nothing has
tested one either.

## 7. Twister

`frdm_k64f` and `nucleo_f401re` are real twister platforms with
`arduino-r3` sockets carrying `socket,i2c`. A suite putting `grove_btn`
(digital) or `grove_sens` (I²C) on a carrier-exposed Grove socket would
be the first **NESTED** promotion in twister — a shield on a socket
exposed by a shield. Take it: it is the strongest available end-to-end
evidence, and both shield kinds are inside §6's working set.

Do NOT attempt a `grove_light` suite — §6 says why it cannot pass.

## 8. Acceptance criteria

1. `boards/shields/grove/` declares two shields (`seeed_grove_base_v1`,
   `seeed_grove_base_v2`) in plural `shield.yml` form, one Kconfig
   symbol each, folder named after neither — the `arduino_lcd`
   falsifier shape. Confirm both are discovered.
2. Every exposed socket node LABELLED (item 30); an unlabeled one is
   already a loud error, so this is enforced, not aspirational.
3. A corpus rig on `frdm_k64f` **or** `nucleo_f401re` — pick whichever
   board's existing goldens are cheapest to sit beside, and say which
   and why — putting at least one I²C shield and one digital shield on
   carrier-exposed sockets, with its goldens.
4. A twister suite for the nested promotion (§7).
5. The ADC connectors exist and their breakage is reported per §6's
   three-way question, with the actual diagnostic quoted.
6. **Every existing golden byte-unchanged** — this slice adds, it does
   not migrate. State it as a checked result. `RIGC_REFREEZE=1` is
   BLOCKED — hand-edit and verify BOTH ways.
7. The singleton identity law: check whether either carrier belongs in
   it or in `EXPECTED_REJECTING` **with its reason stated**. Do not
   assume.
8. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **722**, integration **268**, coverage **93%** (2026-08-14, item 30).
   Re-derive rather than carry.

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criteria 3 and 6).
Confirm its `@pytest.mark.build` marking before claiming it. The driver
runs the full gate once, after review.

Brief the reviewer to MUTATION-CHECK: break one `gpio-map` entry's
target position on a carrier connector — a golden must fail on the
resolved pin, not merely somewhere; remove one exposed node's label —
the loud error must fire; drop `socket,i2c` from `grove_i2c` — the I²C
shield's rig must be refused with a named diagnostic.

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
file lists and socket tables are PREDICTIONS — re-derive them from
bridle's own sources. Run negative controls IN-TREE. Purge
`__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. Dispatch as
`general-purpose` on **sonnet** from a session rooted at `/wrk/z/ws-up`.
