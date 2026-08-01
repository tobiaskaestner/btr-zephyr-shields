# Backlog — test suite refactor: module structure + fixture tree layout

Recorded 2026-07-27 from Tobi's review of the current suite. **Scheduled AFTER
the current queue and DEFINITELY BEFORE the bridle migration** — the tests move
into bridle there, and refactoring afterwards rewrites freshly condensed
history (the same argument that put the metadata/content split ahead of the
migration).

Not yet dispatched. Two parts; they touch the same files and should land as
one sequence, Part A first.

## Why both parts exist

Tobi, reading the suite: it is hard to tell from a module name (a) what
component is under test, (b) what workflow or stage inside a workflow, or (c)
what feature the suite addresses. And in the fixture tree, it is hard to look
things up because content is organized by test case rather than by kind.

---

# Part A — module structure

## The diagnosis, measured

Seven test modules named on **five different axes**:

| module | lines | named on | covers |
|---|---|---|---|
| `test_edt_build` | 37 | component | `edt_build.py` alone, no rig concepts; BSD-3 upstream candidate |
| `test_connector_bindings` | 57 | data | the four REAL connector YAMLs as edtlib bindings |
| `test_controller_label` | 78 | invariant | one determinism rule in one function |
| `test_board_read` | 138 | layer | board projection + plain-build net + `edt.pickle` cross-check |
| `test_cmake_alone_entry` | 457 | entry point | `-DRIG` as sole coordinate, exclusions, rig-swap guard |
| `test_tier2_goldens` | 605 | mechanism | real pass-2 `zephyr.dts`, structural compare |
| `test_tier1_goldens` | **1262** | mechanism | expander output frozen — and de facto ALL feature coverage |

**No module is named for a feature, yet features are what changes.** Every
feature slice lands in `test_tier1_goldens.py`, which is 41% of all test code
and holds at least six features discoverable only by grepping function names:
revisions (13), variants (7), params (6), metadata/content split (6), delta
engine (5), plus ~14 one-off rejects.

Root cause: **the golden MECHANISM became the organizing principle and features
got filed underneath it.** That is why one module is 1262 lines and two are
under 80.

**Worth preserving:** the tier-1/tier-2 RELATIONSHIP is good design — tier 2 is
the oracle that licenses a tier-1 refreeze. It is the file boundary that is
wrong, not the concept. "How strongly do we assert" is marker-shaped; "what is
under test" is file-shaped.

## The rules (Tobi, ratified)

1. A module is named for its **component/stage plus feature**, never for the
   assertion mechanism.
2. **NO module mixes unit and integration tests.** For a human reader looking
   for one, the other is noise. This is a file-level rule, stronger than
   markers alone.
3. Assertion-kind (`unit`/`integration`, `build`, and tier if kept) lives on
   **markers**, for selection.
4. Rule 2 gets an **enforcement test**: collect each module, fail if any yields
   both markers. Without it the boundary decays the first time someone adds a
   build test to a unit file. Same reasoning as T1's hermeticity check.

## Measured starting point

Only ONE module mixes today:

| module | build | non-build |
|---|---|---|
| `test_board_read` | 12 | 0 |
| `test_cmake_alone_entry` | 11 | 0 |
| `test_tier2_goldens` | 31 | 0 |
| `test_controller_label` | 0 | 2 |
| `test_edt_build` | 0 | 1 |
| **`test_tier1_goldens`** | **26** | **59** |

Its 53 test functions divide: **41** fixture-only (unit candidates), **10**
run a real build, **2** read the corpus without building
(`test_corpus_rig_identity`, `test_corpus_complete`).

**Caveat — "candidate" is not "verified".** Some fixture-based tests still
touch repo data: `unknown_board`'s golden reads `no such board directory under
./boards`, so it depends on the real board tree. Contrast `no-board-declared`,
pure loader shape, touching nothing. Per-test verification via T0's
`conftest.assert_fixture_local()` is the tool; expect the final unit count
somewhat under 41.

## The insight that decides the approach

**The feature clusters and the unit set are nearly the same set** — loader-shape
features are hermetic by nature, while corpus sweeps and real-board tuples are
exactly the integration ones. So splitting by FEATURE delivers rule 2 almost
for free.

Splitting `test_tier1_goldens.py` merely into `_unit` / `_integration` halves
would cement the mechanism naming rule 1 rejects, and would move the same tests
twice.

## Proposed layout

```
tests/
  loader/       test_variants.py test_revisions.py test_params.py
                test_deltas.py test_metadata_split.py          ← unit
  analyzer/     test_allocation.py test_socket_mating.py
  emitter/      test_overlay.py test_config_sheet.py
  boardread/    test_edt_build.py test_projection.py
                test_controller_label.py
  integration/  test_cmake_entry.py test_corpus.py
                test_pass2_dts.py                              ← integration
```

**De-risk option** if the full move is too big for one slice: do the feature
split of the UNIT side only, leaving the integration remainder as one file to
break up later. Rule 2 is satisfied either way.

---

# Part B — the fixture tree as a Zephyr module

## Tobi's ask

The fixture folder should be organized the way a Zephyr module organizes
things, **with `fixtures/` as the module root** — `fixtures/boards/rigs/` for
rigs, `fixtures/dts/bindings/connectors/` for connector bindings, and so on.
Rationale: looking things up is currently hard.

## Current state

51 top-level directories under `fixtures/`. About 45 are per-CASE directories
(`unmapped-socket/`, `no-board-declared/`, …), each holding whatever that one
test needs. Six are ad-hoc GROUPING directories that already reach for
organization-by-kind: `connectors/`, `v1b-shields/`, `v1c-shields/`,
`v1c-badyml/`, `v1c-misnamed/`, `v1c-mapping-badyml/`.

Two things to note about those six. First, they show the module layout is not a
new idea here — it is what the tree has been groping toward. Second, four of
them carry **slice names** (`v1b-`, `v1c-`) in the directory name, which is
design-process archaeology of exactly the kind the comment-style rule bans in
comments. Those names should not survive the move.

## Target

```
fixtures/
├── boards/
│   ├── mainboards/                    synthetic board .dts
│   ├── shields/<name>/                fixture shields, one dir each
│   └── rigs/<rigname>/                rig.yml + <rigname>.yml + fragments
├── dts/bindings/connectors/           synthetic connector types
└── include/dt-bindings/connector/     position index headers
```

## The trade-off to make deliberately

Today a case is CO-LOCATED: `fixtures/unmapped-socket/` holds its `rig.yml`,
its content file and its board `.dts` together, so everything one test uses is
visible in one place. Organizing by KIND scatters a case across several
directories. Tobi's ask is explicitly for lookup-by-kind, so that is the
ratified direction — but the cost is real and should not be discovered
mid-slice.

**It is smaller than it looks**, because rigs keep one directory per rig under
`boards/rigs/<rigname>/`, which is both the real convention and the bulk of any
case (metadata + content + fragments stay together). Only boards, shields,
bindings and headers move out — and those are SHARED across cases already,
which is precisely why the six ad-hoc grouping directories exist.

## A free win worth taking

`mainboards/` is the decided future name for the board kind
(`bridle-migration.md`). **The fixture tree is the cheapest possible place to
prove that layout works** — no real board content, no external references, and
the suite itself is the test. Adopting it here first de-risks the real rename.

## Cost

Mechanical but wide: every path constant in the tests, and every golden whose
diagnostic embeds a fixture path (`at tests/fixtures/<case>/...` appears in
most reject `stderr.txt` goldens). Expect a large refreeze whose diff must
classify into exactly one class — provenance paths — with anything else being a
finding. That is the same acceptance shape S1 used, and it worked.

`goldens/` is an OUTPUT tree keyed by test case, not module content; it stays
where it is. Only the paths embedded INSIDE goldens change.

---

# Sequencing and risks

- **After the current queue** (S1/S2 landed; T0 landed; T0b in flight; T1 next;
  then hwmv2 revision semantics, rig-schema, shield plurality).
- **Before the bridle migration**, without exception.
- **Never concurrently with a feature slice** — both parts churn golden paths,
  and a feature slice's own refreeze would become impossible to classify.
- Part A before Part B: moving modules changes which tests reference which
  fixtures, and doing B first means touching those references twice.
- T1 does NOT need to wait for this. Markers are cheap to reapply after a move,
  so marking now and restructuring later costs little; restructuring first
  would delay the split that was actually asked for.

# Part C — retire the tier-1 / tier-2 names (Tobi, 2026-07-27)

"Tier 1" and "tier 2" are design history: they record the order the two golden
layers were built, not what either one is. Rename them.

**Three axes are already in play, and the new names must not collide:**

| axis | question | values |
|---|---|---|
| SUBJECT | what artifact is frozen | ← tier-1/tier-2 lives here |
| COST | does a real build run | existing `build` marker |
| HERMETICITY | can it travel | `unit` / `integration` (T1) |

That rules out the tempting options. `built` collides with the COST marker;
`integrated` collides with HERMETICITY; `pass1`/`pass2` is accurate to
`architecture.md` but is still positional and says nothing about the artifact.

**RECOMMENDED: `emitted` / `resolved`.**

- **emitted** — what the expander itself wrote: exit code, rendered
  diagnostics, `rig-gen.overlay`, `context.cmake`, `config-sheet.md`. Frozen
  byte-exact after normalization.
- **resolved** — what a real build resolves that into: the pass-2
  `zephyr.dts`, compared STRUCTURALLY via `dts_equiv.py`, never byte-wise.

The pair is idiomatic to this codebase rather than invented for it: the
emitter deliberately emits a token SYMBOL verbatim and lets the build resolve
it (slice P), and resolution is exactly what pass 2 adds — phandles, labels,
the merged overlay. It also names the ORACLE relationship correctly: the
resolved tree is the oracle that licenses re-freezing an emitted golden, which
is the one property of the tier system worth keeping.

Carries into the layout as `test_emitted_*.py` / `test_resolved_*.py`, or as a
marker pair if the split by stage already separates them.

Alternative if `resolved` reads as overloaded (the codebase uses "resolved"
for names, boards and topology): `emitted` / `devicetree`. Weaker, because
"devicetree" is the whole domain, but unambiguous in a golden-naming context.

# Part D — rename the fixture shields (Tobi, 2026-07-27: yes)

Current names carry slice history and say nothing: `restate_fixture`,
`rev_fixture`, `paramrev`, `badyml_fixture`, `misnamed_fixture`,
`mapentry_fixture`, plus `grove_servo_flags` and `uart_probe`. Drop the
`v1b-`/`v1c-` directory prefixes and the redundant `_fixture` suffix — inside
`fixtures/` everything is a fixture.

Name each for **what it demonstrates**, which splits cleanly in two, because
the two kinds are read for opposite reasons:

- **Reference shields** (T0b's new exemplary set) — named for the PATTERN an
  author would copy: `i2c_fixed_addr`, `spi_cs_position`, `gpio_collection`,
  `parameterized_device`.
- **Anti-example shields** (exist to be rejected) — named for the DEFECT:
  `bad_revisions_block`, `node_name_mismatch`, `mapping_entry_in_revisions`,
  `nonzero_pwm_flags`.

Naming an anti-example for its defect makes "this is broken on purpose"
self-evident, so no separate `broken/` subdirectory is needed and Part B's
Zephyr-module mirror stays clean — a real module has every shield under
`boards/shields/`.

**REVISED 2026-07-28 — do Part B FIRST, then Part D, NOT together.** The
earlier advice here was to combine them on the grounds that one refreeze
classifies more easily than two. That had it backwards, because the two do not
overlap in the goldens the way it assumed:

- **Part B** changes the `at <path>:<line>` provenance lines — a PATH class.
- **Part D** changes shield names inside diagnostic MESSAGE text — a NAME class.

Separately, each refreeze has exactly ONE class and is trivially classifiable.
Combined, every changed golden line has to be attributed to one of two causes
first. Two single-class refreezes beat one two-class refreeze.

Part D is also more invasive than it looks, and that is a second reason to
isolate it: a shield's directory basename is the RESOLUTION key while its node
name is its IDENTITY, and the two must agree (`lang-shield-name`, from V1c fix
2). So renaming a fixture shield means the directory, the `.shield` filename,
the node label inside it, `shield.yml`'s `name:`, every rig instance that
references it, and every golden that names it — all in one step.

# Open questions

- Whether `emitted`/`resolved` survive as MARKERS at all once files are split
  by stage, or become redundant. The refreeze-oracle relationship must survive
  in some form regardless of where the names land.
