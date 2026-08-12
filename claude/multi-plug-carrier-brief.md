# Multi-plug carriers, slice 2 — re-export from more than one parent

**Status:** briefed 2026-08-12, ready to dispatch. Slice 2 of the
multi-plug thread (`multi-plug-shield-design.md` §0; slice 1 landed as
`99fd59c`/`b2b5630`): a multi-plug carrier may now DECLARE exposed
sockets, and one exposed socket composes from SEVERAL named parents —
the original motivating hardware (a carrier plugging two of a
mainboard's connectors and re-exporting the combined connections
through a third).

## 1. The rulings this slice implements

1. **(Tobi, 2026-08-12) An exposed socket MAY combine same-kind buses
   from different parents**, spelled with the multi-bus qualified-role
   vocabulary — the role names belong to the EXPOSED socket's own
   connector type (the 2026-08-09 multi-bus ownership ruling, applied
   unchanged one level up). The multi-bus brief's §4 flagged "a carrier
   exposing a multi-bus socket" as unverified; this slice makes it real.
2. **(Tobi, 2026-08-12) Corpus = a span-carrier on quail**: plugs two
   mikrobus sockets, re-exports ONE ordinary `socket,mikrobus` socket
   with MIXED parents (positions and buses drawn from both), plus an
   existing click plugged on it. The combined-two-SPI exposed socket is
   FIXTURE-ONLY, reusing the existing `fixture-multibus` connector type
   (it already declares `socket,spi-sensors`/`socket,spi-motors`).
3. Slot names, per-reference granularity, slot-silent rendering for
   single-plug shields: all carried from slice 1 unchanged. Promotion
   stays refused (R4, its own future slice).

## 2. The grammar — one refusal lifted, zero new author syntax again

**Lifted:** slice 1's parse-time refusal "a plural shield may not
declare an exposed socket" (`shields.py:310-321`). Its test dies in the
same change (mechanism and tests together).

**Already in the syntax, currently discarded:** an exposed socket's
`gpio-map` rows each carry a parent PHANDLE (`shields.py:557-566`), and
each `socket,<bus>` property targets a node — on a plural carrier those
phandles name WHICH plug. Exactly slice 1's GpioRef discovery: widen
"parent must be the carrier's plug" to "one of the carrier's plugs" and
RECORD the slot, per row and per bus.

**The one real widening:** `shields.py:59`'s `_BUS_PROPS` fixed 3-name
dict must become the qualified pattern match (`socket,(i2c|spi|uart)
(-\w+)?`) — its own comment block (`shields.py:53-58`) names itself as
the not-yet path, and `board_edt.py`'s multi-bus widening is the exact
mirror to follow. The child-side bus NAME (the exposed socket's
vocabulary, validated against ITS connector type's declared roles,
exact-match, no fallback) is independent of the parent-side name:

```dts
/* on a plural carrier with plugs left / right */
combined {
	compatible = "socket,fixture-multibus";
	#gpio-cells = <2>;
	gpio-map = <MB_CS  0 &left_plug  SOME_LEFT_POS  0>,
		   <MB_INT 0 &right_plug SOME_RIGHT_POS 0>;   /* mixed parents */
	socket,spi-sensors = <&left_plug>;    /* left parent's SPI */
	socket,spi-motors  = <&right_plug>;   /* right parent's SPI */
};
```

**Pass-through parent-bus selection (driver decision, flag to veto):**
a pass-through selects the named parent's bus of the same KIND. If that
parent socket offers MORE than one bus of that kind (a multi-bus PARENT
— possible only with fixture connectors today), that is a loud
"ambiguous, not supported yet" error this slice, not a guess. Also
driver-decided: per-bus cs-pool overrides on an exposed socket adopt the
board side's qualified spelling (`socket,<qualified>-cs-pool`), with
bare `socket,cs-pool` keeping today's meaning untouched.

## 3. The model

- `ExposedSocket.gpio_map: Dict[int, Tuple[int, int]]` →
  `Dict[int, Tuple[str, int, int]]` — (parent SLOT, parent position,
  flags). Single-plug carriers normalize to slot `"plug"`.
- `ExposedSocket.buses` markers: `"plug"` → `("plug", slot)`. The
  scope-creating marker `("scope", dev-label)` is UNCHANGED — the scope
  root is a device, and a device already carries its own slot
  (`Device.plug`); verify this rather than assuming it (§5).
- `ExposedSocket.cs_pool` — per-qualified-bus overrides per §2; keep the
  bare override's behavior byte-identical for existing content.
- `compose_socket` takes `parents: Dict[str, BoardSocket]` (slot →
  resolved parent) instead of one `parent`. Each gpio row resolves
  through ITS slot's parent; each pass-through bus through its named
  parent. Nexus rows get a PER-ROW parent nexus label — the model and
  the emitter are ALREADY per-row (`BoardSocket.nexus_rows` is
  `(child_pos, parent_nexus_label, parent_pos)`; `overlay.py:411-413`
  renders each row's own `&{parent}`); only the constructor stamps one
  label today.
- `BoardSocket.parent: Optional[BoardSocket]` → `parents:
  Dict[str, BoardSocket]` (empty for a board socket). Exactly ONE
  consumer exists: `overlay.py:398`'s transitive `visit(sock.parent)` —
  it visits all parents instead.
- **The composed socket's `path`** (scope identity for net keys):
  single-parent keeps today's `f"{parent.path}/{exposed.name}"`
  BYTE-IDENTICAL (golden safety); a multi-parent composition uses the
  socket_label (the `<carrier>.<exposed>` reference string — unique per
  carrier instance, deterministic). Driver decision; the constraint is
  only single-parent stability + multi-parent uniqueness.
- `resolve_one`'s carrier path (`analyzer/sockets.py:260-291`): resolve
  ALL the carrier's slots (its `shield.plugs` keys) before composing;
  any slot failing to resolve fails the composition (skip-don't-abort,
  as today). The slice-1 comment block explaining why only `"plug"` is
  asked for dies with the restriction it documents.

## 4. Semantics

- **Slot-silence carries over:** a SINGLE-plug carrier's composition,
  diagnostics, and artifacts are byte-identical to today. The
  `phys-subset` pass-through message (`sockets.py`, "its parent socket
  '<label>' offers no socket,<kind>") names the parent SLOT only when
  the carrier is plural.
- Mating/subset/stackability for the carrier itself: slice 1's per-slot
  machinery, unchanged. The CONSUMER of a composed socket needs no new
  logic anywhere: it sees one `BoardSocket` whose `buses` keys are the
  child-side (possibly qualified) names its own devices already spell —
  `subset_gaps`, CS scoping by `bus.path`, address allocation, and the
  emitter all work on that value exactly as before.
- Chains recurse: a consumer slot ref naming an exposed socket of a
  carrier that itself plugs another carrier's exposed socket — the
  existing depth-first resolution + cycle guard, now over (instance,
  slot). No new mechanism; one fixture proves it still holds (§7).

## 5. Scope — the trace, verified 2026-08-12 (re-verify, don't trust)

- `scripts/rigc/shields.py` — `_parse_exposed` (~541-600): plug-map
  parameter instead of the single plug; per-row slot recording; the
  `_BUS_PROPS` pattern widening + validation of qualified names against
  the EXPOSED type's connector binding; qualified cs-pool parsing. The
  §6-refusal branch at 310-321 goes, its test with it.
- `scripts/rigc/model.py` — §3's `ExposedSocket`/`BoardSocket` shapes.
- `scripts/rigc/analyzer/sockets.py` — `compose_socket` (67-125) multi-
  parent per §3; `resolve_one`'s carrier branch (260-291) resolves all
  slots; the pass-through kind-ambiguity refusal; slot-qualified
  phys-subset wording for plural carriers only.
- `scripts/rigc/emitter/overlay.py:398` — `visit` walks `parents`.
- **Verify, expected UNCHANGED:** the scope-creating (mux) path end to
  end on a plural carrier — root device sits on one slot's bus, channel
  labels don't involve parents; `registry.py`/`board_edt.py`/
  `board_census.py` (board-side, untouched); every consumer BELOW the
  resolution map (cs/addresses/gpio/wires/emitters) — they read composed
  `BoardSocket` values through the slice-1 accessors and must need
  nothing.
- Modules this change INVALIDATES (prediction — run the suite, the
  failures are the census): `tests/unit/analyzer/test_composer.py` and
  `tests/unit/emitter/test_composer.py` (every hand-built
  `compose_socket(parent=...)` call and every `ExposedSocket` with
  2-tuple gpio_map values), `test_shields.py`'s exposed-socket parses,
  `test_sockets.py`'s carrier cases, possibly `test_overlay.py`'s synth-
  nexus tests.

## 6. Explicitly OUT OF SCOPE

- **Promotion** of any multi-plug shield (R4) — the slice-1 refusal
  stands and covers carriers too.
- A pass-through from a parent offering several same-kind buses (§2's
  ambiguity refusal — its own slice if ever needed).
- Any change to how a SINGLE-plug carrier composes (byte-identical is a
  criterion, not an aspiration).
- New production connector types. The corpus carrier re-exports plain
  `socket,mikrobus`; the combined-bus case lives on the existing
  fixture-multibus type.

## 7. Corpus and fixtures

**Corpus:** new shield `boards/shields/mikrobus_span_adapter/` (name
final at implementation) — plural (left/right, both mikrobus), pure
copper like `arduino_uno_click` (no devices of its own), exposing one
`socket,mikrobus`: SPI + CS position from the LEFT parent, INT (and
I2C) from the RIGHT parent. New corpus rig on quail: the adapter on
`quail_sock2`/`quail_sock3`, with the EXISTING `eth_click` plugged on
the exposed socket — its SPI/CS resolve through the left chain and its
`int-gpios` through a synthesized-nexus row chaining to the RIGHT
parent's nexus. That row is the slice's falsifier: name it in a test
assertion, not just a golden. Wire into `ACCEPT_CASES` + emitted
goldens (hand-authored, verified both ways; `RIGC_REFREEZE=1` is
blocked). `eth_click` itself must be BYTE-UNTOUCHED.

**Fixtures:**
- Combined-SPI: a plural fixture carrier exposing a
  `socket,fixture-multibus` socket, `spi-sensors` from the left parent,
  `spi-motors` from the right; the existing `fixture_spi_sensor`-style
  shields consume it. Negative control (multi-bus brief §5's shape):
  both consumers legally at the SAME cs index — a regression merging
  the two parents' CS namespaces must fail this test and nothing else.
- One chain fixture: a plural carrier whose OWN slot plugs another
  (single-plug) carrier's exposed socket — recursion + cycle guard
  still hold over (instance, slot).
- Rejects, each asserting its own sentence, controls run in-tree:
  gpio-map phandle naming a non-plug node of the shield; a pass-through
  naming a parent whose socket lacks the KIND (slot-qualified
  phys-subset); the same-kind-ambiguous parent refusal; a qualified
  child bus name the exposed type does not declare (exact-match,
  existing `lang-`/`phys-` family — verify which fires and pin it).

## 8. Acceptance criteria

1. **Every existing golden byte-unchanged** — especially the
   `arduino_uno_click` chains (`frdm_eth_nest`, `nucleo_mux_farm`, the
   `frdm_cs_clash` reject) — single-parent composition must be
   byte-identical, including `BoardSocket.path` and nexus output.
2. **The corpus chain falsifier**: eth_click's `int-gpios` row in the
   synthesized nexus chains to the RIGHT parent's nexus while its CS
   chains left — asserted by sentence/line in the new test module.
3. **Combined-SPI negative control** passes and is MUTATION-VERIFIED:
   collapsing `parents` to a single parent must fail it (and the
   corpus falsifier), nothing else.
4. **Refusals of §7 fire on their own sentences.**
5. `test_singleton_identity_law.py`'s derived EXCLUDED set grows by the
   span adapter (multi-plug predicate — no hand-list, no new predicate).
6. The slice-1 accessor grep criterion still holds (no new bare map
   walks in analyzer/emitter).
7. Full gate green (driver-run; floor 88, currently 93).

## 9. Reduced verification contract

Implementor runs mypy + unit + non-build integration + ONE named build
module: the NEW `scripts/rigc/tests/integration/test_multiplug_carrier.py`
(confirm the `@pytest.mark.build` marker exists on the corpus round-trip
before claiming it). Observing modules: the new module (2, 3, 4),
`test_emitted_corpus.py`/`test_resolved_corpus.py` (1 + the new rig),
`test_singleton_identity_law.py` (5), plus §5's invalidated unit
modules. Driver runs the full gate after review. Brief the reviewer to
mutation-check criteria 2/3 (the parents-collapse mutation) and the
qualified-name exact-match (a child bus name the type doesn't declare
must fail on the declaration check, not downstream). Standing rules:
reports are hypotheses; run the callers, don't reason about them; purge
`__pycache__` after mutate-and-restore; no probe artifacts in build dirs.
