# Slice brief — the rig.yml / `<rigname>.yml` split (slices S1, S2)

Ratified by Tobi 2026-07-26 (round record: design-log 2026-07-26h). **Run
this BEFORE the hwmv2-revision-semantics and rig-schema slices, and before
the bridle migration** — see "Sequencing" below for why each.

## The finding, in one paragraph

`rig.yml` is not symmetric with `board.yml` or `shield.yml`: it is the union
of two roles those files keep apart. Metadata files are named after the
entity TYPE (`board.yml`, `shield.yml`, `rig.yml` — the same filename in
every folder) and carry NO hardware description. Content files are named
after the entity INSTANCE and its qualifiers
(`<board>_<soc>_<variant>_<rev>.dts`, `<name>_<rev>.shield`, and —
already — `<rigname>_<variant>_<rev>.yml`). Rigs built the fragment half of
that convention correctly and left the base content in the metadata file, so
the delta fragments have no same-stem base to be deltas of. Both roles being
YAML is what hid this.

## OPEN DECISION, settle before writing code

**The content file's name.** Recommendation: **`<rigname>.yml`**. It is what
the existing fragment names already imply, it keeps YAML editor/schema
association, and a distinct extension would reopen the `.rig.` naming
decision the naming sweep settled. The obvious objection — two files in the
same language means the boundary is convention, not enforced — is answered by
`rig-schema.yaml`: with `additionalProperties: false` on a metadata-only
schema, putting `instances:` back into `rig.yml` fails loudly at discovery.
The split and the schema slice are mutually reinforcing, which is also why
the schema slice must come after this one.

## Target shape

```
boards/rigs/ard_datalogger/          boards/st/nucleo_f401re/
├── rig.yml                          ├── board.yml
├── ard_datalogger.yml               ├── nucleo_f401re.dts
├── ard_datalogger_frdm.yml          ├── nucleo_f401re_<variant>.dts
├── ard_datalogger_2.yml             ├── nucleo_f401re_1_0_0.dts
└── ard_datalogger_defconfig         └── nucleo_f401re_defconfig
```

**`rig.yml` — metadata only.** `name`, `full_name`, `vendor`, `revisions:`,
`variants:`, and the board per selectable coordinate:

```yaml
rig:
  name: ard_datalogger
  full_name: Arduino-header data logger (dual host)
  vendor: btr
  variants:
    default: nucleo
    list:
      - name: nucleo
        board: nucleo_f401re/stm32f401xe/rig
        sockets: {ard: nucleo_ard}
      - name: frdm
        board: frdm_k64f/mk64f12/rig
        sockets: {ard: frdm_ard}
  revisions:
    default: "1"
    list: ["1", "2"]
```

**`<rigname>.yml` — content only**, and board-agnostic:

```yaml
instances:
  - name: logger
    shield: adafruit_data_logger
    socket: ard
```

Fragments unchanged in naming and semantics, now with a base to layer onto:
`ard_datalogger_frdm.yml`, `ard_datalogger_2.yml`,
`ard_datalogger_frdm_2.yml` (revision last).

## Why the board belongs in metadata even though it IS topology

Both readings are right and upstream shows they do not conflict. The SoC name
appears in THREE roles: `soc/st/stm32/soc.yml` registers which SoCs exist at
all; `board.yml`'s `socs:` declares which of them THIS board offers as a
selectable qualifier; and `<board>.dts` `#include`s the SoC dtsi — the
content. Resolution from a qualified target to arch/soc build content is a
NAME LOOKUP into the soc roots, never a parse of the `.dts`; the include is
content that must AGREE with the selection, and `<board>_<soc>.dts` naming is
what keeps them consistent.

Rigs have the same three roles: `list_boards.py` is the registry, `rig.yml`
says which board(s) this family offers, and `<rigname>.yml` uses that board's
sockets. So the board's CONSEQUENCES are topology (the instances reference
its sockets — the `#include` analogue) while its IDENTITY is a coordinate.
Content therefore carries no `board:` at all: it is derived, never declared,
which removes the second source of truth entirely.

## S1 — the move. ZERO semantic change

Content keys (`instances:`, `wires:`, `params:`, `dt-includes:`) move from
`rig.yml` to `<rigname>.yml`. Metadata keys stay. `board:` stays in `rig.yml`
for now (S2 moves it under the axis values). Nothing else changes.

Touch points: `list_rigs.py` (already reads ONLY the metadata keys — see its
own comment about not validating shape, which this slice finally makes
honest), `loader_yml.load` (opens the content file; `deps.see` both),
`cmake/dts.cmake`'s `_rig_yml` build_info key and the static
CMAKE_CONFIGURE_DEPENDS set, every corpus rig folder, every test fixture.

**Acceptance: every tier-1 and tier-2 golden byte-identical EXCEPT provenance
paths naming the rig file.** That is the whole point of slicing it this way —
a pure move is provable, and it gives a clean bisect point before any
behaviour changes. Prove it with `git diff`, do not assert it.

## S2 — board per coordinate, and V2's residue falls out

Three changes, all interlocking:

1. **`board:` moves under each axis value** in `rig.yml` (shape above), with
   the degenerate single-board rig keeping a top-level `board:`. Resolution
   still happens in `list_rigs.py` BEFORE any fragment is read — the
   contradiction that forced the current rejection ("resolve from metadata
   early, override from content late") is gone because there is no late
   override.
2. **The socket map applies to the BASE topology**, not only where a delta
   restates `socket:`. Today `sockets:` is a variant-fragment key and
   `resolve_socket` is reached only from `_apply_instance_patch` when
   `"socket" in item.v` (`loader_yml.py:812`), so abstract socket names only
   work if every instance is restated in every variant fragment — which is
   exactly why this feature's positive path has never been exercised. Move
   the map to the axis declaration and apply it at resolution.
3. **Rule 10 widens.** A non-default axis value contributing only a board
   and/or a socket map — both metadata — contributes something. Today the
   rule demands a fragment FILE and would reject a legal dual-host rig whose
   `frdm` variant needs no fragment at all. The rule's purpose (catch an axis
   value that silently does nothing) survives with two sources of
   contribution instead of one.

**The board-swapping rejection in `_apply_delta` is then DELETED**, not
lifted: a variant no longer carries `board:` in a fragment, so there is
nothing to reject.

**V2 IS FULLY ABSORBED after S2.** Its two residual items were board swapping
and `sockets:` positive-path coverage; S2 delivers the first as a declaration
and exercises the second by construction.

## Golden budget

- **S1**: no new cases. The evidence IS the unchanged goldens.
- **S2**: the dual-host rig as a new accept family — `ard_datalogger` with
  BOTH tuples built for real (`/nucleo` and `/frdm`), tier-1 and tier-2, and
  the frdm tuple carrying NO fragment so it proves content reuse across
  boards. Rejects: a shield needing a bus the selected socket does not expose
  (`nucleo_ard` deliberately exposes no `socket,uart` while `frdm_ard` has
  `uart3` — the same content realizable on one host and loudly rejected on
  the other is the property worth freezing); an axis value contributing
  nothing at all (rule 10 still fires); a socket name resolving under no
  declared map.

Portability is sound by construction, not by the boards happening to be
similar: `ARDUINO_HEADER_R3_D10` is 16 in one shared header and both socket
nodes map that index to their own pin (`&gpiob 6` on nucleo, `&gpiod 0` on
frdm), all 22 positions from the same namespace. A shield says "D10"; only
the resolved controller and pin differ.

## Sequencing, and why this order

- **Before hwmv2 revision semantics**: that slice rewrites the axis
  declaration block. Doing it first would write upstream's revision block
  into a conflated file and then move it.
- **Before rig-schema.yaml**: a schema authored against today's `rig.yml`
  would cement the conflation, and `additionalProperties: false` over a file
  holding topology forces jsonschema to compete with the loader for
  diagnostics the loader does better (line-accurate, candidate lists).
  Afterwards, `rig-schema.yaml` validates metadata only and is genuinely
  symmetric with `board-schema.yaml` — and it becomes what ENFORCES the split.
- **Instead of a fragment-aware resolver for V2**: building V2-residue first
  means building resolver machinery that S2 immediately retires.
- **Before the bridle migration**: rig content moves into bridle there, and
  splitting afterwards would rewrite history that had just been condensed.

## Still unresolved, non-blocking

The socket map is a bridge between abstract topology and a concrete board;
this brief puts it with the board in metadata, on the grounds that a rig
naming `nucleo_ard` anywhere in content is no longer portable and portability
is the property the split buys. The counter-position (it is naming, so it
belongs with content) leaves the proposal intact and moves one key.

Also open, inherited: whether a board that is a nested coordinate should make
the rig target multi-segment (`name@rev/board/variant`, hwmv2's own qualifier
path) rather than the single-segment `name[@rev][/variant]` we ratified. This
brief deliberately does NOT do that — declaring the board per axis value gets
single-source resolution and board swapping without touching the grammar, and
leaves nesting available if a family ever needs both axes across boards.
