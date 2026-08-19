# The API + CLI reference slice — decisions and the route taken

**Asked by Tobi, 2026-08-19**, alongside the workdir ruling
(`workdir-retention-ruling.md`):

> extend the documentation by the API references from rigc as it can be
> extracted from the source code. Also, check if rigc's CLI interface is
> already documented and up to date.

Plus one ruling that unblocked the docs work:

> **on 3. dismiss `.docvenv`, docs should build from the workspace
> `.venv`.**

Standing instruction for the session: decide rather than ask, and record
the decision. Every decision below is mine unless attributed.

---

## 0. The `.venv` ruling — applied

`doc/howto/build-the-docs.rst` prescribed a throwaway `.docvenv` and
opened by explaining why doc dependencies do *not* belong in the workspace
environment. Both are gone. The page now says the docs build with the
workspace `.venv`, which is what has actually been true since the Sphinx
packages were installed there on 2026-08-14, and what built `-W` clean for
reference slice 1 and for everything in this slice.

The third blocker in the 2026-08-15 handoff is closed.

## 1. Is the CLI documented and up to date? — NO, on both counts

**Documented:** there was no reference page for any command. `west
build-rig`, `west rigs` and `rigc expand` appeared only inside tutorials,
as steps in a narrative. `grep -rn 'rigc-generated' doc/` returned
nothing — the work directory a diagnostic names was documented nowhere.

**Up to date:** eight stale statements, found by reading each parser and
each tutorial against the code. Every one of them is a documented promise
the tool stopped keeping, and all but the last two are consequences of the
same slice — `board-coordinate-s6-brief.md` retiring rig-level `board:`:

| # | Where | The stale claim |
|---|---|---|
| 1 | `rigc expand --board` help | "overriding rig.yml's `board:` (or the selected variant's)" — that grammar is retired; `--board` is the only source |
| 2 | `rigc expand --promote` help | "a shield name" — it takes a full target, `@rev` and assignments and `;`-lists included; metavar said `SHIELD` |
| 3 | `west build-rig --rig` help | "(today: `socket=<label>`)" — misses `socket.<slot>=`, `config.<label>=`, params and lists |
| 4 | `west build-rig --rig` help | "The board defaults to the rig's own (cmake's boards.cmake fork resolves it)" — `boards.cmake` FATALs when no board is given |
| 5 | `west rigs --explain` help | "(`socket=<label>` today)" — same as 3 |
| 6 | `build-a-rig-that-exists.rst` | shows `cat rig.yml` output containing a `board:` line no rig file has, and `socket: nucleo_ard` where the corpus says `arduino_r3` (twice, config sheet included) |
| 7 | `make-the-rig-permanent.rst` | *authors* a `rig.yml` with `board:`, then teaches that it is "a default rather than a requirement" and that "a board given on the command line wins over the rig's declared one" |
| 8 | glossary | `rig`, `rig metadata file` and `invocation coordinate` each describe the rig as carrying a board |

And, worse than stale text: **three tutorial commands could not work at
all.** `west build-rig --rig <name> <app>` with no `-b` is a
configure-time `FATAL_ERROR` since S6, and it was the headline command of
`build-a-rig-that-exists.rst` plus one command each in
`add-a-second-socket.rst` and `make-the-rig-permanent.rst`.

Separately, three `--help` strings cited design-record documents
(`multi-plug-list-brief.md`, `board-as-coordinate-brief.md`,
`board-coordinate-s6-brief.md`, `rig-variants-revisions.md`) in text
argparse prints to users. `documentation-guidelines.rst` keeps the design
record out of `doc/`; a `--help` string is the same audience.

**Route taken: fix all of it in this slice.** The tutorial commands, the
authored files, the help strings and the glossary entries are the CLI's
documentation, and "check whether it is up to date" has no useful answer
that leaves them wrong. Every command I changed was then RUN — see §5.

## 2. Where the API reference lives, and what generates it

**Decision: `sphinx.ext.autodoc`, one `automodule` per module, no
hand-written per-module prose.** The ask says "as it can be extracted from
the source code", and this package's docstrings are unusually substantial
— a hand-written reference beside them would be a second, worse copy that
starts drifting immediately.

Feasibility was measured before committing to it, not assumed:

- **All 37 modules import with no Zephyr tree and no `ZEPHYR_BASE`** —
  every `devicetree` import is deferred into a function body. So autodoc
  needs one `sys.path` entry and nothing else, and the docs build acquires
  no new dependency. (Had that not held, the fallback was
  `autodoc_mock_imports`.)
- **A trial build over all 37 modules produced 10 reST warnings**, not
  hundreds: three stray `*` (a `*-map` glob read as emphasis), two
  indented blocks read as block quotes, one line-wrap that split
  `RIG_REVISION_REQUESTED` and left a trailing `_` (an anonymous
  reference). All ten are fixed in the source, all ten were formatting
  rather than meaning.

**Decision: `undoc-members` ON, `private-members` OFF.** A reference is
complete or it misleads, and `model.py`'s dataclasses document their
fields in trailing comments autodoc cannot see — without `undoc-members`
those fields vanish from the rendered class. Private helpers stay out: the
API reference describes the surface one module offers another, and this
project's private functions are documented at length where they live.

**Decision: seven pages, by pipeline stage**, not one page per module (37
pages of two lines each) and not one page for everything (a 600 KB scroll).
`api/index.rst` carries the stage table — front door, loader, board
reader, analyzer, emitter, plus vocabulary — which is also the first
document anywhere in this tree that states the pipeline's shape for a
reader who is not already in it.

**Decision: the design-record citations stay.** Docstrings cite
`claude/*-brief.md` constantly, and `documentation-guidelines.rst` says a
page in `doc/` "never narrates how the team arrived at it". Three options:
strip the citations from ~9,600 lines of source (destroys the internal
provenance the project relies on); hand-write the pages (drifts); or
publish the docstrings as they are and scope the rule. Took the third, and
said so on the page: an admonition on `api/index.rst` tells the reader
those documents are working notes, not part of this documentation set, and
that they are provenance for a decision rather than required reading. The
guideline governs *authored* pages; the API reference is a rendering of
code.

## 3. Writing the reference found four defects — three fixed, two reported

Same lesson as reference slice 1 ("writing reference documentation is a
defect-finding activity"), and this time the finding mechanism was
publication itself: autodoc puts a module docstring in front of a reader,
and a stale one becomes visibly false.

**Fixed here** (each was already wrong, independent of the docs):

- `rigc/__init__.py` announced "**R2 state**" and claimed everything
  needing the shield library, board devicetree or headers "stays a loud,
  distinct refusal". The accept path has been complete since R5 — three
  slices earlier. Replaced with the five-stage pipeline as it is.
- `loader/__init__.py` claimed a clean load "falls through to cli.py's own
  `Unimplemented("expand: the accept path...")`". No such fall-through
  exists.
- `unimplemented.py` described itself entirely in terms of the
  differential period, which is over. It now says what still reaches it:
  an unreadable/empty/non-mapping YAML document, and cli.py's unreachable
  unknown-subcommand branch.
- `emitter/context.py::render` claimed `RIG_BOARD` is "the CLI's
  `--board` ... or the rig's own declared board otherwise" — S6 again.
- `loader/__init__.py`'s submodule list still called `params.py`
  "params/pin machinery"; the rig-side key has been `config:` since item
  29.

**Reported, not fixed** — each needs a ruling, and neither is a
documentation change:

- **Backlog 41: `rig.yml` silently ignores unknown keys.** A `board:`
  under `rig:` — the grammar S6 retired, and the exact thing
  `make-the-rig-permanent.rst` taught readers to write — is *ignored*, not
  refused. `_resolve_metadata` reads `name`/`revision`/`variants` and never
  looks at what else is there. So a pre-S6 rig, or one copied out of the
  tutorial as it stood this morning, builds against whatever `-b` says
  while its own file names a different board. Item 39/40's family:
  declared, parsed past, never read. Refuse-vs-warn is a ruling.
- **Backlog 42: `west rigs --rig TARGET` is accepted and ignored.**
  `list_rigs.add_args()` contributes `--rig` to the parser and
  `Rigs.do_run` never reads `args.rig`, so the flag silently lists every
  rig instead of resolving the target. Documented on the reference page as
  having no effect, which is honest but not a fix; the fix is either to
  wire it to `--explain`'s resolver or to stop offering it, and that is a
  surface decision.

## 4. The two drift guards

Both are corpus-level laws beside `test_dts_vocabulary_drift.py`, both
pure text scans, neither `@pytest.mark.build`.

**`test_api_reference_drift.py`** — four tests. Every production module
has an `automodule` somewhere (forward); every `automodule` names a module
that exists (reverse, which the docs build also catches under `-W`, but
`check.sh` alone should too); each module is documented exactly once; and
the pages exist at all, so neither direction can pass vacuously. The
module set comes from a filesystem walk rather than
`pkgutil.walk_packages`, because a module that fails to import is exactly
one this test should still see.

**`test_cli_reference_drift.py`** — three tests over
`doc/reference/commands.rst`. The `rigc expand` side interrogates the
**real parser** (`build_parser()`); the two west commands are scanned as
text, since importing either drags a Zephyr checkout into a test about a
documentation page. `list_rigs.py` is scanned **one function deep** —
`add_args`, the one `west rigs` actually calls — so that
`add_args_formatting`'s cmake-only `--json`/`--cmakeformat` do not start
demanding entries on a page about human-facing commands.

The forward check requires an option to have its **own entry** (a
list-table cell, or a definition-list term: an option at column 0 whose
next line is indented), not merely a mention. That refinement was not
foresight — the first version scanned the whole page, and a mutation that
renamed the `--explain` entry to `--explainer` **passed**, because a
paragraph elsewhere begins with ``--explain`` and reads as a term. It is
`test_dts_vocabulary_drift.py`'s heading-only lesson, re-learned by
running the negative control.

Both guards found real gaps the moment they first ran: three undocumented
options (`--verbose` had no entry; `--json`/`--cmakeformat` exposed the
scan-scope question above).

## 5. Verification — what was actually run

Every command that appears on the new reference page or in a fixed
tutorial was executed, not reasoned about:

- `west build-rig -b nucleo_f401re/stm32f401xe/rig --rig nucleo_datalogger
  … -p always` — builds; its four `-- Rig:` STATUS lines and the memory
  figures in `build-a-rig-that-exists.rst` were re-captured from it, and
  `ls build/rig` now lists `rigc-generated` because of the retention
  ruling.
- `west build -b … -- -DRIG=nucleo_datalogger` — the without-`build-rig`
  form, identical configure.
- `west build-rig -b mikroe_quail/stm32f427xx/rig --rig
  'eth_click:socket=quail_sock1;temp_click:socket=quail_sock2' …` — the
  list-promotion example. The board name I first wrote
  (`quail/stm32f411xe/rig`) does not exist; the run is what said so.
- `west build-rig -b nucleo_f401re/stm32f401xe/rig --rig
  'adafruit_winc1500:config.w_irq_jmp=D2' …` — the config-assignment
  example. Also `west rigs --explain` on the same target, to show the
  desugaring.
- `west rigs`, `west rigs --explain adafruit_data_logger`, `west rigs
  --boards-for adafruit_data_logger` — the outputs on the page are these
  runs' own.
- `west rigs --boards-for 'eth_click;temp_click'` lists **nothing** (four
  candidate mikroBUS sockets, so nothing is inferable) while
  `eth_click:socket=quail_sock1` lists `mikroe_quail/stm32f427xx/rig`. The
  page states that contrast because measuring it is what stopped a wrong
  example from shipping.

Docs: `sphinx-build -W --keep-going` clean, from the workspace `.venv`,
with the API reference in the toctree.

## 6. Deliberately NOT done

- **Reference slices 2 and 3** (`rig-file.rst`, `promotion.rst`, the
  42-code diagnostic catalogue) remain sequenced and unstarted. This slice
  documents the promotion target *grammar* on the commands page, because a
  reference for `--rig` cannot omit what its value looks like — when
  `promotion.rst` lands it should own the semantics and the commands page
  should link to it rather than restate.
- **`doc/index.rst`'s opening sentence** ("A rig is a board plus the
  modules plugged into it") is left alone. It is the conceptual framing of
  what gets built, and the page's own later prose ("A rig then just says
  what is plugged where") is already S6-correct. The glossary, which makes
  concrete claims about files and flags, is where the fix belonged.
- **`west rigs --rig`** is documented as ineffective rather than removed
  or wired up (backlog 42).
