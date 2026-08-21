# rigc external code review — findings and improvement plan (2026-08-19)

Scope: `scripts/rigc/` (38 non-test modules, ~9,600 lines), reviewed cold —
no prior session context, only the code, `doc/`, and in-source comments,
deliberately taking an external reviewer's seat. Cyclomatic complexity
measured with radon 6.0.1 (247 blocks, average 5.3 / grade B).

This brief has two parts: the findings (context for whoever implements),
then a task list scoped for one-task-per-agent implementation, each with
acceptance criteria. Tasks are ordered by value; A and B are independent
and parallelizable per package.

---

## Part 1 — Findings

### 1.1 Architecture: strong, and accurately documented at the stage level

The five-stage pipeline (cli → loader → board reader → analyzer → emitter,
with `model`/`diag`/`buskind` as shared vocabulary) is real in the code and
matches `doc/reference/api/index.rst`'s table exactly. The design
disciplines are consistently applied and genuinely good:

- passes are value functions returning `(piece, diagnostics)`; one composer
  per stage (`analyzer.analyze`, `loader.load`);
- diagnostics are data with one renderer (`diag.render`);
- IO at the edges (`emitter.write_artifacts` is the only artifact writer;
  `fragments.py` decides over a `FragmentPresence` value the caller probes);
- one seam per shared lookup (`analyzer/socketmap.py`, `buskind.py`);
- deterministic output (sorted keys throughout, `ordering.allocation_key`).

### 1.2 Architecture: weaknesses

1. **Filesystem layout does not mirror the documented stages.** The docs
   group `rigc.shields`/`rigc.registry` under the loader stage and
   `boarddt`/`board_edt`/`edt_build`/`board_census`/`dtsio` under the board
   stage, but all seven sit flat at package top level. `boarddt.py` vs
   `board_edt.py` is a near-collision an outsider cannot tell apart from
   the names alone.
2. **`dtsio.py` understates its contents** — it is shield-TU cpp+dtlib
   plumbing *plus* the connector-header index parser *plus* the
   per-instance-parameter token resolver.
3. **Two error-reporting conventions.** Most of the tree returns
   `Diagnostic` values; `promote.py` returns plain error-message *strings*
   (`parse_promotion_opts` returns `Union[ParsedPromotionOpts, str]`,
   `check_promotable` returns `Optional[str]`), and `cli.py` wraps them
   back into diagnostics at the call site.
4. **CLI owns grammar it shouldn't.** `cli._expand` parses the
   `;`-separated `--promote` list inline (element splitting, per-element
   opt parsing, duplicate check) — promotion grammar that belongs beside
   the rest of it in `promote.py`.
5. **Vestigial seam.** `SocketBinding` is an always-empty identity map
   (binding.py says so itself) threaded through six signatures
   (`load` → `_resolve_metadata` → `parse_instance` → `_parse_sockets_block`
   → `_apply_instance_patch` → `apply_delta`). Kept deliberately as a
   future seam, but it costs a parameter in every topology function today.

### 1.3 Latent bug: hard-coded `"plug"` slot names

`model.py` states the contract twice: a single-plug shield's slot name is
the plug node's **own name** — "`plug` by convention, but its NAME, not a
default". `shields.py` enforces nothing about the node name. Yet:

- `loader/delta.py:112` (`_parse_sockets_block`, single-plug branch)
  returns `{"plug": <ref>}` **literally**, while `Shield.plugs` is keyed by
  the actual node name. A single-plug shield whose plug node is named
  anything else gets an `Instance.sockets` map whose key matches no slot:
  the authored `socket:` is silently ignored and inference runs instead.
- `analyzer/wires.py:81` and `emitter/sheet.py:132` call
  `for_slot(..., "plug")` literally; on such a shield sheet.py's
  `assert socket is not None` fires — a crash on an accepted rig.
- `emitter/sheet.py:55` (`_strap_owner_slot`) and
  `analyzer/ordering.py:34` (`dev.plug or "plug"`) fall back to the same
  literal.
- `analyzer/sockets.py:293`'s docstring even claims "a single-slot shield's
  one slot is always named `plug`" — an invariant asserted in prose and
  enforced nowhere.

Either the convention becomes a checked rule (a `lang-shield-plug`
diagnostic when a single plug node is not named `plug`) or the literals go
and the one slot name is always read from `shield.plugs`. Task C below
picks the second (it matches model.py's stated contract); if the
maintainer prefers the first, C shrinks to one diagnostic in shields.py
plus deleting model.py's "not a default" sentences.

### 1.4 Cyclomatic complexity

Average is healthy (5.3); the tail is not. 18 functions exceed CC 15:

| CC | Function | Location |
|----|----------|----------|
| 43 | `_parse_shield` | shields.py:154 |
| 29 | `_allocate_scope` | analyzer/addresses.py:160 |
| 28 | `_expand` | cli.py:314 |
| 27 | `_parse_device` | shields.py:355 |
| 26 | `parse_promotion_opts` | promote.py:188 |
| 26 | `resolve_sockets` | analyzer/sockets.py:280 |
| 24 | `allocate_cs` | analyzer/cs.py:123 |
| 22 | `apply_delta` | loader/delta.py:354 |
| 21 | `render_sheet` | emitter/sheet.py:96 |
| 21 | `render_overlay` | emitter/overlay.py:53 |
| 20 | `check_wires` | analyzer/wires.py:22 |
| 19 | `_parse_exposed` | shields.py:569 |
| 19 | `_compose_channel_map` | analyzer/sockets.py:184 |
| 18 | `resolve_axis_selection` | loader/axes.py:436 |
| 18 | `check_nets` | analyzer/gpio.py:271 |
| 17 | `parse_revision_decl` | loader/axes.py:219 |
| 17 | `_parse_sockets_block` | loader/delta.py:53 |
| 16 | `compose_socket` | analyzer/sockets.py:74 |

`shields.py:_parse_shield` (43) is the outlier: one function walks the
template's children four times (plugs, pads/config, device groups, plug
bus groups, exposed sockets) with the group-classification rules inline.

### 1.5 Naming (modules, functions, fields)

Mostly apt. The exceptions an outsider stumbles on:

- **`GpioRef`** models gpio *and* pwm *and* adc references (it carries a
  `function` field saying which). Every pwm ref being a "GpioRef" misleads;
  `FunctionRef` or `PosRef` would say what it is.
- **`Instance.pins` / `pin_refs`** hold *strap* selections from the rig's
  `config:` block. The rig-facing key was renamed from `pin:` to `config:`
  (params.py notes this); the model field kept the old name.
- **`ExposedSocket.buses: Dict[str, object]`** and **`channel: object`**:
  the `object` values force `assert isinstance` / `cast` at the consumers
  (sockets.py:126, overlay.py:366). The actual shapes are
  `("plug", slot) | ("scope", label)` and `int` — expressible as types.
- **`Solved.channels`** values are anonymous 6-tuples unpacked as
  `(fn, ctrl, ch, period, flags, pos)` at three sites; a NamedTuple would
  name them once.
- `boarddt` vs `board_edt` (see 1.2).

### 1.6 Documentation fit

- The API reference delegates all prose to module docstrings via
  `automodule`, with a drift test guaranteeing coverage. The stage
  descriptions match the code. Good mechanism.
- **The gap is the Explanation quadrant**: `doc/explanation/` contains only
  the documentation guidelines. The actual architecture rationale lives in
  `claude/architecture.md` — a working note the docs explicitly disclaim.
  An external reader gets the *what* (reference) and *how* (tutorials) but
  the *why* only through insider notes.
- `doc/reference/api/index.rst` already warns that docstrings cite
  `claude/` design records "as provenance, not a reference you are expected
  to have" — an honest patch over the problem Part 1.7 describes, not a fix.

### 1.7 Inline comments: the main liability

The comment *quality* is high in places (`board_edt._controller_label`'s
"Constraint the code cannot show" is exemplary; the cs.py aliasing-bug
note guards a real invariant). But measured across the 38 non-test
modules:

- **174 citations of `*-brief.md` files** (in 36 of 38 modules) — session
  working notes under `claude/`, unreadable as references for an outsider
  and half-opaque even when opened ("multi-plug-shield-brief.md Sec 2
  ruling 2").
- **47 references to `rigexp`**, often with line numbers
  ("rigexp/loader_yml.py:1028", "analyzer.py:263-440") — `scripts/rigexp`
  **no longer exists in the tree**. Every one of these points at deleted
  code.
- **43 R-number references** (R3…R27, "R2's ShieldRef seam") plus a private
  codeword vocabulary: Conv. 1–4, S6/S8, V1a/V1b/V1c, D1, T0b, L3, "Option
  C", "ratified ruling 3", "acceptance criterion 6", "item 29/30",
  "gap #4", "RULED 2026-08-14", "(Tobi, 2026-08-08, decision 2)".
- **Change-narration presented as documentation** — pure noise for anyone
  who wasn't there, exactly the pattern flagged in this review's mandate:
  - model.py: "R2's ShieldRef seam is GONE (rigc-r3-brief.md Sec 0)…"
  - binding.py: the whole module docstring narrates what `board:`/`sockets:`
    grammar *used to be* and which rules "went with the grammar they policed".
  - cli.py's docstring: three paragraphs on the history of workdir deletion
    (D10, its supersession, the retired `RIGC_KEEP_WORKDIR` env var, "7001
    directories / 787MB in one session").
  - shields.py `_RESERVED` comment: "its removal is a CLEANUP, not the
    fix… Verified by mutation: restoring `plug` here changes no behavior."
  - cs.py: "The earlier shape — `dict(nets_before)` — shallow-copied the
    dict but SHARED the per-key claim lists…" (the invariant is worth
    keeping; the archaeology of the old bug is not).
  - buskind.py: "(now: four, before this move)".
  - unimplemented.py: "That period is over."
- **Sheer volume**: model.py is roughly half comment; several field
  comments are 15-line essays (`ExposedSocket.pwm_map`,
  `BoardSocket.pwm_cells`). Load-bearing constraints drown in provenance.

What must be *kept* (rewritten present-tense, citation-free): golden-bytes
contracts (workdir name normalization, diagnostic wording/order stability),
real invariants (cs.py no-aliasing, emitter's 2-cell PWM refusal,
`_needed_param_includes` ↔ `check_param_token` coupling), and external
constraints (the zephyr shield-schema pin in `parse_legacy_revision_decl`).

### 1.8 Small items

- `cli.py:320`: leftover `# breakpoint()` debug comment.
- `loader/__init__.py:297` passes context string `"rig"` to
  `require(content_v, "instances", …)` although the mapping is the content
  document — the diagnostic would say "rig: required key…" for a file that
  isn't rig.yml. (Wording may be golden-frozen; verify before changing.)

---

## Part 2 — Improvement plan (agent-sized tasks)

Ground rules for every task:

- The frozen golden/test suite is the gate: run
  `scripts/rigc`'s full pytest suite before and after; stderr bytes and
  emitted artifacts must not change unless the task explicitly says so.
- Diagnostics order and wording are contracts. Refactors must preserve
  them byte-for-byte.
- One task per agent; do not mix comment rewrites with refactors in one
  change.

### Task A — comment and docstring hygiene sweep  [4 parallel agents]

Split: A1 top-level modules (`__init__`, `cli`, `model`, `diag`, `buskind`,
`dtsio`, `promote`, `registry`, `shields`, `boarddt`, `board_edt`,
`edt_build`, `board_census`, `deps`, `unimplemented`), A2 `loader/`,
A3 `analyzer/`, A4 `emitter/`.

Rewrite policy, applied per comment/docstring:

1. **Delete** references to `rigexp` paths/line numbers (the tree is gone).
   Where the sentence's only content was "ported from rigexp X", delete the
   sentence; where it stated a behavioral contract ("reproduces the
   blueprint's discovery order"), restate the contract without the citation
   ("problems are reported in a single sequential pass so conflict and
   exhaustion findings interleave in processing order").
2. **Replace** `*-brief.md` / R-number / ruling / codeword citations with
   the one-sentence *reason* in place. If the reason is already stated,
   just drop the citation. Codewords (Conv. N, S6/S8, D1, V1b, "Option C",
   R18…) must not survive; spell out what they mean or delete.
3. **Rewrite change-narration as present-tense invariants.** "X is GONE /
   retired / no longer fires / used to be Y" becomes either a statement of
   what *is* (if load-bearing) or nothing. History belongs in git.
4. **Keep and sharpen** the load-bearing constraints listed in finding 1.7
   ("what must be kept"). Target: every surviving comment states a
   constraint the code cannot show, in ≤5 lines.
5. **Shrink model.py field essays** to ≤4 lines each; move anything longer
   into the owning module's docstring only if it is a real contract.
6. Remove `# breakpoint()` at cli.py:320 (A1).

Acceptance: zero occurrences of `rigexp`, `-brief.md`, `RULED`, `ratified`,
and bare `R[0-9]+`/`S[0-9]`/`V1[abc]`/`Conv\.` codewords in non-test
`scripts/rigc/**/*.py`; full test suite green; `doc/` build green
(docstrings are the API reference, so read the rendered pages);
no functional diff (`git diff` touches only comments/docstrings).

### Task B — complexity refactors  [5 agents, independent]

Target: every function in the 1.4 table at CC ≤ 15, verified with
`radon cc -s`. Byte-identical outputs; extract, don't redesign.

- **B1 `shields.py`** (`_parse_shield` 43, `_parse_device` 27,
  `_parse_exposed` 19): extract per-section helpers from `_parse_shield`
  (`_parse_plugs`, `_parse_pads_and_config`, `_parse_template_groups`,
  `_parse_plug_groups`, `_parse_exposed_sockets`), keeping walk order (and
  therefore diagnostic order) identical. In `_parse_device`, split the
  reg/addr-from/unit-address validation block from the property walk. In
  `_parse_exposed`, the gpio-map loop and the bus-property loop are natural
  helpers.
- **B2 `cli.py`** (`_expand` 28): extract the whole `--promote`
  materialization block into a helper returning
  `(rig_path, revision) | exit-code`, and move the `;`-list element loop
  into `promote.py` (a `parse_promotion_list(target, shield_dirs)`
  returning elements or an error string — same convention the module
  already uses). `_expand` keeps: path absolutization, workdir setup,
  the load→board→analyze→emit sequence.
- **B3 `analyzer/`** (`_allocate_scope` 29, `resolve_sockets` 26,
  `allocate_cs` 24, `check_wires` 20, `_compose_channel_map` 19,
  `check_nets` 18, `compose_socket` 16): in `_allocate_scope`, the three
  near-identical sorted member-building loops collapse into one loop over
  `(group, kind)` pairs; the problem→diagnostic translation is a helper.
  In `resolve_sockets`, lift `infer_socket`/`resolve_one` to module-level
  functions taking explicit state (they already close over only four
  values). In `allocate_cs`, extract per-scope member building and the
  placement→result folding. `check_wires`: extract the via-route
  resolution. `check_nets`: extract the per-key verdict.
- **B4 `loader/`** (`apply_delta` 22, `_parse_sockets_block` 17,
  `resolve_axis_selection` 18, `parse_revision_decl` 17,
  `_apply_instance_patch` 15): `apply_delta` becomes five per-key handlers
  (`instances:`, `add-instances:`, `remove-instances:`, `remove-wires:`,
  `add-wires:`) called in the same fixed order. In `resolve_axis_selection`
  extract the hwmv2 branch (`_resolve_revision_selection`). Axes/decl
  parsers: extract the shared list-of-entries loop.
- **B5 `emitter/`** (`render_sheet` 21, `render_overlay` 21): extract one
  helper per output section (sheet: socket table / straps / channels /
  wires / cs; overlay: i2c scopes / spi scopes / plain groups), appending
  to the same list in the same order.

Acceptance per agent: radon shows CC ≤ 15 for the named functions; emitted
artifacts and stderr byte-identical on the test corpus; no public-name
changes (tests import some helpers).

### Task C — fix the hard-coded `"plug"` slot name  [1 agent]

Per finding 1.3. Chosen direction: the slot name always comes from the
shield.

1. `loader/delta.py:_parse_sockets_block` single-plug branch: key the
   returned map by `next(iter(shield.plugs))` (guard the plugs-empty error
   case, which returns before this point).
2. `analyzer/wires.py:81` and `emitter/sheet.py:132`: replace
   `for_slot(..., "plug")` with the instance's one slot
   (`next(iter(inst.shield.plugs))`); both sites already know the shield is
   single-plug.
3. `emitter/sheet.py:_strap_owner_slot` fallback and
   `analyzer/ordering.py:34`: same substitution where an `inst`/`shield`
   is in hand; where only a `Device` is (ordering.py), `dev.plug` is
   already correct for bus devices — keep, but document that plain-group
   devices never reach the allocators.
4. Add a regression test: a single-plug shield whose plug node is named
   `north`, with an authored `socket:` — assert the socket is honored (not
   inferred) and the sheet renders without crashing.
5. Leave `GpioRef.plug`/`Device.plug` *defaults* alone only if removing
   them would churn tests; otherwise make them required at construction in
   shields.py (which always knows the real slot).

Acceptance: new test passes; full suite green; corpus output unchanged
(every corpus shield names its plug `plug`, so bytes must not move).

### Task D — structural moves (needs maintainer sign-off first)  [1 agent]

Optional; import/doc churn. Do not start without an explicit go-ahead.

1. New `rigc/board/` package: `boarddt.py`→`board/resolve.py`,
   `board_edt.py`→`board/project.py`, `edt_build.py`→`board/edt_build.py`,
   `board_census.py`→`board/census.py`, with compatibility re-export
   shims if external callers exist (`west_commands`, `list_rigs.py` —
   grep first).
2. Move `shields.py`→`loader/shields.py`, `registry.py` stays top-level
   (cli needs it pre-loader) or moves with a shim.
3. Rename `GpioRef`→`FunctionRef` and `Instance.pins`/`pin_refs`→
   `straps`/`strap_refs` (mechanical, tests included).
4. Update `doc/reference/api/*.rst` (the drift test will insist).

Acceptance: suite green, docs build green, `git log` one move per commit.

### Task E — small typed/model cleanups  [1 agent]

1. `Solved.channels` value → `NamedTuple ChannelResolution(fn, ctrl,
   channel, period, flags, position)`; update the three unpack sites.
2. `ExposedSocket.buses` → `Dict[str, Tuple[str, str]]` with the two
   marker kinds documented; `channel: Optional[int]`; drop the
   `assert isinstance`/`cast` at consumers.
3. `Jumper.state_of`/`positions` are fine; leave.
4. Verify the `require(content_v, "instances", "rig")` context string
   (finding 1.8) against goldens; fix the label only if no golden pins it.

### Task F — one Explanation page  [1 agent]

Distill `claude/architecture.md` into
`doc/explanation/architecture.rst`: the five stages, why diagnostics are
values, why the emitter cannot fail, why output is deterministic — written
for an outsider, no brief citations. Link it from `explanation/index.rst`.
Acceptance: docs build green; page reads standalone.

---

Execution note: A and B touch the same files (comments vs code), so run
A *after* B within each package, or accept rebase pain. Suggested order:
C → B (parallel per package) → A (parallel per package) → E → F → D.

---

## Addendum (2026-08-20): size policy, and D's final scope

Size limits adopted with the maintainer: **a Python module stays under
1,000–1,200 lines; a package stays under 15–20 modules.** Applies to
tests as well as source. One conscious exemption: `tests/integration/`
(23 one-file-per-feature suites) — grouping them would fight the
conftest/goldens layout for no gain.

Survey at adoption time (post A–C/E–G): every source module ≤875 lines
(`shields.py` the closest to the ceiling — its future split seam is
device-parsing vs exposed-socket parsing, already visible as helper
boundaries); top-level package at 16 modules, which Task D's moves
reduce to 11. The only file over the ceiling anywhere is
`tests/unit/test_shields.py` at 1,599 lines — hence:

### Task D5 — split test_shields.py  [1 agent, after D1–D4]

Split `scripts/rigc/tests/unit/test_shields.py` along the same seams
the source's parse helpers use: plugs, devices+addressing, exposed
sockets, pads/straps/jumpers. Pure moves of test functions plus the
shared fixtures they need; target every resulting module ≤600 lines;
suite passes unchanged (same test count).

### Task H — test-code comment sweep  [3 agents, after D5]

The Task A hygiene rules applied to `scripts/rigc/tests/` (measured
2026-08-20: 217 brief citations, 7 rigexp mentions, ~98 codeword lines
across 55 of 70 test files). Scopes: (H1) `tests/unit/*.py` top level;
(H2) `tests/unit/{loader,analyzer,emitter}/`; (H3) `tests/integration/`
plus `tests/compare.py` and the conftests. Additions specific to tests:
a docstring saying WHAT a test pins keeps that contract restated in
plain words (never a bare "rule 10"/"criterion 2.2" pointer); test
NAMES carrying meaningless codeword suffixes (`_r26`, `_rule_10_`) are
renamed descriptively — nothing selects tests by name; assertion
strings and golden files stay untouched (they carry the post-G wording
and gate it). Gate: full check.sh; test COUNT must not change except
where a rename is reported.
