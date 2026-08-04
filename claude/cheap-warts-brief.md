# Cheap warts — implementation brief

Post-cutover backlog group E, the "individually cheap" items.
Dispatched 2026-08-03.

## 0. Scope — four items, not seven

Group E lists items 18–24. Checked against the code before dispatch:

- **18, 19, 21** are real and cheap. In scope.
- **24** is real but its description is stale in a way that changes the
  work. In scope, re-specified below.
- **22 and 23 are not tasks.** Item 22 records that the config-sheet's
  section partition is frozen by inference-from-body-shape and closes
  with "Safe"; item 23 records that root-node properties would be
  invisible to both halves of the overlay split and closes with "No hole
  today". Both are observations kept so a future reader does not
  rediscover them. Leave them alone; do not invent work for them.
- **20 (banner) and 27 (stale `zephyr.dts` annotations)** are pure
  golden refreezes with no code at all. The reviewer does those
  separately. **Do not touch them.**

Two of the four in scope churn a golden. As with the lazy-shield-library
slice: **goldens are off limits to you**, you gate on `CHECK_FAST=1`
which cannot see emitted goldens anyway, and the reviewer runs the full
suite and performs the classified refreeze. Do not run `RIGC_REFREEZE=1`
and do not hand-edit anything under `scripts/rigc/tests/goldens/`.

## 1. Item 18 — the CWD-relative unknown-board message

`boarddt.py:143` renders `os.path.relpath(MODULE_ROOT)` inside a
`phys-board` diagnostic:

```
no such board directory under ./boards
```

`./boards` is only correct when the tool happens to be invoked from the
module root — which the integration harness pins deliberately. Invoked
from anywhere else the same failure renders different text, so a user
cannot reproduce a colleague's diagnostic. C1 fixed three sibling sites
and left this one outside its ratified refreeze class; this closes it.

**Fix: `anchor_path(MODULE_ROOT)`, the ratified renderer**, which
`boarddt.py:92` already uses eleven lines earlier for `board_dts` — with
a comment explaining precisely this hazard, which is what makes leaving
the other site as-is indefensible.

Note what `anchor_path` does here: `MODULE_ROOT` is the repo root and has
no `scripts/<module>/` component, so it renders **unchanged, i.e.
absolute**. That is the correct and already-ratified answer, not a
degradation — compare `loader/__init__.py::_missing_content_diag`, whose
comment states that a path outside `scripts/<module>/` "stays absolute
here — which is what an author needs in order to create the file". The
integration harness's `normalize()` turns the repo root into
`<REPO_ROOT>`, so the golden stays machine-independent.

**Predicted golden impact: `goldens/unknown-board/stderr.txt`, one line**
— `under ./boards` becomes `under <REPO_ROOT>/boards`. Nothing else.

## 2. Item 19 — a rig's own `dt-includes:` headers are absent from RIG_DEPENDS

A rig declares its token vocabulary with `dt-includes:`, the loader
cpp-resolves parameter tokens against exactly those headers, and none of
them reaches `RIG_DEPENDS`. Editing such a header therefore does not
retrigger configure. Reproduced deliberately from the blueprint; with
rigexp retired it is simply a defect.

**Do NOT mirror cpp's include search in Python.** A second
implementation of a search path is a second thing to drift. The
preprocessed output already records the answer: `parse_dts` writes
`<workdir>/<name>.pre`, and cpp linemarkers (`# <line> "<file>"`) name
every file it actually opened, nested includes included. Read the truth
back out instead of predicting it.

**Fix**: add a helper to `dtsio.py` that recovers the real files a
preprocess opened, from the `.pre` linemarkers, excluding the workdir
(the synthesized TU is a generated artifact, not a source file) — the
same exclusion rule `source_files` already applies, and worth reading
that function first since this is its sibling. Then have
`check_include` return those paths alongside its error detail, and
compose them upward through `params.check_dt_includes` →
`loader._gather_content` → `load()`'s returned `Deps`, the way every
other dependency in this codebase composes (ratified ruling 3: deps are
returned values, never an accumulator written into).

Watch the signature change: `check_include` currently returns
`Optional[str]` (an error detail or None). It becomes a tuple; update
its docstring to state both elements and their ownership, per the
docstring convention.

**Deps must be recorded whether or not the header check passes** — a
header that fails to preprocess is still a file the rig depends on, and
is exactly the file an author is about to edit.

**Predicted golden impact: `goldens/lotus_buttons/context.cmake` only.**
It is the sole corpus rig declaring `dt-includes:` (one entry,
`zephyr/dt-bindings/input/input-event-codes.h`); the four other
`dt-includes:` fixtures are all rejects and emit no `context.cmake`.
Expect that header — and any header it itself includes — to appear as
`<ZEPHYR_BASE>/...` entries, since `normalize()` substitutes
`$ZEPHYR_BASE`. If more than `lotus_buttons` changes, stop and report.

## 3. Item 21 — `types: Optional[dict]` was never tightened

`loader/__init__.py:360`'s `load()` takes `types: Optional[dict]` where
every caller passes `Dict[str, ConnectorType]`. Tighten it. Check the
whole call chain types through cleanly rather than adding a cast; mypy is
the acceptance here. No behaviour change, no golden impact.

## 4. Item 24 — re-specified, because its premise has moved

The backlog says the `'list' must be a non-empty list` `lang-schema` site
(`loader/axes.py:109`) "is still uncovered by any fixture". Checked:
**`tests/unit/loader/test_axes.py::test_empty_list_is_rejected` already
covers the code path.** So the site is not uncovered; what is uncovered
is its **wording**, because that test asserts only `diags[0].code`.

That distinction matters here specifically: reject-corpus diagnostic
wording is a ratified user-facing product surface — it is the stated
reason 40 reject goldens exist and the reason `stderr.txt` stays
byte-exact permanently.

**So the work is: add a reject fixture + goldens for it**, the same shape
as the existing axis rejects (`no-such-axis`, `unknown-revision`,
`variant-revision-collision` — read one before authoring). A rig
declaring `revisions: {list: []}`, its content file, and the
`exit_code`/`stderr.txt` goldens. No build is involved, so this is not a
`build`-marked test.

**You cannot create the goldens** (see §0). Author the fixture and wire
it into the reject corpus exactly as its siblings are wired; the reviewer
runs the suite, which will report the golden as missing, and creates it.
Say clearly in your report that you did this and what you expect the
diagnostic to say.

While you are there, strengthen `test_empty_list_is_rejected` to assert
the message text as well as the code — a unit test that pins only the
code is what let the wording go unfrozen in the first place.

## 5. Tests

Each item gets coverage at the layer it belongs to, with a stated
negative control — an implementation the test genuinely distinguishes:

- **18**: a unit test that the message renders the same regardless of
  process CWD. The control is the current implementation: run the
  renderer from two different working directories and assert equal
  output; `os.path.relpath` fails it, `anchor_path` passes. This is the
  test the wart existed for want of.
- **19**: the linemarker helper is pure over a text file and gets direct
  unit tests, including the workdir-exclusion rule (control: a helper
  that forgets to exclude puts the generated TU in the deps) and nested
  includes. The end-to-end "a declared header reaches `load()`'s Deps"
  assertion reaches cpp and is therefore integration-layer.
- **21**: mypy is the test.
- **24**: as specified above.

Standing conventions apply: `test_<module>.py` names the production unit
under test; inline YAML/DTS is dedented `"""\`-opened blocks, never
`\n`-escape strings.

## 6. Gate and handoff

```
CHECK_FAST=1 ZEPHYR_BASE=/wrk/z/ws-up/zephyr \
  PYTHON=/wrk/z/ws-up/.venv/bin/python3 \
  /wrk/z/ws-up/btr-shields/scripts/check.sh
```

mypy clean, unit suite green, coverage at or above `fail_under = 88`,
fast integration selection green.

These four items are independent. If one turns out to be more expensive
than this brief claims, **land the other three and report the fourth**
rather than dropping all of them or forcing it — and say which of the
brief's factual claims turned out to be wrong, since two of them already
were.

Leave everything **uncommitted**. Report: what changed file by file; the
exact commands you ran and their outcomes; your predicted full-suite
golden diff; and anything that surprised you.
