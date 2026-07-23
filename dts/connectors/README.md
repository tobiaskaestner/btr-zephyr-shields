# `dts/connectors/` — plug-side connector-type facts (pass-1 only)

These `plug,<type>.yaml` files hold the **plug-side** half of a rig
connector type: claimable positions (name, function, optional), and the
bus-proxy node names a shield may declare (`i2c`/`spi`/`uart`). They are
read by `scripts/rigexp/ctypes_registry.py` with a plain `yaml.safe_load` —
never by edtlib.

## Why not `dts/bindings/connector/`

The **socket-side** half of a connector type (`socket,cs-pool` default,
`socket,stackable` presence) lives as ordinary schema'd properties in the
real `dts/bindings/connector/<type>.yaml` binding, because a board's socket
node with `compatible = "socket,<type>"` genuinely gets loaded and validated
by edtlib on every real build (rig or plain). The **plug** side never does:
no board node is ever compatible with a plug, so its facts have no home in
a real binding.

They CANNOT be folded into the real binding as extra top-level/per-property
keys either. `edtlib.Binding` validates every loaded binding file against a
closed allowlist of top-level keys (`ok_top`) and per-property keys, and
raises a hard error on anything else (`devicetree/edtlib.py`, `ok_top`
check + per-property check) — and pass 2 loads `connector/<type>.yaml`
for REAL, because the board DT's socket node has that compatible. Custom
keys there would break every regular (non-rig) build using that board.
`dts/bindings/` (and every dir Zephyr's bindings CI lints) is globbed
wholesale and schema-checked, so a plug-facts file placed there — even
under a `plug,*.yaml` name edtlib never loads by compatible — would still
be linted and rejected for its custom top-level shape (`plug:`,
`bus-proxies:`, `positions:` are not `ok_top` keys).

So: socket-side facts live in the real binding (schema'd, edtlib-validated,
Bridge-A step 3, amended 2026-07-23 in `claude/rigs/implementation-plan.md`
§"Connector types → binding YAML"); plug-side facts live here, outside
every binding-globbing root, read directly by the loader.

## The `i2c-port` exception

`i2c-port` sockets (`compatible = "socket,i2c-port"`) are **shield-
synthesized only** — authored inside a `.shield`'s own DT subtree (e.g.
`boards/shields/i2c_mux/i2c_mux.shield`'s `ch0`..`ch3` channel sockets) and
parsed by the loader's own `dtlib` pass over that translation unit, never
by edtlib against a real board DT (the emitter lowers them to plain
`channel@N` mux children — `ti,tca9548a`-shaped — before anything reaches
pass 2; grep any accept-rig `zephyr.dts` golden for `socket,i2c-port` to
confirm it never appears there). There is therefore no real
`dts/bindings/connector/i2c-port.yaml` to hold its socket-side facts — one
would be schema surface with no board node ever exercising it. Its
`socket:` facts (stackable, cs-pool default) are instead declared inline in
`plug,i2c-port.yaml` here, alongside its plug facts, since this type has no
edtlib-validated home either way.
