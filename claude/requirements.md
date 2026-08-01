# Rigs — Consolidated Requirements Model

Consolidation of R1–R27 from `rig-playbook.md` (S1–S8 sweep, 2026-07-17) into six
orthogonal concepts. Original R-numbers are kept as provenance; each appears in
exactly one primary home (cross-references where a requirement touches a second
concept). Companion: `design-log.md` (evidence), diagrams atlas.

The six concepts split naturally along a compiler shape:

| Layer | Concept | One-liner |
|---|---|---|
| language (nouns) | 1. Assemblies & instantiation | types for hardware assemblies; explicit, parameterized instances |
| language (nouns) | 2. Interface contracts | connectors, sockets, and ports as typed, checkable interfaces |
| semantics | 3. Resource model | everything consumable is a declared resource with regime and scope |
| semantics | 4. Allocation & realizability | the solver that assigns pools and proves the rig buildable |
| semantics | 5. Nets & instance references | rig-level wiring between instances, referencable before expansion |
| output contract | 6. Expansion contract | what the expander emits and the guarantees it makes |

---

## Concept 1 — Assemblies & instantiation

A module/assembly is a *type*; a rig contains explicit, countable, parameterized
*instances* of it. Closes the type/instance gap (claim C1) that today's shields
fake with instance-space patches.

- **R8** — instantiation is explicit and countable: N requested → N namespaced
  subtrees (labels, paths) or a hard error; never silent collapse. *(S3)*
- **R10** — tree-level singletons (`aliases`, `chosen`) get per-instance
  treatment and deterministic generated names. *(S3)*
- **R6** — physical variability (jumpers, solder bridges, strap options) is an
  instantiation parameter, not a forked overlay. *(S2; feeds Concept 4 via R17)*
- **R3** — the rig description makes explicit what shields leave implicit:
  which socket an instance occupies (→ Concept 2), which resources it consumes
  (→ Concept 3). The rig file is the single source of truth for assembly.
  *(S1)*

DT precedent: bindings/`compatible` already do type-vs-instance at the *device*
level; this lifts the same idea to assemblies.

## Concept 2 — Interface contracts

Attachment is a structural, type-checked match between what a module *requires*
and what a socket *offers* — never a textual label coincidence (closes C2, and
kills every S6 failure).

- **R11** — connectors declare machine-readably what they carry (bus endpoints,
  functions, pin roles); socket type is data, not comments. *(S4-a)*
- **R14** — a socket is one referenceable unit bundling heterogeneous resources;
  attachment resolves the module's abstract needs against the bundle. *(S4-b)*
- **R12** — module placement names a socket *instance* as an instantiation
  parameter ("module M in socket K"). *(S4-a/b)*
- **R20** — matching is an interface contract checked at expansion: module
  declares required connector type + used signal subset; socket declares
  offered type. *(S6: `arduino_serial`, `mikrobus_1_i2c` failures)*
- **R25** — module interfaces include *ports*: named signals with direction
  (offered outputs / accepted inputs), beyond consumed resources — even signals
  appearing in no connector (S7's SQ pad). *(S7; consumed by Concept 5)*
- **R19** — carriers re-export: an interposer/adapter declares its own sockets
  whose resources resolve through its parent connector, chainable to arbitrary
  depth. *(S6, S8)*

DT precedent: gpio-map nexus nodes are exactly this for pins — verified to
compose recursively (S6). The concept generalizes nexus to buses, CS, and roles.

## Concept 3 — Resource model

Everything an instance consumes is a declared resource claim against something a
board, socket, or interposer provides. Resources carry a **sharing regime** and
live in a **scope**.

- **R5** — all consumption modeled and checked: pins, addresses, CS slots;
  double-claim = expansion-time error, not runtime surprise. *(S2)*
- **R15** — every provided resource declares its regime, because regimes compose
  differently: **dedicated** (claimed exclusively — UART, INT pin),
  **shared-bus** (arbitrated by address — I2C), **shared-pool** (allocated —
  CS slots). *(S4-b)*
- **R13** — providers declare shared underlying wiring so cross-socket conflicts
  are detectable (Grove sockets 5/6 sharing gpio0 26). *(S4-a)*
- **R23** — claims carry signal role (driver / listener / bidirectional): one
  driver + N listeners on a pin is a net (→ Concept 5), two drivers a conflict.
  Without role, R5 false-positives on every legal shared signal. *(S7)*
- **R21** — cross-layer provision is explicit: *how* a resource is provided
  (native controller pin-mux vs GPIO from the socket) is a property of the
  attachment, checked end-to-end through the adapter chain and against SoC
  pinctrl claims. *(S6 CS coincidence chain)*
- **R26 (scoping half)** — interposers create new resource scopes rooted in
  their own device node; uniqueness and exhaustion are evaluated per scope
  along the chain, not globally. *(S8; allocation half → Concept 4)*

DT precedent: I2C mux child buses (`ti,tca9548a`) are scopes in-tree today.

## Concept 4 — Allocation & realizability

Composition is resource allocation, not merging (the sharpest lesson of the
sweep: a SPI child's `reg` must equal its `cs-gpios` index — no textual
mechanism can compose that).

- **R4/R16** — shared-pool allocation is bus-wide and atomic: parent array
  entries (drawn from each socket's provision) and child `reg` written together
  across all modules on the bus, whatever socket or nesting level contributed
  them. *(S2, S5)*
- **R9** — realizability: modules declare capability domains (fixed vs
  selectable address, and by what physical means); the expander proves the
  topology buildable or rejects it with a physical-level explanation (two fixed
  0x68 on one bus: impossible; behind a mux: fine). *(S3, S8)*
- **R17 (domain half)** — selectable addresses are {value ↔ strap
  configuration} domains the allocator chooses from. *(S5; output half →
  Concept 6)*
- **R27** — interposer channel↔module assignment is an allocation domain like
  any other. *(S8)*
- **R18** — allocation is deterministic, order-independent, and pinnable: same
  rig → same assignment; explicit pins respected; adding a module must not
  reshuffle existing assignments. *(S5; cross-ref R7 in Concept 6)*

## Concept 5 — Nets & instance references

Rig-level wiring between instances — the object today's DT never stores (it
stores endpoints' opinions about pins, never the wire).

- **R22** — nets are first-class: output port of instance A → input port(s) of
  instance B, routed via connector pins or pad-to-pad (existing in no
  connector); expansion emits standard DT (shared pin refs or direct phandles)
  and validates topology (exactly one driver, ≥1 listener). *(S7)*
- **R24** — instance-qualified references ("instance X's port P") resolved at
  expansion into generated phandles. Raw DTS labels are structurally incapable
  (the target node doesn't exist until expansion) — the front-end's hardest
  design point, whatever the syntax. *(S7; also needed by R12 placement and
  R18 pinning)*

DT precedent: the *output* side is ordinary DT phandle practice
(`io-channels`, `trigger-sources`); only rig-level authoring is new.

## Concept 6 — Expansion contract

The expander is a compiler; this is its ABI.

**Compatibility scope (decided 2026-07-17, pushback round):** the rig model is
**not required to work with existing `board.dts`/shield overlay files.**
Hardware participates in rigs by opting in: boards provide socket fragments
(plus per-socket nexus nodes in their normal DT — themselves plain,
upstreamable, rig-agnostic); shields are (re)written as templates. There is no
shim that ingests legacy shield overlays. The one hard guarantee for
unconverted hardware: **the legacy path never breaks** — `west build -b
<board> --shield <shield>` (S1) behaves exactly as today; rigs are purely
additive.

- **R1** — expressiveness floor: everything S1 does today (nexus routing, bus
  children, connector-relative pins) must be expressible *in the rig model's
  own terms* (rig-enabled board + template) without loss.
- **R2** — fidelity, restated per the compatibility scope: for a rig that
  mirrors an S1-style setup using *converted* hardware descriptions, the
  projected overlay is equivalent to the legacy overlay output. This is a
  regression/validation tool (`build-rig/upstream/` vs `build-rig/proposal/`),
  not an interop promise for unconverted files.
- **R7** — meaning is order-independent: module declaration order never changes
  the result; ambiguity is rejected, not resolved silently. *(S2 last-wins)*
- **R17 (output half)** — expansion emits two artifacts: the plain DTS **and
  the physical configuration sheet** (strap settings, jumper positions, mux
  channel assignments — everything a human must do to the copper). *(S5, S8)*
- Implicit throughout: targets are *standard* devicetree constructs only (S8
  showed the target structures exist in-tree); diagnostics speak at the
  physical level ("two devices fixed at 0x68 on one bus"), not merge mechanics.

---

## Coverage check (scenario × concept)

| | C1 Assemblies | C2 Interfaces | C3 Resources | C4 Allocation | C5 Nets | C6 Contract |
|---|---|---|---|---|---|---|
| S1 | R3 | — | — | — | — | R1 R2 |
| S2 | R6 | — | R5 | R4 | — | R7 |
| S3 | R8 R10 | — | — | R9 | — | — |
| S4-a | — | R11 R12 | R13 | — | — | — |
| S4-b | — | R14 | R15 | — | — | — |
| S5 | — | — | — | R16 R17 R18 | — | R17 |
| S6 | — | R19 R20 | R21 | — | — | — |
| S7 | — | R25 | R23 | — | R22 R24 | — |
| S8 | — | — | R26 | R27 | — | — |

All 27 requirements placed; every scenario contributes to ≥1 concept; every
concept is motivated by ≥2 scenarios (C5 by one scenario but two independent
sub-cases). No requirement was dropped in consolidation.

## Open questions (not covered by S1–S8)

1. **Kconfig.** Shields carry Kconfig fragments too; the sweep only examined
   devicetree. What does multi-instantiation mean for config symbols
   (per-instance config? counts? nothing)? Needs its own scenario pass.
2. **Front-end syntax.** All concepts are syntax-neutral; per the 2026-07-17
   decision, first expression is valid-DTS conventions. R24 (instance
   references) is the acid test any syntax must pass.
3. **Aliases/chosen policy** (R10): deterministic naming scheme needs concrete
   rules — propose during implementation of Concept 1.
4. **Runtime identity.** Do instances need runtime-discoverable identity
   (device names, sensor labels) beyond DT node names? Touches Zephyr driver
   model, not just DT.
5. **Validation ecosystem.** Who authors connector-type definitions (grove,
   mikrobus, arduino-r3) — one shared registry analogous to `dts/bindings`?
6. **Multi-board rigs and off-DT components** (deferred playbook candidates):
   inter-board links, USB/network peers. Partially advanced by the ontology
   stress test (ontology.md §4): runtime-enumerated devices project into a
   third output artifact — **test expectations** — rather than DT (amendment
   A6); expansion outputs are a triple (DTS, config sheet, expectations).
7. **Non-allocating link families** (from ontology stress test): bus-wide
   parameter agreement (CAN bitrate), bus-level physical constraints (CAN
   termination), lane-width matching (MIPI), in-path devices (PHYs). None
   break the six concepts; A1–A6 refine C2–C4/C6. A dedicated scenario pass
   (CAN rig with termination jumpers would be the richest) is future work.
