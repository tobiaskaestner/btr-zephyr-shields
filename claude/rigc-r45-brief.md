# Slice brief — R4.5: loader decomposition, logging skeleton, address extraction

Drafted 2026-07-29 by the driver from Tobi's joint-code-review rulings
(same day, recorded in NEXT-SESSION 2026-07-29 queue item 2) plus R4
review carry-forward M2. **RATIFIED by Tobi 2026-07-29**: RIGC_LOG
env knob, stderr-when-enabled, as written; Part C stays in; execution
mode = sonnet implementor, then **TOBI REVIEWS PERSONALLY** (no opus
round this slice — the slice exists for his code understanding), driver
supports the review and commits after his accept. An INTERLUDE slice,
deliberately: three behavior-preserving changes
whose shared purpose is understandability of the code already written,
before the emitter builds on it.

## Goal

Zero observable change: the full differential stays **94/146 with a
byte-identical red set** and the default gate stays green — the
T0b/T0c zero-golden-churn standard is the acceptance for all three
parts. What changes is the code's shape and its observability.

## Part A — `load()` becomes three phases

`loader/__init__.py::load()` is ~140 lines of linear glue (the same
smell the testability ANALYSIS flagged in the blueprint's 137-line
load). Split along its latent seams:

- **`_resolve_metadata(doc, revision, variant)`** — steps 2–5: rig
  shell, axis declarations + collision, axis resolution, board +
  SocketBinding. Entirely cpp-free.
- **`_gather_content(rig, rig_dir)`** — steps 6–9: content file,
  fragment discovery, rule 10, dt-includes union + probe.
- **`_build_topology(rig, binding, lib, content, deltas)`** — steps
  10–11: stage 0, the two delta stages, invariants.

Rules, non-negotiable:

- **Phase results are VALUE records** (small frozen dataclasses), never
  a shared mutable context object — a "LoadContext" each phase writes
  into is the blueprint's `solved` under a new name and a §6 violation.
  R4's D1 (an aliased mutable crossing a pass boundary) is the fresh
  reminder of why this rule is load-bearing.
- **Diagnostic order is the frozen contract.** The composed order after
  the split must equal today's traversal order; `load()` concatenates
  phase diagnostics explicitly. The D1 LoadError boundary stays at the
  top of `load()`, wrapping all three phases.
- The cpp-free phases get unit tests over synthetic documents — this is
  what finally moves the orchestration-coverage number both reviewers
  flagged (66–68% on `loader/__init__.py`).
- Side benefit to preserve, not undo: the hwmv2 revision-semantics
  slice later lands entirely inside `_resolve_metadata`.

## Part B — the logging skeleton

Stdlib `logging`, hierarchical per-module loggers
(`logging.getLogger(__name__)` → `rigc.loader.axes` etc.), and:

- **stderr purity is the prime constraint.** The package root logger
  `rigc` gets a `NullHandler` (library convention); Python's
  `lastResort` handler otherwise leaks WARNING+ to stderr from an
  unconfigured tree — a golden-corruption hazard. A real handler is
  attached ONLY when **`RIGC_LOG=<level>`** is set in the environment
  (the argv surface is frozen; no new flag). When enabled, records go
  to stderr — enabling logging during a golden-comparing run breaks the
  comparison BY DESIGN and the module docstring says so.
- **The vocabulary rule (ratified in review, restated as the law of
  this part): log records describe the TOOL'S EXECUTION; Diagnostics
  describe the USER'S INPUT.** `log.warning`/`log.error` are reserved
  for tool-internal conditions (a fallback taken, an inconsistency in
  rigc's own state) — never for findings. If a message is about the
  rig/shield/board being wrong, it is a Diagnostic or it is nothing.
- **Level policy:**
  - INFO — lifecycle milestones: the resolved argv, library-scan
    summary (N shields eager, M pending), each `load()` phase entry,
    each analyzer pass entry, board resolved (name → dts path), the
    verdict (accept/reject/refusal) with exit code.
  - DEBUG — per-item results: selected axes, board + socket binding,
    per-instance shield/socket resolution, each allocation decision,
    TU paths, and **the exact argv of every cpp invocation** (dtsio) —
    the rigc-side counterpart of T2's `rerun.sh`.
  - Small value-shaped functions stay silent; their callers log
    results. The log reads as a pipeline narrative, not a call trace.
- Lazy `%`-style formatting in every call (`log.debug("cpp argv: %s",
  argv)`) — zero formatting cost when disabled.
- BSD-3 reader modules use plain `logging.getLogger(__name__)` — stdlib
  only, no product import, boundary intact.
- **The stderr-purity discipline test**: a full `main()` run over a
  rejecting input with `RIGC_LOG` unset emits ONLY renderer bytes on
  stderr while a `caplog` handler observes the records exist; a second
  test proves `RIGC_LOG=debug` attaches a handler. Both subprocess-free.

## Part C — address allocation's value-shaped core (R4 review M2)

Give addresses the treatment CS got. Extract the choosing contract —
*given a scope's address domain, the already-taken addresses, and the
members (some reg-fixed, some strap-pinned, some free), assign each an
address + strap state, or report the domain exhausted* — as a pure
function on small values, with `allocate_addresses` reduced to the pass
wrapper that builds members from the rig and folds results into the
pass's own return. `_allocate_scope`'s threaded pass-local mutable and
its caller-populated `bus_label` precondition go away.
`test_addresses.py` sheds its Rig/Shield/BoardSocket scenarios the same
way `test_cs.py` never needed them; the pass wrapper keeps a
scenario-shaped module like `test_cs_pass.py`. (The R4 review verified
the current behavior byte-correct and the D1 hazard class structurally
absent here — this is design debt, not a bug fix, and the extraction
must not change one byte.)

## Acceptance

A. Full differential (`RIG_EXPAND_COMPILE=rigc`, private basetemp):
   **94/146 and the red set byte-identical** to the pre-slice run
   (diff the FAILED lists). This proves stderr purity end to end, since
   every covered golden byte-compares stderr.
B. Default gate green: frozen 146, rigc unit suite green and grown
   (phase tests, address-contract tests, the two logging tests), mypy
   clean, subprocess-free by the discipline test.
C. Zero edits outside `scripts/rigc/**`. No new dependencies.
D. No log call anywhere carries input-finding content (the vocabulary
   rule) — reviewer-audited, and every log call uses lazy formatting.
E. STOP and report: the phase record shapes, the address-contract
   signature, where each INFO/DEBUG line landed, coverage delta on
   `loader/__init__.py` and `analyzer/addresses.py`, deviations
   flagged.

## Out of scope, deliberately

- Any golden change; any diagnostic wording/ordering change; anything
  the emitter needs (R5).
- Logging in the frozen rigexp; pytest `--log-cli-level` wiring for the
  frozen suite (it already exists there via T2).
- A `RIGC_LOG_FILE` destination (revisit if stderr-when-enabled proves
  annoying in practice).
- The remaining R4 carry-forwards (M6/M7/M8) — they are R5-brief
  material.

## Needs Tobi's ratification

1. **`RIGC_LOG` env knob, stderr-when-enabled** (§B) — including the
   documented caveat that enabling it breaks golden comparison by
   design. Alternative (a file destination) deliberately deferred.
2. **Execution mode.** Standing pattern (sonnet implementor → opus
   reviewer → driver commits), or DRIVER-LED with Tobi reviewing
   interactively — this slice exists for code understanding, so
   hands-on may serve the purpose better; it is also the first slice
   small enough for that to be practical. Driver has no strong
   preference; flag raised because the slice's purpose is unusual.
3. Part C riding along (it is the third behavior-preserving change of
   the same class, but it could split out if the slice should stay
   two-part).
