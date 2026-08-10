# Shield plurality — N shields declared in one folder

**Status:** briefed 2026-08-10, not started. Backlog item 8, the last
pre-migration task before BRIDLE MIGRATION (item 9). Design inputs:
`bridle-migration.md`'s "PRE-MIGRATION TASK — shield plurality" section
and `ontology.md`'s Q6 row (both predate the rulings in §2, and §2
CORRECTS one of them by name).

## 1. What's already there, verified rather than assumed

Everything in this section was read in the tree today, not recalled.

- **The schema already allows it.** `zephyr/scripts/schemas/shield-schema.
  yaml` defines one `$defs/shieldSchema` and offers it under BOTH `shield:`
  (mapping) and `shields:` (array), with a `dependentSchemas` rule making
  the two mutually exclusive. Upstream `b836fcdd709` brought the plural
  form; this project's own two commits on top — `3f205005b99`
  (`template:`) and `8da5b3a0f60` (`revisions:`) — put both keys INSIDE
  that shared `$defs`, so a plural entry may already carry either.
  `additionalProperties: false` at both levels. **No schema work in this
  slice.**
- **`list_shields.py` already emits it.** `find_shields_in`
  (`zephyr/scripts/list_shields.py:66-110`) reads shield.yml, validates,
  and branches: `shields` → one `Shield(name, dir)` per entry, all sharing
  `dir`; `shield` → one. Legacy fallback (no shield.yml, `Kconfig.shield`
  present, every `*.overlay` becomes a shield named after the overlay
  basename) is untouched by this slice and stays not-owed-and-never
  (`ontology.md`'s Q6 row: it DERIVES identity by parsing a filename).
- **cmake already consumes it.** `cmake/dts.cmake:687-700` runs
  `list_shields.py --json`; `:705-725` collects
  `_rig_shield_candidate_dirs_<name>` per NAME, so N names sharing one dir
  is already the shape it handles. Its collision resolution
  (`:727-770`) probes `${cand}/${shield_name}.shield` — constructed from
  the NAME, so it stays correct under plurality unchanged.
  `bridle-migration.md`'s "cmake needs nothing" holds; re-verified.
- **The 1-per-folder assumption is exactly two lines.**
  `loader/library.py:364-365`: `name = os.path.basename(shield_dir)` then
  `base_file = os.path.join(shield_dir, name + ".shield")`. Everything
  downstream is already name-keyed (`_Pending.base_file` is a path handed
  in; `ShieldLibrary.pending`/`axes`/`ymls` are `Dict[name, ...]`).
- **`parse_shields` is N-capable per translation unit**
  (`shields.py:46-60`, iterates every node under `shield-templates`) but
  **ground rule 3 still gives each shield its own file** — N FILES, not N
  nodes in one file, so labels stay shield-scoped and `gl_plug` may be
  reused. That docstring's "exactly one shield node" claim stays true.
- **Identity is ALREADY name-first, not node-first.** `_pick_shield`
  (`library.py:278-296`) does `parsed.get(name)` and errors when the TU
  defines no node of that name. So `bridle-migration.md`'s "identity
  ruling" is, mechanically, already implemented — what changes is only
  where `name` comes from, and what the diagnostic SAYS.

### The census that corrects the recorded plan

`bridle-migration.md` predicts the discovery self-filter "must become the
`template: true` marker in shield.yml". Measured today:

| fact | count | command |
|---|---|---|
| folders carrying a `<basename>.shield` | 27 real (+1 non-library dir) | `find . -name '*.shield' \| xargs -n1 dirname \| sort -u` |
| of those, carrying NO shield.yml | **12** | same list, filtered on `! -f shield.yml` |
| shield.yml files in the tree | 18 (14 corpus + 4 fixture) | `find . -name shield.yml` |
| of those, declaring `template: true` | **18 — all of them** | `grep -l 'template: true'` |

The 12 yml-less folders are all fixtures (`reference-shields/`,
`multibus-sockets/`, `shield-node-name-mismatch/`,
`shield-lazy-parse-preserves-priors/`, `param-shield-no-includes/`,
`pwm-nonzero-flags/`, `shield-uart-subset/`, `boards/shields/
restate_fixture`). Requiring shield.yml for discovery would mean authoring
12 new fixture files for no test value. **Re-derive both counts yourself
before relying on them** — that is this project's standing rule and it has
caught a wrong count three times.

## 2. Rulings (Tobi, 2026-08-10)

1. **Two discriminators, one per case — NOT "`template:` replaces the
   marker file".** When a folder has a shield.yml, `template: true` is
   what discriminates a rig template from a legacy overlay-style shield
   (dozens of which exist in bridle and upstream zephyr, and which will
   increasingly ship a shield.yml of their own). When a folder has NO
   shield.yml, the `<basename>.shield` marker file is the discriminator,
   exactly as today. This CORRECTS `bridle-migration.md`'s prediction,
   which assumed one rule would serve both.
2. **`lang-shield-name` is reworded, and its golden is a classified
   diff.** The current message says a node name "must match the folder it
   lives in" — false the moment a folder declares names. Reword to speak
   of the name declared FOR the shield, naming shield.yml as the source
   when that is where the name came from.
   `goldens/shield-node-name-mismatch/stderr.txt` is hand-edited. This is
   the slice's ONLY stderr churn, and stderr is byte-exact permanently by
   ruling — so it is a product decision, made here, not a refreeze.
3. **The corpus gains a real plural folder**, exercised end to end — not
   fixtures alone. See §5.

## 3. The discovery rule, as one algorithm

Replaces `library.py:359-378`'s loop body. For each folder under each
shield-library root, in sorted order:

```
shield.yml present?
├── no  → name := folder basename                        (today, unchanged)
│         discovered as a rig template iff <dir>/<name>.shield exists
│         (absent: skip silently — it is a legacy shield or not a shield)
└── yes → for each entry under `shield:` (one) or `shields:` (N):
          name := entry's `name:`
          entry declares `template: true`?
          ├── no  → NOT a rig template: skip (a legacy shield with metadata)
          └── yes → discovered; base_file := <dir>/<name>.shield
                    base_file missing → LOUD DIAGNOSTIC naming the entry
                                        and the path it expected
                    `revisions:` read from THIS ENTRY, not the folder
```

Three consequences worth stating because each is a decision, not a
detail:

- **A yml-carrying folder without `template: true` stops being
  discovered.** Measured above as unobservable in this tree (18/18 declare
  it), but it IS a behaviour change and it wants a test that pins it.
- **`template: true` with no `<name>.shield` becomes an error where it is
  a silent skip today.** This is the "say so by name" case
  `bridle-migration.md` predicted, and it is the only genuinely new
  diagnostic in the slice. Give it its own code; do not overload
  `lang-shield-name`, which is about a TU's node.
- **`discover_shields` must NOT simply follow `pending`.**
  `promote.py:94-106` derives its name set from `lib.pending` today. If
  non-template names leave `pending`, `check_promotable`'s precise error
  (`promote.py:327-329`, "shield.yml does not declare 'template: true'")
  becomes unreachable — `--promote <legacy>` would degrade to "no such
  shield". Keep that message reachable: `discover_shields` enumerates
  DECLARED names with their flags (it already opens shield.yml itself,
  `promote.py:101-103`), while `load_shield_library` populates
  `pending`/`axes` with templates only. This is the Sec-4
  two-authorities-on-purpose split doing its job; the split is preserved,
  not collapsed.

## 4. Scope — VERIFY EVERY PATH

**This list is a prediction, not a guarantee.** Every dispatch in this
project that found an out-of-list item found it by RUNNING mypy/pytest or
grepping call sites, never by re-reading the brief harder. Trace the
actual callers.

Production, expected:

| file | what |
|---|---|
| `scripts/rigc/loader/library.py` | the scan loop (§3); `_load_shield_revisions` becomes per-ENTRY, not per-folder (its `owner=` string currently interpolates `os.path.basename(shield_dir)`:317 — that must become the declared name); `_pick_shield`'s message (ruling 2) |
| `scripts/rigc/promote.py` | `discover_shields`'s name enumeration (§3's third consequence); `ShieldInfo`'s docstring, which today asserts the `<name>.shield` marker is "the single authority for 'is this a shield at all'" — no longer true and must be rewritten, not left stale |

Suspect but unconfirmed — check each, and report what you find either
way: `loader/__init__.py`'s `load_shield_library` call site,
`west_commands/rigs.py` (`--boards-for`, `--explain`), `cli.py`,
`cmake/dts.cmake`'s dependency registration for shield.yml
(`:582` comment), `doc/tutorials/write-a-shield-template.rst` (the only
doc page naming shield.yml).

Tests, expected (`test_<module>.py` mirrors the production module — the
named unit must be the subject):

- `scripts/rigc/tests/unit/loader/test_library.py` — the scan's own unit
  tests (`:478+`).
- `scripts/rigc/tests/unit/test_promote.py` — `discover_shields` /
  `check_promotable`.
- New fixtures under `scripts/rigc/tests/fixtures/boards/rigs/` following
  the existing shape, one per rejection: a `template: true` entry with no
  `<name>.shield`; a plural folder whose `<name>.shield` node name
  disagrees with the declared name (the DECLARED-name half of ruling 2 —
  the existing `shield-node-name-mismatch` fixture covers the folder-name
  half and must keep working); a duplicate name within one `shields:`
  list; a `shields:` entry missing `name:`. Note rigc parses shield.yml
  with its own `parse_marked`, NOT jsonschema — malformed shapes are this
  code's problem, not the schema's.
- One ACCEPT fixture: a plural folder both of whose shields a single rig
  references.

## 5. The corpus example (ruling 3)

One new folder under `boards/shields/`, declaring **two** shields via
`shields:`. Constraints, in priority order:

1. **The folder name must equal neither declared name.** This is the
   slice's real falsifier: with a folder named after one of its shields,
   the old folder-basename path could still be what is working.
2. **Two genuinely distinct devices** — different `compatible`, different
   interface — so the folder is the RESIDUE case
   (`bridle-migration.md`'s `rpi_pico_lcd`, eleven distinct LCDs in one
   folder), not a variant/revision/socket axis in disguise. If an existing
   axis would collapse it, it is the wrong example.
3. **`shield,plugs = "arduino-r3"`.** Measured: `frdm_k64f` and
   `nucleo_f401re` each offer exactly one arduino-r3 socket and both are
   twister platforms here, so both shields promote with no `:socket=`
   disambiguation. (mikrobus would drag in quail's four-socket ambiguity;
   grove would drag in the lotus/bridle platform gap.)
4. **Minimal.** No new bindings, no drivers, no Kconfig beyond the
   `SHIELD_<NAME>` symbols. Fictional `vnd,*` compatibles are the corpus's
   established style (`temp_click.shield` says "hypothetical" in its own
   header).

A concrete instantiation that satisfies all four, offered so you need not
re-derive one — take it or improve on it, but state which:
`boards/shields/arduino_lcd/` declaring `lcd_char_1602` (GPIO-only
character LCD) and `lcd_tft_24` (SPI TFT plus a couple of GPIOs).

**Two things to VERIFY rather than assume about this folder:**

- **`Kconfig.shield` with two symbols in one folder.** One folder now
  serves N names. Check how `SHIELD_DIRS` / the Kconfig collection treats
  a dir that appears once for two names, and that both
  `SHIELD_LCD_CHAR_1602` and `SHIELD_LCD_TFT_24` actually turn on.
  `shields_list_contains` takes the NAME, so the shape should work — prove
  it, do not reason about it.
- **Per-name `<name>.conf`.** `cmake/dts.cmake` constructs `<name>.conf`
  from the name; with one dir and two names there are two possible conf
  files. Confirm the one that exists is picked and the absent one is not
  an error.

**Twister suites are OPTIONAL here.** Add them only if the two shields
build unchanged on `frdm_k64f/mk64f12/rig` and `nucleo_f401re/
stm32f401xe/rig`; if they do not, say why in the report rather than
forcing it. Either outcome is acceptable — an unreported skip is not.

## 6. Acceptance criteria

1. A folder declaring `shields: [A, B]`, where the folder is named neither
   A nor B, yields exactly two discovered rig templates, each parsing its
   own `<name>.shield` translation unit.
2. A rig referencing A and B by name loads, expands and emits, with A and
   B resolving to their own templates.
3. `west rigs --boards-for A` and `--explain A` answer for a plural name;
   `rigc expand --promote A` promotes one.
4. **`test_singleton_identity_law.py`'s census picks the two corpus names
   up automatically** (it is parametrized over a DERIVED domain of
   promotable shields) and the law holds for both. This is the slice's
   strongest end-to-end criterion and it costs nothing to state — but it
   means both corpus shields must genuinely promote and pass, so run that
   module.
5. Each rejection in §4 produces its own diagnostic with a byte-exact
   golden, and the NEW `template: true`-without-a-template error names
   both the entry and the path it expected.
6. **The 12 yml-less fixture folders are untouched and still discovered.**
   Zero new fixture shield.yml files. If you find yourself authoring one,
   the discovery rule has been implemented wrong.
7. Golden impact, classified — see §7. Anything outside that classification
   is a finding to report, not a refreeze.

## 7. Golden impact, classified in advance

- **`goldens/shield-node-name-mismatch/stderr.txt`** — the ONE permitted
  stderr change, ruling 2. Hand-edit it. `RIGC_REFREEZE=1` is BLOCKED by
  the harness permission classifier in this environment; expect to hit
  that block and work from the failure list instead.
- **New golden directories** for the new fixtures — additions, not diffs.
- **Everything else must be byte-unchanged.** In particular no
  `context.cmake` / `RIG_DEPENDS` movement for the 14 existing shields:
  the new corpus folder is additive and nothing existing references it.

Verify the hand-edited golden BOTH ways, as S5 established and as this
project has since relied on twice: (a) the reject test passes, and (b)
applying only the intended wording change to HEAD's version of that file
reproduces the working tree exactly. (a) alone would pass against a golden
edited to match a wrong output; (b) alone would not prove the tool agrees.

## 8. Out of scope — named, not silently skipped

- **Cross-folder / cross-root duplicate names.** Today `pending[name] = ...`
  silently last-wins across roots, and `cmake/dts.cmake:727+` has its own
  deliberate warn-and-pick resolution for the real
  `adafruit_data_logger` collision between this module and zephyr. Do NOT
  hard-error on that. A duplicate WITHIN one `shields:` list is in scope
  (§4) because plurality is what makes it newly reachable.
- **The legacy overlay-basename fallback** — not owed, and never
  (`ontology.md` Q6).
- **shield.yml unknown-key tightening** — that is backlog item 7
  (`rig-schema.yaml`), which deliberately holds this debt for every
  retired key at once.
- **`shields.py`'s `_parse_exposed` 3-kind vocabulary** — carried from the
  multi-bus slice, still not this one's business.

## 9. Reduced gate contract

Run: `mypy`, the unit tier, the non-build integration tier, and
`test_singleton_identity_law.py`, because it is the module that OBSERVES
criterion 4, the slice's strongest criterion. (The rule, learned in S5:
the reduced contract must name the module that observes the acceptance
criteria, which is not always the module the code lives nearest.)

**CORRECTION, found by the implementor 2026-08-10:** this section
originally called `test_singleton_identity_law.py` "the one build-marked
module". It carries no `@pytest.mark.build` — its own docstring says so
("NOT build-marked: no configure, no toolchain") — and it is already
inside the non-build tier. `test_emitted_rejects.py` carries no build
mark either. **This slice therefore has no build-marked module that
observes its criteria at all**, which is a fact about the slice, not an
omission to fix: everything it changes is observable without a
toolchain. Naming a build module by reflex is the failure mode; check the
marker.

The driver runs the FULL gate once, independently, after review — the
build tier is ~100% of the cost, which is why it is not yours to run in
full.

## 10. Applied after review (driver, 2026-08-10)

Two findings landed on top of the implementor's work, one from the
reviewer and one from the driver's own probing:

1. **`promotable[name]` records what an entry DECLARED, never that a
   template was found.** A `template: true` entry with no
   `<name>.shield` stays in `ymls`/`promotable` while never entering
   `pending`, so `discover_shields` reports it with `template=True` and
   `check_promotable` passes it — deliberately, since the scan's own
   `lang-shield-template` finding already says precisely what is wrong
   and a second vocabulary would duplicate or contradict it. Promotion
   then fails at load, where the name genuinely cannot resolve.
   Documented on the field and pinned by a test; it was neither before.
2. **A `shields:` block that is not a list was dropped SILENTLY** — the
   one-dash-short typo. Every name in the folder vanished from the
   namespace with no diagnostic, and the only later symptom was an
   instance's `shield:` reference failing to resolve, blaming the
   innocent rig. Now a `lang-schema` error with its own fixture and
   byte-exact golden (`shield-plural-not-a-list`).

**A property of this whole reject-fixture family, worth knowing before
writing another one:** its rigs declare `instances: []` and `run_expand`
resolves no real board, so expand exits 1 EITHER WAY — via the intended
diagnostic, or via `phys-board` once the load gets that far. The
`assert result.returncode != 0` line is therefore nearly vacuous; the
stderr assertions and the golden are what actually discriminate.
Verified by building the control fixture and running it, after a first
control run from outside the tree produced a `phys-board` exit that
proved nothing.
