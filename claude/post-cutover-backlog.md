# Post-cutover backlog — everything known-open after C4

Assembled 2026-07-30b at the end of the cutover run (C1–C2d landed, C3 in
flight, C4 next). Sources: `cutover-decisions.md` (D0–D10), the R5 and C2
review rounds, `NEXT-SESSION.md`'s standing queue, and the design log.

Long-parked DESIGN work is NOT here — that is `parked.md` (CAN scenario,
Kconfig layering, multi-board rigs, auto-routing, power/ground, lints, app
rig overlays, cmake re-idiomization for upstream, …). This file is
cutover-era debt and the near queue.

---

## A. Rulings — ALL THREE SIGNED OFF 2026-07-30b

All three are now CLOSED — two with no work to do, one implemented.

1. **CLOSED, IMPLEMENTED 2026-07-31 (`84e7e4e`) — stop the expander
   leaking a temp workdir per invocation** (D10; design SIGNED OFF
   2026-07-30b).

   `cli.py` calls `tempfile.mkdtemp(prefix="rigc-")` inside a `try:` with no
   `finally`, and there is no `rmtree` or `TemporaryDirectory` anywhere in
   the package, so every invocation leaves its workdir behind — cpp
   intermediates, shield translation units, the lot. Measured in one
   session: **7001 directories, 787 MB.** On this machine `/tmp` is tmpfs,
   i.e. RAM, and this competed with the OOM killer twice. It is not a test
   artefact: `dts.cmake` runs the expander once per configure, so every real
   build leaks one too.

   **Ratified design.** Remove the workdir when `main()` returns 0. KEEP it
   on any non-zero exit, because a cpp failure embeds the workdir path in
   the rendered diagnostic — that is precisely why the harness carries a
   workdir placeholder — so the directory is the evidence a user needs when
   something failed. Optionally gate the success-path deletion behind
   `RIGC_KEEP_WORKDIR` for debugging a run that succeeded.

   **Acceptance.** No golden may change: the workdir path reaches stderr
   before any cleanup, and the harness normalises it regardless. The frozen
   suite stays at its current count. Add unit coverage that the reject path
   KEEPS its directory and the accept path removes it — and give each a
   negative control, since "the suite is green" cannot distinguish working
   cleanup from no cleanup.

   **Watch for.** The deletion must not race the diagnostic render, and the
   `param-missing-header` golden is the one that embeds a workdir path, so
   it is the case to check first. Do not widen this into renaming anything:
   the `rigc-` prefix and `_WORKDIR_RE` were already aligned at C3.

2. **CLOSED — the `shield-uart-subset-frdm` tier-2 build** (D8/D9). The skip
   is signed off; this is not work. Original reasoning: Ratified, then
   declined by the driver on measurement: the file is 142 bytes of banner
   with no devicetree content, its overlay stays byte-compared (stronger
   than what any other rig gets), and C2c's census test enforces the
   invariant structurally. Either ratify the skip or run it as a clean
   standalone slice (`fixtures/zephyr/module.yml` with `board_root: .`,
   plus `-DEXTRA_ZEPHYR_MODULES`, following the bridle precedent).

3. **M8 — the recipe-error traceback family** (parked at R5). A bogus
   `--build-info` path and an insufficient recipe both escape as
   `RuntimeError` tracebacks where a `phys-board` diagnostic belongs.
   `edt_build.preprocess` raised identically in both implementations, so
   this was blueprint parity; with rigexp retired it is simply a defect.
   Fixing it changes stderr for uncovered inputs — cheap now that no
   differential constrains it.

4. **CLOSED — exit vocabulary stays 0/1/2/3** (D11). The decline is signed
   off and §8.3 is withdrawn, not deferred. Original reasoning:
   Ratified as a collapse, declined by C3 on a false premise: four LIVE
   `Unimplemented` sites remain in `loader/documents.py` (YAML parse
   failure, unreadable file, empty document, non-mapping document), and
   four unit tests reach exit 3 through real control flow. Collapsing means
   authoring a new `lang-parse` diagnostic and its wording — product
   design. rigexp's own wording is recoverable via `git show` for a
   hand-differential.

---

## B. Unblocked by C2 — the item with real leverage (DONE)

5. **CLOSED, LANDED 2026-08-03 (`c46fdc3`) — LAZY SHIELD LIBRARY.**
   Discovery stays eager (folder walk + `shield.yml`, preserving the
   known-shields census); the template parse defers to `resolve()`'s first
   reference, generalising the path revisioned shields already used.
   `nucleo_mux_farm` went from 14 shield TUs to 2. All three warts retired
   together. Brief: `lazy-shield-library-brief.md`.

   The second pin was removed by ruling, not by engineering: **Tobi,
   2026-08-03 — scan-time diagnostic ORDER need not be preserved, because
   rigexp is no longer a point of reference.** `stderr.txt` stays
   byte-exact; what changed is that its content may be re-derived when the
   tool's own execution order changes for a good reason. In the event no
   reject golden churned at all: the corpus's only scan-time template
   diagnostic (`shield-node-name-mismatch`) belongs to a rig that DOES
   reference the broken shield, so it still fires, from `resolve()`.

   **Correction to this file's own earlier claim**: "RIG_DEPENDS breadth is
   no longer a blocker — compared as a SET" was misleading.
   `compare_context_cmake` compares it as a set with EXACT membership, so
   breadth is order-free but not membership-free. The slice refroze 18
   `context.cmake` files, one `RIG_DEPENDS` line each.

---

## C. The standing feature queue, in order

6. **hwmv2 revision semantics** (`hwmv2-revision-semantics-brief.md`). The
   brief PREDATES the freeze and targets rigexp's `_parse_axis_decl`; it
   now lands in `rigc/loader/axes.py`, which R2 built as a deliberate seam
   (axis decl/resolve as swappable value functions). Re-read the brief
   against the current code before dispatching.

7. **`rig-schema.yaml`, metadata-only** (`rig-schema-brief.md`). Becomes
   what ENFORCES the metadata/content split, and
   `additionalProperties: false` closes the general unknown-key gap S1/S2
   deliberately left open in content files. After item 5, since both
   predecessors change the keys it describes.

   **This item GREW, and it is now the home of a standing debt** (Tobi,
   2026-08-08). Two grammars have since been retired by deleting their
   parsing while leaving a stray key SILENTLY IGNORED rather than an
   error: `board:`/`sockets:` (`7c724bd`) and, when it lands,
   `dt-includes:` (`param-vocabulary-brief.md`). Both were ruled that way
   deliberately, on the grounds that one-off unknown-key errors would be
   inconsistent machinery — the tightening belongs HERE, once, for every
   retired key at once. Scope it as **rig.yml AND shield.yml**, not rig.yml
   alone: `shield.yml` gains `shield,param-includes`'s sibling questions in
   the same period. The user-visible consequence until then: a rig.yml
   outside this repo still carrying `board:` builds whatever `-b` says,
   silently.

8. **Shield plurality** — pre-migration (`bridle-migration.md`).

9. **BRIDLE MIGRATION** — the goal the whole mission serves. Its
   prerequisite, the lazy shield library (item 5), is DONE: the eager scan
   bridle would have made untenable is gone.

10. **Board as an invocation coordinate** — **DONE 2026-08-08.** "The board
   is no longer part of the rig definition", now literally true: §9.5's six
   slices (S1–S6) made the board an independent coordinate and emptied the
   corpus of `board:`, and `7c724bd` retired the declaration grammar
   itself. `--boards-for` is the product-coordinate query it predicted, and
   it answers promoted shields too (`8887163`). Nothing in rig.yml names a
   board; the invocation is the only source.

---

## D. Test and coverage debt C2 created or exposed

11. **`rig-gen-includes.dtsi` ordering has zero real-data witnesses.**
    `lotus_buttons` is the only rig emitting it and declares one header, so
    both the producer and comparator ordering guards rest on synthetic
    fixtures alone. A second `dt-includes:` entry anywhere in the corpus
    would fix it.

12. **Four of eighteen overlays carry no targeted fact**, so
    `compare_overlay` returns None for any content whatsoever and
    `zephyr.dts` is their entire coverage: `nucleo_mux_farm`,
    `shield_rev_family`, `shield_rev_family_2`, `shield_rev_pilot`.

13. **`expectations.yml` is compared by nothing** — always emitted, no
    golden, no assertion. Pre-dates C2 and is documented, but it is the one
    artifact with no check at all.

14. **`CHECK_FAST=1` checks no emitted golden at all**, and overlay
    semantics are now build-marked only. The fast gate is therefore unit
    tests plus reject goldens; that is defensible but should be a stated
    property rather than a surprise.

15. **Ratchet the coverage floor.** `fail_under = 88` against a measured
    89%. Lowest: `emitter/sheet.py` 71%, `loader/library.py` 71%,
    `emitter/overlay.py` 77%.

16. **The integration suite has a cross-file collection-order coupling.**
    `test_board_read.py` fails when run in isolation
    (`ModuleNotFoundError: devicetree`) because it relies on
    `test_connector_bindings.py` calling `ensure_devicetree_on_path()` at
    module scope during collection. Pre-dates the cutover and only bites a
    single-module invocation, but it means the suite is not
    module-independent.

17. **Nothing ties the two emissions together any more.** Byte-freezing the
    overlay used to pin the standalone `--board-dts` run and the cmake
    build to the same output. A divergence between those board-reading
    paths is now visible only through `context.cmake` and config-sheet
    facts.

---

## E. Small warts, individually cheap (ALL RESOLVED)

18. **CLOSED, LANDED 2026-08-04 (`d3eed8a`).** `boarddt.py`'s
    unknown-board message rendered `os.path.relpath` against the CWD. Now
    `anchor_path`, the ratified renderer the same function already used
    for `board_dts`. Its unit test renders the message from two working
    directories and asserts them equal — mutation-verified as a real
    control. Refroze `unknown-board/stderr.txt`, one line.

19. **CLOSED, LANDED 2026-08-04 (`d3eed8a`).** A rig's own `dt-includes:`
    headers now reach `RIG_DEPENDS`, recovered from cpp's own linemarkers
    (`dtsio.linemarker_files`) rather than by reimplementing its include
    search. Forced a change to `run_cpp`: gcc writes NOTHING to `-o` on a
    failing run (verified) while still emitting linemarkers for every file
    it opened, so `run_cpp` now captures stdout and writes `out_path`
    itself, as BYTES — byte-identical to `-o`, and no longer
    locale-dependent. Refroze `lotus_buttons/context.cmake`, one entry.

20. **CLOSED, LANDED 2026-08-04 (`8dd24ec`), together with item 27.** The
    57 `generated by rigexp` banners are rewritten; no occurrence of the
    retired tool's name remains anywhere under `tests/goldens/`. Done as a
    pure refreeze with no code in the tree, so the diff is only bytes no
    comparator reads.

    **This also removed a trap**: `RIGC_REFREEZE=1` rewrites whole files,
    so ANY refreeze silently performed this rewrite as a side effect — the
    lazy-shield-library and small-warts slices each had to revert 40–58
    unrelated files to keep their own diffs reviewable. Future refreezes
    are clean. The general discipline stands regardless: **classify every
    refreeze diff before committing it.**

21. **CLOSED, LANDED 2026-08-04 (`d3eed8a`).** `loader.load()`'s
    `types` tightened to `Optional[Dict[str, ConnectorType]]`.

22. **NOT A TASK — an observation, kept so it is not rediscovered.**
    `config-sheet.md` section PARTITION is still effectively frozen: kind
    is inferred from body shape and a repeated kind is a parse error, so
    splitting one section into two fails loudly. Safe, but a rendering
    change the comparator does not free.

23. **NOT A TASK — an observation, kept so it is not rediscovered.**
    Root-node properties would be invisible to both halves of the overlay
    split (`dts_equiv` excludes `/`). No hole today — the emitter only adds
    children of `/`.

24. **CLOSED, LANDED 2026-08-04 (`d3eed8a`) — and its premise was wrong.**
    The site was NOT uncovered: `test_axes.py::test_empty_list_is_rejected`
    already reached it. What was uncovered was its WORDING, because that
    test asserted only the diagnostic code — and reject-corpus wording is
    the ratified product surface those goldens exist for. Added the
    `empty-revisions-list` reject fixture and its goldens; the unit test
    now asserts the message text too. **Lesson worth keeping: "uncovered"
    in this file has meant two different things** (no code path reaches it
    vs. nothing freezes its wording); say which.

---

## F. Upstream and infrastructure

25. **Five carried zephyr commits are not upstream** (shield `revisions:`
    schema, the `template:` boolean, two edtlib patches, the cmake
    `cmake-modules` key). `west.yml` therefore stays PINNED to a hash;
    tracking the branch again is deferred until they land upstream, because
    that branch already rebased once and silently invalidated a differential
    run. Upstreaming them is the real fix.

26. `refactor-tests-plan.md` **Part D** — fixture shield renames. Recorded
    as needing to stay separate from other work.

27. **CLOSED, LANDED 2026-08-04 (`8dd24ec`), together with item 20.** Two
    `zephyr.dts` goldens carried stale source-line annotations (e.g.
    `samd2x.dtsi:37` where the pinned tree says `:38`) — NOT zephyr drift,
    the checkout is exactly at the pin `8da5b3a0f60`. Frozen against an
    older tree and invisible ever since because `dts_equiv` ignores
    comments, which is also why they could not be trusted as provenance.
    Proven comment-only three ways: the gate was green immediately before
    the refreeze, a census put every changed line in exactly two classes,
    and both files are byte-identical once trailing comments are
    stripped.

---

## G. Process discipline worth keeping (not tasks)

- **Every comparator guard needs a named negative control, mutation-tested.**
  The integration suite cannot falsify a comparator: emitter output equals
  the goldens, so a gutted comparator passes everything. Ten injected
  mutations proved it.
- **A census-style test is falsified by mutating the world it observes**,
  never by editing its own assertion.
- **A negative control needs an input that distinguishes the WRONG
  implementations from each other**, not merely from nothing. Two-element
  examples made a control vacuous twice (escape order, header order).
- Never `cmd | tail; echo $?` — that reports tail's status and hid a
  failing gate for a full cycle.
- Purge `__pycache__` after any mutate-and-restore: a same-size,
  same-second restore leaves bytecode Python considers valid.
