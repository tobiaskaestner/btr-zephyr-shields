# §9.6 part 2 — the `<device>.<prop>=<value>` promotion CLI grammar

**Status:** briefed 2026-08-09, not started. Depends on part 1
(`param-vocabulary-brief.md`), landed `067b4e6`. Not a fresh design — the
existing parser's own docstring already previews this exact extension by
name (`promote.py:155-159`, citing `zephyr,code`).

## 1. What's already there, verified rather than assumed

- `promote.py:139-159`'s `parse_promotion_opts` already parses the FULL
  chained grammar — `<shield>[@rev][:<key>=<value>[:<key>=<value>...]]` —
  and is documented as designed to grow into parameter assignments. The
  only restriction today is `key not in _PROMOTION_OPTS`, a closed tuple
  holding exactly `("socket",)` (line 136).
- `check_promotable` (`promote.py:238-263`) does **not** gate on required
  params at all — it only checks `@variant` and `template:`. The actual
  blocker is downstream: `promote_shield` (`promote.py:183-236`) prints a
  content document with **no `params:` block whatsoever** (verified by
  reading its return: `content = "instances:\n  - name: ...\n    shield:
  ...\n"`, optionally `+= "    socket: ...\n"` — nothing else), so a
  promoted shield with a required, undefaulted param fails downstream at
  `check_param_invariant` (rule 2) exactly as an authored rig.yml omitting
  a required assignment would.
- `shield_declares_required_params` (`promote.py:266-`) exists SOLELY so
  `test_singleton_identity_law.py`'s S4 census can exclude such shields
  from its domain today. Confirmed directly:
  `test_singleton_identity_law.py:167-185`'s
  `test_excluded_set_is_exactly_the_required_param_shields` asserts
  `EXCLUDED == {"grove_btn", "pilot_alt_button"}` and its own docstring
  states this "can only SHRINK... the day Sec 9.6's grammar lands."
- The CLI's one call site is `cli.py:337-345`: `shield_name, _, opt_text =
  args.promote.partition(":")`, then `promote.parse_promotion_opts(...)`,
  then `promote.promote_shield(shield_name, args.revision,
  socket=opts.get("socket"))`. This is the only place threading is needed.
- `_PROMOTION_OPTS`'s closed-tuple ruling (Tobi, 2026-08-08) — "socket
  alone to start, everything else later" — is confirmed (Tobi, 2026-08-09)
  to mean exactly this: a dotted `<device>.<prop>` key is a DIFFERENT
  grammar category from the fixed keywords, not a new member of
  `_PROMOTION_OPTS`. Not a fork to re-litigate.

## 2. The one real parsing decision: split on the FIRST dot only

Devicetree property names may legally contain a literal `.` (rare, but the
grammar does not forbid it; `zephyr,code`-style comma-separated vendor
prefixes are the common case, dots are not). Shield-local device LABELS in
this corpus are always simple identifiers (`gb_key`, `dl_rtc` — verified,
never dotted). So a `<device>.<prop>` key must be split with
`partition(".")`, taking the FIRST dot as the separator and everything
after it — dots included — as the full property name. Same
first-occurrence-only pattern `cli.py:337` already uses for
`shield_name`/`opt_text`.

## 3. Scope — VERIFY EVERY PATH

### Production
- `scripts/rigc/promote.py`:
  - `parse_promotion_opts` — recognize a key containing `.` as a
    `<device>.<prop>` assignment (via the first-dot split, §2), routed
    separately from the `_PROMOTION_OPTS` membership check. Return shape
    needs to separate the two categories rather than overload one flat
    `Dict[str, str]` — e.g. a small return dataclass/2-tuple
    `(fixed: Dict[str, str], params: Dict[str, Dict[str, str]])` (device
    label -> prop -> value), matching `Instance.params`'s own shape
    (`model.py:225`) so `promote_shield` can print it with the identical
    structure a real rig.yml already uses.
  - `promote_shield` gains a `params: Optional[Dict[str, Dict[str,
    str]]] = None` argument. When given, print a `params:` block onto the
    ONE synthesized instance, same YAML shape as any authored rig.yml
    (verified against `boards/rigs/lotus_buttons/lotus_buttons.yml:25-27`
    — `params:\n  gb_key:\n    zephyr,code: INPUT_KEY_0\n`, 4-space then
    6-space indent under the instance).
  - **Do not validate device/property existence in promote.py.** Print
    the text and let it flow through the SAME `rigc.loader.load` path
    every promoted document already goes through
    (`PromotedRig`'s own documented contract, `promote.py:109-122`: "the
    printed rig.yml declares no board of its own... loads through
    rigc.loader.load with no diagnostics given a board -- that is this
    dataclass's whole contract"). Rules 1/3/4/5/6 — undeclared
    property, unknown device, token resolution, header validity — all
    already fire correctly against whatever text lands in that
    `params:` block, because `apply_params_block` cannot tell a
    promoted document's params from an authored one. Writing any
    parallel validation in `promote.py` would be a second authority for
    facts the loader already owns.
- `scripts/rigc/cli.py:337-345` — thread the params half of the new
  return shape into `promote_shield`'s new argument.
- `check_promotable`/`shield_declares_required_params`: **UNCHANGED.**
  Neither gates on params today, and neither should after this lands —
  `shield_declares_required_params` is not a promotability rule, it is
  S4's own domain-eligibility predicate (see below), a distinction its
  own docstring already draws.

### Content
- None. `grove_btn`/`pilot_alt_button` already declare
  `shield,param-includes` (part 1). No shield or rig file changes.

### Tests
- `test_singleton_identity_law.py` — this is where the acceptance
  criterion lives, and it is more than "the assertion shrinks":
  `_census()` (whatever currently builds `ELIGIBLE`/`EXCLUDED` off
  `shield_declares_required_params`) must gain a way to supply CLI params
  for a shield that needs them, comparing the promoted side (`--promote
  grove_btn:gb_key.zephyr,code=INPUT_KEY_0`, say) against a REAL rig.yml
  using the identical assignment — the same shape S4 already uses for
  `socket=` (mikrobus quail shields). `EXCLUDED` should shrink to `set()`
  — both `grove_btn` AND `pilot_alt_button` become includable, since both
  need exactly one required param and nothing else blocks them.
- `test_promote.py` — unit coverage for `parse_promotion_opts`'s new
  dotted-key branch (accept, reject on ambiguous/malformed, the
  first-dot-only split with a deliberately dotted property name as the
  negative control proving it doesn't mis-split).
- New reject fixture/golden: a `<device>.<prop>` naming a real device but
  an UNDECLARED property (rule 1) reached via promotion — confirms rules
  1/3 fire identically for promoted and authored params rather than
  assuming it from the shared-codepath argument above.

## 4. Acceptance criteria

1. `west rigs --promote 'grove_btn:gb_key.zephyr,code=INPUT_KEY_0'
   <board>` (or the CLI's real invocation shape) builds successfully.
2. Same for `pilot_alt_button` with its own required `zephyr,code`.
3. `test_singleton_identity_law.py`'s `EXCLUDED` shrinks to `set()` —
   verified as a real comparison against a corpus rig assigning the same
   value, not merely an emptied exclusion set.
4. A promoted shield missing a required assignment still fails exactly as
   today (rule 2, `check_param_invariant`) — this must NOT regress; it is
   the control proving the params: block is real, not a rubber stamp.
5. Every existing golden byte-unchanged — this slice is additive; nothing
   authored today uses the new grammar.

## 5. Out of scope

- Any change to `_PROMOTION_OPTS`'s fixed-keyword set itself.
- Any change to rule 1–6 diagnostic wording — reusing the existing
  codepath means there is nothing new to word.
- `board_as_coordinate`/multi-bus-socket work — unrelated slices.
