# Board as invocation coordinate — implementation brief

Implementation companion to `board-as-invocation-coordinate.md`, which
stays what it is: the design exploration record (Tobi + driver,
2026-07-29). This file is the actionable half, written 2026-08-04 after
reading that document against the current tree.

**Headline: the architectural prerequisite is DONE and intact. §7's
ORIGINAL sequencing is SUPERSEDED by §9 (Tobi, 2026-08-05): the singleton
identity law is downstream of the coordinate change, not upstream of it,
and the law's oracle is our own promoted shield rather than an upstream
legacy `--shield` build. Read §9 before §7.**

Status:

| step | state |
|---|---|
| aliases + alias-aware lookup (old §7.1) | LANDED `d47ec86` |
| empty-rig identity law (old §7.2a) | LANDED `e6423c0` — the law HOLDS |
| §4.2 unique-by-type socket inference | LANDED `1c2344e` |
| S1 coordinate change, mechanism only | see §9, `board-coordinate-s1-brief.md` |
| S2 `--boards-for` | LANDED 2026-08-06 — `board-coordinate-s2-brief.md` |
| S3 `--rig <shield>` promotion + `--explain` | ruled, not started (§9) |
| S4 singleton identity law (old §7.2b) | authored failing-first, after S3 (§9) |
| S5 content migration (old §7.3) | ready, not started |
| S6 strict symmetry — `board:` out of rig.yml | the stated TARGET (§9) |

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
- **Singleton rig ≡ upstream shield** (new): as originally stated,
  `--board b --shield s` ≡ `--board b --rig <one default-placed instance
  of s>`. **This statement is RETIRED — see §9.1.** Both of its recorded
  blockers are also now stale: §4.2 unique-by-type inference LANDED in
  `1c2344e` (`socket:` is optional in `parse_instance`, `delta.py:77-81`),
  and the "no shield in the tree exists in upstream form" cost was wrong —
  `adafruit_data_logger`, `adafruit_winc1500` and `arduino_uno_click` all
  exist in the pinned zephyr tree with real `.overlay` files alongside our
  same-named `.shield` templates, which is exactly the collision
  `dts.cmake:612-664`'s marker preference already resolves.

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

## 7. Sequencing — SUPERSEDED by §9.5 (kept for its per-step detail)

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

## 9. RULINGS 4–8 and the REVISED sequence (Tobi, 2026-08-05)

§7 below is superseded by §9.5. These rulings came out of reading §5 and
§6 against the tree; every factual claim here was checked, not reasoned.

### 9.1 RULING 4 — the natural mapping holds for OUR shields; the law is INTERNAL

`a → [a]` — a single shield instance canonically promoted to a rig —
**holds, and is claimed for `.shield` template shields only.** It is NOT
claimed for legacy `.overlay` shields.

Consequence: the singleton identity law's oracle is **our own promoted
shield**, not an upstream `--shield` build:

> **`--board b --rig <shield-name>` ≡ `--board b --rig <checked-in rig
> with one socket-less instance of that shield>`**

Both sides go through rigc on the same board target, so the law is
**byte-equality of the emitted artifact set** — the standard the frozen
suite already applies. No new comparator, no oracle to hand-author.

This retires the three divergences `P2-S1-equivalence.md` measured
(129/134 nodes identical): `+/connector_arduino_r3`, `int1-gpios`/
`cs-gpios` retargeted to the typed socket with IDENTICAL cell values, and
upstream's shield repointing the `/aliases rtc` while ours deliberately
does not (Conv. 8). All three were artifacts of comparing against
*upstream's mechanism* on a *different board*, and none of them is a gap.
The legacy comparison keeps its existing status: a classified-divergence
audit, useful, **not a gate**.

Why the law may be authored AFTER the coordinate change, against §7.2's
"write both first": the two laws are different kinds. **2a is a
conservation law** — it must hold before and after, which is why it landed
first and why it polices the change. **The singleton law is
constitutive** — it defines what the new coordinate MEANS, so it cannot
predate the coordinate. The guard against it encoding whatever the code
ends up doing is the project's own red-proof discipline: author the
fixture and the law FIRST, require it to fail for the named reason, then
implement.

### 9.2 RULING 5 — an ad-hoc rig: a shield name is a valid `--rig` argument

Rigs being persistable and version-controllable is a designed merit and is
not being weakened. But an ad-hoc / on-the-fly rig has its own virtues, so
a **shield name is recognizable as a `--rig` argument** in the sense of the
natural mapping, its socket resolved canonically by the §4.2 inference that
`1c2344e` landed.

Two things this needs, both driver-flagged during the ruling:

- **Namespace.** `-DRIG=` resolves a rig FOLDER via `list_rigs.py` today.
  Reuse the precedent rather than invent one: `dts.cmake:612-664` resolves
  a shield-name collision by preferring the folder carrying the
  `<name>.shield` marker, warning when ambiguous. Rule: **rig folder wins,
  shield name is the fallback, a name that is BOTH is an error naming both
  paths.**
- **`template: true` becomes load-bearing.** It is declared in our carried
  commit `3f205005b99` ("its `<name>.overlay` is replaced by a
  `<name>.shield` template") and **nothing reads it** — not
  `list_shields.py`, not upstream `shields.cmake`, not rigc, which uses the
  marker FILE instead. If a shield name becomes a `--rig` argument, that
  flag is the natural authority for "promotable".

### 9.3 RULING 6 — `--explain`, and desugaring as the anti-erosion property

**Adopted.** The ad-hoc form must desugar to the persisted form and be
able to PRINT it — `west rigs --explain <expr>` emitting the rig.yml +
content file it stands for. Three properties earn it:

1. the singleton law becomes checkable at the MODEL level, not only the
   artifacts;
2. ad-hoc → checked-in is a copy-paste promotion, so the on-the-fly path
   FEEDS the version-controlled one instead of competing with it;
3. if it cannot be printed it cannot be built — which structurally forbids
   the ad-hoc form from ever expressing something the persisted form
   cannot.

It gets MORE load-bearing under §9.4's target state: with no `board:` in
rig.yml, `--explain` is where "what would this actually build" is answered.

### 9.4 RULING 7 — board symmetry: STAGED, with the strict form as the target

Tobi's symmetry argument, which reordered the whole queue: when
`--rig some_shield` names a promoted shield the board is necessarily
absent, so **out of symmetry the board should also be absent for
`--rig some_persisted_rig`**. Two things in `cmake/boards.cmake` make the
promotion impossible before this is addressed — step 1 INFERS `BOARD` from
the rig (a shield declares none), and `-DBOARD` + `-DRIG` is a hard FATAL
**even when the values match** (`boards.cmake:97`). The promoted form's
only possible invocation is precisely the forbidden one.

Measured cost of the strict form (board leaves rig.yml entirely): **17
rig.yml files declare `board:`** (`ard_datalogger` three times, via
variants), **19 goldens carry `RIG_BOARD`**, `list_rigs.py`'s board column
and `west rigs` enumeration go, and `binding.resolve_board`'s "a board per
variant or once at the top level, **never neither**" is one of S2's five
rules with frozen wording (goldens `no-board-declared`,
`variant-board-partial`). A corpus + diagnostic-family migration, not a
flag flip.

**RULED: stage it** — the same mechanism/data split that made §7.1
reviewable. Mechanism now, corpus migration as its own classified step.
**The strict form is the stated TARGET**, recorded here so the
intermediate cannot calcify. Its payoff is the argument that motivated the
whole direction: `ard_datalogger`'s dual-host variants collapse to one
variant-less rig built twice, and `variants:` returns to topology
alternates only.

Note the mechanism change is smaller than "delete step 1". It is
**inverting step 1's authority**: keep the inference as a FALLBACK, drop
the exclusivity FATAL, let a user-passed `BOARD` win over the rig's
declared board, which becomes a DEFAULT rather than a derivation.

**`--boards-for` is promoted from "independent, shippable any time" to a
PREREQUISITE** — it is what enumeration becomes once declaration is gone,
so it must exist before enumeration is at risk.

### 9.5 RULING 8 — the revised sequence

1. **S1 — coordinate change, MECHANISM ONLY.** Invert step 1's authority;
   `resolve_board` accepts an injected board ("never neither" relaxes to
   "never neither unless injected"); board column optional in
   `list_rigs.py`. **Zero golden churn is the acceptance criterion.**
   Spec: `board-coordinate-s1-brief.md`.
2. **S2 — `--boards-for`**, before enumeration is ever at risk.
3. **S3 — the `--rig <shield>` promotion** + the §9.2 namespace ruling +
   `--explain`. Params-on-the-CLI slots in here once §9.6's token exit is
   ruled.
4. **S4 — the singleton identity law**, authored failing-first (§9.1).
5. **S5 — content migration to conventional labels** (old §7.3). Now
   properly motivated: under a free board, `nucleo_ard` in content is a
   portability bug, not a style question.
6. **S6 — strict symmetry.** `board:` out of rig.yml, variants collapse to
   topology-only, `RIG_BOARD` + the 19 goldens refreeze as a classified
   step.

### 9.6 OPEN — the ad-hoc params token exit

`--rig adafruit_data_logger:param1=0x87:param2="foo"` was proposed. Two
findings against the tree:

- **`params:` already exists** (`delta.py:106`, `loader/params.py`), so the
  CLI form is SUGAR over an existing feature, not a new one. But it is
  **two-level, keyed by the shield's DEVICE label**, validated against
  that device's `shield,params` declaration:
  ```yaml
  - name: btn_start
    shield: grove_btn
    params:
      gb_key:
        zephyr,code: INPUT_KEY_0
  ```
  So a bare `param1=` cannot address anything —
  `adafruit_data_logger` has five devices (`dl_rtc`, `dl_sd`, `dl_led1`,
  `dl_led2`, `dl_sq`). The CLI form needs the device coordinate:
  `<device>.<prop>=<value>`. The grammar must also compose with `@`,
  already taken by shield revisions (`i2c_sensor@2`).
- **The value is a cpp token, not a literal.** `params.py:147` sends any
  non-int-literal through `check_param_token` against the RIG's
  `dt-includes:`. Verified: the vocabulary header lives in the rig
  (`lotus_buttons.yml:20`, `input-event-codes.h`) and **no shield template
  includes it**. An ad-hoc rig has no content file, hence no
  `dt-includes:`, and `grove_btn`'s *required* param is exactly such a
  token.

Three exits: (1) int literals only ad-hoc — harsh, excludes the corpus's
own required param; (2) a companion CLI input (`--rig-include`); (3)
**make the shield declare its param vocabulary** — a shield saying
`shield,params = "zephyr,code"` already claims to know what it needs, so
letting it carry the `#include` puts the vocabulary with the declaration.
Driver recommendation: **(3)** — the only exit that makes the ad-hoc form
self-sufficient, and it improves the persisted form too. NOT YET RULED.

## 10. Not in scope here (was §8)

Rewriting ontology §7. The design doc is its input, and the singleton
identity law (§9.1) is its instrument — so the rewrite wants both to
exist first.
