# Board as invocation coordinate — implementation brief

Implementation companion to `board-as-invocation-coordinate.md`, which
stays what it is: the design exploration record (Tobi + driver,
2026-07-29). This file is the actionable half, written 2026-08-04 after
reading that document against the current tree.

**Headline: the architectural prerequisite is DONE and intact. All three
rulings are now settled (2026-08-04). Steps 1 and 2 of §7 have landed;
the remaining blocker is the singleton identity law, which needs a
feature that does not exist yet (§5).**

Status of §7's steps:

| step | state |
|---|---|
| 1. aliases + alias-aware lookup | LANDED `d47ec86` |
| 2a. empty-rig identity law | LANDED `e6423c0` — the law HOLDS |
| 2b. singleton identity law | **BLOCKED**, see §5 |
| 3. content migration | ready, not started |
| 4. the coordinate change | ready once rulings applied |
| 5. `--boards-for` | independent, shippable any time |

## 1. What is already in place — verified, not assumed

§6 of the design doc was written as guidance TO the rigc R2 brief. R2
delivered all three points, and they survived the cutover:

- **One constructor, one value.** `loader/binding.py::resolve_board`
  produces a `SocketBinding`; nothing else constructs one.
- **One seam.** The binding applies at instance construction
  (`loader/delta.py::parse_instance`). The delta engine merges abstract
  references and never sees a board label — the mistake S2 had to fix in
  the blueprint.
- **One diagnostic module.** Every board/sockets diagnostic of S2's five
  shape rules lives in `binding.py`, so the frozen wording survives a
  mechanism swap.
- **`SocketBinding.get` is lookup-else-identity.** This is the property
  the whole §4 resolution depends on: a board whose labels follow the
  convention needs NO map, and the map degrades to dead weight rather
  than becoming wrong.

Door 1 is also exactly where the doc says: `cmake/boards.cmake` step 1
does `-DRIG` → board inference plus the RIG/BOARD exclusivity FATAL, with
its reconfigure/rig-swap edge cases already worked out and commented.
Deleting it is mechanical.

Downstream is genuinely board-parametric: the analyzer takes a
`--board-dts` PATH, and emitter/shields/registry/dtsio/board readers
never see `rig.board` at all. The doc's "analyzer/emitter ZERO" claim
holds.

## 2. RULING 1 — the per-type socket-label convention

The design doc (§4.1) says board rig-extensions should carry
"conventional labels per connector type: singleton types bare (`ard`),
multi-socket types an indexed family matching the silkscreen
(`mikrobus_1..n`)". That was written without a census. Here is the census:

| board | label(s) today | node name(s) | type |
|---|---|---|---|
| nucleo_f401re | `nucleo_ard` | `connector_arduino_r3` | arduino-r3 |
| frdm_k64f | `frdm_ard` | `connector_arduino_r3` | arduino-r3 |
| quail | `quail_sock1..4` | `connector_mikrobus_1..4` | mikrobus |
| seeeduino_lotus | `grove_d2..d7`, `grove_a0..a2` | `connector_grove_*` | grove |

Two things the doc could not have known:

- **Lotus already conforms.** `grove_d2` is type-prefixed and
  silkscreen-indexed. It is not board-prefixed at all.
- **The node NAMES are already conventional everywhere** —
  `connector_<type>[_<position>]`. Only the LABELS carry board identity.

That makes the doc's proposed `ard` for a singleton inconsistent with the
tree's own existing practice: grove is type-prefixed even though it has
nine sockets, so "bare for singletons" would mean arduino-r3 and grove
follow different rules for no reason a user could predict.

**Proposed convention instead: `<type>` for a singleton socket,
`<type>_<silkscreen>` for a family**, where `<type>` is the connector type
name with dashes as underscores — the name that already exists in
`dts/bindings/connectors/<type>.yaml` and in the `socket,<type>`
compatible. That yields:

| board | conventional label | change |
|---|---|---|
| nucleo_f401re | `arduino_r3` | add alias |
| frdm_k64f | `arduino_r3` | add alias |
| quail | `mikrobus_1..4` | add aliases |
| seeeduino_lotus | `grove_d2` … | **none — already conforms** |

Deriving the vocabulary from the connector type rather than inventing one
is the same construct-don't-parse discipline the rest of the project
follows, and lotus needing zero changes is a useful check that the
convention describes what a sensible author already did.

**RULED 2026-08-04: adopt `<type>` / `<type>_<silkscreen>`** as proposed.

### 2.1 The "additive" claim is FALSE today — and this is step 1's real work

Both this brief's first draft and the design doc (§4.1) assert that
conformance is additive: "DT allows multiple labels per node … add the
alias, rename nothing". Checked against the board reader, that is wrong.

`board_edt.py` takes `label = node.labels[0]` and keys
`sockets[socket.label] = socket`, and `analyzer/sockets.py` resolves a
content reference with `board.sockets.get(ref)`. So the socket dict is
indexed by the DEFINING label only, and a second label is **inert**: after
adding `arduino_r3` to nucleo's node, `socket: arduino_r3` would still be
rejected as "board has no socket". Writing the conventional label FIRST
instead would make it resolve but would break every reference to
`nucleo_ard` — a rename, which is exactly what the additive story was
meant to avoid.

**So step 1 is a production change, not a data change.** The board reader
must index every label of a socket node, not just the defining one.

Do it WITHOUT changing what `Board.sockets` iterates. `analyzer/sockets.py`
walks `board.sockets.values()` to build the "sockets of <board>: …" census
inside the `phys-socket` diagnostic, and that wording is frozen in the
`unmapped-socket` golden — keying the same dict by two labels would list
every aliased socket twice and churn it. Keep `Board.sockets` canonical
and keyed by the defining label, and add an explicit alias-aware LOOKUP
(a `Board` method, with the alias index built in `board_edt.py`) that
`analyzer/sockets.py` uses in place of the bare `.get`. Iteration stays
one entry per physical socket; only resolution widens.

`Socket.label` stays `labels[0]` — see §6 for why that matters.

## 3. RULING 2 — the `/rig` extension target

Today `list_rigs.py` resolves `nucleo_f401re/stm32f401xe/rig` and the user
never types it. Under `--board`, the doc (§3) lists three options and
picks none:

1. users name the extension target explicitly (`--board
   nucleo_f401re/stm32f401xe/rig`) — honest, ugly, and leaks a
   migration artifact into the everyday UI;
2. the machinery infers the `/rig` qualifier from a plain
   `--board nucleo_f401re` — friendly, but it is inference over board
   names, and this project has a standing rule against parsing what it
   can construct;
3. boards carry typed sockets natively, so no extension target exists —
   the real end state, and the recorded native-socket-board gap.

Note this interacts with the bridle migration: the E3 lotus extension is
already recorded as double-scaffolding that dissolves when sockets go
native in bridle's own board. So option 3 is where two separate threads
are already heading, and options 1 and 2 differ mainly in how much
interim UI debt we take.

**RULED 2026-08-04: option 1 — the extension target stays EXPLICIT.**
Users name `nucleo_f401re/stm32f401xe/rig`. No inference over board names
is built.

The stated expectation is that upstream boards gain typed sockets over
time, at which point the `/rig` variant has nothing left to add and goes
away on its own — option 3 arriving by attrition rather than by a
migration step. That makes option 2 actively unattractive: an inference
mechanism would be built to hide an artifact we expect to disappear, and
would then itself need retiring.

Practical consequence for whoever implements step 4: do not add a
board-name fixup anywhere. If a plain `--board nucleo_f401re` fails
because the board declares no typed socket, that is the correct and
informative outcome — it is the same `phys-socket` answer §4 of the
design doc already relies on, and it names exactly what the board is
missing.

## 4. RULING 3 — per-board fragments

Variants carry `<rigname>_<variant>.overlay` / `_defconfig`. A freely
chosen board has no declared name to construct a filename from. The doc
names upstream shields' `boards/<board>.overlay` existence-checked
discovery as the adoptable precedent and observes that
construct-then-check-exists does not violate Q6.

**RULED 2026-08-04: adopt it.** A rig gets per-board fragments the way a
shield has them today — `boards/<board>.overlay` (and the `_defconfig`
counterpart) inside the rig's own directory, discovered by
construct-then-check-exists, which is Q6-clean because the filename is
constructed from the resolved board name and merely probed, never parsed.

Two things to settle while implementing rather than after:

- **Which board name constructs the filename.** Under ruling 2 the user
  names the extension target (`nucleo_f401re/stm32f401xe/rig`), and that
  string contains `/`. Upstream shields key on a plain board name. Decide
  explicitly whether the fragment is keyed by the full qualified target,
  by the bare board name, or by the normalized form — and note the hwmv2
  precedent already in this codebase: `normalize_revision` exists because
  a revision id's dots cannot go into a filename. This is the same class
  of problem and should reuse that thinking, not invent a second scheme.
  Whatever is chosen, derive it from the RESOLVED name (hazard class B1).
- **Where it sits in the overlay chain.** `parked.md`'s "Application
  rig-specific overlays" entry already records the chain: board.dts →
  generated overlay → shield `boards/<board>.overlay` → `rig.overlay` →
  app overlays → `EXTRA_DTC_OVERLAY_FILE`. A rig's own per-board fragment
  belongs beside `rig.overlay`, most-specific-wins; say which side and
  why.

Note this makes the per-board fragment the mechanism that absorbs what
S2's per-variant boards do today — a variant that exists ONLY to swap the
host board becomes a board fragment instead, which is precisely the
axis-conflation §3 of the design doc lists as the argument FOR the whole
direction.

## 5. The two identity laws have no tests

The design doc calls these the replacement for the old §7 lift, and calls
the singleton law "the instrument for the §7 rewrite". Neither exists in
the tree:

- **Empty rig ≡ plain board** (saferail 11): `--board b --rig <empty>`
  produces byte-equal `zephyr.dts` to `--board b`. No test anywhere.
- **Singleton rig ≡ upstream shield** (new): `--board b --shield s` ≡
  `--board b --rig <one default-placed instance of s>`.
  **BLOCKED, and not on cost.** "Default-placed" is load-bearing —
  upstream `--shield` names no socket — but `loader/delta.py::
  parse_instance` does `require(item, "socket", "instance")`, so every
  instance MUST name its socket. Omission is exactly §4.2 of the design
  doc's unique-by-type inference, which that doc says exists "to make the
  singleton identity law hold", and which is unimplemented. So the law
  cannot be written in its stated form today. Three ways forward, in
  preference order: implement §4.2 first (a small, self-contained loader
  feature the design doc already rules is sugar-only, not the general
  mechanism); write a weakened version naming the socket explicitly (still
  a real equivalence, but it drops the half the law exists for); or defer.
  A SECOND cost applies either way: no shield in the tree exists in
  upstream form — every one is a `.shield` template with no plain
  `.overlay` — so the law needs a shield authored in both worlds, with the
  hand-written overlay as the oracle. Known-feasible: the P2 S1-equivalence
  work did exactly that against the legacy `--shield` build.

**Write both BEFORE the coordinate change, not after.** They are the only
things that would catch a regression in what the product coordinate is
supposed to preserve, and a law written after the change it is meant to
police tends to encode what the code now does. Both are build-marked
integration tests; the second additionally needs a shield that exists in
both worlds (a `.shield` template and a plain overlay), which may make it
the more expensive of the two — measure before committing to it, and if
it is disproportionate, say so rather than weakening it.

## 6. Golden impact — measured, and larger than the doc implies

The socket label reaches emitted artifacts, but the two artifacts get it
from DIFFERENT places, and that difference decides the cost. Traced, not
assumed:

- **`rig-gen.overlay` emits the BOARD socket's own label.**
  `emitter/overlay.py::_socket_ref` returns `socket.nexus_label or
  socket.label`, and `socket.label` is the board node's defining label.
  So the phandle stays `<&nucleo_ard 13 0x11>` no matter what the content
  calls the socket. **The overlay does not churn.**
- **`config-sheet.md` echoes the CONTENT's string.**
  `emitter/sheet.py` renders `inst.socket` directly, into the
  instance/socket tuple that C2b made a compared FACT. **The config sheet
  does churn**, for every migrated instance.

This corrects an earlier draft of this brief, which claimed both churn.
The revised expectation for step 3:

- **Adding the aliases is ZERO golden churn** — a second DT label plus an
  alias-aware lookup changes nothing until content references it. That is
  why it is its own step, and it is what makes the step cheap to verify:
  `git diff --stat` on the goldens must be empty.
- **Migrating the content churns `config-sheet.md` only**, across the
  accept rigs that name a board-prefixed socket (eight instances name
  `nucleo_ard` today). `zephyr.dts` byte-identical and the overlay
  byte-identical are both acceptance criteria — the second is a genuine
  falsifier here, since an implementation that "helpfully" made the
  overlay use the conventional label instead would show up immediately.

Keeping `Socket.label` as the defining label is therefore deliberate, not
an oversight: the overlay is a DT fragment applied to THAT board in THAT
build, so referencing the board's own defining label is correct. Board
agnosticism belongs in the rig's content, which is the thing that gets
reused across boards — not in a generated per-build artifact.

**The alias must exist before content references it**, or resolution
fails outright — so the alias step strictly precedes the content step, on
every board any corpus rig targets.

Instance-scoped sockets (`mux_1.ch0`) are already board-agnostic by the
provider rule and change not at all.

Instance-scoped sockets (`mux_1.ch0`) are already board-agnostic by the
provider rule and change not at all.

## 7. Sequencing

1. **Aliases + alias-aware lookup** (ruling 1 settled). Two halves, one
   commit, because neither is useful alone (§2.1): the board reader gains
   an alias index and `analyzer/sockets.py` resolves through it, and the
   conventional labels are added to nucleo, frdm and quail — lotus already
   conforms and must not be touched. Zero golden churn, zero behaviour
   change: prove it with `git diff --stat` on the goldens, not by
   assertion. Add the lint the design doc suggests (§4.1, third bullet):
   every `socket,*` node in a board rig-extension carries its type's
   conventional label, in the shape `test_layer_discipline.py` already
   uses — note it is a census-style test, so it is falsified by mutating
   the WORLD it observes (drop a label from a board) and never by editing
   its own assertion.
2. **The two identity-law tests** (§5), against TODAY's coordinate. They
   must pass before anything changes, or they are not laws. **2a landed
   (`e6423c0`) and the law holds** — with a verified negative control: a
   single instance in the fixture makes `dts_equiv` report differences.
   **2b is blocked** (§5).
3. **Content migration** to conventional labels: the classified refreeze
   of §6. `zephyr.dts` byte-identical is the acceptance criterion.
4. **The coordinate change itself** — delete `boards.cmake` step 1 and
   both guards, make the board column optional in `list_rigs.py`, have
   the loader take an injected board instead of resolving one. By this
   point it is close to the constructor swap §6 of the design doc
   predicts, because steps 1–3 have already retired the S2 mapping
   vocabulary's only real user.
5. **`--boards-for`** (§5 of the design doc, "Tobi: ship it") — the
   enumeration query. Independent of 1–4 and shippable on its own; it
   reads the same census the step-1 lint builds.

Steps 1, 2 and 5 are each independently valuable and safe to land even if
the coordinate change never happens. Step 3 is only worth doing as part
of this direction.

## 8. Not in scope here

Rewriting ontology §7. The design doc is its input, and the singleton
identity law (§5 above) is its instrument — so the rewrite wants both to
exist first.
