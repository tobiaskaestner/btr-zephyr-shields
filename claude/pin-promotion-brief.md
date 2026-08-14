# Config-element promotion — `--promote 'shield:config.<label>=<value>'`

**Status:** briefed 2026-08-12. **§2's four rulings are SIGNED OFF
(Tobi, 2026-08-12), all four as recommended.** NOT dispatched — parked
in the backlog (`post-cutover-backlog.md` item 28) behind the standing
queue, by Tobi's own instruction.

**TWO sub-rulings inside the slice remain OPEN** and must be settled
before dispatch, not during it — neither is among the four:

- **§5** — whether the strap-value type check (a real, reproduced
  crash) is in this slice or its own.
- **§7** — whether the identity law's now-unexercised reject branch is
  kept with a comment or deleted.

**ONE ORDERING DEPENDENCY OUTSIDE THE SLICE — backlog item 29 — HAS
LANDED.** It was the rig→shield reference vocabulary question (`pin:`
vs the model's own `config { }`, the label-vs-node-name split between
`params:` and `pin:`, and the fact that a config-element reference was
not greppable from either side), and it was ruled and dispatched
BEFORE this slice, exactly as this brief asked: the rig-side key is
now `config:`, and every rig→shield string reference — `params:`
already, `config:` now, and `wires:` — resolves by DTS **label**, never
by node name. This brief's grammar and worked examples below are
written against that landed vocabulary: `config.<label>=<value>`, not
the withdrawn `pin.<element>=<value>`.

The fourth and last route into a promoted instance. Promotion can
today assign a socket (`socket=`), a slot (`socket.<slot>=`) and a
device property (`<device>.<prop>=`); it cannot assign a **config
element** — a strap or a routing jumper — so a shield whose jumper
selection is mandatory is discoverable, passes `check_promotable`,
desugars cleanly, and then always fails analysis. There is no command
line that works.

## 1. The gap, measured — every count re-derived, command cited

```
$ grep -rln 'position-domain\|shield,domain' boards/shields scripts/rigc/tests/fixtures
boards/shields/adafruit_winc1500/adafruit_winc1500.shield     # jumper  irq-jmp   (position-domain)
boards/shields/temp_click/temp_click.shield                   # strap   addr-strap (shield,domain)

$ grep -rn '^\s*config:' boards/rigs scripts/rigc/tests/fixtures
boards/rigs/nucleo_wifi_logger/nucleo_wifi_logger.yml:21      # jumper, D7 — the reject rig
boards/rigs/nucleo_wifi_logger_ok/nucleo_wifi_logger_ok.yml:17 # jumper, D2 — the realizable one
boards/rigs/quail_temp_farm/quail_temp_farm.yml:18            # strap,  0x49
```

**Two config elements in the entire tree, three `config:` users, and
ZERO of either in the fixtures.** That is the slice's dominant fact:
the test surface is greenfield, and every test must reach for a REAL
corpus shield. The law fixture board already hosts both
(`nexus_arduino_r3` for the winc, `nexus_mikrobus` for temp_click) —
driver-verified by running them, not inferred.

**Exactly one shield is blocked**, and only the jumper kind blocks:

- `temp_click`'s strap **free-allocates** when unassigned, so it
  promotes today (it is one of the 13 twister suites).
- `adafruit_winc1500`'s jumper **must be selected** — non-CS positions
  are never auto-allocated. Driver-run at HEAD `7b6d583`:

  ```
  $ python -m rigc expand --promote adafruit_winc1500 ... --board singleton_law_board
  error[phys-position]: 'adafruit_winc1500/wifi: irq-gpios' routes through jumper
    'irq-jmp' whose position must be selected — add config: { w_irq_jmp: <position> }
    to the instance (domain: D7, D2)
  EXIT=1
  ```

  It is the sole member of `test_singleton_identity_law.py`'s
  `EXPECTED_REJECTING` for exactly this reason, and that module's own
  comment already names the cause: "needs a routing-jumper selection
  (`config:`) that neither side supplies".

All four spellings a user would reach for were probed and each fails
on its own sentence — the grammar is genuinely absent, not merely
undocumented (probed pre-item-29, against the then-current `pin:`
vocabulary; re-probe against `config:`/labels before dispatch):

| probed target | result |
|---|---|
| `adafruit_winc1500:pin.irq_jmp=D2` | `error[lang-param]`: params names no device `pin` |
| `adafruit_winc1500:irq_jmp.position=D2` | `error[lang-param]`: no device `irq_jmp` |
| `adafruit_winc1500:irq-jmp.pin=D2` | `error[lang-param]`: no device `irq-jmp` |
| `adafruit_winc1500:pin=irq_jmp` | `error[lang-promote-opts]`: unknown option `pin` |

## 2. THE RULINGS (Tobi, 2026-08-12) — all four as recommended

1. **Spelling: `config.<label>=<value>`**, reserving the device-half
   `config` exactly as `socket` is already reserved for slots. This is
   the SECOND refinement of one existing mechanism (the `<device>.
   <prop>` partition), not a new fixed keyword — `_PROMOTION_OPTS`
   stays the closed one-tuple `("socket",)`.

   The unifying rule this makes explicit, and it predicts the shape of
   any future route: **the reserved device-half names the instance-
   level KEY the assignment routes to.** `socket` → `socket:`/
   `sockets:`, `config` → `config:`, everything else → `params:`.

   Consequence, loud rather than latent, and **verified rather than
   assumed**: a shield device or config element labeled literally
   `config` could no longer receive a promotion parameter. `grep -rn
   --include='*.shield' -E '^\s+(config|socket):\s' boards/shields
   scripts/rigc/tests/fixtures` → **no match**; no label containing
   `config` exists anywhere. Same verification the `socket` reservation
   got on 2026-08-12.

   Rejected alternative: a bare `<label>=<value>` shorthand. It
   collides with the closed keyword set and revives the bare-word
   question decision 3 (2026-08-08) already settled — explicit
   `key=value`, no positional shorthand.

2. **ONE namespace for straps and jumpers, not two.** `config.<label>`
   covers both kinds, and `loader/params.py:apply_config_block` keeps
   sole authority for the strap-vs-jumper dispatch (it resolves the
   config element off the Shield BY LABEL and branches on
   `isinstance(elem, Strap)`). A CLI that pre-classified would be a
   second authority for a fact the loader already owns — the same
   reasoning that keeps `promote_shield` from validating device or
   property existence. The rig's own `config:` block is likewise one
   block for both kinds; this mirrors it exactly.

3. **`parse_promotion_opts` does NOT validate element names**, even
   though it now receives the resolved `Shield`. The precedent looks
   contrary — the slot form checks `slot_name not in shield.plugs` —
   but that check rode along on a decision the parser genuinely has to
   make (plural vs single-plug picks WHICH SPELLING is legal). Nothing
   about the shield changes the config spelling, so there is no fork to
   resolve, and `apply_config_block`'s own `lang-config` already names
   the offender and lists the shield's config elements by LABEL:

   ```
   error[lang-config]: instance 'adafruit_winc1500': config names no config
     element 'w_irq_jmpx' of shield 'adafruit_winc1500'
     config elements of 'adafruit_winc1500': w_irq_jmp
   ```

   Counter-argument, recorded because it is real and was weighed
   rather than missed: a CLI-anchored refusal fires earlier and at the
   cmake seam (`list_rigs.py` parses for exactly that early exit).
   **Ruled against** — it duplicates a diagnostic rather than adding
   one. If a user ever reports the late refusal as confusing, the ~6
   lines are recoverable; do not add them speculatively.

4. **Name/value normalization is the loader's, unchanged — and there
   is none.** `apply_config_block` resolves `cfg_name` against
   `shield.config_element()` by LABEL and by label alone; the `_`→`-`
   normalization item 29 found and removed does not come back here.
   `config.w_irq_jmp=` is the only spelling that resolves — the label
   itself, verbatim. `promote_shield` prints the key verbatim and the
   loader resolves it, exactly as it already does for an authored
   `config:` block. No normalization anywhere, CLI or loader.

## 3. The grammar

```
<element>    := <shield>[@rev][:<assignment>...]
<assignment> := socket=<label>              # fixed key, single-plug only
              | socket.<slot>=<label>       # per-slot, plural only
              | config.<label>=<value>      # NEW — strap or jumper, by LABEL
              | <device>.<prop>=<value>     # params
```

- Composes with everything already there, with no new separator and
  therefore **no new cmake escaping level**: `;` between list
  elements, `:` between options, `.` inside keys. `_cmake_list_escape`
  and its five-level `;` analysis are untouched — a `config.` value
  never contains a `;`.
- `ParsedPromotionOpts` gains ONE field, `configs: Dict[str, str]`
  (config-element LABEL → raw value text), flat and unsplit per ruling
  2. Duplicate `config.<label>=` within one element is refused
  unconditionally, like every other duplicate — a property of the
  target string alone, needing no shield.
- Empty value refused (`config.w_irq_jmp=`), matching the three
  existing routes.
- **Print order is a contract, not a detail:** `config:` renders AFTER
  `socket:`/`sockets:` and BEFORE `params:`, matching both authored
  corpus rigs (`nucleo_wifi_logger_ok`, `quail_temp_farm`) and pinned
  by `test_explain.py`'s whole-stdout style.

Worked example — the shield that motivates the whole slice:

```
west build-rig -b nucleo_f401re --rig 'adafruit_winc1500:config.w_irq_jmp=D2'
```

## 4. Semantics below the desugaring — unchanged, and that is the premise

The loader, analyzer and emitter need ZERO changes. `Instance.pins`/
`.jumpers` already exist and already carry exactly this; the value
travels as YAML text through the identical `rigc.loader.load` path
every promoted document already takes, so YAML retyping (`0x49` →
int) is the same mechanism `quail_temp_farm` already relies on.
**If something below the desugaring seam seems to need a change, the
premise is wrong — stop and report.**

Both downstream refusals are already graceful and were driver-probed:

```
config: { tc_addr_strap: 0x55 }  ->  error[phys-pin]:     pinned address 0x55 is not in the
                                       domain of strap 'addr-strap' ({0x48, 0x49})
config: { w_irq_jmp: D9 }        ->  error[phys-position]: jumper 'irq-jmp' selection 'D9' is
                                       not in its position domain (D7, D2)
```

## 5. A REAL PRE-EXISTING CRASH this grammar makes reachable by typo

A strap value that YAML does not parse as an int reaches an unguarded
format code. Driver-reproduced from an authored rig at HEAD:

```
config: { tc_addr_strap: hello }
  File "scripts/rigc/analyzer/addresses.py", line 233, in _allocate_scope
    f"instance '{inst.name}': pinned address {want:#04x} is not in the "
ValueError: Unknown format code 'x' for object of type 'str'
```

`Instance.pins` is typed `Dict[str, int]` and NOTHING enforces it —
`apply_config_block` assigns `val_v.value` straight through. It is
reachable today from an authored rig, which is why it is **not**
introduced by this slice; but a CLI surface makes
`config.tc_addr_strap=x49` a one-keystroke traceback instead of a
hand-edited YAML mistake.

**Recommended IN SCOPE:** a type check in `apply_config_block` on the
Strap branch producing a `lang-config` error naming the element and the
offending text. Cheap, additive, and it moves nothing — no fixture
rig uses `config:` at all, so no golden can move. **Flag for veto**:
it is a second concern in one slice, and splitting it out is
defensible. Whichever way it is ruled, say so explicitly in the
report; do not let it be silently absorbed.

## 6. Scope trace — a PREDICTION to falsify by grep and run, not to trust

The missed-caller lesson has now recurred three times (§9.6 part 2,
the multi-bus slice, the plurality slice). **Trace every caller of
`promote_shield`/`parse_promotion_opts` yourself; this list is what a
grep found on 2026-08-12 and it is a hypothesis.**

| file | change |
|---|---|
| `scripts/rigc/promote.py` | `ParsedPromotionOpts.configs`; the `config.` branch in `parse_promotion_opts`; `_render_instance` prints the block; `promote_shield` gains `config=`; `promote_shield_list` threads `opts.configs` |
| `scripts/rigc/cli.py:426-428` | thread `config=opts.configs or None` |
| `scripts/west_commands/rigs.py:384-387` | `--explain`, same |
| `scripts/west_commands/rigs.py:463-466` | `--boards-for`, same |
| `scripts/list_rigs.py` | **predicted ZERO change** — it parses only for the early refusal and forwards the option TEXT opaquely (`PromotedTarget.opts`, its own docstring: "cmake forwards that value opaquely and never parses it"). If this prediction is wrong, that is the report's headline. |
| `scripts/rigc/loader/params.py` | only if §5 is ruled in scope |

Six `promote_shield(...)` call sites thread `socket=`/`sockets=`/
`params=` today; every one of them must gain `config=` or silently
drop it — the exact shape of the §9.6 part 2 bug where two callers
were missing from the brief's own file list.

## 7. The load-bearing acceptance criterion — the identity law

`EXPECTED_REJECTING` **shrinks from `{"adafruit_winc1500"}` to
`set()`**, and it must shrink because the shield genuinely accepts on
both sides, never because the exclusion was emptied. Same discipline
§9.6 part 2 applied to `EXCLUDED`, and the same falsifier: the law
compares emitted artifacts byte-for-byte, so a promoted winc1500 must
produce the identical `rig-gen.overlay` + `config-sheet.md` as a
checked-in rig carrying `config: { w_irq_jmp: D2 }`.

Driver-verified in advance that the accepting side is reachable:
`socket: nexus_arduino_r3` + `config: { w_irq_jmp: D2 }` on the law
fixture board exits 0 today.

Mechanics: add a `_CONFIG_ASSIGNMENTS` table threaded through BOTH
sides — `_materialize_fixture`'s authored block and
`_promotion_target`'s CLI opts — exactly the way `_SOCKET_ASSIGNMENTS`
and `_REQUIRED_PARAM_ASSIGNMENTS` already are.

**A consequence to rule rather than discover:** winc1500 is the ONLY
member of the reject branch, so with `EXPECTED_REJECTING == set()` the
branch — `_normalize_reject_paths` and the stderr comparison — becomes
**live code with no case exercising it**. The partition assertion
still does its job (it now demands every shield accept). Recommended:
KEEP the branch, with a comment stating it is currently unexercised
and why the derived domain can repopulate it. **Flag for veto** — the
project's own "no live code left untested" rule (S6) points the other
way, and deleting it is also defensible.

## 8. Golden impact — classify in advance, per the house rule

**Predicted ZERO movement in every existing golden.** The three
authored `config:` rigs (migrated from `pin:` by item 29) are
untouched by THIS slice; the promotion paths that change are
additive; no fixture exercises `config:`. `nucleo_wifi_logger`'s
byte-exact reject `stderr.txt` and `nucleo_wifi_logger_ok`'s emitted
pair must both be unchanged — state this as a checked result, not an
assumption. New golden dirs, if any, are pure additions. CLI grammar
refusals are unit-tested in `test_promote.py` per the list-promotion
precedent, not given reject goldens.

`RIGC_REFREEZE=1` remains BLOCKED by the harness classifier —
hand-edit and verify BOTH ways if anything does move.

## 9. Twister — a 14th suite, attempt it and report honestly

`adafruit_winc1500` becomes promotable, so `tests/shields/
adafruit_winc1500/` becomes possible (13 suites today). The upstream
pieces exist — `zephyr/dts/bindings/wifi/atmel,winc1500.yaml`,
`zephyr/drivers/wifi/winc1500/`, and the shield's own
`Kconfig.shield`/`Kconfig.defconfig`. **Its own commit**, after the
grammar lands, matching `6becaee`'s precedent.

If it needs application Kconfig beyond the shield's own, **record why
and skip it** — the i2c_mux precedent (`CONFIG_I2C_TCA954X=n`, then a
second wall behind it) is how a refused suite gets documented rather
than quietly dropped. Verify with `west twister --build-only` on both
platforms before committing; do not infer buildability from the
pattern match.

## 10. Explicitly OUT OF SCOPE

- **`invert:`** — the LAST instance-level key with no CLI route, and
  it has a real user (`lotus_buttons`, `invert: true`). Under ruling
  1's rule it would be a fixed key, not a dotted one, since it takes
  no element name. Its own slice.
- Any change below the desugaring seam (§4).
- Making the `phys-position` diagnostic promotion-aware. Its text says
  "add `config: { w_irq_jmp: <position> }` to the instance", which for
  a promoted rig names a materialized file under `rigc-generated` that
  is deleted on success. The analyzer does not know it was promoted.
  **Named, not fixed** — flag it as its own question.
- Indexed/repeated elements, wires, anything the list brief already
  parked.

## 11. Tests

- `test_promote.py`: the `config.` parse (by LABEL — the only spelling
  that resolves, item 29 having removed the `_`→`-` normalization),
  duplicate refusal, empty-value refusal, print order and the rendered
  block, one-element-list equivalence (a `config.`-carrying single
  target and the same target as a one-element list render
  byte-identically).
- `test_singleton_identity_law.py`: §7 — `_CONFIG_ASSIGNMENTS`,
  `EXPECTED_REJECTING == set()`, partition still pinned.
- `test_explain.py`: the desugared pair for a `config.`-carrying
  target, whole-stdout pinned (module's existing style).
- `test_boards_for.py`: a `config.`-carrying target answers boards —
  the §6 caller that would otherwise silently drop the option.
- `test_list_rigs_cmakeformat.py`: the `{PROMOTED}` line for a
  `config.`-carrying target, WHOLE-line pinned (the revved-promoted
  precedent — that test is what caught `i2c_sensor@2@2`).
- `test_cmake_alone_entry.py`: one `-DRIG='...:config.w_irq_jmp=D2'`
  case through the real cmake entry, proving the seam is
  text-transparent as §6 predicts.
- If §5 is ruled in: a `lang-config` type-refusal unit test.

## 12. Acceptance criteria

1. Every existing golden byte-unchanged (§8), stated as a checked
   result.
2. `EXPECTED_REJECTING` is `set()` and winc1500 compares ARTIFACTS on
   both sides (§7) — not stderr.
3. `west build-rig -b nucleo_f401re --rig 'adafruit_winc1500:config.w_irq_jmp=D2'`
   configures clean, run for real.
4. All four §6 caller surfaces thread `config` (`--promote`,
   `--explain`, `--boards-for`, the cmake seam), each with a test.
5. The label spelling resolves (`config.w_irq_jmp=`); the node-name
   spelling (`config.irq-jmp=`) is REFUSED with the `lang-config`
   sentence, matching item 29's own loader contract exactly — there is
   no normalization left to make it resolve; both downstream domain
   refusals still fire on their own sentences.
6. Full gate green, driver-run. Coverage floor 88, currently 93%. The
   unit/integration counts recorded at the multi-plug thread's tip were
   709 / 254 — **re-derive them from a real run rather than from this
   line**; a count carried forward from a handoff has been wrong before
   (the 2026-08-08 "ahead 27+1" precedent).

## 13. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_cmake_alone_entry.py`** (the module that observes
criterion 4's cmake half). **Confirm its `@pytest.mark.build` marking
before claiming it** — the plurality brief's §9 named a build module
by reflex that carried no marker at all. Observing modules:
`test_promote.py`, `test_explain.py`, `test_boards_for.py`,
`test_list_rigs_cmakeformat.py`, `test_singleton_identity_law.py`.
Driver runs the full gate once, after review.

Brief the reviewer to MUTATION-CHECK, not just read: delete the
`config` threading from ONE of the four caller sites (the law case
must fail as a COMPARISON, not drop out of the domain); gut
`_render_instance`'s `config:` block (`test_explain.py` must fail on
the printed document);
revert `EXPECTED_REJECTING` to its old value (the partition assertion
must fail). A green gate proves nothing about whether these are
contracts.

Standing rules: an implementor's report is a HYPOTHESIS — the driver
re-runs it; run negative controls IN-TREE (the reject-fixture family's
`returncode != 0` is nearly vacuous); purge `__pycache__` after any
mutate-and-restore; `RIGC_REFREEZE=1` stays blocked. Dispatch as
`general-purpose` on **sonnet** with the role rules folded into the
prompt if the session is rooted at `/wrk/z/ws-up` — `rig-implementor`/
`rig-reviewer` are not discoverable from there.
