# Workdir retention — the ruling that reverses D10's accept-path deletion

**Asked by Tobi, 2026-08-19**: *"rigc should not delete the temporary
files it writes under `build/rig/rigc-generated`."*

Implemented the same day. This document records the decision, the three
sub-decisions it forced, and the route taken through each — Tobi's
standing instruction for the session was to decide and move on rather
than ask, so every one of them is mine unless marked otherwise.

## The change, in one line

`rigc expand` keeps `<--out-dir>/rigc-generated` on **every** exit. The
accept-path `shutil.rmtree` at the end of `cli.py::_expand` is gone, and
with it the `accepted` flag and the whole `try/finally` that existed only
to carry it.

## What the directory holds, measured rather than assumed

From a real accepted run of `test_three_cell_pwm.py`'s two accept cases
(the plain and the carrier rig), read off disk afterwards:

```
shield-tc_carrier.dts           146 B    <- what the loader wrote
shield-tc_carrier.dts.pre       916 B    <- what cpp made of it
shield-tc_pwm_consumer.dts      156 B
shield-tc_pwm_consumer.dts.pre  936 B
three_cell_pwm_board.dts.pre   1030 B    <- the board, preprocessed
                                20 KB total
```

A real board is bigger but not by much: the `adafruit_winc1500` workdir
already sitting in `/wrk/z/ws-up/build-rig/rig/` measures **80 KB**, of
which 63 KB is `nucleo_f401re_stm32f401xe_rig.dts.pre`.

That is the whole cost of the retention, per build directory, and it is
why the accumulation argument that motivated D10 does not survive
contact with the current layout (below).

## Why D10 said the opposite, and why that reason has expired

`cutover-decisions.md` D10 / `post-cutover-backlog.md` group A item 1
deleted the workdir on a clean accept because the expander was **leaking
one directory per invocation into `/tmp`** — 7001 directories / 787 MB
measured in a single session, 292 permanent keeps counted another time.
Deleting on success was the cheap half of the fix.

The expensive half — moving the workdir out of `/tmp` and into
`--out-dir` under a **deterministic** name, wiped on entry — is what
actually ended the pile, and it ended it *completely*:

- one `--out-dir` can hold exactly **one** `rigc-generated`, ever, because
  the name carries no `mkdtemp` suffix and entry wipes what is there;
- the directory has an owner and a lifetime — the build directory's — so
  `west build -p`, `rm -rf build/` and pytest's `tmp_path` retention each
  reap it for free.

So the deletion was answering a problem that the location change had
already solved by itself. What it still cost was real: an **accepted** run
is precisely the run that produces an overlay someone later doubts, and
the accept path was the one path that destroyed the evidence needed to
settle the doubt. The reject path had kept its intermediates since D10
for exactly that reason (a `param-missing-header` diagnostic embeds the
workdir path inside gcc's own stderr text); the argument was never
verdict-specific, only the implementation was.

## Decision 1 — the entry wipe STAYS

**Route taken: keep it.** "Do not delete the temporary files" is about
*this* run's files. Keeping a *previous* run's files in the same
directory would hand a debugging session a `shield-x.dts.pre` that no
longer corresponds to the `rig-gen.overlay` sitting one directory up —
worse evidence than none, and the exact failure mode ("a previous run's
intermediates mistaken for this run's") the deterministic name was chosen
to prevent. The wipe is now the only deletion `_expand` performs, and it
has its own test (below) so it cannot quietly become an append.

## Decision 2 — `RIGC_KEEP_WORKDIR` is RETIRED, not inverted

Three options were on the table:

1. keep the variable as a no-op (nothing to override any more);
2. invert it into `RIGC_RM_WORKDIR` for anyone who wants the old
   behaviour;
3. remove it, leaving one behaviour and no knob.

**Route taken: 3.** Option 1 is dead vocabulary — a name that reads as if
it still decided something, which is precisely the defect open as backlog
item 40 (`plug,positions`' `optional:` sub-key, parsed and never read).
Option 2 buys a code path nobody exercises to recover ~80 KB per build
directory that `west build -p` already recovers. One behaviour, no knob.

The variable was referenced in exactly two places (`cli.py` and its own
unit test), so retirement cost nothing. Anyone with it exported in a
shell profile now simply gets what they were asking for.

## Decision 3 — the `try/finally` goes with it

**Route taken: remove the block and de-indent the body** (~170 lines),
rather than leaving a `finally:` whose only remaining statement is a
`log.debug`. Verified mechanically: `git diff -w` on `cli.py` shows **22
deletions and nothing else**, so the de-indent moved no code.

## Tests — what each one pins, with the mutation that proves it

`tests/unit/test_cli.py`'s workdir section, three tests:

| test | pins | mutation that fails it |
|---|---|---|
| `test_accept_path_keeps_the_workdir` | the ruling itself | re-add the accept-path `rmtree` |
| `test_reject_path_keeps_the_workdir` | the other exit, unchanged | ditto (both exits share the sentinel) |
| `test_entry_wipe_clears_a_previous_runs_workdir` | the one deletion left | replace the entry `rmtree` with `makedirs(exist_ok=True)` |

Both mutations were applied and run, one at a time, with `__pycache__`
purged between (the same-second-restore trap in this project's notes):
mutation 1 failed tests 1 and 3, mutation 2 failed test 3 alone. Neither
was a green-on-mutation.

`test_accept_path_keeps_the_workdir` keeps a control assertion that
`context.cmake` still landed in `--out-dir` — otherwise "the workdir
survived" would also be satisfied by a run that emitted nothing at all.
The two retention tests stay SEPARATE now that both verdicts agree,
because the two exits reach the end of `_expand` by different routes (one
returns early out of `_reject`, the other falls off the end) and one
route surviving proves nothing about the other.

**What is NOT tested, deliberately**: that the *contents* survive an
accept. Nothing in `_expand` ever deleted individual files — the
whole-tree `rmtree` was the only reaper — so a directory-level assertion
is a complete proof, and a contents assertion in the unit layer would
need a real shield library and a cpp subprocess (both hermeticity
violations at that layer). Verified once by hand instead, from the real
integration accepts; the measured listing is at the top of this document.

## Out of scope, checked rather than assumed

`west_commands/rigs.py::Rigs.do_run` and `promote.py`'s query path each
create a `tempfile.mkdtemp` under `/tmp` and delete it unconditionally.
Left alone: neither is `build/rig/rigc-generated`, and a *query* command
(`west rigs --boards-for`, `--explain`) emits no artifact for anyone to
doubt later, so it has no evidence worth keeping. `cmake/dts.cmake` never
reads or globs the workdir — it only sets `--out-dir` to
`${CMAKE_BINARY_DIR}/rig` — so nothing on the cmake side changes.

## Documentation

The workdir was documented **nowhere** under `doc/` before this change
(`grep -rn 'rigc-generated' doc/` → no match). It is now part of
`doc/reference/expander-cli.rst`, written in the same session — see
`claude/api-reference-brief.md`.
