# Zephyr Rigs — Design Log

Running log of design discussions, verified claims, and upstream comparisons for the
"rigs" hardware-model extension (multi-instantiation of hardware assemblies in
Zephyr devicetree). Companion documents:

- `gemini-code-1784292710667.md` — original transpiler spec (extended pipeline,
  `/dts-v1-zephyr-ext/` dialect)
- `rig-playbook.md` — rig topology scenarios of increasing complexity

---

## 2026-07-17 — Challenging the core idea; premise verification

### Session context

Resumed work after long pause. Prior state: transpiler spec on paper, `zephyr-rigs`
git worktree (of `/wrk/z/ws-up/zephyr`) clean at `origin/main`, exploration work in
three stashes (dts.cmake tracing, kconfig debug, GitBuildSnapshot.cmake).

### Upstream comparison: RFC #82889 / PR #82825

The closest upstream effort is the "shield options" RFC:

- [RFC #82889](https://github.com/zephyrproject-rtos/zephyr/issues/82889) —
  `<shield_name>[@<index>][:<option>{=<value>}]` syntax, CPP-parameterized
  overlays, build-generated "derived overlays" per instance. Opened 2024-12-12,
  still in "Architecture Review", no movement.
- [PR #82825](https://github.com/zephyrproject-rtos/zephyr/pull/82825) — the
  implementation. Opened 2024-12-10, repeated stale cycles, **closed unmerged
  2026-02-27** with no substantive maintainer review.

**Verdict: strictly less powerful than the rigs concept, and effectively dead.**
Capability gaps of the RFC mechanism:

| Capability | RFC #82889 |
|---|---|
| Rig described in a versioned artifact | no — topology lives in the `west build` command line |
| Label namespacing per instance | manual (author must token-paste `SHIELD_DERIVED_NAME` into every label) |
| Phandle rewiring to per-instance nodes | no |
| Cross-instance references (module A wired to module B) | no |
| Nested composition (template uses template) | no |
| Computed per-instance values (CS index, address allocation) | no |
| Connector realization | only via pre-existing board nexus labels |

Relevant precedent: the RFC's CLI UX (`shield@index:opt=val`) is worth staying
compatible with. Its death after ~2 years also signals low upstream maintainer
engagement with this problem space.

### Design decision (superseding the original spec's front end)

The expensive part of the original spec is the **new grammar**
(`/dts-v1-zephyr-ext/`): parser fork, no editor/dtc tooling on sources, bespoke
error reporting, near-zero upstreamability. The actual hard problem — label
namespacing, phandle rewiring, resource allocation — is a **tree transform**, not
a language transform.

Decision:

1. Build the **tree-transform engine first**: a dtlib pass over *syntactically
   valid DTS* using conventions (templates under a reserved node, instances as
   nodes with `rig,template = "..."`-style properties). dtlib parses it
   unmodified; the pass expands templates, prefixes labels, rewires phandles,
   allocates resources, emits plain DTS.
2. Hook via `EXTRA_DTC_OVERLAY_FILE` / snippet / `pre_dt` hooks from a module —
   **no Zephyr core patches** (obsoletes the dts.cmake insertion-point stashes).
3. Defer any nicer front-end syntax until 2–3 real rig descriptions have been
   written in the convention syntax. If the conventions are tolerable, the whole
   dialect front end is unnecessary; if not, it becomes thin sugar over the same
   engine.

Known ergonomic cost of valid-DTS conventions: references to per-instance nodes
("instance 2's UART") cannot be real `&label` references in the source (the node
doesn't exist pre-expansion), so they become string/property conventions — losing
source-level phandle checking.

### Premise verification (evidence for upstream argumentation)

Three claims underpinning the rigs concept, checked against the Zephyr tree
(`zephyr-rigs` worktree at origin/main, 2026-07-17).

#### Claim 1 — DT conflates type and instance; shields are forced singletons. HOLDS (sharpened)

DT has a type/instance split at the *device* level only: binding (`compatible` +
YAML) = type, node = instance, drivers instantiate per node
(`DT_INST_FOREACH_STATUS_OKAY`). There is **no type concept for assemblies** of
nodes. A shield overlay is a reusable description forced into instance-space:
concrete paths, globally-unique labels, concrete connector labels. Overlay
application is merge-by-path, so applying a shield twice merges into the *same*
nodes instead of creating a second instance. Singleton-ness is an artifact of the
reuse unit being a textual patch on the global instance tree.

**In-tree evidence — manual namespacing:** shield authors hand-suffix every label
and node name with the shield name, e.g. in
`boards/shields/adafruit_data_logger/adafruit_data_logger.overlay`:
`rtc0_adafruit_data_logger`, `sdhc0_adafruit_data_logger`,
`green_led_adafruit_data_logger`, `led_1__adafruit_data_logger` (double
underscore typo included). Humans are manually performing the namespacing a
type/instance mechanism would provide — and it still only supports one instance.

#### Claim 2 — Connectors have no proper DT representation; convention only. HOLDS (with a caveat that supports the design)

Caveat: **GPIO routing through connectors is first-class** via nexus nodes, e.g.
`boards/st/nucleo_f401re/arduino_r3_connector.dtsi`:

```dts
arduino_header: connector {
    compatible = "arduino-header-r3";
    #gpio-cells = <2>;
    gpio-map-mask = <0xffffffff 0xffffffc0>;
    gpio-map = <ARDUINO_HEADER_R3_A0 0 &gpioa 0 0>, ...;
};
```

Shields target `&arduino_header ARDUINO_HEADER_R3_D10` abstractly; the board maps
to SoC GPIOs. This composes correctly and is machine-checked.

But beyond GPIO, nothing: `arduino_i2c`, `arduino_spi`, `mikrobus_i2c` are **pure
label conventions** aliasing SoC bus nodes. No declaration of what a connector
carries, no validation that a shield's requirements match the connector, no
connector identity/occupancy ("socket 2 of 4") — which is why boards with
multiple same-type connectors invent ad-hoc numbered labels (`grove_i2c0`, …).
Linux never solved this either (BeagleBone cape/overlay-manager history).

The nexus caveat is *supporting* evidence: DT can represent connector semantics
when machinery exists. "Connectors as nodes" = generalizing gpio-map from pins to
buses and slots.

**Additional in-tree evidence (2026-07-17, playbook S4-a/S4-b):**

- `boards/mikroe/quail/mikroe_quail.dts:335-365` — a 4-socket mikroBUS board
  hand-encodes the socket × resource product as a 16-label matrix
  (`mikrobus_<N>_{adc,i2c,spi,uart}`), with per-socket nexus nodes and
  unnumbered default aliases on top. A connector *type* emulated by manual
  enumeration.
- Convention fragmentation: `boards/shields/mikroe_temp_hum_click` (© 2026)
  targets numbered `&mikrobus_1_i2c`; the ecosystem convention elsewhere is
  unnumbered `&mikrobus_i2c` (`boards/shields/arduino_uno_click`). Two live
  conventions for the same concept.
- `boards/cytron/maker_pi_rp2040/grove_connectors.dtsi` — seven `grove-header`
  nexus nodes whose socket *type* (I2C/UART/analog) exists only in comments; the
  board defines no grove bus labels, and **zero Grove module shields exist
  in-tree** — a 7-socket connector standard with an empty attachment ecosystem.
  Sockets 5/6 physically share `gpio0 26`, unmodeled.
- `boards/shields/arduino_uno_click` — an Arduino→mikroBUS adapter expressed as
  nexus remapping + label aliasing; works only because it hard-picks socket 1 as
  `mikrobus_header` (S8 material).

**S6 verified failures and the CS coincidence chain (2026-07-17, playbook S6):**

- Adapter on nucleo_f401re: hard error `undefined node label 'arduino_serial'` —
  the Arduino label convention is à la carte per board, undeclared either way.
- Adapter + `mikroe_temp_hum_click` on frdm_k64f: hard error `undefined node
  label 'mikrobus_1_i2c'` — numbered vs unnumbered mikroBUS label drift makes
  two same-ecosystem in-tree shields mutually incompatible.
- Working case (frdm_k64f + adapter + `mikroe_eth_click`) has **no `cs-gpios`**
  on the merged spi0: it works only because the click's implicit "CS 0 exists"
  assumption, FRDM-K64F's `SPI0_PCS0_PTD0` native-CS pin mux, and the adapter's
  copper routing of D10→socket-1-CS agree by coincidence — three layers, checked
  nowhere. In-tree CS conventions now count three: shield writes array wholesale
  (S2), per-socket nexus routing (Quail), and none-at-all (ETH Click).
- Positive finding: the click's `int-gpios` resolves through a two-level nexus
  chain (mikrobus_header → arduino_header → SoC GPIO) — gpio-map composes
  recursively and is the proven pattern R14 bundles should generalize.

#### Claim 3 — Composition breaks on parent-owned arrays (`cs-gpios`). HOLDS STRONGLY

DTS merge replaces property values wholesale; `/delete-property/` and
`/delete-node/` exist, **no append operator**. Child nodes compose (two I2C
children at different `reg` merge fine); parent-owned arrays indexed by children
do not.

**In-tree evidence — four Arduino SPI shields each write the whole array on
`&arduino_spi`, three of them claiming D10 with `reg = <0>`:**

- `boards/shields/adafruit_data_logger/adafruit_data_logger.overlay:39` — `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D10 GPIO_ACTIVE_LOW>`
- `boards/shields/adafruit_winc1500/adafruit_winc1500.overlay:11` — `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D10 0>`
- `boards/shields/link_board_eth/link_board_eth.overlay:11` — `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D10 GPIO_ACTIVE_LOW>`
- `boards/shields/buydisplay_2_8_tft_touch_arduino/buydisplay_2_8_tft_touch_arduino.overlay:45` — `cs-gpios = <&arduino_header ARDUINO_HEADER_R3_D9 GPIO_ACTIVE_LOW>`

Combining any two: last `cs-gpios` silently wins, and children collide on
`reg = <0>`. Long-documented as
[issue #52948](https://github.com/zephyrproject-rtos/zephyr/issues/52948).

**Sharpening:** this is deeper than a missing `+=` operator. A SPI child's `reg`
must equal its index in the parent's `cs-gpios` array, so composition is
**resource allocation** (assign CS indices globally, rewrite child `reg`), not
concatenation. No textual mechanism (CPP, append operator) can do it; it requires
a pass with whole-tree knowledge. Strongest single argument for the
tree-transform engine.

### Baseline builds (methodology + verified diagnostics)

Each playbook scenario gets a `--cmake-only` baseline build under
`build-rig/upstream/S<n>` (workspace-relative), to be compared later against
`build-rig/proposal/S<n>`. Full configure logs live next to the build dirs
(`S<n>-configure.log`).

Build invocation (history: initial S1–S3 runs hit a Kconfig failure from module
version skew — workspace modules at zephyr v4.3.1 manifest vs `zephyr-rigs` at
main — worked around with a pinned `ZEPHYR_MODULES`; resolved 2026-07-17 by
Tobi running `west update`, after which the full module set configures cleanly
and all S1–S3 findings reproduce identically; the pin is gone):

```sh
ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs west build -b <board> \
  -d build-rig/upstream/S<n> zephyr-rigs/samples/hello_world --cmake-only -- \
  "-DSHIELD=..."
```

Verified diagnostics (2026-07-17):

- **S1** (one shield): configures clean, zero DT warnings.
- **S2** (two different SPI shields): exit 0, exactly one warning —
  `unique_unit_address_if_enabled` on `sdhc@0` vs `winc1500@0`. The `cs-gpios`
  clobber (flags silently changed from `GPIO_ACTIVE_LOW` to `0`) and the D7
  double-booking produce **no diagnostic**. Upstream claim wording: "one
  ignorable warning, then a successfully generated broken configuration."
- **S3** (same shield twice): exit 0, **zero diagnostics**, output byte-identical
  to S1 — the second instance silently collapses into the first.

### Decision 2026-07-17 (late session): rig = third build-system entity; front end split into two candidates

- A **rig is a build-system entity peer to boards and shields**, with the
  defining asymmetry: shields never build without a board; a rig is
  **self-contained** (contains ≥1 board incl. the projection-target MCU).
  `west build --rig <name>` — no `-b`. Discovery via `rigs/` + `rig.yml`,
  mirroring `board.yml`/`shield.yml`.
- Front-end language is **explicitly undecided** between two carried
  candidates (conventions.md): #1 pure valid-DTS conventions (phandle pairs
  for R24, everything one language) vs #2 **YAML/DTS hybrid** (topology in
  `rig.yml`, DT-shaped payloads — connector types, template device subtrees —
  stay DTS; dotted-path references for R24). Tobi's symmetry argument favors
  #2: the topology level is metadata-shaped, and `rig.yml` completes the
  existing `board.yml`/`shield.yml` pattern. Verdict after writing S5 + S7 in
  both. Engine and object model are unaffected either way.

### Pushback round (2026-07-17, late): connector-type slimming + compatibility scope

- `rig-types` renamed **connector-types**. Connector types slimmed to the
  *logical* interface: named links (kind implies addressing mode) + claimable
  positions only; pure bus-member positions (SCK/MISO/MOSI, SDA/SCL, RX/TX)
  removed — no claim/allocation/output ever touches them. Dual-function
  copper (Arduino D11–D13) is discovered via net identity at the board
  binding, never declared in the type.
- `rig,binds-gpios` was a reinvented gpio-map → deleted. Board-side connector
  realization lives in the board's own DT as **real per-socket nexus nodes**
  (Quail already has them upstream); socket fragments reference nexus + bus
  labels; connector-type positions carry the nexus pin index (one source of
  truth with the dt-bindings header pattern).
- **Compatibility scope**: rigs do NOT consume existing board.dts/shield
  overlays. Opt-in via socket fragments + templates; no legacy-overlay shim.
  Sole guarantee for unconverted hardware: the legacy `-b`/`--shield` path
  (S1) never breaks. Rigs are purely additive — which is also the upstream
  pitch: zero risk to existing users.

### Pushback round, continued (2026-07-17): templates read as DT; entity-scoped naming

- **Bus membership by parentage, not property.** `rig,attach` deleted.
  Templates declare *bus proxy nodes* (`i2c { … }`, `spi { … }`) whose device
  children are ordinary DT (unit addresses, `reg`); proxy binds to the
  consumed connector type's link by name match (explicit link phandle only to
  disambiguate). Literal `&mb_i2c { }` extension was rejected: the type node
  is shared, so multiple included templates would merge their devices into it
  and dissolve template ownership. `reg` rule: authored = fixed/pinned claim;
  omitted = allocated (pools) or domain-resolved (straps). `rig,uses` becomes
  derived.
- **Entity-scoped property naming** (replaces blanket `rig,`): `shield,*` on
  templates (`shield,plugs` = consumed connector type; folder `templates/` →
  `shields/`), `socket,*` on board-fragment sockets (`socket,type`,
  `socket,nexus`, `socket,links`), `connector,*` inside connector types
  (`connector,function`, `connector,pool`, `connector,optional`), `rig,*`
  only for rig-level facts (`rig,template`, `rig,socket`, `rig,pin`, wires).
  Device-level rig-specific facts describe the shield's copper →
  `shield,cs-position`, strap domains, pad roles.

### Pushback round 2 (2026-07-18): types-as-bindings; address authority

- **Connector types are bindings + index header, not devicetrees** (Tobi's
  observation: the type dtsi had no structural connection to socket,i2c or
  shield proxies — a schema pretending to be an instance). socket,<type>.yaml
  gets edtlib validation of board sockets for free; plug,<type>.yaml declares
  the shield-side contract incl. proxy↔socket pairing; the dt-bindings header
  is the position-index single source (board gpio-map and shield references
  use the same constants). Upstream story: generalize the existing
  arduino-header-r3 binding+header pattern from pins to links.
- **Plug node**: shields type by string (`shield,plugs = "arduino-r3"`) and
  reference positions through their own local plug node
  (`<&dl_plug ARDUINO_HEADER_R3_D7 flags>`).
- **Address authority rule**: shield declares domains (copper knowledge,
  never migrates to rig files); rig file owns per-instance selection
  (`rig,pin`/`pin:`), free selections are allocated + emitted to the config
  sheet; expander is the sole author of `reg` and unit-address in output,
  always as a matching pair (source nodes of non-singleton domains and
  pool-addressed devices carry neither). Fixed-address duplicates on one
  scope remain a hard rejection (R9).
- conventions.md at v3; trial files reworked and re-verified (S5 rig source:
  37→25→17 nodes across rounds).

### Implications summary

- Claim 1 ⇒ need templates + instantiation step (types for assemblies).
- Claim 2 ⇒ need connectors as first-class nodes with declared capabilities
  (generalize the nexus pattern).
- Claim 3 ⇒ expander must be a tree transform with global knowledge (allocates
  CS indices, addresses, labels during merge).

## 2026-07-19 — Toolchain terms pinned down; S3 seeded-error piece; v1 cleanup

### Architecture vocabulary (new doc: architecture.md)

Tobi's observation: "loader", "expander", "object model" had leaked into
conventions/requirements as if defined — they weren't. Pinned down before the
prototype hard-codes them:

- **Rig model** (renamed from "object model" at Tobi's suggestion) — syntax-
  free semantic representation of the rig; schema = ontology.md §1–2;
  declared facts only ("derived, never declared" stays an analyzer concern).
  Zephyr analog: edtlib.EDT, one level up.
- **Loader** — one per front-end candidate; text → rig model; owns parsing,
  reference resolution, plug-binding schema validation, source locations.
  Knows no physics (loads S3 happily). Candidate-1's loader ≈ stock dtlib +
  schema pass; candidate-2's is new code — hence the verdict.
- **Expander** — rig model (+ board DT, Conv. 4) → projection; split into
  **analyzer** (closure, scope tree, checks, allocator; everything that can
  reject a rig; produces the *solved rig*) and **emitter** (pure rendering of
  the projection triple: overlay / config sheet / expectations; no error
  class of its own). Split into two stages per Tobi's pushback.
- **Integration thesis**: the seam with Zephyr is the overlay file (emitter
  output enters where --shield overlays do; downstream toolchain unchanged,
  re-validates output — the "two validation regimes" rule falls out). Error
  taxonomy follows the component split: loader errors = language, candidate-
  dependent (the open verdict); analyzer errors = physics, candidate-
  independent.
- Parked: where the expander runs (west vs CMake); discovery (rigs/ root
  scanning).

### S3 trial piece (NEXT-SESSION step 1) — done

`s3-stacked-loggers` authored in both candidates; source deliberately
well-formed, rig deliberately unrealizable. Expansion contract recorded in
EVALUATION.md: accept stacked mating + LED nets (R22); E1 fatal rtc@68 unary
domain ×2 on one i2c scope (R9); E2 fatal copper-fixed CS D10 ×2; W1
drive-type-on-roles refinement candidate (shared open-drain INT → warning,
not error). Smoke-tested: CPP + stock dtlib clean (16 nodes), phandles
resolve, candidate-2 YAML parses.

### Housekeeping

Superseded v1 `common-dts/rig-types/` + `common-dts/templates/` deleted
(renamed away in pushback round 1; nothing referenced them).

## 2026-07-19 (later) — Expander prototype; front-end verdict: candidate #2

Prototype built per architecture.md in frontend-trial/scripts/ (rigexp
package: shared rig model, loader per candidate, analyzer + emitter under
the strong contract; run_trials.py drives S5/S7/S3 + 6 seeded mistakes
through BOTH candidates).

Verified: front-end neutrality (S5/S7 byte-identical outputs across
candidates); S5 golden-sketch match incl. strap config sheet; R18/R7
(reversed declaration order -> byte-identical outputs); S3 rejected by the
analyzer with E1/E2 as contracted, candidate-independent wording.

**Verdict: candidate #2 (rig.yml hybrid), by the pre-registered criterion —
and the decisive comparison came out INVERTED from the pre-trial framing.**
Stock dtlib's "free" reference checking resolves cell-value references in
post-processing: node path only, no file:line, no candidate list, first
error only (verified in dtlib source). Candidate-2's ~60-line hand-built
dotted-reference resolution beats it (file:line + key path + known-name
lists). The one genuinely hard case (m4 cross-pair, both labels valid but
pair wrong) needs hand-written loader code in BOTH candidates. Full
evidence: EVALUATION.md §"Expander prototype results"; verbatim side-by-side
messages: scripts/out/comparison.md (generated).

Ratification pending (Tobi) before conventions.md is rewritten around
rig.yml. Prototype stopgap flagged: endpoint roles for device gpio
properties are name-inferred (int*/irq* = device drives) — R23 authoring
gap, to be solved together with the drive-type refinement.

## 2026-07-19 (labels & aliases round) — rig.overlay; R10 resolved

Tobi raised: shield-internal node labels collide under multi-instantiation,
and rig-level aliases must be able to name a distinct device on one of many
shield instances.

- **Output labels are compositions**: `<instance>_<shield-local label>`
  (`logger_a_dl_rtc`) — deterministic, analyzer-collision-checked (strong
  contract), stable under adding/removing other instances (R18 spirit), and
  the rig's PUBLIC reference API (same name in final zephyr.dts). Confirmed
  from the prototype's working scheme.
- **Aliases are a selection problem** → the authority-rule pattern again:
  shields never author /aliases or /chosen (S3 collapse in miniature; loader
  error); the rig owns the selection; no counter-based auto-numbering
  (renumbering deployed rigs = the R18 reshuffle ban applied to names).
- **Where the selection lives**: first proposal (aliases: key in rig.yml)
  rejected by Tobi as awkward — aliases are tree content, not topology.
  Adopted instead (Tobi's proposal): the rig directory gains an optional
  **rig.overlay**, completing the entity symmetry (board.yml+dts /
  shield.yml+overlay / rig.yml+overlay). Named .overlay, not .dts: a rig is
  never the tree root, the board is.
- **rig.overlay contract**: output-regime — never loader-parsed, never in
  the rig model, not expander-interpreted; applied on the standard overlay
  chain AFTER the generated overlay (board.dts → generated → rig.overlay →
  EXTRA_DTC_OVERLAY_FILE), so it references generated labels and plain dtc
  resolves them. Zero new machinery. Doubles as the ESCAPE HATCH for
  tree-level facts the model doesn't (yet) express — adoption de-risking,
  same philosophy as "the legacy path never breaks".
- **Deliberate trades**: ownership rule documented, not enforced (expander
  sole author of bus children/reg/cs-gpios; violating it from rig.overlay is
  undefined behavior); typo'd labels in rig.overlay fall back to dtc
  build-time error quality. Both lints parked (parked.md) per Tobi.

Written out: conventions.md Conv. 8 (+ candidate-2 note: per-shield-TU
parsing makes the label prefix discipline unnecessary — candidate-1
structurally cannot), architecture.md (pipeline + analog table + seam
thesis), parked.md (R10 closed; two lints parked).

## 2026-07-20 — Verdict ratified; conventions.md v4 (rig.yml)

Tobi ratified candidate #2. conventions.md rewritten v3 → v4:

- rig.yml is THE front-end; candidate #1 (pure valid-DTS, rig,* props,
  <&instance &node> phandle pairs) retired to git history / candidate-1-dts
  trial files. New "two source artifacts" table up front (rig.yml topology +
  DTS payloads below).
- Ground rules reframed: topology is YAML (all refs strings), payloads are
  DTS; **one translation unit PER SHIELD** (Ground rule 3) → shield-scoped
  labels, dl_/tc_ prefix discipline retired; rig,* naming retired.
- Conv. 5 rewritten as rig.yml (instances/socket/pin by string); Conv. 6
  rewritten as dotted `instance.node` references with the loader resolution
  rules (scope = pads ∪ devices ∪ straps, unique-within-shield; cross-pair
  mistake becomes first-class lang-wire-ref). Conv. 1–4, 7–8 substantively
  unchanged (front-end-neutral / already current).

S7 trial gained candidate-2-hybrid/s7-sqw-counter.rig.overlay — Conv. 8
normative example (aliases onto generated labels logger_1_dl_rtc etc.);
label-consistency verified mechanically (every &-ref is an emitted label).

Doc-leads-code item flagged in NEXT-SESSION: the prototype still builds one
shared shield-library TU; per-shield TUs (Ground rule 3) are normative but
unimplemented — harmless while the trial files keep their prefixes.

## 2026-07-20 — Routing jumpers (R6); strap vs jumper clarified; realizable S2

Tobi asked to nail down "address strap vs solder jumper." Result: both are
configuration elements with a selectable DOMAIN, differing in WHAT they
select — a strap picks a value in an in-band ADDRESS space (target: reg), a
jumper picks which connector POSITION/net an endpoint attaches to (target: a
gpio-spec position cell / CS slot). Both share the fixed/pinned/allocated
trichotomy; the address axis was fully modeled, the position axis had only
fixed (shield,cs-position) + allocated (cs-pool) — the pinned/general case
was the R6 gap.

Implemented the routing jumper (decisions ratified by Tobi):
- syntax = target-the-jumper: a `config` node with `shield,position-domain =
  <pos state>…` and `#gpio-cells = <1>`; the signal references it like the
  plug but position-deferred (`irq-gpios = <&w_irq_jmp flags>`). Nexus-aware
  gpio parse (read phandle, consume target's #gpio-cells) handles plug(2) and
  jumper(1) uniformly.
- non-CS positions must be EXPLICITLY pinned (`pin: {irq_jmp: D2}`); no
  auto-routing (only the fungible CS pool auto-allocates). Unpinned /
  out-of-domain → phys-position error. Auto-routing parked.
- expander resolves the position, rewrites to `<&socket pin flags>`, and
  emits the jumper action + CS pin to the config sheet.

Touched model/shields/loader_yml/analyzer/emitter; conventions.md Conv. 2
gained "Position selection: routing jumpers".

S2 reworked to exercise all of R4/R5/R6/R7: one jumpered WINC shield, two
rigs — `s2-wifi-logger` (IRQ at D7 → phys-net reject; CS still allocates
around the SD's D10, showing collision A handled) and `s2-wifi-logger-ok`
(IRQ at D2 → realizable: overlay + two-line config sheet). The earlier
commit's both-CS-copper-fixed rejection was dropped — that copper conflict is
S3's job; letting the allocator resolve CS is the more faithful R4 story.
Seeded m6 (unpinned jumper) + m7 (out-of-domain) added. All green; R7
verified for the realizable rig.

## 2026-07-20 — S4 backfill (Grove R11/R12/R13; mikroBUS R14/R15)

S4-a (Grove) + S4-b (mikroBUS), candidate-2 only. Each half a realizable
rig + a reject rig.

Net-identity refactor (driven by S4-a R13): nets are now keyed by the SoC
pin the socket gpio-map resolves to (ontology §2 derived closure) rather
than (socket, position). Two DIFFERENT sockets whose positions map to the
same SoC pin are one net — the Maker Pi header5 SIG0 / header6 SIG1 → gpio0
26 alias. NetClaim carries its own socket+position so a cross-socket net's
diagnostic names both endpoints. Positions absent from the fragment's
gpio-map (per-socket dedicated lines, e.g. mikroBUS INT) fall back to
socket-local keys. No regression to S2/S3/S5/S7 (same-socket sharing
unchanged).

S4-a: new board cytron_maker_pi_rp2040, connector type grove
(socket/plug bindings + header), modules grove-pir/grove-button. s4a-grove
clean (R11 typed sockets, R12 attach by socket-instance name); s4a-shared
rejects with phys-net naming "the shared SoC net gpio0 pin 26" (R13). Gotcha
fixed: the header index parser rejects trailing comments on #define lines
(unlike node comments) — grove.h cleaned.

S4-b: reuses Quail + flash-click, adds temp-hum-click (HTS221 fixed 0x5f).
s4b-sockets clean — socket selection picks the controller: flash in sock1 ->
spi1 (CS gpioa3), flash in sock3 -> spi3 (CS gpiod11), two independent SPI
scopes emitted; temp-hum on shared i2c1 (R14/R15). s4b-dup-addr rejects:
two 0x5f on the shared i2c1 across sockets 2+4 -> phys-addr (R9/R15), the
cross-socket sibling of S3. UART regime not exercised (emitter has no uart
device path) — noted in SCENARIOS.md, left for later.

Corpus now 12 trial rigs; R7 verified for both new realizable rigs.

## 2026-07-20 — S6 backfill (nested composition, R19/R20/R21)

Interposers land. New machinery: a carrier shield both plugs a parent
connector AND re-exports its own sockets (Shield.exposes / ExposedSocket).
Exposed sockets are pass-through: gpio-map binds exposed positions to the
carrier's own plug positions, socket,<bus> = <&plug> passes the parent bus
through. The rig names a nested socket by dotted string
carrier_instance.exposed_socket.

Analyzer: socket resolution is now recursive + memoized (_resolve_socket):
a board socket directly, or a carrier's exposed socket COMPOSED against the
carrier's own resolved socket (_compose_socket) — gpio-map composes to real
SoC pins, buses to real controllers, with a pass-through subset check
(parent must actually offer a bus the carrier forwards). Cycle-guarded.

Payoff: because net identity is keyed on the SoC pin (S4-a refactor),
cross-layer conflict detection (R21) came for free — s6-cross-layer catches
an ETH click's chained CS colliding with a board-level Data Logger CS on the
same SoC pin, one claim two layers deep. Emitter: composed sockets aren't
real DT nodes (BoardSocket.is_nexus=false), so nested gpio-specs emit against
the resolved SoC controller, not a nexus label.

Trials: s6-eth-click (two clicks on the adapter, shared spi0, distinct
chained CS — clean; R7 holds even with the carrier declared last),
s6-cross-layer (R21 reject). R20 nested type/subset checking works via the
same mating path. Parked: native-pinmux-CS vs GPIO-CS provisioning and
pinctrl-claim checking (the deep half of R21). Corpus now 14 rigs.

## 2026-07-21 — Nested-socket emission: Option C (nexus synthesis)

Decided (with Tobi) how a nested click's connector-routed signals render.
Rejected Option A (resolve straight to the SoC pin — loses provenance,
diverges from legacy overlays, asymmetric with board sockets). Adopted
Option C: the emitter SYNTHESIZES a gpio-nexus node for each carrier-exported
socket in use, chaining to its parent's nexus; every gpio-spec and every
cs-gpios entry is emitted uniformly through a nexus, and dtc chases the
multi-level gpio-map to the pin — matching hand-written nested overlays and
keeping the routing visible.

Changes: BoardSocket carries nexus_label / nexus_rows / parent (replacing the
is_nexus flag); _compose_socket fills them chaining to the parent's nexus;
_allocate_cs stores (socket, pos) so cs-gpios emits nexus-form; emitter
_synth_nexus_nodes walks sockets transitively and emits one nexus node per
carrier socket. Board-socket cs-gpios also moved to nexus form
(<&quail_sock1 2 ...> vs <&gpioa 3 ...>) for consistency — the analyzer still
resolves to SoC pins internally, so conflict detection is unchanged.

Verified: S6 realizable overlay now emits adapter_1_mb1/mb2 nexus nodes with
gpio-map -> &frdm_ard, cs-gpios + int-gpios through them; all 14 rigs green;
R7 holds for s6/s5/s4b after the change (synthesis is sorted-deterministic).

## 2026-07-21 — bridle real-hardware port; per-instance polarity (gap #1)

Tobi cloned the bridle project as a second testing ground and pointed at
grove_btn/grove_led on seeeduino_lotus. Bridle expresses each Grove module as
64 overlay files (d0..d31 × normal/_inv) + 64-line Kconfig.shield + 32-entry
Kconfig.defconfig — the exact C1×C2 explosion the playbook predicted, done by
a real project. Strong validation of the diagnosis.

Ported to the trial: seeeduino_lotus.rig.dtsi (physical Grove connectors as
typed socket,grove nodes, real SAMD21 pins, incl. the daisy-lacing SIG1(Dn) =
SIG0(D(n+1)) — real R13 material), grove-btn (gpio-keys) + grove-led
(gpio-leds) as ONE shield each, lotus-buttons.rig.yml with three modules.
64 overlays + 96 lines Kconfig -> one shield + one line per module.

The two bridle axes: "which pin" = socket placement (already had it);
"polarity/_inv" = NEW per-instance `invert:` param (gap #1). Minimal
implementation: Instance.invert; loader reads `invert:`; emitter flips the
active-level bit (GPIO_ACTIVE_LOW = 1<<0) of the module's gpio signals.
Verified: inverted button emits 0x21 vs 0x20; R7 holds.

Confirmed-still-parked gaps: Kconfig multi-instantiation (open q1, now with a
concrete instance), PWM/pinctrl provisioning (R21 deep half), and gpio-keys/
gpio-leds AGGREGATION (gap #4) — bridle merges all buttons under one gpio-keys
parent by path-merge; we emit one node per instance (non-idiomatic). Aggregation
is the next design round (touches R10 singletons). Corpus now 15 rigs.

## 2026-07-21 — gap #4: device collections (aggregation), Conv. 9

Collection bindings (gpio-keys/gpio-leds/…) put compatible on a parent and
each device as a child entry. Under multi-instantiation, N modules must
aggregate as N children of ONE node. Added `shield,collect = "<compatible>"`:
a shield marks a device an entry (no compatible of its own); the expander
groups all collected entries across instances by compatible and emits one
collection node per compatible, each entry a child keeping its per-instance
label + node name (Conv. 8 scheme).

Aggregation, NOT collapse — each entry retains identity (R8); the merge is
emission-only (analyzer/net logic untouched). Minimal: Device.collect;
shields parse shield,collect (kept out of passthrough); emitter _collections
groups + _collection_entry renders children; non-bus loop skips collected.
grove-btn/grove-led switched from self-compatible to shield,collect.

Verified: lotus-buttons now emits one gpio_keys node (btn_start/btn_stop
children, btn_stop inverted -> 0x21) + one gpio_leds node — matching bridle's
merged /grove_btns from one shield + placements vs 64 overlays. All 15 rigs
green; R7 holds. Parked (parked.md): explicit collection names; merging into
a board-provided collection. Decision default taken: aggregate by compatible.

## 2026-07-21 — Kconfig layering; expander gains a fourth output

Discussed the Kconfig space. Settled layering (Tobi agreed):
1. Type-level Kconfig + defconfig from BOTH shield templates and rigs (a rig
   is a board-like build entity, so it gets the board-style defconfig trio).
2. NO per-instance Kconfig — symbols are global; per-device config lives in
   DT; driver auto-enable follows the generated overlay via Kconfig's
   dt_compat_enabled / dt_nodelabel_enabled (bridle already does this).
3. The emitter therefore gains a FOURTH output: a per-rig Kconfig fragment /
   ACTIVATION MANIFEST — which shield types + board are instantiated (so
   their type-level Kconfig.defconfig apply; the rig.yml replaces the
   --shield CLI) plus rig-derived defaults.
4. The app prj.conf composes on top and overrides.

Pipeline: expander -> overlay -> DT (edtlib) -> Kconfig (dt_* sees the DT);
the activation manifest feeds the shield-Kconfig machinery. The emitter stays
DT-centric; Kconfig follows the DT rather than being hand-generated per
instance.

Recorded: architecture.md (emitter = four outputs; pipeline diagram; analog
table), conventions.md Conv. 7, ontology.md §3 note (build-config is a
separate axis from the MCU projection), parked.md (settled layering;
implementation + manifest file format still parked, ties to build
integration). Prototype not yet updated (docs lead). Two further subtleties
to discuss next (Tobi).

## 2026-07-21 — overlay subtleties; `.shield` suffix (shields are not overlays)

Two overlay subtleties discussed, plus a suffix decision that resolves the
first.

- **Subtlety 1 — board-specific shield fragments.** Zephyr's
  `<shield>/boards/<board>.overlay` (applied only on that board) is preserved,
  split by our two regimes: `boards/<board>.shield` = board-conditional
  template fragment (loaded, checked); `boards/<board>.overlay` = raw output
  fragment (applied as-is). The suffix tells you the regime.
- **Subtlety 2 — application rig overlays.** Extend the app's
  `boards/<board>.overlay` auto-discovery to rigs: board-keyed keeps working
  on the rig's board, plus a new rig-keyed overlay. Pure build-integration
  (overlay discovery/ordering) → parked.

**Suffix decision (Tobi): shield templates are `.shield`, not `.dtsi`.** A
shield template is a third kind of DT-shaped file — parsed as its own TU
(never `#include`d) and consumed by the rig loader (never dtc); neither an
include (`.dtsi`) nor an applied delta (`.overlay`). "Shields are not
overlays. Shields are shields." Renamed all 12 trial shields `*.dtsi` →
`*.shield`; updated the candidate-1 `#include`s and the loader glob; all 15
rigs still green. Board fragments stay `.dtsi` (genuine includes); rig payload
stays `.overlay` (genuine applied-as-is). Recorded in rig-dt-syntax.md (new
"File suffixes" section), conventions.md (two-source table, Ground rule 3,
Conv. 2 board-specific fragments).

Also flagged (parked): drop the broader `rig-`/`.rig.` prefix — low value,
hard upstream; a mechanical sweep for near upstream-prep. `.shield` is step
one.

## 2026-07-21 — Slice A: multi-function positions (PWM/ADC), pinctrl scope line

Built Slice A of PWM/pinctrl (Tobi-approved). A connector position is one net
reachable as several FUNCTIONS (ontology Refinement 1, finally exercised): the
board declares a nexus per function (gpio-map + socket,pwm-map + socket,adc-map,
mirroring bridle's laced gpio-map/pwm-map). A shield device picks the function
by property (gpios/pwms/io-channels, detected in shields.py by name, cell
layout by the plug's #<fn>-cells). The expander resolves the position through
the matching nexus.

Key reuse: a PWM/ADC claim registers TWO net claims — the pin (via gpio-map,
role dedicated → exclusive with any other use of the position) and the channel
(key ("chan", ctrl, channel), dedicated → one consumer per timer/adc channel).
Both cross-function pin clashes AND channel contention fall out of the existing
net-identity + exclusive-conflict machinery (generalized _cs_copper_conflict →
_exclusive_conflict, keyed by net kind). GPIO emits nexus-form (Option C);
PWM/ADC emit resolved form (<&tcc0 ch period flags>, <&adc0 ch>) since those
aren't nexuses in idiom; the expander enables the resolved controllers.

Pinctrl scope line held: the rig model SELECTS/NAMES the board pin-mux
(config-sheet note + `&ctrl { status="okay"; }`), never authors SoC pinmux —
the board provides the fragments (bridle GROVE_PWM_Dn_PINCTRL). Applying them
is R21's deep half, still parked.

Trials on real Seeeduino Lotus: lotus-pwm (servo grove_d2 PWM + light grove_a0
ADC, clean), lotus-pwm-clash (two servos → same tcc0 ch0 across different pins
→ phys-channel). All 17 rigs green; R7 holds. Gotcha: shared shield-library TU
needs globally-unique labels (grove-light plug renamed gl_plug→glt_plug) —
disappears once per-shield TUs land. DAC noted as same pattern, not built.
Corpus now 17 rigs.

## 2026-07-21 — per-shield translation units (Ground rule 3 implemented)

The shared shield-library TU (labels globally unique across all shields) had
bitten twice — the dl_/tc_ prefixes, and the grove-light gl_plug rename in
Slice A. Implemented Ground rule 3: loader_yml.load_shield_library now parses
EACH .shield file as its own CPP+dtlib translation unit and merges by shield
name, so labels are shield-scoped. Proof: reverted grove-light's plug label
back to gl_plug (collided with grove-led under the shared TU) — now green.
Prefix discipline is no longer required for candidate-2. Candidate-1 (retired)
keeps shared-TU-per-rig via #include, inherent and unaffected. All 17 rigs
green. Docs updated (conventions Next step, NEXT-SESSION). Next: S8.

## 2026-07-21 — S8: active interposer / scope creation (R26/R27) — sweep complete

Built S8, the last playbook scenario. An active interposer (I2C mux) CREATES
scopes rather than passing them through (S6). New: connector type i2c-port
(bare, stackable I2C port), i2c-mux.shield (TCA9548A @0x70, four downstream
i2c-port channels with socket,i2c = <&mux> = new scope per channel),
i2c-sensor.shield (fixed 0x48).

Mechanism: an exposed socket's socket,i2c pointing at a DEVICE of the shield
(not the plug) marks scope creation; _compose_socket mints a fresh BusRef
(path = the channel's instance-qualified id) and records solved.scopes.
Because _allocate_addresses already groups by bus PATH, per-scope address
uniqueness (R26) fell out for free — four channels = four scopes, so four
0x48 is legal; two 0x48 on one channel still conflicts. The emitter nests each
scope's modules inside the mux device's channel@N node (golden TCA9548A
structure). R27 (channel<->module assignment) = the rig's socket placement +
config sheet, no new allocator. Scope-awareness composes with nesting (R19)
with no depth assumption.

Trials: s8-mux (4x 0x48 behind a mux, clean, golden output), s8-mux-collision
(2x 0x48 on one channel -> phys-addr on the channel scope). All 19 rigs green;
R7 holds. Fixes en route: i2c-mux bad gpio.h include removed; _compose_socket
needed `solved` passed; _synth_nexus_nodes skips gpio-less exposed sockets
(empty nexus_rows).

S1-S8 sweep now fully realized. Remaining: S1 fidelity milestone (build +
diff proposal/S1 vs upstream/S1) — a build/diff task, not a new mechanism.
Corpus: 19 rigs.

## 2026-07-21 — S1 fidelity milestone (R2) — prototype phase complete

Last prototype step. s1-datalogger.rig.yml (Data Logger on Nucleo Arduino
header) generated and compared to the real legacy adafruit_data_logger.overlay
+ the real build-rig/upstream/S1/zephyr.dts. Result: the trial nucleo_ard
gpio-map matches the real arduino_header for every used position (D3→gpiob3,
D4→gpiob5, D7→gpioa8, D10→gpiob6), so every generated reference resolves to the
SAME SoC pin as legacy; same addresses/compatibles/gpio-leds aggregation. R2
satisfied (equivalence, not byte-identity). Differences: label naming
(permitted), aliases-in-rig.overlay (Conv 8), and two enumerated gaps for the
real impl — status="okay" (trivial) and sdmmc device sub-nodes (not modeled).
Full write-up: frontend-trial/FIDELITY.md.

A full west build diff was deferred: the trial board fragment is a truncated
hypothetical, not a converted real board; comparing at the overlay level is
exactly what R2 specifies. Drove two fixes: data-logger LEDs → shield,collect=
"gpio-leds" (Conv 9), and a collection-entry naming bug (>1 collected device
per instance now gets unique node names, entry name = composed label).

Prototype phase COMPLETE: S1–S8 sweep + bridle port + PWM/ADC, 20 rigs green,
R7 throughout. Next: wrap-up + real-implementation plan.

## 2026-07-21 — Prototype phase closed; real-implementation plan

Prototype phase complete (S1–S8 + bridle port + PWM/ADC, 20 rigs, R7). Wrote
implementation-plan.md. Structure (per Tobi): additive-first principle
(add>edit, consume dtlib/edtlib don't patch, downstream module before
upstream); driver-agent execution model delegating phases to sub-agents with
human review gates. Phases: P0 reuse-boundary (dtlib/edtlib) ∥ P1 integration
seam (downstream-first, bridle as role model, + spike) → P2 walking skeleton
(S1 end-to-end for real, real zephyr.dts diff, legacy-path regression) → P3
widen slices (allocation / interposers / multi-function), each INCLUDING its
config outputs (Kconfig manifest folded into 3a, pinctrl into 3c) + twister
tests. Cross-cutting: test/CI (twister mirroring the prototype oracle),
diagnostic parity. PARKED until downstream proves out: upstream landing
sequence + rig- naming sweep.

Kicked off P0 and P1 as parallel read-only analysis sub-agents (the driver
model in action).

## 2026-07-24 — fork-per-phase landed; cmake-alone entry ratified; the board→rig lift named

Fork-per-phase cmake refactor (decision B + placement option B) implemented
and landed (`016af37`, btr-shields): boards/shields/dts namesake forks,
rig.cmake dissolved, saferail-13 pre_dt mirror deleted (native
pre_dt_module_run(), called twice), overlay/conf handoff switched from
cache-FORCE to prepend — user extras now WIN (the old clobber was a latent
bug). Reviewed jointly (driver + Tobi; reviewer agent deliberately not
dispatched). Workspace note: the zephyr-rigs worktree is retired — the
workspace zephyr checkout IS branch tskr/zephyr-rigs (rig commits rebased
onto current upstream main); tier-2 goldens refrozen for the rebase
(`f734fa6`: path comments + upstream `ranges;` on st pinctrl, net +5 lines).

Tobi pushback → ratified follow-on (brief: cmake-alone-rig-entry-brief.md):
the rig→board inference living in `west build-rig` violates the cmake-alone
contract (and blocks twister-as-platform). Slot-10 inference moves into the
boards fork via the resolver (cmake passes the FULL `name@rev/variant`
target string, never parses rig content — variant-proof by construction:
a variant may override the board, so the board is a property of the resolved
TARGET, not the FILE). build-rig demoted to a pure cmake wrapper (rig.yml
scanning deleted). -DBOARD+-DRIG mismatch → FATAL.

Named the principle underneath (Tobi): **the board→rig lift** — a board is
a trivial rig (`a → [a]`); rig grammar/resolution are the board machinery
lifted; identity-build + commutation laws; BOARD = projection of the build
coordinate. Recorded as ontology.md §7 with the symmetry-table review
heuristic and the deliberately-open endgame ("every build is a rig build").

Also queued: per-instance parameters into the V1 design round (grove_btn's
type-level `zephyr,code` is the trigger; rig.overlay rejected as the
modeling answer — see rig-variants-revisions.md §QUEUED). Upstream-issue
candidate #3 found during the module-chain review: BOARD_EXTENSION_DIRS in
dts.cmake:181 / kconfig.cmake:96 is dead since HWMv1 extension removal
(c02c6add101).

## 2026-07-24b — edtlib extension-keys carried commit ratified (saferail 10 amended); vendor-prefixes fix

Vendor-prefix warnings for `socket,*` compatibles: fix = btr-shields ships
its own `dts/bindings/vendor-prefixes.txt` (pseudo-vendor precedent:
upstream registers `zephyr` and `vnd`); auto-merged per DTS_ROOT by
dts.cmake. Queued as a one-file driver task after the cmake-alone slice.

Tobi ratified carrying a THIRD zephyr-branch commit: edtlib
`Binding._check` ok_top (edtlib.py:462-468) additionally permits
vendor-namespaced top-level keys (comma-containing, e.g. `rig,positions`),
preserved in Binding.raw — NOT a blanket unknown-key allowance. Unlocks
the original Bridge-A one-file-per-connector-type design: plug contracts
merge into the socket bindings, `dts/connectors/` dissolves. Saferail 10
("consume edtlib zero-patch") formally AMENDED: it binds the expander and
the implementor agents; a deliberate, test-carrying, upstream-RFC-shaped
carried commit is a distinct driver-level instrument. Supporting find:
edtlib's binding scan only validates a dts/bindings file whose raw TEXT
matches a compatible present in the current DT (`dt_compats_search`
fast path) — validation is content/build-nondeterministic, so the current
dts/connectors boundary, while correct, is subtler than it looks; the
patch replaces subtlety with a stated rule. Details in
implementation-plan.md (new queue bullet).

## 2026-07-24c — edtlib carried commits LANDED (rig branch); rig,* namespace chosen

The third-and-fourth carried commits are on `tskr/zephyr-rigs` (local
branch updated, [ahead 2] of tiacsys — push is Tobi's call):
- `c1c4d2acf2d` edtlib: fix operator precedence in the *-cells binding
  validation — REAL upstream bug (upstream-issue candidate #4, PR-able
  independently of rigs): '(A and B) or C' iterated EVERY top-level value;
  non-iterable values crashed with raw TypeError, iterables-of-non-strings
  under unrelated keys (e.g. examples: as list of mappings) were falsely
  rejected. Found BY preparing the extension-keys change (bool-valued
  extension key was the first non-iterable to walk through it).
- `1a657124349` edtlib: permit vendor-namespaced top-level binding keys —
  comma-containing keys opaque, preserved in Binding.raw. DELIBERATE
  exception, docstring'd + test-pinned: the -cells suffix keeps its edtlib
  meaning under a vendor namespace (specifier2cells) — that is what
  enables vendor-defined *-map nexus resolution, so full opacity would
  have been WRONG, not just churn. Fixtures use vnd,* (upstream-shaped,
  rig-agnostic).
Both signed-off (DCO from birth, upstream-destined). python-devicetree
suite 99 green; btr gate green against the patched tree. Extension-key
namespace for OUR content: **rig,*** (Tobi). NEXT: dispatch the downstream
migration slice (plug contracts -> socket bindings as rig,* keys,
dts/connectors/ dissolves, loader reads Binding.raw, goldens
output-stable).

## 2026-07-24d — connector unification LANDED; plug,* supersedes rig,*; workflow rule

`e425a19` (btr-shields): one file per connector type under
**dts/bindings/connectors/** (plural — Tobi review amendment); plug
contracts ride as **plug,*** extension keys. NAMESPACE RULE (Tobi,
supersedes the earlier rig,* ratification): extension keys are namespaced
by the SIDE they describe (plug,*, socket,*), NEVER by the project — no
rig,* key exists. dts/connectors/ + README dissolved; ctypes_registry
single-source; i2c-port got its first real binding (verified pass-2-inert:
synthesized sockets carry no compatible). NEW STANDING TEST
test_connector_bindings.py: edtlib-loads all four files every run — the
only validation i2c-port.yaml will ever get (edtlib's binding scan is
content-sniffing; an unmatched compatible is never parsed), and the
permanent end-to-end proof of carried commit 1a657124349. Golden refreeze:
8x context.cmake, RIG_DEPENDS line only, grep-proven. Gate 70 green.

WORKFLOW RULE (learned the honest way): SendMessage to a completed agent
RESUMES it live in the same checkout — the driver must NOT edit that tree
until the resumed round reports (this session driver and resumed agent
applied the same amendments in parallel; idempotent transforms made it
harmless, diverging ones would not have been). Either wait, or give
amendment rounds worktree isolation. The agent correctly flagged the
concurrent mutation and declined to claim the driver's additions.

## 2026-07-24e — E2 LANDED (quail + frdm extensions)

`0bf32b9`: boards/extend/mikroe/quail/ + boards/extend/nxp/frdm_k64f/,
five rigs repointed, clones stay until E4. Refreeze classification
verified independently (dts_equiv old-vs-new golden): quail +9
re-inherited upstream nodes, frdm +1, all shared nodes byte-identical,
zero removed. cmake-alone slot-10 inference resolved a brand-new
extension target first try. Upstream bases already carry the
load-bearing bus config (no gaps). GOTCHA for E3: a literal `*/` inside
a DTS block comment (glob prose like `mikrobus_*/`) terminates the
comment — corrupted parse, caught by the implementor's own gate run.
NEXT: E3 lotus (base in BRIDLE — the cross-module case; keep
--board-dts explicit), then E4 (delete four clones + trigger the
test-suite de-provenance sweep).

## 2026-07-24f — E3 prereq decided: bridle stays OUT of the west manifest

Tobi: do NOT register bridle as a west project. Lotus rig builds pass
`-DEXTRA_ZEPHYR_MODULES=<topdir>/bridle` explicitly (cache var / env —
zephyr_module.cmake honors both). DELIBERATE: the stronger test — the
cross-module extension must work with module membership coming from a
bare cmake variable, proving nothing ties to west. Known, accepted cost:
lotus rigs are not self-contained-by-one-flag until bridle joins the
workspace properly ("we'll come back to bridle soon enough" — the
no-flag failure mode is a confusing no-such-board listing; documented,
not fixed, this slice). Probes verified 2026-07-24: bridle-as-module
configures cleanly against the rebased zephyr; the bridle lotus base
builds from its own root.

## 2026-07-25 — TRAJECTORY: bridle is the landing target (Tobi)

After V1/V2 land: btr-shields' content upstreams INTO BRIDLE (Tobi is a
bridle maintainer — the first upstream audience is one he co-owns). The
workspace switches; commits get RECREATED as a cleaner, condensed series
(today's commit messages + this ledger are the raw material). The code
lives in bridle for a while, then upstreams into zephyr in small chunks
from there. The E3 no-manifest decision (2026-07-24f) was preparation
for exactly this, besides boundary-testing.

Implications recorded now:
- Carried-commit calculus: once mechanics live in bridle, carried commit
  #1 (module.yml cmake-modules) MAY be retirable — bridle's own
  ZephyrBuildConfiguration workspace hook can prepend CMAKE_MODULE_PATH
  for the forks natively (the P1 road not taken, because bridle owned
  it; in bridle, we ARE bridle). shield-template schema + both edtlib
  commits stay zephyr-targeted (they patch zephyr's own scripts).
- Lotus: the E3 extension is scaffolding TWICE (E4 deletes the clone;
  the bridle migration gives seeeduino_lotus native typed sockets and
  dissolves the extension). E1/E2-style extensions become the permanent
  pattern in reverse: bridle-hosted machinery extending ZEPHYR-owned
  boards — the exact cross-module case E3 proves.
- De-provenance sweep + naming sweep: their real deadline is the bridle
  migration (recreated series + migrated tree born clean).
- claude/rigs corpus needs a destination split at migration: settled
  designs/ontology → bridle docs; pushback ledger → working history.

## 2026-07-25b — E3 LANDED (lotus cross-module extension)

`fd77560`: boards/extend/seeed/seeeduino_lotus/ extends BRIDLE's base
(bridle deliberately NOT in the manifest — every lotus build passes
-DEXTRA_ZEPHYR_MODULES explicitly, per 2026-07-24f; harness threads it
per-case, self-located). All five clone-divergence check items came back
clean (pinctrl/pre_dt_board/Kconfig = byte-copies of bridle's own —
extension carries nothing; BOARD_DIR = base dir so bridle's
pre_dt_board.cmake applies automatically). Refreeze verified: +13
re-inherited legacy connector nodes, 80/80 shared nodes byte-identical.
ACCEPTED-WITH-QUEUE at joint review: the labels[-1] controller-label
flip (tcc0 → grove_pwm_d19 in enable-line + phys-channel diagnostic —
cosmetic functionally, a diagnostics-quality regression textually;
follow-up queued in implementation-plan: controller-label determinism +
diagnostic wording, two separable fixes). Gate 75 green ×3. E4
dispatched (delete all four clones; goldens must be byte-untouched).

## 2026-07-25c — E4 LANDED: extension migration E1-E4 COMPLETE

`90b4126`: all four clones deleted (47 files); btr-shields clones no
board. Two golden lines moved (fixture repoint file:line; unknown-board
known-list now empty — standalone-diagnostic grooming candidate noted),
everything else byte-identical. Gate 72 green ×2 (75→72 = parametrization
losing the deleted board's entry). Every corpus rig now runs on an hwmv2
extension of its REAL base: nucleo/quail/frdm extend zephyr boards,
lotus extends bridle's (cross-module, no-manifest discipline). QUEUE:
de-provenance sweep (now unblocked, deadline = bridle migration),
controller-label determinism follow-up, V1/V2 (+ instance parameters
design round), then the bridle migration (2026-07-25 trajectory entry).

## 2026-07-25d — controller-label determinism LANDED (slice A)

`2378fab`: `board_edt._controller_label` returns `labels[0]`, the
DEFINING label, replacing `labels[-1]` ("last-attached alias wins").
`labels[0]` is what the node's own declaring dtsi gives it and is stable
under module composition forever, so it closes the E3 regression at its
root: re-inheriting bridle's legacy grove aliases can no longer flip the
emitted enable-line or the phys-channel diagnostic. It also makes `*-map`
controllers agree with the `labels[0]` already used for gpio targets and
bus refs. Tier-1 refreeze, 7 lines, label text only (`&adc0`→`&adc`,
`&grove_pwm_d19`→`&tcc0` in lotus_pwm's overlay + config sheet;
`grove_pwm_d19`→`tcc0` in lotus_pwm_clash's three diagnostic lines);
tier-2 and the semantic-pin cross-checks stayed green UNREFROZEN, which is
the proof the resolved DT is identical. New `test_controller_label.py` +
a fixture whose controller carries a later-attached alias pins the
invariant so the failure mode cannot return silently.

**Half of the queued fix DEFERRED TO V1, deliberately.** The plan asked
for analyzer diagnostics to name controllers INDEPENDENTLY of the
emitter's pick. A survey found exactly one controller-identity rendering
(`phys-channel` via `_net_descr`'s "chan" branch), and it reads the same
`board_edt` pwm_map/adc_map value the emitter does — so today the fix
covers both, but genuine independence needs `model.BoardSocket.pwm_map`'s
tuple widened, i.e. the model.py freeze lifted. Recorded as a comment at
`analyzer.py:363` and queued to V1, which lifts the freeze anyway.

## 2026-07-25e — rig<->board naming symmetry (Tobi); slice B1 LANDED

**Ruling (Tobi):** `rig.conf` breaks the rig<->board symmetry. Boards
carry `<board>_defconfig`, so rigs carry `<rigname>_defconfig` — and
`rig.overlay` likewise becomes `<rigname>.overlay` (board `<board>.dts`,
shield `<name>.shield`). Ratified with it: **rig names go UNDERSCORED**
throughout, since boards and shields already are and rigs were the odd
one out. `rig.yml` stays unprefixed — that is the `board.yml`/`shield.yml`
position, not an inconsistency.

**Where the convention line falls, decided explicitly:** upstream shields
name their Kconfig fragment `<name>.conf`, NOT `_defconfig` — only boards
use `_defconfig`. Rigs therefore follow the BOARD convention, shields keep
their own. Justification: a rig OWNS a board, a shield merely attaches to
one (ontology §7's "board = trivial rig"). Expect the question at
upstreaming; that sentence is the answer. Consequence, decided the same
round (Tobi): shield revision Kconfig fragments are `<name>_<rev>.conf`,
following the shield convention. Zero migration cost — no shield in
btr-shields has a `.conf` today.

**Two upstream precedents found (cite when upstreaming):**
`kconfig.cmake:67-69` DEPRECATES `<board>_<rev>.conf` in favour of
`<board>_<rev>_defconfig` — upstream is itself migrating board revision
config files to `_defconfig`, which is the exact template for the rig
revision row. And `zephyr/boards/shields/x_nucleo_iks01a2/
x_nucleo_iks01a2_shub.overlay` already encodes a shield MODE as an
underscore-suffixed overlay with no machinery behind it — the same ad-hoc
pattern as iks01a1/a2/a3, i.e. live evidence for what Q6's
`<name>_<rev>.shield` formalizes.

`eb929e0` (slice B1): all 13 corpus rigs underscored, folders renamed to
their `rig.yml` identity, both hand-authored files renamed. `RigCase`
collapses to one identity field now that folder == rig name, and
`rig_yml_name()` drops out; `test_corpus_rig_identity` still asserts
folder == `rig.yml`'s `rig.name`, so drift stays caught.

**Driver finding at review — a V1 trap closed.** The implementor derived
both filenames from `${RIG}`, the raw user coordinate. `list_rigs.py`
already PARSES `name[@rev][/variant]` (`_RIG_TARGET_RE`) and merely
rejects qualifiers for now, so the day V1 lands, `-DRIG=rig@2/variant`
would compute `rig@2/variant_defconfig` — and since both fragments are
OPTIONAL, that degrades to a SILENTLY unapplied defconfig, not an error.
Fixed to derive from the resolved bare name (`_RIG_RESOLVED_NAME`, which
`list_rigs.py`'s `{NAME}` already emits qualifier-stripped), threaded
through both resolution paths. Generalizable: when a value has a raw
user-supplied form and a resolved form, derive from the resolved one.

**Second driver finding — a golden-staleness class worth remembering.**
The implementor disclosed 2 stale provenance lines in a tier-2 golden and
deferred them as self-healing. In fact its own one-line comment edit to
`grove_sockets.dtsi` ADDED a line, shifting every subsequent line number
embedded in tier-2 provenance comments: 152 stale references across
lotus_pwm AND lotus_buttons. The gate could not see it because
`dts_equiv` compares structurally and ignores comments. **RULE: the gate
passing is not evidence that goldens match the tree. Any edit changing a
file's line count invalidates every tier-2 provenance comment citing it.**
Refroze tier-2: only those two files moved, nothing structural. This
strengthens the parked normalize-on-freeze item — it should strip line
numbers, or a cosmetic dtsi edit will keep doing this.

## 2026-07-25f — de-provenance sweep LANDED (slice B2)

`3660303`: the test suite's FRAMING recast for a reader who was not here.
Saferail numbers, THE FLIP, dual-read comparability, review dates, and
slice/agent attributions are gone; what each test guarantees and what
breaks without it stays. The line drawn: **why the test must exist =
KEEP, who found it and when = GO**, and a verifiable upstream fact (an
edtlib line reference, an upstream deprecation) is a constraint, not
archaeology.

Upstream sorting came back a DELIBERATE PARTIAL, which was the correct
outcome. Only `test_recipe_from_build_info` was cleanly separable and
moved to a BSD-3 `test_edt_build.py` (assertions byte-identical);
everything else that appears to touch `edt_build` reaches it through
`board_edt.load_board`, which projects onto `model.Board` and is Apache
product layer. **RECORDED GAP, not filled:** `edt_build.build_edt()` /
`preprocess()` — the generic cpp+EDT mechanics, the actual upstreaming
candidate — have NO dedicated test; every exercise goes through
`board_edt`'s higher-level API. Fill before that reader travels.

Grooming: the unknown-board diagnostic stops printing `known boards:
(none)`, which implied no boards exist. Every board this tooling builds is
now an extension whose base lives outside `MODULE_ROOT`, so
`find_v2_boards()` never attaches it and the standalone catalog is
PERMANENTLY empty — the diagnostic says so and points at `west boards` /
`--board-dts`, rather than widening the scan (which would dump the entire
upstream catalog into an unrelated error). `zephyr/module.yml`'s header
rewritten to current reality: manifest repo, no `EXTRA_ZEPHYR_MODULES`,
no deleted clone, plural `dts/bindings/connectors/`.

**Naming-sweep inventory (parked item, decisions deferred):** most of the
original ask is MOOT. The `.rig.yml`/`.rig.dtsi` infix is gone as of B1,
and the `/ { rig { } }` node never existed in the real tree. What remains
is `rig-shields` — the DT subtree every `.shield` wraps content in
(`shields.py:31`), present in all 13 shield files and rendered into
diagnostic SrcRef paths in 3 tier-1 goldens. Highest blast radius of
anything left; **awaiting Tobi's decision.** Two stale doc mentions of the
dead infix (`cli.py:163` help text, `dts.cmake:476` comment) are
housekeeping, not decisions. `_rig_*` cmake prefixes remain their own
parked item; `rig-gen.*` was deliberately chosen and is not up for review.

## 2026-07-25g — rig Kconfig fragments ride shield_conf_files (slice C')

**Design round, two positions.** Tobi's first intent, prompted by the
`_defconfig` rename: the rig defconfig should apply AFTER board and shield
defconfigs but BEFORE prj.conf — i.e. the app wins over the rig, matching
what `_defconfig` means for a board. Driver analysis surfaced what that
costs: upstream's merge order (`kconfig.cmake:308-318`) has no pre-prj
slot a module can join (`zephyr_file(... KCONF)` APPENDS, so pre-setting
`board_extension_conf_files` lands ours BEFORE the extension defconfig,
and a fork cannot inject mid-file), so it needed a 5th carried zephyr
commit adding one; and it would drag SHIELD confs ahead of prj.conf too,
since upstream places them AFTER it.

**Tobi WITHDREW the precedence change on that evidence** and ratified the
smaller move instead: append the rig fragments onto `shield_conf_files`
and leave the sequence alone — deliberately, to keep the
application-level overlay/config machinery undisturbed until it is sorted
out after V1/V2. No carried commit needed.

`76b45cf`: the move, verified PRECEDENCE-IDENTICAL on all three axes
(rig still overrides prj.conf; still overrides every shield's own `.conf`;
a user `-DEXTRA_CONF_FILE` still wins). The cleanest form of that last
argument, found by the implementor's independent re-derivation:
`shield_conf_files` is a strictly EARLIER merge slot than
`EXTRA_CONF_FILE_AS_LIST`, whatever either list holds. So "user extras
win" stops depending on this fork prepending correctly into a variable
`configuration_files.cmake` already finalized, and falls out of upstream
ordering — strictly more robust. The fork no longer touches
`EXTRA_CONF_FILE` at all. Because nothing of ours enforces that ordering
any more, a new build-marked test pins it on the real `.config`
(`CONFIG_I2C_TCA954X_ROOT_INIT_PRIO`: 61 from nucleo_mux_farm's own
defconfig, 55 from a user fragment — 55 present, 61 absent).

Step 7 now documents a deliberate ASYMMETRY as a constraint: DT still
prepends onto `EXTRA_DTC_OVERLAY_FILE` because the expander is the sole DT
author and step 5 drops every shield overlay, so rig DT has no existing
slot to join; Kconfig does.

`build_info` keys under `cmake.vendor-specific.rig.*` drop the redundant
`rig-` prefix inside the `rig` namespace and track the current filenames:
`rig-yml`→`yml`, `rig-conf`→`defconfig`, `rig-overlay`→`overlay`, plus
`overlay-gen`/`defconfig-gen` for the generated counterparts.

**A driver claim CORRECTED by the implementor, recorded so it is not
re-derived wrongly:** the move does NOT drop the rig fragments out of
upstream's kconfig provenance. `kconfig.cmake:394` records the whole
`merge_config_files` list under `build_info(kconfig files)`, which
includes `shield_conf_files` — so the fragments go from DOUBLE-recorded
(generic `files` + misattributed `extra-user-files`) to singly recorded
and correctly attributed. Provenance improves. (Nuance: that call sits
inside `if(CREATE_NEW_DOTCONFIG)`, so it is skipped on a cached
reconfigure.)

**Finding, unrelated to the slice:** `rig-gen.conf` is NEVER produced —
the emitter has no such output key, so the expander's generated Kconfig
fragment remains designed-but-unimplemented (parked "Kconfig layering").
Every rig build therefore prints `rig: no Kconfig fragment produced`,
which reads like a fault on a healthy build, and `defconfig-gen` can
never appear today. Reword or drop that STATUS line when the parked
feature is picked up.

## 2026-07-25h — V1 design round: per-instance parameters SETTLED (two pushbacks)

Full design: `rig-variants-revisions.md` §"PER-INSTANCE PARAMETERS — DESIGN
SETTLED". This entry records how the round moved, because two of the
starting assumptions turned out to be wrong.

**Two facts verified in-tree that reshaped the design:**
1. The generated overlay contains NO `#include` at all — every value is
   fully cpp-resolved (`zephyr,code = <11>`, i.e. `INPUT_KEY_0` already
   resolved by the loader's per-shield cpp). So the 2026-07-24 direction
   note's plan — "the EMITTER emits the symbolic token verbatim, pass-2 cpp
   resolves it via the shield TU's own includes" — was NOT implementable as
   written: the generated overlay is not the shield's TU. An emitted
   `INPUT_KEY_1` would have reached dtc undefined, i.e. exactly the cryptic
   failure mode that got `rig.overlay` rejected as the modeling answer.
2. `zephyr_dt_preprocess` passes EVERY overlay to ONE cpp invocation as
   `-include <file>` (`zephyr/cmake/modules/extensions.cmake:4910-4911`), so
   all overlays share a single translation unit. That is what makes Tobi's
   collector-overlay idea work, and it makes it strictly better than an
   inline include block in `rig-gen.overlay`: whatever the collector hoists
   also reaches the hand-authored `<rigname>.overlay` (which today must
   include its own headers for R21 pinmux) and app overlays.

**Tobi's pushback 1 — how does the in-DT declaration generalize to several
properties?** Answer: `shield,params` is a DT string LIST, so a node declares
as many as it needs, and each node carries its own annotation because the
declaration sits with the properties it governs — that co-location is the
reason the in-DT form beat a `shield.yml parameters:` block. One value
feeding SEVERAL properties stays unsupported: assign twice, explicitly
(Q7's minimal vocabulary). 

**Tobi's pushback 2 — defaults are wrong for values only the rig can know**
(a keycode, `zephyr,chosen`, an alias). This produced the rule that removed
a whole decision: **the property's PRESENCE in the template is its default;
its ABSENCE means the parameter is REQUIRED** and a rig that omits it is a
loader error. One vocabulary, no `required:` flag, and the template stops
lying — `grove_btn` becomes correct by construction rather than patched
per-rig.

**Tobi's pushback 3 — "inside the yaml the tokens still come out of
nowhere."** The concern was rig.yml's self-explanatoriness, not validation: a
`.shield` tells a reader where its tokens come from via its own `#include`
lines; a rig.yml saying `zephyr,code: INPUT_KEY_1` told them nothing.
Answer: **`dt-includes:` in rig.yml** — the author writes the include they
would have written in DTS. One construct does three jobs: it makes the file
self-explanatory, it gives the loader exactly what to resolve against, and
it IS the content of the collector overlay (a DECLARED include set, not one
scraped out of the shields). Named `dt-includes` and deliberately NOT
`includes`, since V1 also introduces rig FRAGMENT inclusion and a bare
`includes:` would read as that.

**The resolve-vs-emit fork DISSOLVED** rather than being decided: resolution
and emission are different jobs. The loader RESOLVES (validation + the
number the config sheet renders); the emitter EMITS THE SYMBOL verbatim
(diagnostic readability in overlay and goldens, Tobi's requirement).

**Rejected as overengineering (Tobi):** per-parameter vocabulary/range
checking — rejecting `GPIO_PULL_DOWN` assigned to `zephyr,code` because it
resolves in the wrong vocabulary. A token that resolves is accepted; the
gap is recorded, and genuine type checking belongs to the binding layer
where `zephyr,code` already has a type.

**Two conventions settled from in-tree evidence rather than invention:**
parameter errors take the **`lang-*`** family, not `phys-*` — the codes in
use split cleanly into `lang-*` for declaration/assignment errors
(lang-parse/lang-schema/lang-prop/lang-instance-shield) and `phys-*` for
physical conflicts, and a bad token is not a physics violation. And
`shield,params` must join `_MODEL_PROPS` (`shields.py:24`) so the annotation
is stripped from emission, exactly as `shield,collect` is.

**`invert:` is NOT the mechanism's first client**, reversing the 2026-07-24
direction note. It is not a property assignment: the emitter XORs `0x1`
across ALL of the instance's gpio flags (`emitter.py:176,235`). Parameters =
property values; `invert` = a flag transform. Keeping them distinct avoids
describing the transform falsely; revisit only if a second one appears.

**model.py freeze LIFTED** (saferail 9 was a Bridge-A rail; Bridge-A is
complete). Replaced by: a model change requires a recorded design decision.

**Companion feature identified, deliberately NOT folded in:** rig-level
`aliases:`/`chosen:` addressing instance devices symbolically
(`sw0: btn_start.gb_key`). Same "rig-level assignment, loader-validated,
expander-authored" family, and it would retire Conv. 8's accepted trade
(today the rig author hand-writes emitter-generated label spellings in
`<rigname>.overlay`, where a typo silently creates a fresh node — the very
objection that killed rig.overlay for parameters). But it needs its own
addressing and diagnostics and it reopens Conv. 8, so it stays a separate
slice. Tobi has not ruled on scheduling it.

## 2026-07-25i — slice P LANDED: per-instance parameters

`454b7c7`, gate 81. The design of 2026-07-25h implemented as specified; six
validation rules all demonstrated by committed diagnostics. Sequencing
ratified by Tobi: **P → V1 → V2** (P standalone and FIRST — the design round
was about sharing one vocabulary, not one commit, and the implementation
needs nothing from the delta engine).

**The load-bearing assumption was PROVEN, not assumed:** `rig-gen.overlay`
reaches cpp via `-include <abs-path>`, and GCC documents `-include` as
searching the preprocessor's WORKING directory first — but the nested quoted
`#include "rig-gen-includes.dtsi"` still resolves against the including
file's own directory. Verified by a real build whose `zephyr.dts` shows both
buttons' keycodes resolved to DISTINCT values (`0xb`, `0x2`) sourced from
`rig-gen.overlay`. No `-I<out-dir>` fallback needed.

**GOTCHA worth keeping — a YAML trap in this very design's first draft.** The
spec illustrated assignment in FLOW style, `params: {gb_key: {zephyr,code:
INPUT_KEY_0}}`. That does NOT parse as intended: PyYAML splits the unquoted
comma inside a flow mapping, silently yielding `{zephyr: None, code:
INPUT_KEY_0}`. Any property name containing a comma — i.e. every
vendor-namespaced DT property — must be written in BLOCK style, or quoted if
flow is wanted. Block style is also the corpus's existing convention (`pin:`
never uses flow). Mitigation that already existed by construction: the two
bogus keys are undeclared parameters, so rule 1 fires — the mistake is loud,
not silent. Spec corrected.

**model.py freeze formally LIFTED** and `rigexp.model` dropped off the mypy
exemption list, which now holds only `devicetree.*`. Dropping it surfaced 13
PRE-EXISTING annotation gaps (eleven `src: SrcRef = None` needing
`Optional[SrcRef]`, plus one comprehension) — all mechanical, no semantic
change, which is what kept this from becoming a model.py migration.

Driver added two fixtures the dispatch had not asked for (rules 5 and 6 were
demonstrated ad hoc but uncovered): `param-no-vocabulary` and
`param-missing-header`. NOTE: the rule-6 golden freezes a diagnostic
CASCADE — the header failure (root cause, first) plus a consequent
unresolvable-token error for the same assignment. Left as-is; suppressing
the consequent is a loader change, not a fixture change.

**Slice A's deferred half is now unblocked** by the freeze lift: analyzer
diagnostics sourcing controller identity independently of the emitter needs
`model.BoardSocket.pwm_map`'s tuple widened. V1 or its own small slice.

## 2026-07-26a — V1 readiness pass: four decisions, spec now implementor-ready

`rig-variants-revisions.md` §"V1 — IMPLEMENTOR-READY SPEC" is the
deliverable. Four things were settled; two of them changed ratified design.

**1. Diagnostic family: `lang-rev`/`lang-variant`, SUPERSEDING Q7's
`phys-rev`/`phys-variant`.** Slice P established the split from the code
itself: `lang-*` for authoring/declaration/schema errors (17 codes),
`phys-*` for physical conflicts (13). Every delta failure describes a wrong
DOCUMENT, not wrong hardware — and the physical errors still happen, just
after resolution, on the resolved topology, under their existing codes.
Q7's "physically worded" rule is about PHRASING and is untouched: the
sentence "rev 2 removes instance th2, which variant frdm does not have"
stays exactly that, under a `lang-rev` code.

**2. `params:` under a delta — wholesale replace KEPT, with a
restate-check.** Worked through a two-shield example (design round with
Tobi). The finding that settled it: wholesale replace is not merely
acceptable, it is REQUIRED — when a delta changes an instance's `shield`,
the base's assignments are keyed to devices the new shield does not have, so
merging them would produce errors for a correctly written delta. The hazard
is narrow: same shield + previously-assigned OPTIONAL parameter + delta
omitting it = silent revert to the shield default. Fixed by a check, not by
weakening the rule: a delta supplying `params` for an instance whose
`shield` it does not change must restate every already-assigned property.
Merge semantics stay uniform; only the check is context-aware. A deep-merge
exception for `params` was rejected — it would need a `remove-params` verb
and "no deep merges anywhere" would stop being true.

**3. The per-stage invariant REPLACES a proposed variants-may-add /
revisions-may-not asymmetry (Tobi's opening position, withdrawn on the
argument).** Deltas never "add parameters": shields DECLARE, rigs ASSIGN, so
a parameter set changes only as a consequence of a shield change — and a
revision swapping a shield is Q7's own motivating example, so forbidding it
would gut revisions. Subtler still: a shield REVISION can change the set,
since `<name>_<rev>.shield` is a DT overlay that can author a default where
the base had none (required → optional) or add a device with `shield,params`
and no default (a new required parameter). So the rule is: after EVERY delta
stage, the effective topology must satisfy P's parameter rules. One
invariant covers all three sources.

**4. A real limitation found while working the example: family-wide
revisions cannot re-parametrize a variant-substituted instance.** Under
variant `hpm` the delta must say `hpm_dev`, under `bosch` `bme_dev`; one
fragment cannot serve both. Q9's instance-name-stability convention does not
rescue it — the collision is at device-label and parameter-name level inside
third-party shields we do not control. Decision: VALIDATE it (rule 12,
error naming the variant) and record **per-variant revision streams** as the
escape hatch. Q9 deferred those "until a real case"; this is the case, now
written down with it.

**Also settled: `dt-includes:` UNIONS across delta stages** — the one key in
the vocabulary with union semantics, stated explicitly rather than left to
inference. A vocabulary is additive and there is no meaningful reason to
remove a header; a variant substituting a shield legitimately needs one the
base never declared. (The key postdates Q7, so the vocabulary had said
nothing about it.)

**Driver slicing recommendation, recorded in the spec:** V1a selection and
collection (qualifier resolution, declarations, fragment construction and
discovery, provenance — no deltas, already useful and fully testable),
V1b the delta engine (vocabulary, resolution order, per-stage invariant,
rules 5–12), V1c shield revisions (DT side, rule 13). Slice A's deferred
analyzer-independence half can ride V1b, which is already in the model.

## 2026-07-26b — bridle migration planning; connector-standalone boundary established

Plan: `bridle-migration.md`. Workspace `/wrk/z/ws-b/` prepared by Tobi
(bridle as manifest repo, own branch, zephyr pointed at the patched branch).
Ground rule unchanged: NO history reuse — logical commits authored fresh,
each standing on its own. V1/V2 finish in btr-shields first (Tobi's call);
only the finished feature migrates.

**The substantive finding of this round — where "standalone" actually
ends.** Tobi asked whether, once the typed-connector commit lands, existing
hand-written shield overlays could also use the socket's i2c/spi bus
properties, or whether that needs the expander. Verified in-tree, the answer
splits by HOW DEVICETREE EXPRESSES THE THING:

- **GPIO/PWM/ADC: usable standalone.** The socket bindings declare real
  standard nexus properties (gpio-map, pwm-map, io-channel-map) with
  upstream-matching cell shapes, so a typed socket node IS an ordinary
  nexus — `gpios = <&grove_d2 GROVE_SIG0 flags>` resolves in a plain
  overlay exactly as `arduino_header` does today.
- **Buses: NOT usable, structurally.** DT expresses bus membership by
  PARENTAGE (an I2C device must be a child node carrying `reg`), and a nexus
  only redirects cell values inside a phandle-array property. There is no
  nexus for parentage. `socket,i2c`/`socket,spi`/`socket,uart` are
  `type: phandle` — metadata pointing AT a controller. An overlay must write
  `&i2c1 { sensor@68 { … }; }`, naming the controller directly, which makes
  it board-specific again: exactly the composability break the feature
  removes.
- **Chip-select is the sharpest case.** `cs-gpios` IS a phandle-array, so a
  shield could contribute a CS entry through the gpio nexus — but the SPI
  child's `reg` must equal that entry's INDEX in `cs-gpios`, a global
  order-dependent allocation across every shield on the bus. The founding
  argument ("composition is resource allocation, which no textual mechanism
  can do") applies even to the half that looks nexus-shaped.

Why it matters beyond the question: it gives each commit a statable value.
1+2 deliver the gpio/pwm/adc half COMPLETELY and stay useful to bridle even
if the expander were never taken further; 3's value is "unlocks bus devices
and CS allocation", not "generates boilerplate". That answers a reviewer's
"why do I need a code generator?" with a devicetree fact.

**Ordering preference recorded (Tobi):** stand the tool up STANDALONE first,
add build-system integration only after — which is also how it was
originally prototyped, so it is a return to a known-good shape.

**Content triage is three ways, not two:** real bridle content (the grove
shields + lotus rigs — bridle owns seeeduino_lotus and those shield
families, this is the payoff), test fixtures only (the synthetic rejects),
and does-not-travel (nucleo/quail/frdm extensions, click and adafruit
shields — S1-S8 playground). The coupling to watch: the golden corpus is
tied to the playground, so if the corpus does not travel the expander lands
UNTESTED. Tests therefore split across commits 3 and 6, which is B2's
upstream-destination sort put to use.

**Found while planning: both comment sweeps MISSED
`dts/bindings/connectors/*.yaml` and `include/dt-bindings/connector/*.h`** —
neither was in either scope list. They carry the heaviest archaeology left
(grove.yaml cites "Bridge-A rewrite phase 2a", "Slice A", "the trial's
modules", a carried-commit hash; arduino-r3.h has 27 hits) AND they are the
most public artifacts in the migration, since a binding description is what
an upstream reviewer reads first. Recorded as a pre-migration task.

**Naming — OPEN.** `rigexp` was an internal name; Tobi wants the tool to
describe what it does while keeping "rig". Candidates `rig2overlay` /
`rig2dt`. Recorded objection to the `X2Y` shape: the tool emits more than
devicetree (config sheet, expectations, a designed Kconfig fragment) and its
primary value is arguably the analyzer's VALIDATION — a converter name hides
both. Decide before authoring commit 3; the `_rig_*` cmake re-idiomization
(parked "until patch-drafting time") rides along with it.

## 2026-07-26c — the tool is named `rigc` (Tobi)

Ratified from the naming ideation of 2026-07-26b. `rigexp` was internal;
`rigc` is the upstream name, by analogy to `dtc`. The analogy was the
deciding argument: it carries both things a converter-shaped name
(`rig2dts`/`rig2overlay`) hides — that the tool REJECTS invalid input (the
analyzer's physical diagnostics are the primary value, not a side effect) and
that it emits SEVERAL artifacts, not one. `rig2dt` was additionally wrong on
a technicality: `dts` is devicetree SOURCE, `dt` is the abstract tree, and
what the tool writes is a `.overlay` in dts syntax. Accepted cost: cryptic
to a newcomer.

Recorded in `bridle-migration.md` with the follow-on renames
(`scripts/rigc/`, `python -m rigc expand`, `RIGC_*` cmake vars) and, more
importantly, what deliberately does NOT rename: **the generated artifacts
stay `rig-gen.*`**, because an artifact is named for what it is generated
FROM, not by — zephyr writes `zephyr.dts`, not `dtc.dts`. Also unchanged:
the `Rig:` message prefix, `west build-rig`/`west rigs`, `.shield`,
`rig.yml`, `<rigname>_defconfig`, `shield-templates`, and the diagnostic
codes.

Terminology consequence: **"the expander" retires as a noun** — the tool is
`rigc`. "Expansion" survives as the phase/verb, already the CLI subcommand
(`rigc expand`), and the internal pipeline stays loader → analyzer →
emitter. `architecture.md` defines "expander" as a toolchain term and needs
updating when the migration commits are authored.

## 2026-07-26d — combined (variant, revision) fragments: revision LAST, per hwmv2

Tobi asked what resolves `pilot_variants_2_variant_a_defconfig` for
`pilot_variants@2/variant_a`. Answer: nothing — V1a constructs only
single-axis names, so such a file sits SILENTLY ignored, the worst failure
shape since it looks like it should work. The round-2 sketch had anticipated
the combined form ("per-(variant,rev) DT, if ever needed") without ratifying
it. Decided: build it in V1b, where a variant can first differ in topology
and rule 12 already forces the per-(variant, revision) question.

**Order settled from upstream, not preference: REVISION LAST** —
`<rigname>_<variant>_<rev>_defconfig`. `zephyr_build_string()`
(`extensions.cmake:1774`) joins board → qualifiers (soc/cpucluster/variant)
→ revision, confirmed against real boards
(`nrf9160dk_nrf9160_ns_0_14_0.overlay`: board, soc, variant `ns`, revision
`0.14.0` last).

Worth recording because it is counter-intuitive: **upstream deliberately does
NOT mirror its own selection grammar.** The grammar puts revision FIRST
(`board@rev/soc/variant`); the filename puts it LAST. The driver had
recommended revision-first on the reasoning that a filename should read like
the target string an author types — wrong, and upstream evidently considered
that shape and chose otherwise. Tobi caught it by asking whether his own
proposal matched hwmv2 rather than accepting the recommendation.

Two consequences folded into the spec:
- **Adopt hwmv2's revision normalization** (`extensions.cmake:1772`,
  `string(REPLACE "." "_")`) so a dotted revision id becomes underscores in
  the filename (`1.2` -> `1_2`). V1a's pilot used bare integers and never
  exercised this; follow upstream rather than inventing a rule the first time
  a dotted revision is declared.
- **Rule 4's collision guard must WIDEN.** It currently rejects a variant
  name equal to a revision id, which suffices while each filename carries one
  axis. With a combined form, a variant named `variant_a_2` constructs the
  same filename as variant `variant_a` + revision `2`. Since Q6's protection
  is that filenames are only CONSTRUCTED and never parsed, the hazard is two
  distinct selections constructing ONE name — so the check becomes: no two
  selectable (variant, revision) tuples may construct the same filename.

Nothing in V1a needed reverting: only single-axis names exist there, so no
ordering was encoded.

## 2026-07-26e — V1a + V1b LANDED; V2 shrank to almost nothing

`5031a0f` (V1a, selection + collection) and `5995f08` (V1b, the delta
engine). Gate 81 -> 98 -> 109.

**The sequencing bonus arrived more completely than predicted.** Round 3
collapsed variants and revisions onto ONE delta mechanism, and the note then
said building it for revisions would "de-risk variants for free". In
practice V1a/V1b absorbed nearly all of slice V2's scope: the `variants:`
block, `<rig>_<variant>.yml` fragments, per-variant overlay/defconfig
collection, the `/variant` qualifier, variant-name/revision-id validation,
variant diagnostics and variant golden tuples all landed. **V2's remaining
substance is two items: board swapping, and a positive-path test for
`sockets:` abstract->label maps.**

**A variant's `board:` is REJECTED for now — the requirement is unchanged.**
Board resolution happens in `list_rigs.py` BEFORE any fragment is read, and
cmake sets BOARD from that answer, so applying a variant's override in the
loader left the model, the overlay header and context.cmake's `RIG_BOARD`
claiming one board while pass 1 read and pass 2 built another. The agent had
reported this as "accepted but cosmetic/inert"; it is not inert, it is an
active disagreement. Driver made it a loud rejection: a placeholder that
cannot produce a wrong build, lifted by the slice that makes the resolver
fragment-aware. That slice is V2's residue and belongs with the rig-swap
guard / `RIG_INFERRED_BOARD` / RIG-BOARD-exclusivity surface, so it gets its
own review rather than a corner of another slice. Ratified order: **V1c, then
V2-as-residue.** Nothing tested board substitution because V1b's golden
budget only asked for SHIELD substitution — which is how it slipped through
as "inert".

**Rule 10's default exemption (V1a) and rule 4's widening (V1b)** are both
recorded in their own entries (2026-07-26 rule-10 correction in the V1a
commit; 2026-07-26d for the combined-fragment order). Both came from Tobi
questioning a driver recommendation rather than accepting it.

**Slice A's deferred analyzer-independence half: CLOSED, not dropped.** Both
consumers read the same single `socket.pwm_map[pos][0]`, so no independent
re-derivation exists for the emitter's pick to diverge from — slice A's own
`labels[0]` fix closed it architecturally. `model.py` untouched. Recorded so
it is not re-queued.

**A verification lesson worth keeping: the agent STALLED mid-V1b** (watchdog,
600s) and the resumed run left a defect the gate could not see. A
golden-freeze block had been duplicated into the widened-collision test, so
it wrote that fixture's diagnostic into `variant-no-fragment`'s golden while
the rule-10 test lost its freeze entirely — a committed golden that was WRONG
and asserted by NOTHING. The gate stayed green because nothing checked it.
**Rule: after a stalled/resumed slice, run the suite TWICE and diff the
goldens — a clobbering freeze only surfaces on the second run, and a golden
nobody asserts never surfaces at all.** Generalizes the B1 lesson (the gate
passing is not evidence that goldens match the tree).

## 2026-07-26h — rig.yml is TWO files: the metadata/content split (Tobi's finding, RATIFIED)

Tobi's own observation, and it names an asymmetry that had been felt but not
articulated: **`rig.yml` is not symmetric with `board.yml` or `shield.yml`,
because in the simplest case it also IS the `<rigname>.yml` that sits
symmetric with `<board>.dts` and `<name>.shield`.** Three entities, three
content filetypes (.dts, .shield, .yml), similar meta-level semantics — and
the rig using YAML for content as well as metadata is what masked the
conflation.

**The sharpest form of the argument, from the naming conventions themselves:**
metadata files are named after the entity TYPE (`board.yml`, `shield.yml`,
`rig.yml` — the same filename in every folder); content files are named after
the entity INSTANCE and its qualifiers (`<board>_<soc>_<variant>_<rev>.dts`,
`<name>_<rev>.shield`, `<rigname>_<variant>_<rev>.yml`). Under that rule the
missing file has a name, and **our own V1 design already implies it**: the
delta fragments are instance-named with no same-stem base to be deltas of.
`pilot_variants_variant_c.yml` sits beside `rig.yml`, where the board and
shield equivalents always sit beside `<board>.dts` / `<name>.shield`. We built
the fragment half of the convention correctly and left the base in the
metadata file.

**Three pieces of in-tree evidence, strongest first:**
- **`list_rigs.py` already reads exactly the metadata keys and nothing else** —
  `name`, `board`, `revisions`, `variants` — ignoring instances/wires/params,
  and carries a comment saying it deliberately does not validate shape because
  that is the loader's job. The split is already implemented AS BEHAVIOUR
  INSIDE ONE FILE, with a comment apologising for the missing boundary.
  Upstream's discovery layer reads whole metadata files cheaply and validates
  them strictly precisely BECAUSE they contain no content.
- **`board.yml` and `shield.yml` contain zero hardware description.** Not one
  key. `rig.yml` is literally the union of the two roles.
- **V1c is the mirror image and needed a ruling to cross the line.** For
  shields the boundary is crisp, so the loader reading `shield.yml` for the
  revisions axis required an explicit decision (metadata supplies the axis,
  never a second identity). For rigs there is no boundary, so no such
  discipline can exist.

**A driver claim CORRECTED by Tobi: `<rigname>.yml` is the analogue of
`<board>.dts`, not of `rig-gen.overlay`.** Both are generator INPUTS and
`zephyr.dts` is the common output; `rig-gen.overlay` is on the output side of
one generator and the input side of the next, joining the board's own input
stream as an extra overlay. The driver had put `rig-gen.overlay` opposite
`<board>.dts`, which is the wrong end of the pipeline. The generators are
offset by one configure stage, which Tobi acknowledged and which the symmetry
table should state rather than imply a flat correspondence.

**The `board:` question, settled by looking at how the SoC actually resolves.**
Tobi argued `board:` is topology, as the SoC is a `<board>.dts` detail. The
driver argued it is a coordinate. Both are right, and upstream shows they do
not conflict, because the SoC name appears in THREE roles:
`soc/st/stm32/soc.yml` registers which SoCs exist at all; `board.yml`'s
`socs:` declares which of them THIS board offers as a selectable qualifier;
`<board>.dts` `#include`s the SoC dtsi. **Resolution from a qualified target
to arch/soc build content is a NAME LOOKUP into the soc roots, never a parse
of the `.dts`** — the include is content that must AGREE with the selection,
and `<board>_<soc>.dts` naming keeps them consistent. So a board's
CONSEQUENCES are topology (the rig's instances reference its sockets, the
`#include` analogue) while its IDENTITY is a coordinate. Content therefore
carries NO `board:`: derived, never declared, so there is no second source of
truth to diverge.

**Which DISSOLVES V2's board swapping rather than merely diagnosing it** — a
correction to the driver's first take. The current rejection exists because
the board is resolved from metadata early and would be overridden from content
late. Put the board under the axis value and resolution stays single-source
and early; the variant's fragment supplies only topology suited to it. The
rejection gets DELETED rather than lifted, and no fragment-aware resolver is
ever built.

**Ratified target shape, worked through on a real dual-host rig** (arduino
shields on either nucleo_f401re or frdm_k64f — see the brief for the files):
`rig.yml` carries name/full_name/vendor/revisions/variants plus a `board:` and
a `sockets:` map per axis value; `<rigname>.yml` carries instances/wires/
params/dt-includes and is BOARD-AGNOSTIC, naming an abstract socket (`ard`)
that each axis value maps to its board's label (`nucleo_ard` / `frdm_ard`).

**Confirmed with Tobi: omitting a variant's fragment entirely is legal and
means "reuse the base content on this board."** Exactly the board precedent —
`nucleo_f401re.dts` is the content for every revision, and
`<board>_1_0_0.dts` exists only where a revision differs — and exactly the
reasoning V1a's rule-10 correction already established. What is guaranteed is
an HONEST ATTEMPT, not success: the same content is re-checked per coordinate,
so a shield needing a bus the selected socket lacks is loudly rejected on that
host and realizable on the other. `nucleo_ard` deliberately exposes no
`socket,uart` while `frdm_ard` carries `uart3`, which makes that a real corpus
case rather than a hypothetical.

**Portability is sound by construction, not by the two boards resembling each
other:** `ARDUINO_HEADER_R3_D10` is 16 in one shared header, and both socket
nodes map that index to their own pin (`&gpiob 6` nucleo, `&gpiod 0` frdm),
all 22 positions from the same namespace. A shield says D10; only the resolved
controller and pin differ. Same reason bridle's 64-overlay product collapses.

**Three changes the split REQUIRES, recorded so none is discovered late:**
1. Content keys move out of `rig.yml` (slice S1, a pure move).
2. The socket map must apply to the BASE topology, not only where a delta
   restates `socket:`. Today `resolve_socket` is reached only from
   `_apply_instance_patch` (`loader_yml.py:812`), so abstract names work only
   if every instance is restated in every variant fragment — which is exactly
   why this feature's positive path was never exercised.
3. **Rule 10 widens**: an axis value contributing only a board and/or socket
   map — both metadata — contributes. Otherwise a legal dual-host rig whose
   frdm variant needs no fragment is rejected.

**SEQUENCING (driver's call, Tobi delegated): pull the split in straight,
BEFORE V2-residue, before the revision-semantics and rig-schema slices, and
before the migration.** Doing V2 first means building a fragment-aware
resolver that S2 immediately retires. Doing revision semantics first writes
upstream's revision block into a conflated file and then moves it. Doing the
schema first CEMENTS the conflation — and afterwards the schema becomes what
ENFORCES the split, since `additionalProperties: false` on a metadata-only
schema makes putting `instances:` back a loud discovery-time failure. That
answers the one real objection to two same-language files: the boundary is
enforced, not merely conventional. Doing it after the migration would rewrite
history that had just been condensed.

**V2 IS FULLY ABSORBED after S2** — its two residual items were board swapping
and `sockets:` positive-path coverage, and S2 delivers the first as a
declaration and exercises the second by construction.

Brief: `rig-metadata-content-split-brief.md` (S1 = the move, zero semantic
change, evidence is unchanged goldens; S2 = board per coordinate + socket map
at base + rule 10). Open, non-blocking: whether the socket map is metadata
(this brief) or content; and whether a nested board coordinate should make the
rig target multi-segment (`name@rev/board/variant`) rather than the ratified
single-segment form — deliberately NOT done, since per-axis-value declaration
gets board swapping without touching the grammar.

## 2026-07-26g — V1c LANDED (`bfe8433`, zephyr `ca040c05cad`): four driver fixes, one latent crash, symmetric provenance ruled

V1c (shield revisions) implemented by the sonnet implementor, then verified
INDEPENDENTLY by the driver. The agent's own report was honest and flagged
three of its decisions for ratification; independent review still found four
defects it had not seen, one of them a reachable crash. Gate: **119 passed**
(117 + 2 driver-added rejects), mypy clean on 22 files, three green runs,
golden drift clean across two consecutive runs.

**What the agent built and what it got right.** shield.yml gains the same
axis block (reusing `_parse_axis_decl`), `shield: <name>@<rev>` resolves per
instance, base `<name>.shield` + `<name>_<rev>.shield` share ONE translation
unit with DT's overlay-by-label doing the merge, `<name>_<rev>.conf` rides
the shield Kconfig tail after the base, rule 13 plus the "declares no
revisions: at all" and "no default" shapes, and the zephyr
`shield-schema.yaml` extension as a STANDALONE upstreamable commit (Tobi's
instruction — it is the same mechanism that required the carried `template:`
commit, since `list_shields.py` jsonschema-validates every shield.yml under
`additionalProperties: false`).

**Ratified from the agent's flagged list:**
- **Lazy revision resolution**, and its reasoning beat the driver's own
  eager suggestion: eagerly parsing every DECLARED revision would leak that
  fragment's path into every OTHER rig's RIG_DEPENDS purely because a
  revision was declared somewhere, breaking rule 10's "declaring an axis is
  not a breaking change until a fragment is authored" property.
- **The rule-10 shield analogue** as an OR of fragment kinds: a non-default
  revision must contribute `<name>_<rev>.shield` OR `<name>_<rev>.conf`,
  default exempt.
- **The per-stage parameter invariant holds with ZERO code changes** — a
  shield revision introducing a new required parameter is rejected by the
  existing fresh re-check. Now proven by test rather than by inspection.

**MODEL DECISION (the lifted freeze requires one recorded): `Shield` gains
`revisions: Optional[AxisDecl]` and `revision: Optional[str]`** — the
declared axis and which revision THIS Shield object represents. Needed
because provenance must name the resolved revision, and because one shield
name now yields several Shield objects within a single library.

**Four driver fixes applied after review:**

1. **A wrong-blaming diagnostic (reproduced, not inferred).** One parser
   serves rig.yml and shield.yml, and its messages were hardcoded to "rig
   ...", so a malformed shield.yml block reported
   `rig revisions: default '3' is not one of the declared values` — blaming
   the RIG for a shield's own declaration and naming no shield. Fixed with an
   `owner` parameter defaulting to "rig", so rig-side wording is
   byte-identical and the shield side names the shield. This project has
   treated wrong-blaming diagnostics as review-blocking before (the
   wrong-board-blaming phys-socket errors of the cmake-alone slice).
2. **Identity: the FOLDER basename had silently become the resolution key**
   while the docstring still asserted the DT node name was "the SOLE identity
   source", and `parsed.get(name) or next(iter(parsed.values()), None)`
   papered over any mismatch. All 14 corpus shields happen to agree, so it
   was latent. Replaced by `_pick_shield`, which reports a `lang-shield-name`
   error naming the folder and the nodes actually defined. **RULING: the node
   name stays the identity every artifact spells; the folder basename is the
   RESOLUTION key, and the two must agree.** This is the same
   identity-authority question the bridle plural-shield work needs settled
   (see `bridle-migration.md`), decided here first.
3. **A LATENT CRASH that fix 2 exposed.** `resolve()` ended in
   `assert decl is not None`, justified by "a non-revisioned shield is always
   in `shields`". Once `_pick_shield` can fail that stops being true, and a
   node/folder mismatch would raise `AssertionError` instead of diagnosing.
   Replaced with a quiet return — the error is already reported against the
   template, and echoing it once per referencing instance would only bury it.
4. **`shield.yml` was untracked in deps**, so editing a `revisions:` block —
   moving a default from rev 1 to rev 2, say — did not retrigger configure.
   The agent's churn argument was real but the SHAPE was wrong: tracking at
   scan time would put every shield's metadata into every rig's RIG_DEPENDS.
   Fixed by tracking at RESOLVE time, so a rig depends only on the shield.yml
   of shields it actually names, recorded BEFORE resolution can fail (since
   declaring the missing revision is exactly how such a failure is fixed).

**RULING (Tobi): provenance goes SYMMETRIC.** The agent suppressed a
DEFAULTED shield revision from `RIG_SHIELD_REVISIONS` / `build_info` / the
STATUS line to protect zero churn, and flagged the resulting asymmetry with
`RIG_REVISION`/`RIG_VARIANT`, which do show their defaults. Measured cost of
symmetry was small and the argument against suppression decisive: silence
would mean BOTH "revision 1" and "this shield has no revisions", so
provenance could not answer which revision a given build used — the question
it exists for, and the same species as the B1 record-the-RESOLVED-form rule.
Now written whenever a shield DECLARES an axis.

**Churn accounting, proven rather than asserted.** Every changed line across
13 goldens classifies as exactly two kinds: 13 × `RIG_DEPENDS` (additive
only, zero paths removed) and 1 × a new `RIG_SHIELD_REVISIONS`. The best
evidence the deps shape is right is `pilot_variants_variant_c` picking up
`pilot_alt_button/shield.yml` — its VARIANT-SUBSTITUTED shield — so
resolve-time tracking follows the RESOLVED topology through the delta
engine, not the declared one. Note fix 4 is slightly broader than the hole it
closes: any shield.yml edit now retriggers configure for rigs using that
shield, which is why 13 goldens moved rather than the 2 predicted.

**A budget gap found by Tobi's own question, then verified.** "Can a rig
revision 2 select `shield: sensor@2` while revision 1 uses `@1`?" — yes,
today, with no further code: V1b routes an instance patch's `shield:` through
the same resolver as a base reference, so the `@rev` grammar composes with
rig revisions for free. Verified independently (bare/`@1` → `vnd,temp0x48`,
`@2` → `vnd,temp0x48v2`, zero diagnostics on all three). The agent had
reported this path as "code-verified" via an uncommitted throwaway script,
which by this project's own rule is a hypothesis. **FOLDED IN before the
commit** as `shield_rev_family`: the bare tuple resolves the sensor to
revision 1, the rig's own revision 2 moves it to the shield's revision 2,
with tier-1 goldens plus a real tier-2 build asserting BOTH `zephyr.dts` and
the collected `i2c_sensor_2.conf`. The `.conf` assertion is the load-bearing
one — it proves the composition survives the whole handoff (loader resolves
the delta, the expander reports the resolved shield revision through
context.cmake, dts.cmake turns that into a collected fragment) rather than
only proving the loader picked the right shield. Kept SEPARATE from
`shield_rev_pilot`, which demonstrates a direct `@2` reference from a base
topology: two distinct things, one fixture each.

**Landed as `bfe8433`** (btr-shields, gate 124, `main` ahead 5 UNPUSHED) plus
**`ca040c05cad`** in zephyr — the schema file committed ALONE per Tobi, so it
stands as its own upstreamable carried commit (the fifth).

**Two gaps recorded, neither fixed:**
- **Validation timing is now asymmetric.** A revisioned shield's base
  template is no longer parsed at library load, so its internal validation
  (unknown connector type, missing plug, addr-from rules) runs only when a
  rig selects it, while non-revisioned shields still validate on every
  expand. Its TU's `#include`s likewise stop reaching deps for unselected
  revisioned shields — no golden caught that because every shield includes
  the same connector headers. Inert by luck, not by construction.
- `string(FIND ... "@")` returning -1 would make `SUBSTRING` swallow a whole
  RIG_SHIELD_REVISIONS entry. Harmless today (entries always carry `@`).

## 2026-07-26f — schema symmetry round: the rig.yml / board.yml delta, three rulings, two open cells

A comparison of `rig.yml` against `board-schema.yaml` key by key, run while
V1c was in flight. It produced three rulings from Tobi, reclassified the
board→rig lift's open cells, and surfaced a third gap nobody had listed.

**Where the two schemas already agree by construction:** target grammar
(`name@rev/variant` mirroring `board@rev/qualifiers`, same three-way split,
parser mirrored from `parse_board_components`), fragment filenames
(`zephyr_build_string`, `_`-joined, revision LAST), revision dot
normalization, cumulative layering, and filenames constructed never parsed.

**RULING 1 (Tobi): revision logic and behaviour become EXACTLY upstream's.**
Format typing (`letter` / `number` / `major.minor.patch`) with per-format id
validation, the `exact:` opt-out, nearest-lower-match resolution, and the
loose-typing zero-append (`@1` → `1.0.0`). Two pieces are deliberately NOT
copied, and both refusals are load-bearing rather than lazy:

- **`format: custom` → `include(<dir>/revision.cmake)`.** Upstream resolves
  revisions in cmake; we resolve them in Python (`list_rigs.py` + the
  loader). Copying `custom` means either arbitrary cmake in a rig folder
  feeding a Python resolver, or moving resolution into cmake. Rejected
  loudly instead — which means full parity cannot be claimed, only
  behavioural parity for the three real formats.
- **The valid-revision glob** (`extensions.cmake:1114-1126`, discovering
  revisions by matching `<board>_*.conf` filenames). Reachable only via
  `custom`, and it PARSES FILENAMES — against Q6. Worth recording that
  upstream violates construct-don't-parse in exactly this one place.

Three consequences. (a) **The one-schema-for-both-axes property of the V1
spec §2 is spent** — upstream's revision block is
`revision: {format, default, exact, revisions: [{name}]}` and variants have
no counterpart, so the two axes diverge in shape. Ratified direction: go to
upstream's SHAPE as well, not a near-miss, because a reviewer diffs our
schema against `board-schema.yaml` and every gratuitous difference costs
credibility. (b) **Requested vs resolved becomes representable and must be
carried** — nearest-lower means `@1.5` resolves to `1`, upstream keeps both
(`BOARD_REVISION` vs `ACTIVE_BOARD_REVISION`), and the RESOLVED value is
what constructs filenames. This is the `_RIG_RESOLVED_NAME` hazard class
again; the configure log shows `requested -> resolved` when they differ.
Needs a model field, hence this entry. (c) **V1c is writing the simple
`{default:, list:}` block right now** — it lands as-is (its value is the DT
mechanic, orthogonal to id typing) and the follow-up migrates rigs AND
shields in one place, `_parse_axis_decl`. Accepted churn: the carried
`shield-schema.yaml` commit gets rewritten before upstreaming.

**RULING 2 (Tobi): `full_name` REQUIRED on rig.yml, `vendor` optional, and
the target regex's `@` position fixed.** Shields require name + full_name +
vendor; boards require name + full_name; rigs carried none — rigs were the
odd one out of the three. `full_name` required touches every existing
rig.yml and must then SURFACE somewhere (`west rigs` format keys, mirroring
`west boards` / `west shields`), else it is a required key nobody reads.
Regex: ours accepted `@` inside the qualifier (`(/(.+))?$`) where upstream
forbids it (`(/([^@]+))?$`), so `rig/variant@2` parsed for us and is fatal
upstream. Foresight attached: author the schema with board-schema's
`oneOf: [required:[name, full_name], required:[extend]]` shape in mind, so
requiring `full_name` need not be unpicked if rig `extend:` ever lands.

**RULING 3 (Tobi): the expectation-management plan, cheapest first.** (1) a
`rig-schema.yaml` that REJECTS the unsupported thing BY NAME with a pointer
to what to use instead, (2) the symmetry table amended in ontology §7, (3)
implementation of rig `extend:` only, and only after root-precedence policy.

**The lift's two open cells, reclassified.** Tobi observed two things boards
can do that rigs cannot: a board.yml may declare MULTIPLE boards, and a
board may be EXTENDED from another folder or module. §7's own stated limit
settles them, and it settles them differently:

- **`boards:` multiplicity is ARTIFACT-level — not owed by the lift.** It
  governs how many declarations share one YAML file; each declared board is
  still its own coordinate, so the coordinate algebra is untouched. Two
  supporting arguments: upstream needs it because boards have no delta
  engine (siblings must be spelled out) whereas we have variants +
  fragments, and the sharing pressure is asymmetric — a board directory
  carries heavy shared DTS/Kconfig, a rig folder carries `rig.yml` plus a
  defconfig. Usage: 47 of 1066 board.yml, 45 of 210 shield.yml.
- **`extend:` is COORDINATE-level — owed, and deferred.** It adds new
  SELECTABLE COORDINATES from another module. That is the algebra, not the
  packaging, so §7 was right to reserve the slot.

**The symmetry-table heuristic was one-directional, which is WHY these
accumulated.** As written it says every mechanism added on the RIG side must
map to its board-side counterpart or state why not — board→rig gaps are
invisible to it. Widened to bidirectional in §7 with both cells filled.

**Calibration on `extend:`: upstream has ZERO in-tree users** — two test
fixtures under `tests/cmake/hwm/board_extend`, nothing else — while we have
four. It is a downstream-facing affordance whose main real users are people
like us, and correspondingly thinly exercised, so inheriting its exact
semantics is riskier than inheriting `board_check_revision`, which many
boards drive. Three facts for when it comes: it is EASIER than board
extension was (candidate-#2's cross-dir `#include` gap does not recur,
because our merge is data-level YAML deltas, not translation units);
mechanically it is multi-root fragment discovery — the shield library is
ALREADY multi-root unioned for exactly this reason — plus an `extend:`
declaration contributing axis values; and its prerequisite is
root-precedence policy, not effort, since the live last-wins collision
(stock `adafruit_data_logger` resolving over ours) multiplies with it. The
migration makes it pressing: once rig content lives in bridle, a downstream
consumer wanting "bridle's rig, our sensor swapped" can only fork the rig
folder — the copy-a-folder antipattern V1c exists to kill for shields.

**THE THIRD GAP, surfaced by the same comparison and confirmed against
bridle: shield plurality.** Our rig-template discovery requires exactly one
shield per folder, named after it (`<dir>/<basename>.shield`), with identity
taken from the DT node name. Upstream permits N per folder by TWO different
mechanisms, and bridle uses the second:

- **shield.yml plural form** — names listed explicitly under `shields:`,
  all sharing `dir` = the folder (`list_shields.py` `find_shields_in`). The
  archetype is `adafruit_2_8_tft_touch_v2` + `_nano`: two names, one folder,
  differing by form factor. 45 of 210 upstream shields use it.
- **the legacy fallback** — no shield.yml at all: if `Kconfig.shield`
  exists, EVERY `*.overlay` in the folder becomes a shield whose name is the
  overlay BASENAME. Identity by filename parse, listed nowhere.

**Bridle is entirely in the legacy mode — zero shield.yml files in 19
folders** — so the migration must author shield.yml for every ported shield
regardless. Its `grove_btn` and `grove_led` folders hold 64 overlays each
(32 positions × normal/`_inv`), which is the bridle-64-overlays product
argument the comment sweep deliberately kept. Triage of the remaining
multi-overlay folders is in `bridle-migration.md`; the finding is that
plurality is mostly NOT a gap to implement but a triage to perform, because
each folder decomposes onto an axis we already have or are building.

## 2026-07-29a — board as INVOCATION coordinate; the lift re-attributed; `--boards-for` (Tobi)

Forward-looking exploration, NO queue change. Full record:
`board-as-invocation-coordinate.md`. Headlines:

- **Tobi's reframing: rigs aren't boards — rigs are a topology/assembly of
  SHIELD INSTANCES.** Shield-templates (slice R) left the *instance* spot
  empty; the rig fills it. Ontology §7's lift `a → [a]` was misattributed:
  it is shield-instance → rig, NOT board → rig. The build coordinate
  factors as a PRODUCT `board × rig` (`west build --board X --rig Y`),
  replacing containment ("the rig owns the board"). §7 rewrite is a
  deliberate future step; two identity laws replace the old one: empty rig
  ≡ plain board (saferail 11 unchanged), **singleton rig ≡ upstream
  shield** (new — upstream `--shield` is the degenerate rig).
- **Twister needs the product**: `testcase.yaml extra_args: -DRIG=…` with
  twister's own platform = zero twister changes — IMPOSSIBLE under the
  current exclusivity FATAL (`boards.cmake:97`), since twister always
  supplies the platform. Prerequisite, not convenience.
- **Socket map resolution**: the unnamed PROVIDER RULE (a socket is named
  by its provider; `mux_1.ch0` was the tell). Board-provided names go
  board-independent via CONVENTIONAL per-type labels (`ard`,
  `mikrobus_1..n`); DT multi-label makes conformance ADDITIVE (alias, no
  renames); lintable. `loader_yml.py:1028` is already lookup-else-identity,
  so conforming boards need no map. Unique-by-type inference only as
  degenerate sugar (makes the singleton law hold). Per-board binding files
  only if a real case arrives.
- **`--boards-for <rig>` (Tobi: extremely useful, ship it)** — enumeration
  returns as a QUERY: census board rig-extensions' typed socket labels
  against the rig's requirements. Upstream has wanted exactly this for
  years (hand-maintained twister `platform_allow` is the void it fills);
  inverse `--rigs-for <board>` is the same census backwards.
- **Code map**: board identity enters at two doors only (boards.cmake
  step 1 via list_rigs; loader `_resolve_board`); analyzer/emitter and the
  whole downstream are already board-parametric (`--board-dts` threaded).
  Change surface is small; the hard residue is design-level (labels
  convention, per-board fragments).
- **R2 must read §6 of the exploration doc**: SocketBinding as a value,
  ONE application seam outside the delta engine, map diagnostics isolated
  — then the eventual open-board move is a constructor swap and the
  differential goldens never notice.
