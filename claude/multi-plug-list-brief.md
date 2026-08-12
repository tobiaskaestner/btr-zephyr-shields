# List promotion, slice 4 — `-DRIG='shield_a;shield_b'`

**Status:** briefed 2026-08-12, ready to dispatch. The natural
extension of promotion's a → [a] morphism: a promotion target may name
SEVERAL shields, desugaring to one synthetic rig with N instances. The
container is already list-shaped (`Rig.instances`); the loader,
analyzer, and emitter need ZERO changes — this slice is surface only:
parse a list, desugar to N instances, and generalize the singleton
identity law to its induction step.

## 1. The rulings (Tobi, 2026-08-12)

1. **Separator: semicolon.** `-DRIG='eth_click;temp_click'` — mirroring
   upstream `-DSHIELD`'s own cmake-list idiom, which rig promotion
   exists to subsume. The separator stack composes with zero
   collisions: `;` between elements, `:` between options within an
   element, `.`/`,` inside keys and property names. Per-element options
   therefore fall out for free — each element is a complete
   single-shield target string:

   ```
   -DRIG='can_span_click:socket.left=quail_sock1:socket.right=quail_sock2;temp_click:socket=quail_sock4'
   ```

2. **Duplicates are REFUSED first, extended later.** `[a, a]` is
   physically meaningful (stackable connectors; two clicks on two
   sockets) but needs an instance-naming rule the singleton desugaring
   deliberately fixed (instance name = shield name, and instance names
   reach artifacts). Same staging discipline as the 2026-08-08
   `_PROMOTION_OPTS` ruling: a repeated shield NAME in one list is a
   loud error with its own sentence, and the indexed-naming design
   waits for hardware that wants it.

## 2. The grammar

- The `-DRIG`/`--rig` target splits on `;` FIRST, then each element
  parses exactly as a single-shield target does today
  (`<shield>[@rev][:opts...]`) — `parse_promotion_opts` per element,
  unchanged. A one-element list is byte-identical to today's grammar
  by construction (splitting on a `;` that is not there).
- **Every element must be a SHIELD.** An element naming a persisted
  rig — or a both-namespaces name — is refused: a rig already is a
  container, and a list mixing containers with elements has no
  coherent desugaring. Per-element namespace checking reuses
  `both_paths_error`/the existing single-name resolution; the
  "rig-in-a-list" refusal gets its own sentence naming the offending
  element. (Driver decision on the exact wording family — flag it.)
- The desugared rig's NAME (reaches artifacts and RIG_* provenance):
  the element shield names joined with `+` (`eth_click+temp_click`) —
  deterministic, filename- and cmake-safe. Driver decision; flag for
  veto.
- `west build-rig --rig` accepts the semicolon string verbatim;
  additionally accepting a REPEATED `--rig` flag that joins with `;`
  is in scope if argparse makes it a two-line change, out of scope
  otherwise (say which in the report).
- Promotion options on a persisted rig stay refused (standing ruling);
  a LIST is promotion-only by construction since every element must be
  a shield.

## 3. Semantics — everything below the desugaring is unchanged

- One instance per element, named after its shield (unique because
  duplicates are refused), each carrying its own element's
  socket/sockets/params/@rev exactly as the singleton desugaring does.
- Per-element inference: each instance infers independently, with the
  existing per-slot strictness — two same-type elements on a
  two-socket board BOTH refuse (no bipartite matching; strictness per
  element is the design, consistent with every prior ruling).
- Socket exclusivity across elements falls out of the existing
  stackability census: two elements naming the same non-stackable
  socket refuse with the existing message; a stackable one accepts.
- `--boards-for '<a>;<b>'`: a board answers iff the whole desugared
  rig resolves clean — the existing machinery over the N-instance rig,
  nothing new. Assert one positive (a board hosting both) and one
  negative (a board that hosts each alone but not both — socket
  exclusivity), with the REASON asserted, not just the emptiness.
- `--explain` prints the N-instance desugared pair.

## 4. CMAKE HAZARD — the one place this slice can actually break

`;` is cmake's list separator. The RIG cache variable's value now
legitimately contains semicolons, and ANY unquoted `${RIG}` expansion
in `cmake/boards.cmake`/`cmake/dts.cmake`/`shields.cmake` (argv
passing to list_rigs, message() calls, comparisons) silently splits it
into multiple arguments. **Grep every `RIG` use under `cmake/` and
verify each expansion is quoted or list-safe; run the cmake-alone
entry path (`-DRIG='a;b'`) for real** — `test_cmake_alone_entry.py` is
the module that observes this, and it needs one list-target case. If a
fork needs an actual quoting fix, that IS in scope (it is not "cmake
logic", it is the seam carrying the string) — but report it
prominently; if anything beyond quoting seems needed, STOP and report.

## 5. The identity law's induction step

The slice's real acceptance criterion, in the house shape: promoted
`[a;b]` ≡ the two-instance rig.yml carrying the identical assignments.
Extend `test_singleton_identity_law.py` (or a sibling module if the
census machinery fights it — implementor's call, say which and why)
with a SMALL fixed set of representative pairs, not a full N×N census:

1. Two single-plug shields with explicit sockets (e.g. `eth_click` +
   `flash_click` on the law fixture board's two mikrobus sockets).
2. A multi-plug element composed with a single-plug one
   (`can_span_click:socket.left=...:socket.right=...` + a grove/pilot
   shield) — slices 1-3 composing with 4 in one comparison.

Both compare byte-for-byte in the accept branch, partition pinned (the
S4 rule: a comparison law's reject branch checks nothing, so pin which
branch each case is in).

## 6. Explicitly OUT OF SCOPE

- Duplicate elements (ruled: refused; indexed naming is future work).
- Wires between promoted instances (rig.yml exists for that).
- Any twister suite for a list target (suites are per-shield).
- Any change below the desugaring seam: loader/analyzer/emitter/model
  are UNTOUCHED — if one seems to need a change, the premise is wrong;
  stop and report.

## 7. Tests

- `test_promote.py`: list parsing, per-element opts, the duplicate
  refusal sentence, the rig-in-a-list refusal sentence, one-element
  equivalence (a no-`;` target parses byte-identically to today).
- `test_cmake_alone_entry.py`: the §4 list case through the real cmake
  entry.
- `test_boards_for.py`: §3's positive and negative, reasons asserted.
- `test_explain.py`: the N-instance desugared pair, whole-stdout pin
  (the module's existing style).
- `test_list_rigs_cmakeformat.py`: the `{PROMOTED}` line for a list
  target — whole-line pin, per the revved-promoted precedent.
- The law cases of §5.
- Goldens: NEW only; zero existing golden movement (single-target
  paths byte-identical by the one-element-equivalence construction).

## 8. Acceptance criteria

1. Every existing golden byte-unchanged; a no-`;` target's entire
   pipeline output byte-identical to today.
2. The §5 law pairs compare byte-for-byte, partitions pinned.
3. The cmake seam carries a semicolon target intact end-to-end
   (`test_cmake_alone_entry.py`'s list case, real configure).
4. Duplicate and rig-in-a-list refusals fire on their own sentences.
5. `--boards-for` per §3, both directions, reasons asserted.
6. Full gate green (driver-run; floor 88, currently 93).

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + ONE named build
module — `test_cmake_alone_entry.py` (the module observing the cmake
hazard; confirm its build marking before claiming it). Observing
modules: `test_promote.py`, `test_explain.py`, `test_boards_for.py`,
`test_list_rigs_cmakeformat.py`, the law module. Driver runs the full
gate after review. Brief the reviewer to mutation-check: the duplicate
refusal (delete → its test fails on the sentence), the law pairs (gut
the list desugaring's per-element option threading → the §5.2 mixed
pair must fail as a COMPARISON, not drop out of the domain), and the
cmake quoting (unquote one `${RIG}` expansion → the list case must
fail). Standing rules: reports are hypotheses; trace every caller of
the target-splitting seam by grep and run (`resolve_target`,
`_resolve_both_namespaces`, `cli.py`'s `--promote`, and whatever a
grep finds that this list misses — the missed-caller lesson has now
recurred three times); purge __pycache__ after mutate-and-restore;
RIGC_REFREEZE stays blocked.
