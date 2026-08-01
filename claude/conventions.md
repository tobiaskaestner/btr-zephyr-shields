# Rigs — Front-End Conventions (v4, rig.yml verdict 2026-07-19)

v3 → v4: the front-end verdict is **decided — candidate #2, `rig.yml`**
(YAML topology + DTS payloads), ratified 2026-07-20 after the expander-
prototype comparison (`frontend-trial/EVALUATION.md` §"Expander prototype
results"). The decisive finding inverted the pre-trial framing: stock dtlib
gives no file:line for cell-value reference errors, while the hand-built
YAML resolver reports file:line + key path + candidate lists. Candidate #1
(pure valid-DTS: a `/ { rig { … } }` file with `rig,*` properties and
`<&instance &node>` phandle pairs) is **retired**; its full spec lives in
git history (v3) and its trial files under `frontend-trial/candidate-1-dts/`.

Everything upstream of the front-end (requirements, ontology, rig model) is
front-end-neutral. Toolchain terms (loader / rig model / expander = analyzer
+ emitter) are defined in `architecture.md`.

Lineage: v2 introduced entity-scoped naming, logical connector types, bus
membership by parentage, and typed sockets in the board's own DT; v3 made
connector types bindings + index header, gave shields plug nodes and string
typing, and grew the address authority rule. The trial files under
`frontend-trial/` are the normative examples, smoke-tested (CPP + stock
dtlib for the DTS payloads; PyYAML + the prototype loader for `rig.yml`).

## The two source artifacts

A rig has exactly one topology artifact and reuses DTS everywhere below it:

| artifact | language | who reads it | what it holds |
|---|---|---|---|
| `rig.yml` | YAML | the loader | topology: instances, sockets, pins, wires |
| shield `<name>.shield` | DTS-syntax template (not a devicetree) | the loader (dtlib), one TU **per shield** | the shield's devices, pads, straps, plug node |
| `bindings/{socket,plug},<type>.yaml` | YAML bindings | edtlib (socket) / loader (plug) | connector-type contract |
| `include/dt-bindings/connector/<type>.h` | C header | CPP | position-index single source |
| board `<board>.dts` (+ socket fragment) | DTS | the expander (edtlib) | typed socket nodes |
| `rig.overlay` (optional) | DTS overlay | **nobody in the pipeline** — dtc at build | rig-level tree facts (Conv. 8) |

## Ground rules

1. **Topology is YAML; payloads are DTS.** `rig.yml` is the assembly
   instruction and is pure YAML — every reference in it is a **string**
   (a name), resolved by the loader. Shields are DTS-shaped *templates*:
   they borrow DTS syntax but are not devicetrees (they are instantiable and
   socket-relative); only the expander's *output* is a real overlay that
   joins the board DT. Reserved shield nodes nest under root
   (`/ { shield-templates { … } }`; top-level `/name/ { }` is not valid DTS —
   trial finding).
2. **Two validation regimes.** Source: PyYAML + JSON-schema (`rig.yml`),
   dtlib + the plug binding (shields). Output: dtc + Zephyr bindings, as
   today. Board-side socket nodes are ordinary board DT — validated there by
   their own binding. `rig.overlay` is output-regime, validated by the
   existing toolchain only (Conv. 8).
3. **One translation unit per shield.** Each shield `.shield` file is preprocessed
   and dtlib-parsed on its own, giving every shield a **private label
   namespace**. Shield-internal labels need only be unique within their
   shield; nothing references them globally (the rig file uses instance-
   qualified names; output labels are generated). This is why v3's
   `dl_`/`tc_` prefix discipline is gone — it existed only to keep
   candidate #1's global phandle namespace collision-free.
4. **Entity-scoped property naming** in the DTS payloads: `connector,*` in
   connector types, `shield,*` in shield definitions, `socket,*` on board
   socket nodes. The prefix tells you which layer owns the fact. (`rig,*` is
   retired with candidate #1 — rig facts now live in `rig.yml` as plain
   keys.)
5. **Within a shield, references are phandles; from `rig.yml`, references
   are strings.** A shield's internal wiring (`<&plug …>`,
   `shield,addr-from = <&tc_addr_strap>`, `shield,of = <&dl_rtc>`) is
   parse-checked by dtlib. Every rig→below reference (`board`, `shield`,
   `socket`, a strap name in `pin:`, an `instance.node` in `wires:`) is a
   string resolved by the loader — against the shield library, the board DT,
   or within the named instance's shield.
6. **Compatibility scope**: no shim for existing boards/shields. Boards and
   shields opt in by conversion; the legacy `-b`/`--shield` path (S1) never
   breaks. Rigs are purely additive.

## The build-system target

A **rig is a third build-system entity**: self-contained (contains ≥1 board,
the projection-target MCU), unlike shields which never build alone.
`west build --rig <name>` — no `-b`. Discovery via a `rigs/` root and
`rig.yml`, mirroring `board.yml`/`shield.yml`.

## Convention 1 — Connector types ARE bindings (+ index header), not devicetrees

A connector type is a **contract**, and DT's native schema language is
bindings. There is no type devicetree (v2's `/connector-types/` nodes were
schemas pretending to be instances — nothing structurally consumed them). A
type is three artifacts, generalizing the upstream `arduino-header-r3`
binding+header pattern from pins to links:

- **`bindings/socket,<type>.yaml`** — validates board socket nodes (edtlib,
  for free): `gpio-map` (child pins = header indices), `socket,i2c/spi/uart`
  as *optional* phandle properties (subset exposure = binding optionality),
  `socket,stackable` (mating multiplicity), `socket,cs-pool` (ordered CS
  candidate indices; mikroBUS `[CS]`, Arduino `[D10, D9, D8]`).
- **`bindings/plug,<type>.yaml`** — the shield-side contract, consumed by the
  loader: allowed bus proxies (pairing `i2c` proxy ↔ `socket,i2c` is
  declared here, once), claimable positions with functions/optionality.
- **`include/dt-bindings/connector/<type>.h`** — position indices: the single
  source of truth shared by board gpio-map, shield references, and docs.

Link kinds imply addressing mode and regime (spi → out-of-band pool, i2c →
device-static, uart → none). Bus member pins are electrical realization — not
modeled. Dual-function copper (Arduino D11–D13) is discovered from net
identity at the board binding, never declared in the type.

Normative examples: `frontend-trial/common-dts/bindings/*.yaml`,
`…/include/dt-bindings/connector/*.h`.

## Convention 2 — Shields: bus membership by parentage; plug node as reference frame

Under `/ { shield-templates { … } }`. The consumed type is named **by string**,
like compatibles: `shield,plugs = "arduino-r3";`. Each shield declares a
local **plug node** — its stand-in for whatever socket it mates:

```dts
data_logger: adafruit-data-logger {
    shield,plugs = "arduino-r3";
    dl_plug: plug { #gpio-cells = <2>; };
    i2c {
        dl_rtc: rtc@68 { reg = <0x68>; /* 1-element domain */
            int1-gpios = <&dl_plug ARDUINO_HEADER_R3_D7 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>; };
    };
};
```

Devices sit under **bus proxy nodes** (`i2c { }`, `spi { }`) matched to the
socket's `socket,<name>` per the plug binding — the DT idiom (devices are
children of their bus), kept shield-local: extending a shared node by label
would merge all shields' devices and dissolve ownership. Labels are
shield-scoped (Ground rule 3), so short local names (`dl_rtc`) no longer
need a per-shield prefix — the prefixes in the trial files are legacy.

**Address authority rule** (supersedes v2's reg rule):

- The **shield declares the domain, never the selection** — reachable
  addresses are copper knowledge (`shield,domain = <0x48 0>, <0x49 1>`); a
  fixed-address device is the 1-element domain. Domains must not migrate to
  the rig file (copper facts would drift).
- The **rig file owns the selection** — per-instance, human-configurable, in
  `rig.yml`: `pin: { addr_strap: 0x49 }`; left free, the allocator selects
  and the config sheet instructs the human.
- The **expander is the sole author of `reg` and the unit-address in the
  output, always as a matching pair**. Source nodes of non-singleton-domain
  devices (and all pool-addressed SPI devices) carry *no `reg`* — the reg ==
  unit-address rule becomes a rendering guarantee, not an authoring
  obligation. Authored `reg` (singleton domains, `rtc@68`) is validated.
- **Deferred addresses are explicit, not absent** (pushback round 3):
  the device points at its resolver — `shield,addr-from = <&tc_addr_strap>;`
  (device→strap; `nvmem-cells` precedent for value-comes-from-that-node).
  Schema rule: an addressable-bus device carries exactly one of `reg` /
  `shield,addr-from`, making forgot-vs-deferred checkable. Optionally the
  unit-address carries the resolver's name as a human-readable marker:
  `sensor@addr_strap` — dtlib-legal (unit-address is lexically just node-name
  characters; dtlib lowercases it; `@{...}`/`@$(...)` do NOT parse), pure
  documentation with a lint that it matches the `addr-from` target. A real
  placeholder syntax was considered and rejected: it re-opens the grammar
  fork for a cosmetic gain on two node classes and starts the slope toward a
  template language.

**Position selection: routing jumpers** (R6, 2026-07-20) — the position-side
twin of the address strap. A signal's *net attachment* (which connector
position it uses) can be a config element too, with the same fixed / pinned /
allocated trichotomy as addresses:

- **fixed** — copper decides: `int1-gpios = <&plug ARDUINO_HEADER_R3_D7 …>`
  (a 1-element position domain), and `shield,cs-position = <…>` for a
  copper-fixed CS.
- **allocated** — the expander picks from the socket's `socket,cs-pool`.
  This is CS-only: a chip-select is fungible, so pool allocation is automatic
  (it resolves the S2 cs-gpios clobber, playbook collision A).
- **pinned** — a **routing jumper**: a `config` node declaring a
  `shield,position-domain = <position state>, …`, referenced by the signal
  exactly like the plug but with the position deferred:

  ```dts
  config {
      w_irq_jmp: irq-jmp {
          #gpio-cells = <1>;            /* supplies the position; flags stay on the signal */
          shield,position-domain = <ARDUINO_HEADER_R3_D7 0>, <ARDUINO_HEADER_R3_D2 1>;
          shield,sheet-label = "IRQ select (SJ2)";
      };
  };
  spi { wifi {
      irq-gpios = <&w_irq_jmp GPIO_ACTIVE_LOW>;   /* position from the jumper, flags kept */
  }; };
  ```

  The rig selects in `rig.yml` under the same `pin:` map used for address
  straps — `pin: { irq_jmp: D2 }` (position by name). The expander resolves
  the position and rewrites to the standard `irq-gpios = <&socket <pin>
  flags>`, and emits the human action to the config sheet. **A non-CS
  routing jumper must be pinned by the rig** (positions are not auto-routed —
  only the fungible CS pool is); an unpinned or out-of-domain selection is a
  `phys-position` error. This is the position-space analogue of the address
  authority rule: the shield declares the *domain* (copper), the rig owns the
  *selection*, the expander authors the resolved position.

Other `shield,*` facts: `shield,domain`/`shield,sheet-label` (address
straps), pads with `shield,role`/`shield,of`. The used connector subset is
derived from proxies + referenced positions.

**Board-specific fragments** (preserving Zephyr's `<shield>/boards/<board>.overlay`,
split by regime — see `rig-dt-syntax.md` §File suffixes). A shield may carry
per-board deltas applied only when the rig's board matches:
`<shield>/boards/<board>.shield` is a board-conditional *template* fragment
(loaded into the rig model, checked, projected); `<shield>/boards/<board>.overlay`
is a board-conditional *raw* fragment (appended to the output as-is, e.g. a
board-node poke). The `.shield`/`.overlay` suffix tells you which regime. The
loader knows the board from `rig.yml`, so it pulls in the matching fragment.

## Convention 3 — Position references: plug-relative, header-indexed

Shield properties keep their real names and cell layouts; phandles target the
shield's own **plug node**, with the index from the shared header:
`int-gpios = <&dl_plug ARDUINO_HEADER_R3_D7 GPIO_ACTIVE_LOW>;`. In-tree,
parse-checked, and reads as "pin D7 of *my* connector." The expander rewrites
`&plug` to the mated socket node (which IS the nexus) — emitting exactly what
good shields hand-write today. Verified: nexus chains compose recursively
(S6); the board's gpio-map uses the same header constants (single source).

## Convention 4 — Typed sockets in the BOARD's devicetree

Board-side realization is a **proper node of the board DT** — not a rig-side
fragment. Real phandles, dtc-resolved, validated by a normal binding:

```dts
nucleo_ard: connector {
    compatible = "socket,arduino-r3";
    #gpio-cells = <2>;
    gpio-map = <8 0 &gpioa 10 0>, …;       /* the socket IS the nexus */
    socket,i2c = <&i2c1>;
    socket,spi = <&spi1>;
    /* absent socket,uart = subset exposure, declared by absence */
};
```

Migration, not shim: a board replaces its legacy connector `.dtsi` with this
fragment, which also carries the legacy labels (`arduino_header:
&connector…{}`, `arduino_i2c: &i2c1 {}`) so unconverted shields keep working.
The per-socket nexus + binding are plain, upstreamable, rig-agnostic DT.
The `gpio-map` child pins use the **same dt-bindings header** the shields
reference — the position-index single source of truth. Consequence: **the
expander reads the board DT** to find socket nodes (by compatible) — accepted
trade for killing v1's string-encoded bindings.

Normative example: `frontend-trial/common-dts/boards/*.rig.dtsi`.

## Convention 5 — The rig file (`rig.yml`)

Topology only, all references by string:

```yaml
rig:
  name: quail-temp-farm
  board: mikroe_quail                 # cross-tree: board-DT name
  instances:
    - name: flash_a
      shield: flash-click             # shield-library name
      socket: quail_sock1             # cross-tree: socket label in the board DT
    - name: temp_b
      shield: temp-click
      socket: quail_sock4
      pin:
        addr_strap: 0x49              # selection within temp-click's strap domain
```

Instances are countable (R8); stacking = several instances naming the same
socket (legal iff the socket's connector type is stackable). `pin:` keys name
config straps *within the instance's shield* — the loader resolves them there
(a name that is not a strap of that shield is a `lang-pin` error with the
shield's strap list). Interposer shields expose their own socket nodes;
nesting recurses; scope creation is structural (device roots a new link).

## Convention 6 — Instance-qualified references: dotted names (R24)

Cross-instance wiring uses `<instance>.<node>` strings, resolved by the
loader (`frontend-trial/candidate-2-hybrid/*.rig.yml`):

```yaml
  wires:
    - from: logger_1.sq               # instance logger_1, node sq of its shield
      to: counter_1.trig
      route: adhoc                    # or: { via: D2 } — a header position name
```

Resolution rules (the loader work candidate #1 got from dtlib, now defined):
the part before the dot is an **instance name** (unique in the rig); the part
after is resolved **within that instance's shield** over pads ∪ devices ∪
straps and must be **unique** there. This makes the cross-pair mistake that
dtlib cannot catch — a node that exists but on the *wrong* instance's shield —
a first-class `lang-wire-ref` error naming the shield's actual node set.
`route: adhoc` = a pad-to-pad jumper existing in no connector (S7b);
`route: { via: <position> }` = the net rides that header pin (S7a). Chains
extend for nesting (`carrier_1.sock2` → …), designed but not yet exercised.

## Convention 7 — Expander output

Per firmware image, **four** outputs: plain `.overlay` (composed labels per
Conv. 8, allocated `reg`/`cs-gpios`, position phandles rewritten to socket
nexus references); the **physical configuration sheet** (`shield,sheet-label`
entries, socket assignments); **test expectations** (A6); and a **Kconfig
fragment** — the activation manifest naming the instantiated shield types +
board (so their type-level `Kconfig.defconfig` apply, the rig.yml replacing
the `--shield` CLI) plus rig-derived defaults. No per-instance driver config
in Kconfig: that lives in DT, and driver auto-enable follows the overlay via
`dt_compat_enabled` (decided 2026-07-21). Fidelity per the compatibility
scope: converted-hardware rigs mirroring S1 diff equal to the legacy output.
The generated overlay is the first of up to two overlays a rig contributes
(the optional hand-authored `rig.overlay` is the second — Conv. 8).

## Convention 8 — The rig directory; labels, aliases, chosen (2026-07-19)

A rig is a **directory**, completing the entity symmetry:

| entity | metadata / topology | DT payload |
|---|---|---|
| board | `board.yml` | `<board>.dts` (tree root) |
| shield | `shield.yml` | `<shield>.overlay` |
| rig | `rig.yml` (loader-parsed) | `rig.overlay` (optional, output-regime) |

`.overlay`, not `.dts`: a `.dts` is a tree root, and a rig is never the
root — the board is. The rig's DT payload patches an existing tree.

**Output labels are compositions** — `<instance>_<shield-local label>`
(`logger_a_dl_rtc`). Deterministic, collision-checked by the analyzer
(strong contract: the emitter never discovers problems), stable under
adding/removing *other* instances (R18 spirit). This scheme is the rig's
**public reference API**: the same name appears in the final `zephyr.dts`.

**`rig.overlay` lives in the output regime.** Never parsed by the loader,
never in the rig model, not interpreted by the expander. It rides the
standard overlay chain AFTER the generated overlay:

    board.dts → <generated>.overlay → rig.overlay → EXTRA_DTC_OVERLAY_FILE

so it can reference generated instance labels (`&logger_a_dl_rtc`) and
plain dtc resolves them. Validated by dtc + edtlib bindings like any
overlay — the two-regimes ground rule is unchanged. It doubles as the
**escape hatch** for tree-level facts the rig model does not (yet) express
(`chosen` console, `clock-frequency` on a board bus, pinctrl tweaks) —
de-risking adoption, same philosophy as "the legacy path never breaks."

**Aliases are a selection problem**; the authority-rule pattern applies:

- **Shields never author `/aliases` or `/chosen`** — a tree-level singleton
  inside a reusable unit is the S3 collapse in miniature. Loader error.
- **The rig owns the selection**, authored natively in `rig.overlay`:
  `aliases { rtc0 = &logger_a_dl_rtc; };`
- **No expander auto-numbering** (`rtc0`/`rtc1` from a counter): any counter
  scheme renumbers a deployed rig's aliases when instances come and go — the
  R18 reshuffle ban applied to names. If a consumer ever demands generated
  aliases, they must derive from instance names; parked until then.
- `chosen`: same treatment; collision with the board's own `chosen` entries
  is an error, no silent override (detail open until a scenario exercises it).

**Ownership rule** (documented now, lint parked): the expander is the sole
author of bus children, `reg`, and `cs-gpios` in the output; writing them
from `rig.overlay` is undefined behavior. Accepted trade, eyes open: a
typo'd generated label in `rig.overlay` surfaces as a dtc undefined-label
error at build time — the one place rig authoring falls back to today's
error quality (loader-side lints parked, see `parked.md`).

This resolves R10 (aliases/`chosen` policy).

## Convention 9 — Device collections (aggregation, 2026-07-21)

Some bindings are **collections**: one node carries the `compatible` and each
real device is a *child entry* (`gpio-keys`, `gpio-leds`, `pwm-leds`, …). Under
multi-instantiation, N modules of the same kind must land as N children of
**one** collection node — not N separate nodes (non-idiomatic), and not one
node clobbered N times (the S3 collapse).

A shield marks such a device an **entry**, naming the collection by its
compatible; the entry carries no `compatible` of its own:

```dts
gpio {
    gb_key: button {
        shield,collect = "gpio-keys";
        gpios = <&gb_plug GROVE_SIG0 (GPIO_PULL_DOWN | GPIO_ACTIVE_HIGH)>;
    };
};
```

The expander groups every collected entry across all instances **by the
collect compatible** and emits one collection node per compatible, each entry
a child keeping its own per-instance label (`<instance>_<shield label>`, the
Conv. 8 public API) and node name:

```dts
/ {
    gpio_keys: gpio_keys {
        compatible = "gpio-keys";
        btn_start_gb_key: btn_start { label = "btn_start"; gpios = <&grove_d2 0 0x20>; };
        btn_stop_gb_key:  btn_stop  { label = "btn_stop";  gpios = <&grove_d6 0 0x21>; };
    };
};
```

This is aggregation, not collapse — each entry keeps its identity (R8); the
merge is emission-only, so net/conflict analysis is unchanged. Normative
example: the bridle port (`SCENARIOS.md`, `shields/grove-btn.shield`), where it
replaces bridle's path-merge of 64 per-pin overlays. Parked: an explicit
collection *name* (to split into multiple collections of one compatible), and
merging into a collection the **board** already provides.

## Next step

The verdict is in; the prototype covers the full S2–S7 sweep plus the bridle
real-hardware port, and Ground rule 3 (per-shield translation units) is now
implemented — labels are shield-scoped, no prefix discipline. Remaining, per
`NEXT-SESSION.md`: S8 (active interposer / scope creation), then the
S1-fidelity diff (`build-rig/proposal/S1` vs `build-rig/upstream/S1`), then the
build-integration phase (Kconfig manifest, pinctrl application, `rig-` prefix
sweep — see `parked.md`).
