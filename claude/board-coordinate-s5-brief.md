# S5 — content migration to conventional socket labels

Slice brief, written 2026-08-06. Parent: `board-as-coordinate-brief.md`
§9.5 step 5 (its §7.3 / §7 step 3 is the older per-step detail, and §6 is
the measured golden impact this slice depends on). Ruling 1 (§2) fixed the
convention; `d47ec86` shipped the mechanism.

**This is a DATA slice.** Every production change it needs already landed.
If you find yourself editing `board_edt.py`, `analyzer/sockets.py` or the
emitter, stop and report — that is a sign the premise is wrong, not that
the slice grew.

## 1. What this slice is

Rig **content** references sockets by board-specific label today
(`nucleo_ard`, `quail_sock2`, `frdm_ard`). Migrate those references to the
per-type convention ruling 1 settled:

> **`<type>` for a singleton socket, `<type>_<silkscreen>` for a family**,
> where `<type>` is the connector type name with dashes as underscores —
> the name that already exists in `dts/bindings/connectors/<type>.yaml`
> and in the `socket,<type>` compatible.

Under a free board (S1), a board-specific label in content is a
**portability bug, not a style question**: content naming `nucleo_ard` can
only ever build on that one board, which is precisely what
board-as-coordinate exists to undo.

## 2. Prerequisite — VERIFIED, not assumed

The alias labels exist on every board a corpus rig targets, in DT
multi-label form. Checked in the tree:

```
nucleo_ard: arduino_r3: connector_arduino_r3 {
frdm_ard:   arduino_r3: connector_arduino_r3 {
quail_sock1: mikrobus_1: connector_mikrobus_1 {   (…2, 3, 4)
grove_d2: connector_grove_d2 {                    (lotus: already conventional)
```

§6's rule — *"the alias must exist before content references it, or
resolution fails outright"* — is therefore satisfied. Note the aliases are
the SECOND label; `labels[0]` stays the board-specific one, which §3
below depends on.

## 3. Golden impact — traced to the code, and narrower than it looks

The socket label reaches several places, from **different sources**, and
that difference is the whole cost model. Traced, not assumed:

- **`rig-gen.overlay` does NOT churn.** `emitter/overlay.py::_socket_ref`
  returns `socket.nexus_label or socket.label`, and `socket.label` is
  `labels[0]` — the board's DEFINING label. The phandle stays
  `<&nucleo_ard 13 0x11>` regardless of what content calls the socket.
- **Reject `stderr.txt` does NOT churn.** All four sites that print a
  socket in a diagnostic render `socket.label`, never the content's
  string: `analyzer/addresses.py:243,245` and `analyzer/gpio.py:241,249`.
  The two reject goldens that carry a board-prefixed label
  (`frdm_cs_clash/stderr.txt`, `nucleo_wifi_logger/stderr.txt`) are
  insulated for the same reason the overlay is. **This matters because
  `stderr.txt` is byte-exact PERMANENTLY by owner ruling** — a churn there
  would need its own product decision, and this slice must not produce one.
- **`config-sheet.md` DOES churn.** `emitter/sheet.py` renders
  `inst.socket` — the CONTENT's string — into the instance/socket tuple
  C2b made a compared fact.

> **The golden impact of this slice is `config-sheet.md`, and nothing
> else.** Any other golden moving is a defect, not a refreeze.

## 4. Scope — counted, per label

| references | label | disposition |
|---|---|---|
| 10 | `nucleo_ard` (8 rigs, one of them a reject) | **migrate** → `arduino_r3` |
| 9 | `quail_sock1..4` | **migrate** → `mikrobus_1..4` |
| 3 | `frdm_ard` | **migrate** → `arduino_r3` |
| 1 | `ard` (abstract, `ard_datalogger`) | **LEAVE — see §5.1** |
| 7 | `grove_d2/d4/d6/a0` | none — lotus already conforms |
| 11 | `mux_1.ch0`, `adapter_1.mb1`, … | none — instance-scoped, already board-agnostic by the provider rule |

**22 references migrate. 19 do not.** Derive the list yourself with a
grep over `boards/rigs/` rather than trusting this table — it is a census
taken on 2026-08-06 and the corpus is allowed to move under it.

## 5. RULINGS (Tobi, 2026-08-06)

### 5.1 `ard_datalogger` is NOT touched — its collapse is S6's

`ard_datalogger` is the only user of the abstract socket map
(`sockets: {ard: nucleo_ard}` / `{ard: frdm_ard}`), which exists solely
because nucleo and frdm spell the same connector differently. Once both
carry `arduino_r3`, that map has nothing left to do — and §9.4 already
promises its dual-host variants collapse to one variant-less rig built
twice.

> **RULED: the collapse happens in S6, not here.** S5 leaves
> `ard_datalogger`'s content, map and variants exactly as they are.

Consequence, and it is why this ruling makes the slice cleaner rather
than deferring work: **nothing is orphaned by S5.** Had the abstract
`ard` been migrated, the map would have been left mapping a key nothing
references, and this slice would have owed a decision about whether an
inert map is an error, a warning, or silently fine. It owes none. That
question moves to S6 along with the collapse.

### 5.2 The refreeze is CLASSIFIED, and this is the first slice that churns at all

S1–S4 each had zero golden churn as an acceptance criterion. This one
does not, and `RIGC_REFREEZE=1` **rewrites whole files** — twice in this
project's history that dragged 40–58 unrelated files into a slice's diff
and had to be hand-reverted.

> **RULED: only `config-sheet.md`'s instance/socket tuples may move.
> Every other changed byte, in any golden, is a defect to report — never
> to refreeze.**

Classify the refreeze diff BEFORE committing it. State the file count and
what changed in each.

### 5.3 The multi-board answer is an ACCEPTANCE CRITERION

Today all 17 corpus rigs answer exactly their declared board, so a
`boards_for` stub returning `[rig.board]` passes every integration
assertion — the discrimination lives entirely in the unit layer, and S2's
own handoff recorded that S5 is what finally fixes it.

> **RULED: the slice must demonstrate at least one corpus rig whose
> `--boards-for` answer now contains more than one board**, as a test, not
> as a note in the report. This is the integration tier's first real
> falsifier for socket conformance and it is half of why the slice is
> worth doing.

### 5.4 Do NOT flip the defining label

Making `arduino_r3` the first label and `nucleo_ard` the alias would make
content resolve identically — and would churn `rig-gen.overlay`, the
`zephyr.dts` references, and both byte-exact reject goldens named in §3.

> **RULED: `labels[0]` stays the board-specific label on every board.
> `Socket.label` stays `labels[0]`.**

§6 states the reason and it is not incidental: the overlay is a DT
fragment applied to THAT board in THAT build, so referencing the board's
own defining label is correct. Board agnosticism belongs in the content —
the thing that gets reused — never in a generated per-build artifact.

This is the change an implementor is most likely to make "helpfully".
§3's overlay-byte-identical criterion exists to catch exactly it.

### 5.5 No new production code

Ruling 1's mechanism landed in `d47ec86`. If the migration appears to
need a production change, the premise is wrong — report it rather than
widening the slice.

## 6. Acceptance criteria

1. **`rig-gen.overlay` byte-identical for every rig.** A genuine
   falsifier, not a formality (§5.4).
2. **`zephyr.dts` byte-identical for every rig** — the migration is a
   rename in the content's vocabulary, not a topology change.
3. **Every `stderr.txt` and `exit_code` byte-identical.** Byte-exact
   permanently by ruling; §3 traced why they should be insulated, so a
   churn here means something is wrong with that reasoning — report it.
4. **`config-sheet.md` churns, and ONLY in its instance/socket tuples**,
   only for migrated instances. Classified per §5.2.
5. **No content file anywhere under `boards/rigs/` names a
   board-prefixed socket**, except `ard_datalogger`'s abstract `ard`
   (§5.1). Assert this as a census-style test — and remember a census
   test is falsified by mutating the WORLD it observes (add a
   board-prefixed reference to a rig), never by editing its own
   assertion.
6. **At least one corpus rig answers more than one board** via
   `--boards-for`, as a test (§5.3).
7. mypy clean, unit green, coverage at or above the 88 floor.

## 7. Verification contract — REDUCED, and it overrides the agent definition

Any instruction to run `scripts/check.sh` is superseded. The driver runs
the full gate once, after review.

```
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr
PY=/wrk/z/ws-up/.venv/bin/python3
cd /wrk/z/ws-up/btr-shields

$PY -m mypy scripts/rigc
$PY -m pytest scripts/rigc/tests/unit -q
$PY -m pytest -m "not build" scripts/rigc/tests/integration -q
$PY -m pytest scripts/rigc/tests/integration/test_resolved_corpus.py -q
git diff --stat -- scripts/rigc/tests/goldens/     # CLASSIFY, do not clear
```

`test_resolved_corpus.py` is the ONE build-marked module here — unlike
every prior slice in this sequence, it is the module that would show a
migration breaking a real build.

- **Do NOT background a command and end your turn waiting on it.**
- Never `cmd | tail; echo $?` — that reports tail's status.
- The papers are at `btr-shields/claude/`; any reference to
  `/wrk/z/ws-up/claude/rigs/` is stale.

## 8. Out of scope — do not start

S6 in every part: `board:` leaving rig.yml, the variant collapse,
`ard_datalogger` (§5.1), retiring the `sockets:` map vocabulary, the 19
`RIG_BOARD` goldens. The §9.6 params CLI grammar. Any change to the
boards' own DT labels (§5.4).
