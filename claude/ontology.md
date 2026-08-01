# Rigs — Physical Ontology

§1–2 double as the schema of the **rig model** (the loaders' output, the
expander's input — see `architecture.md` for the toolchain terms).

Grounding for the six concepts in `requirements.md`. Base: Tobi's sketch
(2026-07-17) — boards vs shields, nets vs buses, connectors, chaining, bus
creation. This document formalizes it and marks every **refinement** where the
S1–S8 evidence forced a change to the sketch.

## 1. Entity catalog

### Net
The primitive: one equipotential piece of copper. Everything else is structure
over nets. Two nets are the same net if and only if they are electrically
continuous — sharing (Quail I2C across 4 sockets, Grove sockets 5/6 on
gpio0 26) is *discovered from net identity*, never separately declared (R13).

**Refinement 1 — nets don't have functions; endpoints do.** The sketch lists
"GPIO, TIMER/PWM, ADC, DAC" as net kinds, but these are *endpoint capabilities*,
not properties of copper. The same net is GPIO or PWM or UART-TX depending on
SoC pinmux (S6's `/* pins conflict with uart2 */` is exactly this collision).
So: a net connects **endpoints**; each endpoint has a *function* (what it does:
drive, listen, convert) and a *role* on the net (driver / listener / bidir —
R23). Pin-mux is then endpoint-function selection, and claim-checking runs on
nets × roles.

*Exercised (2026-07-21, "Slice A"):* a connector position is one net reachable
as several functions. The board declares per-function nexuses (gpio-map,
`socket,pwm-map`, `socket,adc-map`); a shield device picks the function by
property (`gpios` / `pwms` / `io-channels`); the expander resolves the position
through the matching nexus. A PWM/ADC claim registers on **two** nets — the
pin (exclusive: can't also be GPIO) and the channel (exclusive: one consumer
per timer/adc channel) — so cross-function pin clashes and channel contention
both fall out of net identity. Pinmux itself stays SoC-specific: the board
provides the pinctrl fragments; the rig model only *selects/names* them (the
"how a resource is provided" half of R21; full pinctrl application deferred).

### Pad (and Refinement 2 — pads are 1-net connectors)
A named, physically accessible endpoint: header pin, test point, solder pad
(S7's "SQ"). Unification: a pad is a **connector of arity 1**. This makes S7(b)
(pad-to-pad jumper wire) ordinary: a jumper wire is an ad-hoc net mating two
1-net connectors. No special "port" machinery at the physical level — R25's
ports are the *interface view* of pads.

### Link / Bus (signal groups)
**Refinement 3 — addressing mode is orthogonal to net count.** The sketch ties
"single net = single-ended, multi-net = bus." The evidence for two independent
axes:

| | no addressing | in-band addressing | out-of-band addressing |
|---|---|---|---|
| **single net** | GPIO, PWM, ADC line, IRQ | 1-Wire | — |
| **multi net** | UART (RX+TX), SWD | I2C (SDA+SCL), CAN | SPI (SCK+MISO+MOSI **+ CS pool**) |

- *No addressing* → the link is point-to-point: attaching means claiming it
  exclusively (**dedicated** regime, R15).
- *In-band* → targets carry their own address: attaching means arbitrating the
  address space (**shared-bus** regime; realizability = address-set feasibility,
  R9; strap-selectable addresses are domains, R17).
- *Out-of-band* → addressing is topology: each target needs an extra dedicated
  net (CS) plus a computed index (**shared-pool** regime; composition =
  allocation, R4/R16; SPI `reg` = CS array index is the canonical case).

The three sharing regimes of R15 are therefore not axioms — they *derive* from
the addressing taxonomy. (Single-ended is assumed throughout; differential
pairs (CAN, USB) are an acknowledged extension, not modeled yet.)

### Connector
A typed grouping of positions, each position bound to one net. A connector
**type** (arduino-r3, mikrobus, grove, "pad") fixes positions and their
intended link structure (mikroBUS position 2 = CS of the SPI link); a connector
**instance** on a PCBA binds positions to that PCBA's actual nets. Exposure in
arbitrary multiplicity (Quail ×4, Maker Pi ×7). PCBAs **expose** (socket) or
**consume** (plug) connector instances; attachment = mating one exposed with
one consumed instance of the same type.

**Trial addendum (frontend-trial, 2026-07-17):** connector types carry a
**mating multiplicity**: stackable types (Arduino R3 — stacking headers are
pass-through by construction) accept N consumers per exposed instance; others
(mikroBUS) exactly one. Pool positions are an *ordered candidate list*
(Arduino CS: D10, D9, D8…), with socket-dedicated (1-element) and
copper-fixed (pinned) as special cases.

**Refinement 4 — subset exposure is normal and must be typed.** Boards expose
*partial* connector types (nucleo_f401re: Arduino R3 without `arduino_serial` —
verified hard error in S6). A connector type therefore needs optional position
groups, and the mating check (R20) matches the consumer's *used subset* against
the exposer's *offered subset*. Pretending types are all-or-nothing reproduces
today's à-la-carte label chaos.

### Device
Silicon (or an opaque smart module) on a PCBA: endpoint of nets, target of
addressing, origin of a DT node. Devices declare capability domains (fixed
address 0x68; strap-selectable {0x48↔open, 0x49↔closed}) — the inputs to
realizability (R9).

### Configuration element
Jumpers, solder bridges, DIP switches, strap pins: physical state that selects
among net topologies or address domains. First-class because expansion must
*choose* their state (S5) and emit it (config sheet, R17). A jumper is a
switchable net segment; a strap is a device-address selector.

### PCBA: Board and Shield
A PCBA = {devices, nets, connector instances, configuration elements}.

**Refinement 5 — the board/shield split is build-visibility, not MCU-presence.**
The sketch says shields have "no MCU running SW" — but the WINC1500 (S2) has an
MCU running its own firmware. What matters to the rig model: a **board** is a
PCBA whose MCU runs *the firmware image this build produces* (the root of the
DT projection); a **shield** is a PCBA whose intelligence, if any, sits behind
a link protocol and is opaque to the build. Multi-image boards (nRF5340
app+net) and multi-board rigs then generalize naturally: one projection per
firmware image (deferred, requirements.md open question 6).

### Interposers: pass-through vs scope creation
Shields chain (consume one connector, expose others, any arity — S6, S8). Two
electrically distinct behaviors:

- **Pass-through** (S6 adapter): exposed positions bind to *the same nets* as
  consumed positions (possibly regrouped/renamed). Net identity is preserved;
  claims propagate through.
- **Scope creation** (S8 mux, bridges like SPI→I2C): the exposed link's nets
  are *new copper*, electrically distinct from the parent, rooted in a device
  on the interposer. R26's scopes are not an abstraction trick — they are
  literally different nets, which is why the same fixed address is legal per
  channel.

### Rig
The top-level assembly: board(s) + shield instances + connector matings +
ad-hoc nets (jumper wires between pads) + configuration-element states +
instantiation parameters. The single source of truth (R3).

**Invariant (2026-07-17):** a rig contains **at least one board** — the MCU the
projection applies to — making it self-contained as a build target; a shield,
by contrast, never exists without a board. This asymmetry makes the rig a
*third build-system entity* peer to boards and shields
(`west build --rig <name>`, no `-b`; see conventions.md).

## 2. Relations

Diagram: `diagrams/ontology.dot` / `.svg` (also first section of the atlas
artifact).

The nouns connect through five declared relation families plus a derived
family. Everything analyzable (sharing, conflicts, scopes) is *computed* from
declared relations — never separately declared, so it cannot drift out of sync
with the copper.

### Composition (catalog / type level)

| Relation | Signature | Notes |
|---|---|---|
| defines | ConnectorType → Position* | position = role + optionality group (Ref. 4) + width (A1) |
| contains | PCBA → {Device, Net, Pad, ConfigElement}* | a PCBA is its parts list |
| exposes / consumes | PCBA → Connector* | socket vs plug; each Connector is instance-of one ConnectorType |
| binds | Connector: Position ↦ Net | per position, onto the PCBA's nets; gpio-map generalized; a Pad is the arity-1 case |

### Electrical

| Relation | Signature | Notes |
|---|---|---|
| has | Device → Endpoint* | |
| attaches | Endpoint → Net | carries Function (GPIO/PWM/ADC…) and Role (driver/listener/bidir, R23) |
| groups | Link → Net* | width parameter; members may be atomic NetGroups (pairs/lanes, A1) |
| carries | Link → AddressSpace | mode per A2: none / device-static / device-dynamic / message |
| roots | Device → Link* | scope creation (mux, bridge): the link's nets are new copper (R26) |
| sits-in | Device → Link | in-path device (PHY/transceiver, A3): claims pass through, projection sees it |
| constrains / agrees-on | Link → BusConstraint*, Parameter* | termination counts (A4); bus-wide parameters like bitrate (A5) |

### Configuration

| Relation | Signature | Notes |
|---|---|---|
| switches | ConfigElement → Net segment | jumper = switchable copper |
| selects | ConfigElement → address ∈ Device.AddressDomain | strap (R9/R17) |
| enables | ConfigElement → BusConstraint element | e.g. termination jumper (A4) |

### Assembly (rig level)

| Relation | Signature | Notes |
|---|---|---|
| instantiates | Rig → Instance (of PCBA) | with parameter valuation: free / pinned / allocated (R6, R18) |
| mates | Rig: exposed Connector × consumed Connector | same ConnectorType; subset (R20) and width (A1) checks |
| merges | Mating: Net ↔ Net | position-wise identification of nets across the mating |
| wires | Rig: Pad × Pad → AdHocNet | jumper wires (S7); ordinary nets thereafter |
| claims | Instance → Net (via Endpoint, with Role) · address ∈ AddressSpace · slot ∈ Pool | the unit all checking runs on (R5) |

### Derived (computed, never declared)

- **Net identity**: the equivalence closure of `binds` ∘ `merges` over all
  matings and pass-through interposers. All sharing and conflict analysis runs
  on equivalence classes, which is what makes Grove 5/6-style sharing (R13)
  fall out for free.
- **Scope tree**: board-rooted links plus device-`roots`-Link edges form a
  forest; address-uniqueness and pool-exhaustion checks run per scope node
  (R26).
- **share / net / conflict**: ≥2 claims on one net-class or space → shared;
  1 driver + N listeners → net (legal, R22); 2 drivers, or 2 fixed identical
  addresses in one scope → conflict (R5/R9).
- **Allocation**: only device-static AddressSpaces and out-of-band Pools engage
  the allocator (A2); message and dynamic modes engage consistency checks (A5)
  and expectations (A6) instead.
- **projects-to**: Rig → per firmware image: {DTS, Config Sheet, Expectations}
  — see §3.

## 3. The projection principle

The devicetree is not the rig — it is the **projection of the rig onto one
MCU's point of view**: what that MCU can reach, through which endpoints, over
which nets, behind which scopes, at which addresses. Expansion = computing this
projection. Two corollaries:

- Everything MCU-reachable lands in the DT in *standard* constructs (S8 showed
  the targets exist: mux channels, phandles, cs-gpios).
- Everything the MCU *cannot* see but a human must realize — jumper positions,
  strap settings, which module plugs into which socket — is the complement of
  the projection: exactly the **physical configuration sheet** (R17). The two
  expansion outputs are the two halves of rig state, split by MCU visibility.

(Runtime-discoverable devices add a third projection output — test
expectations, A6. Software build configuration is a *separate* axis, not part
of the MCU projection: it is the expander's fourth output, a Kconfig
activation manifest — see `architecture.md` / conventions.md Conv. 7.)

## 4. Ontology → concepts → evidence

| Ontology element | Concept (requirements.md) | Grounding evidence |
|---|---|---|
| PCBA types, instantiation params, config elements | C1 assemblies & instantiation | S3 collapse; S5 straps |
| Connector types, positions, subset matching, pads | C2 interface contracts | S4-a/b, S6 label failures |
| Nets, endpoints/roles, addressing taxonomy, scopes | C3 resource model | S2 D7, Quail matrix, grove 5/6, S8 |
| Addressing modes → arbitrate/allocate/claim | C4 allocation & realizability | S2 CS, S3 0x68, S5 |
| Ad-hoc nets between pads, endpoint roles | C5 nets & references | S7 both routings |
| Projection principle | C6 expansion contract | S1 fidelity; S5/S8 config sheet |

## 5. Stress test: CAN, Ethernet, USB, MIPI CSI/DSI (2026-07-17)

Challenge round against four bus families outside the S1–S8 evidence. Verdict:
the two axes survive, but each family forces an amendment (A1–A6 below).

### CAN
Two-wire **differential** pair, multi-drop. In-band addressing — but IDs name
*messages*, not nodes: attaching N nodes allocates **nothing**. What expansion
must instead check/emit: **exactly-two termination** on the bus (typically
jumper-selectable per shield → realizability constraint + config-sheet entry)
and **bus-wide parameter agreement** (bitrate — a property all attached
endpoints must share). Entry paths: native controller + **transceiver** (a
device *in* the signal path transforming levels, not addressing — e.g.
Zephyr's `can-transceiver` phandle), or SPI→CAN bridge (MCP251xfd, in-tree
`canis_canpico` shield) — ordinary scope creation.

### Ethernet
Decomposes entirely into existing taxonomy cells: RGMII/RMII between MAC and
PHY = multi × none (dedicated point-to-point); **MDIO** = multi × in-band with
strap-selected PHY addresses — behaves exactly like I2C (arbitrate, straps →
config sheet). MAC addresses are protocol-level, allocated by nobody at
expansion. Above L2 (switches, IP) the rig model deliberately ends: network
topology is not copper-attachment. SPI→ETH bridges (ENC28J60/424J600 — our S6
click!) are scope creation, already covered.

### USB
Differential point-to-point with hubs as protocol-level fan-out. Addressing is
in-band but **assigned at runtime by enumeration** — a binding *time* the
ontology lacked. Consequence: attached USB devices may need **no DT node at
all** (the controller is the projection's edge); the rig still records them
physically — what they contribute to outputs is not DT but an *expectation*
("VID:PID X must enumerate on port 2"), pointing at a third output artifact
class beyond DTS + config sheet: **test expectations**.

### MIPI CSI-2 / DSI
Differential **lanes** (1 clock + N data), point-to-point, no in-band
addressing; control runs over a separate I2C sidechannel (CCI). A camera
connector (RPi FFC) is therefore the strongest connector-as-bundle specimen
yet: CSI lanes + I2C + GPIOs (reset/powerdown) + power in one mating — R14
validated from a foreign domain. New constraint: **lane-width matching**
(1/2/4-lane endpoints) — numeric capacity matching in the mating check,
sibling of R20's subset matching. DT precedent, and a strong one: mainline
of-graph bindings (`port`/`endpoint`/`remote-endpoint`) already express
cross-device point-to-point links for exactly these pipelines — existing DT
practice for what Concept 5 calls nets.

### Amendments

- **A1 — grouped nets.** Differential pairs and lanes: nets may form atomic
  groups (a pair/lane attaches as a unit). Net-count axis gains a width
  parameter; width can be negotiable (CSI lanes) → mating checks include
  capacity (extends R20).
- **A2 — addressing axis refined.** "In-band" splits by *target* and *binding
  time*: device-addressed/static (I2C, MDIO — arbitrate at expansion, straps),
  message-addressed (CAN — nothing to allocate), device-addressed/dynamic
  (USB — runtime enumeration, nothing to allocate, projection ends at the
  controller). Only static device addressing and out-of-band pools engage the
  allocator (C4); the other modes engage checks and expectations instead.
- **A3 — in-path devices (PHYs/transceivers).** A device class that sits *in*
  a link transforming electrical representation, not addressing (CAN
  transceiver, Ethernet PHY). Pass-through at the net-identity level for
  claims, but projection-visible (DT phandles). Distinct from scope-creating
  bridges.
- **A4 — bus-level physical constraints.** Realizability inputs attached to a
  link as a whole, not to endpoints: termination count (CAN: exactly 2),
  eventually stub length/capacitance. Often jumper-backed → config sheet.
- **A5 — bus-wide parameter agreement.** Some link parameters must be equal
  across all endpoints (CAN bitrate); expansion validates consistency and can
  propagate a rig-level parameter to all instances.
- **A6 — third output artifact: test expectations.** Runtime-enumerated or
  protocol-discovered devices (USB; network peers) don't project into DT but
  do project into verifiable expectations. Output triple: **DTS + physical
  configuration sheet + expectations**. (Extends the projection principle:
  MCU-visible-static → DT; human-realized → config sheet;
  runtime-discoverable → expectations.)

## 6. Deliberately out of scope (for now)

Power and ground nets (voltage domains, current budgets — realizability inputs
eventually; entities exist in the model as nets, checks deferred). Protocol-
level topology (Ethernet switching, USB device trees beyond the controller,
IP). Mechanical constraints (stacking height, footprint). Multi-board rigs
(one projection per firmware image — deferred with open question 6).

## 7. The board→rig lift (2026-07-24)

A board is a trivial rig: `board b  ↦  rig{board: b, instances: []}` — the
natural lift, `a → [a]`. The rig is not a fourth kind of thing bolted next
to boards; it is the general form of the build coordinate, of which a bare
board is the degenerate case. Several already-ratified choices are this
principle surfacing before it was named:

- **Grammar identity** (deliberate, rig-variants-revisions.md): rig targets
  are `name@rev/variant`, hwmv2-exact — `board@rev/qualifiers` lifted.
  Revisions mirror revisions; variants mirror qualifiers (parallel
  alternatives under one name).
- **Resolver identity**: list_rigs.py holds the same role for rig targets
  that list_boards.py holds for board targets — cmake passes the full
  target string and consumes structured facts, never parsing content.

Laws that keep the lift honest (testable, not decorative):

- **Identity build**: expanding the trivial rig is the identity — no
  overlay, no conf, byte-equal zephyr.dts to the plain board build
  (saferail 11 restated as algebra).
- **Commutation**: qualifying then lifting ≡ lifting then qualifying — the
  shared grammar guarantees the coordinate algebra doesn't fork.

What it predicts / decides:

- **BOARD is derived data of the build coordinate** — the cmake-alone entry
  slice (slot-10 rig→board inference) is this law mechanized; for a trivial
  rig the projection is trivially the board itself.
- **Twister platforms**: "teach twister that a platform can be a rig"
  dissolves into "platforms ARE rigs; boards are trivial rigs" — no fourth
  entity to teach, the coordinate twister already holds is the degenerate
  case (parked upstream item, reframed).
- **Symmetry-table heuristic** (review rule, BIDIRECTIONAL): every mechanism
  added on the rig side must map to its board-side counterpart or state why
  not, AND every board-side mechanism must map to a rig-side counterpart or
  be classified as artifact-level. The one-directional form of this rule let
  board→rig gaps accumulate unnoticed until they were looked for
  deliberately; the classification below is what the second direction
  produces, and the limit-of-the-claim paragraph is the instrument that
  decides each cell.

The table, as it stands (2026-07-26). The FIRST entry came from the rig side
pointing back at boards, which is what the second direction of the rule is
for — and it found a conflation, not a missing feature:

| board-side mechanism | rig-side | verdict |
|---|---|---|
| **metadata file (`board.yml`, TYPE-named, zero hardware description) SEPARATE from content file (`<board>_<soc>_<rev>.dts`, INSTANCE-named)** | `rig.yml` was BOTH | **RATIFIED SPLIT** (2026-07-26h): `rig.yml` metadata, `<rigname>.yml` content. The fragments were already instance-named with no same-stem base to be deltas of. Note the two generators are offset by one configure stage: `<rigname>.yml` and `<board>.dts` are both SOURCES, `zephyr.dts` is the common output, and `rig-gen.overlay` is the intermediate that joins the board's own input stream |
| `revision:` (format-typed, `exact:`) | `revisions:` → becoming upstream-exact | owed, in flight |
| `variants:` under `socs:`, recursive | flat `variants:` axis | owed, delivered differently: a rig has no qualifier tree because `board:` already carries a fully-qualified target |
| `extend:` from another folder/module | none | **owed, DEFERRED** — adds new SELECTABLE COORDINATES, so it is coordinate-level; prerequisite is root-precedence policy, not effort |
| `boards:` (many declarations per file) | none | **not owed** — artifact-level: each declared board is still its own coordinate. Variants + fragments carry what upstream needs multiplicity for |
| `runners:` | none | not yet classified; a rig owns the physical board, so this is a real future cell |
| N shields per folder (plural `shields:`) | exactly one `<dir>/<basename>.shield` | artifact-level, and **to be ADOPTED** — the plural list declares the NAME SET and the filename is constructed from the name, which is Q6's own discipline. Cost is one function (`load_shield_library`); cmake already consumes `(name, dir)`. Needs an identity ruling: declared name wins over the DT node name |
| the legacy overlay-basename shield fallback | — | **not owed, and never** — it DERIVES identity by parsing a filename, the inverse of Q6. Bridle runs entirely in this mode; see `bridle-migration.md` |

Limit of the claim: the lift is real at the COORDINATE level, not the
artifact level. Boards are static DTS files; rigs are generated content;
the module chain (slots 10–20) rightly keeps consuming BOARD as a concrete
fact. Near-term reading: RIG, when present, is the primary coordinate and
BOARD is what it projects to. The radical reading — every build is a rig
build — is an upstream endgame question, deliberately left open (parked),
not a near-term design input.
