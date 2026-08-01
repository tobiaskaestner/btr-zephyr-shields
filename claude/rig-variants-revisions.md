# Rig revisions & variants — design brief

**Status: IMPLEMENTOR-READY (readiness pass 2026-07-26). Design settled
2026-07-23 over five pushback rounds (Q4–Q9 ratified); the readiness pass
added four decisions and a slicing recommendation. START AT §"V1 —
IMPLEMENTOR-READY SPEC" below — everything after §"ROUND 3" is the round
history, kept for the why. Per-instance parameters (§"PER-INSTANCE
PARAMETERS") LANDED in `454b7c7`; V1 itself is not started.**

Settled shape in one paragraph: qualifier grammar hwmv2-exact
(`--rig name@rev/variant`, same `@rev` for `shield: name@rev`); variant =
first-class named axis = a general DELTA over the base (board and/or
sockets and/or instance substitutions — NOT board-tied); revision = the
temporal delta on the same engine, ONE family-wide stream applied after
the variant; fragments are files named by `_`-joined axes constructed
from the declared lists (never parsed); shield revisions are first-class
via native DT overlay mechanics (base `.shield` + `<name>_<rev>.shield`
in the same TU) — the migration answer to today's ad-hoc
`adafruit_2_8_tft_touch_v2` / `x_nucleo_iks01a1/2/3` folder-copying;
merge vocabulary minimal (shallow, explicit adds/removes, errors never
silent no-ops, wires by endpoint pair); default variant allowed;
diagnostics stay physically WORDED but take the `lang-*` family
(`lang-rev`/`lang-variant`, superseding Q7's `phys-*` choice — readiness
pass 2026-07-26: a delta failure describes a wrong document, not wrong
hardware).

## V1 — IMPLEMENTOR-READY SPEC (readiness pass 2026-07-26, Tobi)

Everything below is settled. Q4–Q9 were ratified 2026-07-23; the readiness
pass added the four decisions marked **NEW 2026-07-26**. Round record:
design-log 2026-07-26a. Read §"FRAGMENT FILENAMES re-derived" and
§"PER-INSTANCE PARAMETERS" alongside this — V1 inherits both.

TERMINOLOGY, never conflate: **V1 = the delta engine + revisions + shield
revisions. V2 = VARIANTS.** Variants ride the engine V1 builds; round 3
collapsed both onto one mechanism with two axes of meaning (variant =
parallel alternatives, unordered; revision = temporal evolution, ordered).
V1 must therefore build the engine so V2 is only "same engine, other axis".

### 1. Identity and selection

Grammar is hwmv2-exact (Q4): `<name>[@<rev>][/<variant>]`, e.g.
`--rig bench@2/bosch`. `list_rigs.py` ALREADY parses it
(`_RIG_TARGET_RE`, `parse_rig_target`) and currently rejects qualifiers
with a loud not-yet-supported diagnostic; V1 makes them resolve and deletes
that placeholder.

- Bare `--rig bench` selects the declared defaults; if an axis has no
  declared default, error listing that axis's declared values (Q5).
- `build-rig` passes the qualifier through untouched; `west rigs` /
  `list_rigs.py --json` gain revision/variant columns.
- **CRITICAL, and the exact trap B1 already fell into once:** every
  constructed FILENAME derives from the RESOLVED bare name plus the
  SELECTED axes — never from `${RIG}`, which now genuinely carries
  `@rev/variant`. `_rig_name` / `_RIG_RESOLVED_NAME` is the source
  (`cmake/dts.cmake`, `cmake/boards.cmake`). Both fragment kinds are
  OPTIONAL, so getting this wrong degrades to a SILENTLY unapplied
  fragment, not an error.

### 2. Declarations

`rig.yml` gains `revisions: {default:, list: []}` and
`variants: {default:, list: []}`; `shield.yml` gains the SAME `revisions:`
block (one schema, learned once). Declarations list the axes only — content
lives in fragments, so rig.yml never becomes a monolith.

### 3. Fragment files — constructed, never parsed

Q6's mechanic is the load-bearing rule: **filenames are never parsed.** The
declared axes CONSTRUCT the expected filename by `_`-joining, exactly as the
build derives `<board>_<soc>_<variant>.dts`. Names per
§"FRAGMENT FILENAMES re-derived": `<rigname>_<variant>.yml`,
`<rigname>_<rev>.yml`, `<rigname>_<variant>.overlay`,
`<rigname>_<variant>_defconfig`, `<rigname>_<rev>_defconfig`; shield side
`<name>_<rev>.shield` and `<name>_<rev>.conf` (shield convention, Tobi
2026-07-25).

Verified safe against shield discovery: a folder is a template iff it holds
`<basename>.shield`, so a revision fragment never masquerades as a template.

**Combined per-(variant, revision) fragments — DECIDED 2026-07-26, build in
V1b.** Nothing resolved `<rig>_<variant>_<rev>_*` in V1a; only single-axis
names are constructed, so a combined file would sit silently ignored. The
round-2 sketch anticipated it ("per-(variant,rev) DT, if ever needed") but
never ratified it. It belongs in V1b, where a variant can first differ in
topology and therefore have something interesting to carry per revision, and
where rule 12 already forces the per-(variant, revision) question.

**ORDER: REVISION LAST** — `<rigname>_<variant>_<rev>_defconfig`, matching
hwmv2 exactly. Established from `zephyr_build_string()`
(`zephyr/cmake/modules/extensions.cmake:1774`):

```cmake
string(JOIN "_" ${outvar} ${BUILD_STR_BOARD} ${str_segment_list} ${revision_string})
```

board → qualifiers (soc/cpucluster/variant) → revision. Confirmed against
real boards, e.g. `boards/nordic/nrf9160dk/nrf9160dk_nrf9160_ns_0_14_0.overlay`
(board, soc, variant `ns`, revision `0.14.0` last).

Note upstream DELIBERATELY does not mirror its own selection grammar, which
puts revision FIRST (`board@rev/soc/variant`) while the filename puts it
LAST. An earlier driver recommendation of revision-first — reasoning that a
filename should read like the target string — was simply wrong, and is
recorded here so it is not re-derived: upstream considered that shape and
chose the other.

**Also adopt `zephyr_build_string`'s revision normalization**
(`extensions.cmake:1772`): `string(REPLACE "." "_" ...)`, so a dotted
revision id becomes underscores in the filename (`1.2` → `1_2`). V1a's
pilot uses bare integers and never exercised this; the moment a rig declares
a dotted revision, hwmv2's own normalization is the rule to follow rather
than inventing one.

**Rule 4's collision guard must WIDEN when this lands.** Today it rejects a
variant name equal to a revision id, which suffices while each filename
carries one axis. With a combined form, a variant literally named
`variant_a_2` constructs the same filename as variant `variant_a` +
revision `2`. Q6's protection is that filenames are only ever CONSTRUCTED,
never parsed — so the hazard is not misparsing, it is two distinct
selections constructing one name. The check therefore becomes: no two
selectable (variant, revision) tuples may construct the same filename.

### 4. Resolution order, and the per-stage invariant

Base → variant delta → revision delta. ONE family-wide revision stream,
applied AFTER the variant (Q9); per-variant streams stay deferred (see
rule 12). Everything resolves in the LOADER: analyzer and emitter are
untouched, because what reaches them is an ordinary resolved rig.

**NEW 2026-07-26 — the per-stage invariant.** After EVERY delta stage, the
effective topology must satisfy the per-instance-parameter rules: every
assignment names a declared parameter, and every required parameter is
assigned. This REPLACES an earlier proposal to forbid revisions from
changing the parameter set. Reasoning: deltas never "add parameters" at all
— shields DECLARE them, rigs ASSIGN them — so a parameter set changes only
as a consequence of a shield change, and a revision swapping a shield is
Q7's own motivating example. Note a shield REVISION can change the set too:
`<name>_<rev>.shield` is a DT overlay, so rev 2 can author a default where
the base had none (required → optional) or add a device with
`shield,params` and no default (a NEW required parameter). The invariant
covers all three sources uniformly, with no special rule.

**Shield revisions use no YAML vocabulary at all.** Shields are DT
templates, so they get native mechanics: base `<name>.shield` plus
`<name>_<rev>.shield` cpp-included after it into the SAME translation unit,
and DT's own overlay-by-label semantics do the merging. An instance selects
one with `shield: <name>@<rev>` (the identical `@rev` grammar).

### 5. Merge vocabulary (Q7, plus the 2026-07-26 amendments)

One grammar for both fragment kinds. **No deep merges anywhere** — the
deepest merge unit is an instance's top-level key.

| key | semantics |
|---|---|
| `board:` | VARIANT fragments only; a revision carrying it is an error |
| `sockets:` | variant only; per-key replace into the base map |
| `instances:` | matched by `name` against the EFFECTIVE topology; given keys shallow-replace, unspecified keys inherit; **no match = error** (additions are never implicit) |
| `add-instances:` | full declarations; the name must NOT already exist |
| `remove-instances:` | names must exist |
| `add-wires:` / `remove-wires:` | matched by endpoint pair; a re-route is remove+add, no "replace" |
| `dt-includes:` | **NEW 2026-07-26: UNIONS, does not replace** |

**`dt-includes:` unions** — the one key with union semantics, stated
explicitly rather than left to inference. A vocabulary is additive by
nature and there is no meaningful reason to REMOVE a header; a variant
substituting a different shield legitimately needs a vocabulary the base
never declared.

**`params:` replaces WHOLESALE, plus a restate-check — NEW 2026-07-26.**
Wholesale replace is not merely acceptable, it is REQUIRED: when a delta
changes an instance's `shield`, the base's assignments are keyed to devices
the new shield does not have, so merging them would produce errors for a
correctly written delta. The hazard is narrow and real: same shield +
previously-assigned OPTIONAL parameter + delta omitting it = a silent
revert to the shield default. So:

> if a delta supplies `params` for an instance whose `shield` it does NOT
> change, it must restate every property the effective topology had
> assigned; omitting one is an error naming that property.

Merge semantics stay uniform; only the CHECK is context-aware, which is far
easier to reason about than context-dependent merging. A deep-merge
exception for `params` was rejected: it would need a `remove-params` verb,
and "no deep merges anywhere" would stop being true.

### 6. Validation rules — all loud, all `lang-*`

**NEW 2026-07-26: the family is `lang-*`, NOT `phys-*`** — superseding
Q7's `phys-rev`/`phys-variant`. Evidence: the codes in use split cleanly
into `lang-*` for authoring/declaration/schema errors (17 codes) and
`phys-*` for physical conflicts (13). Every delta failure describes a wrong
DOCUMENT, not wrong hardware; physical errors still occur, but AFTER
resolution, on the resolved topology, under their existing `phys-*` codes.
Q7's "physically worded" rule is about PHRASING and survives untouched:
"rev 2 removes instance th2, which variant frdm does not have" stays
exactly that sentence, under a `lang-rev` code.

Codes: `lang-rev`, `lang-variant`, plus P's existing `lang-param` /
`lang-dt-include`.

1. `@rev` names a revision not in the declared list — `lang-rev`
2. `/variant` names an undeclared variant — `lang-variant`
3. bare name, axis has values but no declared default — name the axis and
   list its values (Q5)
4. a variant name equals a declared revision id — the constructed
   filenames would collide (Q6) — `lang-variant`
5. a revision fragment carrying `board:` or `sockets:` — variant-only keys
6. an `instances:` delta naming an instance the effective topology lacks
7. `add-instances:` naming an existing instance
8. `remove-instances:` naming an absent instance — if a variant already
   removed it, the message NAMES the variant, so drift cannot hide
9. `remove-wires:` naming an endpoint pair that does not exist
10. a selected **NON-DEFAULT** axis value whose constructed fragment files
    do not exist — name the files that were looked for. **CORRECTED
    2026-07-26 during V1a** (`5031a0f`): as first written this required
    EVERY declared value to contribute, default included, which is wrong
    three ways — it contradicts the base+layered-fragments model of §3, it
    has no hwmv2 precedent (boards have `<board>.dts` and
    `<board>_<variant>.dts`, never a `<board>_<default>.dts`), and it makes
    declaring an axis on an existing rig a BREAKING change until a fragment
    describing what the rig already is gets authored. The declared default
    is exempt: it MAY carry a fragment, it just must not be required to.
    Evidence the original was wrong — the rule-4 collision fixture was
    emitting two spurious rule-10 errors for its own default variant and
    revision.
11. the `params` restate-check of §5 — `lang-param`
12. **NEW 2026-07-26:** a family-wide revision whose `params` names a
    device the POST-VARIANT topology does not have — error naming the
    variant. This is unavoidable by construction: under variant `hpm` the
    delta must say `hpm_dev`, under `bosch` `bme_dev`, and one fragment
    cannot serve both. Q9's instance-name-stability convention does not
    rescue it, because the collision is at device-label and parameter-name
    level inside third-party shields. **Per-variant revision streams
    (`<rigname>_<variant>_<rev>.yml`) are the recorded escape hatch** —
    Q9 deferred them "until a real case", and this is that case. Do NOT
    build them in V1; validate and name the limitation.
13. `shield: <name>@<rev>` naming a revision `shield.yml` does not
    declare — `lang-rev`

### 7. Provenance and plumbing

- `context.cmake` carries the SELECTED revision and variant.
- `build_info` gains `revision` and `variant` under
  `cmake.vendor-specific.rig.*` — prefix-free, per the key convention
  settled in `76b45cf`, and the applied fragment list alongside them.
- `RIG_DEPENDS` must include every applied fragment, so editing one
  retriggers configure (the existing depfile handoff).

### 8. Model additions

The freeze is lifted (P), under "a model change requires a recorded design
decision" — this section is that record. Add the axis declarations and the
selected revision/variant to the rig model. Analyzer and emitter get no
changes at all; if a change appears necessary there, the delta engine has
leaked out of the loader — stop and report.

### 9. Golden budget (Q8, extended)

Pilot = a NEW rig family; existing corpus rows stay frozen and untouched.
Base + 1 variant + rev 2 (a sensor swap) → 4 accept tuples
(`base@1`, `variant@1`, `base@2`, `variant@2`), each with tier-1 AND
tier-2 goldens. Synthetic tier-1 rejects, one per new failure mode:
unknown variant, unknown revision, variant-name/revision-id collision,
delta naming an unknown instance, the `params` restate-check, and the
family-wide-crossing-variant case of rule 12. Shield revisions ride at
ZERO churn: give one corpus shield a rev 2 whose default stays rev 1, so
every existing row is untouched by construction, plus one new accept tuple
exercising `shield: <name>@2`.

### 10. Slicing recommendation (driver)

V1 is the largest slice on the board; three sub-slices, each with its own
report and commit:

- **V1a — selection and collection.** Qualifier resolution end to end
  (`list_rigs.py`, `west rigs`, `build-rig`, the cmake forks), the
  declaration blocks, fragment-name construction and discovery, provenance.
  NO deltas yet: a selected axis whose fragment only supplies
  `.overlay`/`_defconfig` files is already useful and fully testable.
- **V1b — the delta engine.** The merge vocabulary, the resolution order,
  the per-stage invariant, rules 5–12, PLUS the combined per-(variant,
  revision) fragment of §3 (revision LAST, hwmv2 order), hwmv2's revision
  dot-normalization, and the widened rule-4 collision guard those require.
- **V1c — shield revisions.** The DT side, `shield: <name>@<rev>`, rule 13.

Slice A's deferred half (analyzer diagnostics sourcing controller identity
independently of the emitter, needing `model.BoardSocket.pwm_map` widened)
can ride V1b, which is already in the model.

## ROUND 3 — variants generalized beyond board substitution (Tobi)

Pushback: "variants are not exclusively tied to different boards … they can
also provide different shields with similar functionality or use different
shield versions."

**The convergence this forces (and the simplification it buys):** a variant
is now a general DELTA over the base topology — board and/or socket map
and/or instance substitutions. But that is exactly what a REVISION is
mechanically. So the design collapses to ONE delta/merge mechanism with two
axes of meaning:

- **variant** = parallel alternatives (siblings; unordered; "the honeywell
  build vs the bosch build", "the nucleo deployment vs the frdm one")
- **revision** = temporal evolution (ordered; "rev 2 replaced the sensor")

One merge vocabulary (the round-2 Q7 one — instance-name-keyed replace,
add-instances / remove-instances, wires by endpoint) powers both. The
loader resolves base → variant delta → revision delta into a PLAIN rig;
analyzer/emitter stay untouched. Sequencing bonus: building the delta
engine for revisions first (as already planned) now de-risks variants for
free — variants become "the same engine, different axis + file naming".

**Variant fragment can express** (all optional, any combination):
```yaml
# rigs/datalogger/rig_honeywell.yml — a variant fragment
board: nucleo_f401re_btr        # optional — omit to inherit base board
sockets: {ard: nucleo_ard}      # optional — abstract->label map
instances:                       # instance deltas, matched by name
  - {name: sensor, shield: honeywell_hpm}   # different shield, same slot
```

**Shield revisions — FIRST-CLASS (round 4, Tobi's pushback REVERSING the
round-3 parking recommendation).** Ground truth verified in the tree:
upstream has NO software mechanism for shield revisions (shields.cmake /
list_shields.py / shield.yml — nothing), but the phenomenon exists today
as ad-hoc name encoding: `adafruit_2_8_tft_touch_v2`, and
`x_nucleo_iks01a1/a2/a3` = three hardware generations as three
near-duplicate shield folders. The rigs model is the migration target for
exactly these, so it must represent them properly, not perpetuate the
folder-copying:

- **shield.yml gains the SAME `revisions:` block** as rig.yml (one schema,
  learned once): `revisions: {default: …, list: […]}`.
- **Mechanics**: shields are DT templates, so they get TRUE hwmv2
  mechanics — base `<name>.shield` + per-revision DT fragment
  (`<name>_<rev>.shield` naming TBD with Q6) cpp-included after the base
  into the same TU; DT's native overlay-by-label semantics do the merging,
  no YAML merge vocabulary needed on the shield side. Per-revision
  `.conf` analogously.
- **Reference syntax**: an instance says `shield: <name>@<rev>` — the
  identical `@rev` grammar as rigs and boards (Q4, ratified hwmv2-exact).
- **Composition with variants**: variant substitution covers "similar
  functionality, DIFFERENT shield"; `@rev` covers "same shield, different
  hardware generation"; they compose (a variant fragment may substitute
  `shield: x@2`).
- **Migration story**: existing `_v2`-style names keep working unchanged
  (a name is a name); families like iks01a1/2/3 can consolidate into one
  template with three revisions when ported to rig shields.

**Declaration shape (uniform)**: rig.yml lists the axes only; content
lives in fragments — `variants: {default: …, list: [nucleo, frdm,
honeywell]}` + `rig_<variant>.yml` per variant; revisions analogously
(file naming = Q6, still open). Keeps rig.yml from becoming a monolith and
mirrors the hwmv2 file-per-target feel Tobi asked for.

**New question Q9 — revision × variant interaction**: does a revision
apply family-wide (base-level delta, applied after whichever variant; rev
numbering shared across variants — RECOMMENDED start) or can a variant
have its own revision stream (`rig_nucleo_2.yml` — defer until needed)?
Merge-by-instance-name makes family-wide revs work even when a variant
substituted the instance's shield, as long as names are stable — worth
stating as a naming convention in conventions.md when this lands.

---

Everything below is the ROUND 2 record (grammar/Q4-Q8 still open except
where round 3 supersedes: the variant block is now a general delta, not
just {board, sockets}).

## Ratified direction (Tobi, 2026-07-23)

Model this CLOSELY on hwmv2 board notation and mechanics:

- **Selection grammar**: qualifier path on the rig id — Tobi's example
  `--rig my-rig/variant@rev2`. Variant is a FIRST-CLASS NAMED AXIS (not
  merely implied by board choice) — which also cleanly admits two variants
  on the SAME board (different socket assignments), previously deferred.
- **Mechanics borrowing**: like `board.dts` / `board_variant.dts` /
  `<board>_<rev>.overlay`, rig folders carry base files + per-variant /
  per-revision files layered on top, rather than one monolithic rig.yml.
- Still design-first: this brief is the deliverable for now.

## Sketch (round 2)

### Identity & grammar

`<rig-name>[/<variant>][@<rev>]` (Tobi's ordering), or hwmv2-exact
`<rig-name>[@<rev>][/<variant>]` (boards put `@rev` on the base name:
`nucleo_f401re@B/stm32f401xe`). With a single qualifier axis both parse
unambiguously — **Q4: pick one.** Recommendation: mirror hwmv2 exactly
(`my-rig@rev2/nucleo`) purely for `-b` muscle memory; accept Tobi's
ordering if he prefers the variant reading first.

`west build-rig --rig datalogger/nucleo@2` — note the UX win: the variant
block names its board, so build-rig's board inference KEEPS working with
variants (no `--board` needed, unlike round 1's proposal).

### rig.yml declarations (the board.yml analogue)

```yaml
rig:
  name: datalogger
  revisions:            # hwmv2-style; exact match first, nearest deferred
    default: 1
    list: [1, 2]
  variants:
    default: nucleo     # Q5: allow a default variant? (boards: yes-ish)
    list:
      - name: nucleo
        board: nucleo_f401re_btr
        sockets: {ard: nucleo_ard}     # abstract -> board label
      - name: frdm
        board: frdm_k64f_btr
        sockets: {ard: frdm_ard}
  instances:
    - name: logger
      shield: adafruit_data_logger
      socket: ard        # ABSTRACT name, resolved via the variant map
```

Round-1 Q1 resolves as: variant blocks own the socket maps (option (a)),
with abstract socket names in instances. Single-variant rigs keep writing
raw labels (abstract==label degenerate case) — the existing corpus parses
unchanged. Type-based matching (`type: arduino-r3`) demoted to possible
later sugar, not load-bearing.

### File layout (hwmv2-flavored, flat — replaces round 1's boards/ dir)

```
rigs/datalogger/
  rig.yml                  # base topology + revisions/variants declarations
  rig.conf                 # common Kconfig
  rig.overlay              # common DT (rare once variants exist — see note)
  rig_nucleo.conf          # per-variant Kconfig     (board_variant analogue)
  rig_nucleo.overlay       # per-variant DT — the pinmux home (R21):
                           #   inherently board-specific, so overlays mostly
                           #   live at variant level, not common level
  rig_2.yml                # revision-2 topology DELTA on the base (Q6 naming)
  rig_nucleo_2.overlay     # per-(variant,rev) DT, if ever needed (defer?)
```

Apply order mirrors zephyr's layering: base → variant → revision (most
specific last). rig.cmake's existing collection loop extends naturally;
the SELECTED (variant, rev) and the applied file list go into
context.cmake + the build_info rig provenance block.

### Revision semantics (round-1 Q3 revised)

Borrow "overlay on top of base" rather than full copies: `rig_<rev>.yml`
is a DELTA with a deliberately MINIMAL merge spec — not a general patch
language:
- instances match by `name`; a matched instance's keys shallow-replace;
- `add-instances:` / `remove-instances: [names]` for topology growth;
- wires likewise by endpoint pair.
Diagnostics must stay physically worded ("rev 2 removes instance 'th2',
which rev 1 does not define — [phys-rev]"-family). **Q7: is this merge
vocabulary sufficient for the real evolution cases Tobi has in mind
(sensor swap, wire move, shield add), or do wires need names?**

### Mechanics touched (unchanged from round 1 unless noted)

- `-DRIG` parsing + `list_rigs.py` / `west rigs` gain qualifier columns;
  bare `--rig datalogger` with variants and no default → error listing
  the declared variants (mirrors zephyr's board-qualifier error).
- Goldens: corpus rows become (rig, variant, rev) tuples; each shipped
  tuple gets tier-1 (+tier-2 if accept) goldens. **Q8: which tuples for
  the first corpus rig — one rig × 2 variants × 2 revs = 4 rows?**
- Expander: qualifier resolution + variant socket-map substitution +
  revision merge happen in the LOADER (before analysis), so the analyzer/
  emitter stay untouched — the resolved topology is an ordinary rig.
- build-rig: parse the qualifier off `--rig` before rig-name matching.

## Question status (round 4)

- **Q4 — RATIFIED (Tobi): hwmv2-exact.** `<name>[@<rev>][/<variant>]`,
  e.g. `--rig datalogger@2/nucleo`. Same grammar for shield references
  (`shield: <name>@<rev>`).
- **Q5 — RATIFIED (Tobi): default variant allowed.** Bare
  `--rig datalogger` builds the declared default; error listing variants
  only when no default is declared.
- **Q6 — RATIFIED (Tobi): upstream nomenclature, `_` separates the axes.**
  `rig_<variant>.yml` / `rig_<rev>.yml` (+ `rig_<variant>.overlay/.conf`),
  shield revisions `<name>_<rev>.shield` (safe with the discovery glob —
  a folder is a template iff it holds `<basename>.shield`; the revision
  fragment never matches). KEY MECHANIC (how hwmv2 dodges underscore
  ambiguity, mirrored here): filenames are NEVER parsed — the declared
  axes in rig.yml/shield.yml CONSTRUCT the expected filename by joining
  with `_` (exactly how the build derives `<board>_<soc>_<variant>.dts`).
  One validation rule follows: a variant name must not equal any declared
  revision identifier (else the constructed names collide) — enforced in
  the loader with a physically-worded diagnostic.
- **Q9 — RATIFIED (Tobi, 2026-07-23): family-wide revision streams.** One
  revision stream per rig, applied AFTER the variant delta; per-variant
  streams deferred until a real case. Naming convention to conventions.md:
  instance names stay stable across substitutions (that is what makes
  family-wide revs compose with variant shield swaps).

## Q7 — the merge vocabulary (ROUND 5 PROPOSAL, for pushback)

Rig-side only (shield revisions merge via native DT overlay semantics).
One grammar for BOTH fragment kinds; application order
base → variant → revision, each stage validating against the topology
effective at that point. **No deep merges anywhere** — the deepest merge
unit is an instance's top-level key.

Fragment keys (all optional):
- `board:` — VARIANT fragments only (a revision that changes the board is
  a new rig/variant, not an evolution; revision fragments carrying
  `board:` are rejected with a physically-worded diagnostic).
- `sockets:` — variant fragments only (abstract→label is board-tied);
  per-key replace into the base map.
- `instances:` — list of deltas matched by `name` against the EFFECTIVE
  topology. Match found → the given keys shallow-replace (shield, socket,
  …); unspecified keys inherit. Match NOT found → error (typo
  protection): additions are never implicit.
- `add-instances:` — full instance declarations; name must NOT exist.
- `remove-instances: [names]` — names must exist (a family-wide rev
  removing an instance a variant already removed → error naming the
  variant, so silent no-ops can't hide drift).
- `add-wires:` / `remove-wires:` (matched by endpoint pair) — a re-route
  is remove+add; no wire "replace" (keeps the vocabulary minimal; a wire
  has no stable identity beyond its endpoints).

Diagnostics family: `phys-rev` / `phys-variant` (wording physical:
"rev 2 removes instance 'th2', which variant 'frdm' does not have").

## Q8 — golden budget (ROUND 5 PROPOSAL)

Pilot = a NEW rig family (existing corpus rows stay frozen untouched):
base + 1 variant + rev 2 (sensor-shield swap) → 4 accept tuples
(base@1, variant@1, base@2, variant@2), each with tier-1 AND tier-2
goldens (~5s/row tier-2 — cheap). Plus 4 synthetic tier-1 rejects for the
new failure modes: unknown variant, unknown revision, variant-name ==
revision-id collision, rev-delta naming an unknown instance. Shield
revisions ride the same slice at zero churn: give one corpus shield a
rev 2 whose default stays rev 1 → every existing golden row is untouched
by construction, and one new accept tuple exercises `shield: <name>@2`.

## FRAGMENT FILENAMES re-derived under the B1 rename (2026-07-25)

The B1 naming ruling (design-log 2026-07-25e) invalidates the FILENAMES in
the round-2 layout sketch above (`rig.conf`, `rig.overlay`,
`rig_<variant>.conf/.overlay`, `rig_2.yml`). **Q6's MECHANIC is untouched
and still governs**: filenames are NEVER parsed — the declared axes in
rig.yml/shield.yml CONSTRUCT the expected filename by `_`-joining, exactly
as the build derives `<board>_<soc>_<variant>.dts`. Only the prefix moves,
from the literal `rig` to the rig's own name.

The board analogy resolves the apparent inconsistency of `rig.yml` staying
unprefixed: boards do exactly the same split — `board.yml` is UNPREFIXED
metadata while content files are name-prefixed (`<board>.dts`,
`<board>_defconfig`). Shields likewise carry an unprefixed `shield.yml`.

| role | rig | board | shield |
|---|---|---|---|
| identity + axis declarations | `rig.yml` | `board.yml` | `shield.yml` |
| base content | `rig.yml` topology → `rig-gen.overlay` | `<board>.dts` | `<name>.shield` |
| hand-authored DT escape hatch | `<rigname>.overlay` | — (the `.dts` IS authored DT) | — (the `.shield` IS authored DT) |
| base Kconfig fragment | `<rigname>_defconfig` | `<board>_defconfig` | **`<name>.conf`** |
| Kconfig symbols / defaults | `Kconfig.rig` (parked) | `Kconfig.<board>` + `Kconfig.defconfig` | `Kconfig.shield` + `Kconfig.defconfig` |
| per-variant topology delta | `<rigname>_<variant>.yml` | — | — |
| per-variant DT | `<rigname>_<variant>.overlay` | `<board>_<variant>.dts` | ad-hoc only: `x_nucleo_iks01a2_shub.overlay` |
| per-variant Kconfig | `<rigname>_<variant>_defconfig` | `<board>_<variant>_defconfig` | — |
| per-revision content | `<rigname>_<rev>.yml` | revision files/dirs | `<name>_<rev>.shield` (Q6) |
| per-revision Kconfig | `<rigname>_<rev>_defconfig` | `<board>_<rev>_defconfig` | **`<name>_<rev>.conf`** |
| board-specific fragments | — (the variant owns the board) | — | `boards/<board>.overlay` + `boards/<board>.conf` |

**DECIDED (Tobi, 2026-07-25): shield revision Kconfig fragments follow the
SHIELD convention — `<name>_<rev>.conf`, not `_defconfig`.** Rigs follow
the BOARD convention because a rig OWNS a board; a shield merely attaches
to one. The rig column above is the mechanical consequence of the B1
ruling and Q6's construct-don't-parse rule; Tobi has seen this table.

Two rows carry their own notes into the V1 round:
- **The per-variant topology delta is the one genuinely rig-only row**,
  because rig topology lives in YAML while boards and shields express
  theirs in DT and get layering free from cpp/overlay semantics. That is
  also why the shield side needs no merge vocabulary at all (Q7 is
  rig-side only).
- **`Kconfig.rig` is where true defconfig PRECEDENCE could live later.**
  Both boards and shields pair their fragment with `Kconfig.defconfig`
  for Kconfig-LEVEL defaults. Tobi's withdrawn precedence change
  (design-log 2026-07-25g) belongs there if it is ever revisited — it
  needs no merge-order change, so it does not disturb the application
  overlay machinery that C' deliberately left alone.

## PER-INSTANCE PARAMETERS — DESIGN SETTLED (2026-07-25, Tobi)

Two pushback rounds; the round's record is in design-log 2026-07-25h. Settled
shape in one paragraph: a shield DECLARES parameterizable properties per
device node with `shield,params`, where the property's PRESENCE in the
template is its default and its ABSENCE means the rig MUST assign it; a rig
ASSIGNS per instance under `params:`, keyed by device label then property;
a rig declares the token vocabularies it draws on in `dt-includes:`, so
rig.yml is self-explanatory the way a `.shield`'s own `#include` lines make
it self-explanatory; the LOADER resolves assigned tokens against exactly
those headers (validation, and the number the config sheet renders) while
the EMITTER emits the symbol VERBATIM, so `rig-gen.overlay` and the goldens
stay readable; and a fourth generated artifact carries the declared
`#include` lines so those symbols resolve in pass 2.

### Declaration — shield side, in the `.shield` template

```
gb_key: button {
        shield,collect = "gpio-keys";
        shield,params = "zephyr,code";      /* required: no default authored */
        gpios = <&gb_plug GROVE_SIG0 (GPIO_PULL_DOWN | GPIO_ACTIVE_HIGH)>;
};
```

- `shield,params` is a DT **string list**, so one node declares as many
  properties as it needs; each node carries its own annotation, because the
  declaration sits with the properties it governs. This is why the in-DT
  form was chosen over a `shield.yml parameters:` block: co-location means
  the declaration cannot drift from its target, and a typo'd property name
  is checkable against the node itself.
- **Presence/absence carries required-vs-optional** — one vocabulary, no
  `required:` flag: property authored on the node → that value is the
  DEFAULT and the rig may override it; property absent → the parameter is
  REQUIRED and a rig that omits it is a loader error. This is what stops the
  template from lying: a keycode, a `zephyr,chosen` selection, an alias —
  these can only be known at rig level, so the shield authors no value.
- One rig-level value never feeds several properties or nodes. The rig
  assigns twice, explicitly (Q7's minimal-vocabulary rule). Revisit only
  against a real case; do not invent aliasing.
- `shield,params` joins `_MODEL_PROPS` in `shields.py:24` so the annotation
  is stripped from emission, exactly like `shield,collect`.
- Naming follows the established entity-scoped convention
  (`shield,plugs` / `shield,collect` / `shield,addr-from` / `shield,domain`).

### Assignment + vocabulary — rig side, in rig.yml

```yaml
rig:
  name: lotus_buttons
  board: seeeduino_lotus/samd21g18a/rig
  dt-includes:
    - zephyr/dt-bindings/input/input-event-codes.h
  instances:
    - name: btn_start
      shield: grove_btn
      socket: grove_d2
      params:
        gb_key:
          zephyr,code: INPUT_KEY_0
    - name: btn_stop
      shield: grove_btn
      socket: grove_d6
      params:
        gb_key:
          zephyr,code: INPUT_KEY_1
```

**BLOCK style is required, and this is not cosmetic** (found while
implementing, 2026-07-25): an earlier draft of this section showed
`params: {gb_key: {zephyr,code: INPUT_KEY_0}}`, which does NOT parse as
intended — PyYAML splits the unquoted comma inside a FLOW mapping, yielding
`{zephyr: None, code: INPUT_KEY_0}`, silently. Block style parses correctly
and matches the corpus's existing convention (`pin:` is always block style).
Flow style would need the property name quoted (`{"zephyr,code": ...}`).
Mitigation already in place: the mistake fails LOUDLY rather than emitting
garbage — the two bogus keys are undeclared parameters, so rule 1 fires.

- **`params:`** is keyed by the shield-local DEVICE LABEL, then by property
  name — the same addressing style `pins:`/`jumpers:` already use.
- **`dt-includes:`** answers "where does `INPUT_KEY_1` come from?" — the
  concern that killed a vocabulary-free design (Tobi, 2026-07-25). The rig
  author writes the include they would have written in DTS. Integer literals
  need no declaration. **Do NOT name this key `includes:`** — V1 also
  introduces rig FRAGMENT inclusion (`<rigname>_<variant>.yml`), and a bare
  `includes:` reads as fragment inclusion to anyone skimming.
- Resolution happens in a synthetic TU built from exactly the declared
  headers, using the include dirs the expander already receives
  (`--include-dir`). It is NOT injected into a shield's TU: the vocabulary
  is a RIG declaration, so it gets its own TU and the resolution has a clean
  story.
- **Merge behaviour (Q7 holds, no exception): `params:` is an instance
  top-level key, so a variant/revision delta specifying `params` REPLACES
  it wholesale.** A revision changing one keycode restates that instance's
  parameters. Coarse but consistent with "no deep merges anywhere"; revisit
  only if it bites in practice — do not introduce a silent deep-merge.

### Emission + the fourth generated artifact

- The emitter emits the assigned token **verbatim**
  (`zephyr,code = <INPUT_KEY_1>;`), for diagnostic readability in the
  overlay and in tier-1 goldens (Tobi's requirement).
- Shield-authored defaults arrive at the loader already cpp-resolved to
  numbers, so the ONLY symbols a generated overlay can contain are
  rig-assigned ones — which is why the collector needs nothing but the
  rig's own `dt-includes`.
- **New generated artifact: `rig-gen-includes.dtsi`** (DECIDED, Tobi
  2026-07-25, choosing it over a `rig-gen-includes.overlay`) — nothing but
  the declared `#include` lines. It is **NOT** an entry in
  `EXTRA_DTC_OVERLAY_FILE`; instead `rig-gen.overlay` opens with
  `#include "rig-gen-includes.dtsi"`, and both files sit in
  `<build>/rig/`. Why this form won: a QUOTED include resolves relative to
  the directory of the file containing the directive, so it needs no `-I`
  plumbing, no ordering constraint, no extra overlay-list entry, no
  `EXISTS` guard in `dts.cmake`, and no build_info key — where the
  `.overlay` form needs every one of those plus a guarantee it is
  prepended first. The dependency is also visible in the file that has it,
  rather than living as an invisible ordering contract in cmake.
- **CAVEAT TO PROVE BEFORE RELYING ON IT:** `rig-gen.overlay` reaches cpp
  via `-include <abs-path>`, and GCC documents `-include` as searching the
  PREPROCESSOR'S WORKING DIRECTORY first for that file. The nested quoted
  include is expected to still resolve against the including file's own
  directory (standard quoted-include behaviour), but the implementor must
  confirm this with a real build, not assume it. If it does not hold, the
  fallback is `-I<out-dir>` via `DTS_EXTRA_CPPFLAGS`, or the
  `.overlay` form with its prepend ordering.
- Vocabulary REACH is the same either way, and is worth documenting
  deliberately so it is intentional rather than discovered: VERIFIED
  (2026-07-25) `zephyr_dt_preprocess` passes every overlay to ONE cpp run
  as `-include <file>` (`extensions.cmake:4910-4911`), so all overlays
  share a single translation unit and cpp defines persist across it — the
  hand-authored `<rigname>.overlay` (which today must include its own
  headers for R21 pinmux) and app overlays therefore see the rig's declared
  vocabulary too.
- **Emit it only when `dt-includes` is non-empty** (and emit the
  `#include` line in `rig-gen.overlay` only then). Consequence worth
  having: the 12 corpus rigs that declare nothing gain no file, no include
  line, and zero golden churn.
- The **config sheet** (the human-facing output) grows a parameter table:
  instance, device, property, symbol, resolved value — `INPUT_KEY_1 (12)`.
  Discoverability lands in the artifact that exists to be read.

### Validation — every rule loud, in the `lang-*` family

Parameter errors are DECLARATION/ASSIGNMENT errors, not physics, so they
take the `lang-*` family (`lang-parse`/`lang-schema`/`lang-prop`/
`lang-instance-shield` precedent), NOT `phys-*` (which is for physical
conflicts). Proposed codes `lang-param` and `lang-dt-include`:

1. a `params:` entry naming a property the device did NOT declare → error
   (typo protection; declaration is what makes typos loud)
2. a declared-and-absent (REQUIRED) parameter left unassigned → error
   naming the shield, device and property
3. a `params:` entry naming an unknown device label → error
4. a token that does not resolve against the declared headers → error
   naming the fix ("add the defining header to rig.yml `dt-includes:`")
5. a token used with `dt-includes` empty/absent → same code, hint that
   nothing is declared
6. a `dt-includes` header not found on the include path → error at expand
   time, naming the searched dirs

**Explicitly OUT OF SCOPE (Tobi, 2026-07-25: overengineering for now):**
per-parameter vocabulary/range checking, i.e. rejecting `GPIO_PULL_DOWN`
assigned to `zephyr,code` because it resolves in the wrong vocabulary. A
token that resolves is accepted. Recorded so the gap is known, not
forgotten: genuine type checking belongs to the binding layer, where
`zephyr,code` already carries a type.

### model.py — the freeze is LIFTED for this slice

Saferail 9 froze `model.py` for Bridge-A; Bridge-A is complete, and V1 needs
genuine model additions. Lift it formally, replacing the blanket ban with:
**a model change requires a recorded design decision** (design-log line),
so discipline survives without a freeze. Additions:

- `Instance.params: dict[str, dict[str, str]]` — device label → property →
  raw value TEXT (text, because emission is verbatim), plus
  `Instance.param_refs` for `file:line` in diagnostics
- the device model gains its declared parameter names (from `shield,params`)
- rig level gains `dt_includes: list[str]` (+ refs)

`invert:` STAYS a separate instance-level flag transform and does NOT become
the mechanism's first client — contrary to the 2026-07-24 direction note.
Reason: it is not a property assignment. The emitter XORs `0x1` across ALL
of the instance's gpio flags (`emitter.py:176,235`); describing that as
"assign property P on node N" would be false. Parameters = property VALUES;
`invert` = a flag transform. Revisit only if a second transform appears.

### Slice scope + golden budget

- Fix the trigger bug AT ITS ROOT in the same slice: drop `grove_btn`'s
  type-level `zephyr,code = <INPUT_KEY_0>`, declare it required, and give
  `lotus_buttons`' two buttons distinct keycodes. Tier-1 AND tier-2 refreeze
  for that rig, justified as the bug fix (today both buttons emit
  `zephyr,code = <11>` — see the golden).
- Also fix `grove_btn.shield`'s "Currently INERT here" comment, which is
  STALE: the property has reached the overlay since `afe5857`, as the
  goldens prove. (Parked note said "fix it with whichever change touches the
  file first" — this is that change.)
- New synthetic tier-1 rejects, one per rule: undeclared property (1),
  unassigned required parameter (2), unknown device label (3), unresolvable
  token (4).
- Zero churn for the other 12 corpus rigs, by construction (no declared
  parameters, no `dt-includes`, no collector artifact).

---

## Trigger + rejected alternative (record, 2026-07-24)

Trigger: `grove_btn.shield` encodes `zephyr,code = <INPUT_KEY_0>` at TYPE
level; a keycode is an INSTANCE fact. Live bug since `afe5857` made
collection-entry passthrough real: both lotus-buttons buttons get
INPUT_KEY_0. (That file's "currently INERT" comment is stale — fix it with
whichever change touches the file first.)

`rig.overlay` was considered and REJECTED as the modeling answer (agreed
2026-07-24): it couples the rig author to emitter-generated node names, its
failure modes are silent (typo'd path creates a fresh node) or cryptic
(missing prop → DT_PROP compile error in input_gpio_keys.c, not a loader
diagnostic), and it violates rig.overlay's scoping to DT the expander
CANNOT author (R21 pinmux). Acceptable only as TODO-marked scaffolding in
lotus-buttons if corpus correctness is wanted pre-V1.

Direction (agreed, NOT yet a settled design — design it IN the V1 round so
it shares the merge grammar, one vocabulary not two dialects):

- Generalize `invert:`: the shield DECLARES the parameter (required/optional
  + which property on which inner node it lands on), rig.yml ASSIGNS it per
  instance, the LOADER validates loudly (declaration is what makes typos
  loud — an undeclared property would emit an untyped DT prop, which edtlib
  treats as inert: the worst silent no-op), the EMITTER emits the symbolic
  token verbatim (pass-2 cpp resolves it via the shield TU's own includes —
  the YAML loader never needs the header).
- `invert:` becomes the first client of the general mechanism, or is
  explicitly grandfathered — decide in the round.
- Prerequisite: formally lift the model.py freeze (saferail 9 was a
  Bridge-A rail; Bridge-A is complete; an instance-param field is a genuine
  model addition V1 needs anyway).

## Superseded (round 1)

Round 1 proposed variant=board-selection (no named axis), a shields-style
`boards/` subdir, and full-copy revisions — all replaced above per the
ratified direction. Kept in git history.
