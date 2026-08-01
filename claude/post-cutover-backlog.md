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

## B. Unblocked by C2 — the item with real leverage

5. **LAZY SHIELD LIBRARY.** The scan eagerly cpp-parses EVERY discoverable
   shield template (13 TUs for a rig referencing 2). It does not scale —
   bridle is 19+ folders — and it is the root of both recorded warts: one
   malformed shield poisons the whole scan, and deps record
   scanned-but-unreferenced shields. Fix: keep discovery eager (folder walk
   + `shield.yml`, cheap, preserves the known-shields census), defer the TU
   parse to first reference, extending the path revisioned shields already
   use.

   **C2 removed ONE of its two pins, not both.** RIG_DEPENDS breadth is no
   longer a blocker — `context.cmake` compares that list as a SET now, so
   the eager set is not frozen. But **scan-time diagnostic ORDER still is**:
   broken shields report before rig-side diagnostics today, and
   `stderr.txt` stays byte-exact permanently by owner ruling. So the slice
   must either preserve diagnostic order or come with an explicit ruling to
   refreeze the affected reject goldens.

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

8. **Shield plurality** — pre-migration (`bridle-migration.md`).

9. **BRIDLE MIGRATION** — the goal the whole mission serves. Do the lazy
   shield library (item 4) first: bridle is what makes the eager scan
   untenable.

10. **Board as an invocation coordinate** — "the board is no longer part of
   the rig definition." `board-as-invocation-coordinate.md`, design-log
   2026-07-29a: rig × board becomes a product coordinate (`--boards-for`)
   rather than a property the rig file carries. Explicitly post-cutover.
   Note S2 already moved `board:` under each variant entry, so this
   finishes a direction already started.

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

## E. Small warts, individually cheap

18. `boarddt.py`'s unknown-board message still uses `os.path.relpath`
    against the CWD, so it renders differently depending on where the tool
    was invoked. Deliberately left outside C1's ratified refreeze class;
    fixing it churns the `unknown-board` golden.

19. The rig's own `dt-includes:` headers are absent from `RIG_DEPENDS`
    (blueprint wart, reproduced deliberately). Editing such a header does
    not retrigger configure.

20. **57 goldens still spell `generated by rigexp`** in a banner comment no
    comparator reads. Cosmetic; a one-shot rewrite is now free of
    consequence, and doing it removes a retired tool's name from the tree.

21. `loader.load()`'s `types: Optional[dict]` was never tightened to
    `Dict[str, ConnectorType]` (noted at R5, pre-existing).

22. `config-sheet.md` section PARTITION is still effectively frozen: kind
    is inferred from body shape and a repeated kind is a parse error, so
    splitting one section into two fails loudly. Safe, but a rendering
    change the comparator does not free.

23. Root-node properties would be invisible to both halves of the overlay
    split (`dts_equiv` excludes `/`). No hole today — the emitter only adds
    children of `/`.

24. The `"'list' must be a non-empty list"` `lang-schema` site is still
    uncovered by any fixture. Older than S2; found while closing its test
    gap.

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
