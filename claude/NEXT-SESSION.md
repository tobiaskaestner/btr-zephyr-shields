# Rigs — Session Handoff

## RESUME (2026-08-31) — THE MIGRATION SEAM IS CUT. The tests, the gate, the docs and the transpiler's own data roots are all split along the travels/stays line, and `west build-rig` is gone. Ten commits, tree clean, BOTH gates green. NEXT = rig-schema.yaml → BRIDLE MIGRATION — the mechanics are now portable, which they were not before this block.

History note: every earlier RESUME block now lives in
`claude/session-history.md` — this file carries only the current state
and the open points. Re-derive state from `git status`/`git log`, never
from prose.

### STATE AT SESSION CLOSE (2026-08-31)

Tree **clean**, `main` ahead 10 of origin, HEAD `551fd3c`.

**The gate is now TWO scripts. Run both — `check.sh` alone is no longer
the full gate.** Both green on this exact tree:

- `scripts/check.sh` (**travels**) — ALL GREEN: mypy clean (119 source
  files), unit **780 passed** (94% coverage), travelling integration
  **71 passed**.
- `scripts/check-extended.sh` (**stays**) — ALL GREEN: staying
  integration **232 passed**, build tier included.
- `sphinx -W` clean.

The block's ten commits, oldest first:

| commit | what |
|---|---|
| `fa0bd6e` | the integration suite splits by tether: 10 travelling modules, 13 staying; `harness.py`/`corpus.py` replace the shared conftest |
| `602aa84` | connector-type bindings vendored into fixtures + a drift guard, so their test travels |
| `2a1aeec` | two stale quail goldens pick up the conventional socket labels (closed the old open point 5) |
| `ec98b14` | `--connector-dir` threaded from `DTS_ROOT`; `registry.BINDINGS` demoted to a dev/test fallback with a real diagnostic; a latent uncaught `LoadError` in `cli.py` fixed |
| `dc8aa74` | `test_emitted_rejects` reclaimed to the travelling side — five vendored shields + a fixture board; 36 goldens travel with it |
| `173c88c` | `west build-rig` retired; the resolved corpus rebuilt on `west build … -- -DRIG=`; three equivalence tests retired; four tutorials rewritten |
| `61d100d` | the gate splits: `check.sh` travels, `check-extended.sh` stays; `pyproject.toml` `testpaths` narrowed to the travelling dir |
| `6b35bde` | `doc/reference/rig-file.rst` + `promotion.rst`; `AxisDecl`'s stale docstring corrected |
| `274f44e` | `doc/reference/diagnostics.rst` (44 codes) + two drift guards |
| `551fd3c` | `AxisDecl` drops the dead `boards`/`sockets` fields |

**The seam, in one paragraph.** What travels: `scripts/rigc/`, `doc/`,
`cmake/`, `scripts/check.sh`, `pyproject.toml`, and
`scripts/rigc/tests/integration/`. What stays: `boards/` (rigs, shields,
extensions), `scripts/rigc/tests/goldens/`,
`scripts/rigc/tests/integration_stay/`, `scripts/check-extended.sh`,
`dts/bindings/connectors/` and `include/dt-bindings/connector/`.
`check.sh` names no staying path anywhere, comments included — verified
by grep, and worth re-verifying if you touch it.

**Names and facts to know when reading older notes:**

- `tests/integration/` = travels (reads nothing outside `scripts/rigc/`,
  `doc/` and the fixtures). `tests/integration_stay/` = stays (tethered
  to `boards/`). The split is by TETHER, not by kind.
- Test modules import from `harness` (generic, travels) or `corpus`
  (tethered, stays), **never from `conftest`** — two sibling conftests
  would race for `sys.modules["conftest"]` and cross-wire silently.
- `harness.run_expand` has **no** shield-dir default, deliberately, so a
  call that forgets `shield_dirs` fails loudly instead of silently
  reaching production shields. `corpus.run_expand` restores the old
  default for the stay side.
- Vendored fixtures: `fixtures/dts/unified-connectors/` + the four
  headers under `fixtures/include/dt-bindings/connector/` (byte-identical
  to production, **drift-guarded** by
  `integration_stay/test_vendored_connector_drift.py`);
  `fixtures/boards/shields/` (five shields, byte-identical copies,
  **deliberately NOT guarded** — see `test_emitted_rejects`'s docstring
  for why pinning them is the point); `fixtures/boards/mainboards/
  emitted_rejects_board.dts`; `fixtures/extra_dts_root/`.
- There is no `west build-rig`. A rig is built with `-DRIG=<name>` passed
  through an ordinary `west build`, or a bare `cmake -DRIG=` with west
  absent.
- One row of `doc/reference/diagnostics.rst` (`lang-connector-root`) was
  reconstructed by hand after a mutation test on an untracked file lost
  it. It renders and the guard passes, but it is the one piece of prose
  in this block written from inference rather than authored — worth a
  read.

### OPEN POINTS

1. **`rig-schema.yaml`** (backlog item 7) — item 41 belongs to it.
2. **BRIDLE MIGRATION** (backlog item 9) — the mission goal, and now
   unblocked. Re-run `bridle-migration.md`'s triage against bridle's
   CURRENT upstream first.
3. **Backlog 41 and 42 still open, still unruled**: 41 = `rig.yml`
   silently ignores unknown keys under `rig:`; 42 = `west rigs --rig
   TARGET` accepted and never read.
4. **Scope-marker invariant is assert-only**: a `socket,<bus> =
   <&device>` scope marker on an exposed socket that lacks
   `shield,channel` is caught by an `assert` in `analyzer/sockets.py`,
   not a diagnostic. A small loader/parser check would make it a proper
   `lang-exposed` finding.
5. **Three `ruff F401` unused-import warnings** — in
   `integration/harness.py`, `integration/test_dts_vocabulary_drift.py`
   and `integration_stay/test_emitted_corpus.py`. Pre-existing, possibly
   fixture re-export false positives. Only matters if ruff joins the
   gate; check then.
6. **The `connector-dirs` provenance key is deferred.** `context.cmake`
   records `shield-dirs`; the symmetric connector entry was deliberately
   kept out of `ec98b14`, because `context.cmake` is golden-compared as a
   key→value mapping and adding a key refreezes every emitted golden.
   Worth doing as its own commit.
7. **The travelling gate has no build tier.** All 53 build-reaching
   tests are tethered to real boards and stay here. bridle will get
   mypy + 780 unit + 71 fixture-only integration tests and **cannot
   prove the transpiler configures a real board** until it has rigs of
   its own. By design — this repo is the harness — but it shapes what
   the bridle PRs can claim.
8. **`claude/bridle-enhancement-issue.md` is UNTRACKED and deliberately
   uncommitted.** A drafted `[FER]` issue body for `tiacsys/bridle`,
   written against that repo's `.github/ISSUE_TEMPLATE/enhancement.md`,
   to accompany the migration PRs. Awaiting Tobi's review. Before
   filing: strip the HTML comment header above the `---`, and re-run the
   S2/S3/S6 upstream baselines — its claims are verified against zephyr
   `v4.4.0-8558-g640b25d911f` as of **2026-07-17** and are presented in
   the issue with that date attached. It leads on bridle's own
   `boards/shields/grove*` being **229 overlay files** for four logical
   modules; recheck that count if bridle moves before filing.

### CARRIED — harness facts that stay true

- `ZEPHYR_BASE` for this workspace is `/wrk/z/ws-up/zephyr`; the venv is
  `/wrk/z/ws-up/.venv`. `doc/_build/html` is a local render, never
  committed — rebuild before reading it.
- From a session rooted at `/wrk/z/ws-up`, `rig-implementor`/
  `rig-reviewer` are NOT agent types (they are project agents of
  btr-shields).
- `RIGC_REFREEZE=1` works. Always inspect `git diff tests/goldens`
  line-by-line after — a refreeze surfaced unrelated pre-existing drift
  once already (that was old open point 5, now closed), and it must not
  ride along.
- Exit-status trap: `check.sh > log; echo $?; tail log` in a compound
  reports the LAST command's status. Make the script the last command,
  or capture `$?` immediately.
- Subagents stall by backgrounding the gate and waiting on dead
  monitors. The instruction that works: run each gate in ONE foreground
  Bash call with `timeout: 600000` set explicitly, never backgrounded,
  and report in the same turn.
- A byte-compared stderr golden makes source LINE NUMBERS part of the
  contract — "no behavior change" never implies "no golden change".
- `CHECK_FAST=1` now deselects **nothing** in `check.sh`: the travelling
  suite carries no build-marked tests at all. The whole build tier lives
  in `check-extended.sh`, where `CHECK_FAST=1` deselects 108 of 232.
- Mutating an UNTRACKED file has no git safety net. `git checkout`
  cannot restore it. Copy it aside first — this cost a hand-reconstructed
  table row in `diagnostics.rst` this block.
