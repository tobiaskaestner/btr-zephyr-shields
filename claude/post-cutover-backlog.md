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

8. **Shield plurality** — **DONE 2026-08-10** (`605d258`,
   `shield-plurality-brief.md`). A shield.yml may declare N shields in one
   folder; the folder stops naming the shield wherever one exists.
   Discovery gained a second discriminator rather than a replacement
   (`template: true` where there is a shield.yml, the `<basename>.shield`
   marker where there is not), so the yml-less fixtures were untouched.
   One item moved to 7 rather than being closed here: `shield:` and
   `shields:` are mutually exclusive only by the zephyr-side jsonschema
   during a cmake build, never by rigc's own parse.

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

28. **PIN PROMOTION — the config-element grammar**
   (`pin-promotion-brief.md`). BRIEFED and RULED 2026-08-12, **parked
   here deliberately rather than dispatched** (Tobi, same day): it goes
   behind the standing queue above, not ahead of it.

   *(Numbered 28 because these numbers are stable identifiers that
   briefs and handoffs cite by value — "backlog item 7", "item 9". A
   new item appends; it never renumbers. Its PLACE in section C is what
   says where it sits in the queue.)*

   **The gap.** Promotion can assign a socket, a slot and a device
   property; it cannot assign a **config element** — a strap or a
   routing jumper. So a shield whose jumper selection is mandatory
   passes `check_promotable`, desugars cleanly, and then always fails
   analysis with no command line that works. `adafruit_winc1500` is the
   only such shield in the corpus and is the sole member of
   `test_singleton_identity_law.py`'s `EXPECTED_REJECTING` for exactly
   this reason. Four plausible spellings were probed at HEAD `7b6d583`
   and each fails on its own sentence — the grammar is absent, not
   merely undocumented.

   **Ruled (Tobi, 2026-08-12), all four as recommended:** the spelling
   is `pin.<element>=<value>`, reserving the device-half `pin` exactly
   as `socket` is reserved for slots — a REFINEMENT of the existing
   `<device>.<prop>` partition, so `_PROMOTION_OPTS` stays the closed
   one-tuple; ONE namespace for straps and jumpers, leaving
   `apply_pin_block`'s dispatch the sole authority; NO element-name
   validation in `parse_promotion_opts` (`lang-pin` already names the
   offender and lists the elements); normalization stays the loader's.

   The rule those make explicit, worth carrying forward because it
   predicts the shape of any future route: **the reserved device-half
   names the instance-level KEY the assignment routes to** — `socket` →
   `socket:`/`sockets:`, `pin` → `pin:`, everything else → `params:`.

   **TWO sub-rulings inside the slice are still OPEN** and belong to
   whoever picks it up, before dispatch rather than during: whether the
   strap-value type check is in scope (§5), and whether the identity
   law's reject branch is kept or deleted once `EXPECTED_REJECTING`
   empties (§7).

   **A REAL PRE-EXISTING CRASH found while briefing, and it is not
   gated on this slice** (§5 of the brief): a strap value YAML does not
   parse as an int reaches `f"{want:#04x}"` at
   `analyzer/addresses.py:233` and raises an unhandled `ValueError`.
   `Instance.pins` is typed `Dict[str, int]` and nothing enforces it.
   Driver-reproduced from an AUTHORED rig, so it is reachable today —
   this grammar would only make it a one-keystroke typo instead of a
   hand-edited YAML mistake. If the slice stays parked a long time,
   this is separable and cheap.

   **The residual, named so it is not rediscovered:** `invert:` is the
   LAST instance-level key with no CLI route, and it has a real user
   (`lotus_buttons`). Under the same rule it would be a fixed key, not
   a dotted one. Its own slice, not folded in here.

   **SEQUENCING — read item 29 first.** If the `pin:` → `config:`
   rename is wanted, it must land BEFORE this slice: this grammar bakes
   `pin.` into a user-facing CLI surface and into the reserved-half
   rule. Afterwards it is two migrations instead of one.

29. **CLOSED, LANDED 2026-08-14 (`33e5e49`).** `pin:` is `config:`, and
   the DTS label is the naming authority for `config:`, `wires:` and
   `params:` alike. The `_`→`-` normalization is gone; an unlabeled
   device, pad, strap or jumper is a loud `lang-shield-label` error.
   Every golden byte-unchanged, checked. **Item 30 carries what this
   slice did NOT reach.** The doc page (the brief's §8) is still owed.

   **THE rig→shield REFERENCE VOCABULARY — consistency, explainability,
   grep-ability.** Raised by Tobi 2026-08-12 while clarifying the
   ontology behind item 28. Not a defect anyone has hit: every
   diagnostic involved already lists the valid names. It is a
   **learnability and navigability** item, and it has three distinct
   parts that want ruling together.

   **(a) One concept, three names.** `ontology.md` calls it a
   **configuration element**; the shield DTS declares it under
   `config { }`; the rig assigns it under `pin:`. The rig-side name is
   the odd one and it is actively misleading for half the cases —
   `pin: { addr_strap: 0x49 }` assigns an **I²C address**, not a pin.
   (`pin:` is right only for the jumper kind, where a position IS a
   pin.) `config:` is the name the rest of the model already uses.

   **(b) Naming authority differs per assignment block, and NOTHING
   says so.** Conv. 5 (`conventions.md`) establishes that every
   rig→below reference is "a string resolved by the loader" — but
   never says WHICH string, and the two blocks answer differently:

   | rig block | resolves against | example |
   |---|---|---|
   | `params:` | the device's DTS **LABEL** | `gb_key: button { … }` → `params: { gb_key: … }` |
   | `pin:` | the config element's **NODE NAME** | `w_irq_jmp: irq-jmp { … }` → `pin: { irq_jmp: … }` |

   Driver-probed, not inferred — the label is **rejected** on the
   `pin:` side:

   ```
   $ pin: { w_irq_jmp: D2 }
   error[lang-pin]: pin names no config element 'w_irq_jmp' of shield 'adafruit_winc1500'
       config elements of 'adafruit_winc1500': irq-jmp
   ```

   `irq_jmp` resolves only because `loader/params.py:227` tries
   `cfg_name.replace("_","-")` before the raw name.

   **(c) The config-element side is NOT greppable, and the device side
   IS** — which is why the asymmetry has gone unnoticed. Given
   `params: { gb_key: … }` the literal `gb_key` appears verbatim in the
   shield. Given `pin: { irq_jmp: … }` **no literal is shared with the
   shield at all**: the shield carries the label `w_irq_jmp` and the
   node name `irq-jmp`, neither of which is the rig's string.

   Grepping the underscore form *appears* to work — `w_irq_jmp`
   contains `irq_jmp`, `tc_addr_strap` contains `addr_strap` — but that
   is a **coincidence of both corpus config elements happening to be
   labelled `<prefix>_<underscored node name>`, not a contract**. A
   shield author who labels a config node anything else breaks the
   lookup in both directions: rig → shield, and "which rigs assign this
   element".

   **Explainability, measured:** `grep -rln 'pin:' doc/` → **no
   match**. The Sphinx user tree documents `pin:` nowhere. It is
   covered only in `conventions.md` (the position-selection section,
   and Conv. 5's naming rule), which is a design document, not user
   documentation.

   **RULED 2026-08-13, and BRIEFED — `reference-vocabulary-brief.md`.**
   `pin:` becomes `config:`; the **LABEL** is the naming authority for
   every rig→shield string reference; `doc/` gains a reference page
   covering every `shield,*` property. **This item now sequences BEFORE
   item 28** by Tobi's instruction.

   **Node-name-wins was ruled AGAINST on a census gathered to check
   it** (31 shields, all 21 shield roots): device node names are 18
   distinct over 30 uses — `sensor` alone is spelled the same in EIGHT
   shields — against 29-of-30 for labels, whose one collision is a
   deliberate fixture variant pair. Both are unambiguous within a
   shield, so node-name-wins was implementable; it was rejected because
   it costs ~4× the migration (12 rig files + 2 goldens + the promotion
   grammar, vs 3 rig files + 2 config elements) and moves AGAINST the
   grep-ability that motivated the item. The deciding argument was
   consistency: the shield's own internal reference is already a label
   (`shield,addr-from = <&tc_addr_strap>`), so label-wins makes the rig
   string and the phandle the SAME identifier.

   The options below are kept as the record of what was weighed:
   - Rename `pin:` → `config:`, aligning the rig with the model. A
     grammar retirement: 3 corpus rigs, item 28's `pin.<element>=`
     promotion grammar becomes `config.<element>=`, plus goldens.
     **If ruled this way it belongs with item 7**, which is already the
     home for every retired-key/unknown-key debt, rather than standing
     alone.
   - Fix the naming authority: pick LABEL or NODE NAME for both blocks
     and state it as a numbered convention. Label-everywhere is the
     cheaper migration (devices already use it) but config nodes would
     then need labels to be mandatory.
   - Keep both spellings and make the rule explicit: document the
     normalization in Conv. 5 and give `doc/` a page.

   **Sequencing: SETTLED — this goes FIRST**, ahead of item 28, whose
   grammar becomes `config.<label>=<value>` and whose brief is updated
   in the same commit as the rename.

   **Two things the briefing turned up that are decisions, not
   details** (both in the brief, §4 and §6): the `label=node.labels[0]
   if node.labels else node.name` fallback in `shields.py` must become
   a LOUD error, or an unlabeled config node silently reintroduces the
   two-spellings problem; and `wires:` is a THIRD rig→shield reference
   surface resolving by node name (`Shield.by_name`, 2 fixture users,
   zero corpus) — recommended in scope, flagged for veto.

30. **CLOSED, LANDED 2026-08-14.** The fourth reference surface —
   `socket: <carrier>.<exposed>` — resolves by DTS LABEL, completing
   item 29's ruling across all four surfaces
   (`exposed-socket-vocabulary-brief.md`). `Shield.exposed_socket()`
   mirrors `config_element`'s shape; `_parse_exposed` now goes through
   `_require_label`, which is the last of its four call sites, so no
   `labels[0] if … else node.name` lookup fallback survives in
   `shields.py`. Internal keying stays node-name (§5's rule): paths and
   nexus labels are still built from `exposed.name`.

   **This entry's own cost estimate was wrong, and the reason is worth
   keeping.** It predicted "labelling 8 nodes, migrating 15 references,
   and moving goldens". Only the first happened. All 8 node names
   (`mb1`, `mb2`, `ch0..ch3`, `combined` ×2) were ALREADY syntactically
   valid DTS labels, so labelling each node with its own current name
   made every one of the 15 references resolve by label unchanged —
   **zero references migrated, and every emitted golden byte-unchanged**
   despite the ref string reaching `BoardSocket.label`, the
   multi-parent `path`, `scope_path` and the config sheet. The
   two-spellings ambiguity closed anyway: the label is now the only
   accepted spelling; it merely happens to equal the old node name for
   today's corpus. Read a cost estimate here as a hypothesis.

   The one intended golden change was the carried debt:
   `remove-wire-missing_b.yml`'s `remove-wires:` endpoints moved from
   `x.sq → y.led-2` to `x.dl_sq → y.dl_led2`, hand-edited (`RIGC_REFREEZE=1`
   is blocked) and verified failing before / passing after.

31. **Grove SPI and UART connectors — deferred, deliberately** (Tobi,
   2026-08-14, during the grove base-carrier slice). The carriers ship
   I²C, digital I/O and ADC connectors only. What was left out, and
   why it is not just "more of the same":

   - **`grove_spi`** (`seeed_grove_base_v1`, `seeed_grove_rpipico_v1`) —
     a Grove SPI connector is a different pin contract from a digital
     one. Whether it is a `socket,grove` carrying an SPI bus proxy, or
     its own connector type, is unruled.
   - **UART** (`grove_d0_uart`, `grove_d1_uart0`, `grove_d5_uart1`,
     `grove_d7_uart`) — same question, plus **this project has no UART
     bus proxy at all**: `plug,bus-proxies` on the grove binding lists
     `i2c` only. UART support is the prerequisite, not the carrier.
   - **The dual-role connectors are the interesting sub-case.**
     rpipico's `grove_d7_i2c1`/`grove_d9_i2c0` and xiao's `grove_d5_i2c`
     are digital connectors that ALSO carry I²C, each on a *different*
     controller. That is `socket,i2c` per exposed socket rather than per
     carrier — worth confirming the model already allows it before
     assuming this is free.

32. **Two host connector types are missing, and they block two Grove
   carrier variants.** `dts/bindings/connectors/` holds exactly four
   types: `arduino-r3`, `grove`, `i2c-port`, `mikrobus`.
   `seeed_grove_rpipico_v1` plugs `&rpipico_header` and
   `seeed_grove_xiao_v1` plugs `&xiao_d`; neither type exists, so
   neither variant is authorable. **Ruled v1+v2 only** (Tobi,
   2026-08-14) for that reason — they are blocked on the host types,
   not on anything about carriers.

   Each is a Convention 1 job of its own: a binding plus a
   `dt-bindings/connector/<name>.h` position header, the single source
   of truth for position indices. The carrier folder is authored to
   hold all four, so both variants drop in with no carrier-side work
   once the types exist.

33. **ADC/PWM cannot pass through a carrier's exposed socket — a MODEL
   gap, not a binding gap** (found during the grove base-carrier slice,
   grove-carriers-brief.md Sec 6, ruling 3). `seeed_grove_base_v1`/`_v2`
   author `grove_a0..a4`/`a0..a3` anyway, each with both a working
   digital `gpio-map` (a real bridle fact — A0-A4 double as plain GPIO)
   and an attempted `io-channel-map` targeting the carrier's own plug,
   authored the way a real ADC pass-through would need to be declared.

   **The attempted `io-channel-map` is a confirmed no-op, independent of
   any binding fix.** `scripts/rigc/shields.py`'s `_parse_exposed`
   (the sole parser of an exposed socket node) reads exactly four
   things off it — `gpio-map`, `socket,<bus>`, `socket,cs-pool`,
   `shield,channel` — never `io-channel-map`/`pwm-map`; verified
   empirically (`ExposedSocket.buses`/`.gpio_map` for `grove_a0` come
   back populated, no `adc_map` field exists on the dataclass at all to
   have caught it). So the property is silently dropped before it ever
   reaches composition.

   **The wall, reached end to end**: a `grove_light`-shaped shield
   plugged onto `seeed_grove_base_v2`'s exposed `grove_a0` fails with

       error[phys-function]: 'light_a/light: io-channels' uses position
       SIG0 as ADC, but socket 'grove_1.grove_a0' offers no adc on it
       (no socket,adc-map entry)

   from `analyzer/gpio.py`'s `_collect_channel` (`fmap = socket.adc_map;
   resolved = fmap.get(pos)` → `None`), because `analyzer/sockets.py`'s
   `compose_socket` — the ONLY function that ever builds a carrier's
   synthesized `BoardSocket` — has no branch for `pwm_map`/`adc_map` at
   all, only `gpio_map` and `buses` (i2c/spi/uart). `BoardSocket.pwm_map`/
   `.adc_map` DO exist as fields (`model.py`) and DO get populated for a
   real board socket — `board_edt.py:180` is the only other, and only
   real, site that ever sets them, reading a board's own `pwm-map`/
   `io-channel-map` via `edtlib.Node.maps()`. The SAME shield plugged
   directly onto a real board socket that carries one (`seeeduino_lotus`'s
   own `grove_a0`, checked by an ad-hoc build) resolves cleanly to
   `io-channels = <&grove_a0 0>;` plus `&adc { status = "okay"; };` —
   proving the gap is specific to the carrier-composition path, not a
   general regression.

   **Answering the brief's three-way question, by this evidence: it is
   #2, a model gap, and bigger than a binding fix.** `arduino-r3.yaml`
   lacking `io-channel-map`/`pwm-map` and neither `frdm_k64f` nor
   `nucleo_f401re` carrying an ADC nexus on their own `arduino-r3`
   sockets (§6's own finding) are BOTH true and BOTH necessary — but
   insufficient on their own: even granting both, `_parse_exposed` would
   still drop a carrier's declared `io-channel-map`, `ExposedSocket`
   still has nowhere to hold it, and `compose_socket` still has no code
   path to forward it into the synthesized socket's `adc_map`/`pwm_map`.
   Closing this needs THREE changes together, all in `scripts/rigc/`,
   before a binding/board-DT fix on the arduino-r3 side would even have
   anything to attach to:
     1. `ExposedSocket` gains `pwm_map`/`adc_map`-shaped fields, and
        `_parse_exposed` learns to read `pwm-map`/`io-channel-map` off an
        exposed node exactly as it already reads `gpio-map`.
     2. `compose_socket` gains a pass-through branch for each, mirroring
        the existing `gpio_map` nexus-row branch — nontrivial: PWM/ADC
        pass-through is BY POSITION only (unlike the i2c/spi/uart
        by-kind bus lookup), so it is a closer cousin of the gpio-map
        branch than of the bus branch.
     3. THEN, and only then, `arduino-r3.yaml` gaining `io-channel-map`/
        `pwm-map` plus a real ADC/PWM nexus on `frdm_k64f`'s and
        `nucleo_f401re`'s own arduino-r3 sockets becomes the thing that
        actually lets `grove_light`/`grove_pwm_led`/`grove_servo`
        resolve through a carrier on either twister board — the payoff
        §5 describes but does not yet reach.

   The multi-bus slice's CS-pool regression (a pass-through branch
   leaking state into a composed socket of a different type) is the
   standing warning for step 2: authoring it carelessly is exactly the
   kind of non-obvious-state mistake that class of bug already happened
   once.

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
