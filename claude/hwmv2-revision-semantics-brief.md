# Slice brief — hwmv2 revision semantics (ruling 2026-07-26f)

Ratified by Tobi 2026-07-26: **revision logic and behaviour become exactly
upstream's.** This brief is implementor-ready; the design record is
design-log 2026-07-26f. Dispatch AFTER V1c lands — V1c writes the current
simple axis block, and this slice migrates it once for rigs AND shields.

## Scope

`_parse_axis_decl` is the single place the declaration shape lives, and it is
shared by rig.yml and (post-V1c) shield.yml. Change it there and both axes
follow.

### 1. Declaration shape — go to upstream's, not a near-miss

Replace `revisions: {default:, list: []}` with upstream's block:

```yaml
revision:
  format: number            # letter | number | major.minor.patch
  default: "1"
  exact: false              # optional
  revisions:
    - name: "1"
    - name: "2"
```

Rationale for copying the SHAPE and not just the behaviour: a reviewer diffs
our schema against `board-schema.yaml`, and a near-miss costs more than
either a full copy or a clean divergence. **This spends the V1 spec §2
one-schema-for-both-axes property** — `variants:` keeps `{default:, list:}`.
That is a ratified trade, not an oversight; record it where §2 states the
property.

### 2. Behaviour — port, do not reinvent

Source of truth is `board_check_revision` (`zephyr/cmake/modules/
extensions.cmake:1048-1160`). Port to Python:

- **Per-format id validation.** `letter` → `^[A-Z]$`; `number` → `^\d+$`;
  `major.minor.patch` → `^((0|[1-9][0-9]*)(\.[0-9]+)(\.[0-9]+))$`.
- **Loose typing for major.minor.patch** (extensions.cmake:1092-1103): `@1`
  becomes `1.0.0`, `@1.2` becomes `1.2.0` — append missing zeroes BEFORE
  matching.
- **Nearest-lower-match** (extensions.cmake:1133-1152): an undeclared
  revision resolves DOWN to the highest declared revision less than or equal
  to it, per-format comparison (VERSION_ / STRGREATER / GREATER semantics).
- **`exact: true`** disables that, and an undeclared revision is then fatal —
  which is our CURRENT unconditional behaviour, so `exact: true` reproduces
  today's rigs bit for bit.
- **No revisions declared but `@rev` given** stays fatal, wording in the
  existing `lang-rev` family (upstream: "Board 'X' does not define any
  revisions").

### 3. Requested vs resolved — a new model field, deliberately

Nearest-lower means the selected string and the effective string differ
(`@1.5` → `1`). Upstream keeps both (`BOARD_REVISION` vs
`ACTIVE_BOARD_REVISION`) and so must we, because **the RESOLVED value is what
constructs fragment filenames** — the `_RIG_RESOLVED_NAME` hazard class (B1:
derive from the resolved form, never the raw one; a silently unapplied
defconfig is the failure mode).

- model carries both; `_normalize_revision` applies to the RESOLVED value
  when joining filenames, never to the requested one.
- `context.cmake` / `build_info` carry the RESOLVED value.
- the configure log prints `requested -> resolved` **only when they differ**.

This is a `model.py` change; the design decision is recorded (2026-07-26f),
which is what the lifted freeze requires.

### 4. Deliberately NOT copied — reject loudly, do not silently ignore

- **`format: custom`** → upstream includes `<dir>/revision.cmake` and lets
  the board author call `board_check_revision` themselves. We resolve in
  PYTHON (`list_rigs.py` + loader), so this would mean arbitrary cmake in a
  rig folder feeding a Python resolver. Reject with a diagnostic naming the
  three supported formats and saying custom is unsupported for rigs. Parity
  is therefore behavioural-for-the-three-real-formats, NOT full — do not
  claim otherwise in docs or commit messages.
- **The valid-revision glob** (extensions.cmake:1114-1126) discovers
  revisions by matching `<board>_*.conf` FILENAMES. Reachable only via
  `custom`, and it parses filenames — against Q6. Skip it. (Worth a sentence
  in the eventual upstream discussion: this is the one place upstream
  violates its own construct-don't-parse discipline.)

## Interactions to verify, not assume

- **Rule 4 (collision guard).** Format typing SHRINKS the collision surface
  for `letter`/`number` (ids can no longer look like identifiers) but not for
  `major.minor.patch`, where revision `1.2` normalizes to `1_2` and a variant
  may legally be NAMED `1_2`. Keep the widened guard; re-run its fixture.
- **Rule 10 (non-default must contribute a fragment).** With nearest-lower,
  `@1.5` resolving to a default revision hits rule 10's default EXEMPTION.
  Assert that explicitly — it is the case most likely to regress.
- **Two selections, one fragment set.** `@1.5` and `@1` now resolve
  identically. Intended; provenance distinguishes them via requested vs
  resolved.

## Golden budget

Existing corpus rows must be BYTE-UNTOUCHED — every current rig either
declares no revisions or can declare `exact: true` to reproduce today's
behaviour. Prove it with `git diff --stat`, do not assert it. New coverage:
one accept tuple per format (letter / number / major.minor.patch), one
nearest-lower resolution whose provenance shows `requested -> resolved`, one
`exact: true` rejection, one zero-append case (`@1` → `1.0.0`), and rejects
for `format: custom` and for a malformed id per format.
