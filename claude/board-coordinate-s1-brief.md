# S1 — the coordinate change, MECHANISM ONLY

Slice brief, written 2026-08-05. Parent: `board-as-coordinate-brief.md`
§9 (rulings 4–8, Tobi, 2026-08-05). This is step 1 of §9.5's revised
sequence and it unblocks everything after it.

Read §9.4 of the parent first — it is the ruling this slice implements.

## 1. What this slice is

Today `BOARD` is **derived data of the rig coordinate**: `cmake/boards.cmake`
step 1 asks `list_rigs.py` for the rig's board and `set(BOARD ...)` from the
answer, and a user-passed `BOARD` is a category error that FATALs **even when
the value matches** (`boards.cmake:97`, and the corresponding
`west build-rig` comment block, `scripts/west_commands/rig.py:10-33`).

After this slice `BOARD` is an **independent coordinate with a per-rig
default**: given, it wins; absent, it is inferred from the rig exactly as
today. Nothing else about the product changes.

**This is a mechanism change with NO data change.** No rig.yml is edited, no
corpus content moves, and the strict form (§9.4's target — `board:` leaving
rig.yml entirely) is explicitly NOT this slice. Do not start it.

## 2. Acceptance criteria

1. **ZERO golden churn.** Prove it with `git diff --stat` on
   `scripts/rigc/tests/goldens/`, empty. Not by assertion. This is the
   slice's central claim and the reason it is safe: today's inferred board
   EQUALS the rig's declared board, so injecting the resolved board back
   into rigc must be byte-inert. If a golden moves, the injection is not
   faithful — stop and report, do not refreeze.
2. `-DBOARD` + `-DRIG` **succeeds** and the GIVEN board is the one built.
3. `-DRIG` alone still infers, exactly as today.
4. A rig declaring **no** `board:` builds when a board is injected, and
   still rejects with today's frozen wording when one is not.
5. The rig-swap guard still fires for inferred builds.

## 3. The cmake side — invert step 1's authority

`cmake/boards.cmake`, step 1. Keep the resolver call and the marker
machinery; change who wins.

- **`BOARD` given by the user → use it.** Delete the exclusivity FATAL.
- **`BOARD` not given → infer from the rig**, as today, and set the
  `RIG_INFERRED_BOARD` marker.
- **Set the marker ONLY when we inferred.** A user-supplied `BOARD` must
  not be recorded as our inference — `zephyr_check_cache(BOARD)` already
  makes `BOARD` immutable per build dir, so a changed `-DBOARD` on a
  reconfigure is already caught upstream of us. This keeps the rig-swap
  guard's meaning exactly as documented for inferred builds.
- **Provenance, when the given board differs from the rig's declared one:**
  a `message(STATUS ...)` naming both. The codebase's own idiom — cf.
  `dts.cmake`'s `"Rig: shield '<s>' <- <dir>"`. Verify first that no golden
  reads cmake configure stdout (they compare rigc's stderr and artifacts);
  if one does, report instead of adding the message.
- **A rig that declares no board and no `-DBOARD` given:** FATAL naming
  both the rig and the missing flag. `list_rigs.py` already carries
  `board: str | None` and `default_board()` already returns `None` when
  unanswerable, so the resolver needs no new failure mode — only
  `{BOARD}` rendering empty and boards.cmake handling that answer.

Read the existing comment block at `boards.cmake:10-17` and `67-98`
before editing: it enumerates six reconfigure/rig-swap cases by hand. Every
one of them must still be answered after the change, and the comment must
describe the NEW rule, not the old one. A stale comment here is a review
finding.

`scripts/west_commands/rig.py` needs **no code change** — it already passes
`args.board` through untouched, so `west build-rig -b <board> <rig>` starts
working the moment the FATAL is gone. Its comment block (lines 10–33)
asserts the exclusivity as a design rule and **must be rewritten**.

## 4. The rigc side — an injected board

Add `--board <name>` to `expand` (`cli.py`; the option list is documented in
its module docstring, lines 4–8 — update it).

- **cmake passes `--board ${BOARD}` ALWAYS**, not only when the user
  supplied it. cmake becomes the single authority on which board is being
  built, and `RIG_BOARD` (`emitter/context.py:85`) then reports the board
  actually built rather than the board declared. This is what makes
  criterion 2.1 provable: inferred == declared today, so the value is
  unchanged everywhere.
- **`--board` given → `rig.board` is that value, unconditionally**,
  whatever rig.yml or the selected variant declares. No disagreement
  diagnostic: cmake owns the provenance message (§3).
- **`--board` absent → today's behaviour exactly** (rig.yml's `board:`, or
  the selected variant's). The standalone/no-cmake path depends on this —
  `boarddt.load_board(rig.board, ...)` uses the name for dts discovery when
  `--board-dts` is absent.

`loader/binding.py::resolve_board` is the single constructor (parent §1) and
is where this lands. Its contract changes in exactly one place:

- the **declared-board coherence rules keep firing as today** when a board
  IS declared — top-level XOR per-variant, and "every variant must declare
  a board, or none should". They are about the declaration's internal
  coherence and are unaffected by injection.
- **"never neither" relaxes to "never neither unless injected."** That is
  the only rule that changes.
- **`sockets:` handling is UNCHANGED in every case.** A variant's
  `sockets:` map still applies when its `board:` is overridden — this is
  the detail that later lets a dual-host variant collapse to a board
  fragment, so getting it wrong here quietly blocks S6.

Note `resolve_board` currently returns `("", SocketBinding(), [error])` on
every rejection; preserve that shape and the "later diagnostics must not be
dropped" property its docstring states.

## 5. Tests

**Unit** (`scripts/rigc/tests/unit/` — `test_<module>.py` mirrors the
production module, so `resolve_board`'s tests belong in the file that
already names `binding.py`):

- injection overrides a top-level `board:`;
- injection overrides a per-variant `board:` **while the variant's
  `sockets:` map still applies** — assert the binding, not just the board;
- injection satisfies "never neither" (no board declared anywhere);
- **no injection + no board declared still rejects**, same diagnostic —
  this is the negative control for the one relaxed rule, and it must fail
  for that reason and nothing else;
- the two coherence rules still fire under injection (declared twice;
  partial per-variant).

**Integration** — `test_cmake_alone_entry.py` is where the guard's tests
live and one of them **inverts**:

- `test_cmake_alone_board_rig_both_given_is_fatal` (line 189) asserts the
  FATAL, including `"both given"` and `"drop -dboard"` in the output. It
  must become its opposite: the combination configures, and the GIVEN board
  is the one built. Rename it to say what it now asserts. Do not leave the
  old name.
- `test_cmake_alone_reconfigure_of_rig_build_dir_proceeds` (line 208) and
  both rig-swap tests (lines 337, 370) must keep passing UNCHANGED. If one
  needs editing, that is a signal about the marker logic — report it.
- **The real falsifier for the whole slice:** a `build`-marked test that
  passes a board DIFFERENT from the rig's declared one and asserts the
  build actually used the given board. Without this, everything above is
  consistent with the injection being ignored. `ard_datalogger` declares
  `nucleo_f401re/.../rig` and `frdm_k64f/mk64f12/rig` per variant, so both
  are real, buildable boards to cross.
- a `build`-marked test for a rig declaring no `board:` built with
  `-DBOARD` (new fixture rig — no corpus rig omits `board:`).

Every new negative control must be **mutation-verified**: the control fails
for its named reason and nothing else. Purge `__pycache__` after any
mutate-and-restore, and hash-check the restore against a hash taken BEFORE
mutating.

## 6. Docstrings and conventions

- Public functions state **return semantics and ownership** in prose.
- Tests write YAML/DTS as **dedented triple-quoted blocks**, not inline
  `\n` escapes.
- `resolve_board`'s docstring currently states the five rules including
  "never neither" — it must state the new rule. Same for `cli.py`'s option
  list and `emitter/context.py:48`'s note on `RIG_BOARD`.

## 7. Out of scope — do not start

`--boards-for` (S2), the `--rig <shield>` promotion (S3), the singleton
identity law (S4), content migration to conventional labels (S5), and
strict symmetry / removing `board:` from rig.yml (S6). Also: the ad-hoc
params CLI grammar, whose token exit is unruled (parent §9.6).
