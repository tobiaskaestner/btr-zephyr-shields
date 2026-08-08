# §9.6 part 1 — the parameter vocabulary moves to the shield

**Status:** briefed 2026-08-08, not started. Blocked on the board-declaration
retirement landing first (both slices edit `scripts/rigc/loader/`).

This is the FIRST half of §9.6. It ships no CLI grammar at all. The
`<device>.<prop>=<value>` surface is part 2 and depends on this landing.

## 1. The ruling, and how it widened

§9.6 exit (3) was ruled 2026-08-06: *the shield that declares a parameter
declares the vocabulary that parameter is drawn from.* As recorded, it said
`check_param_token` **"gains a second source"** — the shield's headers
alongside the rig's `dt-includes:`.

**Tobi widened it on 2026-08-08: the source MOVES, and rig-level
`dt-includes:` retires wholesale.** The shield becomes the only vocabulary
source.

That widening came from a measurement, not a preference (§2). It is the
same shape as the S6 ruling on `board:`: a grammar kept alive only by the
fixtures that test it.

## 2. Why "move" rather than "gain" — measured 2026-08-08

**Rig-level `dt-includes:` would have ZERO live users under the narrow
reading.**

- **Corpus: exactly one rig declares it** — `lotus_buttons`, solely for
  `grove_btn`'s required `zephyr,code`. That is precisely the case this
  slice moves onto the shield.
- The corpus's only OTHER param assignment,
  `pilot_variants_variant_c.yml`'s `zephyr,code: 5`, is a bare integer
  literal. `is_int_literal` short-circuits it at `params.py:159` before the
  vocabulary is consulted at all. It needs no header today and none after.
- **Fixtures: six users, three of which exist only to test the grammar.**

| fixture | diagnostic | fate |
|---|---|---|
| `param-missing-header` | `lang-dt-include` | dies with rig-level `dt-includes:` |
| `param-no-vocabulary` | `lang-dt-include` | dies |
| `param-unresolvable` | `lang-dt-include` | MIGRATES to the shield side |
| `param-undeclared` | `lang-param` | unaffected |
| `param-unknown-device` | `lang-param` | unaffected |
| `reference-shields/.../fixture_button.shield` | — | comment only; assigns a plain integer |

Three further reasons, beyond "no users":

1. **Simpler.** `check_param_token` swaps one argument instead of merging
   two lists. A merged vocabulary needs a precedence rule and a diagnostic
   that can say which header a token came from; neither is worth inventing
   for a source with no users.
2. **It fixes the promoted/ad-hoc case BY CONSTRUCTION**, which was §9.6's
   whole blocker: a promoted shield has no `rig.yml` to carry
   `dt-includes:`. If the shield is the only source, part 2 needs nothing
   from the rig at all.
3. It avoids shipping a grammar with zero users — ruled against for
   `board:` in nearly the same words (s6-brief §11).

**The counter-argument, recorded rather than dismissed:** an escape hatch
has value if a rig ever needs a token the shield author did not anticipate.
Under this ruling that is a SHIELD bug — the shield owns the parameter's
contract — and nothing in the tree wants it today. If a real case appears,
re-adding a rig-level source is additive and this brief's §5 dependency
work is what makes it cheap.

## 3. The new declaration

Beside `shield,params`, on the SAME device node — the vocabulary is a
contract of the parameter, not an accident of what the template happened to
`#include`:

```dts
gb_key: button {
        shield,collect = "gpio-keys";
        shield,params = "zephyr,code";
        shield,param-includes = "zephyr/dt-bindings/input/input-event-codes.h";
        gpios = <&gb_plug GROVE_SIG0 (GPIO_PULL_DOWN | GPIO_ACTIVE_HIGH)>;
};
```

**Rejected: recovering the shield's own `#include` lines instead.** Two
ways, both worse:

- `source_files()` (what the shield library already uses for deps)
  recovers files from each node's and property's `.filename`. **A
  macro-only header contributes no node and no property, so
  `input-event-codes.h` would never appear.** This is the trap that makes
  the implicit design fail silently rather than loudly.
- `linemarker_files()` does see it, but returns every transitively opened
  header. `zephyr,code: GPIO_ACTIVE_HIGH` would then resolve, which
  silently weakens the very rules (4/5) this machinery exists to enforce.

A textual scan of `#include` lines would make rigc a second authority on
what cpp already owns. Declare it.

## 4. Scope — VERIFY EVERY PATH, this is a trace not a census

### Production
- `scripts/rigc/shields.py:39,202-209` — `shield,params` is parsed here
  into `Device.declared_params`; `shield,param-includes` joins it. Line 39
  is the known-property allowlist and must gain the name too.
- `scripts/rigc/model.py:85` — `Device.declared_params`; add the includes
  field beside it. **`model.py:331-332` — `Rig.dt_includes` /
  `dt_includes_refs` GO.**
- `scripts/rigc/loader/params.py` — `check_param_token` takes the shield's
  vocabulary instead of the rig's; `check_dt_includes` moves to shield-
  library load (or dies, if the library's own parse already validates the
  header — decide and state which); `apply_params_block`'s signature loses
  `dt_includes`.
- `scripts/rigc/loader/delta.py` — **`union_dt_includes` dies** along with
  its threading through `apply_instances_block` / `apply_delta`.
- `scripts/rigc/loader/__init__.py:180-208, 262-281, 323, 343, 355,
  443-444` — `Content.dt_includes`/`_refs` and every call site.
- `scripts/rigc/loader/documents.py` — the `dt-includes` schema key goes.
  **A stray `dt-includes:` is SILENTLY IGNORED, not an unknown-key error**
  (Tobi, 2026-08-08). This is not a fresh decision for this slice: the
  board-declaration retirement (`7c724bd`) settled the identical question
  for `board:`/`sockets:` the same way, and the two answers must match.
  **Rig.yml/shield.yml schema tightening is its own queued slice** — that
  is where an unknown key becomes an error, for every retired key at once
  rather than one grammar at a time.

### Content
- `boards/shields/grove_btn/grove_btn.shield` and
  `boards/shields/pilot_alt_button/pilot_alt_button.shield` — both declare
  `zephyr,code`, both gain `shield,param-includes`. These are the only two
  shields in the tree declaring `shield,params` (fixtures aside).
- `boards/rigs/lotus_buttons/lotus_buttons.yml` — drops its `dt-includes:`
  block and the comment explaining it.

## 5. THE ACCEPTANCE CRITERION THAT MATTERS MOST

**`scripts/rigc/tests/goldens/lotus_buttons/context.cmake` must be
BYTE-UNCHANGED.**

Its `RIG_DEPENDS` today carries
`<ZEPHYR_BASE>/include/zephyr/dt-bindings/input/input-event-codes.h`,
reaching it through the RIG's `dt-includes:` via `check_include`'s
linemarker recovery. After this slice the header must still be there,
sourced from the shield instead — otherwise editing it stops retriggering
configure, and the regression is invisible until someone edits a keycode
header and gets a stale build.

`RIG_DEPENDS` is sorted, so an unchanged SET is unchanged BYTES. If that
golden moves, the dependency plumbing is wrong — do not refreeze it.

This is why `check_include` should be reused verbatim on the shield side
rather than replaced: it already returns `(detail, files)`, and `files` is
exactly the dependency data.

## 6. Goldens — classified, and reject `stderr.txt` is byte-exact BY RULING

- `param-missing-header`, `param-no-vocabulary`: the mechanism they
  describe ceases to exist. **Delete fixture and golden together**, in the
  same change — S6's rule, which is what keeps "no live code left
  untested" true in both directions.
- `param-unresolvable`: MIGRATES. The token still fails to resolve, but now
  against the shield's vocabulary, so the message changes. That is a
  user-facing diagnostic rewording — a product decision, wanted, but it
  must be presented as its own classified diff, not folded into a refreeze.
- `param-undeclared`, `param-unknown-device`: `lang-param`, untouched. If
  either moves, something is wrong.
- Every corpus golden other than `lotus_buttons`: byte-unchanged.

`RIGC_REFREEZE=1` is blocked by the harness permission classifier in this
environment. Hand-edit from the exhaustive failure list and verify two
ways: the emitted-corpus tests pass, AND the diff applied is only what was
intended.

## 7. Reduced verification contract — the modules that OBSERVE, and the
modules this INVALIDATES

The rule learned twice (S5 named only the first set, S6 only the second,
both incomplete):

**Observe the criteria:** `tests/integration/test_emitted_corpus.py` (the
`lotus_buttons` golden, §5), `tests/integration/test_emitted_rejects.py`
(the three param goldens), `tests/unit/loader/test_params.py`.

**Invalidated by the change:** `tests/unit/loader/test_delta.py:274-305`
(four `union_dt_includes` tests, whose subject is being deleted —
DROP them with it, do not adapt), `tests/unit/test_promote.py` and
`tests/integration/test_singleton_identity_law.py` (both read
`shield_declares_required_params`, which is adjacent to the parsing being
extended), plus anything asserting `Rig.dt_includes`.

## 8. Out of scope

- **The `<device>.<prop>=<value>` CLI grammar.** That is part 2. Its slot
  already exists: `--rig <shield>:<key>=<value>` landed 2026-08-08
  (`bde0b0a`), `_PROMOTION_OPTS` is the closed set it joins, and the
  separator is already `:` precisely because `zephyr,code` contains a
  comma.
- `grove_btn` and `pilot_alt_button` becoming promotable. That is part 2's
  acceptance criterion, and S4's `EXCLUDED` assertion
  (`test_singleton_identity_law.py:177`) is written to SHRINK when it
  lands. It must not shrink in this slice.
- `RIG_DEPENDS`'s shape. Unchanged (§5).
