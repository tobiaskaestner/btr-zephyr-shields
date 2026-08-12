# Multi-plug shields — a shield mating more than one socket at once

**Status:** design exploration started 2026-08-09; **rulings confirmed
with Tobi 2026-08-12 (§0 below)** — the direction, granularity, and slice
boundaries are now decided; the consumer trace §5 asked for is done and
recorded there. Still NOT a brief: spellings, model shapes, fixtures, and
acceptance criteria remain to be written. This document exists to hold
what's been established so the exploration doesn't have to be re-derived.

## RESUME HERE

**If starting a fresh session for this specific thread:** root it at
`/wrk/z/ws-up/btr-shields` (not the west topdir `/wrk/z/ws-up`) — the
`rig-implementor`/`rig-reviewer` agent types in `.claude/agents/` are only
discovered when the session's own working directory is at or below that
directory, and this exploration will eventually need both once it reaches
brief stage.

**Read, in order:** §0 below (the 2026-08-12 rulings + verified trace —
it supersedes §2's line numbers and answers §5's questions 1 and 2), then
the rest of this document, then `claude/multi-bus-socket-brief.md`
(already implemented, reviewed, fixed, and committed as
`eef9836`/`b9c3be3`) as the METHOD template — not because its content
applies here, but because §2-§4 of that brief is the concrete shape
"verify every path, don't reason abstractly" produces.

**Concrete next action:** DISPATCH. The slice-1 brief exists —
**`claude/multi-plug-shield-brief.md`** (2026-08-12; mating + per-slot
resolution only, re-export and promotion ruled out per §0 R4/R5), and
Tobi ruled the same day that this slice jumps AHEAD of rig-schema.yaml
in the standing queue. §0.5's open spellings are decided in that brief
(driver decisions, flagged for veto there).

## 0. CONFIRMED 2026-08-12 — rulings, direction, and the verified trace

Design session Tobi + driver, 2026-08-12, working over two inline
hypothetical shields (§0.4, confirmed "ok with all three" as matching the
remembered hardware's shape).

### 0.1 Rulings

1. **Slot names are the plug NODE NAMES, and the shield owns them.** A
   shield declares N plug nodes (today exactly one, under the reserved
   name `plug` — `shields.py:81`), each declaring its own connector type.
   Rig side: a `sockets:` map, slot name → board socket label, alongside
   the unchanged single-plug `socket:` (mutually exclusive — and enforce
   that in rigc's own parser from day one, not only jsonschema; the
   `shields:`/`shield:` gap queued in rig-schema.yaml is the debt shape
   not to repeat).
2. **Granularity is PER-REFERENCE, not per-device.** Cross-plug gpio refs
   are real hardware (confirmed against Tobi's remembered boards; both
   §0.4 shields carry one deliberately). A bus DEVICE's bus binds to
   exactly one plug — that half is a fact, not a ruling. Author-facing
   syntax for per-reference slot selection already exists and needs no
   invention: the phandle. `shields.py:292/315` already validates
   `target.path == plug.path` and then DISCARDS which plug matched; the
   change is widening "must be THIS shield's plug" to "one of this
   shield's plugs" and keeping the answer on `GpioRef`.
3. **The model.py freeze is NOT a constraint here** (Tobi: "it served
   well to this point, but we extend strictly beyond rigexp's original
   feature set"). `Shield.plugs` may change shape.
4. **Promotion of a multi-plug shield is a SEPARATE SLICE.** Until then,
   the S4 pattern applies: an asserted exclusion that visibly shrinks.
   (`:socket=` is inherently single-slot; a multi-plug shield promotes
   only where a board offers ALL slot types — its own design question.)
5. **Multi-parent re-export (`compose_socket`) is a SEPARATE SLICE.**
   Slice 1 of this thread is mating + per-slot resolution only, which is
   fixture-provable end-to-end without touching composition.

### 0.2 Direction (agreed shape, not yet a brief)

- **Additive grammar, uniform model.** The authored single-plug form
  stays byte-identical; PLURALITY OF PLUG NODES is the discriminator — no
  `type: multi-socket` marker (a second discriminator alongside the
  visible arity would own a marker↔shape consistency rule forever). The
  loader normalizes a single-plug shield to one default slot, so there is
  ONE pipeline — no parallel single/multi path (the drift `buskind.py`
  exists to kill, not to be reintroduced one level up).
- **A list is the wrong generalization.** `can_span_click` (§0.4) plugs
  TWO SOCKETS OF THE SAME TYPE; positional identity cannot tell them
  apart, only the shield's own names can. Map with named slots — the same
  ruling shape as multi-bus role names (`socket,spi-sensors`, never
  `socket,spi[1]`).
- **Diagnostics render the slot qualifier only for a plural shield**
  (the qualified-bus-name precedent: `spi` bare when there is one,
  role-qualified when there are two). Zero movement in existing
  byte-exact stderr goldens BY CONSTRUCTION — acceptance criterion 1 of
  the eventual brief.

### 0.3 The consumer trace, run 2026-08-12 (supersedes §2's line numbers)

Model anchor points in the current tree: `Shield.plugs: str`
`model.py:159`; `Instance.socket: Optional[str]` `model.py:225`;
`SocketResolution.sockets: Dict[str, BoardSocket]` keyed by bare
`inst.name` `analyzer/sockets.py:48`.

**Every downstream consumer has the same shape** — fetch the instance's
one socket, then loop devices — at 13 sites: `cs.py:129`, `gpio.py:130`,
`addresses.py:143`, `wires.py:66`, `overlay.py:125/170/237`,
`sheet.py:33/62/77/94`, `expectations.py:42/48`. Under ruling 2 the
lookup moves into the per-REFERENCE loop (gpio) / per-BUS-GROUP
(bus devices), through ONE shared accessor (the `buskind.py` precedent is
the anti-drift device). Mechanical, but 13 sites is 13 sites.

**Per-slot logic needed inside `resolve_sockets` itself:**

- Inference (`sockets.py:148`) goes per slot: unique candidate of the
  slot's type resolves silently, zero/many refuses — the existing
  strictness, per slot. §0.4's `can_span_click` kills inference by
  construction (four mikrobus candidates per slot), so its explicit
  `sockets:` map is mandatory, which is correct behavior, not a gap.
- Mating (`sockets.py:254`) per slot.
- Subset exposure (`sockets.py:265`) MUST go per slot: needed buses
  computed from the slot's own bus groups, or a bus needed only by slot
  `aux` would be demanded of slot `main`'s socket.
- The exclusivity/stackability census (`sockets.py:274`) falls out
  naturally once each slot's resolved socket lands in `per_socket`.

**Parser:** bus groups are recognized by NAME against the single ctype's
`bus_proxies` (`shields.py:118`); with two plugs that needs a per-group
plug binding (spelling TBD, §0.4 uses a placeholder property). The plug
node lookup is the literal reserved name (`shields.py:81`).

**Not traced yet (out of slice 1 anyway):** the cmake/promotion surface
(ruled out by R4) and multi-parent composition (R5).

### 0.4 The two confirmatory shields (hypothetical; every spelling is a
placeholder to be designed at brief time)

**Shield A — `acq_bridge`: Arduino R3 + mikroBUS at once.**

```dts
/ {
	shield-templates {
		acq_bridge: acq_bridge {
			/* DELTA 1: no template-level shield,plugs string; N plug
			 * nodes, each declaring its own connector type. The node
			 * names ARE the shield-owned slot names. */
			ard_plug: ard {
				compatible = "shield,plug";
				shield,plugs = "arduino-r3";
				#gpio-cells = <2>;
			};
			mb_plug: mb {
				compatible = "shield,plug";
				shield,plugs = "mikrobus";
				#gpio-cells = <2>;
			};

			/* DELTA 2: both plug types offer i2c/spi, so a bus group
			 * must say which plug its bus copper comes from. */
			i2c {
				shield,plug = <&ard_plug>;
				adc_fe: adc_fe {
					compatible = "ti,ads1115";
					drdy-gpios = <&ard_plug ARDUINO_HEADER_R3_D2 GPIO_ACTIVE_LOW>;
				};
			};
			spi {
				shield,plug = <&mb_plug>;
				radio: radio {
					compatible = "semtech,sx1276";
					spi-max-frequency = <8000000>;
					reset-gpios = <&mb_plug MIKROBUS_RST GPIO_ACTIVE_LOW>;
					dio0-gpios  = <&mb_plug MIKROBUS_INT GPIO_ACTIVE_HIGH>;
					/* CROSS-PLUG REF (ruling 2): TX-sync copper to an
					 * Arduino pin. */
					sync-gpios  = <&ard_plug ARDUINO_HEADER_R3_D3 GPIO_ACTIVE_HIGH>;
				};
			};
		};
	};
};
```

```yaml
instances:
  - name: acq
    shield: acq_bridge
    sockets:            # DELTA 3: slot -> board socket label
      ard: nucleo_ard
      mb:  nucleo_mb    # no corpus board hosts both types today
```

On a board offering exactly one socket of each type, both slots resolve
by per-slot inference with no `sockets:` at all.

**Shield B — `can_span_click`: two of quail's four mikroBUS sockets.**
Two plugs of the SAME type — the case that rules out a positional list.

```dts
/ {
	shield-templates {
		can_span_click: can_span_click {
			left_plug: left {
				compatible = "shield,plug";
				shield,plugs = "mikrobus";
				#gpio-cells = <2>;
			};
			right_plug: right {
				compatible = "shield,plug";
				shield,plugs = "mikrobus";
				#gpio-cells = <2>;
			};

			/* Two bus groups of the SAME kind — Device.bus's bare kind
			 * string collides here; only the plug binding disambiguates. */
			spi {
				shield,plug = <&left_plug>;
				can0: can0 {
					compatible = "microchip,mcp2515";
					spi-max-frequency = <10000000>;
					/* CROSS-PLUG REF: INT is copper on the RIGHT socket */
					int-gpios = <&right_plug MIKROBUS_INT GPIO_ACTIVE_LOW>;
				};
			};
			spi2 {
				shield,plug = <&right_plug>;
				log_flash: log_flash {
					compatible = "jedec,spi-nor";
					spi-max-frequency = <20000000>;
				};
			};
		};
	};
};
```

```yaml
instances:
  - name: canspan
    shield: can_span_click
    sockets:
      left:  quail_sock2
      right: quail_sock3
```

### 0.5 Still open before a slice-1 brief exists

- Exact spellings: the plug-node compatible, the bus-group→plug binding
  property, the second same-kind bus group's node name (interacts with
  how `Device.bus`'s qualified names are parsed today), the `sockets:`
  key in rig.yml (vs `socket:` mutual exclusion diagnostics).
- Model shapes: `Shield.plugs` map (slot → type), `GpioRef` slot field,
  where the bus group's plug binding lives (`Device`? a bus-group
  entity?), `Instance.sockets` map, `SocketResolution` re-keying (key
  `(inst, slot)` vs nested map — decide WITH the accessor design).
- Fixture plan + golden classification (new fixtures additive; criterion
  1 is zero movement in existing stderr goldens).
- Which of §0.4's shields becomes the corpus example vs fixture-only —
  `can_span_click` on quail is buildable against a REAL board today and
  exercises same-type slots, cross-plug refs, and dead inference at once.

## 1. The motivating scenario

A real-world topology (Tobi's own past hardware): a carrier shield that
plugs into TWO of a mainboard's connectors SIMULTANEOUSLY — e.g. both the
Arduino header and the mikroBUS header at once — and re-exports the
combined available connections through a third connector of its own.

This is distinct from the multi-bus-socket work (`multi-bus-socket-brief.md`,
landed and committed since this document was started): that gap is "one
socket offers more than one bus of the same kind." This gap is "one shield
instance mates more than one socket, of possibly different connector
types, at the same time." Different axis, and — verified below — a
structurally bigger one.

## 2. The gap, verified against the actual code (2026-08-09)

The 1:1 shield↔socket assumption is baked in at three separate points, not
one:

1. **`Shield.plugs: str`** (`model.py:149`) — exactly one connector type per
   shield template. No way to declare two.
2. **`Instance.socket: Optional[str]`** (`model.py:215`) — exactly one
   socket reference per instance.
3. **`SocketResolution.sockets: Dict[str, BoardSocket]`**, keyed by
   `inst.name` ALONE (`analyzer/sockets.py:47`; every assignment site —
   `resolve_one`, lines 185/191/205/242 — stores exactly one `BoardSocket`
   per instance name). The entire downstream allocation pipeline (CS,
   addresses, GPIO, emission) is built on "one instance resolves to one
   socket."

And no device-level reference carries a socket-slot identifier at all:
`GpioRef` (`model.py:58-71`) resolves a position against "the shield's one
socket" implicitly — there is no field saying WHICH of several plugs a
given pin comes from, because there has never been more than one to choose
from.

**The re-export half already exists, partially.** A carrier plugging into
one parent and exposing a synthesized socket onward is exactly
`ExposedSocket`/`compose_socket` (`analyzer/sockets.py:67-116`). What's
missing is the MATING half: `compose_socket` takes a single `parent:
BoardSocket` (line 68) — carrier composition today is a strict tree, one
parent per carrier, never a shield with two simultaneous parents of
possibly different connector types.

Checked and confirmed empty: no existing design doc (`design-log.md`,
`parked.md`, `rig-playbook.md`, both board-coordinate briefs) records this
scenario as a known gap. It is new as of this session.

## 3. Why this is bigger than the multi-bus-socket case, not just similar

The multi-bus design (a named-slot pattern: `socket,spi-sensors` /
`socket,spi-motors`) turned out to be a bounded, mostly-mechanical slice
because the allocation CORE (`analyzer/cs.py`/`analyzer/addresses.py`) was
already scoped by `bus.path` — a real per-bus identity — rather than by
kind string, so widening the KEY SPACE at the edges was enough; the middle
of the pipeline didn't need to change.

This gap is different in KIND: it changes the fundamental
Shield:Socket relationship from 1:1 to 1:N, which plausibly cascades
through every layer that currently keys off "the instance's one socket" —
not yet verified how far. Candidate structural shape, sketched, NOT
committed to:

- `Shield.plugs` becomes a mapping of slot-name -> connector-type (e.g.
  `{"main": "arduino-r3", "aux": "mikrobus"}`) instead of a bare string.
- Every position/GPIO/bus reference on the shield's devices needs a new
  axis saying which slot it draws from — same SHAPE of problem as the
  bus-specializer question, one level up (per-device slot selection
  instead of per-device bus-kind selection).
- `Instance.socket` becomes a mapping (slot-name -> board-socket-label)
  rather than one optional string.
- `SocketResolution.sockets` needs re-keying (by `(inst.name, slot)` or
  similar) — NOT YET TRACED how far this propagates into `cs.py`/
  `addresses.py`/emitter call sites that currently do `sockets.get(inst.name)`.
- The re-export side: `compose_socket`/`ExposedSocket` would need to pull
  from MULTIPLE named parents when building an exposed socket's
  `gpio_map`/`buses` — some exposed positions map to slot "main", others
  to slot "aux". Whether `ExposedSocket`'s existing pass-through/
  scope-creation markers (`"plug"` / `("scope", label)`) generalize to
  "which parent slot" cleanly, or need a third dimension, is open.

## 4. What's NOT yet done

- Trace whether `cs.py`/`addresses.py`'s allocation core survives a
  multi-socket instance the way it survived multi-bus (the multi-bus case
  was a pleasant surprise BECAUSE it was already scoped by `bus.path`;
  this case's core loop keys by `inst.name` via `sockets.get(inst.name)` —
  first look suggests this does NOT survive unchanged, needs verification
  file-by-file the way the multi-bus trace was done).
- Whether a device can reference pins from BOTH plug slots at once (finer
  grain than "this whole device belongs to slot X"), or whether the
  simpler form — every device belongs to exactly one of the shield's named
  slots — covers the real scenario. The motivating hardware
  (re-export-to-a-third-connector) suggests the SHIELD's own re-export
  logic needs both slots, but individual DEVICES on it plausibly do not —
  worth confirming against the real remembered hardware before assuming.
- Naming/ownership question analogous to the multi-bus ruling: do plug-slot
  names belong to the SHIELD (since a shield's own template defines which
  of its pins go where) rather than the connector type? Likely yes — this
  is the shield's own physical fact, not something a connector type
  imposes — but not yet stated as a ruling.
- No fixture, no acceptance criteria, no scope trace of production files
  comparable to the multi-bus brief's §4. This document is pre-brief.

## 5. Open questions for next pass

1. Does splitting "which slot a device belongs to" from "which slot the
   carrier's re-export logic draws from" simplify this, or is that a false
   simplification given the real hardware?
2. How far does the `sockets.get(inst.name)` re-keying propagate — this is
   the next concrete trace to run, mirroring how the multi-bus brief's §4
   was built by reading every call site rather than reasoning abstractly.
3. Is there a real fixture-provable slice here? The multi-bus-socket work
   this shared `model.py` territory with (`Shield`, `Instance`,
   `BoardSocket`) has now landed (`eef9836`/`b9c3be3`), so this is
   unblocked — but re-verify §2's citations against the current tree
   first (see RESUME HERE above); `BoardSocket.buses`'s keys and
   `BusRef`'s own fields changed shape in that work.
