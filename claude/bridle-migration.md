# Bridle migration — plan

**Status: PLANNING (opened 2026-07-26). Not started.** V1/V2 finish in
`btr-shields` first (Tobi, 2026-07-26) — the fast iteration loop stays where
it is; only the finished feature migrates.

Trajectory context: design-log 2026-07-25 (the trajectory entry) and
2026-07-26b (this planning round).

## Target workspace

Tobi has prepared `/wrk/z/ws-b/` — a SECOND west workspace where **bridle is
the manifest repo**, on its own branch, with the `zephyr` project pointed at
a branch carrying our patches. This is separate from `/wrk/z/ws-up/` (where
btr-shields is the manifest repo) and unrelated to the
`btr-shields-review` worktree mechanism, which shares one workspace.

## Ground rule: no history reuse

The btr-shields history does NOT travel. Instead: **logical commits that by
and large stand on their own**, authored fresh. The commit messages and the
design log are the raw material for them.

## Commit sequence

Each row states why the commit stands alone — that is the acceptance test
for the sequence, not just an ordering preference.

| # | commit | stands alone because | depends on |
|---|---|---|---|
| 1 | connector types: `dts/bindings/connectors/*.yaml` + `include/dt-bindings/connector/*.h` + `socket`/`plug` vendor-prefixes | typed, edtlib-validated connectors, consumable by EXISTING hand-written shield overlays with no new tooling | zephyr edtlib patches (see below) |
| 2 | typed socket nodes native in bridle's own boards | the board describes each connector ONCE, typed; legacy nexuses/aliases coexist untouched | 1 |
| 3 | the `rigc` package + CLI, with unit tests and the synthetic fixtures | runs STANDALONE — `python -m rigc expand --rig X --board-dts Y` emits an overlay with no build integration at all | 1, 2 |
| 4 | build integration: the cmake forks, `module.yml`, `west build-rig`/`west rigs`, the rig resolver | `-DRIG=` works end to end | 3 + a build hook |
| 5 | the grove shields as real bridle content | **the payoff** — replaces the 64-overlay-per-shield families | 1-4 |
| 6 | rigs + the corpus golden suite | the executable contract, against content that now exists | 5 |

Tobi's preference, recorded: **stand the tool up standalone first (3), add
build-system integration only after (4).** That ordering also matches how
the tool was originally prototyped, so it is a return to a known-good shape
rather than a new risk.

## What commits 1+2 deliver on their own — and what they cannot

Verified in-tree 2026-07-26, and worth stating in the commit messages
because it answers the obvious reviewer question ("why do I need a code
generator?") with a devicetree FACT rather than a preference.

**GPIO / PWM / ADC: fully usable without `rigc`.** The socket
bindings declare real, standard nexus properties (`gpio-map`, `pwm-map`,
`io-channel-map`) with upstream-matching cell shapes. A typed socket node
therefore IS an ordinary DT nexus: a hand-written overlay can write
`gpios = <&grove_d2 GROVE_SIG0 GPIO_ACTIVE_HIGH>` and it resolves, exactly
as `arduino_header` does today.

**Buses: NOT usable without `rigc`, and this is structural, not a
gap.** Devicetree expresses bus membership by **parentage** — an I2C device
must be a CHILD node of the controller, carrying `reg = <addr>`. A nexus
only redirects cell values inside a phandle-array property, so there is no
nexus mechanism for parentage. `socket,i2c`/`socket,spi`/`socket,uart` are
`type: phandle` — pointers AT a controller, i.e. declarative metadata. To
place a device an overlay must write `&i2c1 { sensor@68 { … }; }`, naming the
controller directly, which makes it board-specific again — precisely the
composability break the feature removes.

The bus phandles still earn their place in commit 1, just not as something
overlays consume: the board declares machine-readably which controller each
socket reaches, edtlib validates the phandle resolves, and ABSENCE is
meaningful (no `socket,uart` on the Nucleo arduino header = not wired).

**Chip-select is the sharpest case for why `rigc` is unavoidable.**
`cs-gpios` IS a phandle-array, so a shield could in principle contribute a
CS entry through the socket's gpio nexus — but the SPI child's `reg` must
equal that entry's INDEX in `cs-gpios`, a global, order-dependent allocation
across every shield on the bus. That is the founding argument in the design
log ("composition is resource allocation, which no textual mechanism can
do"). Even the half that looks nexus-shaped needs global knowledge;
`socket,cs-pool` exists to feed that allocator.

Consequence for the sequence: commits 1+2 remain useful to bridle even if
`rigc` were never taken further, and commit 3's value statement is
"unlocks bus devices and CS allocation", not "generates boilerplate".

## Content triage — three ways, not two

- **Travels as REAL bridle content:** the four `grove_*` shields and the
  lotus rigs. Bridle OWNS `seeeduino_lotus` and the grove shield families —
  this is the migration's payoff. The E3 board extension DISSOLVES here:
  sockets go native into bridle's own board (design-log 2026-07-25).
- **Travels as TEST FIXTURES only:** the synthetic rejects
  (`unknown-board`, `not-rig-enabled`, `route-no-via`, `pwm-nonzero-flags`,
  `param-*`, `controller-label`). Already self-contained; they are what keeps
  `rigc` honest.
- **Does NOT travel:** the nucleo / quail / frdm board extensions and their
  rigs, the click shields, the adafruit shields — scenario playground for
  S1-S8. Candidates for samples/docs later, not for the migration.

**The coupling to watch: the test suite is tied to the playground corpus.**
Tier-1/tier-2 goldens key on the 13 rigs. If the corpus does not travel, the
`rigc` lands UNTESTED — and that suite is the only thing proving it works.
Hence tests split across commits 3 and 6: unit + fixture tests with the
tool, corpus goldens with the content. This is exactly the
upstream-destination sort B2 already performed, now put to use.

## Prerequisite: the zephyr patches

Commit 1 has a HARD dependency on the edtlib **vendor-namespaced binding
keys** patch (`1a657124349`): the socket bindings carry `plug,bus-proxies` /
`plug,positions` as top-level keys, which edtlib's `ok_top` rejects without
it. Also carried: the edtlib `*-cells` precedence BUG fix
(`c1c4d2acf2d`, PR-able on its own).

Decision to make: author commit 1 to AVOID that dependency (move the plug
contract somewhere edtlib does not police), or accept that bridle requires
the patched zephyr until the edtlib fixes land upstream. The `ws-b` zephyr
branch already carries them, so this is about what bridle can promise
downstream users, not about local feasibility.

**Carried commit #1 (`cmake-modules` module.yml key) may retire entirely:**
bridle has its own `ZephyrBuildConfiguration` hook, which can replace it.
If so, commit 4 loses a zephyr dependency and the migration needs only the
two edtlib patches. Verify before authoring 4.

## Naming — DECIDED: the board kind is `mainboards/` (Tobi, 2026-07-27)

`boards/` carries two meanings today: the root for all board-root content, and
the kind "boards" itself. Bridle shows it plainly — `shields` sits
alphabetically between `seeed` and `st`, in the vendor slot. Top-level
structure STAYS (Tobi's constraint); the fix is one level down, splitting the
kind out of the root:

```
boards/
├── mainboards/   st/ nxp/ seeed/ …   PCBs with an MCU that run Zephyr
├── shields/
└── rigs/
```

**Cost: ZERO code.** `list_boards.py:231` globs `(root / 'boards').rglob(board.yml)`
— recursive at any depth — takes the board dir as `board_yml.parent` (:233),
and reads vendor from `board.get('vendor')` (:189), i.e. from the file's
CONTENT, never its path. The vendor directory is pure organization and the
build system has never read it. `boards/shields/` and `boards/rigs/` do not
move.

**Why `mainboards` and not `hosts`:** `hosts/` was the first choice — it names
the ROLE (a shield plugs into a host; a rig names a host plus shields) and it
is already this project's word for it, as in the dual-host `ard_datalogger`
rig. It was REJECTED because "host" means the build machine in CMake and
Zephyr (host tools, host compiler, native_sim on the host), and that collision
is live in this exact domain. `mainboard`/`daughterboard` is the older and
unambiguous naming of the same relation, and a shield IS a daughterboard.
Rejected too: `bases/`, which collides with the extension vocabulary already
in use ("the REAL base board dts", in every `boards/extend/*` header), and
`targets/`, which recreates the residual-category error since a rig is a
target as well.

Consequence, free rather than structural: `boards/extend/` currently sits in
the vendor slot itself. Once vendors move under `mainboards/`, extensions may
sit at `boards/mainboards/extend/<vendor>/` or inline under their real vendor
(`boards/mainboards/st/nucleo_f401re_rig/`) — rglob does not care.

## Naming — DECIDED: the tool is `rigc` (Tobi, 2026-07-26)

`rigexp` was an internal project name. The upstream name is **`rigc`**, by
analogy to `dtc`: in this ecosystem that analogy carries the two things a
converter-shaped name (`rig2dts`, `rig2overlay`) would have hidden — that the
tool REJECTS invalid input (the analyzer's `phys-*` diagnostics are its
primary value, not a side effect), and that it emits SEVERAL artifacts
(overlay, config sheet, expectations, the includes fragment, and a designed
Kconfig fragment) rather than one. `rig2dt` was additionally dropped on a
technicality: `dts` is the established word for devicetree SOURCE, `dt` is
the abstract tree, and what the tool writes is a `.overlay` in dts syntax.
Cost accepted: `rigc` is cryptic to a newcomer.

Renames that follow, to apply while authoring commit 3:

- `scripts/rigexp/` → `scripts/rigc/`; every import; `python -m rigc expand`
- `RIG_EXPAND_PYTHONPATH` / `RIG_EXPAND_COMMAND` → `RIGC_PYTHONPATH` /
  `RIGC_COMMAND`
- mypy exemption keys, `check.sh`, docs

Deliberately NOT renamed:

- **the generated artifacts stay `rig-gen.overlay` / `rig-gen-includes.dtsi`
  / `rig-gen.conf`.** An artifact is named for what it is generated FROM, not
  by — zephyr writes `zephyr.dts`, not `dtc.dts`. The `-gen` infix already
  carries "generated counterpart of the hand-authored file".
- the `Rig:` cmake message prefix — it reports on the rig, not the tool
- `west build-rig` / `west rigs` — UI, mirroring `west build` /
  `west shields`; a separate decision, and they should stay
- `.shield`, `rig.yml`, `<rigname>_defconfig`, `shield-templates`, the
  `lang-*`/`phys-*` diagnostic codes — all unaffected

**Terminology consequence:** "the expander" retires as a NOUN for the tool —
the tool is `rigc`. "Expansion" survives as the phase/verb, which the CLI
already uses (`rigc expand`), and the internal pipeline stays
loader → analyzer → emitter. `architecture.md` defines "expander" as a
toolchain term and needs updating when the migration commits are authored.

Riding along, per parked.md: the `_rig_*` cmake prefix **re-idiomization**
(function-wrapped module body with explicit `PARENT_SCOPE` exports, matching
`pre_dt_module_run()` / `zephyr_process_snippets()`) is explicitly parked
"until patch-drafting time" — this is that time, so it belongs IN the
recreated commits, not as a follow-up.

## PRE-MIGRATION TASK — the sweeps missed the bindings

Both comment sweeps (`1c8068f`, `df98521`) scoped cmake, production Python,
tests, `.shield` and `rig.yml`. **`dts/bindings/connectors/*.yaml` and
`include/dt-bindings/connector/*.h` were in NEITHER**, and they carry the
heaviest archaeology in the tree: `grove.yaml`'s `description:` cites
"Bridge-A rewrite phase 2a", "Slice A / ontology Refinement 1", "the trial's
modules", "authored in 3a" and a carried-commit hash;
`include/dt-bindings/connector/arduino-r3.h` has 27 hits.

These are the MOST public artifacts in the migration — a binding
`description:` is the first thing an upstream reviewer reads, and it ships to
every consumer of the connector type. **Sweep them before authoring commit
1.** Same two rules as the other sweeps; note a binding description is
user-facing documentation, so it should also read as documentation rather
than as a design record.

## PRE-MIGRATION TASK — shield plurality: bridle has N shields per folder, we allow 1

**The constraint.** Our rig-template discovery requires exactly one shield
per folder, named after it (`<dir>/<basename>.shield`,
`loader_yml.load_shield_library`), with identity taken from the DT node name.
Upstream permits N per folder two ways, and **bridle uses the second**:

- **shield.yml plural form** — names listed explicitly under `shields:`, all
  sharing `dir` = the folder (`list_shields.py` `find_shields_in`).
- **the legacy fallback** — no shield.yml at all: if `Kconfig.shield`
  exists, EVERY `*.overlay` becomes a shield named after the overlay
  BASENAME. Identity by filename parse, listed nowhere.

**Bridle is entirely legacy: ZERO shield.yml in 19 shield folders.** So the
migration authors shield.yml for every ported shield regardless — which is
also where `template: true` and (post-V1c) `revisions:` have to go.

**The triage, and it is good news.** Each multi-overlay folder decomposes
onto an axis we already have or are building, so plurality is mostly NOT a
gap to implement:

| bridle folder | overlays | decomposes to |
|---|---|---|
| `grove_btn`, `grove_led` | 64 each | position (d0..d31) becomes the rig-level socket/pin choice; `_inv` becomes the `invert:` flag. **The product collapses to ONE template** — this is the bridle-64-overlays product argument, mechanized |
| `sc16is75x_bb` | 8 | 750/752 × i2c/spi × irq/noirq: part = variant, bus = which socket it plugs into (rig-level), noirq = config flag. The 64-overlay pathology in miniature |
| `grove_sens` | 3 | bme280 / bmp280 / dps310 — a sensor swap in one slot: **variants**, literally the spec's own rule-12 example |
| `waveshare_pico_10dof_imu_sensor` | 2 | `_r1` / `_r2` — **shield revisions**, the real-world case V1c was designed for |
| `tcs-604` | 2 | `_ard` vs `_x_grove_testbed` — which carrier it plugs into: rig-level socket choice, not a shield distinction at all |
| `grove` | 4 | `seeed_grove_base_v1/v2` (revisions) + `rpipico`/`xiao` carriers (different hosts) |
| `rpi_pico_bb` | 2 | bb vs bb_plus — part variants |
| `loopback_test` | 2 | base + `_tmph` — optional add-on |
| `rpi_pico_lcd` | 11 | eleven DIFFERENT vendor+size LCDs sharing a folder. **The residue** — genuinely distinct hardware, no axis applies |

**So the decision needed is only about the residue** — and for `rpi_pico_lcd`
the answer is to ADOPT the plural `shields:` declaration, not to fan out into
eleven folders (Tobi, 2026-07-26). Everything else is a modelling win the
migration should BOOK rather than port: porting `grove_btn` as 64 shields
would carry the exact duplication the rig model exists to remove.

**Why plural is the right answer and not a compromise.** The plural list
DECLARES THE NAME SET; it does not map name to filename. `list_shields.py`
yields `(name, dir)` pairs — all N names sharing one dir — and
`shields.cmake:96-114` then CONSTRUCTS `<dir>/<name>.overlay` and
`<name>.conf` from the name. That is Q6's own construct-don't-parse
discipline, which also makes bridle's legacy mode its exact inverse: there
the name is DERIVED by parsing the overlay filename.

**Cost, checked rather than estimated:**

- **cmake needs nothing** — `cmake/dts.cmake:487+` already consumes the
  `(name, dir)` JSON like upstream and constructs `<name>.conf` from the name.
- **One function changes** — `loader_yml.load_shield_library`, whose
  `<dir>/<basename>.shield` lookup is the only 1-per-folder assumption.
- **`parse_shields` is already N-capable** — it iterates every node under the
  `shield-templates` wrapper.

**Two constraints on the shape:**

- **N FILES, not N nodes in one file.** Ground rule 3 gives each `.shield` its
  own translation unit so labels are shield-scoped and `gl_plug` may be
  reused; eleven LCD nodes in one TU would force cross-shield label
  prefixing, which is exactly what ground rule 3 exists to avoid.
- **Identity authority must be RULED, not inherited.** Today
  `Shield.name = node.name` (`shields.py`), with folder, filename and node
  name kept consistent by requiring agreement. Plural drops the folder out of
  that triple. Ruling: **the declared name in shield.yml is the authority**
  and a mismatching node name is a loud diagnostic — matching upstream, where
  shield.yml `name:` is what `-DSHIELD` matches and what `list_shields`
  reports.

**Second edge of that ruling, and it is load-bearing: the template SELF-FILTER
changes.** `load_shield_library` today uses `<basename>.shield` presence as
the discriminator that lets it scan a whole `boards/shields` tree and pick up
ONLY rig templates, silently skipping legacy shields (which ship a
`<name>.overlay`). Once names come from shield.yml rather than the folder,
that filter no longer holds, and the discriminator must become the
`template: true` marker in shield.yml — which is exactly what that marker was
introduced for (`9af9fb3`, rig-template-marker preference). Expect this to
show up as a diagnostic-quality question too: a folder declaring
`template: true` but shipping no `<declared-name>.shield` should say so by
name.

**Recorded risk:** the collapse is only a win if the axes it relies on are
in place — the `invert:` flag (deliberately NOT folded into `params:` at
slice P, since it is a flag transform rather than a property assignment) and
per-instance parameters both have to carry the 64-overlay case. Verify that
against `grove_btn` BEFORE committing to the collapse in the migration
sequence, because the fallback (port the product as-is) is much worse than
discovering the gap early.
