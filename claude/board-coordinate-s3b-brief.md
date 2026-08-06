# S3b — the `--rig <shield>` build path

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md`
§9.2 (ruling 5). Second half of step 3 of §9.5; the first half landed as
`7af1fc9` (S3a), spec `board-coordinate-s3-brief.md`.

**Read S3a's brief and `scripts/rigc/promote.py` before this file.** S3a
built the desugaring, the namespace rule and `west rigs --explain`. This
slice makes the same desugaring *buildable*, and reuses it verbatim — it
does not re-derive any part of it.

## 1. What this slice is

`west build-rig -b <board> --rig <shield-name> <app>` builds a promoted
shield, end to end, producing exactly the firmware that a checked-in rig
containing one socket-less instance of that shield would.

Ruling 6's property — "if it cannot be printed it cannot be built" — is
now the other way round too: whatever `--explain` prints is what gets
built, from the same function.

## 2. Acceptance criteria

1. **ZERO golden churn.** `git diff --stat` on
   `scripts/rigc/tests/goldens/` empty. Every existing rig resolves and
   builds exactly as today; a promoted shield is a NEW path, not a
   changed one. A moving golden means an existing rig's resolution
   changed — stop and report, do not refreeze.
2. `west build-rig -b nucleo_f401re/stm32f401xe/rig --rig adafruit_data_logger
   btr-shields/samples/rigs/scenario-1` **configures and links.**
3. The same invocation with **no** `-b` fails with a message saying a
   promoted shield declares no board and one must be given. A shield has
   no board to infer — this is S1's "no board anywhere" FATAL reached by a
   new route, and it must stay legible.
4. `--rig <a real rig>` is unchanged in every respect, including the
   rig-swap guard and both cmake-alone entry paths.
5. A name that is both a rig and a shield errors identically to
   `--explain`'s message — one namespace rule, not two.
6. mypy clean, unit green, coverage at or above the 88 floor.

## 3. RULING — where the namespace rule goes now (driver, 2026-08-06)

S3a deliberately kept it out of `list_rigs.py`, to keep that slice off the
cmake-facing seam and to let this one decide with the desugaring already
proven. Deciding now:

> **`list_rigs.py` becomes the resolver for BOTH namespaces**, delegating
> the shield half to `rigc.promote`.

Rejected alternatives, and why:

- *A second resolver script that cmake calls instead.* Two resolvers means
  two places axis resolution could drift, and `list_rigs.resolve_rig_target`
  is already the ratified cmake seam (design rule 1: cmake never parses rig
  content, resolution semantics live in one module).
- *cmake tries `list_rigs`, then falls back on failure.* `list_rigs`
  `sys.exit`s the same way for "no such rig" and "malformed rig.yml", so a
  fallback would silently promote a shield whenever a same-named rig was
  broken — turning an authoring error into a different build.
- *Teaching cmake to ask twice.* Same problem, plus a second
  `execute_process` per configure.

What that costs: `list_rigs.py` gains an import of `rigc.promote`. That is
acceptable and is NOT the thing S3a was avoiding — the objection was
dragging zephyr's `list_shields.py` and a second discovery glob into the
seam. `rigc.promote.discover_shields` reuses `loader/library.py`'s own
scan, imports no zephyr script, and runs no cpp.

**Breadth, and this is the trap:** `find_rigs` walks every board root, so
the shield scan must take the matching `<root>/boards/shields` list. S3a
shipped with the narrow default and it made a cross-module shield
invisible AND uncollidable — the namespace rule failing open. Verified
against a real cross-module shield, fixed in review. Do not reintroduce
it: `resolve_rig_target` already has `args.board_roots` in hand.

## 4. The cmake side — two forks, one new answer

Both forks call `list_rigs.py --rig=<target> --cmakeformat=...` and get
`{NAME};{DIR};{BOARD};{REVISION};{VARIANT}` back.

**Add one key: `{PROMOTED}`** — the shield name when the target resolved
as a promoted shield, `NOTFOUND` otherwise. Then:

- `DIR` is empty/`NOTFOUND` for a promoted shield: there is no rig folder.
- `BOARD` is `NOTFOUND`: a shield declares none. S1 already made that a
  clean answer rather than a failure — `boards.cmake`'s existing "declares
  no board" FATAL fires only when no `-DBOARD` was given, which is
  criterion 2.3 exactly. **Check that message reads correctly for a
  shield** before deciding whether it needs its own wording; if the
  existing text says "rig 'X' declares no board:" for something the user
  typed as a shield name, differentiate it.
- `REVISION` carries `@rev` for a promoted shield (the SHIELD's revision,
  per S3a); `VARIANT` is always `NOTFOUND` — S3a refuses `/variant` on a
  promoted shield, and that refusal must reach the cmake path too.

`cmake/dts.cmake` step 3 currently does `set(_rig_yml "${_rig_dir}/rig.yml")`
and FATALs if it does not exist (lines 283-288). For a promoted shield
there is no such file — see §5 for what it passes instead.

Read the comment blocks at `boards.cmake:10-17` and `67-98` and
`dts.cmake:231-300` before editing. They enumerate the reconfigure and
rig-swap cases by hand; every one must still be answered, and the comments
must describe the NEW rule. **A stale comment here is a review finding**,
and S1's own review found exactly that.

## 5. The rigc side — materialize, then load unchanged

`rigc expand` takes a path to `rig.yml`. A promoted shield has no such
file, and the fix must not fork the loader.

**Ruling: `expand` gains `--promote <shield-name>`, and rigc WRITES the
two documents into its own workdir, then loads them by path.**

- one desugaring, `promote.promote_shield`, called from both `--explain`
  and here. Never a second construction of that text.
- everything downstream — loader, deps, diagnostics, emitter — runs on a
  real rig.yml on a real path, unchanged. No in-memory document source, no
  new code path through `documents.py`.
- the positional `rig` argument and `--promote` are mutually exclusive;
  say so in the parser and test it.
- D10 still applies: the workdir is removed on accept, kept on reject. A
  rejected promoted rig therefore leaves its synthesized pair on disk,
  which is the evidence a user needs. Say that in the docstring.

Diagnostics for a rejected promoted rig will name a path inside that
workdir. That is honest — the file genuinely is synthesized — and no
golden covers it. **Do check what one actually looks like** and report the
text in your handoff; if it is unreadable, say so rather than papering
over it.

`cmake/dts.cmake` then passes `--promote ${_rig_promoted}` in place of the
`rig.yml` positional. Note `CMAKE_CONFIGURE_DEPENDS` (step 4) registers
`rig.yml` and the content file; for a promoted shield the equivalent
dependency is the shield's own `.shield` template and its `shield.yml` —
which `RIG_DEPENDS` already records through the normal resolution path.
Check whether the static registration needs anything and say what you
found.

## 6. Tests

**Unit** — `tests/unit/test_promote.py` and `tests/unit/test_cli.py`
(each names its unit):

- `--promote` and the positional are mutually exclusive;
- `--promote` writes both documents into the workdir with the names
  `promote_shield` returned, and their content is byte-identical to what
  `promote_shield` returns — the pin that there is ONE desugaring;
- `list_rigs`-side: a target resolving as a shield reports `PROMOTED`, an
  empty `DIR` and no board; a rig target is unchanged; the both-names
  error is the S3a message.

**Integration, not build-marked** — resolution only, via `list_rigs.py`'s
own CLI: the `--cmakeformat` line for a promoted shield, for a rig, and
the both-names error. These are subprocess-cheap and catch a cmakeformat
key regression without a configure.

**Build-marked — the real falsifier, and this slice needs it:**

- criterion 2.2, a full configure of a promoted shield on a real board;
- criterion 2.3, the same with no `-b`, asserting the diagnostic;
- criterion 2.4's regression: an existing rig still builds. `west
  build-rig --rig nucleo_datalogger` is already covered by
  `test_resolved_corpus.py`, so do not duplicate it — just do not break it.

Put the new build tests in `test_cmake_alone_entry.py`, which already owns
the `-DRIG`/`-DBOARD` entry-path guards and carries the module-level
`build` marker.

Every negative control **mutation-verified**: fails for its named reason
and nothing else. Hash before mutating, restore from a copy, verify
against that hash, purge `__pycache__`. Never restore with `git checkout`.

## 7. Verification contract — REDUCED, and it overrides the agent definition

`rig-implementor.md` says to run `check.sh`. **You do not.** The driver
runs the full gate once, after review.

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc
$PY -m pytest scripts/rigc/tests/unit -q
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q
$PY -m pytest scripts/rigc/tests/integration/test_cmake_alone_entry.py -q
git diff --stat -- scripts/rigc/tests/goldens/          # must print NOTHING
```

plus, by hand from `/wrk/z/ws-up`, criteria 2.2 and 2.3 through the real
front door, and `.venv/bin/west rigs --explain adafruit_data_logger` to
confirm S3a's output is unchanged.

`test_cmake_alone_entry.py` is the ONE build-marked module you run —
it is where your new tests go and where a resolution regression would
show. Do NOT run `scripts/check.sh`, the full integration suite, or
`test_resolved_corpus.py` (~2 minutes of configures the driver covers).

- **Do NOT background a command and end your turn waiting on it.**
- Never `cmd | tail; echo $?` — that reports tail's status.
- If something fails and you cannot fix it in scope, report it honestly.
  Never refreeze a golden.

## 8. Out of scope — do not start

S4 (the singleton identity law — this slice is its prerequisite, not its
implementation), S5, S6. The ad-hoc params CLI grammar, whose token exit
is still unruled (parent §9.6). Any change to the desugaring itself:
`promote_shield`'s output is fixed by S3a and S4 will compare against it.

**Also ignore an untracked `doc/` tree** if you see one — that is
unrelated driver work in progress, not yours to touch or report on.
