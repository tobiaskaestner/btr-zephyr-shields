# Multi-plug shields — a shield mating more than one socket at once

**Status:** design exploration started 2026-08-09, paused here for a fresh
session to pick up. NOT a brief — no ruling, no scope trace verified
end-to-end, no acceptance criteria. This document exists to hold what's
been established so the exploration doesn't have to be re-derived.

## RESUME HERE

**If starting a fresh session for this specific thread:** root it at
`/wrk/z/ws-up/btr-shields` (not the west topdir `/wrk/z/ws-up`) — the
`rig-implementor`/`rig-reviewer` agent types in `.claude/agents/` are only
discovered when the session's own working directory is at or below that
directory, and this exploration will eventually need both once it reaches
brief stage.

**Read, in order:** this document in full, then
`claude/multi-bus-socket-brief.md` (already implemented, reviewed,
fixed, and committed as `eef9836`/`b9c3be3`) as the METHOD template — not
because its content applies here, but because §2-§4 of that brief is the
concrete shape "verify every path, don't reason abstractly" produces, and
this document is not yet at that level of rigor.

**Concrete next action:** §5 question 2 below — trace how far
`sockets.get(inst.name)`'s single-socket-per-instance assumption
propagates through `cs.py`/`addresses.py`/the emitter, the same way the
multi-bus brief's §4 was built (grep every call site, read it, cite
file:line, don't assume the core survives unchanged just because it did
for the bus case). Do this against the CURRENT tree — `model.py`,
`analyzer/cs.py`, `analyzer/sockets.py`, `board_edt.py` all changed
between when §2 below was written and the multi-bus-socket commits
landing; the line numbers in §2 have not been re-verified since.

## 1. The motivating scenario

A real-world topology (Tobi's own past hardware): a carrier shield that
plugs into TWO of a mainboard's connectors SIMULTANEOUSLY — e.g. both the
Arduino header and the mikroBUS header at once — and re-exports the
combined available connections through a third connector of its own.

This is distinct from the multi-bus-socket work (`multi-bus-socket-brief.md`,
landed and committed since this document was started): that gap is "one
socket offers more than one bus of the same kind." This gap is "one shield
instance mates more than one socket, of possibly different connector
types, at the same time." Different axis, and — verified below — a
structurally bigger one.

## 2. The gap, verified against the actual code (2026-08-09)

The 1:1 shield↔socket assumption is baked in at three separate points, not
one:

1. **`Shield.plugs: str`** (`model.py:149`) — exactly one connector type per
   shield template. No way to declare two.
2. **`Instance.socket: Optional[str]`** (`model.py:215`) — exactly one
   socket reference per instance.
3. **`SocketResolution.sockets: Dict[str, BoardSocket]`**, keyed by
   `inst.name` ALONE (`analyzer/sockets.py:47`; every assignment site —
   `resolve_one`, lines 185/191/205/242 — stores exactly one `BoardSocket`
   per instance name). The entire downstream allocation pipeline (CS,
   addresses, GPIO, emission) is built on "one instance resolves to one
   socket."

And no device-level reference carries a socket-slot identifier at all:
`GpioRef` (`model.py:58-71`) resolves a position against "the shield's one
socket" implicitly — there is no field saying WHICH of several plugs a
given pin comes from, because there has never been more than one to choose
from.

**The re-export half already exists, partially.** A carrier plugging into
one parent and exposing a synthesized socket onward is exactly
`ExposedSocket`/`compose_socket` (`analyzer/sockets.py:67-116`). What's
missing is the MATING half: `compose_socket` takes a single `parent:
BoardSocket` (line 68) — carrier composition today is a strict tree, one
parent per carrier, never a shield with two simultaneous parents of
possibly different connector types.

Checked and confirmed empty: no existing design doc (`design-log.md`,
`parked.md`, `rig-playbook.md`, both board-coordinate briefs) records this
scenario as a known gap. It is new as of this session.

## 3. Why this is bigger than the multi-bus-socket case, not just similar

The multi-bus design (a named-slot pattern: `socket,spi-sensors` /
`socket,spi-motors`) turned out to be a bounded, mostly-mechanical slice
because the allocation CORE (`analyzer/cs.py`/`analyzer/addresses.py`) was
already scoped by `bus.path` — a real per-bus identity — rather than by
kind string, so widening the KEY SPACE at the edges was enough; the middle
of the pipeline didn't need to change.

This gap is different in KIND: it changes the fundamental
Shield:Socket relationship from 1:1 to 1:N, which plausibly cascades
through every layer that currently keys off "the instance's one socket" —
not yet verified how far. Candidate structural shape, sketched, NOT
committed to:

- `Shield.plugs` becomes a mapping of slot-name -> connector-type (e.g.
  `{"main": "arduino-r3", "aux": "mikrobus"}`) instead of a bare string.
- Every position/GPIO/bus reference on the shield's devices needs a new
  axis saying which slot it draws from — same SHAPE of problem as the
  bus-specializer question, one level up (per-device slot selection
  instead of per-device bus-kind selection).
- `Instance.socket` becomes a mapping (slot-name -> board-socket-label)
  rather than one optional string.
- `SocketResolution.sockets` needs re-keying (by `(inst.name, slot)` or
  similar) — NOT YET TRACED how far this propagates into `cs.py`/
  `addresses.py`/emitter call sites that currently do `sockets.get(inst.name)`.
- The re-export side: `compose_socket`/`ExposedSocket` would need to pull
  from MULTIPLE named parents when building an exposed socket's
  `gpio_map`/`buses` — some exposed positions map to slot "main", others
  to slot "aux". Whether `ExposedSocket`'s existing pass-through/
  scope-creation markers (`"plug"` / `("scope", label)`) generalize to
  "which parent slot" cleanly, or need a third dimension, is open.

## 4. What's NOT yet done

- Trace whether `cs.py`/`addresses.py`'s allocation core survives a
  multi-socket instance the way it survived multi-bus (the multi-bus case
  was a pleasant surprise BECAUSE it was already scoped by `bus.path`;
  this case's core loop keys by `inst.name` via `sockets.get(inst.name)` —
  first look suggests this does NOT survive unchanged, needs verification
  file-by-file the way the multi-bus trace was done).
- Whether a device can reference pins from BOTH plug slots at once (finer
  grain than "this whole device belongs to slot X"), or whether the
  simpler form — every device belongs to exactly one of the shield's named
  slots — covers the real scenario. The motivating hardware
  (re-export-to-a-third-connector) suggests the SHIELD's own re-export
  logic needs both slots, but individual DEVICES on it plausibly do not —
  worth confirming against the real remembered hardware before assuming.
- Naming/ownership question analogous to the multi-bus ruling: do plug-slot
  names belong to the SHIELD (since a shield's own template defines which
  of its pins go where) rather than the connector type? Likely yes — this
  is the shield's own physical fact, not something a connector type
  imposes — but not yet stated as a ruling.
- No fixture, no acceptance criteria, no scope trace of production files
  comparable to the multi-bus brief's §4. This document is pre-brief.

## 5. Open questions for next pass

1. Does splitting "which slot a device belongs to" from "which slot the
   carrier's re-export logic draws from" simplify this, or is that a false
   simplification given the real hardware?
2. How far does the `sockets.get(inst.name)` re-keying propagate — this is
   the next concrete trace to run, mirroring how the multi-bus brief's §4
   was built by reading every call site rather than reasoning abstractly.
3. Is there a real fixture-provable slice here? The multi-bus-socket work
   this shared `model.py` territory with (`Shield`, `Instance`,
   `BoardSocket`) has now landed (`eef9836`/`b9c3be3`), so this is
   unblocked — but re-verify §2's citations against the current tree
   first (see RESUME HERE above); `BoardSocket.buses`'s keys and
   `BusRef`'s own fields changed shape in that work.
