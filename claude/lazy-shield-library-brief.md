# Lazy shield library — implementation brief

Post-cutover backlog item 5 (group B), the item with real leverage.
Dispatched 2026-08-03.

## 0. The ruling that unblocks this

The one remaining pin on this slice was **scan-time diagnostic ORDER**:
broken shields report before rig-side diagnostics today, `stderr.txt` is
byte-exact permanently, and a lazy scan moves or elides those
diagnostics.

**Tobi, 2026-08-03: order need not be preserved. rigexp is no longer a
point of reference.** A reject golden whose diagnostic order changes is
a deliberate refreeze, not a regression — provided the change is
*classified* (see §4) rather than blanket-blessed.

That does not loosen `stderr.txt` as a contract. It stays byte-exact.
What changed is that its CONTENT may now be re-derived when the tool's
own execution order changes for a good reason.

## 1. What is wrong today

`loader/library.py::load_shield_library` walks every shield-library root
and, for every folder that has a `<name>/<name>.shield`:

- reads `shield.yml` (cheap YAML) to get the `revisions:` axis;
- **if the shield declares no axis, cpp-preprocesses and dtlib-parses its
  template right there** (`parse_tu` → `parse_dts` → a `gcc -E`
  subprocess), whether or not any rig references it;
- if it DOES declare an axis, defers the parse to `resolve()`'s first
  selection (`_Pending`) — the lazy path this slice generalises.

Consequences, all recorded as warts:

1. **It does not scale.** 14 shield folders in this repo means 14 cpp
   subprocesses per invocation; `nucleo_mux_farm` references 2 shields
   and pays for 13. Bridle is 19+ folders; a real upstream shields tree
   is worse. `dts.cmake` runs the expander once per configure, so every
   build pays this.
2. **One malformed member poisons the whole scan.** A `LoadError` from
   any template's cpp/dtlib parse aborts the scan, so a broken shield
   nobody references fails a rig that never mentions it.
3. **Dependency data records shields nobody referenced.** Every
   discovered `.shield` lands in `RIG_DEPENDS`, so editing an unrelated
   shield template re-triggers configure for every rig in the tree.

One change retires all three.

## 2. The change

**Discovery stays eager. Parsing becomes lazy.**

Discovery = the folder walk, the `<name>.shield` presence probe, and the
`shield.yml` axis read. It is cheap, it has no subprocess, and it is what
builds the known-shields census that `lang-instance-shield` prints. It
does not change.

Parsing = `parse_tu` + `parse_shields` + `_pick_shield`. It moves to
`ShieldLibrary.resolve()`, for axis-less shields exactly as it already
works for revisioned ones.

Concretely:

- `_Pending.decl` becomes `Optional[AxisDecl]`, and
  `load_shield_library` records a `_Pending` for **every** discovered
  shield, not just the revisioned ones. The `decl is None` branch that
  calls `parse_tu` at scan time goes away entirely; `axes[name] = decl`
  still records `None` for an axis-less shield, so `axes` remains the
  census and remains the thing that distinguishes the two kinds.
- `resolve()`'s bare-name path, for `decl is None`, stops returning
  `(None, [], deps)` on a cache miss (today's "the scan already reported
  this") and instead parses the base template on first reference,
  memoizing the result in `self.shields[name]` exactly as
  `_resolve_revision` memoizes `self.shields[f"{name}@{rev}"]`.
- Factor the shared body — build the TU, `parse_shields`, `_pick_shield`,
  collect deps — so the axis-less path and `_resolve_revision` do not
  hand-duplicate it. One helper, two callers.

### 2.1 Failure memoization is REQUIRED

Today a broken axis-less template reports **once**, at scan time, no
matter how many instances reference it. Naive laziness reports once per
reference.

**Decided: a failed base parse is memoized and reports once.** Record the
name in a failure set on the library; a later `resolve()` of a name in
that set returns `(None, [], deps)` silently — which is precisely the
semantics the current cache-miss branch has, just reached by a different
route.

This is not observable in any golden today (`shield-node-name-mismatch`
references its broken shield once), which is exactly why it needs a unit
test with a negative control: an implementation that forgets to memoize
failures passes the whole frozen suite.

**Deliberate non-change:** `_resolve_revision` does NOT memoize its
failures today, so a repeated bad revision re-reports. Leave that alone —
it is pre-existing behaviour, no golden distinguishes it, and changing it
is not this slice. Note the asymmetry in a comment so it reads as a
decision rather than an oversight.

### 2.2 The LoadError boundary needs no new plumbing

A lazy base parse can now raise `LoadError` from inside
`_build_topology`, which already carries its own D1 boundary for exactly
this reason (a lazily-resolved revision could already raise there). The
`try/except LoadError` in `load_shield_library` stays — it still guards
the eager `shield.yml` reads in `_load_shield_revisions`.

Verify this rather than assume it: a fixture whose *referenced* shield
template fails to preprocess must still render every diagnostic gathered
before the raise, not just the fatal one.

### 2.3 Dependency data moves to the point of reference

Drop the `deps = union(deps, touch(base_file))` in the discovery loop.
The base template is recorded when a rig actually references it.

There is already a precedent in this file for exactly this split:
`shield.yml` is READ at scan time but only recorded as a dep inside
`resolve()` (`touch(self.ymls[name])`), on the stated grounds that "a rig
depends only on the metadata of shields it actually names". The base
template now follows the same rule.

**Touch the base file explicitly** in the resolve path — for both the
axis-less and the revisioned case. In practice it also arrives via
`source_files(dt, workdir)` (cpp linemarkers name it, because it defines
nodes), but a template that defines no nodes at all would silently drop
out of `RIG_DEPENDS` if we relied on that. Adding it to
`_resolve_revision` too is predicted to be golden-inert; if a golden does
change because of it, that is a finding to report, not to bless.

## 3. What must NOT change

- **Discovery breadth.** `axes` must still name every discovered shield.
  A rig naming an unknown shield must still print the full
  `known shields: ...` list — all 14 in this repo — with **zero**
  templates parsed. This is the single most important invariant in the
  slice and it needs a test that fails if discovery is made lazy too.
- **The `lang-shield-name` diagnostic itself.** Same code, same wording,
  same `SourceRef(template, 1)` anchor.
- **`RIG_SHIELDS`**, which is derived from resolved instances, not from
  the library.
- **The connector-type registry.** `load_types` reads all four connector
  YAMLs and all four index headers regardless of the rig; that is
  rig-independent and out of scope.
- **`model.py`** (saferail 9).

## 4. Predicted golden impact — this IS the acceptance criterion

State the prediction first, then measure it. A prediction that survives
measurement is evidence; a refreeze performed without one is a blank
cheque.

**Predicted: every reject golden is byte-identical. Zero churn.**

Reasoning, verified against the corpus: exactly one reject golden carries
a scan-time template diagnostic (`shield-node-name-mismatch/stderr.txt`,
one `lang-shield-name` line), and that fixture's rig **does** reference
the broken shield, so the diagnostic is still produced — just from
`resolve()` instead of the scan. It is the only diagnostic in that file,
so there is no relative order for the move to disturb. No golden carries
`lang-cpp`, `lang-parse` or `lang-shield-type` at all. The
`lang-schema` shield-side diagnostics
(`shield-bad-revisions-block`, `shield-revisions-mapping-entry`) come
from `shield.yml`, which stays eager.

**Predicted: every accept golden changes in exactly one way** —
`context.cmake`'s `RIG_DEPENDS` loses the `.shield` entries of shields
that rig does not reference, and nothing else. `overlay`,
`config-sheet.md`, `zephyr.dts`, `conf`, `expectations.yml`,
`exit_code` all unchanged.

Worked example, `lotus_buttons`: it references `grove_btn` and
`grove_led`. Its `RIG_DEPENDS` should lose the twelve other
`boards/shields/*/*.shield` entries and keep everything else — both
grove templates, both `shield.yml`s, the board `.dts`, the rig's own two
YAML files, the four connector bindings, the four index headers.

`compare_context_cmake` compares `RIG_DEPENDS` as a **set with exact
membership** (`_UNORDERED_SET_VARS`), not must-contain — so this churn
is real and the goldens must be refrozen. Note for the record: the
backlog's "RIG_DEPENDS breadth is no longer a blocker" meant order-free,
not membership-free.

**The refreeze is the reviewer's job, not the implementor's.** You run
`CHECK_FAST=1`, which by construction checks no emitted golden at all
(check.sh's own docstring; backlog item 14) — so you cannot see this
churn and must not attempt to. Do not run `RIGC_REFREEZE=1`. Do not
hand-edit a golden. Report your prediction; the reviewer runs the full
suite, refreezes, and classifies the diff against §4.

If you believe a golden outside this predicted class must change, **stop
and report** rather than working around it.

## 5. Tests

Unit layer (`scripts/rigc/tests/unit/loader/test_library.py`), in-process,
no subprocess — note that anything reaching `parse_tu` reaches cpp and is
therefore integration by construction (dtsio.py's own seam rule), so
split accordingly and put the cpp-reaching cases in the integration
layer.

Required, each with a stated negative control — an implementation the
test actually distinguishes:

1. **Discovery is still eager and complete.** After
   `load_shield_library` over a multi-folder root, `axes` names every
   folder and `shields` is empty. Negative control: a lazy-discovery
   implementation (walk deferred to first reference) fails this.
2. **Nothing is parsed until referenced.** Same scan, then assert no
   translation unit was written into the workdir. Negative control:
   today's eager implementation fails it. This is the test that proves
   the slice did what it says.
3. **First reference parses; second reference does not re-parse.**
   Negative control: an unmemoized implementation fails the second half.
4. **A broken template reports once across two references** (§2.1).
   Negative control: an implementation that memoizes only successes
   reports twice.
5. **An unreferenced broken template is silent** — a rig that never names
   it loads clean. Negative control: today's implementation fails this;
   it is wart 2, and this test is what retires it.
6. **`RIG_DEPENDS` excludes unreferenced templates and includes
   referenced ones**, asserted on the `Deps` value returned by `load()`,
   not on a golden. Negative control: keeping the discovery-time
   `touch(base_file)` fails it.
7. **The known-shields census survives** — an unknown shield reference
   still lists every discovered shield (§3, first bullet).

Follow the ratified test conventions: `test_<module>.py` names the
production unit under test; inline YAML/DTS is written as dedented
`"""\`-opened blocks, never `\n`-escape strings.

## 6. Logging

`log.info("shield library: %d eager, %d pending", ...)` becomes a lie the
moment nothing is eager. Make it report what is now true — how many
shields were DISCOVERED — and add a DEBUG or INFO line at the point a
template is actually parsed, so `-vv` shows the lazy parse happening.
`parse_tu` already logs `shield TU: <name>` at INFO, so the count of
those lines is the direct measurement for §7.

Keep the standing rule: log records describe the tool's execution;
Diagnostics describe the user's input. Logging never becomes a second
findings channel.

## 7. Measure the win

Report, as numbers, for one real rig (`nucleo_mux_farm` is the recorded
example: 13 eager TUs for a rig referencing 2):

- `shield TU:` lines at `-vv` before the change and after;
- wall time of one `expand` invocation before and after.

Two runs, same rig, same flags. This is the claim the slice exists to
make, so it needs a measurement rather than an assertion.

## 8. Gate and handoff

Your gate, as many times as you like:

```
CHECK_FAST=1 ZEPHYR_BASE=/wrk/z/ws-up/zephyr \
  PYTHON=/wrk/z/ws-up/.venv/bin/python3 \
  /wrk/z/ws-up/btr-shields/scripts/check.sh
```

mypy clean, the whole unit suite green, coverage at or above the
`fail_under = 88` floor, and the fast integration selection green. The
full suite (`check.sh` with no `CHECK_FAST`) and the golden refreeze are
the reviewer's, per §4.

Leave everything **uncommitted**. Report: what changed file by file; the
exact commands you ran and their outcomes; the §7 measurement; your
prediction for the full-suite golden diff; and anything that surprised
you.

## 9. Project paths

The agent definition still points at `/wrk/z/ws-up/claude/rigs/` — those
documents now live in the repo at `/wrk/z/ws-up/btr-shields/claude/`.
This brief and its acceptance criteria win over the agent definition
wherever they disagree.
