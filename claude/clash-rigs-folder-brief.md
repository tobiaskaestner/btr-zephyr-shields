# `boards/rigs/clash/` — the rigs that cannot build

**Status:** briefed 2026-08-14, ready to dispatch. Ruled by Tobi
2026-08-14: "move the rigs that won't compile into a sub-folder
`boards/rigs/clash` so they don't confuse as samples."

## 1. The five, and why they are not samples

`boards/rigs/` holds 22 rigs. Five are `REJECT_CASES` in
`scripts/rigc/tests/integration/conftest.py` — they exist to prove a
diagnostic fires, and every one of them FAILS to expand by design:

| rig | expected verdict |
|---|---|
| `nucleo_wifi_logger` | `phys-net` |
| `quail_dup_th` | `phys-addr` |
| `frdm_cs_clash` | `phys-cs` |
| `nucleo_mux_clash` | `phys-addr` |
| `lotus_pwm_clash` | `phys-channel` |

Re-derive from `REJECT_CASES` rather than trusting this table. Note that
two of them (`nucleo_wifi_logger`, `quail_dup_th`) are NOT named
`*_clash`, which is part of why the current layout misleads.

They keep their names, their content, and their goldens. Only their
directory moves.

## 2. THE KEY FACT — a rig's name is not its directory

`scripts/list_rigs.py::find_rigs_in` reads the name from `rig.yml`'s
`rig.name` key, never from the folder:

```python
rig_data = data.get('rig') or {}
name = rig_data.get('name')
...
ret.append(Rig(name=name, dir=maybe_rig, ...))
```

So **`RIG=<name>` invocations, every `RigCase` in `conftest.py`, and
every golden directory name are unaffected.** Only paths move. Verify
this before relying on it — it is what makes the slice small.

## 3. What to change

**a. `scripts/list_rigs.py::find_rigs_in` must recurse.** Today:

```python
for maybe_rig in rigs_dir.iterdir():
    if not maybe_rig.is_dir():
        continue
    rig_yml = maybe_rig / RIG_YML
    if not rig_yml.is_file():
        continue
```

A flat scan. `boards/rigs/clash/` would be examined, found to have no
`rig.yml`, and skipped — silently hiding all five rigs. That silence is
the danger: nothing errors, `west rigs --list` just gets shorter.

**Do NOT descend into a directory that is itself a rig.** A rig folder
may contain its own subdirectories (fixture rigs carry `shields/`), and
a nested `rig.yml` under one would be a different thing entirely. The
rule: a directory containing `rig.yml` IS a rig and is not descended
into; a directory without one is descended into looking for rigs.

**Depth**: implement arbitrary depth rather than exactly one extra
level. One level is what today's ruling needs, but a depth limit is an
arbitrary constant somebody will hit later, and the recursion is the
same code either way. Say what you chose.

**b. Move the five**, keeping each rig's own folder name:
`boards/rigs/clash/nucleo_wifi_logger/`, etc. Use `git mv`.
(`git mv` is fine and is NOT covered by the never-`git checkout`
prohibition, which is about discarding working-tree state.)

**c. Two goldens quote the moved paths.**
`scripts/rigc/tests/goldens/nucleo_mux_clash/stderr.txt` and
`.../quail_dup_th/stderr.txt` contain `boards/rigs/…` source anchors.
Re-derive the list by grep (`grep -l "boards/rigs" scripts/rigc/tests/goldens/*/stderr.txt`)
rather than trusting it — the other three appear not to, but check.
Hand-edit (`RIGC_REFREEZE=1` is BLOCKED) and verify BOTH ways: failing
before, passing after.

**d. Grep the whole tree for the five names as PATHS** — `doc/`,
`cmake/`, `tests/`, `README`s, other briefs under `claude/`. A stale
path in prose is not a test failure and will not surface any other way.

## 4. What must NOT change

- No rig name. No golden directory name. No `RigCase` entry.
- No content file. This is a move, not an edit — except the two
  goldens' path strings in §3c.
- The 17 accept rigs stay exactly where they are. **Cleanup of
  single-instance rigs is a SEPARATE question and is NOT in this
  slice** — every one of them was found to carry load-bearing coverage
  (multi-plug span, variants axis, authored address, dual-host, and
  `nucleo_datalogger`'s role as the canonical rig for six test
  modules).

## 5. A README earns its place here

`boards/rigs/clash/README.rst` (or `.md`, match the tree's convention —
check what `boards/rigs/` and `tests/rigs/` already use): one short page
saying these rigs are expected to FAIL, naming the diagnostic each one
proves, and pointing at `REJECT_CASES` as the authority. Without it the
folder name alone still leaves a reader guessing whether "clash" means
broken-and-should-be-fixed.

## 6. Acceptance criteria

1. The five live under `boards/rigs/clash/`, keeping their own folder
   names; `find_rigs_in` recurses and finds them.
2. `west rigs --list` (and the cmake `--cmakeformat` path) returns the
   SAME set of rig names as before the move. This is the load-bearing
   check — prove it by capturing the list before and after and diffing,
   not by eyeballing.
3. A directory that is itself a rig is not descended into (§3a).
4. Only the two path-quoting goldens moved; hand-edited, verified both
   ways. Every other golden byte-unchanged, stated as a checked result.
   Run `scripts/rigc/tests/integration/test_golden_path_hygiene.py`.
5. No rig name, `RigCase`, or golden directory changed.
6. §3d's grep done, with what it found reported (including "nothing").
7. The README exists.
8. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **771**, integration **284**, coverage **94%** (2026-08-14, `0246554`).
   Re-derive rather than carry.

## 7. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_rejects.py`** (it owns the reject goldens §3c
touches). Check whether it is `@pytest.mark.build`-marked before
claiming anything about it — `test_singleton_identity_law.py` turned out
NOT to be, contrary to a previous brief's assumption, so verify rather
than assume. The driver runs the full gate.

Brief the reviewer to MUTATION-CHECK: revert `find_rigs_in` to the flat
`iterdir` — `west rigs --list` must LOSE the five names, and criterion
2's before/after comparison must catch it; revert one moved golden's
path string — its test must fail on the path.

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
tables are PREDICTIONS — re-derive them. Run negative controls IN-TREE.
Purge `__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** (`git mv` is fine). Never store anything in
a `west build -d` directory. When you name a function in your report,
qualify it as `path/to/module.py::function_name`. Dispatch as
`general-purpose` on **sonnet** from a session rooted at `/wrk/z/ws-up`.
