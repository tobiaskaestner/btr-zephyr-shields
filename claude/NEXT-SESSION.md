# Rigs — Session Handoff

## RESUME (2026-08-21) — THE EXTERNAL REVIEW IS EXECUTED, ALL OF IT. rigc was cold-reviewed and then cleaned end to end: complexity, comments, diagnostics, structure, types, tests, docs. Ten commits, tree clean, gate ALL GREEN. NEXT = reference slices 2/3, then rig-schema.yaml → BRIDLE MIGRATION (unchanged).

History note: every earlier RESUME block now lives in
`claude/session-history.md` — this file carries only the current state
and the open points. Re-derive state from `git status`/`git log`, never
from prose.

### STATE AT SESSION CLOSE (2026-08-21)

Tree **clean**, `main` ahead 64 of origin, HEAD `d661d32`. Last full
gate on this exact tree: **`check.sh: ALL GREEN`** — mypy clean (113
source files), unit **780 passed** (94% coverage), integration **297
passed** (build tier included), docs `sphinx-build` clean.

The block's ten commits, oldest first (the review brief
`claude/rigc-external-review-brief.md` is the spec for all of them):

| commit | what |
|---|---|
| `7e79747` | the external review itself — findings + task plan A–H |
| `8f33917` | fix: single-plug slot name from the shield, never a literal `"plug"` (latent bug, regression-tested) |
| `c65279a` | refactor: every function ≤ CC 15 (was: 18 functions above, worst 43) |
| `9a19d9e` | doc: source comments rewritten for an external reader (−335 lines of prose; zero brief/rigexp/codeword citations left) |
| `ebaa4ed` | doc: diagnostics + emitted banners drop design-history tokens; 53 goldens refrozen |
| `934454d` | refactor: ChannelResolution NamedTuple; ExposedSocket typing honest |
| `d396533` | doc: `doc/explanation/architecture.rst` — the why, for outsiders |
| `cf80dae` | refactor: `rigc/board/` package (resolve/project/edt_build/census), shields.py → loader/, `FunctionRef`, `straps`/`strap_refs` |
| `d661d32` | doc: test_shields split to size (4 modules + conftest) + the whole test tree's comment sweep |

Renames to know when reading old notes: `GpioRef`→`FunctionRef`
(`Device.gpio_refs`→`function_refs`), `Instance.pins`/`pin_refs`→
`straps`/`strap_refs`, `boarddt`→`board/resolve`, `board_edt`→
`board/project`, `board_census`→`board/census`, `shields.py`→
`loader/shields.py`. Board unit tests live in `tests/unit/board/`,
shields tests in `tests/unit/loader/test_shields_{plugs,devices,
exposed,elements}.py`.

**Size policy (adopted, recorded in the review brief's addendum):**
modules ≤ 1,000–1,200 lines, packages ≤ 15–20 modules, tests included;
`tests/integration/` (one file per feature) is a conscious exemption.
Largest module today: `loader/shields.py` at 875 — its future split
seam (device parsing vs exposed-socket parsing) already exists as
helper boundaries.

### OPEN POINTS

1. **Reference slices 2 and 3** — unchanged, still unstarted: (2)
   `rig-file.rst` + `promotion.rst` (the latter takes over the
   promotion grammar's semantics from `commands.rst`); (3) the
   42-code diagnostic catalogue.
2. **`rig-schema.yaml`** (backlog item 7) — item 41 belongs to it.
3. **BRIDLE MIGRATION** (backlog item 9) — the mission goal. Re-run
   `bridle-migration.md`'s triage against bridle's CURRENT upstream
   first.
4. **Backlog 41 and 42 still open, still unruled**: 41 = `rig.yml`
   silently ignores unknown keys under `rig:`; 42 = `west rigs --rig
   TARGET` accepted and never read.
5. **Stale tier-2 goldens** (found by the Task-G refreeze, deliberately
   NOT fixed there): `tests/goldens/quail_sockets/zephyr.dts` and
   `quail_temp_farm/zephyr.dts` lack the `mikrobus_N:` labels that
   `mikrobus_sockets.dtsi` has carried since `d47ec86`. One
   single-purpose refreeze commit closes it.
6. **Scope-marker invariant is assert-only**: a `socket,<bus> =
   <&device>` scope marker on an exposed socket that lacks
   `shield,channel` is caught by an `assert` in
   `analyzer/sockets.py`, not a diagnostic. Small loader/parser check
   would make it a proper `lang-exposed` finding.
7. **Three `ruff F401` unused-import warnings** in
   `tests/integration/conftest.py`, `test_dts_vocabulary_drift.py`,
   `test_emitted_corpus.py` — noticed during the sweep, possibly
   conftest fixture re-export false positives. Only matters if ruff
   ever joins the gate; check then.

### CARRIED — harness facts that stay true

- `ZEPHYR_BASE` for this workspace is `/wrk/z/ws-up/zephyr`; the venv
  is `/wrk/z/ws-up/.venv`. `doc/_build/html` is a local render, never
  committed — rebuild before reading it.
- From a session rooted at `/wrk/z/ws-up`, `rig-implementor`/
  `rig-reviewer` are NOT agent types (they are project agents of
  btr-shields).
- `RIGC_REFREEZE=1` works (refroze 53 goldens this block). Always
  inspect `git diff tests/goldens` line-by-line after — this block's
  refreeze surfaced unrelated pre-existing drift (open point 5) that
  must not ride along.
- Exit-status trap: `check.sh > log; echo $?; tail log` in a compound
  reports the LAST command's status. Make `check.sh` the last command,
  or capture `$?` immediately.
- Subagents repeatedly stalled by backgrounding the gate and waiting on
  dead monitors. The instruction that works: run `check.sh` in ONE
  foreground Bash call with timeout 600000 ms, never backgrounded,
  and report in the same turn.
- A byte-compared stderr golden makes source LINE NUMBERS part of the
  contract — "no behavior change" never implies "no golden change",
  and `CHECK_FAST=1` checks no overlay goldens at all.
