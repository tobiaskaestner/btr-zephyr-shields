# Multi-bus sockets — a socket may offer more than one bus of the same kind

**Status:** briefed 2026-08-09, not started. No board or shield in the
corpus needs this today — proved with a new fixture connector type only,
following this project's own precedent for shipping new capability ahead of
real corpus adoption (the i2c_mux scope-creating interposer, cross-module
shield discovery).

## 1. The gap, and the ruling

`dts/bindings/connectors/*.yaml` declares `socket,i2c`/`socket,spi`/
`socket,uart` as `type: phandle` — singular — and `BoardSocket.buses:
Dict[str, BusRef]` (model.py:248) is populated from exactly those three
fixed property names (`board_edt.py:37`'s `_BUS_PROPS`), then consumed by
literal-key lookups (`analyzer/addresses.py:148`, `analyzer/cs.py:134`,
`emitter/overlay.py:221`, `emitter/expectations.py:26,31`). A connector that
genuinely wires out two independent buses of the same kind on one physical
header — two SPI buses is the motivating case — has no representation
today. This is a schema gap before it is a code gap: `type: phandle` cannot
hold two references under one property name; a `phandle-array` would hold
them but only as an unlabelled, order-dependent list.

**Ruling (Tobi, 2026-08-09): the specializer name belongs to the CONNECTOR
TYPE, never the board.** A board wiring a connector type with named buses
inherits those names; it never invents its own. This is the same shape as
every other connector-type-owned fact today — GPIO position numbering, the
default CS pool, stackability — a shield written against a connector type
must be able to rely on that type's vocabulary staying fixed regardless of
which board it ends up plugged into. Named roles (`-sensors`, `-motors`)
read better than ordinals and are not forbidden by this rule — the naming
style is the connector type author's call, made once, same status as any
other fact that type's binding fixes.

## 2. The declaration

A connector type binding names an additional bus of a kind by suffixing the
kind with a role name, still a plain phandle, still optional by absence:

```yaml
socket,spi-sensors:
  type: phandle
  description: SPI controller reachable through this socket, dedicated to sensor peripherals (absent = not offered)
socket,spi-motors:
  type: phandle
  description: SPI controller reachable through this socket, dedicated to motor-control peripherals (absent = not offered)
```

Bare `socket,spi` keeps meaning exactly what it means today — "the/the
primary spi bus" — so every existing connector type and shield is untouched.
A type only grows named variants when it genuinely offers more than one bus
of a kind; nothing requires every bus of a type to be named once one is.

A device on a shield selects a specific bus the same way it selects a bare
kind today, just spelling the qualified name:

```dts
motor_dev: drv8825@0 {
        shield,collect = "drv8825";
        /* bus: "spi-motors" -- authored via whatever field/parse
           already carries Device.bus (shields.py); no new syntax, just
           a wider string domain. */
};
```

`Device.bus` (`model.py:79`) is already `Optional[str]`; it widens from an
implied 3-value enum to an open string with zero type change. A shield
author writes the qualified name once, at template-authoring time, exactly
as `bus: "spi"` is written today — which bus a chip needs is a hardware fact
of the shield's own wiring, not something a rig author overrides per
instance the way `params:`/`invert:` are.

## 3. Matching semantics — exact string, never a fallback

`mating_ok`/`subset_gaps` (`analyzer/sockets.py:52-64`) already operate on
plain strings/sets with no kind-specific logic — `subset_gaps` is `needed -
set(offered)`. A device asking for bare `"spi"` is satisfied only by a
socket offering bare `"spi"`; a device asking for `"spi-sensors"` is
satisfied only by a socket offering exactly `"spi-sensors"`. No fallback, no
guessing between candidates — the same strictness `infer_socket` already
enforces for socket mating itself (`sockets.py:139-175`: *"an implementation
that picks between several reasonable candidates is wrong however sensible
its tie-break looks"*). This needs **zero code change** to `subset_gaps`
itself.

## 4. Scope — VERIFY EVERY PATH, this is a trace not a census

### Binding schema
- New FIXTURE connector type only — no production connector changes this
  slice. Follow whatever precedent fixture-only bindings already use in
  this tree (check before inventing a new location).

### Production
- `scripts/rigc/board_edt.py:37,96-110` — `_BUS_PROPS`'s fixed 3-entry dict
  becomes a pattern match (`socket,(i2c|spi|uart)(-\w+)?`) storing the
  QUALIFIED name as the `buses` dict key.
- **`scripts/rigc/board_census.py:81-99`** — a SEPARATE, deliberately
  duplicated copy of `_BUS_PROPS` plus its own `_BUS_PROP_RE` (text-regex
  scan, not an EDT parse — the module's own docstring already flags the
  duplication as intentional: "two different inputs to the same fact, not
  one shared value to import"). Must widen in lockstep or `--boards-for`
  silently stops recognizing named buses and under-reports conformance for
  any shield needing one. Easy to miss — it is not board_edt.py and does not
  show up searching for `BusRef` construction.
- `scripts/rigc/model.py:237-241` (`BusRef`) — gains `cs_pool:
  Optional[List[int]]` (moved off `BoardSocket` per the 2026-08-09 ruling:
  CS numbering is a fact of a specific bus, not of the socket as a whole).
- `scripts/rigc/model.py:255` (`BoardSocket`) — `cs_pool` field GOES.
- `scripts/rigc/model.py:39-48` (`ConnectorType`) — `cs_pool: List[int]`
  becomes `Dict[str, List[int]]`, keyed the same qualified way (only
  spi-kind buses ever populate it; i2c/uart never read cs_pool at all).
- `scripts/rigc/registry.py:39-47` (`_socket_facts`) — its single
  `socket,cs-pool` schema-default read becomes the same pattern match
  against the raw binding dict, returning `Dict[str, List[int]]`.
- `scripts/rigc/board_edt.py:112-138` — cs_pool parsing becomes the same
  pattern match as buses: `socket,<qualified>-cs-pool` per bus, backfilled
  by edtlib per-property exactly as bare `socket,cs-pool` is today.
- `scripts/rigc/analyzer/cs.py:45-54,131-136,162,175` — `effective_cs_pool`
  takes `bus.cs_pool` / `ctype.cs_pool[qualified_key]` instead of
  `socket.cs_pool` / `ctype.cs_pool`. The two-line filter/lookup (`dev.bus
  != "spi" or "spi" not in socket.buses` / `socket.buses["spi"]`) becomes
  `dev.bus not in socket.buses` / `socket.buses[dev.bus]`. **The grouping
  core beneath it — `scopes.setdefault(bus.path, [])`, everything through
  `allocate_cs`'s exhaustion/collision logic — is UNCHANGED**: it already
  scopes by `bus.path` (a real per-bus identity), never by kind string, so
  two independent SPI buses on one socket already get independent CS
  scopes for free once the two-line swap lands.
- `scripts/rigc/analyzer/addresses.py:145-148` — same two-line swap, i2c
  side; `allocate_addresses`/`_allocate_scope` unchanged for the identical
  reason (already grouped by `bus.path`).
- `scripts/rigc/emitter/overlay.py:221`, `emitter/expectations.py:26,31` —
  same two-line-shape swap from a literal `"i2c"`/`"spi"` to `dev.bus`.

### Explicitly OUT OF SCOPE this slice
- **Carrier/mux composition exposing a multi-bus socket**
  (`ExposedSocket.cs_pool`, `analyzer/sockets.py:86-116`'s `compose_socket`).
  `exposed.buses: Dict[str, object]` is already keyed openly and may already
  have the right SHAPE, but this is unverified and untested by this slice's
  fixture — a carrier passing through or scope-creating TWO named SPI buses
  through one exposed socket is a compound of this feature and S6/S8's
  machinery. Flag rather than assume it falls out for free.
- Any REAL production connector type growing named variants — this slice
  proves the mechanism with a fixture only.
- Any CLI/instance-level surface for selecting a bus. Not asked for;
  `Device.bus` is authored once by the shield template (§2).

## 5. The acceptance criterion

A fixture connector type with two named SPI buses (`socket,spi-sensors`,
`socket,spi-motors`), each with its own binding-default `cs_pool`, mated by
two fixture shields (one `bus: "spi-sensors"`, one `bus: "spi-motors"`) on
the SAME fixture board socket instance.

- **Accept case**: both shields build; CS allocation is independent per
  bus. Assert the two devices may legally share the SAME cs-pool INDEX
  without collision, since they sit on different physical buses — the
  negative control this project's discipline demands (post-cutover-backlog
  §G: *"every comparator guard needs a named negative control,
  mutation-tested"*). Without this assertion, a regression that
  accidentally merges the two buses' CS namespaces back into one would
  still pass every other check.
- **Reject case**: a fixture shield declaring `bus: "spi-unknown-name"`
  against that same socket gets the EXISTING `phys-subset` gap diagnostic —
  confirms exact-match, not a guess, with a genuinely novel string rather
  than a name that happens to coincide with something else in the corpus.

`lotus_buttons`/every other existing golden: byte-unchanged. This slice adds
new fixtures/goldens only; nothing existing reads a qualified bus name.

## 6. Reduced verification contract

New tests only. Observe: wherever `board_edt.py`'s bus-parsing has its unit
home (widen `_BUS_PROPS` coverage) and its `board_census.py` sibling, the CS
allocation unit tests (the negative-control independence case above), one
new build-marked integration test for the fixture connector's expand+build
round-trip. No existing golden should move — if one does, something is
wrong and it must NOT be refrozen without understanding why.

## 7. Open, deliberately unresolved

Whether a real board ever needs this is unknown — nothing in the corpus
motivates it today. This brief exists so the mechanism is ready, verified,
and cheap to extend to a real connector type the day one shows up, without
re-deriving the scope trace from scratch.
