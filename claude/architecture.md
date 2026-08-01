# Rigs — Processing Architecture

Defined 2026-07-19 (terms had leaked into conventions.md/requirements.md
undefined; pinned down before the prototype hard-codes them). Names the
components of the rig toolchain, their contracts, and their relation to the
existing Zephyr build machinery. Companion docs: `ontology.md` (the rig
model's schema), `conventions.md` (front-end syntax), `requirements.md`
(R1–R27).

## The pipeline

```
rig source                      candidate-1: rig.dts   candidate-2: rig.yml
(+ shields/*.shield,                    │                     │
 plug,*.yaml bindings)          [loader #1: dtlib]    [loader #2: YAML]
                                        └──────────┬──────────┘
                                                   ▼
                                            RIG MODEL  (syntax-free)
                                                   │
board DT (socket nodes,  ──────────────────────────┤
read via edtlib, Conv. 4)                          ▼
                                               EXPANDER
                                    ┌── analyzer: closure → checks
                                    │              → allocation
                                    └── emitter:  projection
                                                   │
                        ┌──────────────┬───────┴──────┬────────────────┐
                        ▼              ▼              ▼                ▼
                   .overlay      config sheet    expectations   Kconfig fragment
                        │                                        (activation manifest)
rig.overlay (hand-  ────┤  applied AFTER the generated overlay:            │
authored; Conv. 8)      │  references generated labels, dtc resolves       │
                        ▼                                                   ▼
        today's build, UNCHANGED: CPP → dtc/dtlib → edtlib → gen_defines.py → Kconfig
```

## Component definitions

### Rig model

The in-memory representation of *what the rig is*, and nothing else. Its
schema is exactly `ontology.md` §1–2: PCBAs, nets, endpoints with roles,
connectors/positions, matings, claims, address domains, scopes. Two defining
properties:

- **Front-end-neutral.** Both loaders must fill the identical structures —
  this is what makes the candidate comparison honest, and it is the load-
  bearing wall of the front-end verdict protocol.
- **Pre-analysis.** It records *declared* facts only; net-identity closure,
  the scope tree, and conflicts are computed from it by the analyzer, never
  stored in it (ontology §2's "derived, never declared" rule).

Nearest Zephyr analog: `edtlib.EDT` — the semantic object model *of a
devicetree*. The rig model is the semantic model *of a rig*, one level up:
an EDT describes what one MCU sees; the rig model describes the assembly
that projection comes from.

### Loader

Syntax in, rig model out; **one per candidate front-end**. Owns everything
that is about *text*:

- parsing;
- reference resolution (candidate-1: phandle pairs via dtlib; candidate-2:
  dotted names via rules we must define — the decisive comparison);
- schema validation against the `plug,*.yaml` contracts;
- attaching source locations (file:line) to every rig-model fact, so
  downstream diagnostics can point home.

A loader knows nothing about physics: it happily loads the S3 rig, because
two RTCs at 0x68 is a perfectly well-formed *sentence* — it's the world that
rejects it. Nearest Zephyr analog: the dtlib/edtlib front half of
`gen_defines.py`. Candidate-1's loader literally *is* stock dtlib plus our
schema pass; candidate-2's loader is new code, which is precisely why the
verdict hinges on its error quality.

### Expander

Rig model in, the projection out. Owns everything that is about *copper and
physics*. It is also the only component that reads the **board DT** (finds
`socket,*` nodes by compatible — the Conv. 4 trade), because which board a
rig mates against is a fact about the world, not about the rig text. No
Zephyr analog — this is the genuinely new machine; the closest existing
thing in spirit is the human who hand-edits a shield overlay to move a CS
pin today. Two internal stages:

- **Analyzer** — computes the derived facts (net-identity closure, scope
  tree), runs the checks (mating/subset/stackable R20, net roles R22/R23,
  realizability R9), and runs the allocator (device-static addresses, CS
  pools — deterministic, order-independent, pinnable, R18). Output: the
  *solved rig* — rig model + derived facts + allocations + diagnostics.
  Everything that can reject a rig lives here.
- **Emitter** (overlay-emitter) — projects the solved rig into **four**
  outputs, split by consumer: MCU-visible-static → `.overlay`; human-realized
  → **physical configuration sheet**; runtime-discoverable → **test
  expectations** (A6); software-build → **Kconfig fragment** (see below).
  Pure rendering: the emitter never decides anything and never fails on a rig
  the analyzer accepted.

  The first three are the ontology §3 projection (split by MCU visibility).
  The Kconfig fragment is a distinct, build-configuration axis — not part of
  the MCU projection. It is the **activation manifest**: which shield types +
  board the rig instantiates (so their type-level `Kconfig.defconfig` files
  apply — the rig.yml replaces the `--shield` command line), plus any
  rig-derived defaults. It carries **no per-instance driver config**: Kconfig
  symbols are global, so per-device configuration lives in DT, and driver
  auto-enable follows the generated overlay via Kconfig's `dt_compat_enabled`
  / `dt_nodelabel_enabled` functions. An application's `prj.conf` composes on
  top and overrides. (Decided 2026-07-21; see `parked.md` for the settled
  layering.)

## Relation to existing Zephyr technology

| | Role | Zephyr analog | Reused or new |
|---|---|---|---|
| rig source | authoring | shield `.overlay` + `Kconfig.shield` | new syntax, borrowed grammar (DTS or YAML) |
| loader | text → model | dtlib/edtlib parsing | #1 reuses dtlib wholesale; #2 new |
| rig model | semantic IR | `edtlib.EDT` (for DT) | new; schema = ontology.md |
| expander (analyzer + emitter) | checks + allocation + projection | none | new |
| `.overlay` output | MCU-visible projection | shield overlay | **exactly today's artifact** |
| config sheet / expectations | non-MCU-visible rig state | none (README prose today) | new |
| Kconfig fragment | activation manifest + rig defaults | `--shield` list + `Kconfig.defconfig` | generated; rig.yml replaces the shield CLI |
| `rig.yml` | discovery metadata | `board.yml` / `shield.yml` | new; completes the pattern |
| `rig.overlay` | rig-level tree facts (aliases, `chosen`, escape hatch) | user overlay / `EXTRA_DTC_OVERLAY_FILE` | **exactly today's artifact**, shipped in the rig dir (Conv. 8) |
| `west build --rig` | build entry | `west build -b` | extension |

## Integration thesis

1. **The seam with Zephyr is the overlay file.** The emitter's output enters
   the build exactly where `--shield` overlays enter it today (an extra DTC
   overlay at configure time); everything downstream — CPP, dtc, edtlib,
   `gen_defines.py`, bindings validation — runs unchanged and re-validates
   the output. The "two validation regimes" ground rule (conventions.md §2)
   falls out of this seam: the loader validates *source*; the existing
   toolchain validates *output*. The rig source never meets dtc.
   A rig contributes up to TWO overlays at this seam (Conv. 8): the
   generated one, then the optional hand-authored `rig.overlay` — which is
   output-regime content (never loader-parsed, never in the rig model) and
   may reference generated instance labels, resolved by plain dtc.

2. **The error taxonomy follows the component split.**
   - *Loader errors* are language errors: dangling reference, unknown socket
     name, schema violation. Their quality is candidate-**dependent** — the
     open front-end verdict measures exactly this.
   - *Analyzer errors* are physics errors: E1/E2-style, worded at the copper
     level per C6 ("two devices fixed at 0x68 on one bus"), candidate-
     **independent**. S3 measures only how much source-location quality each
     loader threads through to them.
   - The emitter has no error class of its own (see above) — a rig that
     loads and analyzes clean always renders.

## Deliberately undefined (parked)

- **Where the expander runs** — west extension vs. CMake module; the
  prototype is a standalone tool, build integration comes after the S1
  fidelity milestone. (→ parked.md)
- **Discovery** — whether scanning a `rigs/` root (hwmv2-style, `rig.yml`)
  is a loader concern or a fourth component; irrelevant until there are
  rigs to discover. (→ parked.md)
