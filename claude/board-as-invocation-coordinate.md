# Board as invocation coordinate — `--board X --rig Y`

STATUS: **forward-looking design exploration** (Tobi + driver, 2026-07-29).
NOT a change of action for the queued tasks (R2 → shield library → analyzer →
emitter → cutover proceed as planned). The one near-term consumer is the R2
brief: read §6 before writing it. The differential goldens pin today's
behavior until cutover; everything here lands, if it lands, as deliberate
post-cutover steps.

Origin: Tobi's observation after the R1 session — most board variants exist
only to allow different boards inside the rig, so maybe `board:` inside
rig.yml is the wrong long-run home, and the invocation should be
`west build --board some-board --rig some-rig`, mirroring today's
`--board some-board --shield some-shield`.

## 1. The reframed ontology (Tobi, 2026-07-29)

**Rigs aren't boards. Rigs are a topology/assembly of SHIELD INSTANCES.**
When shields were promoted to templates (slice R, `shield-templates`), the
*instance* spot was left empty — the rig is what fills it, not a
generalization of the board. The lift `a → [a]` in ontology §7 was
misattributed: it is not board → rig, it is **shield instance (a default,
anonymous one) → rig**. Upstream `--shield` is the degenerate rig — one
anonymous instance on the well-known connector — not upstream `--board`.

Consequence: the build coordinate factors as a **product, `board × rig`**
(board = base coordinate, rig = modifier), replacing the containment
`rig ⊇ board` ("the rig owns the board", mechanized in `boards.cmake`'s
RIG/BOARD exclusivity FATAL). Tobi's assessment: design process isn't
linear and this may not be the eventual end, but it is **strictly better
than what we had**.

Ontology §7 is NOT yet rewritten — that rewrite is a deliberate step, and
this document is its input. The old lift's testable laws are replaced by
TWO identity laws:

- **Empty rig ≡ plain board** (saferail 11, survives unchanged):
  `--board b --rig <empty>` produces byte-equal `zephyr.dts` to `--board b`.
- **Singleton rig ≡ upstream shield** (NEW — the law the reframing
  predicts): `--board b --shield s` ≡ `--board b --rig <one default-placed
  instance of s>`. This is the instrument for the §7 rewrite.

## 2. The twister argument (and why it needs the product coordinate)

Under `board × rig`, a rig test needs **zero twister changes**: twister
keeps supplying the platform (= board), and `testcase.yaml` simply carries
`extra_args: -DRIG=some-rig`. No third entity gets wired through twister.

Sharpened: under the CURRENT design this trick is **impossible, not just
awkward** — twister always passes the platform, and `boards.cmake:97`
FATALs on `-DRIG` + `-DBOARD` even when the values match. The product
coordinate is the *prerequisite* for twister-for-free, not merely
friendlier to it. (The parked "platforms ARE rigs" story from the old lift
dissolves accordingly: platforms stay boards; rigs ride as args.)

## 3. What pushes back (the challenge round, 2026-07-29)

Recorded so the costs stay visible:

- **Rig-as-thing.** "A rig contains at least one board" made the rig a
  concrete assembly (config-sheet.md is wiring instructions for a physical
  thing). Under the product, a rig is a schema; the thing exists per
  (board, rig) application. But S2's dual-host `ard_datalogger` already
  crossed this line — with variants, the rig name already isn't one
  physical thing. The proposal opens what variants made closed.
- **Closed-world enumeration.** Today every buildable tuple is declared:
  `west rigs` enumerates, goldens freeze tuples, CI builds all. Under
  `--board` the valid set is open. Validation does NOT regress (the
  analyzer already validates per-configure against the real board DT, and
  incompatibility is a clean phys reject); what's lost is the declared
  target list — recovered as a *query*, see §5.
- **The socket map loses its home** — resolved in §4, the main design
  problem.
- **Per-board fragments lose their filename axis.** Variants carry
  `<rigname>_<variant>.overlay/_defconfig`; a free board has no declared
  name to construct from. Upstream shields' `boards/<board>.overlay`
  existence-checked discovery is the adoptable precedent
  (construct-then-check-exists does not violate Q6).
- **The `/rig` extension target.** Today `list_rigs.py` resolves
  `nucleo_f401re/stm32f401xe/rig`; the user never types it. Under
  `--board`, either users name the extension target, the machinery infers
  the `/rig` qualifier, or (long run) boards carry typed sockets natively
  (the recorded native-socket-board gap is this cell).
- **The argument FOR, from inside the current design:** the flat
  `variants:` axis conflates board-application with genuine topology
  alternates — 3 host boards × 2 population variants = 6 entries with
  fragment duplication. `--board` separates the axes; variants return to
  topology alternates only.

Middle ground held in reserve: keep a declared default board (and named,
pre-validated applications) while allowing `--board` as the anonymous
application. Preserves enumeration for declared tuples.

## 4. The socket map — resolution

The precise question: **whose vocabulary are socket names?** Three answers
coexist today: board DT labels used directly (corpus majority —
`quail_sock1`, `nucleo_ard`), rig-abstract names bound per-variant (S2:
`ard` → `nucleo_ard`), instance-scoped names (`mux_1.ch0`). The third is
the tell — the design already has an unnamed **provider rule**:

> A socket is named by whatever provides it. Shield instances provide
> sockets as `<instance>.<socket>` — instance names are rig-owned, so those
> references are ALREADY board-agnostic. The board is the root provider,
> and the only one whose socket names leak board identity.

Fix, in order of preference:

1. **Conventional labels per connector type** (the main mechanism). Board
   rig-extensions declare typed socket nodes under a documented per-type
   naming convention: singleton types bare (`ard`), multi-socket types an
   indexed family matching the silkscreen (`mikrobus_1..n`). Content
   references conventional names directly. Two properties make this cheap:
   - `loader_yml.py:1028` is `socket_map.get(value, value)` —
     **lookup-else-identity**. A conforming board needs NO map; the map
     becomes dead weight, not wrong. Identity is already the
     corpus-majority path.
   - **DT allows multiple labels per node**: `frdm_ard: ard: connector {…}`.
     Conformance is ADDITIVE (add the alias, rename nothing); a
     nonconforming board is fixed once, at the board, for all rigs.
   - **Lintable**: a check over board rig-extensions — every `socket,*`
     node carries its type's conventional label — same move as
     `test_layer_discipline.py`.
2. **Unique-by-type inference as degenerate sugar ONLY.** `socket:` may be
   omitted iff exactly one board socket mates the shield's connector type.
   Exists to make the singleton identity law hold (upstream `--shield`
   names no socket). Mirrors R18's allocation philosophy: free unless
   pinned. NOT the general mechanism — quail's four mikrobus sockets kill
   that.
3. **Escape hatch, only when a real case arrives:** per-board binding file
   in the rig dir (`boards/<board>.sockets.yml`, existence-checked — the
   same slot the per-board fragment story needs). Don't build ahead of
   need; alias labels cover everything we control.

Compatibility then IS the analysis: "board declares no socket
`mikrobus_3`" is a clean phys reject per configure.

## 5. `--boards-for` — enumeration as derived data (Tobi: ship it)

The closed-world enumeration comes back as a **query instead of a
declaration**: `west rigs --boards-for <rig>` scans board rig-extensions,
censuses their typed socket labels against the rig's socket references and
its shields' connector types, and prints the conforming boards.
**Upstream has wished for exactly this for years** — "which boards does
this shield/sample run on" has no answer today except hand-maintained
twister `platform_allow` lists. We can ship it with ease: the inputs
(list_boards board census + typed socket nodes + the rig's requirement
set) all exist in our pipeline. The inverse query (`--rigs-for <board>`)
is the same census read backwards. Feeds twister platform selection
directly (generate/verify `platform_allow`). This is the same move that
made BOARD derived data — pointed the right way this time.

## 6. Code map + rigc R2 seam guidance (the actionable part)

Board identity enters at exactly TWO doors; everything downstream is
already board-parametric:

- **Door 1, build entry:** `cmake/boards.cmake` step 1 → `list_rigs.py`
  query mode → sets `BOARD` + guards.
- **Door 2, expander model:** `loader_yml._resolve_board` → `rig.board`,
  surfacing only as `RIG_BOARD` in context.cmake (`cli.py:213`) and as the
  standalone-mode board→dts discovery fallback. In the cmake path the
  analyzer receives `--board-dts` threaded from cmake's own resolution.
- **Inert to rig.yml:** analyzer (signature takes `board_dts` path),
  emitter, shields, ctypes_registry, dtsio, edt_build, board_edt/boarddt,
  diag — the entire downstream consumes (model, board DT).
- **Mechanical change surface for the product coordinate:** delete
  boards.cmake step-1 inference + both guards; board column optional in
  list_rigs.py; loader takes the board injected instead of resolving it;
  context.cmake handoff shape unchanged; analyzer/emitter ZERO.

**R2 brief guidance** (architecture, not behavior — the goldens pin the S2
vocabulary until cutover: `ard_datalogger` corpus rows, the mapping-entry
rejects, `content-file-carries-sockets`, `revision-carries-board`):

1. Metadata resolution produces a **`SocketBinding` value** (today: the
   selected variant's map; semantics `get(name, name)`). One constructor,
   one place.
2. The binding applies at **exactly one named seam**, and NOT inside the
   delta engine — rigexp learned this the hard way (S2 had to fix the map
   applying only to fragment-restated instances). The content/delta engine
   merges abstract references and never sees a board label.
3. The map's **diagnostic family stays in one module** so frozen wording
   survives a mechanism swap.

Then the eventual move to conventional labels + open board is a
constructor swap: the S2 mapping vocabulary retires as a cutover-class
step (goldens refreeze, fixtures retire) and the content engine, analyzer,
emitter, and reject-corpus anchors never notice.
