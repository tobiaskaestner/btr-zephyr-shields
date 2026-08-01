# Front-End Trial — S5 + S7 + S3 in Both Candidates

Written 2026-07-17 per the decision protocol in `conventions.md`. Both
candidates share `common-dts/` (connector types, templates, board socket
fragments) — **the candidates differ only in the rig topology file**, which
makes the comparison narrow: 4 files decide it
(`candidate-1-dts/*.rig.dts` vs `candidate-2-hybrid/*.rig.yml`).

Smoke-tested: candidate-1 files preprocess with CPP (`-I zephyr-rigs/include`,
real `dt-bindings` headers) and parse with **stock dtlib** (37 / 44 nodes);
candidate-2 files are valid YAML.

## Findings while authoring (model corrections — candidate-independent)

1. **`/rig-types/ { … }` is NOT valid DTS.** Top-level items are only
   `/ { … }` and `&label { … }`. Corrected spelling everywhere:
   `/ { rig-types { … }; };` — conventions.md updated. (Found by dtlib parse
   failure; exactly what the trial is for.)
2. **CS pools have two shapes.** mikroBUS: one dedicated CS position per
   socket. Arduino R3: an *ordered candidate list* (`D10, D9, D8` — any
   digital pin can be CS by shield convention). "Pool = ordered candidate
   positions" generalizes both; the mikroBUS case is a 1-element list.
3. **Third CS provenance flavor.** Data Logger's CS is *fixed by copper* at
   D10 → `rig,cs-position = <&ar3_d10>;` pins the allocation. Flavors now:
   socket-dedicated (mikrobus), pool-allocated (generic arduino SPI module),
   copper-fixed (this shield). All three are pool allocation with different
   constraint strength.
4. **Stackable connector types.** S7 needs two shields on ONE Arduino socket —
   stacking headers is pass-through by construction. mikroBUS sockets take
   exactly one module. New connector-type attribute `rig,stackable`; the
   mating check allows N consumers on stackable types (net merge is identical;
   claims still checked individually). → folded into ontology (Connector).
5. **`#gpio-cells` on gpio-function positions** keeps template properties
   shaped exactly like their bindings expect (`int-gpios = <&mb_int 0
   GPIO_ACTIVE_LOW>`).
6. **Board fragments can reuse the existing board nexus** (`"&arduino_header
   8"`) instead of repeating pin data — the Nucleo fragment does; Quail (no
   suitable per-socket nexus labels upstream) binds SoC GPIOs directly.
7. Cosmetics: `instance@N` without `reg` is fine for dtlib (source never
   meets dtc); repeated `#include` of type files merges idempotently, no
   guards needed.

## Verified strengths per candidate

**Candidate #1 (pure DTS):**
- Phandle pairs WORK mechanically: dtlib's `to_nodes()` returns
  `[instance-node, template-node]` — R24 resolution is a two-element lookup,
  no custom reference syntax, and dangling references fail at *parse time*
  with file:line.
- One language end to end; instance file participates in the same label
  namespace as templates.

**Candidate #2 (YAML topology):**
- S5 topology: 24 lines vs 35, and reads like the assembly instruction it is.
- `pin: {addr_strap: 0x49}` vs `rig,pin = <&tc_addr_strap 0x49>` — same
  meaning; YAML names the strap locally (loader must resolve it *within the
  named template*), DTS references it globally (parser-checked but the global
  label namespace is exactly what makes prefix discipline necessary).
- Symmetry: `rig.yml` next to `board.yml`/`shield.yml`; schema via
  JSON-schema like the rest of Zephyr's metadata; the board reference is a
  plain string in a file that is *all* plain strings (consistent, vs Conv. 4's
  strings-inside-a-phandle-language).

## Friction observed

- **Candidate #1:** the global label namespace forces prefix discipline
  (`mb_`, `ar3_`, `tc_`, `dl_`…) across every included file — it works but
  scales poorly and errors surface as "label redefined" far from the cause.
  `rig,binds-*` mixed phandle/string arrays are as ugly as predicted.
- **Candidate #2:** dotted references need resolution rules we must define
  and implement: `logger_1.sq` — search scope (pads? config? devices?),
  uniqueness within a template, nesting syntax (`carrier_1.sock2.pad`?).
  Candidate #1 got all of this from dtlib for free. Also two languages in
  one repo (topology YAML, payloads DTS) — a real, if familiar, seam.

## Standing (pre-prototype)

| Criterion | #1 DTS | #2 hybrid |
|---|---|---|
| Topology readability | ok | **better** |
| Reference checking | **parse-time, free** | loader work, TBD quality |
| Schema enforcement | custom checker either way | **JSON-schema, trivial** |
| Ecosystem symmetry | — | **rig.yml completes the pattern** |
| Language count | **one** | two (but payloads were DTS anyway) |
| R24 story | **proven today** | designed, not yet proven |

Lean: **#2 for the human surface, provided the loader's reference resolution
and error quality reach what dtlib gives #1 for free.** That is now the
decisive open question → the expander prototype should implement the loader
for BOTH (same rig model) and compare error output on seeded mistakes
(dangling instance ref, wrong socket, template typo). Verdict then.

## S3 seeded-error showcase (added 2026-07-19)

Third trial piece per NEXT-SESSION step 1: `s3-stacked-loggers` in both
candidates (`candidate-1-dts/s3-stacked-loggers.rig.dts`,
`candidate-2-hybrid/s3-stacked-loggers.rig.yml`). Unlike S5/S7 this rig is
**deliberately unrealizable** — the SOURCE is well-formed (verified: CPP +
stock dtlib clean, 16 nodes, both `rig,shield` phandles resolve to the one
shield definition, `int1-gpios` plug phandle resolves; candidate-2 YAML
parses) and every defect is physical, so both loaders must carry it into the
rig model and the *analyzer* must reject it. This is the primary
diagnostics fixture for the loader comparison.

Expansion contract (also in the .rig.dts header comment):

| # | Kind | Fact | Expected outcome |
|---|---|---|---|
| — | mating | 2 consumers on `nucleo_ard` | accept (`socket,stackable`) |
| — | net | LEDs D3/D4: 1 driver (MCU) + 2 listeners | accept (R22) |
| E1 | address | `rtc@68` unary domain {0x68} ×2 on ONE i2c scope | **fatal**, physically worded: PCF8523 has no address-select pins; name the scope (`&i2c1` via `socket,i2c`), both instances, and the fix space (second bus / mux (S8) / drop one) |
| E2 | pool | SD CS copper-fixed D10 (`shield,cs-position`) ×2 | **fatal**: same dedicated net claimed twice; copper-fixed defeats the D10,D9,D8 candidate list; no jumper modeled |
| W1 | roles | both RTC INT1 endpoints drive D7 | today: 2-driver conflict (R22); **refinement candidate**: roles gain a drive-type so open-drain wired-AND downgrades to a warning. Prototype may emit as third error until refined |

Comparison note: E1/E2/W1 are candidate-independent (they live in the shared
shield + board files), so what the comparison measures on S3 is purely how
much *source location and naming quality* each loader can attach to the same
object-model facts (dtlib file:line + labels vs YAML path + dotted names).

Housekeeping: `common-dts/rig-types/` and `common-dts/templates/` (superseded
v1 leftovers, renamed in pushback round 1) removed 2026-07-19; no trial source
referenced them.

## Expander prototype results → FRONT-END VERDICT (2026-07-19)

Prototype in `scripts/` (terms per `architecture.md`): shared rig model,
loader per candidate, analyzer + emitter behind the strong contract. Runner:
`scripts/run_trials.py`; full side-by-side report: `scripts/out/comparison.md`
(generated). Facts, all machine-checked:

1. **Front-end neutrality holds.** S5 and S7 through both loaders produce
   **byte-identical** outputs (overlay + config sheet + expectations).
2. **S5 golden match.** Overlay equals the playbook golden sketch:
   `cs-gpios = <&gpioa 3 …>, <&gpioe 0 …>`, `nor@0/@1` with matching `reg`,
   sensors at 0x48/0x49, strap sheet "socket 3 ADDR state 0 / socket 4
   state 1". **R18/R7 verified**: reversing instance declaration order →
   byte-identical outputs.
3. **S3 contract met.** Both candidates: loader accepts (well-formed
   sentence), analyzer rejects with E1 (0x68 ×2, physically worded, names
   scope + both instances + fix space) and E2 (copper-fixed D10 ×2), plus
   the anticipated third net error carrying the open-drain refinement note.
   Physics diagnostics are candidate-independent as designed — identical
   wording, only source-ref syntax differs (DTS label vs YAML key path).
4. **The decisive comparison — language-error quality — came out INVERTED
   from the pre-trial framing.** "Parse-time, free" (candidate-1's core
   advantage) is real but WEAK: stock dtlib resolves cell-value references
   (`<&logger_9 …>`) in post-processing, where the error carries only the
   node path — **no file:line, no candidate list, first error only**
   (verified in dtlib source; statement-level refs do get file:line).
   Candidate-2's hand-built resolution reports file:line + key path +
   "known X: …" candidates on every seeded dangling reference (m0, m1, m3).
5. **The hard case needed hand-written code in BOTH.** m4 (cross-pair:
   `<&counter_1 &dl_sq>` — both labels exist, the pair is wrong) is
   invisible to dtlib; both loaders implement the same check by hand,
   equal quality. Exactly where candidate-1's freebie ends, the candidates
   converge.
6. **The feared candidate-2 cost was small.** Dotted-reference resolution
   (`instance.node`, scope = pads ∪ devices ∪ straps, unique-within-shield)
   incl. error reporting: ~60 lines (`loader_yml._resolve_dotted`). YAML
   composer marks give line-accurate refs.

**Verdict: candidate #2 (rig.yml hybrid).** The pre-registered criterion
("#2 for the human surface, provided the loader's reference resolution and
error quality reach what dtlib gives #1 for free") is met with margin — the
loader didn't reach dtlib's error quality, it exceeded it. Candidate-1's
remaining advantage (one language end-to-end) does not outweigh: better
topology readability, ecosystem symmetry (`rig.yml` completes
`board.yml`/`shield.yml`), JSON-schema validation, no global-label prefix
discipline, and now demonstrably better diagnostics. Shield payloads and
board fragments stay DTS in both candidates — the verdict changes exactly
one file per rig.

Caveat recorded for fairness: candidate-1's message quality ceiling is not
dtlib-fundamental — a patched dtlib could attach file:line to cell-value
reference errors — but "stock dtlib, zero new code" WAS candidate-1's
pitch; patching it forfeits the advantage the verdict was waiting on.

Verdict recorded per the decision protocol (conventions.md); **ratified by
Tobi 2026-07-20** — conventions.md rewritten to v4 around `rig.yml`.

### Conv. 8 normative example (added 2026-07-20)

`candidate-2-hybrid/s7-sqw-counter.rig.overlay` — the rig's optional DT
payload, hand-authored beside the `.rig.yml`. Exercises rig-owned alias
selections (`rtc0 = &logger_1_dl_rtc`, …) onto **generated** instance
labels. Verified mechanically: every `&`-reference in the overlay is a
label emitted in the generated overlay (`<instance>_<shield-local label>`
composition). Full dtc resolution is left to the real build (the generated
overlay references board labels that need the whole board tree); the
prototype never parses `rig.overlay` — it is output-regime by contract.

## Pushback round revisions (2026-07-17, applied and re-verified)

All files reworked per Tobi's four pushback points; conventions.md rewritten
as v2. Summary of the deltas:

1. `rig-types/` → `connector-types/`; `templates/` → `shields/`.
2. Connector types slimmed to the **logical view**: links (kind implies
   addressing) + claimable positions with `connector,index`; bus member pins
   deleted. S5 translation unit shrank 37 → 25 nodes.
3. `rig,attach` → **bus membership by parentage** (proxy nodes `i2c { }`,
   `spi { }`); authored `reg` = fixed/pinned, omitted = allocated/domain.
4. **Entity-scoped naming**: `connector,*` / `shield,*` (incl. `shield,plugs`)
   / `socket,*` / `rig,*`.
5. Board realization moved into the **board's own DT** as typed socket nodes
   (`compatible = "socket,mikrobus"`, socket IS the gpio nexus, real
   phandles) with legacy labels for migration; v1's string-encoded
   `rig,binds-*` deleted. New rule: in-tree refs = phandles, cross-tree refs
   (`rig,board`, `rig,socket`) = strings. Expander now reads the board DT
   (accepted trade).

Re-verified after rework: both candidate-1 rig files CPP+dtlib clean, phandle
pairs still resolve; board fragments parse with real phandles against
`_soc-stubs.dtsi`; candidate-2 YAML updated (`shield:` key, board socket
labels) and parses. Note for the comparison: the candidates now share even
more — board socket nodes moved out of rig source entirely, so #1 vs #2
differs in exactly one file per rig.

## Pushback round 2 revisions (2026-07-18, applied and re-verified)

6. **Connector types are bindings, not devicetrees.** The v2 type dtsi files
   had no structural connection to their use sites (`ar3_i2c` vs `socket,i2c`
   vs shield proxy `i2c` related only by prose). Deleted `connector-types/`;
   a type is now `bindings/socket,<type>.yaml` (edtlib-validates board
   sockets) + `bindings/plug,<type>.yaml` (loader-validates shields; declares
   the proxy↔socket,<name> pairing once) + `include/dt-bindings/connector/
   <type>.h` (position indices — single source shared by board gpio-map and
   shield references). Generalizes the upstream arduino-header-r3
   binding+header pattern from pins to links.
7. **Plug node as position reference frame.** Shields carry `shield,plugs =
   "<type>"` (string, compatible-style) + a local `plug` node;
   `int-gpios = <&dl_plug ARDUINO_HEADER_R3_D7 …>` — in-tree phandle, header
   constant, reads as "my connector's D7."
8. **Address authority rule.** Shield declares address *domains* (copper);
   rig file owns the *selection* (`rig,pin` / `pin:`); expander is sole
   author of `reg` + unit-address in output, always as a matching pair —
   non-singleton-domain and pool-addressed source nodes carry neither.
   Fixed-address duplicates on one scope stay a hard *rejection* (R9), not
   an assumption that shields can re-address.

Node-count trend for S5 rig source across rounds: 37 (v1) → 25 (v2) → 17
(v3). Each abstraction removal made the source smaller.

Re-verified: rig files + board fragments CPP (with
`-I common-dts/include`) + dtlib clean; phandle pairs resolve; all four
binding YAMLs parse.

## Pushback round 3 (2026-07-18): deferred-address ergonomics

9. **Omission read awkward; language-extension placeholder rejected;
   `shield,addr-from` adopted.** Deferred-address devices now point at their
   resolver (`shield,addr-from = <&tc_addr_strap>`, device→strap — replaces
   strap-side `shield,selects`; `nvmem-cells` precedent). Schema: exactly one
   of `reg` / `shield,addr-from` on addressable-bus devices → forgot-reg is
   detectable.
10. **Symbolic unit-addresses are dtlib-legal** (tested): `sensor@addr_strap`
   parses; dtlib lowercases the unit-address (`@ADDR` → `@addr`; use
   lowercase); `@{addr}` and `@$(addr)` fail (real placeholders need the
   grammar fork — rejected). Adopted as optional documentation convention,
   linted to match the `addr-from` target. Verified in temp-click:
   `sensor@addr_strap` + `shield,addr-from` parse and resolve.
