# Connector unification — slice brief

Status: RATIFIED (design-log 2026-07-24b/c). Prereq LANDED: the zephyr rig
branch carries `1a657124349` (edtlib permits vendor-namespaced top-level
binding keys, preserved in Binding.raw) + `c1c4d2acf2d` (*-cells
validation precedence fix). Extension-key namespace: **`plug,*`** (Tobi).
Consume the patched edtlib AS-IS — the zephyr tree is not touched by this
slice under any circumstances.

## Goal

ONE file per connector type, under `dts/bindings/connectors/<type>.yaml`:
the existing socket binding content plus the plug contract as `plug,*`
extension keys. `dts/connectors/` (all four `plug,*.yaml` + README.md)
DISSOLVES — the edtlib carried commit removed the reason it existed
(binding files may now carry namespaced extension keys; see
`scripts/rigexp/ctypes_registry.py`'s own module docstring for the full
statement of the old constraint this replaces).

## Key mapping

- `positions:` → `plug,positions:` (structure unchanged)
- `bus-proxies:` → `plug,bus-proxies:` (structure unchanged)
- `plug: "<type>"` → DROPPED (identity is the binding's type: filename +
  `socket,<type>` compatible; the loader keys types by name already)
- plug-file description prose: fold what is still true into the unified
  binding's `description:`; drop the "why this lives here" pointers.
- Any other plug-file key: map to `plug,<key>` (or `socket,<key>` if it is
  a socket-side fact) unless it duplicates a fact the socket binding
  already declares (e.g. cs-pool defaults stay where they are — properties
  with defaults, NOT extension keys). Namespace RULE (Tobi, review): keys
  are namespaced by the SIDE they describe, never by the project — there
  is no `rig,*` key.
- NOTE the ratified exception: `-cells`-suffixed keys are NOT opaque to
  edtlib (they land in specifier2cells by design). None of the current
  plug keys end in `-cells`; do not introduce one.

## The i2c-port case (the one type with no real socket binding)

Its sockets are shield-synthesized only (mux/carrier scope creation),
never authored in a board DT; its plug YAML carries socket facts under a
`socket:` key. It gets a NEW unified file `dts/bindings/connectors/
i2c-port.yaml` like the others — but whether that file may carry
`compatible: "socket,i2c-port"` depends on a fact you must CHECK first:
whether the emitter puts that compatible string on synthesized socket
nodes in generated overlays (grep emitter.py / a generated overlay).
- If synthesized sockets carry NO compatible: a compatible-bearing
  binding is inert in pass 2 → use the uniform shape (compatible +
  plug,* keys, socket facts as socket,* keys or properties as
  appropriate).
- If they DO carry it: pass 2 would suddenly TYPE those nodes (property
  validation, edt.pickle changes, tier-2 churn) — STOP and report before
  choosing a shape; do not improvise.
- A compatible-LESS file under dts/bindings/ is NOT acceptable (edtlib's
  binding scan is content-sniffing — validation of such a file would be
  build-dependent; this trap is documented in the registry docstring).
Report which case you found either way.

## Loader (`scripts/rigexp/ctypes_registry.py`)

- Read the unified files from `MODULE_ROOT/dts/bindings/connectors/`
  (same self-located root as today — multi-module connector-type
  discovery is deliberately NOT this slice).
- The existing plain `yaml.safe_load` approach MAY be kept iff the
  unified bindings remain include-free with inline declarations (that
  equivalence-to-Binding.raw argument is already made in the module
  docstring — keep it true and keep the docstring honest). Switching to
  edtlib.Binding is acceptable but not required; do not add machinery
  for its own sake.
- `Depends()` must now record the unified file paths (RIG_DEPENDS).
- Rewrite the module docstring: the two-source split and the
  dts/connectors story are OVER; document the unified shape + the
  carried-commit reference (`1a657124349`) that makes plug,* keys legal
  under dts/bindings/.

## Pass-2 consequence (why the gate exercises the carried commit)

The unified bindings ARE loaded by pass 2 for every board whose DT uses
`socket,<type>` compatibles — with plug,* keys now in the file, an
UNPATCHED edtlib would fatal "unknown key". The patched tree accepts
them (that is the point). Plain builds of converted boards must stay
green.

## Acceptance criteria

1. Commit gate fully green: `ZEPHYR_BASE=/wrk/z/ws-up/zephyr
   PYTHON=/wrk/z/ws-up/.venv/bin/python3 btr-shields/scripts/check.sh`.
2. Goldens OUTPUT-STABLE: byte-identical, no refreeze. RIG_DEPENDS path
   assertions in test code may update (dts/connectors → dts/bindings/
   connector); golden FILES must not change. If any golden moves, STOP
   and report the diff — the driver decides.
3. `dts/connectors/` no longer exists; no references to it remain
   anywhere in the repo (grep).
4. Four unified files under `dts/bindings/connectors/` (arduino-r3,
   grove, mikrobus, i2c-port), each self-describing.
5. Corpus spot-checks via west build-rig: one accept full-link (e.g.
   nucleo-datalogger), one reject with intact phys-* diagnostic (e.g.
   nucleo-mux-clash — exercises i2c-port via the mux), one lotus rig
   (grove type), AND a plain `-b` build of a converted board (pass-2
   loads the plug,*-bearing binding in a rig-free build).
6. mypy clean; the exemption list only shrinks.
