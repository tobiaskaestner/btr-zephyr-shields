# Slice brief — rig-schema.yaml, rig metadata, and expectation signposting

Ratified by Tobi 2026-07-26 (rulings 2 and 3, design-log 2026-07-26f).

**SUPERSEDED IN ONE RESPECT (2026-07-26h): this schema validates METADATA
ONLY.** The metadata/content split (`rig-metadata-content-split-brief.md`)
must land first — a schema authored against today's conflated `rig.yml` would
cement the conflation, and `additionalProperties: false` over a file holding
topology forces jsonschema to compete with the loader for diagnostics the
loader does better (line-accurate, with candidate lists). Content
(`instances:`, `wires:`, `params:`, `dt-includes:`) stays the loader's domain
and is NOT described here.

Afterwards this schema becomes what ENFORCES the split: with
`additionalProperties: false` on a metadata-only `rig.yml`, putting
`instances:` back fails loudly at discovery time. That is the answer to the
one real objection against two same-language files — the boundary is
enforced, not merely conventional.

Dispatch order: split (S1, S2) -> hwmv2 revision semantics -> THIS. Both
predecessors change the very keys this schema describes.

## Why now, not after the migration

`board.yml` and `shield.yml` are both jsonschema-validated with
`additionalProperties: false` (`zephyr/scripts/schemas/`, enforced in
`list_boards.py` / `list_shields.py`). `rig.yml` has **no schema at all**:
`list_rigs.py:94-97` reads it without validating shape, and `loader_yml` is
deliberately permissive about unknown rig-level keys (stated at line 252).

So a typo'd top-level rig key is silently ignored, where the same typo in
board.yml or shield.yml is fatal at discovery. That is the same failure
species as both rules the project learned the hard way — a silently
unapplied defconfig (B1), a golden nobody asserts (V1b). Upstream's direction
of travel is explicit (`b836fcdd709` "list_shields: Switch to JSON schema"),
so upstreaming will require this regardless; doing it BEFORE the bridle
migration means the migration carries a validated artifact instead of a
permissive one.

## 1. `rig-schema.yaml` + validation in list_rigs.py

Mirror `board-schema.yaml`'s structure closely enough that the two diff
cleanly: `$schema`/`$id`/`title`/`description` header, `$defs` for the
reusable blocks, `additionalProperties: false` at every level, conditional
constraints expressed declaratively (`oneOf`, `allOf/if/then`) rather than in
Python.

Validate in `list_rigs.py` exactly as `list_shields.py` does — `jsonschema`,
`validator_for`, `iter_errors`, `best_match` for the message. Keep the
DIVISION OF LABOUR intact: the schema owns SHAPE, the rigexp loader remains
the canonical CONTENT validator (`lang-schema` and friends). The loader's
existing shape checks stay; they are what direct-API and test callers get.

## 2. Metadata — ruling 2

- **`full_name` REQUIRED.** Touches every existing rig.yml. Shields require
  name + full_name + vendor, boards require name + full_name; rigs carried
  none, and were the odd one out of the three.
- **`vendor` optional.**
- **It must SURFACE**: add the format keys to `west rigs`, mirroring
  `west boards` / `west shields` (`list_rigs.py` already has `-f`/`-n`).
  A required key nobody reads is its own smell.
- **Author the requirement in board-schema's shape**, i.e.
  `oneOf: [required: [name, full_name], required: [extend]]`, even though
  `extend:` is NOT accepted yet — so that requiring `full_name` need not be
  unpicked if rig extension ever lands. Cheap foresight, no implementation
  cost.

## 3. The target regex

`_RIG_TARGET_RE` in `list_rigs.py:42` is `^([^@/]+)(@[^@/]+)?(/(.+))?$`;
upstream's `parse_board_components` is `^([^@/]+)(@[^@/]+)?(/([^@]+))?$`. Ours
accepts `@` inside the qualifier, so `rig/variant@2` parses for us (as a
variant literally named `variant@2`) and is fatal upstream. One-character
class fix. `list_rigs.py` is the single parser — cmake never reimplements the
grammar — so there is exactly one site.

Diagnostic wording follows upstream's ("Valid format is: ..."). Add a
synthetic reject fixture.

## 4. Signposting — ruling 3, the cheap half of expectation management

The schema's job is not only to reject but to POINT. Two cells of the
symmetry table (ontology §7) are deliberate absences, and both are things a
newcomer from hwmv2 will literally try in a rig.yml:

- **`rigs:`** (the plural declaration form) — reject BY NAME with: one rig per
  file, and `variants:` is what a rig FAMILY uses.
- **`extend:`** — reject BY NAME as not supported yet, rather than as an
  unknown key. It is a coordinate-level gap that is owed and deferred, not a
  mistake on the author's part.

`additionalProperties: false` alone would produce "additional properties are
not allowed", which names the key but not the alternative. Prefer explicit
`not`/`if-then` branches (or a loader-side check) that carry the pointer.

## Golden budget

Existing corpus rows change only by gaining `full_name:`; if that value
surfaces in provenance or the configure log, that is a JUSTIFIED refreeze —
grep-prove it is confined to the added line. New rejects: unknown top-level
key, `rigs:`, `extend:`, missing `full_name`, and `rig/variant@2`.

## Explicitly out of scope

`runners:` (the remaining unclassified board-side cell) and rig `extend:`
itself. `extend:` has a prerequisite that is policy, not effort — the live
last-wins shield collision across board roots — and it should follow that
fix, post-migration.
