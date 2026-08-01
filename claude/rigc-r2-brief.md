# Slice brief — R2: the loader proper (documents, axes, delta engine)

Drafted 2026-07-29 by the driver, from `rigc-mission-brief.md` (§2 contract,
§4 arc, §5 definitions, §6 design rules), the R1 precedent
(`rigc-r1-brief.md` + its post-ratification naming amendment), a fresh
census of the frozen goldens at btr-shields `ecc3058`, and
`board-as-invocation-coordinate.md` §6 (the SocketBinding seam).
**RATIFIED by Tobi 2026-07-29** — all four flagged rulings accepted as
written (ShieldRef seam; the no-golden hand-differential rule, now
standing discipline; the 19-target list; implementor on sonnet, reviewer
on opus).

## Goal

By slice end, rigc's loader handles the full rig-side document surface —
rig.yml metadata shapes, qualifier axes with S2 mapping entries, the
required content file, fragment discovery, and the V1b delta engine — and
**19 named reject goldens flip green** under `RIG_EXPAND_COMPILE=rigc`,
taking the differential meter from 45/146 to an expected **64/146** (23 of
48 rejects). Everything needing the shield library, cpp/headers, or board
reading stays a loud exit-3 refusal — R3+ territory.

## 0. The target set, from the census (2026-07-29, all verified
single-error, zero `params:`/`pin:` usage)

| family | fixtures |
|---|---|
| lang-schema (6) | `board-declared-twice`, `no-board-declared`, `variant-board-partial`, `sockets-with-variant-board`, `revision-mapping-entry`, `route-no-via` |
| lang-rev, rig axis (3) | `unknown-revision`, `dotted-revision-no-fragment`, `remove-instance-drift` |
| lang-variant (10) | `unknown-variant`, `no-such-axis`, `no-default-variant`, `variant-no-fragment`, `variant-board-restated`, `variant-revision-collision`, `combined-fragment-collision`, `add-instances-already-exists`, `instances-delta-unknown-instance`, `remove-wire-missing` |

The four R1 flips (`missing-content-file`, `content-file-carries-board`,
`content-file-carries-sockets`, `revision-carries-board`) must SURVIVE the
rewrite of the R1 sliver into the full loader — they are acceptance
criteria too, not grandfathered.

NOT R2, deliberately (each needs parsed shields, headers, or boards):
lang-param (6), lang-dt-include (3), shield-side lang-rev (3), shield.yml
lang-schema (2), lang-shield-name (1) → R3. phys-* (10) → analyzer/board
slices. All 19 corpus accepts stay exit-3 until the emitter slice.

## 1. The scope boundary, and why it is byte-safe

The blueprint is `rigexp/loader_yml.py` (1441 lines). Its `load()` builds
the shield library FIRST (`:1186`, eager base-template parse) and resolves
every instance's `shield:` reference during content parse. R2 builds NO
shield library. The boundary is made safe by two facts, both verified:

- **rigc has no accept path.** Until the emitter slice, every load that
  produces zero error diagnostics ends in Unimplemented → exit 3. A
  deferred validation can therefore never produce a wrong ACCEPT — only a
  controlled refusal.
- **Deferral only ever REMOVES potential errors from stderr.** Every R2
  target golden carries exactly ONE error, and rigexp's shield machinery
  contributes zero bytes to it (the referenced shield —
  `adafruit_data_logger` in all six ref-carrying fixtures — resolves
  silently against the conftest's default `SHIELD_DIR`). rigc emitting the
  same single error with no shield machinery at all is byte-identical.

**The seam: `ShieldRef`.** An instance's `shield:` reference parses into an
opaque value (raw ref string + SrcRef) that always constructs — no
existence check, no library. Any access that needs shield DATA (devices,
declared params, node names, config elements) raises Unimplemented. R3
replaces the nominal resolver with the real library behind the same seam.
Consequences, each a recorded decision (ruling 1 below):

- `lang-instance-shield` (unknown shield) cannot fire in R2. No frozen
  golden covers it; a rig naming a nonexistent shield loads nominally and
  exits 3 downstream.
- **Wire endpoints are HALF-validated.** `_parse_wire`/`_resolve_dotted`
  (blueprint `:1383-1440`) run four checks; two are rig-side (dotted
  `<instance>.<node>` form; the instance exists in the effective topology)
  and R2 implements them. The other two (`inst.shield.by_name` node
  existence/ambiguity) need the parsed shield — deferred to R3 via
  ShieldRef. `route-no-via` (endpoints valid, `route:` mapping without
  `via:` → lang-schema) and `remove-wire-missing` (raw-endpoint-pair match
  in `_find_wire`, no shield needed) still flip byte-identically.
- `params:` or `pin:` anywhere (base instance, delta patch,
  add-instances) → Unimplemented, loudly. No R2 target uses either
  (verified). This defers `_apply_params_block`, `_apply_pin_block`,
  `_check_restate`, `_check_param_invariant`, and `_check_param_token`
  wholesale to R3.
- `dt-includes:` UNION machinery (blueprint `:821`, order and
  first-declaration SrcRef retention) is implemented as the pure value
  operation it is, but `_check_dt_includes` (cpp preprocess check,
  `:1367`) is deferred: a rig that declares any dt-includes raises
  Unimplemented after the union. No R2 target declares one.

## 2. Document model

Generalize the R1 sliver, keeping what it proved (mark-aware YAML with
line-accurate anchors, dotted key paths, construct-don't-parse filenames):

- **rig.yml**: `rig:` block with `name:`, optional `board:`/`sockets:`
  (the degenerate single-board shape), optional `revisions:`/`variants:`.
  The R1 `_guard_keys` whitelists widen to exactly this surface; unknown
  rig-level keys follow the blueprint's own permissiveness (`_resolve_axis`
  docstring `:656` leans on it — verify against rigexp, see §6's
  no-golden rule).
- **Content/delta documents**: FLAT top level, one parser for both
  (blueprint `_load_delta_doc:773` — base and fragment are the same
  document shape). Keys: `instances:`/`wires:`/`dt-includes:` (base and
  delta), `add-instances:`/`remove-instances:`/`add-wires:`/
  `remove-wires:` (delta-only), plus the metadata rejection
  (`board:`/`sockets:` → lang-schema, R1's check, now applied to base +
  BOTH delta stages exactly as `_apply_delta:1088` does).
- Content file REQUIRED, name constructed from `rig.name`
  (lang-content, R1's check, unchanged).
- YAML parse errors (`lang-parse`): no frozen golden. Implement per the
  blueprint (both raise sites, `:792` and `:1194`) under §6's
  hand-differential rule, or keep Unimplemented — implementor's choice,
  reported.

## 3. Qualifier axes — with the hwmv2 seam

Port the three functions as VALUE-shaped units:

- **`_parse_axis_decl`** (`:455-527`): `{default:, list:}` shape,
  scalar entries everywhere, MAPPING entries (`{name:, board:, sockets:}`)
  legal ONLY in `variants:` (`revision-mapping-entry` is the reject);
  per-entry boards/sockets collected into the AxisDecl value.
- **`_resolve_axis`** (`:650-687`): the three failure shapes — selected
  against undeclared axis (`no-such-axis`), selected not a member
  (`unknown-variant`, `unknown-revision`), bare with no default
  (`no-default-variant`) — returning `(value | None, diagnostics)`.
- **`_check_axis_collision`** (`:610-647`): rule 4 widened — enumerate
  every constructible stem (each axis alone + every combined pair,
  revision normalized) and report collisions
  (`variant-revision-collision`, `combined-fragment-collision`).
- **`_normalize_revision`** (`:600`): dots→underscores in constructed
  filenames ONLY; the selected value stays raw.

**The hwmv2 seam (interaction recorded in the queue, re-verified from
`hwmv2-revision-semantics-brief.md`):** that ratified slice later replaces
the revisions DECLARATION shape (upstream's `revision: {format:, default:,
exact:, revisions: [{name:}]}`) and the RESOLUTION semantics (per-format
validation, nearest-lower match, zero-append, requested-vs-resolved) —
for rigs AND shields, in this one place. R2 reproduces TODAY'S semantics
(the goldens pin them) but shapes the code so that swap is local:
declaration parsing yields an AxisDecl VALUE; resolution is one pure
function over (decl, selected); normalization applies only at filename
construction. Nothing else in the loader may inspect a declaration's raw
YAML or re-derive resolution. Do NOT pre-build format typing or
requested-vs-resolved — just keep the seam narrow enough that the hwmv2
slice touches only these functions plus the model.

## 4. Board and socket-map resolution — the SocketBinding seam

Port `_resolve_board` (`:530-597`), S2's rules exactly: EITHER one
top-level `board:` (+ optional top-level `sockets:`) OR a `board:` beside
EVERY variants entry — never both (`board-declared-twice`), never partial
(`variant-board-partial`), never top-level sockets alongside per-variant
boards (`sockets-with-variant-board`), never neither (`no-board-declared`).
Resolution reads metadata BEFORE any content file opens.

**Architecture requirement from `board-as-invocation-coordinate.md` §6
(ratified direction, behavior unchanged):**

1. Metadata resolution produces a **`SocketBinding` value** — today: the
   resolved variant's map (or the top-level one), semantics
   `get(name, name)` (blueprint `:1028`, lookup-else-identity). One
   constructor, one place.
2. The binding applies at **exactly one named seam** — instance
   construction (base parse and delta patch alike, as the blueprint
   threads one `socket_map` through both) — and NEVER inside delta
   merging. The content/delta engine handles abstract references only.
3. The board/sockets diagnostic family stays in ONE module so the frozen
   wording survives a later mechanism swap.

`rig.board` lands in the model for provenance (context.cmake is the
emitter's job, later), including the empty-string convention on
resolution failure (`:558` et al.) — reproduce it; it is what keeps later
diagnostics from cascading.

## 5. Content, fragments, and the delta engine

- **Stage 0**: parse base instances (name, `socket:` through the binding,
  ShieldRef; `params:`/`pin:` → Unimplemented) preserving ORDER; then base
  wires (§1's half-validation). Empty `instances:` list stays legal and
  distinct from a missing content file.
- **Fragment discovery** (blueprint `:1242-1253`): constructed stems from
  `rig.revision`/`rig.variant` — never `${RIG}`, never directory listing.
  Variant fragment `<rig>_<variant>.yml`, revision fragment
  `<rig>_<norm(rev)>.yml`; LOADED before rule 10 runs, applied variant
  first, revision second (Q9; `remove-instance-drift`'s hint depends on
  this order).
- **Rule 10** (`_check_fragment_presence:710` + `_variant_metadata_differs:
  690`): a selected non-default value must contribute — a .yml delta, a
  cmake-collected `.overlay`/`_defconfig` (file-existence checks only),
  or (variants) board/sockets metadata actually DIFFERING from the
  default's. Defaults exempt. `variant-no-fragment`,
  `variant-board-restated` (the metadata_hint wording),
  `dotted-revision-no-fragment` (normalization in the looked-for names).
- **The delta engine** (`_apply_delta:1074`): metadata-key rejection
  first; `instances:` patches match the effective topology by name (rule
  6, `instances-delta-unknown-instance`); `add-instances:` must be new
  (rule 7, `add-instances-already-exists`); `remove-instances:` must
  exist, with the `removed_by` variant hint (rule 8,
  `remove-instance-drift`); `remove-wires:` matches by raw endpoint pair
  (rule 9, `remove-wire-missing`); `add-wires:` parses like base wires.
  Diagnostic code is lang-variant or lang-rev by stage (`:1085`).
- Instance-patch internals that touch shield data (shield swap
  re-resolution, params/pin reset) → Unimplemented; a patch touching only
  `socket:` may work through the binding.

## 6. Diagnostics: composition order, and the no-golden rule

- Diagnostics stay RETURN values (R1's core; no accumulator). The
  composed order must equal rigexp's emission order — which is document/
  traversal order by construction. Unit tests assert ordering on synthetic
  multi-error inputs even though every frozen R2 golden is single-error.
- rigexp CONTINUES after most errors (loops `continue`; `_resolve_board`
  errors leave `board=""` and loading proceeds). Reproduce the
  continuation shape — stopping early would DROP later diagnostics some
  future golden asserts; adding extra ones is caught by today's goldens.
- **The no-golden rule (new, needs ratification):** every diagnostic R2
  implements whose wording no frozen golden covers (e.g. `lang-parse`,
  `_require`'s missing-key wording, the half of lang-wire-ref R2 keeps)
  must be verified by a HAND-DIFFERENTIAL: build a throwaway fixture,
  run rigexp and rigc on it, byte-compare stderr. Record each such check
  in the slice report. The alternative — Unimplemented — is always
  acceptable; silent unverified wording is not.

## 7. Unit tests and structure

- The unit-naming rule holds (`test_<module>.py`, mission brief §6).
  Whether the loader stays ONE module or becomes a package
  (`loader/documents.py`, `loader/axes.py`, `loader/binding.py`,
  `loader/delta.py` — with `tests/unit/loader/` mirroring it) is the
  implementor's design call; the discipline test's expectations update
  deliberately either way, flagged in the report.
- Stable contracts that get unit tests: fragment-stem construction +
  collision enumeration; axis declaration parsing (incl. mapping-entry
  gating); axis resolution's three failure shapes; revision
  normalization; board/SocketBinding resolution (all five S2 shape rules
  + binding semantics); dt-includes union (order, dedup, SrcRef
  retention); delta operations over a synthetic effective topology
  (match/add/remove for instances and wires, `removed_by` propagation);
  diagnostic ordering. Wording stays out of unit tests (frozen goldens
  own it) — structure, codes, anchors, ordering only.
- The R1 scaffolding rules persist: no subprocess under `tests/unit/`, no
  module-scope `$ZEPHYR_BASE`, no pytest markers, `assert_fixture_local`
  for anything touching fixture paths, suite well under 1s.

## 8. Acceptance

A. Default gate (knob unset): frozen suite 146 green, rigc unit suite
   green, mypy clean over both packages, one `check.sh` run.
B. `RIG_EXPAND_COMPILE=rigc`: the 19 targets pass AND the 4 R1 flips
   still pass (23 reject goldens green). Report the full pass count
   (expected 64/146); every target that does NOT flip is explained, not
   papered over. Every other red is exit-3 or a clean diagnostic
   mismatch, never a traceback.
C. Zero edits outside `scripts/rigc/**`. No rigexp file, no golden, no
   fixture, no cmake, no check.sh change.
D. Unit suite subprocess-free (discipline test proves it), runtime
   reported; coverage over rigc re-measured and reported (no fail_under
   yet — Tobi's standing call, revisit after R2).
E. Every no-golden diagnostic implemented carries its hand-differential
   evidence in the report (§6).
F. STOP and report before any commit. Report: files/modules created, the
   19 flips with evidence, the deferral seams actually hit (which
   Unimplemented paths fire on which corpus inputs), deviations flagged.

## Out of scope, deliberately

- Shield library, `.shield`/TU parsing, connector-type registry, header
  checks (`_check_dt_includes`, token resolution) → R3.
- Board DT reading, analyzer, emitter, any accept artifact.
- hwmv2 revision SEMANTICS (seam only, §3) and the open-board/socket-label
  direction (seam only, §4).
- Any golden refreeze; any frozen-suite edit.

## Needs Tobi's ratification

1. **The ShieldRef seam** (§1): nominal shield references, deferred node
   validation on wire endpoints, params/pin as loud refusals — including
   the recorded consequence that rigc-R2 silently accepts wire node names
   rigexp would reject (safe: no accept path exists; closed by R3).
2. **The no-golden hand-differential rule** (§6) — becomes standing
   discipline for all remaining slices if ratified.
3. **The target list** (§0) — 19 rejects, expected meter 64/146.
4. Implementor model: sonnet per the standing rule, or a per-slice bump
   as with R1 (the delta engine is the meatiest port so far).
