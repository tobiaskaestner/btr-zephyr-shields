# Slice brief — R1: rigc skeleton, CLI contract, diagnostics core, proof of life

Drafted 2026-07-28 by the driver, from `rigc-mission-brief.md` (§2 contract,
§4 arc, §5 definitions, §6 design rules) plus fresh verification at
btr-shields `28e8ce6` (R0 landed). **RATIFIED by Tobi 2026-07-28** — all
three flagged rulings (anchor-root rule; separate pytest invocation;
exit 3) accepted as written. Implementor runs on Fable (Tobi's explicit
override of the standing sonnet rule, this slice).

## Goal

By slice end, `python -m rigc expand` is a real CLI that parses the entire
frozen argv surface, renders diagnostics in the frozen stderr format from a
return-value diagnostics core, and **at least three reject goldens pass
under `RIG_EXPAND_COMPILE=rigc`** through the frozen suite — proving the
whole TDD loop (unit tests → implementation → frozen golden green through
the differential harness) end to end, once, before any larger slice relies
on it.

## 1. Package skeleton

`scripts/rigc/` grows from the R0 stub. Create only the modules R1 actually
fills (cli, diag, and the thin loader start below) — no empty placeholder
modules for analyzer/emitter; later slices create their own files.

**Unimplemented functionality fails loudly and distinctly:** message
`rigc: not implemented: <what>` on stderr and **exit 3** — never exit 1
(the reject convention: a differential red must never be mistakable for a
wrong diagnostic) and never a traceback. Exit 2 stays argparse's own
usage-error code. So the full exit vocabulary after R1: 0 accept, 1
rejected input, 2 usage error, 3 not implemented.

## 2. CLI contract

`expand <rig_yml>` with exactly the frozen surface (mission brief §2):
`--shield-dir`*, `--board-dts`, `--build-info`, `--bindings-dir`*,
`--include-dir`*, `--connector-dir`*, `--revision`, `--variant`,
`--out-dir` (* = repeatable). `main(argv) -> int` callable in-process, so
the argv contract gets unit tests without a subprocess.

**Inert-but-accepted is legal during construction:** an option R1 has no
subsystem for (e.g. `--shield-dir`) is parsed and ignored, provided the
observable bytes for the covered rejects match. Conformance is observable
behaviour; the goldens are the spec, not rigexp's internals. rigexp's code
MAY be read — it is the blueprint — but every asserted contract comes from
a golden or the frozen conftest, never from "rigexp does it this way".

## 3. Diagnostics core — return values, one renderer

The §6 rules become code here, and this is the slice's real design work:

- A diagnostic is DATA: code, message, source anchor (file, line, key).
- Functions RETURN diagnostics (alone or with a value); nothing takes a
  `diags` accumulator to write into. Composition is upward.
- ONE renderer produces the frozen format:
  `error[<code>]: <message>` newline `    at <path>:<line> (<key>)`.
- Unit tests assert STRUCTURE with synthetic content — codes, anchors,
  ordering, the format shape (a stable contract that would survive a
  rewrite). Per-diagnostic message WORDING is asserted only by the frozen
  stderr goldens, never duplicated into unit tests.

**Anchor-path rendering — a verified portability trap, ruled here.**
rigexp renders anchor paths relative to ITS OWN package dir
(`rigexp/diag.py:17`, `ROOT = dirname(__file__)`; fallback to the absolute
path when outside it). That is why goldens read `at tests/fixtures/…` for
fixtures under `scripts/rigexp/tests/fixtures/`. If rigc copied the
"my own package dir" semantic, every fixture anchor would render absolute
(`..`-fallback) and every reject golden's anchor line would miss.

**Ruling (driver, needs ratification):** rigc's rule is module-agnostic —
*if the path lies under a `scripts/<module>/` component, render it relative
to that component; otherwise render it absolute.* On the entire frozen
corpus this is byte-identical to rigexp's rule (all reject fixtures live
under `scripts/rigexp/`, all corpus rigs under `boards/` render absolute).
Its advantage appears at cutover: when fixtures move to
`scripts/rigc/tests/fixtures/`, anchors render `tests/fixtures/…`
UNCHANGED — the anchor lines of 43 reject goldens do NOT need a refreeze,
unlike the banner class. The renderer takes the rule's inputs as VALUES
(no module-scope `dirname(__file__)` constant), so unit tests exercise it
with synthetic roots.

## 4. Test scaffolding and enforcement

`scripts/rigc/tests/unit/` and `scripts/rigc/tests/integration/` — the
integration dir is created EMPTY and stays empty until cutover (the frozen
suite IS rigc's integration coverage via the harness); a short README in it
says exactly that, so nobody "helpfully" adds tests there.

- ~~Unit modules are CAPABILITY-named~~ **AMENDED post-ratification
  (Tobi, 2026-07-28, reviewing the delivered slice): unit test modules
  name their UNIT** — `test_<module>.py` per production module
  (`test_cli.py`, `test_diag.py`, `test_loader.py`, `test_conftest.py`),
  sub-folders `tests/unit/<module>/` when one unit needs several modules;
  tests may use other units but the named unit is the subject; capability
  grouping lives inside the module. The driver applied the rework (8
  capability modules → 4 unit-named + the meta discipline module, all
  43 tests preserved) and added the naming rule to the layer-discipline
  enforcement, with `test_layer_discipline.py` itself the one recorded
  meta exemption (its subject is the tree, not a unit).
- conftest provides the `assert_fixture_local` equivalent from day one
  (structural proof of what paths a test touches), even though R1's tests
  barely need it — the boundary decays if the enforcement arrives late.
- The discipline test is DIRECTORY-based, rigc's stronger replacement for
  markers: every test module lives under exactly one of `tests/unit/` /
  `tests/integration/`, and no module under `tests/unit/` imports
  `subprocess` (the structural proxy for the no-subprocess definition,
  mission brief §5).
- NO `$ZEPHYR_BASE` lookup at module scope anywhere in the package or its
  tests (the `dtsio.py:27` collection trap, designed out).
- No pytest markers in rigc's tree — the directory IS the classification.
- The unit suite stays subprocess-free and fast: target well under 1s at
  R1's size.

## 5. Gate wiring

- `scripts/check.sh`: mypy `targets="scripts/rigexp"` widens to include
  `scripts/rigc`; report the new mypy file count in the slice report.
- **rigc's tests run as a SEPARATE pytest invocation** in check.sh (own
  `--junitxml=.reports/junit-rigc.xml`), in BOTH the fast and full paths —
  it is cheap by construction.

  **Why separate (driver ruling, needs ratification):** the frozen
  `test_marker_discipline.py` reads a census that
  `scripts/rigexp/tests/conftest.py` builds from the FULL collected item
  list of the run. If rigc's marker-less tests joined the same invocation
  (via `testpaths` in pyproject), the frozen discipline test would fail
  them for carrying zero markers — and editing either frozen file is
  outside R0's ratified exception. Two invocations keep the two worlds'
  enforcement regimes cleanly apart until cutover merges them.
- `pyproject.toml` `testpaths` stays `["scripts/rigexp/tests"]`. mypy
  config: rigc is clean under the SAME `[tool.mypy]` strictness; if any
  config change proves necessary, flag it in the report rather than
  burying it.

## 6. Proof of life — the first goldens green

Target: **at least three** frozen reject tests pass under
`RIG_EXPAND_COMPILE=rigc`. Candidates, all in the loader-shape family:
`missing-content-file` (lang-content), `content-file-carries-board`,
`content-file-carries-sockets`, `revision-carries-board` (lang-schema).

Method, the S2 precedent: run each candidate fixture through rigc and READ
the actual output BEFORE writing its tests — reachability first, then TDD
the gap shut. Byte-compare against the golden yourself (stderr through the
harness's normalization, plus exit code) before claiming it; the frozen
test passing is the confirmation, not the discovery.

This requires a deliberately thin vertical start on the loader: parse the
`rig:` block of rig.yml, construct the content filename from the rig's own
`name:` (construct-don't-parse, the Q6 discipline), detect the missing
content file, load the content document's top-level keys and reject the
metadata keys (`board:`, `sockets:`) that S1/S2 moved out. Implement ONLY
what the chosen rejects need — R2 owns the loader proper. The anchor lines
(`at <path>:<line> (<key>)`) must match byte-for-byte, which forces the
diag anchor machinery to be real rather than cosmetic — that is the point
of doing proof-of-life in this slice.

Unit tests written for this sliver follow the capability naming (e.g.
`test_content_filename.py`) and the stable-contract test: filename
construction and the metadata/content key split qualify; the specific
rejection branch shape does not (that is the goldens' job).

## 7. Acceptance

A. Default gate (knob unset): frozen suite 146 green AND rigc's unit suite
   green AND mypy clean over both packages, one `check.sh` run.
B. `RIG_EXPAND_COMPILE=rigc` full frozen suite: the chosen proof-of-life
   tests PASS (name them); every other failure is the controlled exit-3
   refusal or a clean diagnostic mismatch, never a traceback. Report the
   pass count — it becomes the progress meter's baseline.
C. Zero edits outside `scripts/rigc/**` and `scripts/check.sh`
   (`pyproject.toml` only if flagged). No rigexp file, no golden, no
   fixture of the frozen suite changes.
D. rigc unit suite: subprocess-free (the discipline test proves it),
   runtime reported.
E. STOP and report before any commit. Report: files, the unit modules and
   the capability each names, proof-of-life evidence (the frozen tests
   passing under the knob, with output), the exit-3 behaviour demonstrated
   on one unimplemented path, deviations flagged.

## Out of scope, deliberately

- Shield library, board DT reading, analyzer, emitter, any accept-path
  artifact (`rig-gen.overlay` etc.) — later slices.
- Copying the fixture tree — that is a CUTOVER step; during construction
  the frozen suite supplies fixtures and integration coverage.
- `markers.sh` / `timing_report.py` integration for rigc — inherit at
  cutover.
- Any golden refreeze.

## Needs Tobi's ratification

1. **The anchor-root rule** (§3): module-agnostic `scripts/<module>/`
   rendering — byte-identical today, and it saves the 43 reject goldens'
   anchor lines from a refreeze at cutover.
2. **Separate pytest invocation** for rigc's tests (§5), forced by the
   frozen marker-discipline census; merge happens at cutover.
3. **Exit 3 for not-implemented** (§1) — minor, listed for completeness.
