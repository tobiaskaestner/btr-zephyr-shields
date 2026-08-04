# Unique-by-type socket inference — implementation brief

`board-as-invocation-coordinate.md` §4.2, scoped 2026-08-04.

## 0. What this is

An instance may omit `socket:` **if and only if** the board has exactly
one socket whose connector type mates the shield's `shield,plugs` type.
Zero candidates or two-or-more is an error — never a guess.

Its stated purpose in the design doc is to make the singleton identity
law expressible: upstream `--shield` names no socket, so a rig instance
must also be able to decline to, or `--board b --shield s` has no rig
equivalent to be compared against.

**But do not treat that as the justification.** "It makes a test
expressible" is weak on its own, and the feature has a better case:
under `board × rig`, an instance that omits its socket is the MOST
portable form a rig can take — more portable than conventional labels,
because it depends on the board using no particular label at all. It
works on any board with one mating socket. The identity law then falls
out for free.

The design doc is equally clear on the limit: this is degenerate sugar,
**not the general mechanism**. Quail's four mikrobus sockets kill any
ambition beyond the single-socket case, and nothing here should be built
as if inference could grow into the general answer.

## 1. The rule, and why "exactly one" is the whole design

- **Exactly one mating candidate** → that socket, silently.
- **Zero** → error naming what the board lacks (the shield's plug type,
  and what the board does offer).
- **Two or more** → error listing the candidates and requiring an
  explicit `socket:`.

The strictness is the safety property. Adding a second arduino header to
a board turns a previously-working omission into a LOUD failure rather
than a different build. Inference never picks arbitrarily and never
silently changes its mind. Any implementation that "helpfully" resolves
an ambiguous case is wrong, however reasonable its tie-break looks.

This mirrors R18's standing philosophy — addresses and chip-selects are
allocated automatically unless the author pins them, free unless pinned —
applied to placement rather than to resources.

## 2. Where it must live — the architectural constraint

The predicate already exists: `analyzer/sockets.py::mating_ok(plug_type,
socket_type)`, used at the point a NAMED socket is checked. Inference is
the same predicate run in reverse across `board.sockets.values()`,
keeping the candidates rather than a boolean. That part is a few lines.

**It cannot live where `socket:` is currently required.**
`loader/delta.py::parse_instance` does `require(item, "socket",
"instance")`, and the loader never sees the board at all — it handles the
board NAME as a string and nothing more. That is not incidental: it is
precisely the "board identity enters at exactly two doors" property the
whole coordinate direction depends on, and this slice must not erode it.

So: the loader stops requiring `socket:`, carries the absence through
unresolved, and the ANALYZER — which has the board — resolves it
alongside the existing mating check.

## 3. The model change

`model.Instance.socket` becomes `Optional[str]`: `None` means "not
declared, infer it". This is a `model.py` change and therefore needs a
recorded design decision, which is this section.

The consequence to think about rather than paper over: the loader now
produces an instance that does not yet know where it sits. Every loader-
side consumer of `inst.socket` must be checked for what it does with
`None` — do not assume the type checker finds them all, since some may
stringify it.

## 4. RULING 1 — the candidate set

Does inference consider only BOARD sockets, or also carrier-exported ones
(`mux_1.ch0`, the sockets a shield instance itself provides)?

**RULED 2026-08-04: board sockets only.** Exposed sockets come
from instances, so the candidate set would change as instances are
parsed — inference would become order-dependent, and a rig's meaning
would depend on its declaration order. That is the exact failure class
the delta engine was designed to avoid. A carrier's channel must always
be named explicitly.

## 5. RULING 2 — stacking

If two instances each omit `socket:` and infer the SAME socket, is that a
legal stack (for a stackable connector type) or an ambiguity?

**RULED 2026-08-04: legal, and subject to the existing stacking rule** —
inference resolves placement, and the `per_socket` exclusivity check then
applies to the result exactly as it does for explicitly-named sockets. A
non-stackable type still rejects the second instance. Any other answer
means inference has its own multiplicity semantics, which is a second
rule to keep in sync.

But see §6 — that check does not currently work the way this ruling
assumes.

## 6. A latent defect this slice must fix anyway

While scoping: `analyzer/sockets.py` builds its stacking census with
`per_socket.setdefault(inst.socket, []).append(inst)` — keyed by the RAW
REFERENCE STRING — and then enforces, per key, that a non-stackable
connector type hosts at most one module.

Keying by the raw string is wrong now that a socket can be named more
than one way. Since `d47ec86` a board socket carries both a defining
label and a conventional alias, so two instances can name the SAME
physical socket by DIFFERENT strings, land in different buckets, and slip
past the exclusivity check entirely.

**Currently latent, not live** — measured: the only non-stackable
connector type in the tree is `grove`, whose sockets are on
seeeduino_lotus, and lotus is the one board that got no aliases in
`d47ec86` because it already conformed. So no reachable case exists
today. It becomes reachable the moment a non-stackable type's board gains
an alias.

Inference makes it unavoidable regardless: with `inst.socket` as `None`,
raw-string keying collapses every inferred instance into one `None`
bucket, including instances that inferred DIFFERENT sockets.

**Fix: key the stacking census by the RESOLVED socket**, not the
reference that named it. Same hazard class as hwmv2's B1 (derive from the
resolved form, never the raw one), and the fix is small.

Land it as its own commit BEFORE the inference work, with a regression
test naming two instances on one socket by two different labels. That
test is meaningful today even though the defect is unreachable — it pins
the property for the day a grove-like board gains an alias.

## 7. The config sheet must print the RESOLVED socket

`emitter/sheet.py` renders `inst.socket` into the instance/socket column,
which C2b made a COMPARED FACT. The config sheet is wiring instructions
for a human standing at a bench: it must name the socket they should
physically plug into, and "not declared" is not an instruction.

**Specify it as declared-else-resolved**: print `inst.socket` when the
instance declared one, and fall back to the resolved socket's label
(`s.sockets[inst.name].label`, already available to the sheet) only when
it did not.

That precise shape matters. "Always use the resolved label" would also be
inert today — verified: for a board socket the resolved label is the
board node's defining label, which is what content names today, and for a
carrier-exported socket `compose_socket(inst.socket, …)` makes the
resolved label *equal* the declared reference (`mux_1.ch0`), so carrier
rows do not move either. But it stops being inert at step 3 of
`board-as-coordinate-brief.md`: once content says `arduino_r3` and the
resolved label is still `nucleo_ard`, "always resolved" would silently
decide that the sheet shows the board's own label rather than what the
author wrote.

That is a real question — a bench instruction arguably WANTS the board's
own silkscreen label — but it is step 3's question, not this slice's.
Declared-else-resolved changes nothing today, does the right thing for an
inferred instance, and leaves the choice open. Do not pre-decide it here.

Third instance of the same pattern in this codebase now — hwmv2's
requested-vs-resolved revision, the overlay's board-label-vs-content-name,
and this. Worth noticing as a shape rather than solving a third time from
scratch.

## 8. Golden impact

Expected: **none.** No corpus rig omits `socket:`, so every existing
resolution is unchanged, and §7's sheet change is inert wherever the
declared and resolved socket agree — which is everywhere today.

If a golden moves, something has changed that should not have. Stop and
report rather than refreezing.

New coverage is where the evidence lives:

- inference with exactly one candidate → resolves, no diagnostic;
- zero candidates → the error names the plug type and what the board
  offers;
- two candidates → the error lists both and demands an explicit socket
  (control: an implementation that tie-breaks passes a single-candidate
  test and fails this one);
- an inferred instance's config-sheet row names the resolved socket;
- §6's regression test, two labels for one socket.

## 9. Relation to the singleton identity law

This unblocks it but does not deliver it. The law additionally needs a
shield authored in BOTH worlds — a `.shield` template and a plain
upstream `.overlay` as the oracle — because no shield in the tree
currently exists in upstream form. That is a separate slice
(`board-as-coordinate-brief.md` §5), known-feasible: the P2
S1-equivalence work did exactly that against the legacy `--shield` build.

Do not fold the law into this slice. This one stands on portability and
ergonomics, and should be reviewable on that basis alone.
