# Multi-plug shields, slice 1 — a shield mates more than one socket at once

**Status:** briefed 2026-08-12, ready to dispatch. Implements the rulings
recorded in `multi-plug-shield-design.md` §0 (Tobi, 2026-08-12) — read
that §0 first; this brief does not restate its reasoning, only its
consequences. **Slice 1 is MATING + PER-SLOT RESOLUTION ONLY**: promotion
of a multi-plug shield (ruling R4) and multi-parent re-export through
`compose_socket` (ruling R5) are each their own later slice and are
refused loudly here, never silently mishandled.

Queue note: Tobi ruled 2026-08-12 that this slice jumps AHEAD of
rig-schema.yaml in the standing queue.

## 1. The rulings this slice implements

1. **Slot names are the plug NODE NAMES, shield-owned.** N plug nodes per
   shield, each declaring its own connector type; rig side names slots in
   a `sockets:` map.
2. **Granularity is PER-REFERENCE.** A gpio/pwm/adc ref names its plug by
   phandle (syntax that already exists — `shields.py:292/315` validates
   the phandle against THE plug today and then discards which one). A bus
   DEVICE's bus binds to exactly one plug.
3. The model.py freeze does not bind — `Shield.plugs` changes shape.
4. Promotion: separate slice. Refused with its own sentence (§6).
5. Re-export from a multi-plug shield: separate slice. Refused (§6).

Direction (design doc §0.2): **additive grammar, uniform model**. The
single-plug authored form stays byte-identical; plurality of plug nodes
is the ONLY discriminator; the loader normalizes single-plug to one
default slot so there is ONE pipeline. Diagnostics and emitted artifacts
render a slot qualifier ONLY for a shield with more than one slot —
which is what makes acceptance criterion 1 (zero movement in every
existing golden) hold by construction.

## 2. The authored grammar

Two forms, discriminated by the template-level `shield,plugs` property.
Spellings below are DRIVER-DECIDED (not Tobi-ruled) — flag any change of
heart to the driver before implementing something different.

**Single form — byte-identical to today, no migration, ever:**
`shield,plugs = "<type>"` on the template node + the reserved `plug`
child (`shields.py:41,81`). Internally this becomes slot `"plug"` — the
node's own literal name, so the default slot name is not an invention.

**Plural form — template-level `shield,plugs` ABSENT; instead N plug
nodes**, recognized by `compatible = "shield,plug"`, each carrying its
own `shield,plugs = "<type>"` and `#gpio-cells = <2>` (and other
`#<fn>-cells` as needed). The plug node's NAME is the slot name; its
LABEL is what refs target:

```dts
can_span_click: can_span_click {
	left_plug: left {
		compatible = "shield,plug";
		shield,plugs = "mikrobus";
		#gpio-cells = <2>;

		/* Bus groups NEST under their plug in the plural form.
		 * This is the plug binding — structural, no new property —
		 * and it dissolves the sibling-name collision two same-kind
		 * buses would otherwise have (dtlib requires unique sibling
		 * names, so two top-level `spi` groups cannot exist). */
		spi {
			can0: can0 {
				compatible = "microchip,mcp2515";
				spi-max-frequency = <10000000>;
				/* CROSS-PLUG REF (ruling 2): the phandle names the
				 * OTHER plug. Zero new syntax. */
				int-gpios = <&right_plug MIKROBUS_INT GPIO_ACTIVE_LOW>;
			};
		};
	};
	right_plug: right {
		compatible = "shield,plug";
		shield,plugs = "mikrobus";
		#gpio-cells = <2>;
		spi {
			log_flash: log_flash {
				compatible = "jedec,spi-nor";
				spi-max-frequency = <20000000>;
			};
		};
	};
};
```

Placement rules in the plural form:
- **Bus groups** (names matched against the OWNING plug's connector
  type's `bus_proxies`, qualified multi-bus names included) live UNDER
  their plug node. A bus group at template level in a plural shield is a
  loud `lang-shield-proxy`-family error naming the plugs it could belong
  to.
- **Plain (non-bus) device groups** stay at template level — they are
  plug-agnostic; their devices' refs carry plugs per-reference.
- **`pads` / `config`** stay at template level (shield-level facts).
- Mixing forms — template-level `shield,plugs` AND `shield,plug`-
  compatible children, or a plural child literally named `plug` — is a
  loud error. Enforced in rigc's own parser, not deferred to a schema
  (the `shields:`/`shield:` mutual-exclusion debt shape is not repeated
  here).

**Rig side** (`loader/delta.py:79,133-135`): `socket:` stays the
single-plug spelling; a plural shield's instance uses `sockets:`, a
mapping of slot name → socket reference (each value resolves through
`SocketBinding.get` exactly as `socket:` does):

```yaml
instances:
  - name: canspan
    shield: can_span_click
    sockets:
      left:  quail_sock2
      right: quail_sock3
```

- `socket:` on a plural-shield instance, `sockets:` on a single-plug
  instance, or both keys at once: loud `lang-*` errors.
- A `sockets:` key naming no slot of the shield: loud error listing the
  shield's slots.
- Omitted slots carry `None` → per-slot inference (§4).
- In a delta/variant restatement, `sockets:` REPLACES WHOLESALE (the
  `params:` rule, not a per-key merge).
- A slot value may be a carrier reference (`mux.chan0`) exactly like
  `socket:` today — it is the same reference string resolving through the
  same `resolve_one`.

## 3. The model — uniform, normalized at the parse/load boundary

- `Shield.plugs: str` (`model.py:159`) → `Dict[str, str]`, slot name →
  connector type, authoring order preserved. Single form normalizes to
  `{"plug": "<type>"}` at parse time. Every consumer of the old string
  must be found by grep and traced (`analyzer/sockets.py:160,164-165,
  177-178,254,257-258` per the 2026-08-12 grep — re-derive, don't trust).
- `GpioRef` (`model.py:62`) gains `plug: str` — the slot whose nexus the
  ref resolves through, recorded in `_parse_pos_ref` from the phandle it
  already checks. Single form records `"plug"`.
- `Device` (`model.py:79`) gains `plug: Optional[str]` — the slot its
  BUS group nests under (None for plain-group devices; `"plug"` in the
  single form).
- `Instance.socket: Optional[str]` (`model.py:225`) → `Instance.sockets:
  Dict[str, Optional[str]]`, slot → authored reference or None. Single
  form: `{"plug": <value-or-None>}`.
- `SocketResolution.sockets` (`analyzer/sockets.py:48`) →
  `Dict[str, Dict[str, BoardSocket]]`, instance name → slot →
  resolved socket. `Solved.sockets` (`analyzer/__init__.py:119`)
  changes type with it.
- **One accessor family, one module** (the `buskind.py` precedent — it
  exists because three drifting copies of one check had to be killed;
  do not seed the same drift here). Suggested: `analyzer/socketmap.py`
  with `for_ref(sockets, inst, ref)`, `for_bus_device(sockets, inst,
  dev)`, `slots_of(sockets, inst)`. Exact names are the implementor's;
  the CONSTRAINT is acceptance criterion 6: after this slice,
  `grep -rn "sockets\.get(inst\.name)\|sockets\[inst" scripts/rigc/{analyzer,emitter}`
  finds only the accessor module and `sockets.py`'s own resolution pass.
- `BoardSocket`, `Board`, `ConnectorType`, `registry.py`, `board_edt.py`,
  `board_census.py`: UNTOUCHED. Boards do not know about plugs.

## 4. Semantics, all per-slot

- **Inference** (`sockets.py:148`): per slot — exactly one board socket
  of the slot's type resolves silently; zero or several refuses, with
  the existing wording for a single-slot shield and slot-qualified
  wording for a plural one. No bipartite matching, no tie-break between
  slots: "an implementation that picks between several reasonable
  candidates is wrong however sensible its tie-break looks" applies per
  slot. Two same-type slots on a two-candidate board therefore BOTH
  refuse — correct, not a gap; the explicit `sockets:` map is the answer.
- **Mating** (`sockets.py:254`) and **subset exposure** (`sockets.py:265`)
  per slot. Subset's `needed` set is computed from the slot's OWN bus
  groups' devices — a bus needed only by slot `right` must never be
  demanded of slot `left`'s socket (this has a dedicated fixture, §7).
- **Distinct slots of one instance must resolve to DISTINCT physical
  sockets** — same defining label twice is a loud `phys-socket`-family
  error (one physical connector cannot take two plugs; the stackability
  census would only catch the non-stackable case, and with a miscounting
  message).
- **Stackability census** (`sockets.py:274`): each (instance, slot)
  resolved socket lands in `per_socket` — the existing check then works
  unchanged across instances.
- **GPIO/PWM/ADC claims** (`gpio.py:130` on): each ref resolves through
  ITS slot's socket — `soc_net(socket, pos)` then keys claims per
  physical socket, so a cross-plug ref claims a net on the other slot's
  socket with no new claim logic.
- **Position validation** (`shields.py:292-306`, `_valid_position`): a
  ref's position index validates against the connector type of the plug
  the phandle names — two plugs may have different types with different
  index spaces.
- **CS / addresses** (`cs.py:129`, `addresses.py:143`): the socket lookup
  moves to `for_bus_device`; the allocation core beneath is UNCHANGED —
  it already scopes by `bus.path` (the multi-bus slice verified this),
  so `can_span_click`'s two same-kind buses get independent CS scopes
  for free once the lookup is per-slot.
- **Wires** (`wires.py:66`): a `via: <position>` route resolves through
  the FROM end's socket's connector type — ambiguous for a plural FROM
  instance. Loud "not supported for a multi-plug instance yet" error
  this slice; ad-hoc routes unaffected.
- **Routing jumpers** (position-domain `config` entries): a jumper's
  domain has no plug axis, so a PLURAL shield declaring one is a loud
  `lang-*` error this slice. Straps (address-domain) are bus-scoped and
  work unchanged.
- **Rendering rule, load-bearing for criterion 1:** every diagnostic and
  every artifact renders a slot qualifier ONLY when the shield has more
  than one slot. A single-plug shield's output is byte-identical to
  today's, including `config-sheet.md`'s Socket-assignment table; a
  plural instance emits one table row per slot with the socket cell
  spelled `<slot>: <ref-or-label>` (`sheet.py:23-49`).

## 5. Scope — the trace, verified 2026-08-12 (re-verify, don't trust)

Production, in dependency order:

- `scripts/rigc/shields.py` — the largest single change. `_parse_shield`
  grows the plural walk (plug discovery by compatible, per-plug ctype
  lookup, nested bus groups against the owning plug's `bus_proxies`,
  placement errors); `_parse_device` takes the owning plug/slot;
  `_parse_pos_ref` takes the plug MAP (path → slot), validates against
  the named plug's ctype, records `GpioRef.plug`; `_parse_exposed` on a
  plural shield: loud refusal (§6).
- `scripts/rigc/model.py` — §3's shapes.
- `scripts/rigc/loader/delta.py:57-98,108-179` — `sockets:` parsing,
  mutual exclusions, slot-key validation, wholesale replacement,
  `Instance.sockets` construction. `loader/__init__.py:423-426` logging
  follows the shape.
- `scripts/rigc/analyzer/sockets.py` — `resolve_one` becomes per
  (instance, slot); memoization, carrier recursion, cycle guard all key
  accordingly; §4's per-slot checks; the same-socket-twice error.
- `scripts/rigc/analyzer/{gpio,cs,addresses,wires}.py` — lookup moves to
  the accessor per §4; allocation cores untouched.
- `scripts/rigc/emitter/overlay.py:125,170,237` — per-ref nexus: a
  device node's gpio ref renders `<&{_nexus(socket_of_that_ref)} ...>`,
  no longer one socket per device (`_device_node`/`_collection_entry`
  signatures change accordingly). `emitter/sheet.py:23-98` — per-slot
  display (§4). `emitter/expectations.py:42,48` — `_bus_name` already
  recovers the Device; use its `plug` for the socket lookup.
- Promotion refusal — wherever `check_promotable` lives (grep; it is the
  seam `list_rigs`/cmake/query surfaces share): a plural shield refuses
  with its own sentence, e.g. "shield 'X' plugs 2 sockets — multi-plug
  shields cannot be promoted (yet)". **Trace every caller of the
  promotion parse/refusal seam** — the §9.6-part-2 lesson: the brief's
  file list missed `west_commands/rigs.py`'s `--boards-for` and
  `--explain`; run and grep, do not trust this list either.
- `tests/…` (twister tree), cmake: NO changes expected. If cmake needs
  touching, stop and report — the premise is wrong somewhere.

Modules this change INVALIDATES (the other half of the brief-writing
rule): the unit modules mirroring everything above —
`tests/unit/test_shields.py`, `tests/unit/loader/*`,
`tests/unit/analyzer/*` (sockets/gpio/cs/addresses/wires),
`tests/unit/emitter/*` (overlay/sheet/expectations), `test_promote.py` —
every test constructing an `Instance(socket=...)` or a
`SocketResolution` by hand breaks on the shape change. **This list is a
prediction; run the suite, the failures are the census** (the S6 lesson:
every predicted-broken-test list so far was off in both directions).

## 6. Explicitly OUT OF SCOPE, each refused loudly

- **Promotion** of a plural shield (ruling R4): refused with its own
  sentence; the S4 census asserts the exclusion (§8.5).
- **Exposed sockets on a plural shield** (ruling R5): `_parse_exposed`'s
  machinery assumes THE plug (`shields.py:360,375`); a plural shield
  authoring any `socket,*`-compatible child is a loud "multi-plug
  carriers are their own future slice" error. A SINGLE-plug carrier is
  untouched.
- **`via:`-routed wires from a plural instance** (§4).
- **Routing jumpers on a plural shield** (§4).
- Any real production connector/board change: this slice adds shields,
  fixtures, and one corpus rig; boards are read-only to it.

## 7. Fixtures and the corpus example

**Corpus (ruled in by the design doc §0.5): `can_span_click`** —
`boards/shields/can_span_click/`, the §2 template — plus one corpus rig
plugging it on quail (`sockets: {left: quail_sock2, right: quail_sock3}`),
with goldens. Two same-type slots, a cross-plug ref, two same-kind buses,
and dead inference (four mikrobus candidates per slot), all in one
artifact. **Probe the build tier before committing to the mcp2515**: if
CAN driver Kconfig walls the build the way TCA954x did, swap the chip for
a second known-good SPI device (enc28j60 is proven on this exact socket
family) — the slice's subject is slot machinery, not any particular
driver; record the probe either way.

**Fixtures** (rigc test tree, following `test_multibus_socket.py`'s
precedent for fixture connector types/boards):

- An `acq_bridge`-shaped MIXED-type shield (arduino-r3 + mikrobus slots,
  design doc §0.4 shield A) on a fixture board offering exactly one
  socket of each type → both slots resolve by INFERENCE with no
  `sockets:` at all; a second fixture board with two mikrobus sockets →
  the per-slot ambiguity refusal.
- The per-slot SUBSET fixture: a plural shield whose `right` slot's
  devices need a bus only `left`'s socket offers → `phys-subset` names
  the right slot/socket, and the accept-side twin (bus present on the
  right socket) passes — the pair is the falsifier for §4's per-slot
  `needed` computation.
- Reject fixtures, each with byte-exact stderr golden: `socket:` on a
  plural instance; `sockets:` on a single-plug instance; both keys;
  unknown slot key; two slots → one physical socket; plural shield with
  a jumper; plural shield with an exposed socket; template-level bus
  group in a plural shield; plural template also carrying `shield,plugs`.
- **Run reject controls IN-TREE** and assert the diagnostic's own
  sentence — `instances: []`-style reject fixtures exit 1 either way, so
  `returncode != 0` proves nothing (NEXT-SESSION 2026-08-10, the
  reject-fixture-family property).

## 8. Acceptance criteria

1. **Every existing golden byte-unchanged** — stderr.txt, exit_code,
   context.cmake, config-sheet.md, overlays, all 14 existing shields'
   suites. Nothing existing may be hand-edited or refrozen; if an
   existing golden moves, the slot-silence rule (§4) is broken —
   understand it, don't refreeze it. (`RIGC_REFREEZE=1` is blocked by
   the harness classifier anyway.)
2. **The corpus rig's artifacts prove the mechanism**: `can0`'s CS
   allocated from the LEFT socket's pool; `log_flash`'s from the RIGHT's;
   `can0`'s `int-gpios` rendered through the RIGHT socket's nexus — that
   one line is the cross-plug falsifier, name it in a test assertion,
   not just a golden.
3. **Negative control** (the multi-bus brief's own shape): the two
   same-kind buses' CS namespaces are independent — both devices may
   legally hold the SAME cs-pool index. Without this, a regression
   merging the slot namespaces back into one still passes everything
   else. Mutation-verify it: collapsing the resolution map to one socket
   per instance must fail THIS test.
4. **Per-slot inference** works and refuses per §7's fixture pair.
5. **`test_singleton_identity_law.py`'s derived EXCLUDED set grows** from
   `set()` to `{"can_span_click"}` via the eligibility predicate (not a
   hand-list), asserted with the R4 reason — the S4 pattern: the set
   visibly shrinks again the day the promotion slice lands.
6. **The accessor is the only path**: the §3 grep criterion holds.
7. Full gate green: mypy clean, coverage ≥ the 88 floor (currently 93).

## 9. Reduced verification contract

Per [[reduced-gate-contract]]: the implementor runs mypy + unit + the
non-build integration tier + ONE named build module; the driver runs the
full gate independently after review.

- **The named build module: the NEW `tests/integration/
  test_multiplug_shield.py`** (mirror `test_multibus_socket.py`'s
  shape), which must carry the corpus rig's build-marked round-trip.
  Check the marker actually exists before claiming it — naming a build
  module by reflex without one is the recorded failure mode.
- Modules that OBSERVE the criteria: the new module (2, 3, 4),
  `test_emitted_corpus.py` + `test_emitted_rejects.py` (1 — plus new
  goldens), `test_singleton_identity_law.py` (5), `test_promote.py` /
  `test_boards_for.py` (the refusal sentence), plus §5's invalidated
  unit modules.
- Brief the reviewer to MUTATION-CHECK: criterion 3's collapse mutation,
  the per-slot subset fixture (drop the per-slot `needed` computation →
  its accept/reject pair must flip), and the refusal sentence (delete
  the plural check in `check_promotable` → the test must fail on the
  SENTENCE, not on an unrelated later error — the S6 `:socket` lesson).
- Standing rules: the implementor's report is a hypothesis — the driver
  runs everything independently; trace actual callers, a brief's scope
  list is a prediction; purge `__pycache__` after any mutate-and-restore
  probe; never store probe results in a `-d` build dir.
