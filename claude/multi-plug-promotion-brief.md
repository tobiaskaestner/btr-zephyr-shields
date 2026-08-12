# Multi-plug promotion, slice 3 — the per-slot promotion grammar

**Status:** briefed 2026-08-12, ready to dispatch. Slice 3 of the
multi-plug thread (design `multi-plug-shield-design.md` §0; slice 1
`99fd59c`/`b2b5630`, slice 2 in tree/staged): a multi-plug shield
becomes PROMOTABLE. This retires ruling R4's "separate slice" deferral
and its refusal — the `check_promotable` plug-count gate, its "cannot
be promoted (yet)" sentence, and the singleton-law exclusions all go,
in the same change as the tests that pinned them (mechanism and tests
together).

## 1. Context — what promotion is, and what blocks a plural shield

`--rig <shield>[@rev][:<key>=<value>...]` desugars to a synthetic rig
with ONE instance named after the shield (S3a). `parse_promotion_opts`
(`promote.py:163`) splits `:`-separated assignments into the closed
`_PROMOTION_OPTS` (`("socket",)`, `promote.py:143`) and params — ANY
dotted key routes to params as `<device>.<prop>=<value>` (first-dot
partition). The standing rulings stay in force: promotion options are
PROMOTION-ONLY (never legal on a persisted rig — `list_rigs` refuses so
the cmake seam and both query surfaces share one message); explicit
`key=value` only, no bare-word shorthand; `:` separates because real
property names carry commas.

A plural shield today: `check_promotable` refuses on `plug_count > 1`;
`test_singleton_identity_law.py`'s derived EXCLUDED set is
`{"can_span_click", "mikrobus_span_adapter"}`, asserted with the R4
reason and BUILT to shrink when this slice lands.

## 2. The grammar (driver-decided spellings — flag any change of heart)

**Single-plug: `socket=<label>` — byte-untouched.**

**Plural: `socket.<slot>=<label>`, one assignment per slot.**

```
west build-rig --rig 'can_span_click:socket.left=quail_sock1:socket.right=quail_sock2' <app>
```

- **The `socket.` dotted-key prefix is RESERVED.** Today every dotted
  key is a param (`promote.py`'s first-dot partition). The refinement:
  a dotted key whose device-label half is exactly `socket` is a SLOT
  option, never a param. Consequence, made loud rather than latent: a
  shield device labeled literally `socket` can no longer receive
  promotion params — if a param assignment ever targets one, refuse
  with a diagnostic saying exactly that (no such device exists in the
  corpus or fixtures; verify with a grep and say so in the report).
- `_PROMOTION_OPTS` stays the closed tuple `("socket",)` — the slot
  form is a refinement of the one existing key, not a new key.
- Refusals, each with its own sentence: bare `socket=` on a plural
  shield (name the slots, point at the dotted form); `socket.<slot>=`
  on a single-plug shield (point at the bare form); an unknown slot
  (list the shield's real slots); the SAME slot assigned twice in one
  target (today's `fixed` dict would silently last-wins — make the
  duplicate an error for the slot form, and check whether the existing
  bare-key duplicate silently last-wins too: if it does, that is a
  pre-existing wart to NAME in the report, not to fix here).
- Slots not named fall to per-slot inference, exactly like an omitted
  `sockets:` entry in rig.yml — so on a board where every slot's type
  has a unique candidate, `--rig <plural-shield>` works BARE.

**Desugaring:** the synthetic instance's `sockets` map is built from
the slot options (missing slots → None). `@rev` and params compose
orthogonally, unchanged.

## 3. Semantics and the query surfaces

- `check_promotable`: the plug-count gate GOES. What remains checked is
  what single-plug promotion already checks, per slot.
- `--boards-for <plural-shield>` (bare): answers boards where EVERY
  slot resolves by per-slot inference. For `can_span_click` on quail
  that is NO board (four mikrobus candidates per slot — the ambiguity
  refusal is correct, not a gap); with explicit slot options it answers
  boards carrying those labels — mirror how `socket=` interacts with
  `--boards-for` today and stay symmetric.
- `--explain` prints the desugared form including the sockets map —
  read how it renders `socket=` today and extend in kind (slot-
  qualified lines only for plural shields; single-plug output
  byte-identical).
- **Trace EVERY caller of `parse_promotion_opts`/`promote_shield`/
  `check_promotable`** — `promote.py`, `scripts/list_rigs.py`
  (`resolve_target`, the cmake seam), `scripts/west_commands/rigs.py`
  (`--boards-for`, `--explain`, `_resolve_both_namespaces`) — plus any
  caller this list misses: the recorded §9.6-part-2 lesson is that the
  brief's own list missed exactly two of these. Grep and run; the list
  above is a prediction.

## 4. The identity law — the slice's real acceptance criterion

`test_singleton_identity_law.py`'s **EXCLUDED set returns to `set()`**,
via the derived predicate (drop the `shield_is_multiplug` exclusion),
never a hand-list. Both multi-plug corpus shields join the census:

- **`can_span_click`**: the promoted side needs explicit slot options
  (every candidate board is slot-ambiguous). Study how the law's
  machinery threads promotion options for the required-param shields
  (`grove_btn`'s `<device>.<prop>=` case — §9.6 part 2's own criterion
  was this same set shrinking) and thread `socket.<slot>=` the same
  way; the comparison rig.yml carries the identical `sockets:` map.
- **`mikrobus_span_adapter`**: a pure-copper carrier with no devices —
  both sides emit near-empty artifacts; the law compares them all the
  same. If the law's machinery genuinely cannot host it (e.g. the
  board/fixture coordinate the census assigns cannot mate two mikrobus
  slots), an asserted, REASONED exclusion with a new named predicate is
  acceptable — but only after trying, with the attempt described in
  the report.

The law is expand-level; run it, don't reason about it.

## 5. Twister — the suite promotion unblocks

`tests/shields/` gains `can_span_click/` (13th suite), following the
existing quail click suites' pattern (`bde0b0a` added `:socket=` via
`testcase.yaml` `extra_args: -DRIG=...` — the quoting precedent for
option-carrying RIG strings). Platform: quail only.

**Probe before authoring, per the standing rule:** twister BUILDS AND
LINKS, unlike the corpus `--cmake-only` tier. Check what the suite can
honestly enable: if `CONFIG_CAN`/`CAN_MCP2515` walls (chosen nodes,
init priorities — the TCA954x shape), fall back to enabling only the
spi-nor side (`CONFIG_SPI_NOR`) or plain loadability, matching what the
existing suites of Kconfig-inert shields do — and RECORD the probe
either way. `west twister --build-only -p mikroe_quail/stm32f427xx/rig
-T btr-shields/tests` is the verification, run for real.

No suite for `mikrobus_span_adapter` (a bare promoted carrier exposes
an unplugged socket — nothing observable builds; same reasoning that
keeps `i2c_mux` suite-less, recorded here so nobody re-derives it).

## 6. Explicitly OUT OF SCOPE

- Promotion options on persisted rigs (permanently refused by ruling).
- Any new option key; `_PROMOTION_OPTS` stays `("socket",)`.
- The parked plural-shield refusals (via-routed wires, routing
  jumpers) and the `phys-ambiguous-bus` pass-through — untouched.
- rig.yml grammar: nothing changes on the persisted side.

## 7. Fixtures and tests

- `test_promote.py`: the refusal test flips to acceptance; new parse
  tests for every §2 refusal sentence; the reserved-prefix refusal.
- `test_boards_for.py`: bare plural shield on quail answers empty
  (ambiguity, asserted via the census the module already builds);
  with slot options answers quail. Check the existing
  `..._required_param_answers_once_assigned` shape for the pattern —
  and remember its own history: a new board once flipped its "answers
  EMPTY" assertion; assert the reason, not just the emptiness.
- `test_multiplug_shield.py`/`test_multiplug_carrier.py`: one promoted
  round-trip each (`--rig` with slot options through the cmake-alone or
  build-rig front door, build-marked), asserting the SAME artifacts
  their existing rig-side tests pin — the promoted and persisted forms
  meeting is the law in miniature, at build level.
- `test_list_rigs_cmakeformat.py`: the `{PROMOTED}` line for a
  slot-optioned target — whole-line pin, following the revved-promoted
  precedent (it caught a real desugaring bug once; that is why
  whole-line).
- Goldens: NEW only. Zero existing golden movement (criterion, not
  hope — single-plug promotion paths are byte-identical).

## 8. Acceptance criteria

1. Every existing golden byte-unchanged; single-plug promotion output
   (cmakeformat lines, --explain, artifacts) byte-identical.
2. `EXCLUDED == set()` in the singleton law, predicate-derived, with
   both multi-plug shields comparing (or the one reasoned exclusion of
   §4, if honestly earned).
3. The promoted `can_span_click` build round-trip produces the same
   pinned artifacts as the persisted `quail_can_span` path (cross-plug
   int-gpios line, CS placements).
4. `--boards-for` behaves per §3, asserted both bare and optioned.
5. Every §2 refusal fires on its own sentence.
6. The twister suite builds on quail (with the honest Kconfig level the
   probe supports), suite count 12 → 13.
7. Full gate green (driver-run; floor 88, currently 93).

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + ONE named build
module — `test_multiplug_shield.py` (it carries the promoted round-trip
per §7; confirm the build mark exists). The twister probe (§5) runs
`west twister --build-only` directly, outside pytest — report the
command and its scenario counts verbatim. Observing modules:
`test_promote.py`, `test_boards_for.py`, `test_singleton_identity_law.py`,
`test_list_rigs_cmakeformat.py`, both multiplug modules. Driver runs the
full gate after review. Brief the reviewer to mutation-check: the
reserved-prefix routing (break it → the param-vs-slot boundary test must
fail on its sentence), the duplicate-slot refusal, and the law (gut the
slot-option threading → can_span_click's comparison must fail, not
silently drop out of the domain). Standing rules: reports are
hypotheses; run callers, don't reason; purge __pycache__ after
mutate-and-restore; no probe artifacts in build dirs; RIGC_REFREEZE
stays blocked — new goldens by capture, verified both ways.
