# The rig→shield reference vocabulary — `config:`, labels, and a doc page

**Status:** briefed 2026-08-13, **ruled, ready to dispatch.** Backlog
item 29. **Sequences BEFORE item 28** (pin promotion) by Tobi's own
instruction — item 28 would otherwise bake `pin.` into a user-facing
CLI surface and force a second migration through the same files.

Three deliverables, best as three commits: the key rename, the naming
authority, and a `doc/` reference page.

## 1. The rulings (Tobi, 2026-08-13)

1. **`pin:` becomes `config:`.** The rig-side key takes the name the
   rest of the model already uses — `ontology.md`'s *configuration
   element*, the shield DTS's own `config { }`. The old name was
   actively wrong for half its cases: `pin: { addr_strap: 0x49 }`
   assigns an **I²C address**, not a pin.

2. **The LABEL is the naming authority, for every rig→shield string
   reference.** `params:` is already label-based and does not move;
   `config:` moves off the node name. **Ruled against node-name-wins on
   the evidence in §2**, which was gathered specifically to check it:
   it is implementable but costs ~4× the migration and moves *against*
   grep-ability, which is the whole point of the change.

   The deciding argument is consistency, not convenience: **the
   shield's own internal references are already labels.**
   `temp_click.shield` says `shield,addr-from = <&tc_addr_strap>`.
   Conv. 5 already says *within a shield, references are phandles;
   from `rig.yml`, references are strings* — this makes the string and
   the phandle **the same identifier**, so one grep spans the
   declaration, the internal reference and every rig that assigns it.

3. **`doc/` gets a reference page**, and it covers **every `shield,*`
   property we have introduced** — meaning and syntax, not just the
   rig-side keys. They are our vocabulary and nothing documents them
   today (§8).

## 2. THE EVIDENCE — re-derive it before trusting it

Census over all 21 shield roots (corpus + fixtures), 31 shields
resolved, 10 deliberately-broken fixtures skipped. Script:
`scripts/rigc/loader/library.py`'s own scan, `resolve()` per name,
counting `Device.name` vs `Device.label`.

| | distinct / uses | spelled the same in >1 shield |
|---|---|---|
| device **node names** | 18 / 30 | `sensor` in **8**, `dev` in 3, `button`/`lcd`/`servo` in 2 |
| device **labels** | 29 / 30 | one pair, a deliberate fixture variant (`grove_servo`/`grove_servo_flags`) |
| config **node names** | 2 / 2 | none |
| config **labels** | 2 / 2 | none |

**Within a shield, BOTH spellings are unambiguous** — zero duplicate
node names, zero duplicate labels, zero device/config clashes, in every
one of the 31. Node-name-wins was never blocked; it was rejected on
cost and on grep-ability.

Migration cost, the other half of the ruling: `params:` (device
references) has **12 rig files** plus 2 config-sheet goldens rendering
the device key, plus the `<device>.<prop>=` promotion grammar and
`test_singleton_identity_law.py`'s `_REQUIRED_PARAM_ASSIGNMENTS`.
`pin:` (config references) has **3 rig files and 2 config elements.**

**Only two config elements exist in the whole tree**, both in the real
corpus, **zero in fixtures**:

```
$ grep -rln 'position-domain\|shield,domain' boards/shields scripts/rigc/tests/fixtures
adafruit_winc1500   jumper  irq-jmp    (label w_irq_jmp)
temp_click          strap   addr-strap (label tc_addr_strap)

$ grep -rn '^\s*pin:' boards/rigs scripts/rigc/tests/fixtures
nucleo_wifi_logger, nucleo_wifi_logger_ok, quail_temp_farm   # all corpus
```

## 3. What changes

```yaml
# before                          # after
pin:                              config:
  addr_strap: 0x49                  tc_addr_strap: 0x49
  irq_jmp: D2                       w_irq_jmp: D2
```

- `loader/delta.py` reads `config:` where it read `pin:` (TWO sites:
  `parse_instance` and `_apply_instance_patch`'s shallow-replace).
- `loader/params.py:apply_pin_block` → `apply_config_block`, resolving
  by LABEL.
- `model.py:Shield.config_element(name)` looks up by label.
- **The `_`→`-` normalization DIES.** `loader/params.py:227` tries
  `cfg_name.replace("_","-")` before the raw name — that exists only to
  bridge the underscore/hyphen gap between a rig key and a node name.
  A DTS label is `[0-9a-zA-Z_]+`; a hyphen can never appear in one, so
  after this change the normalization can only mis-resolve. Removing it
  is part of the slice, not a follow-up.
- Diagnostic code `lang-pin` → `lang-config`, and its message names
  labels. `Shield.names()` (the "valid names" list a diagnostic
  renders) renders labels.
- The 3 corpus rigs migrate.

## 4. THE SILENT FALLBACK MUST BECOME A LOUD ERROR

`shields.py:651/658/644` all build their model object as:

```python
label=node.labels[0] if node.labels else node.name
```

So an unlabeled config node is silently addressed by its **node name**
— which is precisely the two-spellings problem this slice exists to
kill, reintroduced by a fallback. **Make an unlabeled config node a
loud `lang-shield-*` error** naming the node and what it needs.

Costs nothing today: both existing config elements carry labels and no
fixture declares one at all. Do it now, while the corpus cannot fight
back.

Apply the same reasoning to `Pad` and `Device` **only if §6 is taken**;
otherwise leave their fallbacks and say so.

## 5. What does NOT change — the blast radius stays small on purpose

**Only the rig-facing LOOKUP moves. Internal keying stays node-name.**
`apply_config_block` still stores `pins[elem.name]`/`jumpers[elem.name]`,
`Device.addr_from` still holds `strap.name` (`shields.py:352`), and
`analyzer/addresses.py` still joins them on that key. Those are
internal dict keys no user ever types.

This is deliberate, and it is what keeps the change cheap:

- The shield's internal reference is a **phandle**, already
  unambiguous and parse-checked by dtlib. The identifier problem is a
  `rig.yml` (string) problem only.
- **The unit-address marker lint stays untouched.**
  `shields.py:381` warns when a device's symbolic unit-address does not
  match its `addr-from` target (`sensor@addr_strap` vs node name
  `addr-strap`). Re-keying `addr_from` to the label would make that
  lint fire on the existing corpus for no gain. `conventions.md` calls
  the marker "pure documentation"; leave it, and **say in the report
  that it was considered and left**, so nobody re-derives it.

If re-keying internally seems necessary, the premise is wrong — stop
and report.

## 6. THE THIRD SURFACE — `wires:`, and it is a real decision

`params:` and `pin:` are not the only rig→shield string references.
`Shield.by_name` (`model.py:226`) resolves a `wires:` endpoint
`<instance>.<node>` against **pads UNION devices UNION straps, all by
NODE NAME**. So `wires: { from: x.sq, to: y.led-1 }` names
`adafruit_data_logger`'s `led-1` node, whose label is `dl_led1`.

**Recommended IN SCOPE.** `Pad`, `Device` and `Strap` all already carry
`.label` with the identical fallback, the surface has **2 fixture users
and zero corpus users**
(`remove-wire-missing`, `route-no-via`), and leaving it out re-creates
the exact split this slice exists to remove — one rig file would then
reference a device by label on one line and by node name on the next.
`Shield.names()` serves both surfaces and must move either way.

**Flag it for veto**: it widens the slice to a third grammar and drags
pad labels in with it. Whichever way it goes, state it explicitly in
the report — do not let it be silently absorbed or silently dropped.

## 7. Golden impact — predicted ZERO, and it is checkable in advance

```
$ grep -rln 'lang-pin\|pin:' scripts/rigc/tests/goldens
(no match)
```

No golden mentions the key or the diagnostic code. The emitted
artifacts are insulated for the same reason S5's were: the **config
sheet renders `shield,sheet-label`** ("set **ADDR jumper** to state 1"),
never the node name or the label, and the **overlay renders the
RESULT** (`reg = <0x49>`, the routed pin). The Parameters table renders
the device key — which does not move, since `params:` is already
label-based.

State this as a checked result, not an assumption. If a golden moves,
that is the report's headline. `RIGC_REFREEZE=1` stays BLOCKED —
hand-edit and verify BOTH ways.

## 8. THE DOC PAGE — its own commit, and its own deliverable

`doc/` mentions `pin:` **nowhere** (`grep -rln 'pin:' doc/` → no
match). The whole `shield,*` vocabulary is undocumented outside
`conventions.md`, which is a design document, not user documentation.

The page must cover **every `shield,*` property, with meaning and
syntax**. Census by grep on 2026-08-13 — **re-derive it and reconcile
against `shields.py`'s parser before writing, this list is a
prediction**:

| property | uses | what it declares |
|---|---|---|
| `shield,plugs` | 114 | the connector type(s) a shield mates — the slot set |
| `shield,plug` | 38 | which slot a bus group nests under (multi-plug) |
| `shield,params` | 30 | property names a rig may/must assign on this device |
| `shield,cs-position` | 21 | copper-fixed CS, vs pool allocation when absent |
| `shield,param-includes` | 20 | headers the param tokens resolve against |
| `shield,addr-from` | 16 | this device's address comes from that strap |
| `shield,collect` | 10 | this device is an entry in a shared collection |
| `shield,channel` | 9 | mux channel index |
| `shield,sheet-label` | 6 | the human-facing name on the config sheet |
| `shield,position-domain` | 6 | a routing jumper's position domain |
| `shield,role` | 5 | pad role: driver / listener / bidir |
| `shield,domain` | 5 | a strap's (address, state) domain |
| `shield,of` | 3 | the device a pad belongs to |
| `shield,plug-compatible` | 1 | — verify against the parser before documenting |

Requirements for the page:

- **Diátaxis reference quadrant**, rST, `sphinx-build -W` clean, same
  as the existing tree.
- Each property: syntax, value shape, where it may appear, what
  consumes it, and one REAL example quoted from the tree — never an
  invented one. The tutorial playground's honesty debt is the standing
  warning here: **do not write commands or snippets that cannot be run
  as written.**
- Document the **naming authority** as a numbered rule, since Conv. 5
  states that rig→below references are strings but never says WHICH
  string — that silence is what let the two blocks diverge.
- Document `config:` (both kinds), and the strap-vs-jumper split with
  the "who resolves it when the rig is silent" table: param → authored
  default, else required; strap → allocated; jumper → nobody, hard
  error; CS position → pool-allocated with no config element at all.

**Out of scope for the page unless it is free:** `socket,*` (9
properties) and `connector,*`. They are equally ours and equally
undocumented, but they are the board/connector side. A sibling page,
named in the report as owed.

## 9. Interaction with item 28

`pin-promotion-brief.md`'s grammar becomes **`config.<label>=<value>`**
and its ruling-1 reserved-half rule reads: the reserved device-half
names the instance-level key the assignment routes to — `socket` →
`socket:`/`sockets:`, `config` → `config:`, everything else →
`params:`. **Update that brief in the same commit as the rename**, so
the two never disagree in the tree.

## 10. Tests

- `test_shields.py` (or wherever config-element parsing is pinned): the
  unlabeled-config-node error of §4, with its sentence.
- Loader unit tests: `config:` resolves by label; the node name is now
  **rejected**, with the `lang-config` sentence listing labels; the
  old `_`→`-` normalization no longer resolves anything.
- `test_emitted_corpus.py` / `test_emitted_rejects.py`: §7's zero
  movement, as a checked result.
- The 3 corpus rigs migrated, and one delta test covering
  `_apply_instance_patch`'s `config:` branch (the shallow-replace site
  is easy to miss — it is the second of the two `delta.py` reads).
- §6's `wires:` fixtures if it is taken.
- If item 28 is already briefed-not-built, no test moves for it; only
  its brief text.

## 11. Acceptance criteria

1. Every existing golden byte-unchanged (§7), stated as a checked
   result.
2. `config:` resolves the label on both delta.py sites; the node name
   is refused with a sentence naming the valid labels.
3. An unlabeled config node is a loud error (§4).
4. The `_`→`-` normalization is gone, and a test proves the hyphen form
   no longer resolves.
5. The doc page builds `-W` clean and every example in it is quoted
   from the tree and runs as written.
6. `pin-promotion-brief.md` updated to `config.<label>=` in the same
   commit as the rename.
7. Full gate green, driver-run. Coverage floor 88. **Re-derive the
   unit/integration counts from a real run** — the last recorded
   numbers (709 / 254) are carried, not observed.

## 12. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (the module that observes criterion
1, since the three migrated rigs are corpus rigs). **Confirm its
`@pytest.mark.build` marking before claiming it** — a brief has named a
build module by reflex before and been wrong. Observing modules: the
loader unit tests, `test_emitted_corpus.py`, `test_emitted_rejects.py`.
Driver runs the full gate once, after review.

Brief the reviewer to MUTATION-CHECK: revert the label lookup to node
name (the loader unit test must fail on the SENTENCE, not merely on a
resolution failure); delete the §4 error (its test must fail); restore
the `_`→`-` normalization (criterion 4's test must fail). A green gate
proves nothing about whether these are contracts.

Standing rules: an implementor's report is a HYPOTHESIS — the driver
re-runs it. **Trace every reader of the `pin` key and of
`config_element`/`by_name`/`names()` by grep and run**; this brief's
own file list is a prediction and the missed-caller lesson has recurred
four times. Run negative controls IN-TREE. Purge `__pycache__` after
any mutate-and-restore. `RIGC_REFREEZE=1` stays blocked. Dispatch as
`general-purpose` on **sonnet** with the role rules folded into the
prompt if the session is rooted at `/wrk/z/ws-up`.
