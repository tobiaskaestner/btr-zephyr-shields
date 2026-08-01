# Analysis — the unit test layer

## STATUS CHANGED 2026-07-28: the SLICING here is SUPERSEDED; the ANALYSIS is input to `rigc`

Tobi's ruling: **rigexp's production code is FROZEN and will not be touched.**
Instead rigexp — including its tests — is the BLUEPRINT for building `rigc`
from scratch in its own `scripts/` subfolder, in proper TDD style, with
`tests/unit` and `tests/integration` subfolders. The loader/analyzer/emitter
design stays; testable design gets the attention it did not get the first time.
That is a NEW SESSION's job and needs its own brief.

So slices **U1/U2/U3 below are DEAD** — every one of them proposed extracting a
seam inside rigexp, which is now excluded by that ruling.

**What survives, and it is the valuable half:** everything in this document
about WHY the seams are missing and WHAT the durable contracts are is exactly
the input `rigc`'s design needs. Specifically:

- the three unit-test-hostile shapes, measured (see "The testability
  diagnosis") — `rigc` should be built so none of them appear;
- the `cs-gpios` walkthrough, which is the worked acid test for "the tests tell
  the story of the design", and names the value-shaped contract hiding inside
  `_allocate_cs`;
- the capability-naming principle for test modules;
- the stable-contract test, and the list of what does and does not qualify.

Read this as a design input, not a work plan.

---

Original brief follows. Ratified by Tobi 2026-07-28 as step 2 of the plan in
`test-instrumentation-brief.md`; step 1 (reclassifying the CLI-driven rejects)
landed as `9983e27`.

## Ratified inputs

1. **A unit test uses NO subprocess.** Reaching a unit through the front door
   (the CLI) has already made it an integration test. Landed.
2. **A reject is not a unit concern.** A reject is an OUTCOME against a
   SCENARIO; scenarios do not exist at unit level, they are consumed by the
   system. So this layer does not duplicate the reject corpus — it is new
   coverage of a different subject.
3. **Aim at STABLE CONTRACTS, not every private helper.**
4. **FINDING (Tobi): the code itself is not very testable**, and that will bite
   harder as refactorings continue. This brief treats that as a first-class
   deliverable rather than an obstacle — see "The testability diagnosis".
5. **REQUIREMENT (Tobi): the unit tests must tell the story of the design.**
   Asked "where and how is the final `cs-gpios` property calculated?", the
   answer should be *look at the tests that call that functionality*.

Requirement 5 is the one with structural consequences, so it comes first.

## The organizing principle: name modules after the design question

Test modules are named for the CAPABILITY they explain, not the production
module they happen to import:

```
unit/test_cs_allocation.py        not test_analyzer.py
unit/test_address_allocation.py
unit/test_revision_normalization.py
unit/test_controller_identity.py
unit/test_position_indices.py
```

"Where is X computed?" is then answered by finding the module named for X, and
its imports point at the production code. A test file named after a production
module answers "what does analyzer.py do", which is not the question anyone
asks.

This refines `refactor-tests-plan.md` Part A: **unit modules by capability,
integration modules by stage.** The two halves are organized on different
axes on purpose, because they answer different questions.

## Worked example, and the acid test for this slice: `cs-gpios`

Tobi's own question. Today the answer spans SIX sites in FIVE modules:

| where | what it contributes |
|---|---|
| `ctypes_registry._socket_facts:53` | the type-level pool, from the connector binding's `socket,cs-pool` default |
| `board_edt._project_socket:120` | the pool as backfilled by edtlib on a real board socket node |
| `shields.py:169` | `shield,cs-position` per device — copper-fixed CS |
| `shields.py:340` | `socket,cs-pool` on a shield-SYNTHESIZED (carrier/mux) socket |
| `analyzer._allocate_cs:538` | **the algorithm**: copper-fixed wins, else first free position from the ordered pool; plus the `socket.cs_pool if not None else ctype.cs_pool` merge |
| `emitter.py:132` | writes the `cs-gpios` array and the child `reg` together |

**What tests answer the question today?** `frdm_cs_clash` (a `phys-cs` reject)
and the corpus goldens for rigs that happen to have a CS device. All
integration, all asserting frozen text or DTS. Nothing names the algorithm, so
the question is currently answered by reading `analyzer.py`, not by reading
tests.

**Why it is not unit-testable as it stands.** The seam exists BY NAME but not
BY SHAPE:

```python
def _allocate_cs(rig, solved, types, diags):
```

It takes the whole `Rig`, plus `solved` — a mutable accumulator it must find
already populated with sockets and bus labels — and reports through `diags`.
Calling it requires constructing a rig, a shield library, sockets and a
half-solved state: that is building a scenario, which requirement 2 says is
not a unit test.

**The contract hiding inside it** is small and value-shaped:

> given an ordered pool, the set of already-taken positions, and members of one
> SPI scope (some copper-fixed), assign a position to each — or report the pool
> exhausted.

Extracting that is what makes `test_cs_allocation.py` possible, and the
extraction stands on its own as a design improvement: it separates *which
positions are available* (four different sources, all upstream) from *how a
position is chosen* (one rule, Conv. 1).

**Acceptance for the worked example:** after this slice, "where and how is
`cs-gpios` calculated" is answered by `unit/test_cs_allocation.py` —
copper-fixed precedence, pool ordering, first-free selection, exhaustion, and
the pool-merge fallback, each named and asserted without a scenario.

## The testability diagnosis, named precisely

"Not very testable" resolves into three specific shapes, all present:

1. **A mutable accumulator threaded in and written to** (`solved`) instead of a
   returned value.
2. **Whole-model inputs** (`rig`) where a value or a small tuple would do.
3. **Diagnostics as a side channel** (`diags`) rather than part of the return.

Measured: **20 of analyzer.py's 23 functions take `solved` and/or `diags`.**
Only `_role_of`, `_soc_net` and the two string formatters are value-shaped.
`loader_yml.load` is 137 lines; `_allocate_scope` and `_allocate_cs` are 73
each.

Consequence, and it is the crux of this slice: **every candidate unit test
either constructs a scenario (and so is not a unit test) or requires
extracting a seam first.** So this layer is not "write tests against existing
code" — it is a sequence of small, independently justified extractions, each
followed by the tests it makes possible.

**The safety property that makes this affordable:** an extraction must be
behaviour-preserving, and the golden corpus is the proof. Every step must leave
all goldens byte-identical — the same acceptance T0b and T0c used successfully
for cross-cutting refactors. Any golden movement means the extraction changed
behaviour and must be understood before proceeding.

## What "stable contract" means operationally

The test: **would you want this contract preserved if the implementation were
rewritten?**

Qualifies:
- `_normalize_revision` — mirrors hwmv2's own normalization; must not drift
- `parse_header_indices` — the position-index single source of truth
- `recipe_from_build_info` — already unit-tested
- `_controller_label` — the defining-label rule; already unit-tested
- CS position allocation — Conv. 1, a durable rule
- address allocation — the address-authority rule
- `_soc_net` / net identity — sharing IS net identity (ontology)

Does NOT qualify (leave to integration):
- `_resolve_board`'s exact five-way rejection split — this slice's shape, and
  the hwmv2 revision-semantics slice is queued to rewrite the axis block again
- `_apply_delta`'s key dispatch — vocabulary, likely to grow
- diagnostic WORDING — already covered where it belongs, by the emitted
  goldens

`_parse_axis_decl` is the cautionary case: it changed shape twice in three
slices, so pinning its current behaviour would create churn for the very next
feature slice. Test what survives — that a mapping entry is legal only in a
rig's `variants:` list — not the five-way branch structure.

## Slicing

- **U1 — CS allocation.** Extract the position-choosing contract, add
  `unit/test_cs_allocation.py`. The worked example above; do it first, because
  it is Tobi's own acid test and it proves the extraction-plus-goldens
  discipline works.
- **U2 — address allocation.** Same shape (`_allocate_addresses`,
  `_allocate_scope`), same treatment.
- **U3 — the already-value-shaped contracts.** `_normalize_revision`,
  `_check_axis_collision`, `_soc_net`, `_role_of`, plus widening the two
  existing unit tests. No extraction needed; cheap coverage of durable rules.
- **U4 — coverage measurement** over `-m unit` (this is T3, and by then it is
  `coverage run -m pytest -m unit`).

U1 before U2 so the discipline is proven on one capability before it is
repeated. U3 could run any time and is a good filler slice.

## Non-goals

- Converting the 40 integration rejects. They stay; they protect the
  user-facing wording of system verdicts.
- Chasing a coverage percentage. The goal is that every durable contract has a
  named test, not a number.
- Refactoring for its own sake. **Each extraction must stand as a design
  improvement independently of the test it enables** — if it does not, the
  contract probably is not stable enough to pin, and it belongs in integration.

## Open question

Where the unit tests live: `tests/unit/` as a directory, or `test_*.py`
siblings distinguished only by marker. `refactor-tests-plan.md` Part A proposes
directories by component; this brief proposes unit modules by capability, which
fits a `unit/` directory more naturally. Settle when Part A is scheduled — the
two should agree rather than be decided twice.
