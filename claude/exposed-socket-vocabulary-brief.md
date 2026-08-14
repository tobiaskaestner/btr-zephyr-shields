# Item 30 — the fourth reference surface: `socket: <carrier>.<exposed>`

**Status:** briefed 2026-08-14, ready to dispatch. Backlog item 30,
un-parked by Tobi 2026-08-14 and sequenced BEFORE the grove base
carriers — carriers are precisely what expose these sockets, and four new
ones would enlarge this surface from 15 references to several dozen
before it is migrated.

Item 29 ruled that **the DTS label is the naming authority for every
rig→shield string reference**. It reached `config:`, `params:` and
`wires:`. It did not reach this one, which is the largest of the four.

## 1. What resolves by node name today

`analyzer/sockets.py`'s `resolve_one` splits the ref and looks the
exposed half up in a dict keyed by NODE NAME:

```python
carrier_name, _, exp_name = ref.partition(".")
exposed = carrier.shield.exposes.get(exp_name)
```

Its miss diagnostic lists `sorted(carrier.shield.exposes)` — node names —
and `_parse_exposed` (`shields.py`) still carries the
`node.labels[0] if node.labels else node.name` fallback that item 29
killed everywhere else. **It is the last surviving instance.**

Census, re-derive before trusting: **15 references**, 12 corpus + 3
fixture (`grep -rn 'socket: .*\.' boards/rigs scripts/rigc/tests/fixtures`),
against **8 exposed-socket nodes**:

| shield | nodes |
|---|---|
| `arduino_uno_click` | `mb1`, `mb2` |
| `i2c_mux` | `ch0`, `ch1`, `ch2`, `ch3` |
| `mikrobus_span_adapter` | `combined` |
| `fixture_span_bridge` (fixture) | `combined` |

## 2. THE KEY FACT — this is far cheaper than backlog item 30 predicted

The backlog entry says closing this means "labelling 8 nodes, migrating
15 references, and moving goldens". **The middle and last are avoidable,
and the reason is worth stating rather than discovering.**

Every one of those 8 node names — `mb1`, `mb2`, `combined`, `ch0..ch3` —
is ALREADY a syntactically valid DTS label (`[0-9a-zA-Z_]+`, no hyphens).
So label each node **with its own current name**:

```dts
mb1: mb1 { compatible = "socket,mikrobus"; … };
```

and every existing reference keeps working — resolving by LABEL now,
where it used to resolve by node name. **Zero of the 15 references
migrate. No golden moves.** The two-spellings ambiguity closes anyway,
because after this the label is the only accepted spelling; it merely
happens to equal the old node name for today's corpus. A future carrier
author who labels a node differently from its name gets the label rule,
and only the label rule.

Take this route. If you find yourself renaming references, stop and
report — the premise is wrong.

## 3. WHY the golden question is sharper here than in item 29

Item 29 could keep internal keying on node names because those keys were
invisible dict keys. **This ref string is not invisible**: it becomes
`BoardSocket.label` in `compose_socket`, and from there it reaches

- the **config sheet's socket column** (user-facing),
- `path` for the MULTI-PARENT composition (`quail_eth_span`'s
  `span.combined` — the single-parent path anchors on
  `exposed.name` instead),
- `scope_path`, the address-scope key for a mux channel
  (`nucleo_mux_farm`'s `mux_1.ch0`),
- and diagnostics that quote a parent socket's label.

That is exactly why §2's label-equals-name choice matters: it keeps every
one of those strings identical, so the change is a pure lookup-authority
change with no emitted consequence. **Verify that claim rather than
assuming it** — the goldens are the check, and they must all be
byte-unchanged.

## 4. What to change

1. **A label-keyed lookup for exposed sockets**, mirroring
   `Shield.config_element`'s shape from item 29. Internal keying
   (`Shield.exposes`, `exposed.name` in paths and nexus labels) stays
   node-name — the same §5 rule item 29 established; only the rig-facing
   lookup moves.
2. **The miss diagnostic lists LABELS**, not `sorted(self.exposes)`.
3. **`_parse_exposed`'s fallback becomes a loud error** via the existing
   `_require_label` helper (`shields.py`), which already serves devices,
   pads, straps and jumpers. This is the last call site it was missing.
4. **The 8 nodes gain labels** equal to their node names (§2).
5. **`remove-wire-missing_b.yml` migrates**, the debt item 30 carries:
   its `remove-wires:` endpoints are still spelled `x.sq → y.led-2`, the
   pre-item-29 node names. `dl_led2` exists as a label, so the coherent
   spelling is `x.dl_sq → y.dl_led2`. **This one DOES move a golden** —
   `find_wire` matches the raw endpoint pair and the reject golden quotes
   it verbatim. Hand-edit it (`RIGC_REFREEZE=1` is BLOCKED) and verify
   BOTH ways: it must fail before the edit and pass after. That is the
   slice's ONE intended golden change; every other golden byte-unchanged.
   Trim the file's comment while you are there — it is one unwrapped
   ~200-character line, out of keeping with the tree.

## 5. Tests

- The label resolves; **the node name is refused when it differs from
  the label**, with the diagnostic naming the valid labels. Today's
  corpus cannot show this (label == name everywhere), so it needs a
  FIXTURE carrier whose exposed node's label differs from its node name
  — that fixture is the only real proof the authority moved.
- An unlabeled exposed node is a loud error (§4.3), with its sentence.
- `remove-wire-missing`'s pair still resolves after §4.5.
- Golden result stated as CHECKED: one intended change, everything else
  byte-unchanged.

## 6. Acceptance criteria

1. `socket: <carrier>.<exposed>` resolves by label; a differing node name
   is refused with a sentence listing labels.
2. An unlabeled exposed socket node is a loud error.
3. All 8 nodes labelled; **no reference migrated** (§2).
4. Exactly ONE golden moves — `remove-wire-missing_b`'s — hand-edited and
   verified both ways. Every other golden byte-unchanged, checked.
5. `_require_label` now serves every model object that carries a label;
   no `labels[0] if … else` fallback survives in `shields.py`. Grep and
   state the result.
6. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **718**, integration **268**, coverage **93%** (2026-08-14, `5e8ded6`).
   Re-derive rather than carry.

## 7. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criteria 4's
byte-unchanged claim across the corpus). Confirm its `@pytest.mark.build`
marking before claiming it. The driver runs the full gate once, after
review.

Brief the reviewer to MUTATION-CHECK: restore the node-name lookup (the
fixture test of §5 must fail on the SENTENCE, not merely on a resolution
failure); delete the §4.3 error (its test must fail); revert
`remove-wire-missing_b` (its golden must fail).

Standing rules: an implementor's report is a HYPOTHESIS. Trace every
reader of `exposes` by grep AND run. Run negative controls IN-TREE.
Purge `__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. Dispatch as
`general-purpose` on **sonnet** from a session rooted at `/wrk/z/ws-up`.
