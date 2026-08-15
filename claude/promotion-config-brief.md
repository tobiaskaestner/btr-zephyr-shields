# `config.<label>=` — the promotion grammar's missing category

**Status:** briefed 2026-08-14, ready to dispatch. Ruled by Tobi
2026-08-14 after asking whether `adafruit_winc1500` could now be
promoted. It cannot, and this slice is why not, fixed.

## 1. The gap, exactly

`adafruit_winc1500` is the sole member of `EXPECTED_REJECTING`
(`scripts/rigc/tests/integration/test_singleton_identity_law.py:187`).
The reason recorded there is right: it "needs a routing-jumper selection
(`config:`) that neither side supplies".

That is not a property of the shield. It is a **missing category in the
promotion grammar.** `rigc/promote.py::ParsedPromotionOpts` has exactly
three fields — `fixed`, `params`, `sockets` — and
`rigc/promote.py::promote_shield` takes `socket`/`sockets`/`params`/
`revision`. There is no way to express a config element at all.

So the blocked set is not one shield: it is **every shield carrying a
jumper or a strap the rig must select**. `adafruit_winc1500` is simply
the only one in the corpus today. Its `w_irq_jmp` has
`shield,position-domain = <D7 0>, <D2 1>` and no default the allocator
may pick, because non-CS positions are never auto-allocated — so the rig
must choose, and promotion has no words for choosing.

The checked-in rig that already does this is
`boards/rigs/nucleo_wifi_logger_ok/nucleo_wifi_logger_ok.yml`:

```yaml
  - name: wifi_1
    shield: adafruit_winc1500
    socket: arduino_r3
    config:
      w_irq_jmp: D2                # move IRQ off the RTC's D7
```

**The value is a position NAME (`D2`), not an index.** Whatever you
build must produce exactly this spelling.

## 2. RULED — the grammar is `config.<label>=<value>`

`rigc/promote.py::parse_promotion_opts` splits a dotted key on the FIRST
dot into `<device>.<prop>`, routing to `params` — except when the
left half is exactly `socket`, which is reserved unconditionally and
routes to `sockets` instead. **Add `config` as a second reserved left
half, by exact analogy.**

```
RIG=adafruit_winc1500:config.w_irq_jmp=D2
```

Reasons this is the right spelling rather than a new separator or a bare
keyword:

- It reuses the reservation mechanism `socket` already established, so
  there is one rule with two reserved words, not two rules.
- `:` stays the separator, which is a hard constraint the existing
  docstring already explains: real devicetree property names contain
  commas, so `,` could never work.
- `config` is ALREADY a reserved word one layer down — a shield's own
  DTS puts config elements in a `config { }` node
  (`boards/shields/adafruit_winc1500/adafruit_winc1500.shield`). A
  shield device labelled `config` would collide, exactly as one labelled
  `socket` already would; that trade was accepted for `socket` and the
  same reasoning applies.
- Explicit `key=value` only, no bare-word shorthand — Tobi's decision 3
  of 2026-08-08, already recorded in `parse_promotion_opts`'s docstring.

Config-element labels resolve by DTS LABEL (item 29, `33e5e49`), so
`w_irq_jmp` is the label, not the node name `irq-jmp`. Do NOT validate
the label against the shield here: `parse_promotion_opts` deliberately
does not validate device or property existence either — that is the
loader's job, and `rigc/loader/params.py::apply_config_block` already
renders the valid labels on a miss. Follow the existing division.

## 3. What to change

1. **`rigc/promote.py::ParsedPromotionOpts`** gains
   `config: Dict[str, str]` — label -> value, the same shape
   `Instance.config` carries, so the printer emits the structure a real
   rig.yml already uses. Give it a `field(default_factory=dict)` like
   `sockets` has, so existing constructions keep working.
2. **`rigc/promote.py::parse_promotion_opts`** routes
   `config.<label>=<value>` to it, with the same refusals the socket
   branch already has: empty label, empty value, duplicate label. Each
   with its own sentence.
3. **`rigc/promote.py::promote_shield`, `::promote_shield_list` and
   `::_render_instance`** gain a `config` argument and print a `config:`
   block. `_render_instance` is the single printer both paths go
   through — keep it that way, so a one-element list stays
   byte-identical to `promote_shield` BY CONSTRUCTION rather than by two
   hand-synchronised builders (its own docstring's stated invariant).
4. **Print order.** `_render_instance` already has a fixed order for
   `socket:`/`sockets:`/`params:`. Put `config:` where
   `nucleo_wifi_logger_ok.yml` puts it — after `socket:`, before
   `params:` — and make `_promotion_target`'s CLI-option order match, so
   the two sides of the singleton law cannot drift.
5. **`rigc/cli.py`** wherever it threads `ParsedPromotionOpts` into
   `promote_shield`/`promote_shield_list` — grep for the call sites; a
   new field that nothing threads is a silent no-op.

## 4. The singleton identity law

`scripts/rigc/tests/integration/test_singleton_identity_law.py`:

- Add a `_CONFIG_ASSIGNMENTS` table, parallel to
  `_REQUIRED_PARAM_ASSIGNMENTS`, mapping `adafruit_winc1500` to
  `{"w_irq_jmp": "D2"}`. `::_promotion_target` reads it to build the CLI
  target; `::_materialize_fixture` reads THE SAME table to write the
  checked-in-rig side. One table, two readers — that is what makes the
  two sides unable to disagree, and it is the module's existing pattern.
- **`adafruit_winc1500` leaves `EXPECTED_REJECTING`** — it now emits
  comparable artifacts on both sides.

**The set does NOT become empty, and this is a correction to an earlier
draft of this brief.** Item 36 (`grove_pwm_led_inv`) joined it on
2026-08-14: that shield authors `PWM_POLARITY_INVERTED`, and the
singleton law's own fixture board carries a 2-cell PWM socket, so
`rigc/analyzer/gpio.py::_collect_channel` correctly refuses it there.
Both sides reject identically.

That matters because the set's comment explains it is "pinned because
the reject branch is the law's weak path: if it ever silently widened,
the suite would stay green while comparing nothing." Removing
`adafruit_winc1500` therefore does NOT strand that branch without a
witness — `grove_pwm_led_inv` keeps it exercised. **Confirm that is
still true when you get there** rather than trusting this paragraph, and
if the set would end up empty after all, say so and stop rather than
inventing a synthetic rejecting shield to fill it — that would be a
design decision, not an implementation one.

## 5. The twister suite

`tests/shields/adafruit_winc1500/`, following
`tests/shields/temp_click/tests.yaml`, which is the precedent for a
suite carrying a promotion option:

```yaml
tests:
  shields.adafruit_winc1500:
    platform_allow: nucleo_f401re/stm32f401xe/rig
    tags: shields
    extra_args:
      - RIG=adafruit_winc1500:config.w_irq_jmp=D2
```

Verify the platform actually works before committing to it — the shield
needs an `arduino-r3` socket with `socket,spi` AND a `socket,cs-pool`
(its CS is pool-allocated, not copper-fixed). `frdm_k64f` may serve too;
check both and say which you used and why. **Build it (`--build-only`)
and report the result** — do not add a suite you have not run.

Note `D7` would ALSO be a legal selection and is the domain's default
position; on a board where nothing else claims D7 the rig is realizable
either way. Using `D2` matches `nucleo_wifi_logger_ok`'s own choice and
keeps the promoted rig comparable to the checked-in one, which is the
point of the law. Say so in the suite's comment.

## 6. Acceptance criteria

1. `config.<label>=<value>` parses, with refusals for empty label, empty
   value and duplicate label, each with its own sentence.
2. A promoted rig prints a `config:` block matching
   `nucleo_wifi_logger_ok.yml`'s spelling — position NAME, not index.
3. `promote_shield` and a one-element `promote_shield_list` produce
   BYTE-IDENTICAL output with a config assignment, proving §3.3's
   invariant survived.
4. `adafruit_winc1500` passes the singleton identity law as an ACCEPT;
   `EXPECTED_REJECTING` is empty, and §4's coverage question is answered
   in the report.
5. A twister suite, built and reported.
6. Every existing golden byte-unchanged — this slice adds a grammar
   category, it changes no existing rig. State as a checked result.
7. Full gate green, driver-run. Re-derive the baseline from the tree.

## 7. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_singleton_identity_law.py`** (it observes criterion 4).
Confirm its `@pytest.mark.build` marking. The driver runs the full gate.

Brief the reviewer to MUTATION-CHECK: route `config.<label>=` to
`params` instead — criterion 2's test must fail on the PRINTED BLOCK,
not merely somewhere; drop the `config` argument from `_render_instance`
while leaving it on `promote_shield` — criterion 3's byte-identity test
must fail; change `_CONFIG_ASSIGNMENTS`'s value to `D7` — the law must
still pass (both sides read the same table), which proves the table is
genuinely the single source and not two coincidentally-equal literals.
That last one is a CONTROL, not a defect hunt: if it FAILS, the two
sides are not reading the same table and that is the finding.

Standing rules: an implementor's report is a HYPOTHESIS. This brief's
line numbers are PREDICTIONS — re-derive them. Trace every caller by
grep AND run. Run negative controls IN-TREE. Purge `__pycache__` after
any mutate-and-restore. **Never `git checkout`/`reset`/`stash`** — copy
a file aside and copy it back. Never store anything in a `west build -d`
directory. When you name a function in your report, qualify it as
`path/to/module.py::function_name`. Dispatch as `general-purpose` on
**sonnet** from a session rooted at `/wrk/z/ws-up`.
