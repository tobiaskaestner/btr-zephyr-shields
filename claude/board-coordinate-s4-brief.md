# S4 — the singleton identity law

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md`
§9.1 (ruling 4), step 4 of §9.5. Prerequisites landed: S3a (`7af1fc9`,
the desugaring + `--explain`), S3b (`805b7b8`, the buildable promoted
shield).

**Read `scripts/rigc/promote.py` and `board-coordinate-s3b-brief.md`
before this file.** `promote_shield`'s own docstring already names this
slice as the reason its instance is named after the shield rather than a
placeholder — that constraint is settled and must not be renegotiated
here.

## 1. What this slice is

The law, from §9.1:

> **`--board b --rig <shield-name>` ≡ `--board b --rig <checked-in rig
> with one socket-less instance of that shield>`**

S3b made the left-hand side buildable. This slice makes the equivalence
*checked*, so the desugaring cannot silently drift from the persisted
form it claims to stand for.

## 2. §9.1 needs a correction, and this brief is it

§9.1 says the law is "byte-equality of the emitted artifact set — the
standard the frozen suite already applies. **No new comparator, no oracle
to hand-author**", authored **failing-first**.

**Neither half is reachable as written.** Five findings, checked against
the tree, each with the ruling that follows from it. §2.1–2.5 below
supersede §9.1's method; they do not touch its *claim*, which stands.

### 2.1 RULING — the law lives at expand level, fixture given by PATH

The rig name is embedded in the emitted artifacts: `rig-gen.overlay`'s
banner, `config-sheet.md`'s header, `expectations.yml`'s `rig:` key, and
`context.cmake`'s `RIG_NAME` (`emitter/context.py:90`). Byte-equality
therefore requires **both sides to carry the same rig name** — and S3a's
own namespace rule (`promote.both_paths_error`) makes a name that is both
a rig and a shield a hard error, so the two sides can never both resolve
in a single invocation.

The escape is already in the tree: **`rigc expand <path-to-rig.yml>`
takes a path and performs no namespace resolution at all.** Given by
path, the fixture rig may legally be named `adafruit_data_logger` while
the promoted side resolves the same name through `--promote`.

> **RULED: the law is asserted at the `expand` level. The fixture side is
> given by path; the promoted side by `--promote`. Both sides are named
> identically.**

**Caveat to CHECK, not assume:** a fixture rig named after a real shield
must not sit in any board root that a live namespace scan walks, or it
trips the collision rule elsewhere. Today `test_promote.py:85` tests
`both_paths_error` as a pure message unit with hand-built paths, and
nothing passes `tests/fixtures/boards` to `find_rigs` alongside the real
shield dirs — so the risk is **latent, not present**. Verify that is
still true and say so in your handoff; if a scan does reach the fixtures
root, report it rather than renaming the fixture to dodge it.

### 2.2 RULING — one exemption, `RIG_DEPENDS`, declared not filtered

Even with matching names, `context.cmake`'s `RIG_DEPENDS` cannot match:
it records resolution HISTORY (`loader/__init__.py:313`), so each side
lists its own two rig documents — the fixture's real
`boards/rigs/<name>/{rig.yml,<name>.yml}` against the promoted side's
synthesized pair inside rigc's workdir. Irreducible: the files genuinely
are different files.

> **RULED: compare every emitted artifact byte-for-byte, plus
> `context.cmake`. `RIG_DEPENDS` is compared as a SET after dropping each
> side's own two rig-document paths — the law's single explicit
> exemption, stated in the test's own docstring as an exemption, never
> applied as a silent filter.**

Everything else in `RIG_DEPENDS` — the shield's `.shield` template, its
`shield.yml`, connector-type YAML, index headers — **must be identical**,
and that is a large part of what the law is actually worth: it is the
proof that promotion reads the same sources the persisted form reads.

Note which artifacts are in play. `emit()` produces `rig-gen.overlay`,
`config-sheet.md`, `expectations.yml`, and `rig-gen-includes.dtsi` **iff
`rig.dt_includes` is non-empty**. A promoted rig declares none, so the
fixture must declare none either — or the sets differ in membership, not
just content. That is a real constraint on the fixture, and it is the
same constraint §2.3 excludes two shields for.

### 2.3 RULING — the domain is derived from the census, the exclusions asserted

§9.1 claims `a → [a]` for our `.shield` shields. **It cannot hold for all
of them today.** Measured: 14 shields under `boards/shields/`, all 14
carrying `template: true`. Two declare a `shield,params` name with **no
authored default** — `grove_btn` and `pilot_alt_button`, both
`zephyr,code`. A checked-in rig supplies such a param via `params:`; a
promoted rig has no way to, so `params.check_required` errors on the
promoted side and the two sides are not comparable. That is exactly
§9.6, whose CLI grammar is still unwritten even now that the vocabulary
question is ruled.

> **RULED: the law's domain is *promotable shields with no required
> parameter*, DERIVED from the census — never hand-listed — and the
> excluded set asserted explicitly as `{grove_btn, pilot_alt_button}`.**

Two things that ruling buys: parametrizing over the whole eligible set
makes this a **census rather than one example** (12 shields today, and at
expand level that is nearly free); and the asserted exclusion set
**shrinks visibly** when §9.6's params grammar lands, which is how a
future slice learns it just widened the law.

Derive eligibility with **one predicate, not two**: resolve the shield
library once at module scope and apply `params.check_required`'s own
rule — a `Device.declared_params` name not covered by that device's
`extra_props`. Factor it so `check_required` and the census call the same
code. A second hand-rolled copy of that predicate is a review finding.

### 2.4 RULING — mutation-verified, not failing-first

§9.1 says to author the law failing-first and require it to fail for the
named reason. **S3b already made it pass.** The law will be green on
arrival; there is no red to prove, and manufacturing one by temporarily
breaking the code proves nothing about the test.

> **RULED: failing-first is replaced by mutation-verification, and the
> brief says so rather than quietly skipping the red proof.**

Two mutations, each required to fail the law **for its own named
reason**, hashed before mutating and restored from a copy (never `git
checkout`, and purge `__pycache__` — a size-preserving same-second
restore leaves bytecode Python trusts):

1. change `promote_shield`'s desugared instance name → must fail on
   `config-sheet.md`, which is where instance names surface
   (`emitter/sheet.py`);
2. drop the desugared instance's socket-less-ness → must fail on
   inference, i.e. on the resolved topology in `rig-gen.overlay`.

That gives the same guarantee the red proof was for: the law is sensitive
to the two properties it exists to pin.

### 2.5 RULING — one build-marked cross-check

Expand-level equality does not prove the *cmake* path feeds the same
thing, and S3b's promoted branch through `dts.cmake` is brand new.

> **RULED: one build-marked cross-check — a promoted build and a
> fixture-rig build, compared with `scripts/dts_equiv.py`.**

This half **wants** different names and may have them: `zephyr.dts`
carries no rig name, and `dts_equiv` ignores comments regardless. So the
build side sidesteps §2.1's whole problem and needs no path trick — it
needs two configures, which is its entire cost. One shield is enough
here; the census belongs at expand level where it is cheap.

## 3. Acceptance criteria

1. **ZERO golden churn.** `git diff --stat -- scripts/rigc/tests/goldens/`
   prints nothing. This slice adds a law; it changes no resolution. A
   moving golden means something else broke — stop and report, do not
   refreeze.
2. The expand-level law passes for **every eligible shield** (12 today),
   parametrized, one case per shield.
3. The excluded set is asserted explicitly and equals
   `{grove_btn, pilot_alt_button}`, with the reason (§9.6) named in the
   assertion's own message.
4. Both mutations of §2.4 fail the law, each for its named reason and
   nothing else.
5. The build-marked `dts_equiv` cross-check passes for one shield.
6. mypy clean, unit green, coverage at or above the 88 floor.

## 4. Tests

**Unit** — the census predicate is a unit and belongs in
`tests/unit/test_promote.py` (it names its unit): eligibility agrees with
`check_required` on a device with a required param, on one with an
authored default, and on one with no params at all.

**Integration, not build-marked** — the law itself. It runs `expand`
twice and compares artifacts; no configure, no toolchain. Put it in its
own module named for what it pins, alongside the other expand-level
integration tests.

**Build-marked** — §2.5's single `dts_equiv` cross-check. It goes in
whichever module already owns configure-level rig comparisons; do not
start a new build-marked module for one test.

The fixture rig: one file pair under `tests/fixtures/boards/rigs/`,
declaring no `board:` (S1's injected-board relaxation is what makes the
promoted side legal, and the fixture must match), no `dt-includes:`
(§2.2), and exactly one socket-less instance named after the shield.

## 5. Verification contract — REDUCED, and it overrides the agent definition

`rig-implementor.md` says to run `check.sh`. **You do not.** The driver
runs the full gate once, after review.

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc
$PY -m pytest scripts/rigc/tests/unit -q
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q
$PY -m pytest <the ONE build-marked module your cross-check lands in> -q
git diff --stat -- scripts/rigc/tests/goldens/          # must print NOTHING
```

- **Do NOT background a command and end your turn waiting on it.**
- Never `cmd | tail; echo $?` — that reports tail's status.
- If something fails and you cannot fix it in scope, report it honestly.
  Never refreeze a golden.

## 6. Out of scope — do not start

S5 (content migration to conventional labels), S6 (strict symmetry). The
§9.6 params CLI grammar — this slice **records** its absence as an
asserted exclusion set and stops there. Any change to the desugaring
itself: `promote_shield`'s output is fixed by S3a, and this slice's whole
job is to compare against it, not to adjust it. If the law fails and the
desugaring looks wrong, **report it** — changing the thing under test to
make the test pass is the one move this slice cannot make.

**Also ignore an untracked `doc/` tree** if you see one — unrelated
driver work in progress, not yours to touch or report on.
