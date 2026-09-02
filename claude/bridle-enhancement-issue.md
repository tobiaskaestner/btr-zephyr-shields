# [FER] Rigs: describe multi-module hardware assemblies as a versioned artifact, not as shield overlays

<!--
Body for a bridle issue filed from .github/ISSUE_TEMPLATE/enhancement.md
  title:     [FER] Rigs: describe multi-module hardware assemblies as a versioned artifact, not as shield overlays
  labels:    enhancement
  assignees: tobiaskaestner, rexut
Everything below the rule is the issue body.
-->

---

**Is your enhancement proposal related to a problem? Please describe.**

Zephyr's shield mechanism cannot faithfully express a hardware
assembly: which module sits in which socket, how many of them there are, and what
resources they jointly consume. Bridle inherits that limitation, works around it
by hand.

Three properties of devicetree and the shield mechanism cause it. All three were
checked against a real tree — `zephyr-rigs` @ `v4.4.0-8558-g640b25d911f`,
2026-07-17, and each was reproduced with a `--cmake-only`
baseline build.

**1. DT conflates type and instance; shields are forced singletons.**
DT has a type/instance split at the *device* level only (binding = type, node =
instance). There is no type concept for an *assembly* of nodes. A shield overlay
is a reusable description forced into instance space — concrete paths, globally
unique labels, concrete connector labels — and overlay application is
merge-by-path. So applying a shield twice merges into the same nodes.

> **Verified:** `-DSHIELD="adafruit_data_logger;adafruit_data_logger"` exits 0
> with **zero diagnostics** and produces a `zephyr.dts` **byte-identical** to the
> single-shield build. The user asked for two SD cards and silently got one.

Shield authors hand-perform the namespacing a type/instance mechanism would
provide: `adafruit_data_logger.overlay` suffixes every label by hand —
`rtc0_adafruit_data_logger`, `sdhc0_adafruit_data_logger`,
`led_1__adafruit_data_logger` (sic! double-underscore typo included).

**2. Connectors have no DT representation beyond convention.**
GPIO routing through connectors *is* first-class, via `gpio-map` nexus nodes, and
it composes recursively — that part works and is worth preserving. Beyond GPIO
there is nothing: `arduino_i2c`, `arduino_spi`, `mikrobus_i2c` are label
conventions aliasing SoC bus nodes: 
* no declaration of what a connector carries,
* no check that a module's needs match the socket
* no connector identity ("socket 2 of 4").

> **Verified:** two in-tree shields are mutually
> incompatible. `mikroe_temp_hum_click` targets numbered `&mikrobus_1_i2c`;
> `arduino_uno_click` exports unnumbered `&mikrobus_i2c` — hard parse error,
> `undefined node label 'mikrobus_1_i2c'`. 
> The Arduino convention is likewise fragile: the same adapter fails on `nucleo_f401re` with
> `undefined node label 'arduino_serial'`.

Two further consequences, in-tree today:

- **Socket type is a comment.** `maker_pi_rp2040`'s seven Grove sockets encode
  UART/I2C/analog only as `/* SCL */`-style comments, and the board defines no
  Grove bus labels. Upstream ships **zero** Grove module shields — a seven-socket
  connector standard with an empty attachment ecosystem. Sockets 5 and 6
  physically share `gpio0 26`.
- **The hand-rolled struct.** `mikroe_quail.dts:335-365` enumerates the
  socket × resource product as a 16-label matrix
  (`mikrobus_<N>_{adc,i2c,spi,uart}`) — a connector *type* emulated by manual
  enumeration.

**3. Composition breaks on parent-owned arrays.**
DTS merge replaces property values wholesale; there is no append. Four in-tree
Arduino SPI shields each write the entire `cs-gpios` array, three claiming D10
with `reg = <0>` (`adafruit_data_logger:39`, `adafruit_winc1500:11`,
`link_board_eth:11`, `buydisplay_2_8_tft_touch_arduino:45`). Long known as
[zephyr#52948](https://github.com/zephyrproject-rtos/zephyr/issues/52948).

> **Verified:** stacking the Data Logger and WINC1500 shields exits 0 with
> exactly **one** warning (`unique_unit_address_if_enabled` on `sdhc@0` vs
> `winc1500@0`). The `cs-gpios` clobber — which silently changes CS polarity from
> `GPIO_ACTIVE_LOW` to `0` depending on shield *order on the command line* — and
> the double-booking of pin D7 by two interrupts produce **no diagnostic at
> all**. One ignorable warning, then a successfully generated broken
> configuration.

More importantly: a SPI child's `reg` must equal its index
in the parent's `cs-gpios` array, so composing two SPI modules is **resource
allocation**, not concatenation. No textual mechanism — CPP, or an append
operator — can do it. It needs a pass with whole-tree knowledge.

---

**What this costs bridle today.** Bridle is where the upstream gap is most
visible, because bridle owns the hardware that stresses it — **Cytron Maker Pi
RP2040** (seven Grove sockets), **Seeeduino Lotus** — and ships the Grove module
shields upstream does not have. With no way to make "which socket" a parameter,
the answer gets enumerated by hand. `boards/shields/grove*` is **229 overlay
files** for four logical modules:

| shield | overlays | plus |
|---|---|---|
| `grove` | 98 | `Kconfig.shield`, `Kconfig.defconfig` |
| `grove_btn` | 64 | 68-line `Kconfig.shield`, 32-entry `Kconfig.defconfig` |
| `grove_led` | 64 | same shape |
| `grove_sens` | 3 | same shape |

`grove_btn` is one button. Its 64 overlays are the product of two axes that
should be parameters — socket position (`d0`…`d31`) and polarity (`_inv`) —
written out one file at a time. Adding a socket to a board, or a third axis to a
module, multiplies the file count again.

This is not an authoring habit to be tidied up; it is the only expression the
upstream model allows, and it is a faithful, working realization of Grove
support. It is also the concrete price tag on defect 1 and defect 2 above — and
it only covers the cases that *can* be pre-written. Shared-bus CS allocation,
nested carriers and cross-module wiring cannot be enumerated in advance at all.

**Describe the solution you'd like**

A **rig**: a build-system entity peer to boards and shields, describing a whole
hardware assembly as a versioned, reviewable artifact instead of a command line
plus a pile of overlays. The defining asymmetry — a shield never builds without a
board;
The key features this proposal seeks to integrate are:

- **Typed connector sockets.** A board declares sockets as real nodes with a
  connector *type* (`socket,grove`, `socket,mikrobus`, `socket,arduino-r3`,
  `socket,i2c-port`) carrying machine-readable schema plus a `plug,*` contract —
  what positions exist, which bus proxies they reach, which CS slots are
  available. Attachment becomes a structural match, checked at expansion, instead
  of a label coincidence. This generalizes the one mechanism upstream already got
  right (`gpio-map`) from pins to buses and slots. *Addresses defect 2.*
- **Explicit, countable instantiation.** A rig names modules and the socket each
  occupies. N instances yield N namespaced subtrees — or a hard error *Addresses defect 1.*
- **Per-instance parameters.** The two axes bridle currently spells out as
  filenames — socket placement and polarity (`invert:`) — become instantiation
  parameters.
- **Global allocation.** The expander assigns CS indices, appends `cs-gpios`
  entries and rewrites child `reg` across every module on a bus. *Addresses
  defect 3.*
- **Claim checking and realizability.** Every connector-routed signal a module
  uses is a claimed resource; two claims on one resource is an expansion-time
  error, not a runtime surprise. Modules declare address capabilities (fixed vs.
  selectable, and how), so impossible topologies are rejected with a
  physical-level explanation.
- **Order independence.** Shield order on the command line must not change
  meaning.

Measured effect on bridle's own hardware, from the trial port of `grove_btn` /
`grove_led` onto Seeeduino Lotus: **64 overlays + 96 lines of Kconfig became one
shield plus one line per module.**

This FER should be split across a couple of PRs that aim to land in bridle:

- `rigc`, a new devicetree transpiler — built on dtlib/edtlib it is basically a 
  tree transform over syntactically valid DTS. 
- `west rigs`, and CMake integration (a rig resolves through `boards.cmake`
  and `shields.cmake` forks, so a bare `cmake -DRIG=<name>` works with west
  absent).
- documentation and a first set of 'migrated' connectors, boards and shields 
  of bridle first

**Why bridle first, and what that implies.** The defect being fixed is upstream
Zephyr's, and upstream is where this ultimately belongs — however, giving this some time
to mature downstream would allow us to bulletproof and debug it properly before upstreaming this
some time next year.


Two design constraints important to this FER: 

1. **The design stays deliberately upstreamable.** No DTS dialect fork, no
   parser of our own, no bespoke tooling requirement — a tree transform over
   valid DTS, and CLI compatibility with the shape upstream's own RFC proposed.
   Anything that would be unlandable upstream should be treated as a design bug
   here, not a local convenience.
2. **The upstream evidence above travels with the feature.** The verified
   scenario catalogue is not decoration for this issue; it is the case the
   eventual upstream proposal rests on, and the earlier attempt (below) died
   partly for want of one. It should be kept reproducible and re-verified as
   upstream moves.

The prior work this FER is based on, has got its own repository which holds 
a lot more integration tests which are not intended to be moved across into the bridle repo.
Instead the proposal is to keep these test suites in this repo and make that repo 
an additional zephyr module bridle pulls in via west.

**Describe alternatives you've considered**

**Upstream RFC #82889 / PR #82825 — the closest prior attempt, and dead.**
[RFC #82889](https://github.com/zephyrproject-rtos/zephyr/issues/82889) proposed
`<shield>[@<index>][:<option>{=<value>}]` with CPP-parameterized overlays and
build-generated derived overlays. Opened 2024-12-12, never left Architecture
Review; its implementation
[PR #82825](https://github.com/zephyrproject-rtos/zephyr/pull/82825) closed
**unmerged** 2026-02-27 after repeated stale cycles with no substantive
maintainer review. Capability gaps against the defects above:

| Capability | RFC #82889 |
|---|---|
| Topology in a versioned artifact | no — it lives on the `west build` command line |
| Label namespacing per instance | manual (token-paste `SHIELD_DERIVED_NAME` into every label) |
| Phandle rewiring to per-instance nodes | no |
| Cross-instance references | no |
| Nested composition (carrier exporting sockets) | no |
| Computed per-instance values (CS index, address) | no |
| Connector realization | only via pre-existing board nexus labels |

It would not have fixed defect 3 at all. Its CLI UX (`shield@index:opt=val`) is
still worth staying compatible with, and its two-year death is itself a data
point: the upstream case needs to be stronger and already implemented, which is
precisely what maturing in bridle buys.

**Keep enumerating overlays by hand.** The status quo: 229 files and growing
multiplicatively per new socket, board or module axis — and silent on every
defect-3 case, which cannot be pre-written.

**A `+=` append operator for DT properties.** Insufficient. Appending a second
`cs-gpios` entry still leaves both children at `reg = <0>`; correctness requires
re-addressing children globally, which is allocation, not text.

**A new DTS dialect** (this project's own original spec, `/dts-v1-zephyr-ext/`).
Rejected early: parser fork, no editor or `dtc` tooling on sources, bespoke error
reporting, near-zero upstreamability. The hard problem — namespacing, phandle
rewiring, allocation — is a *tree* transform, not a *language* transform.

**Additional context**

*Provenance.* The failure modes above come from a scenario catalogue (S1–S8,
`claude/rig-playbook.md`) with a Graphviz diagram per scenario, and from the
premise verification in `claude/design-log.md`. Every claim quoted here is from a
scenario grounded in real in-tree hardware and actually built; S5, S7 and S8 use
hypothetical modules and are deliberately not cited.

*Reproducing the upstream baselines.* Each scenario has a `--cmake-only` baseline
under `build-rig/upstream/S<n>` with its full configure log:

```sh
ZEPHYR_BASE=<zephyr tree> west build -b <board> \
  -d build-rig/upstream/S<n> samples/hello_world --cmake-only -- "-DSHIELD=..."
```

*Freshness.* The upstream behaviour above was verified on **2026-07-17** against
`v4.4.0-8558-g640b25d911f`. Re-run the S2/S3/S6 baselines against current
upstream before treating any of it as current — and again before the upstream
proposal is written.
