# S3 — the `--rig <shield>` promotion. **S3a: desugaring + `--explain`**

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md` §9
(rulings 4–8, Tobi, 2026-08-05), specifically **§9.2 (ruling 5, the ad-hoc
rig) and §9.3 (ruling 6, `--explain`)**. Step 3 of §9.5's sequence.

Read §9.1–§9.3 of the parent before this file.

## 0. S3 IS TWO DISPATCHES — this brief is S3a. Driver's call, 2026-08-06

§9.5 lists S3 as one item. Read against the tree it is two, and the ruling
itself says which comes first.

- **S3a (this brief) — the DESUGARING and `--explain`. No build path.**
  The pure function that turns a shield name into the rig.yml + content
  file it stands for, the namespace rule that decides when a `--rig`
  argument names a shield at all, and the command that prints the result.
  Touches no cmake, no `rigc expand`, no golden.
- **S3b (next) — the BUILD path.** `rigc expand` accepting a promoted
  shield, cmake resolving a shield name through the same rule, and
  `west build-rig -b <board> --rig <shield>` working end to end.

The split is not arbitrary sequencing. **Ruling 6's third property is "if
it cannot be printed it cannot be built"** — that makes the printer the
prerequisite for the builder, not a companion to it. S3a also produces the
oracle S3b is checked against, and S4's identity law is then a diff of two
`--explain` outputs rather than a new comparator.

Precedent for splitting a ruled item on reading it against the tree: hwmv2,
which became dispatch A + B for the same reason.

## 1. What S3a is

Three things, one unit of production code:

1. **`promote_shield`** — pure: a shield name (and optional `@rev`) → the
   text of the `rig.yml` and the content file a checked-in rig would have
   to contain to mean the same thing.
2. **The namespace rule** (§9.2): rig folder wins, shield name is the
   fallback, a name that is BOTH is an error naming both paths.
3. **`west rigs --explain <target>`** — prints those two documents.

`template: true` gets its first reader (§4).

## 2. Acceptance criteria

1. **ZERO golden churn.** `git diff --stat` on
   `scripts/rigc/tests/goldens/` empty. Nothing here is reachable from
   `rigc expand`; if a golden moves, something is wired that should not be.
2. `west rigs --explain adafruit_data_logger` prints a rig.yml and a
   content file that, **copied verbatim into `boards/rigs/<name>/`, load
   through `rigc.loader.load` with no diagnostics.** This is the criterion
   that makes the printed form real rather than decorative — see §6.
3. `west rigs --explain nucleo_datalogger` (a persisted rig) prints that
   rig's two files verbatim.
4. A name that is both a rig folder and a shield is an error naming BOTH
   paths. A name that is neither is the existing "does not resolve"
   message.
5. `west rigs` and `west rigs --boards-for` behave exactly as today.
6. mypy clean, unit suite green, coverage at or above the 88 floor.

## 3. The desugaring — fix these four conventions now, S4 depends on them

The promoted form is the natural mapping `a → [a]` of ruling 4: one
socket-less instance of one shield. Written out:

```yaml
# rig.yml
rig:
  name: adafruit_data_logger
```
```yaml
# adafruit_data_logger.yml
instances:
  - name: adafruit_data_logger
    shield: adafruit_data_logger
```

Every part of that is a decision, and three of them are only legal because
of work that already landed:

- **No `board:`.** This is the FIRST rig.yml in the tree with none, and it
  is legal only because S1 relaxed `resolve_board`'s "never neither" to
  "never neither unless injected". It is also what §9.4's symmetry argument
  demands: a promoted shield has no board, so its desugaring must not
  invent one. A board reaches this rig only by injection.

  **CORRECTION (driver, 2026-08-06, after the dispatch caught it).** §6
  below originally said the round-trip test loads this rig "with no
  board", and that is FALSE — measured, not argued: `loader.load(rig_yml,
  workdir, types=types)` with no `board=` on a boardless rig.yml returns a
  `lang-schema` diagnostic, because the relaxation is conditional on an
  injected board and nothing else. The brief's own "unless injected" was
  accurate; the verification step it then described contradicted it. No
  corpus rig exercised the boardless path, so nothing caught this earlier.
  The round-trip test passes an injected board, which is also the FAITHFUL
  shape: S1 made cmake pass `--board ${BOARD}` unconditionally, so a
  promoted rig is only ever loaded with one.
- **No `socket:`.** The §4.2 unique-by-type inference (`1c2344e`) resolves
  it. This is what makes the promoted form board-agnostic, and it is why
  inference had to land first.
- **The instance name is THE SHIELD NAME.** Not `inst`, not `s`. This is a
  real decision with a consequence you cannot see from here: instance names
  reach `config-sheet.md` (`emitter/sheet.py:48`), which C2b made a
  COMPARED FACT. So S4's identity law can only hold if the checked-in rig
  it compares against uses the same instance name. Fix it here, state it in
  the docstring, and S4 authors its fixture to match.
- **`@rev` on a promoted shield is the SHIELD's revision**, desugaring to
  `shield: <name>@<rev>` in the content file — never a rig revision axis,
  which a promoted rig does not have. `/variant` on a promoted shield is an
  ERROR: there is no variant axis to select from. Say both in the message.
  (§9.6 already noted `@` is taken by shield revisions; this is that
  collision resolved in the only direction that makes sense.)

The content file's NAME is `<rigname>.yml`, per the metadata/content split
— so `adafruit_data_logger.yml`. Return the filename alongside the text;
do not make the caller re-derive it.

## 4. `template: true` becomes load-bearing — and gains a census

It is declared in all 14 shield.yml files and **read by nothing** — not
`list_shields.py`, not upstream `shields.cmake`, not rigc, which uses the
marker FILE `<name>.shield` instead (`loader/library.py`, whose docstring
records that shield.yml is OPTIONAL and supplies only `revisions:`).

**Ruling 5 makes it the authority for PROMOTABLE.** Implement exactly that
and nothing more:

- **promotion requires `template: true`.** A shield with a marker file but
  no `shield.yml`, or one whose `shield.yml` omits the flag, is
  discoverable and referenceable from a checked-in rig but NOT promotable.
  The error says which of the two is missing.
- **discovery keeps the marker file.** Do not touch `library.py`.

That is deliberately two facts about one thing, so **add a census that they
agree**: every shield folder carrying `<name>.shield` declares `template:
true`, and vice versa. Today all 14 satisfy both. Census-style, so it is
falsified by mutating the WORLD it observes — drop the flag from one real
`shield.yml` and exactly that test fails. Without it the two authorities
drift silently and "promotable" quietly stops meaning "buildable".

## 5. The namespace rule (§9.2)

> **rig folder wins, shield name is the fallback, a name that is BOTH is an
> error naming both paths.**

Where it lives, and this is the part worth getting right: **not in
`list_rigs.py`.** That module is the cmake-facing seam, it deliberately
knows only rig.yml's four metadata keys, and teaching it about shields
drags zephyr's `list_shields.py` into a resolver cmake calls per configure.
S3b decides how cmake reaches this; S3a keeps it off that seam entirely.

Put it in the new rigc module. Reuse **rigc's OWN shield discovery**
(`loader/library.py`'s scan), not zephyr's `list_shields.py` — then
"promotable" and "resolvable by the expander" cannot disagree, which is the
same construct-don't-parse instinct the rest of the project follows.

The collision case is not hypothetical in shape: `dts.cmake:612-664`
already resolves a same-named stock-Zephyr/rig-template collision by
preferring the marker. Our rule is the rig/shield axis of the same problem,
and unlike that one it **errors rather than picking**, because a rig folder
and a shield of one name are two different authored things and guessing
between them is exactly the class of tie-break §4.2's inference already
refuses to make.

## 6. `--explain` — and the criterion that keeps it honest

`west rigs --explain <target>`:

- **a persisted rig** → its `rig.yml` and content file, verbatim from disk;
- **a promoted shield** → the synthesized pair from §3;
- **both** → rendered identically, each document preceded by its filename,
  so the two cases are diffable against each other. That diffability IS
  ruling 6's property 1 (the singleton law checkable at the MODEL level),
  and it is what makes S4 cheap.

Out of scope: rendering a persisted rig with its axes RESOLVED (the
selected variant's board folded in, fragments applied). `--explain` prints
the documents as authored. Say so in the help text — a reader who assumes
otherwise for a variant rig would be misled.

**Criterion 2.2 is the anti-decoration guard.** A printer that emits
plausible YAML nothing can load is worse than no printer, because ruling
6's whole argument is that the ad-hoc form cannot outrun the persisted one.
Write the test that closes it: take `--explain`'s output for a promoted
shield, write the two documents into a tmp_path rig folder, run
`rigc.loader.load` against them, assert a Rig with one instance, the right
shield, and NO diagnostics. In-process and no subprocess; the loader runs
standalone with no `--include-dir` (verified: five corpus rigs load in
0.21s).

**Pass an injected `board=`** — see §3's correction. "No board" here means
no board DEVICETREE (no `--board-dts`, no analyzer; a bare string the
loader never dereferences), NOT an absent `board=` argument, which fails on
the very rule S1 relaxed only for injection.

That test is the slice. Everything else is plumbing around it.

## 7. Code

- **`scripts/rigc/promote.py`** (new unit): `promote_shield` (pure, returns
  the two documents + the content filename), the namespace resolution, and
  the promotability check. Public functions state return semantics and
  ownership in prose. Keep IO at the edges: the discovery scan is the edge,
  the document construction is pure over values.
- **`scripts/west_commands/rigs.py`**: `--explain <target>`, short-
  circuiting the listing exactly as `--boards-for` does. Reuse that
  method's shape — `ZEPHYR_BASE` pinned to west's own resolution, workdir
  removed in a `finally` if one is needed at all.

Do not touch `list_rigs.py`, `cmake/`, `rigc/cli.py`, `loader/library.py`,
any rig.yml, or any golden.

## 8. Tests

**Unit — `scripts/rigc/tests/unit/test_promote.py`** (the module names its
unit). Over dedented triple-quoted blocks:

- the desugared pair for a bare shield name: rig.yml has `rig.name` and
  **no `board:`**; the content file has exactly one instance, named after
  the shield, with `shield:` set and **no `socket:`**;
- the content FILENAME is `<name>.yml`;
- `@rev` desugars to `shield: <name>@<rev>` and leaves rig.yml unchanged;
- `/variant` on a promoted shield is an error naming why;
- a shield without `template: true` is not promotable, and the message says
  whether the flag or the shield.yml is what is missing;
- the namespace rule, all three branches: rig-only, shield-only, both →
  error naming both paths. The both-branch is the one that needs a real
  negative control.

**The round-trip test (criterion 2.2)** — `--explain` output → tmp rig
folder → `loader.load` → one instance, right shield, no diagnostics. This
is a unit test: it is in-process and touches only tmp_path.

**Census** — `template: true` ⟺ `<name>.shield`, over the real tree
(§4). Falsified by mutating a real `shield.yml`, never by editing its own
assertion.

**Integration, NOT build-marked** — `west rigs --explain` for one promoted
shield and one persisted rig; the both-names error; `west rigs` and
`--boards-for` still unchanged.

**Build-marked: NONE.** This slice reaches no configure. If you find
yourself needing one, that is S3b leaking in — stop and report.

Every negative control **mutation-verified**: fails for its named reason
and nothing else. Copy the file first, hash BEFORE mutating, restore from
the copy, verify against that hash, purge `__pycache__`. Never restore with
`git checkout`.

## 9. Verification contract — REDUCED, and it overrides the agent definition

`rig-implementor.md` says to run `check.sh`. **You do not.** The driver
runs the full gate once, after review. Measured today: the build-marked
tier is ~3m40s of the 3m44s gate; everything below is seconds.

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc
$PY -m pytest scripts/rigc/tests/unit -q
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q
git diff --stat -- scripts/rigc/tests/goldens/          # must print NOTHING
```

plus by hand from `/wrk/z/ws-up`:
`.venv/bin/west rigs --explain adafruit_data_logger`, the same for
`nucleo_datalogger`, and `.venv/bin/west rigs` unchanged.

**No build-marked test runs in this slice** — the tier is untouched, so
there is nothing in it your change could falsify.

- Do NOT run `scripts/check.sh` or the full integration suite.
- **Do NOT background a command and end your turn waiting on it.**
  Everything above is seconds. Foreground.
- Never `cmd | tail; echo $?` — that reports tail's status.
- If something fails and you cannot fix it in scope, report it honestly.
  Never refreeze a golden.

## 10. Out of scope — do not start

**All of S3b**: `rigc expand` accepting a promoted shield, any cmake
change, `west build-rig --rig <shield>`, `list_rigs.py`. Also S4 (the
singleton identity law), S5, S6, and the ad-hoc params CLI grammar, whose
token exit is still unruled (parent §9.6).
