# Fork-per-phase cmake refactor — implementation brief

Status: RATIFIED 2026-07-24 (decision B + placement Option B). This is the
authoritative build sheet for the slice; the implementor contract's
required-reading rules apply on top.

## Decision (two sentences)

Every file under `btr-shields/cmake/` overloads its upstream namesake and owns
its phase's rig logic; `rig.cmake` dissolves. In a rig build the shields phase
is EMPTY (shield selection is a consequence of rig expansion, not a standalone
phase), and the whole rig block — expand, resolve shields, hand off
overlays/confs, provenance — lives in the dts fork, which delegates to the
real `dts.cmake` as its last act.

Rationale trail: each fork doubles as the draft upstream patch. The shields
patch becomes a one-line early-exit; the dts patch is the self-contained "rigs
are dts/kconfig input" story. The rejected alternative (shields fork defines a
deferred macro the dts fork invokes) is a two-file protocol upstream has no
idiom for.

## Upstream facts this design rests on (verified 2026-07-24, zephyr @ 76305e9aa49)

The module chain (`zephyr/cmake/modules/zephyr_default.cmake:67-108`), with
only the segment after the fork hook shown. The hook: `zephyr_module.cmake:88-98`
prepends each module's `cmake-modules` dir to `CMAKE_MODULE_PATH` — every
namesake below is forkable.

| slot | module | facts that matter here |
|---|---|---|
| 10 | `boards` | list_boards.py → `BOARD_DIR`, `BOARD_DIRECTORIES` (base + `extend:` dirs), `BOARD_QUALIFIERS`, revision handling. |
| 11 | `shields` | outputs (`SHIELD_DIRS`, `SHIELD_AS_LIST`, `shield_dts_files`, `shield_conf_files`) are consumed **only from slot 17 on** — its position is historical, not a data dependency. |
| 12 | `snippets` | appends to `DTC_OVERLAY_FILE`/`OVERLAY_CONFIG` vars. |
| 13 | `hwm_v2` | sets `ARCH_V2_NAME_LIST`; `kconfig_gen` writes board Kconfig glue over `BOARD_DIRECTORIES`. |
| 14 | `configuration_files` | **finalizes** `CONF_FILE`, `EXTRA_CONF_FILE` (merges `OVERLAY_CONFIG`), `DTC_OVERLAY_FILE`, `EXTRA_DTC_OVERLAY_FILE`, `DTS_EXTRA_CPPFLAGS` via `zephyr_get(... MERGE)`. Cache writes after this slot are invisible to it. |
| 15 | `generated_file_directories` | trivial. |
| 16 | `${BOARD_DIR}/pre_dt_board.cmake` | optional board DT flags. |
| 17 | `dts` | includes `boards` + `pre_dt`; body is functions + a **`dts_init` macro** that `zephyr_default.cmake:131-133` calls right after the include (`<module>_init` convention). |
| 18 | `kconfig` | consumes `shield_conf_files`, `SHIELD_AS_LIST`, `EXTRA_CONF_FILE`, `BOARD_DEFCONFIG` (from `BOARD_DIRECTORIES`). |

`pre_dt.cmake` is a **plain function** `pre_dt_module_run()` + one call at file
scope. It folds `APPLICATION_SOURCE_DIR`, `BOARD_DIR`, `SHIELD_DIRS`,
`ZEPHYR_BASE` into `DTS_ROOT` and derives `DTS_ROOT_SYSTEM_INCLUDE_DIRS`
(needs `ARCH_V2_NAME_LIST`, available from slot 13 on). Because it is a
function, it can be **called again** after `SHIELD_DIRS` becomes known — the
include-guard poisoning that forced saferail 13's hand-written mirror is gone.

Dead upstream code (do NOT wire anything to it): `BOARD_EXTENSION_DIRS` in
`dts.cmake:181` / `kconfig.cmake:96` — its only producer was HWMv1 extensions,
removed upstream in `c02c6add101`. Upstream-issue candidate #3, draft
separately.

## Target layout

```
btr-shields/cmake/
  boards.cmake    NEW fork.  include(real boards.cmake) FIRST, then:
                    - _rig_resolve_board_dts()  (moves verbatim from shields fork)
                    - the hwmv2-extension -isystem guard (moves verbatim; runs for
                      EVERY build, rig or plain, exactly as today)
  shields.cmake   SHRINKS to pure dispatch:
                    if(DEFINED RIG): early-exit with the one-paragraph design
                      statement (the draft upstream patch: "rig builds have no
                      shields phase") — nothing else
                    else: include(real shields.cmake) by absolute path
  dts.cmake       NEW fork. Plain build: include(real dts.cmake), done.
                  Rig build, at include time, in this order:
                    1. include(pre_dt)          — real one, first run (SHIELD_DIRS
                                                  still empty; that's fine, see
                                                  "pass-1 recipe" below)
                    2. pass-1 recipe            — derive --include-dir/--bindings-dir
                                                  args from the REAL DTS_ROOT /
                                                  DTS_ROOT_SYSTEM_INCLUDE_DIRS +
                                                  BOARD_DIRECTORIES; board dts via
                                                  _rig_resolve_board_dts()
                    3. run the expander         — list_rigs resolution, VERBOSE
                                                  render, rerun-expand.sh,
                                                  RIG_EXPAND_COMMAND knob, error
                                                  reporting: all move from rig.cmake
                                                  unchanged
                    4. context.cmake handoff    — RIG_NAME/RIG_BOARD/RIG_SHIELDS,
                                                  RIG_DEPENDS + static
                                                  CMAKE_CONFIGURE_DEPENDS set
                    5. shield resolution        — the former Kconfig tail: list_shields
                                                  discovery, rig-template-marker
                                                  collision preference, SHIELD_DIRS,
                                                  pre_dt_shield.cmake includes,
                                                  shield_conf_files, SHIELD_AS_LIST
                    6. pre_dt_module_run()      — SECOND run, now with SHIELD_DIRS:
                                                  recomputes DTS_ROOT /
                                                  DTS_ROOT_SYSTEM_INCLUDE_DIRS for
                                                  pass 2 (shield bindings included)
                    7. overlay/conf handoff     — see "handoff semantics" below
                    8. build_info provenance    — moves from rig.cmake unchanged
                                                  (incl. the list(JOIN) truncation
                                                  workaround)
                    9. include(real dts.cmake)  — LAST line; zephyr_default then
                                                  calls the real dts_init
  rig.cmake       DELETED. Its 675 lines redistribute per the above; the shell-
                  quoting helpers (_rig_shell_quote_argv/_rig_shell_quote_env)
                  move to the dts fork alongside their only callers.
```

MUST-NOT-CHANGE while moving: the dts fork's rig block runs at FILE scope
(zephyr_default's include scope) — never wrap it in a function; steps 5–7 set
variables (`shield_conf_files`, `SHIELD_AS_LIST`, `EXTRA_*`) that
`dts.cmake`/`kconfig.cmake` read from that scope.

Style note (2026-07-24): the `_rig_*` variable prefix is deliberate
downstream collision armor at that shared file scope; it is NOT the
zephyr-modules idiom. The upstream-patch re-shaping (function-wrapped body,
plain locals, explicit PARENT_SCOPE exports, in the pre_dt/snippets mold)
is parked for patch-drafting time — see parked.md §Build integration,
"cmake fork re-idiomization for upstream".

## Handoff semantics (deliberate behavior change, ratified)

The cache-FORCE mechanism dies with the slot move (`configuration_files` has
already run at slot 17). Replace with plain-variable edits:

- `set(EXTRA_DTC_OVERLAY_FILE <expander-overlay> [<rig.overlay>] ${EXTRA_DTC_OVERLAY_FILE})`
- `set(EXTRA_CONF_FILE <expander-conf> [<rig.conf>] ${EXTRA_CONF_FILE})`
  (note: the target variable is now `EXTRA_CONF_FILE`, not `OVERLAY_CONFIG` —
  slot 14 already performed that merge)

PREPEND, not append: precedence rule is **user extras win** — a user-passed
`-DEXTRA_DTC_OVERLAY_FILE=...` / `-DEXTRA_CONF_FILE=...` applies after all rig
fragments and can override them. The old cache-FORCE silently CLOBBERED user
values; that was a latent bug, and its death is part of this slice's contract
(verify it: pass an extra overlay on the command line, see both applied, user
last).

Internal ordering within the rig fragments is unchanged: expander output
first, then the rig folder's hand-authored `rig.overlay` / `rig.conf`.

## Pass-1 recipe: mirror → native pre_dt (saferail 13 AMENDED again)

The `_rig_dts_*` mirror block (rig.cmake:185-298, incl. the `dts/*` arch glob
workaround) is DELETED — the fork sits after hwm_v2, so the real
`pre_dt_module_run()` computes the same lists natively.

Known, accepted delta vs the old mirror: pre_dt folds `APPLICATION_SOURCE_DIR`
into `DTS_ROOT`, so the app dir's include/bindings subpaths (if any exist) now
appear in the pass-1 recipe. The old mirror excluded them citing saferail 12;
that exclusion was about *reading app DT content*, which an unused `-I` dir
does not do — and the test harness already runs pass 1 with recipes from
cached plain-build `build_info.yml`, which include an app dir. Making pass-1's
recipe derivation literally the same code path as pass-2's makes saferail 3's
edt.pickle cross-check (`test_board_dualread.py`) strictly stronger. If that
cross-check or the tier-1 goldens surface a real divergence from this delta,
report it — do not paper over it with a filter.

## Acceptance criteria

1. Commit gate fully green: `ZEPHYR_BASE=/wrk/z/ws-up/zephyr PYTHON=/wrk/z/ws-up/.venv/bin/python3 btr-shields/scripts/check.sh`
   (NOTE the new ZEPHYR_BASE — the zephyr-rigs worktree is retired; the
   workspace zephyr checkout IS the rig branch now.)
2. Corpus behavior unchanged: tier-1/tier-2 goldens pass WITHOUT refreeze
   (`RIGEXP_REFREEZE` must not be needed; if a golden moves, that is a finding).
3. Rig accept path: `west build-rig --rig nucleo-datalogger zephyr/samples/hello_world`
   full compile; the E1 extension rig (`nucleo_f401re/stm32f401xe/rig` based)
   still configures+builds. One reject rig still rejects at configure with the
   same diagnostic.
4. Plain builds untouched: a no-rig, no-shield build and a legacy `--shield`
   build of nucleo_f401re configure identically to before (the shields fork's
   plain path and the boards-fork guard are the only code they traverse).
5. User-extras precedence verified per "handoff semantics" above.
6. `cmake/rig.cmake` no longer exists; no fork re-implements logic the real
   module already runs for us (the mirror block is gone, not relocated).
7. `git diff` between each fork and its upstream namesake reads as the draft
   upstream patch (this is a review criterion, not a test).

## Companion edits (DONE by the driver, 2026-07-24 — not implementor scope)

- `.claude/agents/rig-implementor.md` + `rig-reviewer.md`: gate `ZEPHYR_BASE`
  → `/wrk/z/ws-up/zephyr`; scope wording updated; the "cmake layer UNDER
  REVIEW" freeze replaced by a pointer to this brief.
- `scripts/check.sh` usage comment updated.
- Review mode for THIS slice: driver + Tobi review jointly; the rig-reviewer
  agent is not dispatched.
