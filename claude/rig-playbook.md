# Rig Scenario Playbook

A catalog of rig topologies of increasing complexity, mapping the topology space
the rigs hardware-model extension must cover. Built interactively; each scenario
is grounded in real hardware where possible and records:

- **Physical topology** — what is actually plugged into what
- **Today's expression** — how (or whether) current Zephyr boards/shields/overlays
  can describe it
- **Stress points** — which mechanisms break, referencing the claims in
  `design-log.md` (C1 = type/instance conflation, C2 = connectors as convention,
  C3 = parent-array composability)
- **Requirements extracted** — what the rig model must support to cover it

Visual atlas: every scenario has a Graphviz diagram in `diagrams/<id>-*.dot`
(rendered SVGs alongside; regenerate with `dot -Tsvg -o x.svg x.dot`). Browsable
gallery: https://claude.ai/code/artifact/9dc7b621-f012-4703-b340-6729815d7595
Visual language: blue=board, green=module, amber=interposer, orange=connector,
gray=bus/SoC resource, red=verified defect, green edges=expander-computed,
purple=net/scope.

## Topology dimensions being mapped

Each scenario turns one or more of these dials up:

| Dimension | Range |
|---|---|
| D1. Module instance count | 1 → N identical modules |
| D2. Connector multiplicity | 1 connector → N same-type connectors ("slots") |
| D3. Bus sharing | dedicated bus per module → shared bus (address/CS contention) |
| D4. Resource allocation | static/authored → must be computed (CS index, I2C addr, pin) |
| D5. Nesting | flat → modules containing modules (template uses template) |
| D6. Cross-module wiring | none → module A signal wired to module B |
| D7. Heterogeneity | identical modules → mixed module types per rig |
| D8. Connector realization | native board connector → adapters/muxes in between |

---

## Scenario S1 — Baseline: one board, one shield (today's model, working)

**Dials:** all at minimum. This is the anchor: what current Zephyr handles well,
and the behavior any rig model must reproduce exactly.

**Hardware:** ST Nucleo-F401RE + Adafruit Data Logger shield on the Arduino R3
header. Chosen because this single in-tree shield
(`boards/shields/adafruit_data_logger/adafruit_data_logger.overlay`) touches
every mechanism class at once.

```text
+---------------------------------------------+
|  Nucleo-F401RE                              |
|                                             |
|   [Arduino R3 header] <===================> |  Adafruit Data Logger shield
|     |                                       |    ├─ SD card       (SPI, CS on D10)
|     ├─ gpio-map ──> &gpioa/&gpiob... (C2 OK)|    ├─ PCF8523 RTC   (I2C @ 0x68, INT on D7)
|     ├─ arduino_spi ──> &spi1  (label conv.) |    └─ 2x LED        (GPIO D3, D4, via jumpers)
|     └─ arduino_i2c ──> &i2c1  (label conv.) |
+---------------------------------------------+
```

**Today's expression:** `west build -b nucleo_f401re --shield adafruit_data_logger`.
The shield overlay:

- adds LEDs under `/leds` referencing `&arduino_header <pin>` — routed through the
  **gpio-map nexus node** (first-class, composes)
- adds `rtc@68` under `&arduino_i2c` — **label convention** for the bus, child
  node merge (composes as long as addresses don't collide)
- adds `sdhc@0` under `&arduino_spi` and sets
  `cs-gpios = <&arduino_header D10 ...>` **wholesale** on the board's SPI
  controller (C3 landmine, dormant with a single shield)
- namespaces all labels/node names manually with the `_adafruit_data_logger`
  suffix (C1 workaround, visible in-tree)

**Stress points:** none active — this works. But the latent defects are all
present: the CS array write is a wholesale replace, the I2C address is hardcoded,
and namespacing is manual. Every later scenario activates one of these.

**Requirements extracted:**

- R1. The rig model must express S1 with no loss: GPIO nexus routing, bus child
  placement, connector-relative pin references.
- R2. Round-trip fidelity: for single-instance rigs the generated tree should be
  equivalent to today's overlay output (this is the regression baseline for the
  expander).
- R3. The rig description should capture what the shield overlay leaves implicit:
  which connector the module occupies, and which resources (bus addresses, CS
  slots, pins D3/D4/D7/D10) it consumes.

---

## Scenario S2 — Two different shields, one shared SPI bus (today's model, breaks)

**Dials:** D3 (bus sharing) and D7 (heterogeneity) up one notch; instance count
still 1 per module type. First scenario where today's mechanisms actively fail.

**Hardware:** Nucleo-F401RE + Adafruit Data Logger + Adafruit WINC1500 WiFi
shield, stacked on the same Arduino R3 header. Both are in-tree shields; the
combination is physically buildable (stacking headers) and functionally
reasonable (a WiFi data logger).

```text
+---------------------------------------------+
|  Nucleo-F401RE                              |
|   [Arduino R3 header]                       |
|     |                                       |
|     ├──> Data Logger shield                 |
|     |      ├─ SD card    SPI  CS=D10 reg=0  |   <── collision A: cs-gpios wholesale write
|     |      ├─ RTC        I2C @0x68  INT=D7  |   <── collision C: D7 double-booked
|     |      └─ LEDs       GPIO D3, D4        |
|     └──> WINC1500 shield                    |
|            └─ WiFi       SPI  CS=D10 reg=0  |   <── collision A + B: same CS pin, same reg
|                          IRQ=D7 RST=D5 EN=D6|   <── collision C: D7 again
+---------------------------------------------+
```

**Today's expression:** `west build -b nucleo_f401re --shield adafruit_data_logger --shield adafruit_winc1500`
(shield overlays are applied in order; both patch `&arduino_spi`).

**Stress points — three distinct collision classes in one pair:**

- **A. Parent-array clobber (C3).** Both overlays write `cs-gpios` on
  `&arduino_spi` wholesale:
  - `adafruit_data_logger.overlay:39`: `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D10 GPIO_ACTIVE_LOW>;`
  - `adafruit_winc1500.overlay:11`: `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D10 0>;`

  Last shield on the command line wins — including its *flags* (`GPIO_ACTIVE_LOW`
  vs `0`), so shield order silently changes CS polarity for whichever device
  survives. Merge semantics offer no append, and even append would be wrong (see B).
- **B. Unit-address / CS-slot contention (D4).** `sdhc@0` and `winc1500@0` both
  claim `reg = <0>` — the index into the parent's `cs-gpios` array. Composing
  them is not concatenation but **allocation**: one child must be re-addressed to
  `reg = <1>` and a second CS entry (on a *different* pin) appended, atomically.
  No overlay-level mechanism can express this.
- **C. Pin double-booking, invisible to DT (R3).** Data Logger wires the RTC
  interrupt to D7 (`int1-gpios`); WINC1500 wires its IRQ to D7 (`irq-gpios`).
  Devicetree records both without complaint — GPIO consumption is a driver-level
  concept, and nothing models "header pin D7 is already taken." The failure
  surfaces at runtime (or never, as a heisenbug). Note the physical rig *cannot*
  be fixed in software alone: one shield needs its solder jumper / bodge wire
  moved, and the DT must then follow that change — which today means hand-editing
  a copy of the shield overlay, forfeiting the shield abstraction entirely (C1).

**Verified behavior** (2026-07-17, zephyr-rigs @ v4.4.0-8558-g640b25d911f,
baseline build in `build-rig/upstream/S2`, full log `S2-configure.log`):
configure **succeeds** (exit 0) with exactly **one warning**:

```text
zephyr.dts:563.39-575.6: Warning (unique_unit_address_if_enabled):
/soc/spi@40013000/sdhc@0: duplicate unit-address (also used in node /soc/spi@40013000/winc1500@0)
```

Collision B gets a warning; collisions A and C produce **no diagnostic at all**.
The generated `zephyr.dts` provenance comments document the clobber themselves:

```dts
cs-gpios = < &arduino_header 0x10 0x0 >;  /* in ...adafruit_winc1500.overlay:11 */
```

— the Data Logger's `GPIO_ACTIVE_LOW` flag is silently gone (last shield wins),
both children carry `reg = <0>`, and both D7 claims (`0xd`) coexist. So the
accurate upstream claim is: *one ignorable warning, then a successfully generated
broken configuration.*

**Requirements extracted:**

- R4. Shared-bus attachment must be declared, not patched: a module declares "I
  need one SPI chip-select on my connector"; the expander allocates the CS index,
  appends the `cs-gpios` entry, and rewrites the child's `reg` — globally, across
  all modules on that bus.
- R5. Pin/resource consumption must be modeled and checked: every
  connector-routed signal a module uses (D3, D4, D5, D6, D7, D10, I2C addresses)
  is a claimed resource; two claims on one resource is an *expansion-time error*,
  not a runtime surprise.
- R6. Physical variability (jumpers, solder bridges) needs first-class
  parameters: the D7 conflict is resolvable on real hardware by moving a jumper —
  the module description must expose that as an instantiation parameter (e.g.
  `rtc-int-pin = D2`) rather than requiring a forked overlay.
- R7. Application order must not change meaning: today shield order silently
  selects which CS config survives; rig expansion must be order-independent (or
  reject ambiguity).

---

## Scenario S3 — The same shield twice (today's model, silently collapses)

**Dials:** D1 (instance count) to 2; everything else as S1. The pure C1 singleton
wall, isolated from bus-sharing concerns.

**Hardware:** Nucleo-F401RE + two Adafruit Data Logger shields stacked
(redundant/failover logging — contrived but defensible). Note the physical rig
itself already demands per-instance variation: the second shield must move its CS
to another pin (solder jumper exists for this) — and the RTC cannot be
duplicated at all on the shared bus, see below.

**Today's expression (attempted):**
`-DSHIELD="adafruit_data_logger;adafruit_data_logger"`.

**Verified behavior** (2026-07-17, baseline build in `build-rig/upstream/S3`,
log `S3-configure.log`): configure succeeds with **zero diagnostics**; the
overlay is applied twice; the second application merges by path into the same
nodes. The resulting `zephyr.dts` is **byte-identical to the S1 single-shield
build** (verified by diff). The user requested two SD cards and got one,
silently. This is C1 in its purest form: the reuse unit patches the global
instance tree, so "apply twice" is idempotent instead of instantiating.

**Stress points:**

- **Silent collapse (C1).** No mechanism even *represents* the intent "two of
  these" — the request degenerates before any collision can occur.
- **Singleton tree constructs.** The shield sets `aliases { rtc = &rtc0_...; }`.
  Two instances need per-instance aliases (`rtc0`, `rtc1`) and a policy for
  `chosen`-style global singletons.
- **Physical realizability limit.** The PCF8523 RTC has a fixed I2C address
  (0x68, no address-select pins). Two instances on the one shared `arduino_i2c`
  bus are *physically impossible* regardless of any DT model. Duplicating this
  module requires a second bus, an I2C mux (S8), or omitting one RTC. A correct
  rig model must be able to detect and **reject** such topologies — silent
  acceptance would reproduce today's failure mode at a higher level.

**Requirements extracted:**

- R8. Instantiation must be explicit and countable: requesting N instances yields
  N namespaced subtrees (labels, paths, aliases) or a hard error — never a silent
  collapse into one.
- R9. Modules must declare address capabilities (fixed vs. selectable, and how:
  jumper, strap pin) so the expander can prove a topology realizable — or reject
  it at expansion time with a physical-level explanation.
- R10. Tree-level singletons (`aliases`, `chosen`) need per-instance treatment
  and a deterministic naming scheme for generated names.

---

## Scenario S4-a — Board with N same-type connectors: Grove (today's model: connectors exist, attachment doesn't)

**Dials:** D2 (connector multiplicity) to 7; instance count 0 — because today
nothing can attach.

**Hardware:** Cytron Maker Pi RP2040 — seven Grove sockets, modeled in-tree
(recently, © 2026) as seven `grove-header` GPIO nexus nodes in
`boards/cytron/maker_pi_rp2040/grove_connectors.dtsi`.

**What today's model gets right:** connector *identity* exists at the GPIO level
— `grove_header1..7`, each with its own `gpio-map`. Numbering solves D2 for
pins.

**Stress points:**

- **Socket type is a comment.** A Grove socket carries one of {UART, I2C,
  digital, analog}; here that's encoded only as comments (`/* SCL */`,
  `/* RX */`, `/* ADC0 */`). `grove_header2` routes to the RP2040's i2c1 pins,
  but nothing machine-readable says "this socket carries I2C" — the board
  defines no `grove_i2c`-style bus labels at all (C2).
- **Zero Grove module shields exist in-tree.** The connector nodes are
  write-only: no shield can target "socket 4," because a shield overlay must
  hardcode one label — a hypothetical Grove LED shield would bake in one of
  seven sockets. The empty shield ecosystem around a 7-socket connector standard
  is itself evidence that the singleton/label model cannot express module ×
  socket attachment (C1 × C2).
- **Cross-socket pin sharing.** `grove_header5` pin 0 and `grove_header6` pin 1
  both map to `gpio0 26` (ADC0) — the sockets physically share a wire. Modules
  in sockets 5 and 6 simultaneously can conflict, and nothing models it (extends
  R5 across connector boundaries).

**Verified behavior** (2026-07-17, `build-rig/upstream/S4a`): bare board
configures clean, zero warnings. There is nothing further to build — no
attachment mechanism exists to exercise.

**Requirements extracted:**

- R11. Connector nodes must declare what they carry (bus endpoints, functions,
  pin roles) machine-readably — typed connector classes, not comments.
- R12. Module attachment must name a socket *instance* as an instantiation
  parameter (module M in socket K), not resolve through a global label.
- R13. Connector definitions must expose shared underlying resources (socket 5/6
  sharing gpio0 26) so cross-socket conflicts are detected at expansion time.

---

## Scenario S4-b — Board with N same-type connectors: mikroBUS (today's model: the hand-rolled struct)

**Dials:** D2 to 4, D3 (bus sharing) structurally rich: per-socket dedicated
*and* pairwise-shared *and* fully-shared resources in one connector standard.

**Hardware:** MikroE Quail — four mikroBUS sockets — plus the Temp&Hum Click
(HTS221, I2C @ fixed 0x5f), both in-tree.

**What the socket anatomy actually is** (from `mikroe_quail.dts`): a mikroBUS
socket bundles resources with *three different sharing regimes*:

| Socket resource | Realization on Quail | Sharing |
|---|---|---|
| AN | `skd1..skd4` ADC | dedicated per socket |
| UART | `usart3, usart2, usart6, usart1` | dedicated per socket |
| RST/CS/INT/PWM | per-socket GPIO via nexus node | dedicated per socket |
| SPI | sockets 1,2 → `spi1`; sockets 3,4 → `spi3` | shared pairwise |
| I2C | all four → `i2c1` | shared by all |

**Today's expression:** the board hand-encodes this as a **16-label matrix** —
`mikrobus_<N>_{adc,i2c,spi,uart}` for N=1..4 (`mikroe_quail.dts:335-365`) — plus
four nexus nodes, plus unnumbered convention aliases (`mikrobus_spi: &spi1`)
defaulting everything to socket 1. This is a connector *type* being emulated by
manual enumeration of the socket × resource product — the hand-rolled struct
that proves the missing abstraction (C2).

Convention fragmentation, live: the click shield (© 2026) targets the *numbered*
`&mikrobus_1_i2c`, while the older ecosystem convention is the unnumbered
`&mikrobus_i2c` (cf. `arduino_uno_click` adapter). Two coexisting label
conventions for the same concept, chosen per author.

**Verified behavior** (2026-07-17, `build-rig/upstream/S4b`): Quail +
`mikroe_temp_hum_click` configures clean, zero warnings; provenance shows
`hts221@5f` landing on `/soc/i2c@40005400` (i2c1) purely through the hardcoded
socket-1 label.

**Stress points:**

- **Socket selection is inexpressible.** The click in socket 3 instead of 1: for
  I2C it happens to be electrically identical (shared bus), but an SPI click in
  socket 3 is a *different controller* (spi3) with a *different CS pin*, and a
  UART click a different usart. None of this is selectable without forking the
  shield overlay (C1 × C2).
- **Two identical clicks** (sockets 1+2): silent S3-style collapse in DT — and
  physically unrealizable anyway on the shared I2C (HTS221 fixed 0x5f, R9).
- The per-socket nexus *does* make CS/INT/RST routing socket-relative
  (`&mikrobus_header 2 0` resolves per socket) — the GPIO half of the problem is
  solved; the bus half has no equivalent.

**Requirements extracted:**

- R14. A socket must be one referenceable unit bundling heterogeneous resources
  (bus endpoints, dedicated peripherals, pins); module attachment resolves the
  module's abstract needs (one I2C address, one CS, one INT…) against the
  socket's bundle.
- R15. Each bundled resource must declare its sharing regime — dedicated,
  shared-pool, shared-bus — because they compose differently: dedicated
  resources are claimed exclusively (UART), shared buses arbitrate by address
  (I2C) and need R9 realizability checks, shared pools allocate (CS slots, R4).

---

## Scenario S5 — Computed resource allocation: N modules on shared buses (hypothetical modules)

**Dials:** D4 (resource allocation) is the focus, at maximum: nothing can be
authored statically. D1=2 per module type, D3 as in S4-b.

**Hardware:** MikroE Quail (from S4-b) + hypothetical click modules (no in-tree
click exercises allocation; the connector layer stays evidence-grounded via
S4-b):

- **"Flash Click"** — SPI NOR flash, needs: 1 CS, the socket's SPI bus. Two
  instances, sockets 1 and 2 (both on `spi1`).
- **"Temp Click"** — I2C sensor with one address-select strap: ADDR jumper open
  → 0x48, closed → 0x49. Two instances, sockets 3 and 4 (I2C is `i2c1`, shared
  by *all* sockets — so these also share the bus with anything in sockets 1/2).

**The allocation problem:** no per-module author can write the final values.

- CS: `spi1.cs-gpios` must become a 2-entry array, drawing each socket's CS pin
  from its nexus (socket 1 CS = `gpioa 3`, socket 2 CS = `gpioe 0`), and each
  flash child's `reg` must equal its allocated index — a whole-bus computation
  across modules from different sockets (R4 at N>1).
- I2C: two Temp Clicks on one shared bus are realizable *only because* the
  address is strap-selectable; the expander must assign distinct addresses
  (0x48, 0x49), emit them as `reg`, and **output the required physical strap
  configuration** (socket 3: ADDR open; socket 4: ADDR closed). The DT alone is
  no longer the full build artifact — the rig has a *physical configuration
  sheet* that must ship with it (extends R6/R9).

**Expected expansion result** (golden sketch for later `build-rig/proposal/S5`):

```dts
&spi1 {
    /* allocated: index 0 → socket1 CS, index 1 → socket2 CS */
    cs-gpios = <&gpioa 3 GPIO_ACTIVE_LOW>, <&gpioe 0 GPIO_ACTIVE_LOW>;
    flash_click_1: nor@0 { reg = <0>; ... };   /* socket 1 */
    flash_click_2: nor@1 { reg = <1>; ... };   /* socket 2 */
};
&i2c1 {
    temp_click_1: sensor@48 { reg = <0x48>; ... };  /* socket 3, ADDR open   */
    temp_click_2: sensor@49 { reg = <0x49>; ... };  /* socket 4, ADDR closed */
};
/* plus: physical config sheet — socket 4 module: close ADDR jumper */
```

**Today's expression:** none — inexpressible at every level (S3 collapse for the
duplicate shields, S2 clobber for the CS array, no address assignment concept).
No baseline build; S2/S3 already document the failure modes this scenario
composes.

**Stress points:** allocation must be *stable*: rebuilding the same rig
description must yield identical assignments (reproducible builds, and R7
order-independence), and adding a third module later should not reshuffle
existing assignments a deployed fleet depends on.

**Requirements extracted:**

- R16. The expander allocates shared-pool resources bus-wide: parent array
  entries (drawn from each socket's nexus) and child `reg` written atomically
  across all modules on the bus, regardless of which socket contributed them.
- R17. Modules declare selectable-address domains as {address ↔ strap
  configuration} sets; the expander assigns distinct addresses and emits the
  chosen strap settings as a first-class build output (assembly/configuration
  sheet), not a side effect.
- R18. Allocation is deterministic and pinnable: same input → same assignment,
  independent of module declaration order; users can pin any assignment
  explicitly (e.g., `address = <0x49>;`) and the allocator works around pins.

---

## Scenario S6 — Nested composition: board → adapter → click (today's model: works once, by coincidence)

**Dials:** D5 (nesting) to 2 levels; D8 touched (passive adapter — active interposers are S8).

**Hardware:** NXP FRDM-K64F + `arduino_uno_click` (an Arduino shield carrying
**two mikroBUS sockets** — nesting in the flesh, all in-tree) + MikroE ETH Click
(ENC28J60, SPI) in socket 1.

**Verified behavior** (2026-07-17, three attempts):

1. **Host-board fragmentation.** First attempt used nucleo_f401re (continuity
   with S1–S3): hard parse error — `arduino_uno_click.overlay:57: undefined node
   label 'arduino_serial'`. The board defines `arduino_header`, `arduino_i2c`,
   `arduino_spi` but not `arduino_serial`: the "Arduino R3" label convention is
   à la carte, and nothing declares which subset a board offers or a shield
   requires (C2). Switched hosts to FRDM-K64F (defines all four).
2. **Working case** (`build-rig/upstream/S6`): FRDM-K64F + adapter + ETH Click
   configures clean, zero warnings. Notably the *GPIO* half nests correctly: the
   click's `int-gpios = <&mikrobus_header 7 ...>` resolves through a two-level
   nexus chain (mikrobus_header → arduino_header → `&gpioc`) — gpio-map
   composes recursively. This is the model for what R14 bundles must do for
   buses.
3. **Break case** (`build-rig/upstream/S6-break`): same host + adapter +
   Temp&Hum Click: hard parse error — `undefined node label 'mikrobus_1_i2c'`.
   The adapter exports unnumbered convention labels; the click (© 2026) targets
   Quail-style numbered ones. Two in-tree shields of the same ecosystem,
   incompatible purely through label-convention drift (C1 × C2).

**The chip-select coincidence chain.** The ETH Click sets **no CS at all** — a
third CS convention (S1/S2 shields write `cs-gpios` wholesale; Quail routes CS
per socket via nexus; this click assumes "the bus has CS 0 somehow"). In the
merged S6 tree, `spi0` has **no `cs-gpios` property**. It works because:

1. the click implicitly needs CS index 0 on its socket's bus, and
2. FRDM-K64F's `spi0_default` pinctrl muxes *native hardware chip-select*
   `SPI0_PCS0` onto PTD0 (`frdm_k64f-pinctrl.dtsi`, a group commented
   `/* pins conflict with uart2 */` — pin-mux conflicts are also unmodeled), and
3. PTD0 happens to be `arduino_header` D10, which the adapter happens to route
   to socket-1 CS.

Three layers — module assumption, SoC pin mux, adapter copper — agree by
coincidence, verified nowhere. The click in socket 2 (CS = D9) would configure
just as cleanly and fail at runtime.

**Requirements extracted:**

- R19. Nesting must re-export connectors: a carrier module declares its own
  sockets whose resources resolve through its *parent* connector, chainable to
  arbitrary depth — gpio-map already proves the pattern for pins; R14 bundles
  must chain the same way for buses, CS, and other roles.
- R20. Attachment must be an interface contract, not label coincidence: modules
  declare the connector type they need (and which subset of its signals);
  sockets declare the type they offer; matching is structural and checked at
  expansion. This single mechanism kills all three verified S6 failures.
- R21. Cross-layer implicit dependencies must be declared: *how* CS is provided
  (native controller pin-mux vs. GPIO from the socket bundle) is a property of
  the attachment, checked end-to-end through the nexus/adapter chain — including
  against SoC pinctrl claims on the same physical pins.

---

## Scenario S7 — Cross-module wiring: one instance's output feeds another's input (hypothetical counterpart)

**Dials:** D6 (cross-module wiring) is the focus. D1=2, heterogeneous (D7).

**Hardware:** Adafruit Data Logger (from S1 — its PCF8523 RTC exposes the
square-wave/clock output on the "SQ" pad, already shown jumpered in S1) + a
hypothetical "Pulse Counter" module, stacked on one Arduino header. The rig
wires RTC SQW as the counter's trigger, in one of two physically distinct ways:

- **(a) Via a header pin:** jumper SQ → D2. The counter module samples D2
  (`trigger-gpios = <&arduino_header D2>`). The net rides board copper.
- **(b) Point-to-point:** jumper SQ pad → the counter chip's trigger pad
  directly. The wire exists in **no connector** — no SoC GPIO, no header pin,
  pure module-to-module copper that only the rig assembly knows about.

**Today's expression:**

- (a) is *accidentally* expressible as two unrelated facts: the RTC node exists;
  the counter node references `&arduino_header 8`. The net itself — "these two
  are the same signal, RTC drives it" — is recorded nowhere. Worse, a
  resource-claim checker as specified so far (R5) would flag D2 as a
  *conflict*: RTC output claim + counter input claim, two claims on one pin.
  The distinction between collision and connection is signal **direction**.
- (b) is expressible in DT *output* terms — device-to-device phandle properties
  are standard DT practice (`clocks = <&...>`, `io-channels = <&adc 3>`,
  `trigger-sources`) — but authoring it today means shield B's overlay naming
  shield A's global label (`trigger-source = <&rtc0_adafruit_data_logger>;`):
  a hard textual coupling that breaks if A is absent, renamed, or — the rigs
  case — instantiated more than once. *Which* logger's RTC? Today's labels
  cannot say; this is the cross-instance reference problem in load-bearing form.

**Stress points:**

- The net is the missing object: today DT stores endpoints' opinions about pins,
  never the wire. Sub-case (b) shows the wire can exist with *no* DT-visible
  endpoint on one side at all (the SQ pad is not in any devicetree).
- Under multi-instantiation, references like "logger 2's RTC SQW" must be
  written in the rig description *before* the target node exists (it is
  generated by expansion) — raw DTS labels are structurally incapable of this;
  the reference must be instance-qualified and resolved by the expander into the
  generated node's phandle.

**Requirements extracted:**

- R22. Nets are first-class rig objects: a declared connection from an output
  port of instance A to input port(s) of instance B, whether routed through
  connector pins or point-to-point; expansion emits standard DT
  (shared-pin references or direct phandles) and validates net topology
  (exactly one driver, ≥1 listener).
- R23. Resource claims carry signal role (driver / listener / bidirectional):
  one driver + N listeners on a pin is a *net*, two drivers is a *conflict* —
  refines R5, which without direction produces false positives on every legal
  shared signal.
- R24. Instance-qualified references: rig syntax for "instance X's port P"
  (e.g., `logger2.rtc.sqw`), resolved at expansion into the generated node's
  phandle. Raw source-level DTS labels cannot express this (they name nodes that
  don't exist until expansion) — the strongest known argument that references
  are the front-end's hardest design point (cf. design-log 2026-07-17,
  transpiler-lite concession).
- R25. Module templates declare *ports*: named signals with direction and role
  (SQW: output; TRIG: input), extending the R14/R20 interface contract beyond
  consumed resources to offered signals — S7(b)'s SQ pad must exist in the
  module interface even though it appears in no connector.

---

## Scenario S8 — Active interposers: a mux that multiplies connectors (hypothetical shield, in-tree target structure)

**Dials:** D8 (adapters/muxes) at maximum — an *active* interposer, contrasting
S6's passive one. D1=4 with fixed addresses: deliberately the topology S3 proved
unrealizable, now made realizable by the interposer.

**Hardware:** any Arduino-header host + hypothetical "I2C Mux Shield" — a
TCA9548A (itself at 0x70 on the host bus) fanning out to 8 downstream I2C
sockets — carrying **four identical fixed-address sensors** (e.g. 0x48, no
address select), one per channel.

**The inversion:** this is the scenario where plain devicetree is *least*
deficient. Mux channels as child buses are standard, in-tree DT: binding
`dts/bindings/i2c/ti,tca9548a.yaml`, driver, and real-board usage
(`boards/nxp/imx943_evk/imx943_evk_mimx94398_cm.dtsi` — `pca9548a@77` with
`mux_i2c@0..N` children, each a full bus that hosts devices). Four devices at
`reg = <0x48>` under four different channel nodes is a perfectly valid, driver-
supported tree today. **The final tree is hand-authorable; the *composition* is
not:** a shield for the mux would hardcode which module sits behind which
channel, and each sensor shield hits the S3 singleton collapse and cannot be
told "behind channel 3." Expressible output, inexpressible assembly.

**What distinguishes active from passive interposers:**

- S6's adapter *rewires* existing resources (nexus pass-through); references
  resolve *through* it and vanish in the output.
- The mux *creates new resource scopes rooted in its own device node*: each
  downstream socket's I2C endpoint is a node that exists only inside the
  interposer's expansion. Address uniqueness becomes per-scope (0x48 four times
  is legal — in four scopes), and the interposer itself claims a resource on the
  *parent* scope (0x70 on the host bus).
- Variant worth recording: interposers can also *extend pools* rather than
  isolate scopes — e.g. a GPIO-expander shield providing 8 new CS lines for SPI
  modules. Same shape: new resources rooted in the interposer's own device.
- Scopes must compose: mux-behind-mux is real practice; nothing about R26 below
  may assume depth 1 (it falls out free if socket re-export R19 and scoping are
  compositional).

**Today's expression:** none via shields (composition inexpressible, per above).
No upstream baseline build — but the golden output for
`build-rig/proposal/S8` can be modeled directly on the imx943_evk structure.

**Requirements extracted:**

- R26. Interposer templates declare downstream sockets whose bus endpoints are
  generated *within the interposer's own expansion* (mux channel nodes), and all
  realizability (R9) and allocation (R16) checks become scope-aware: uniqueness
  and pool exhaustion are evaluated per bus scope along the interposer chain,
  not globally.
- R27. The channel↔module assignment is an allocation domain like CS slots and
  addresses (R16/R18): deterministic, pinnable, and emitted into the physical
  configuration sheet (R17) — "sensor 3 plugs into mux socket 5" is assembly
  information exactly like a jumper setting.

---

*S1–S8 sweep complete (2026-07-17). Requirements R1–R27 accumulated and
consolidated into six concepts in `requirements.md` (assemblies & instantiation,
interface contracts, resource model, allocation & realizability, nets &
references, expansion contract). Candidate later additions: multi-board rigs
(inter-board links), rigs with off-DT components (USB, network peers), Kconfig
scenario pass.*
