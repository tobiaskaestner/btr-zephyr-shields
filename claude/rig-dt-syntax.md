# Rigs — Syntax Reference

A one-stop reference for every property and key across the four layers of the
rig model. This is the *what*; `conventions.md` is the *why* (each entry
cross-references its convention). Everything here is exercised by the trial
under `frontend-trial/` and its `SCENARIOS.md`.

A rig is authored across four layers, each with its own namespace. The prefix
tells you which layer owns the fact:

| Layer | File | Language | Namespace |
|---|---|---|---|
| topology | `rig.yml` | YAML | plain keys |
| shield template | `<shield>.shield` | DTS-syntax template (not a devicetree) | `shield,*` |
| board socket node | board `<board>.dts` fragment | DTS | `socket,*` + `compatible` |
| connector type | `bindings/{plug,socket},<type>.yaml` + `<type>.h` | YAML + C header | binding keys |

Reference conventions: `connector,*` (v2's connector-type DTS nodes) and
`rig,*` (candidate-1's rig-file properties) are **retired** — types are now
bindings, and topology is `rig.yml`.

## File suffixes — shields are shields, not overlays

The suffix says how the file enters the pipeline, so the regime is legible
without opening it:

| Suffix | Fed to | Meaning |
|---|---|---|
| `.dts` | dtc (as a root) | a complete devicetree — a board |
| `.dtsi` | CPP `#include` | a devicetree *include*, pulled into a `.dts`/`.overlay` |
| `.overlay` | dtc (as a delta) | applied **as-is** on top of an existing tree |
| **`.shield`** | the **rig loader** | a **template** — instantiated (socket-relative, N times, `shield,*` metadata), not included and not applied as-is |

A shield template is a genuine third kind of DT-shaped file: parsed as its
own translation unit (never `#include`d) and consumed by the rig
loader/expander (never by dtc). It is neither an include (`.dtsi`) nor an
applied delta (`.overlay`) — so it gets its own suffix. The board fragment
keeps `.dtsi` (it *is* `#include`d into the board's `.dts`); the rig payload
keeps `.overlay` (it *is* applied as-is, Conv. 8).

This directly types a shield's **board-specific fragments** by suffix
(preserving Zephyr's `<shield>/boards/<board>.overlay` mechanism, split by
regime):

- `<shield>/boards/<board>.shield` — board-conditional *template* fragment,
  loaded into the rig model (checked, projected) when the rig's board matches.
- `<shield>/boards/<board>.overlay` — board-conditional *raw* fragment,
  appended to the output as-is (e.g. a board-node poke).

---

## Layer 1 — `rig.yml` (topology)

All references are strings, resolved by the loader.

```yaml
rig:
  name: quail-temp-farm            # rig name
  board: mikroe_quail              # board-DT name (cross-tree string)
  instances:
    - name: temp_b                 # unique instance name in this rig
      shield: temp-click           # shield-library name
      socket: quail_sock4          # board socket label, OR <carrier>.<exposed> (nested, R19)
      pin:                         # optional per-instance selections (keys = config-element names)
        addr_strap: 0x49           #   strap  -> address selection (R17)
        # irq_jmp: D2              #   jumper -> position selection, by header name (R6)
      invert: true                 # optional: flip active level of the module's gpio signals
  wires:                           # optional cross-instance nets (S7)
    - from: logger_1.sq            # <instance>.<node>, resolved within that instance's shield (R24)
      to: counter_1.trig
      route: adhoc                 # ad-hoc jumper, OR { via: D2 } to route through a header position
```

| Key | Where | Value | Meaning |
|---|---|---|---|
| `name` | `rig:` | string | rig name |
| `board` | `rig:` | string | the board this rig builds for (Conv. 5) |
| `instances` | `rig:` | list | the modules placed on the board (R8) |
| `name` | instance | string | unique instance name; basis of generated labels (Conv. 8) |
| `shield` | instance | string | which shield template to instantiate |
| `socket` | instance | string | board socket label, or `<carrier>.<exposed>` for a nested carrier socket (R19) |
| `pin` | instance | map | per-instance selection from a config element's domain (strap address / jumper position) |
| `invert` | instance | bool | flip the active-level bit of the module's gpio signals (Conv. 9 / bridle `_inv`) |
| `wires` | `rig:` | list | cross-instance nets (R22) |
| `from` / `to` | wire | `<instance>.<node>` | dotted instance-qualified reference (R24) |
| `route` | wire | `adhoc` \| `{via: <pos>}` | pad-to-pad jumper, or routed through a header position |

Companion (not loader-parsed): the optional **`rig.overlay`** DT payload beside
`rig.yml` — output-regime tree facts (`aliases`, `chosen`, escape hatch),
applied after the generated overlay (Conv. 8).

---

## Layer 2 — shield template (`shield,*`)

A shield is a DTS-shaped template under `/ { shield-templates { … } }`. Reserved
child-node structure:

| Node | Role |
|---|---|
| `plug { #gpio-cells = <2>; }` | the shield's stand-in for the socket it mates; the position/bus reference frame (Conv. 2/3) |
| `i2c {}` / `spi {}` / `uart {}` | bus proxy nodes; device children sit here, matched to the socket's `socket,<bus>` |
| `gpio {}` (or any non-proxy group) | plain (non-bus) device group |
| `pads {}` | arity-1 connectors — signals in no connector (S7) |
| `config {}` | configuration elements: straps and routing jumpers |
| `<name> { compatible = "socket,…"; }` | an *exposed* socket, for carriers/interposers (R19, Conv. 6-nesting) |

The nine `shield,*` properties:

| Property | On node | Value | Meaning | Conv. |
|---|---|---|---|---|
| `shield,plugs` | shield root | string | connector type consumed, compatible-style (`"arduino-r3"`) — the one required property | 2 |
| `shield,cs-position` | SPI device | header index | copper-fixed chip-select (1-element position domain) | 2 |
| `shield,addr-from` | I2C device | phandle → strap | deferred-address resolver; exactly one of `reg` / `shield,addr-from` | 2 |
| `shield,collect` | device | string (compatible) | mark device an *entry* in a collection binding (`"gpio-keys"`); no `compatible` of its own | 9 |
| `shield,domain` | config strap | `<addr state>…` pairs | **address** domain; presence ⇒ node is a strap | 2 (R17) |
| `shield,position-domain` | config jumper | `<pos state>…` pairs | **position** domain; presence ⇒ node is a routing jumper | 2 (R6) |
| `shield,sheet-label` | strap / jumper | string | human label on the physical configuration sheet | 2/7 |
| `shield,role` | pad | `driver`/`listener`/`bidir` | endpoint role on its net (R23) | 2 |
| `shield,of` | pad | phandle → device | the device the pad belongs to | 2 |

Signal wiring uses **gpio-specs** targeting the plug (or a jumper), with the
index from the connector's dt-bindings header:

```dts
int1-gpios = <&dl_plug ARDUINO_HEADER_R3_D7 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>;  /* fixed position */
irq-gpios  = <&w_irq_jmp GPIO_ACTIVE_LOW>;                                       /* position deferred to a jumper */
```

A routing-jumper node carries `#gpio-cells = <1>` (it supplies the position;
flags stay on the signal). Authored example — `frontend-trial/common-dts/shields/*.shield`.

---

## Layer 3 — board socket node (`socket,*`)

A real node in the board's own devicetree (Conv. 4), a gpio nexus, validated by
the `socket,<type>` binding. The expander finds it by compatible.

```dts
nucleo_ard: connector {
    compatible = "socket,arduino-r3";       /* identifies the connector type */
    #gpio-cells = <2>;
    gpio-map = <ARDUINO_HEADER_R3_D7 0 &gpioa 8 0>, … ;   /* position -> SoC pin */
    socket,i2c = <&i2c1>;
    socket,spi = <&spi1>;
    /* absent socket,uart = subset exposure, declared by absence */
};
```

| Property | Value | Meaning |
|---|---|---|
| `compatible` | `"socket,<type>"` | the connector type this socket offers |
| `#gpio-cells` | `<2>` | nexus cell count (position, flags) |
| `gpio-map` | nexus rows | position → SoC pin (`<pos 0 &ctrl pin 0>`); the position-index single source |
| `socket,i2c` / `socket,spi` / `socket,uart` | phandle → controller | bus offered on this socket; **absence = not offered** (subset exposure, R20) |
| `socket,cs-pool` | array of indices | ordered CS candidate positions (default in the binding; e.g. `[16,15,14]`) |
| `socket,stackable` | boolean | present ⇒ N consumers may mate (stacking headers); absent ⇒ exactly one |
| `socket,pwm-map` | 5-cell rows | position → (timer, channel) — the PWM function-nexus (`<pos 0 &tcc0 ch 0>`) |
| `socket,adc-map` | 5-cell rows | position → (adc, channel) — the ADC function-nexus |

**Multi-function positions (Slice A).** A position is one net reachable as
several functions; the board declares a nexus per function (`gpio-map`,
`socket,pwm-map`, `socket,adc-map`). A shield device picks the function by
property — `gpios`/`*-gpios` (2 cells: position, flags), `pwms` (3: position,
period, flags), `io-channels` (1: position). The expander resolves the
position through the matching nexus, emits GPIO in nexus form and PWM/ADC in
resolved form (`<&tcc0 ch period flags>`, `<&adc0 ch>`), enables the
controller, and notes the board pin-mux (pinctrl application is board-side,
stubbed). A PWM/ADC claim is exclusive on both the **pin** and the
**channel**.

**Carrier / interposer pass-through form** (R19): an exposed socket lives in the
*shield* file (Layer 2) and points everything at the carrier's own plug — the
expander composes it against whatever the carrier plugs into:

```dts
mb1 {
    compatible = "socket,mikrobus";
    #gpio-cells = <2>;
    gpio-map = <MIKROBUS_CS 0 &auc_plug ARDUINO_HEADER_R3_D10 0>, … ;  /* parent = the plug */
    socket,spi = <&auc_plug>;                                         /* pass parent's SPI through */
    socket,i2c = <&auc_plug>;
};
```

---

## Layer 4 — connector type (bindings + index header)

A connector type IS three artifacts (Conv. 1); there is no type devicetree.

**`bindings/plug,<type>.yaml`** — shield-side contract, consumed by the loader:

| Key | Value | Meaning |
|---|---|---|
| `plug` | string | the type name (`"arduino-r3"`) |
| `bus-proxies` | list | allowed bus proxy nodes (`[i2c, spi, uart]`) |
| `positions` | map | claimable positions → `{function: gpio\|analog, optional: bool}` |

**`bindings/socket,<type>.yaml`** — board-side, edtlib-validated: `compatible:
"socket,<type>"`, a `properties:` schema (the `socket,*` above, with
`socket,cs-pool` default and `socket,stackable` presence encoding type-level
facts), and `gpio-cells:` names.

**`include/dt-bindings/connector/<type>.h`** — position index `#define`s (the
single source of truth shared by board `gpio-map`, shield references, docs).
Note: no trailing comments on `#define` lines (the index parser is strict).

---

## Cross-cutting rules

- **Entity-scoped naming.** The prefix says which layer owns a fact
  (`shield,*` / `socket,*` / `rig.yml` keys); the specific key says what kind of
  thing it is.
- **Reference kinds.** Within a shield: phandles (`&plug`, `&strap`, `&device`),
  parse-checked by dtlib. From `rig.yml` to below: name strings (`board`,
  `shield`, `socket`), resolved by the loader. Cross-instance: dotted
  `<instance>.<node>` (R24). In the output: generated composed labels
  `<instance>_<shield-label>` (Conv. 8), and synthesized nexus nodes for
  carrier sockets (Conv. 6-nesting, Option C).
- **Authority rule (domain vs selection).** The shield declares only *domains*
  (`shield,domain` for addresses, `shield,position-domain` for positions;
  `shield,cs-position` is the 1-element copper-fixed case). The `rig.yml`
  `pin:` owns the per-instance *selection*. The expander authors the resolved
  value (`reg` + unit-address, allocated CS, routed position) and writes any
  human action to the config sheet.
- **Presence-as-typing.** `shield,domain` vs `shield,position-domain`
  distinguishes a strap from a jumper; `shield,collect` distinguishes a
  collection entry from a standalone device; presence/absence of `socket,<bus>`
  encodes subset exposure; presence of `socket,stackable` encodes mating
  multiplicity.
