# Slice brief — hwmv2 revision semantics

Ratified by Tobi 2026-07-26: **revision logic and behaviour become exactly
upstream's.** Design record: design-log 2026-07-26f.

**REVISED 2026-08-03, re-read against the current code as the backlog
required.** The ratified DIRECTION is unchanged and is not reopened here.
But the brief was written before S1/S2, V1c, the rigc rewrite and the
cutover, and **five of its factual premises no longer hold**. They are
called out in §0. Everything else below is the original brief, updated to
name `rigc` modules instead of rigexp's.

**THREE RULINGS, Tobi 2026-08-03 — all three ratified as recommended:**

1. **Adopt upstream's list shape in full** (§0.2, option (a)). The two
   mapping-entry reject fixtures retire.
2. **The classified reject refreeze is AUTHORIZED** (§0.3), scoped to the
   revision/axis diagnostic family; no reject golden outside that family
   may move.
3. **Shields get hwmv2 semantics too** (§0.5). One revision semantics in
   the tool, not two.

**TWO FURTHER DECISIONS, Tobi 2026-08-04:**

4. **No `exact: true` for existing corpus rigs** (§6). They migrate to
   the new shape and GAIN nearest-lower. No existing golden can detect
   the difference — none requests an undeclared revision — so the accept
   corpus still proves byte-identity while the corpus actually exercises
   the new default behaviour instead of opting out of it. `exact: true`
   gets its own new fixture.
5. **Split into TWO dispatches** (§7). Dispatch A is step 1 alone
   (resolver unification, goldens byte-identical). Dispatch B is steps
   2–4. Review between them.

The slice is unblocked. §0.6 records two hazards found while checking the
migration surface after those rulings — neither needs a decision, but
both change what the implementor must do.

---

## 0. What changed since ratification — read this first

### 0.1 The seam is NOT single-place any more (affects §2)

The original says: "`_parse_axis_decl` is the single place the declaration
shape lives, and it is shared by rig.yml and (post-V1c) shield.yml. Change
it there and both axes follow."

Half true today. The **parser** is shared: `loader/library.py::
_load_shield_revisions` calls `loader/axes.py::parse_axis_decl` for
shield.yml. The **resolver** is not. `loader/axes.py::resolve_axis`
resolves a rig's axis; `ShieldLibrary.resolve` (`loader/library.py`,
roughly lines 118–150) re-derives the same three failure shapes —
not-declared-at-all / not-a-member / no-default — inline, with
shield-flavoured `lang-rev` wording.

`axes.py`'s own module docstring claims it is "the ONLY place a
`revisions:`/`variants:` declaration's raw YAML is read **or a selection
resolved against it**". That second half is false, and this slice is
exactly where it bites: format validation, zero-append and nearest-lower
matching would have to be implemented twice, or the shield path made to
delegate.

**Do the delegation first, as its own zero-churn step.** Factor the
three failure shapes into one function over `(decl, selected)` that both
callers use, parameterised by the owner wording, and land it with the
goldens byte-identical. Only then add hwmv2 semantics, in one place. A
behaviour-preserving refactor with an unchanged corpus is the cheapest
possible proof the two resolvers really were equivalent — and if they
turn out not to be, that is a finding worth having before piling
semantics on top.

### 0.2 Upstream's shape collides with S2's mapping-entry rule — NEEDS A RULING

Upstream's block (verified against the pinned tree's
`scripts/schemas/board-schema.yaml`, `format` is REQUIRED,
`additionalProperties: false`):

```yaml
revision:
  format: number            # letter | number | major.minor.patch | custom
  default: "1"
  exact: false              # optional
  revisions:
    - name: "1"
    - name: "2"
```

Its list entries are **mappings with a `name:` key**. That is precisely
the shape `parse_axis_decl` currently REJECTS for a revisions axis: S2
added `allow_variant_metadata`, and with it False the parser emits

> `<owner> revisions: a mapping entry (name:/board:/sockets:) is legal
> only in a rig's variants: list -- this axis takes bare names`

So adopting upstream's shape **inverts an existing rule**, and two reject
fixtures stop being rejects: `revision-mapping-entry` and
`shield-revisions-mapping-entry`. They would have to be deleted or
repurposed, and `allow_variant_metadata`'s meaning changes from "which
axis may take mappings" to something narrower about which KEYS are
allowed in one.

The 2026-07-26 ruling ("copy the SHAPE, not a near-miss — a reviewer
diffs our schema against `board-schema.yaml`") points at adopting it and
paying that cost. But the cost was not visible when the ruling was made:
S2 did not exist. **Options:**

- **(a) Adopt upstream's shape fully.** Two fixtures retire; the
  mapping-entry rule becomes a per-axis KEY whitelist (`name:` everywhere,
  `board:`/`sockets:` only for a rig's variants). Costs the two fixtures
  and a rewrite of every declaring file. Honours the ratified rationale.
- **(b) Keep bare-scalar entries for revisions**, adopt only `format:` /
  `exact:` / the resolution semantics. Smaller diff, both fixtures live,
  but the schema is then a deliberate near-miss — the exact thing the
  ruling rejected.

Recommendation: **(a)**, because the ruling's rationale is about
reviewability against upstream and (b) reintroduces the near-miss.

**RULED (a), 2026-08-03.** `revision-mapping-entry` and
`shield-revisions-mapping-entry` retire; `allow_variant_metadata` becomes
a per-axis KEY whitelist (`name:` everywhere, `board:`/`sockets:` only
for a rig's variants).

Two mechanical consequences of (a), stated so they are not rediscovered:

- **The key is renamed too.** Upstream's board.yml key is SINGULAR
  `revision:`, containing a plural `revisions:` list. So
  `revisions: {default:, list: []}` becomes
  `revision: {format:, default:, exact:, revisions: [{name:}]}`, and
  `variants:` keeps its own plural key and its own shape.
- **`parse_axis_decl` splits in two.** With the two axes no longer
  sharing a shape, one parser serving both is dead — that is what §1
  means by spending the one-schema-for-both-axes property. Expect a
  revision-block parser and a variants-block parser, with the shared
  part being whatever genuinely remains shared (the default-is-a-member
  check).

### 0.3 The golden budget is wrong as written — NEEDS A RULING

The original: "Existing corpus rows must be BYTE-UNTOUCHED — every current
rig either declares no revisions or can declare `exact: true` to reproduce
today's behaviour."

That holds for the **accept** corpus, and for a good reason: resolved
values do not change, so `context.cmake`'s `RIG_REVISION` /
`RIG_SHIELD_REVISIONS` and every emitted artifact stay identical.

It does **not** hold for the **reject** corpus, which the original never
mentions. `stderr.txt` is byte-exact permanently by ruling, and this slice
changes the wording of every diagnostic that names the declaration shape.
Measured surface, current tree:

- **16 files declare an axis**: 11 rig-side (`boards/rigs/…` +
  fixtures) and 5 `shield.yml` (only `boards/shields/i2c_sensor/shield.yml`
  is a real corpus shield; the other four are fixtures).
- **Reject fixtures in the blast radius** (diagnostic wording names
  `list:`, the mapping-entry rule, or revision resolution):
  `shield-bad-revisions-block`, `shield-revisions-mapping-entry`,
  `revision-mapping-entry`, `unknown-revision`,
  `shield-no-revisions-declared`, `shield-undeclared-revision`,
  `no-such-axis`, `variant-revision-collision`,
  `dotted-revision-no-fragment`, `revision-crosses-variant`,
  `revision-carries-board`.

This is the same class of decision Tobi made for the lazy shield library
on 2026-08-03 (diagnostic ORDER need not be preserved because rigexp is
no longer a reference). Here the question is diagnostic **wording** for
the revision family.

**RULED, 2026-08-03: the classified reject refreeze is AUTHORIZED**,
scoped to the revision/axis diagnostic family. Acceptance criterion
stands: **no reject golden outside that family may move**, and the diff
must be classified per fixture, not blessed wholesale.

### 0.4 Requested-vs-resolved must reach the shield side too (affects §3)

The original's §3 is right and is the most important part of the slice,
but it only discusses rig fragment filenames and `context.cmake`. Two more
consumers exist now:

- `ShieldLibrary._resolve_revision` constructs `<name>_<rev_norm>.shield`
  and `<name>_<rev_norm>.conf` from the selected revision. Under
  nearest-lower these must be built from the **resolved** value, or a
  shield silently loses its revision fragment — the exact
  `_RIG_RESOLVED_NAME` hazard class the original names (B1).
- `RIG_SHIELD_REVISIONS` in `context.cmake` carries `<shield>@<rev>`
  pairs that dts.cmake consumes. Those must be **resolved** values.

Also note the shield-side analogue of rule 10 already lives in
`_resolve_revision` (a non-default revision contributing nothing is an
error, the default is exempt). Nearest-lower interacts with it the same
way the original's §"Interactions" flags for rigs — assert it explicitly
on the shield side too.

### 0.5 Scope question: do shields get hwmv2 semantics at all? — NEEDS A RULING

The original assumes one parser therefore one behaviour, so it never asks.
Now that §0.1 shows the resolvers are separate, it is a real choice:
`format:` would become required on every `shield.yml` declaring revisions
(upstream's schema makes it required), which is new authoring burden on a
file that today declares three lines. Nearest-lower for a *shield*
revision is also a different product question from nearest-lower for a
*board* revision.

Recommendation: **yes, both** — a shield revision is a hardware variant
exactly as a board revision is, and two divergent revision semantics in
one tool is worse than one burden.

**RULED yes, 2026-08-03.** `format:` becomes required on every
`shield.yml` declaring revisions, and nearest-lower applies shield-side.
That makes §0.1's resolver unification a prerequisite rather than a
tidiness step: without it the semantics land twice.

### 0.6 Two hazards found while checking the migration surface

Neither needs a decision; both change what the implementor must do.

**(i) YAML numeric coercion silently corrupts revision ids — and this is
a LIVE latent bug, not a new one.** `parse_axis_decl` currently does
`str(item_v.value)` on whatever YAML produced. Measured:

| YAML | parsed | `str()` |
|---|---|---|
| `1.10` | `1.1` (float) | `"1.1"` |
| `1.2` | `1.2` (float) | `"1.2"` |
| `1.2.0` | `"1.2.0"` (str) | `"1.2.0"` |
| `1` | `1` (int) | `"1"` |

So an unquoted `1.10` becomes `1.1` **today**, silently, and would
construct fragment stem `_1_1` instead of `_1_10`. No corpus rig does
this, which is why it has never bitten. Under `major.minor.patch` the
exposure grows, since two-component ids are exactly what an author would
write.

**Therefore: revision ids must be STRINGS, and a non-string is a
`lang-schema` rejection, not a coercion.** Upstream's schema already says
`name: {type: string}`, so this is part of adopting the shape, not an
addition to it. Consequence: every migrated file quotes its ids —
`default: 1` / `list: [1, 2]` become `default: "1"` /
`revisions: [{name: "1"}, {name: "2"}]`. Several corpus files and
fixtures currently use unquoted integers.

**(ii) One fixture is inexpressible in any hwmv2 format and must be
re-authored.** `dotted-revision-no-fragment` declares
`revisions: {default: 1, list: [1, "1.5"]}` — a mixed axis. Under
`number`, `"1.5"` fails `^\d+$`. Under `major.minor.patch`, BOTH fail:
declared names need three components, and **zero-append does not apply to
them**. Verified in the pinned tree — extensions.cmake:1092-1103 appends
zeroes to `BOARD_REVISION` (the REQUESTED value) only, inside the
format branch and before the regex match; the declared list is never
rewritten, and `board-schema.yaml`'s conditional block validates declared
names per format independently.

Re-author it as `major.minor.patch` with `["1.0.0", "1.5.0"]`; its
point — a dotted revision whose fragment is missing — survives, with
stem `1_5_0`. Its golden moves, inside the authorized family.

---

## 1. Declaration shape

Per §0.2, pending ruling. If (a): replace `revisions: {default:, list: []}`
with upstream's block above, for rig.yml AND shield.yml. `format` is
required; `additionalProperties: false` in upstream's schema is worth
mirroring once `rig-schema.yaml` (backlog item 7) exists — note the
interaction, that item is queued right after this one.

**This spends the V1 spec §2 one-schema-for-both-axes property** —
`variants:` keeps `{default:, list:}`. That is a ratified trade, not an
oversight; record it where §2 states the property.

## 2. Behaviour — port, do not reinvent

Source of truth is `board_check_revision`, verified still at
`zephyr/cmake/modules/extensions.cmake:1048` in the pinned tree
`8da5b3a0f60` (the original's line citations all still hold). Port to
Python, into the ONE resolver §0.1 asks you to create first:

- **Per-format id validation.** `letter` → `^[A-Z]$`; `number` → `^\d+$`;
  `major.minor.patch` → `^((0|[1-9][0-9]*)(\.[0-9]+)(\.[0-9]+))$`.
- **Loose typing for major.minor.patch** (extensions.cmake:1092-1103): `@1`
  becomes `1.0.0`, `@1.2` becomes `1.2.0` — append missing zeroes BEFORE
  matching.
- **Nearest-lower-match** (extensions.cmake:1133-1152): an undeclared
  revision resolves DOWN to the highest declared revision less than or
  equal to it, per-format comparison (VERSION_ / STRGREATER / GREATER
  semantics).
- **`exact: true`** disables that, and an undeclared revision is then fatal
  — which is our CURRENT unconditional behaviour, so `exact: true`
  reproduces today's rigs bit for bit.
- **No revisions declared but `@rev` given** stays fatal, wording in the
  existing `lang-rev` family.

Not in upstream's YAML schema and therefore out of scope, though
`board_check_revision` accepts them as cmake arguments for `custom`
boards: `OPTIONAL`, `HIGHEST_REVISION`, `VALID_REVISIONS`.

## 3. Requested vs resolved — a new model field, deliberately

Nearest-lower means the selected string and the effective string differ
(`@1.5` → `1`). Upstream keeps both (`BOARD_REVISION` vs
`ACTIVE_BOARD_REVISION`) and so must we, because **the RESOLVED value is
what constructs fragment filenames** — hazard class B1: derive from the
resolved form, never the raw one; a silently unapplied defconfig is the
failure mode.

- `model.AxisDecl` / `Rig` carry both; `normalize_revision` applies to the
  RESOLVED value when joining filenames, never to the requested one.
- `context.cmake` / `build_info` carry the RESOLVED value — including
  `RIG_SHIELD_REVISIONS` (§0.4).
- `ShieldLibrary._resolve_revision`'s `.shield`/`.conf` stems are built
  from the RESOLVED value (§0.4).
- the configure log prints `requested -> resolved` **only when they
  differ**.

This is a `model.py` change; the design decision is recorded
(2026-07-26f), which is what the lifted freeze requires.

## 4. Deliberately NOT copied — reject loudly, do not silently ignore

- **`format: custom`** → upstream includes `<dir>/revision.cmake` and lets
  the board author call `board_check_revision` themselves. We resolve in
  PYTHON, so this would mean arbitrary cmake in a rig folder feeding a
  Python resolver. Reject with a diagnostic naming the three supported
  formats and saying custom is unsupported for rigs. Parity is therefore
  behavioural-for-the-three-real-formats, NOT full — do not claim
  otherwise in docs or commit messages.
- **The valid-revision glob** (extensions.cmake:1114-1126) discovers
  revisions by matching `<board>_*.conf` FILENAMES. Reachable only via
  `custom`, and it parses filenames — against Q6. Skip it. (Worth a
  sentence in the eventual upstream discussion: this is the one place
  upstream violates its own construct-don't-parse discipline.)

## 5. Interactions to verify, not assume

- **Rule 4 (collision guard).** Format typing SHRINKS the collision
  surface for `letter`/`number` (ids can no longer look like identifiers)
  but not for `major.minor.patch`, where revision `1.2` normalizes to
  `1_2` and a variant may legally be NAMED `1_2`. Keep the widened guard
  (`axes.py::check_axis_collision`); re-run its fixture
  (`variant-revision-collision`, `combined-fragment-collision`).
- **Rule 10 (non-default must contribute a fragment).** With nearest-lower,
  `@1.5` resolving to a default revision hits rule 10's default EXEMPTION.
  Assert that explicitly — it is the case most likely to regress. Assert
  the shield-side analogue in `_resolve_revision` too (§0.4).
- **Two selections, one fragment set.** `@1.5` and `@1` now resolve
  identically. Intended; provenance distinguishes them via requested vs
  resolved.
- **The lazy shield library** (landed 2026-08-03) means a shield template
  parses on first reference, and `_resolve_revision` is on that path.
  Revision resolution now happens strictly before the parse it triggers;
  check that a nearest-lower resolution memoizes under the RESOLVED key,
  not the requested one, or `@1.5` and `@1` will parse the same template
  twice.

## 6. Golden budget

- **Accept corpus: byte-untouched.** Prove it with `git diff --stat`, do
  not assert it. Note the reason is NOT `exact: true` — ruled 2026-08-04,
  existing corpus rigs do not get it and DO gain nearest-lower. Byte
  identity holds anyway because no golden requests an undeclared
  revision, so nearest-lower never fires on the existing corpus. That
  makes the accept goldens a weaker proof than they look: they prove the
  migration inert, NOT that nearest-lower works. Only the new coverage
  below proves that, so do not let a green accept corpus stand in for it.
- **Reject corpus: a classified refreeze**, scoped to the revision/axis
  diagnostic family, pending the §0.3 ruling. Acceptance: no reject golden
  outside that family moves.
- **New coverage**: one accept tuple per format (letter / number /
  major.minor.patch), one nearest-lower resolution whose provenance shows
  `requested -> resolved`, one `exact: true` rejection, one zero-append
  case (`@1` → `1.0.0`), rejects for `format: custom` and for a malformed
  id per format, and — new since the original — one SHIELD-side
  nearest-lower case proving the `.shield`/`.conf` stem follows the
  resolved value.

## 7. Sequencing — TWO DISPATCHES, ruled 2026-08-04

**Dispatch A — resolver unification, zero churn** (§0.1). Factor the
three failure shapes out of `ShieldLibrary.resolve` and `axes.py::
resolve_axis` into one function over `(decl, selected)`, parameterised by
owner wording. **No hwmv2 semantics, no shape change, no new keys.**

Acceptance: every golden byte-identical, the whole gate green. That is
the entire point — a behaviour-preserving refactor over an unchanged
corpus is the cheapest possible proof the two resolvers really were
equivalent. If they are NOT, this dispatch is where that surfaces, on a
diff with no golden movement in it to hide behind. Correct `axes.py`'s
module docstring in the same change: it currently claims to be the only
place a selection is resolved, which is what made the duplication
invisible.

**Dispatch B — the semantics** (steps 2–4 below), after A is reviewed and
committed:

2. **Declaration shape migration** (§1, ruling (a)): `revisions:
   {default:, list:}` → `revision: {format:, default:, exact:,
   revisions: [{name:}]}` across 16 files, ids quoted as strings (§0.6i),
   `dotted-revision-no-fragment` re-authored (§0.6ii), the two
   mapping-entry fixtures retired. The authorized reject refreeze lands
   here.
3. **hwmv2 semantics** (§2, §3) in the one resolver A created, plus the
   requested/resolved model split.
4. **New coverage** (§6).

Folding A into B makes the diff unreadable — the same mistake the cutover
brief's §8.1 warns about for the banner refreeze, and the one the last
two slices each had to undo by hand.

Within B, keep the shape migration and the semantics as separate commits
even though they ship from one dispatch: step 2 churns many files and
changes no behaviour, step 3 changes behaviour and few files. A reviewer
can check each cheaply; combined, neither.
