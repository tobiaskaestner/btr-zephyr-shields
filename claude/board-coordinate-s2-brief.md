# S2 — `--boards-for`, enumeration as a query

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md` §9
(rulings 4–8, Tobi, 2026-08-05); design source: `board-as-invocation-
coordinate.md` §5 ("Tobi: ship it"). This is step 2 of §9.5's revised
sequence.

Read §9.4 of the parent first — it is why this slice is a PREREQUISITE
rather than an optional nicety. Once `board:` leaves rig.yml (S6), the
declared tuple list is gone and `west rigs`'s board column with it.
`--boards-for` is what enumeration BECOMES, so it must exist before
enumeration is at risk.

## 1. What this slice is

`west rigs --boards-for <rig-target>` prints the boards whose typed
sockets satisfy that rig. Nothing else about the product changes: no
rig.yml is edited, no corpus content moves, no cmake file is touched, and
nothing in the emit path is reached.

**It is a QUERY, not a build check** — see §3, which bounds the claim
precisely. Getting that boundary honest is the main design content of the
slice; the code is small.

## 2. Acceptance criteria

1. **ZERO golden churn.** `git diff --stat` on
   `scripts/rigc/tests/goldens/` empty. Not by assertion. Nothing this
   slice adds is reachable from `rigc expand`.
2. `west rigs` with no `--boards-for` behaves **exactly** as today — same
   lines, same `-f/--format`, same `-n/--name`.
3. `west rigs --boards-for nucleo_datalogger` prints exactly
   `nucleo_f401re/stm32f401xe/rig`; `--boards-for lotus_buttons` exactly
   `seeeduino_lotus/samd21g18a/rig`; `--boards-for quail_temp_farm`
   exactly `mikroe_quail/stm32f427xx/rig`.
4. The census agrees with the REAL board devicetree, proved by a
   build-marked cross-check against `board_edt`'s own projection (§6).
5. The conventional-label lint of `d47ec86` still holds, still falsified
   by mutating a real board file — now expressed over production code
   rather than its own private regex (§5.3).
6. mypy clean (86 files today → 87), unit suite green, coverage at or
   above the `fail_under = 88` floor (90% today).

## 3. The claim the command makes — bound it before writing code

Reading a board's REAL devicetree needs cpp + edtlib + a `BuildRecipe`,
and `boarddt._discover_board_dts`'s own docstring records that the
standalone catalog is **always empty** for every board this tooling can
build: they are all hwmv2 extensions whose base lives outside
`MODULE_ROOT`, and `list_boards.find_v2_boards` never sees them from a
`MODULE_ROOT`-only scan. A real per-board read therefore costs a real
cmake configure per candidate board. That is not a query.

So the census is over the board rig-extension **sources**, exactly as the
design doc says ("scans board rig-extensions, censuses their typed socket
labels"), and the answer it gives is:

> **the boards whose typed sockets satisfy this rig's socket
> requirements** — reference resolution (defining label or conventional
> alias), connector-type mating, bus subset exposure, and stackability.

It is NOT a promise the rig builds there. GPIO position routing, CS-pool
allocation, address domains and net analysis are all outside it, because
the census cannot see them. Say this in the `--help` text in one sentence;
do not let the help imply more.

This bound is not a weakness to apologise for — it is the same necessary
condition upstream has wished for and has no answer to today. The
sufficient condition is a configure, which the user can then run.

## 4. Design — reuse the matching rule, never restate it

The temptation is to write a comparison loop: "does the board have a
socket of the right type". Do not. `analyzer/sockets.py::resolve_sockets`
already IS that rule — mating, bus subset, alias-aware resolution,
carrier composition, stackability — and it is a pure function over
`(Rig, Board, types)`.

**So the census's job is to produce a `model.Board`, and conformance is
`resolve_sockets` returning no errors.** One implementation of the rule,
forever.

### 4.1 The partial Board — name it, document it, and guard it

A text census can populate only some of `BoardSocket`. The census Board
carries:

| field | census value |
|---|---|
| `label` | the node's DEFINING label (`labels[0]`) |
| `type_name` | from `compatible = "socket,<type>"`, **dashes KEPT** |
| `buses` | one key per `socket,i2c` / `socket,spi` / `socket,uart` present |
| `src` | the fragment file + line |
| `path` | the node name, as `/<node name>` |
| `gpio_map`, `pwm_map`, `adc_map`, `cs_pool` | **empty / None** |

and `Board.aliases` gets every additional label, exactly as
`board_edt.project_edt` builds it.

**The dash trap:** `board_edt._project_socket` sets
`type_name = compat.split(",", 1)[1]`, so the value is `"arduino-r3"`,
dashed. The existing lint's `_socket_nodes` helper returns the UNDERSCORED
form because it is comparing against a LABEL convention. The census must
produce the dashed form (it feeds `mating_ok` against
`shield.plugs = "arduino-r3"`); underscoring belongs only inside the
label-convention check. Two different strings for two different jobs — a
single `.replace()` in the wrong place makes every board conform to
nothing, or every mating silently fail.

Write the docstring so a reader cannot mistake this Board for a real one:
say which fields are populated, and that its only valid consumer is
`resolve_sockets`. §6's cross-check is what keeps that promise true.

Consequences worth knowing before you are surprised by them:

- an empty `gpio_map` is harmless for carrier rigs — `compose_socket`
  treats an unrouted parent position as socket-local and carries on. Bus
  pass-through still checks, which is the part that matters.
- `resolve_sockets`'s stackability sweep indexes `types[type_name]`. It is
  only reached for a socket two instances mate, which required
  `mating_ok`, which required a shield to plug that type — and `shields.py`
  already rejects an unknown plug type at load. So no `KeyError` is
  reachable, but do not "defend" against it with a silent `.get`.

### 4.2 Board targets come from `board.yml`, constructed not parsed

Every board rig-extension in the tree has the same shape:

```yaml
board:
  extend: nucleo_f401re
  variants:
    - name: rig
      qualifier: stm32f401xe
```

→ target `nucleo_f401re/stm32f401xe/rig`, which is exactly the string the
corpus rig.yml files declare and the string ruling 2 says users type. Join
the declared parts; never parse a directory name. A `board.yml` this rule
cannot turn into a target is **skipped** — the census's scope is board
rig-extensions — and that skip gets a unit test, so it is a decision
rather than an accident.

A board.yml declaring several variants yields several targets over the
same socket set. That falls out; do not special-case it.

### 4.3 Which files the census reads

Every `*.dts` and `*.dtsi` **directly beside** the `board.yml` (not
recursive). In today's tree each board keeps its sockets in exactly one
`.dtsi` (`arduino_r3_socket.dtsi`, `mikrobus_sockets.dtsi`,
`grove_sockets.dtsi`), included from the `_rig.dts` hub — but a socket
authored straight into the `.dts` is equally valid, so read both rather
than encoding today's filenames.

Regex, not dtlib, and the existing helper's docstring already says why: a
fragment may reference a node its own file never defines (lotus's
`adc0: &adc {};`), so it is not standalone-parseable outside a real board
build. Every socket node in this tree is a childless leaf, which is what
makes a brace-balanced regex exact for the shape.

### 4.4 Root discovery

Default `[MODULE_ROOT]`, scanning `<root>/boards/**/board.yml`. The west
front end already assembles every module board root (`rigs.py:109-116`) —
thread those through rather than hardcoding.

## 5. Code

### 5.1 The new unit: `scripts/rigc/board_census.py`

Three functions, split on the ratified **IO at the edges** line:

- `census_board(board_yml_text, fragments) -> list[CensusBoard]` — **pure
  over text values**. `fragments` is a list of `(filename, text)`. A pure
  function over data beats a mocked filesystem; this is where the interesting
  unit tests live.
- `census_boards(board_roots=None) -> list[CensusBoard]` — the edge: globs,
  reads, delegates to the above. Sorted by target.
- `boards_for(rig, types, boards) -> list[BoardVerdict]` — **pure**. Runs
  `resolve_sockets` per board; `conforms` is `not has_errors(diags)`.
  Return the diagnostics, not just the boolean: a later `--explain` (S3)
  and any "why not this board" affordance both want them, and returning
  them costs nothing now.

`CensusBoard` = `(target, dir, board)`. Public functions state return
semantics and ownership in prose, per the standing convention.

### 5.2 The surface: `west rigs --boards-for <rig-target>`

`scripts/west_commands/rigs.py`. The argument is a rig target
`name[@rev][/variant]`, resolved with `list_rigs.resolve_rig_target` — do
not re-derive axis resolution, it is already written and already the
cmake-facing seam.

- resolved rig dir → `rig.yml` → `rigc.loader.load(rig_yml, workdir,
  types=..., revision=..., variant=...)`, in process. Verified working
  standalone with no `--include-dir` and no board: `dtsio` always appends
  `ZEPHYR_INC`/`MODULE_INC`, and `registry.load_types()` defaults to the
  module's own bindings. Five corpus rigs load in 0.21 s total.
- print one conforming board target per line, sorted; nothing and exit 0
  when none conform (an empty answer is a fact, not an error).
- rig fails to load → render its diagnostics to stderr, exit 1.
- `--boards-for` short-circuits the listing; `-f`/`-n` do not apply to it.
- the loader takes a workdir — use `tempfile.mkdtemp` and **remove it**
  (D10's rule: the tool does not leak a workdir per invocation).

`--rigs-for <board>`, the inverse query, is **out of scope**: it is the
same census read backwards but needs every rig loaded, and it is not on
§9.5's critical path. Note it in the module docstring as the deliberate
non-implementation.

### 5.3 Retire the lint's private regex

`tests/unit/test_board_edt.py` carries `_SOCKET_NODE_RE`, `_socket_nodes`
and `_conventional_label_offenders` (lines ~223-299) — the census this
slice is promoting to production. Move the node-scanning half into
`board_census.py` and have the lint consume it, so there is one scanner.

Keep the lint EXACTLY as strong: it is census-style, falsified by mutating
the WORLD it observes, and `test_conventional_label_offenders_detects_a_
missing_alias` (the mechanism check on synthetic text, run before trusting
the checker on the real tree) must survive the move. Re-verify the
falsification after moving: drop `arduino_r3` from nucleo's real
`.dtsi`, confirm that test and only that test fails, restore against a
hash taken BEFORE the mutation, purge `__pycache__`.

Whether the label-convention predicate itself lives in production or stays
in the test file is your call — the scanner is the part that must be
shared. If it stays in the test, say so in the report.

### 5.4 One unrelated fix that this workflow needs

`tests/integration/test_board_read.py::test_edt_pickle_cross_check` cannot
be run on its own: `pickle.load` needs `devicetree` importable, and
nothing in that module puts it on `sys.path` first, so a standalone run of
the file fails 4/12 with `ModuleNotFoundError: No module named
'devicetree'` (verified; passes with the path exported). Call
`edt_build.ensure_devicetree_on_path()` before the unpickle — the
production idiom, already used by `board_edt`.

This is in scope because §7's verification contract runs that module
alone. It is a test-harness ordering fragility, not a product bug.

## 6. Tests

### Unit — `scripts/rigc/tests/unit/test_board_census.py`

(`test_<module>.py` mirrors the production module: the named unit is the
subject.) Over dedented triple-quoted text blocks, never `\n` escapes:

- a socket node with two labels: `sockets` keyed by the defining label
  only, the second label in `aliases`;
- `type_name` is the **dashed** form (§4.1's trap, pinned);
- buses: `socket,i2c`/`socket,spi`/`socket,uart` present → keys; a socket
  declaring none → empty `buses`;
- target construction from `extend` + `variants`; a two-variant board.yml
  yields two targets over one socket set;
- a `board.yml` with neither shape is skipped;
- sockets are collected across SEVERAL fragments of one board.

`boards_for`, over synthetic `Rig`/`Instance`/`Shield`/`CensusBoard`
values — reuse the helpers already in `tests/unit/analyzer/test_sockets.py`
(`_shield`, `_inst`, `_parent`) rather than inventing a second set:

- an explicit defining label conforms; the same rig naming the
  **conventional alias** conforms against the same board;
- a type mismatch does not conform;
- **bus subset**: a shield needing UART against a socket with no
  `socket,uart` does not conform (this is the real
  `shield-uart-subset-frdm` shape);
- **inference** (`socket:` omitted): exactly one candidate conforms; two
  candidates do not; zero do not;
- **stackability**: two instances on one non-stackable socket do not
  conform.

These are the tests that carry the slice — they are pure, they run in
milliseconds, and they are where the interesting discrimination lives,
because no corpus rig omits `socket:` today (checked: all 41 instance
socket references are explicit).

### Integration, NOT build-marked — `tests/integration/test_boards_for.py`

Drives `west rigs --boards-for` as a subprocess (`west rigs` runs in
0.3 s; nothing here configures cmake):

- the three criterion-3 answers;
- a rig target that does not resolve → nonzero exit, `list_rigs`'s own
  message;
- `west rigs` with no flag still lists all 17 rigs unchanged.

### Build-marked — ONE test, appended to `test_board_read.py`

The census against DT truth, per board, reusing that file's existing
session-cached `plain_build` fixture: for every board, the census's
`(defining label, type_name, sorted bus kinds)` set and its alias map must
equal `board_edt`'s own projection of the real EDT. Compare only the
fields §4.1 says the census populates.

This is the guard that keeps a text scanner honest, and it is the only
build-marked test the slice adds. Add a bullet for it to that module's
docstring, which enumerates its guards.

**Mutation-verify it**: make the census drop a bus (or an alias), confirm
this test fails for that reason and nothing else, restore against a
pre-mutation hash, purge `__pycache__`.

## 7. Verification contract — REDUCED, and it overrides the agent definition

`rig-implementor.md` tells you to run `check.sh`. **For this slice you do
not.** The full gate's cost is 84 build-marked tests (~3m15s of real cmake
configures); the driver runs it once, after review. Your job is the cheap
tiers plus the one build module your change actually touches.

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc                                              # ~5s, 87 files
$PY -m pytest scripts/rigc/tests/unit -q                              # ~1s, 579+
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q        # ~4s, 64+
$PY -m pytest scripts/rigc/tests/integration/test_board_read.py -q    # ~17s, the ONLY build tests
git diff --stat -- scripts/rigc/tests/goldens/                        # must print NOTHING
```

Plus, by hand, the three criterion-3 queries through the real front door:

```
cd /wrk/z/ws-up && .venv/bin/west rigs --boards-for nucleo_datalogger
```

- **Do NOT run `scripts/check.sh`.** Do NOT run the full integration
  suite. Do NOT run any other `build`-marked test.
- **Do NOT start a long command in the background and then end your turn
  waiting on it.** Four of six dispatches in an earlier session did
  exactly that and had to be killed with their work verified by hand.
  Every command above is seconds. Run them in the foreground.
- Never `cmd | tail; echo $?` — that reports tail's status. Redirect to a
  log and read the exit code directly.
- If something fails and you cannot fix it in scope, hand off with the
  failure reported honestly. Do not paper over it, and do not refreeze a
  golden — a moving golden means the slice is wrong, not the golden.

## 8. Out of scope — do not start

The `--rig <shield>` promotion and `--explain` (S3), the singleton
identity law (S4), content migration to conventional labels (S5), strict
symmetry / removing `board:` from rig.yml (S6). Also `--rigs-for` (§5.2),
twister `platform_allow` generation, and any change to cmake, to any
rig.yml, or to any rig content file.

## 9. Known limitation to record, not to fix

`ard_datalogger` declares its board per variant with a `sockets:` map, so
its loaded instances already carry the variant's board-specific label
(`nucleo_ard` for the default `nucleo` variant) — `--boards-for
ard_datalogger` will answer nucleo alone, and `--boards-for
ard_datalogger/frdm` frdm alone. That is CORRECT under today's coordinate
and it is exactly what S5 (content migration to conventional labels) and
S6 (strict symmetry) exist to open up: under a free board, a
board-prefixed label in content is a portability bug. State it in the
module docstring so the next reader does not file it as one.
