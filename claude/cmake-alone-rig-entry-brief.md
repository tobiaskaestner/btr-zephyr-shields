# cmake-alone rig entry — slice brief

Status: direction RATIFIED 2026-07-24 (joint driver+Tobi review discussion,
follow-on to the fork-per-phase refactor, landed `016af37`). Implementation
NOT started. Small slice; independent of E2–E4, schedule at the driver's
discretion. Principle backdrop: ontology.md §7 (the board→rig lift).

## Contract

`cmake -B <dir> -S <app> -DRIG=<name[@rev][/variant]>` with **no -DBOARD**
must configure correctly, with west absent entirely. The rig is the primary
build coordinate; BOARD is derived from it. Today this fails at slot 10
(`zephyr_check_cache(BOARD REQUIRED)`); the rig→board fact lives only in the
`west build-rig` wrapper — which also means twister-as-platform (parked) can
never drive rigs until this lands.

## Design rules (all three ratified)

1. **cmake never parses rig content — it asks the resolver with the FULL
   target string.** Exactly the list_boards.py pattern boards.cmake already
   lives by. The rig qualifier grammar is hwmv2-exact (`name@rev/variant`,
   settled in rig-variants-revisions.md), so the resolver interface takes it
   verbatim from day one: pre-V1 it accepts bare names and rejects
   `@rev`/`/variant` with a LOUD not-yet-supported diagnostic; when V1/V2
   land, resolution deepens behind the same interface with zero cmake churn.
   The board is a property of the resolved rig TARGET, not the rig FILE (a
   variant may override the board) — which is why a static `board` field in
   list_rigs' enumeration JSON is the WRONG design.
2. **build-rig is a wrapper for the cmake invocation, nothing more** (Tobi,
   2026-07-24). Strip its rig.yml scanning / board inference entirely; it
   forwards `-DRIG` and the app dir, and owns zero resolution semantics.
3. **RIG and BOARD are MUTUALLY EXCLUSIVE (Tobi, 2026-07-24, supersedes the
   earlier mismatch-check rule).** If RIG is given, BOARD must NOT be given
   — even a matching value is rejected (category error: BOARD is derived
   data of the rig coordinate; the diagnostic teaches "drop -DBOARD, the
   rig owns it"). This DELETES the canonicalization problem: no comparing
   user strings against rig.yml shorthand, ever.
   Enforcement must survive reconfigures (BOARD is legitimately in the
   cache from our own inference): record the inferred value (e.g.
   `RIG_INFERRED_BOARD` cache var) at inference time; FATAL iff BOARD is
   defined and not byte-equal to that marker (covers first-configure
   both-given — marker absent — and any later conflicting -DBOARD).
   Accepted residual: a redundant, byte-identical -DBOARD into an EXISTING
   rig build dir is indistinguishable from the cache and passes harmlessly;
   all conflicts die. Consequence: `west build-rig` passes NO board to
   cmake at all.
4. **SHIELD gets the same exclusion (Tobi + driver, 2026-07-24).** In a rig
   build, SHIELD must not be defined — today it is a SILENT NO-OP (shields
   fork early-exits, dts fork overwrites SHIELD_AS_LIST), the worst
   outcome. A stock shield riding beside a rig would also carry physical
   claims invisible to the analyzer — the bug class rigs exist to kill.
   Simpler than BOARD: we never set SHIELD, so NO marker — guard in the
   SHIELDS FORK's rig path (its natural phase owner; upgrades that fork's
   draft-patch story from "return early" to "reject -DSHIELD, return
   early"): read via zephyr_get (catches cmdline/cache/env), FATAL if
   set; diagnostic says shields come from the rig (instance or
   rig.overlay) and hints that a build dir switched from --shield use
   needs a pristine. Scope line: only PHYSICAL inputs (BOARD, SHIELD) are
   excluded; config inputs (SNIPPET, EXTRA_CONF_FILE,
   EXTRA_DTC_OVERLAY_FILE) stay open — the rig owns the physical world,
   the config world remains the user's.

## Mechanics

- **boards.cmake fork, BEFORE its `include(real boards.cmake)`:** if RIG is
  defined and BOARD is not, call the resolver with the raw `${RIG}` string,
  `set(BOARD ... CACHE)` from its answer, then let the real module validate
  it exactly as a user-passed board. (This inverts the fork's current
  top-of-file order — today the real include is first.)
- **Exclusivity guard** (replaces the former canonical-mismatch check): at
  the top of the inference block, per design rule 3 — FATAL if BOARD is
  defined and does not byte-equal the recorded `RIG_INFERRED_BOARD` marker;
  set the marker whenever inference runs. No canonicalization anywhere.
- **Resolver home:** extend `scripts/list_rigs.py` with
  `--rig=<target> --cmakeformat={NAME}\;{DIR}\;{BOARD}` (mirroring
  list_boards.py's query mode; it may import the rigexp loader for the
  answer — resolution SEMANTICS belong to the loader, the script is the CLI
  seam). Enumeration mode (`--json`, used by `west rigs` + the dts fork)
  stays as is.
- **Kill the double resolution:** slot 10 stashes the resolved rig dir in an
  internal variable; the dts fork's step 3 consumes it and only falls back
  to its own list_rigs run when absent (standalone SUB_COMPONENTS
  configures).
- **build-rig:** delete the rig.yml scan (`rig.py` ~106–135); keep `-DRIG`
  injection + app-dir handling. EMPIRICAL CHECK required: does zephyr's
  `west build` refuse a fresh build dir with no `-b` before cmake runs? If
  yes, build-rig's one remaining job is bypassing that west-side gate
  (still zero rig knowledge — the board comes back from cmake); if no,
  note that plain `west build -- -DRIG=…` works and build-rig is pure UX
  sugar from here on.

## Acceptance criteria

1. Commit gate fully green; corpus goldens untouched (no refreeze).
2. Fresh-dir `cmake -DRIG=nucleo-datalogger` configure with NO -DBOARD (and
   no west on PATH for the invocation) produces a build equivalent to the
   build-rig path (same board target resolved, same zephyr.dts, same rig
   provenance in build_info.yml).
3. Fresh configure with BOTH `-DBOARD` and `-DRIG` → FATAL_ERROR regardless
   of whether the values match (message says the rig owns the board);
   reconfigure of an existing rig build dir → passes (cache-carried BOARD
   equals the marker).
4. Qualified target (`-DRIG=name@1` / `name/foo`) → loud not-yet-supported
   diagnostic from the resolver (placeholder until V1/V2).
5. `west build-rig` corpus spot-checks still pass with the inference code
   deleted; the empirical `west build`-without-`-b` result is recorded in
   the handoff.
6. A build-marked pytest covering criterion 2 (cmake-only entry) joins the
   suite.
7. `-DSHIELD` + `-DRIG` on a fresh configure → FATAL_ERROR from the shields
   fork with the shields-come-from-the-rig diagnostic; a plain `--shield`
   build (no RIG) is untouched.
