# Trial scenario coverage

Which playbook scenarios (S1–S8) are realized as expander-prototype trial
pieces, what each is expected to do, and what gaps it surfaced. Rig files are
candidate-2 (`rig.yml`) — the ratified front-end; S3/S5/S7 additionally keep
candidate-1 `.rig.dts` files as the historical front-end comparison. Re-verify
everything with `scripts/run_trials.py` (report: `scripts/out/comparison.md`).

Beyond the S1–S8 playbook, `lotus-buttons` is a **real-hardware port** from the
bridle project (see below) — the strongest single validation so far.

| Scenario | Trial file(s) | Outcome | Requirements exercised |
|---|---|---|---|
| S2 | `s2-wifi-logger.rig.yml` (reject) + `s2-wifi-logger-ok.rig.yml` (realizable) | reject / clean | R4, R5, R6, R7 |
| S3 | `s3-stacked-loggers.rig.{dts,yml}` | **reject** (3 errors) | R8, R9 |
| S4-a | `s4a-grove.rig.yml` (realizable) + `s4a-shared.rig.yml` (reject) | clean / reject | R11, R12, R13 |
| S4-b | `s4b-sockets.rig.yml` (realizable) + `s4b-dup-addr.rig.yml` (reject) | clean / reject | R14, R15 |
| S5 | `s5-temp-farm.rig.{dts,yml}` | clean | R16, R17, R18 |
| S6 | `s6-eth-click.rig.yml` (realizable) + `s6-cross-layer.rig.yml` (reject) | clean / reject | R19, R20, R21 |
| S7 | `s7-sqw-counter.rig.{dts,yml}` (+ `.rig.overlay`) | clean | R22, R23, R24, R10 (Conv. 8) |
| S8 | `s8-mux.rig.yml` (realizable) + `s8-mux-collision.rig.yml` (reject) | clean / reject | R26, R27 |
| S1 | `s1-datalogger.rig.yml` (+ `FIDELITY.md`) | clean; **R2 verified** | R1, R2 |

## S2 — heterogeneous shields, one shared SPI bus (reject + realizable)

Adafruit Data Logger + WINC1500 WiFi, stacked on one Arduino socket
(`shields/winc1500.shield`). The WINC's CS is pool-allocated and its IRQ is a
**routing jumper** (domain {D7, D2}). Today (verified, `build-rig/upstream/S2`):
one ignorable dtc warning, then a broken build. The rig model instead:

- **resolves the CS clash by allocation** — SD copper-fixed at D10 (index 0),
  WiFi pool-allocated to D9 (index 1); one atomic `cs-gpios` array, distinct
  `reg`. This is playbook collision A, the silent clobber, handled (R4/R16).
- **catches the IRQ clash** — with the jumper left at D7 (`s2-wifi-logger`),
  RTC INT and WiFi IRQ both drive D7 → `phys-net` (R5), naming both shields
  at file:line; move it to D2 (`s2-wifi-logger-ok`) and the rig is realizable.

Verified: reject = 1 `phys-net` error; realizable = clean overlay (CS
allocated around D10, IRQ on D2) + config sheet with two physical actions
(set the IRQ jumper; route the allocated CS to D9). **R7** — both are
identical under reversed instance order. New error paths covered by seeded
fixtures m6 (unpinned jumper) and m7 (out-of-domain selection).

**R6 addressed.** The routing jumper (Conv. 2, "Position selection") is the
position-side twin of the address strap: shield declares a
`shield,position-domain`, the rig `pin:`-selects, the expander resolves and
sheets it. Deliberately scoped: non-CS positions must be *explicitly pinned*
(no auto-routing); only the fungible CS pool auto-allocates. Auto-routing of
free non-CS positions remains parked.

## S4-a — board with N same-type connectors: Grove (realizable + reject)

New board `boards/cytron_maker_pi_rp2040.rig.dtsi` (seven `socket,grove`
nodes), connector type `grove` (`bindings/{socket,plug},grove.yaml` +
`connector/grove.h`), modules `grove-pir` (SIG0) and `grove-button` (SIG1).
Today (verified, `build-rig/upstream/S4a`): the board configures clean but
nothing can attach — a Grove shield overlay would hardcode one of seven socket
labels, which is why no in-tree Grove shields exist.

- `s4a-grove` (realizable): modules attach to socket *instances* by name
  (R12) against machine-typed sockets (R11) — clean overlay, `int-gpios`
  rewritten to each socket's nexus.
- `s4a-shared` (reject): the R13 case. The board wires header5 SIG0 and
  header6 SIG1 to the *same* SoC pin (gpio0 26). Two modules in those two
  different sockets, on two different pin positions, both drive it →
  `phys-net`, the message naming "the shared SoC net gpio0 pin 26" and both
  claimants.

This drove a net-identity refactor: nets are now keyed by the SoC pin the
gpio-map resolves to (ontology §2 derived closure), not by `(socket,
position)`. Positions absent from the fragment's gpio-map (per-socket
dedicated lines, e.g. mikroBUS INT) stay socket-local. Verified: no regression
to S2/S3/S5/S7; R7 holds for `s4a-grove`.

## S4-b — board with N same-type connectors: mikroBUS (realizable + reject)

Reuses Quail + `flash-click`; adds `temp-hum-click` (HTS221, I2C fixed 0x5f).
A mikroBUS socket bundles three sharing regimes (R14/R15): SPI shared pairwise
(sockets 1,2 → spi1; 3,4 → spi3), I2C shared by all (→ i2c1), CS/RST dedicated
per socket.

- `s4b-sockets` (realizable): socket selection picks the *controller* — a
  Flash Click in socket 1 lands on spi1 (CS gpioa3), another in socket 3 on
  spi3 (CS gpiod11); the overlay emits two independent SPI scopes, each with
  its own `cs-gpios` and `reg = <0>`. A Temp&Hum click sits on i2c1. R7 holds.
- `s4b-dup-addr` (reject): two Temp&Hum clicks in *different* sockets (2 and
  4) still share i2c1; both fixed at 0x5f → `phys-addr`. Socket choice is no
  escape on a shared bus (R9/R15) — the cross-socket sibling of S3's stack.

**Coverage note.** UART (the fourth mikroBUS regime, dedicated-per-socket) is
not exercised: the prototype's emitter handles i2c/spi bus scopes and non-bus
GPIO groups, not uart devices. The three regimes shown (dedicated GPIO/CS,
shared-pairwise SPI, shared-all I2C) cover R15; UART would be another dedicated
example. Left for later.

## S6 — nested composition: board → adapter → click (realizable + reject)

The first interposer scenario. New: host board `frdm_k64f.rig.dtsi`; a
CARRIER shield `arduino-uno-click.shield` that plugs an Arduino R3 socket and
**re-exports two mikroBUS sockets** (R19), pure pass-through (no devices);
`eth-click.dtsi` (ENC28J60, SPI). The rig references a carrier's exposed
socket with a dotted `carrier_instance.exposed_socket` string.

- `s6-eth-click` (realizable): two ETH clicks, one per adapter socket. Each
  click's SPI resolves to the host's spi0 (passed through the adapter), and
  each mikroBUS CS resolves through the two-level chain to the host Arduino CS
  pin (mb1 → D10 → PTD0/gpiod0; mb2 → D9 → gpioc1). The two share spi0 and get
  distinct allocated CS (R4 through R19). `int-gpios` likewise chain to SoC
  pins. Verified: R7 holds even with the carrier declared *after* the clicks
  (socket resolution is recursive + memoized).
- `s6-cross-layer` (reject): the R21 case. An ETH click's CS (adapter mb1 →
  D10 → PTD0) and a Data Logger's copper-fixed SD CS (D10 → PTD0), the logger
  stacked directly on the host Arduino socket, resolve to the **same SoC pin**.
  The expander rejects with `phys-cs` naming "the shared SoC net gpiod pin 0"
  and both claimants — one at the board level, one two layers deep. Today this
  is the coincidence the playbook warns about, verified nowhere.

**Mechanism.** A carrier's exposed socket declares a pass-through gpio-map
(positions → the carrier's own plug positions) and `socket,<bus> = <&plug>`.
The expander resolves an instance's socket recursively: a board socket
directly, or a carrier's exposed socket *composed* against whatever the
carrier itself plugs into — gpio-map composes to real SoC pins (for net
identity), buses to real controllers. Because net identity is already keyed on
the SoC pin (S4-a), cross-layer conflict detection (R21) fell out for free.

**Emission — Option C (nexus synthesis).** A carrier's exposed socket has no
DT node of its own, so the emitter *synthesizes a gpio-nexus node* for each one
in use, chaining to its parent's nexus (`adapter_1_mb1 { gpio-map = <2 0
&frdm_ard 16 0>, … };`). Every connector-routed signal — device gpio-specs
*and* controller `cs-gpios` — is then emitted uniformly through a nexus
(`<&adapter_1_mb1 7 …>`, `<&adapter_1_mb1 2 …>`), and dtc chases the
(possibly multi-level) gpio-map to the pin. This matches hand-written nested
overlays and keeps the routing visible in the artifact; board-socket
`cs-gpios` moved to the same nexus form (`<&quail_sock1 2 …>` rather than
`<&gpioa 3 …>`) for consistency. The alternative (resolve straight to the SoC
pin) was rejected: it loses provenance and diverges structurally from the
legacy overlay the S1-fidelity milestone diffs against.

**Scope note (R21).** Covered: the *chaining* — CS/bus/GPIO resolve end-to-end
through the adapter, and same-pin collisions across layers are caught. Not
modeled: the ETH click's real reliance on native SPI pinmux CS (vs a GPIO CS),
and checking against SoC pinctrl claims on the same pin — that needs a pinctrl
model (parked). The trial models the click's CS as a normal pool-allocated
GPIO CS.

## bridle port — Seeeduino Lotus + Grove Button/LED (real hardware)

Ported from the cloned `bridle` project (`boards/seeed/seeeduino_lotus`,
`boards/shields/grove_btn`, `grove_led`) — a real Zephyr distribution, not a
hypothetical. Bridle expresses each Grove module as **64 hand-written overlay
files** (`grove_btn_d0..d31` × normal/`_inv`) plus a 64-line `Kconfig.shield`
and a 32-entry `Kconfig.defconfig`; the two axes enumerated are *which digital
pin* (32) and *polarity* (2). This is the C1×C2 combinatorial explosion the
playbook predicted — a real project literally generated all 64.

Our expression: `boards/seeeduino_lotus.rig.dtsi` (the board's physical Grove
connectors as typed `socket,grove` nodes, real SAMD21 pin mapping, including
the daisy-lacing where SIG1 of one connector is SIG0 of the next), plus **one**
shield each (`grove-btn.shield` = gpio-keys, `grove-led.shield` = gpio-leds). The
two axes map to model constructs:

- *which pin* → the socket the rig places the module in (R12): `socket: grove_d6`.
- *polarity* → the per-instance `invert:` parameter (gap #1, now built): flips
  the active-level bit (`GPIO_ACTIVE_LOW = 1<<0`) of the module's gpio signals.

`lotus-buttons.rig.yml` (three modules) expands clean; the overlay references
each Grove socket nexus (`<&grove_d2 0 0x20>`, and `<&grove_d6 0 0x21>` for the
inverted button — 0x20 → 0x21 is the flipped polarity). **64 overlays + 96
lines of Kconfig → one shield + one line per real module.** R7 holds including
the invert.

Gaps this port confirms (all previously flagged):

- **Kconfig (parked, open question 1).** Bridle's 32 `SHIELD_GROVE_BTN_Dn`
  symbols + driver auto-enable (`CONFIG_GPIO`) are the config half of
  multi-instantiation — the rig model covers the DT half only. This port is
  the concrete instance to design that against.
- **PWM / pinctrl (parked, R21 deep half).** The board's laced interface is
  also a `pwm-map` (a Grove pin is GPIO *or* PWM), with `GROVE_PWM_Dn_*`
  pinctrl macros — the pin-mux provisioning the prototype does not model.
- **gpio-keys / gpio-leds aggregation (gap #4) — DONE 2026-07-21 (Conv. 9).**
  A shield marks a device `shield,collect = "gpio-keys"`; the expander
  aggregates every collected entry across instances into one node per
  compatible. `lotus-buttons` now emits one `gpio_keys` node (btn_start,
  btn_stop children) and one `gpio_leds` node — matching bridle's merged
  `/grove_btns`, but from one shield + placements instead of 64 overlays.
  Aggregation, not collapse: each entry keeps its per-instance label/node
  (R8); emission-only, so analysis is unchanged; R7 holds. Parked: explicit
  collection names, and merging into a board-provided collection.

## Slice A — multi-function positions: PWM + ADC (realizable + reject)

Exercises ontology Refinement 1 (functions live on endpoints, not nets) on the
real Seeeduino Lotus. The board's Grove sockets gain per-function nexuses
(`socket,pwm-map`, `socket,adc-map`) beside `gpio-map` — mirroring bridle's
laced gpio-map + pwm-map. New shields `grove-servo` (PWM, `pwms`) and
`grove-light` (ADC, `io-channels`).

- `lotus-pwm` (realizable): a servo on grove_d2 and a light sensor on grove_a0.
  The expander resolves each position through the matching nexus and emits
  resolved form — `pwms = <&tcc0 0 20000000 …>`, `io-channels = <&adc0 0>` —
  enables `&tcc0`/`&adc0`, and lists the board pin-mux to apply in the config
  sheet (stubbed).
- `lotus-pwm-clash` (reject): two servos on grove_d2 **and** grove_d4 —
  different pins (porta14 vs porta8) but the board's pwm-map lands both on
  tcc0 ch0 (real bridle fact). One timer channel can't drive two servos →
  `phys-channel`, naming both at their sockets. Caught on the *channel* net
  even though the pins differ.

**Mechanism.** A PWM/ADC claim registers on two nets — the **pin** (exclusive:
resolved via gpio-map, so a pin used as PWM can't also be GPIO) and the
**channel** (exclusive: `("chan", controller, channel)`, so two consumers of
one timer/adc channel conflict). Both reuse the existing net-identity +
exclusive-conflict machinery. GPIO stays nexus-form; PWM/ADC emit resolved
form (those references aren't nexuses in idiom).

**Scope (pinctrl).** The rig model *selects/names* the pin-mux each function
needs (config-sheet note + controller enable); it does **not** author SoC
pinmux values — the board provides the pinctrl fragments (bridle's
`GROVE_PWM_Dn_PINCTRL`). Applying those fragments in the output is the "how a
resource is provided" half of R21, still parked. DAC follows the identical
pattern (a `socket,dac-map` + `io-channels`/`dacs`), not built.

## S8 — active interposer: an I2C mux (realizable + reject)

The last playbook scenario, and the one where an interposer CREATES scopes
rather than passing them through (contrast S6). New: connector type `i2c-port`
(a bare, stackable I2C port — a bus hosts many devices); `i2c-mux.shield` (a
TCA9548A at 0x70 on the host bus, re-exporting four downstream i2c-port
sockets whose `socket,i2c = <&mux>` roots a NEW scope per channel);
`i2c-sensor.shield` (fixed 0x48, the S3 offender).

- `s8-mux` (realizable): four identical 0x48 sensors, one per channel — exactly
  the topology S3 proved unrealizable on one bus, made realizable by the mux.
  The overlay emits `mux@70` with four `channel@N` children, each hosting a
  `sensor@48` (0x48 recurs, legal per-scope) — the golden TCA9548A structure.
  The mux itself claims 0x70 on the parent scope.
- `s8-mux-collision` (reject): two 0x48 sensors on the *same* channel (ch0)
  share one scope → `phys-addr` on `&mux_1_mux_ch0`. The per-scope check (R26)
  fires within a scope, not just across.

**Mechanism.** An exposed socket's `socket,i2c = <&mux>` (a device of the
shield, not the plug) marks scope creation: `_compose_socket` mints a fresh
BusRef whose path is the channel's instance-qualified id, and records it in
`solved.scopes`. Because the address allocator already groups by bus *path*,
per-scope uniqueness (R26) fell out — four channel paths = four scopes. The
emitter nests each scope's modules inside the mux device's `channel@N` node.
Scope-awareness composes with nesting depth for free (R19 + this). R27
(channel↔module assignment) is the rig's socket placement (`socket: mux_1.ch2`)
+ the config sheet — no new allocator. R7 holds (carrier + sensors reordered).

*S1–S8 playbook sweep now fully realized in the prototype. Remaining: the S1
fidelity milestone (diff `build-rig/proposal/S1` against `build-rig/upstream/S1`)
— a build/diff task, not a new mechanism.*

## S1 — fidelity baseline (Data Logger on Nucleo)

`s1-datalogger.rig.yml` = `west build -b nucleo_f401re --shield
adafruit_data_logger`. The generated overlay is equivalent (R2) to the legacy
`adafruit_data_logger.overlay`: every pin reference resolves to the same SoC
pin as in the real `build-rig/upstream/S1/zephyr/zephyr.dts` (the trial
`nucleo_ard` gpio-map equals the real `arduino_header`), same addresses,
compatibles, and `gpio-leds` aggregation. Differences are label naming
(R2-permitted), aliases-in-`rig.overlay` (Conv. 8), and two enumerated gaps
(`status = "okay"`, `sdmmc` device sub-node). Full write-up: `FIDELITY.md`.
This drove the data-logger LEDs onto `shield,collect = "gpio-leds"` (Conv. 9)
and fixed a collection-entry naming bug (a shield with >1 collected device now
gets unique entry node names).
