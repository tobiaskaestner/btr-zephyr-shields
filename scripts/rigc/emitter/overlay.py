"""rig-gen.overlay and rig-gen-includes.dtsi's payload: the device-tree
projection of a Solved rig. Ported from rigexp/emitter.py's overlay half
(rigc-r5-brief.md Sec 1) -- nexus synthesis, I2C scopes + mux nesting,
SPI/cs-gpios, collections, plain groups, controllers, the device-node
renderer.

Label policy (R10 is parked; this is the prototype's deterministic
scheme): generated label = <instance>_<shield-local label>, e.g.
logger_a_dl_rtc.

Per-instance parameters (rig-variants-revisions.md): a rig-assigned
params: value is emitted VERBATIM -- the raw token text, never resolved
here -- so rig-gen.overlay stays readable (zephyr,code = <INPUT_KEY_1>;,
not a bare number). Resolving those tokens is sheet.py's concern (the
config sheet's human-facing display value), not this module's.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple, cast

from ..analyzer import Solved
from ..model import BoardSocket, ConnectorType, Device, Instance, Rig
from . import GEN


def _nexus(socket: BoardSocket) -> str:
    """The DT label a socket is referenced through. Board sockets are real
    nodes (their own label); carrier-exported sockets are referenced through
    the nexus the emitter synthesizes for them (Option C)."""
    return socket.nexus_label or socket.label


def _instance_extra_props(inst: Instance, dev: Device) -> List[Tuple[str, str]]:
    """dev.extra_props, with this INSTANCE's rig-assigned params:
    substituted in: a property the rig assigns REPLACES the shield's own
    rendering of it (a default being overridden) or is simply ADDED (the
    shield declared it required, so there is no default to replace) --
    emitted verbatim, never resolved. Every device-node rendering path
    (plain, collected, mux-nested) goes through this instead of
    dev.extra_props directly, so a parameter assignment on any of them is
    honored the same way."""
    assigned = inst.params.get(dev.label, {})
    if not assigned:
        return dev.extra_props
    kept = [(name, rendered) for name, rendered in dev.extra_props
            if name not in assigned]
    added = [(name, f"{name} = <{value}>;") for name, value in sorted(assigned.items())]
    return kept + added


def render_overlay(rig: Rig, s: Solved, types: Dict[str, ConnectorType],
                   needed_includes: Optional[List[str]] = None) -> str:
    """rig-gen.overlay's full text. rig/s/types are read-only; returns a
    fresh string the caller owns. `needed_includes`
    (`emitter._needed_param_includes`) is the caller's own decision about
    which headers this rig's params actually need -- this function only
    gates the quoted #include line on whether the list is non-empty; it
    never derives the list itself."""
    out = []
    if needed_includes:
        # Opens the file: the needed parameter vocabulary reaches cpp
        # before anything that might use it, via a quoted include
        # resolved against this file's own directory (<build>/rig/, where
        # the emitter also writes rig-gen-includes.dtsi).
        out.append('#include "rig-gen-includes.dtsi"')
    out += [f"/* {GEN}", f" * rig: {rig.name}  board: {rig.board}", " */", ""]

    out += _synth_nexus_nodes(s)

    # I2C scopes -- expander is the sole author of reg + unit-address, always
    # as a matching pair (address authority rule). Mux channels (S8) are NEW
    # scopes emitted nested inside their mux device, not at the top level.
    mux_channels: Dict[str, List[Tuple[object, str]]] = {}
    for path, (root, channel) in s.scopes.items():
        mux_channels.setdefault(root, []).append((channel, path))
    for bus_path in sorted(s.bus_label):
        if bus_path in s.scopes:                     # a mux channel -- emitted nested
            continue
        devs = list(_bus_devices(rig, s, "i2c", bus_path))
        if not devs:
            continue
        out.append(f"&{s.bus_label[bus_path]} {{")
        for inst, dev, socket in sorted(devs, key=lambda m: s.addr[(m[0].name, m[1].name)]):
            addr = s.addr[(inst.name, dev.name)]
            label = f"{inst.name}_{dev.label}"
            if label in mux_channels:                # scope-creating interposer (R26)
                out += _mux_node(rig, s, types, inst, dev, socket, addr,
                                 mux_channels[label])
            else:
                out += _device_node(s, types, inst, dev, socket,
                                    unit=f"{addr:x}", reg=f"<{addr:#04x}>")
        out.append("};")
        out.append("")

    # SPI scopes -- cs-gpios array and child reg written together (R16)
    for bus_path, entries in sorted(s.cs_gpios.items()):
        devs = list(_bus_devices(rig, s, "spi", bus_path))
        if not devs:
            continue
        out.append(f"&{s.bus_label[bus_path]} {{")
        cs = ", ".join(f"<&{_nexus(sock)} {pos} 1 /* ACTIVE_LOW */>"
                       for sock, pos in entries)
        out.append(f"\tcs-gpios = {cs};")
        for inst, dev, socket in sorted(devs, key=lambda m: s.cs[(m[0].name, m[1].name)][0]):
            index, _pos = s.cs[(inst.name, dev.name)]
            out += _device_node(s, types, inst, dev, socket,
                                unit=str(index), reg=f"<{index}>")
        out.append("};")
        out.append("")

    # collection bindings (gpio-keys/gpio-leds, ...): entries from every
    # instance aggregate under ONE node per compatible (gap #4 / R10 sibling)
    out += _collections(rig, s, types)

    # plain non-bus device groups (not collected): per-instance container.
    # Own variable names (plain_socket/plain_devs/plain_dev) rather than
    # socket/devs/dev: those names are already bound above, to the
    # non-Optional BoardSocket/List[Tuple[...]]/Device shapes the bus loops
    # unpack -- Python has no block scoping, so reusing them here with a
    # DIFFERENT shape (an Optional socket, a bare List[Device]) is a type
    # clash mypy (rightly) flags, not just a style choice.
    root_nodes: List[str] = []
    for inst in sorted(rig.instances, key=lambda i: i.name):
        plain_socket = s.sockets.get(inst.name)
        plain_devs = [d for d in inst.shield.devices
                     if d.bus is None and d.collect is None]
        if not plain_devs or plain_socket is None:
            continue
        root_nodes.append(f"\t{inst.name} {{")
        for plain_dev in sorted(plain_devs, key=lambda d: d.name):
            root_nodes += ["\t" + line
                           for line in _device_node(
                               s, types, inst, plain_dev, plain_socket)]
        root_nodes.append("\t};")
    if root_nodes:
        out += ["/ {", *root_nodes, "};", ""]

    out += _controllers(s)
    return "\n".join(out)


def _controllers(s: Solved) -> List[str]:
    """Enable the timer/adc controllers a PWM/ADC claim resolved to, and NOTE
    the board-provided pin-mux each needs (the expander names the pinctrl
    requirement; applying the SoC-specific fragment is the board's job,
    stubbed here)."""
    if not s.controllers:
        return []
    out = ["/* PWM/ADC: enable the resolved controllers; the pin-mux (pinctrl)",
           " * for each muxed pin is board-provided and must be applied —",
           " * stubbed here, see the config sheet. */"]
    for ctrl in sorted(s.controllers):
        out.append(f"&{ctrl} {{ status = \"okay\"; }};")
    out.append("")
    return out


def _sanitize(compat: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in compat)


def _collections(rig: Rig, s: Solved, types: Dict[str, ConnectorType]) -> List[str]:
    """Aggregate collected entries (shield,collect) by their collection
    compatible into one node each -- the idiomatic gpio-keys/gpio-leds shape,
    where the compatible sits on the parent and each module is a child entry.
    (Merging into a board-provided collection of the same compatible: parked.)"""
    groups: Dict[str, List[Tuple[Instance, Device, BoardSocket]]] = {}
    for inst in rig.instances:
        socket = s.sockets.get(inst.name)
        if socket is None:
            continue
        for dev in inst.shield.devices:
            if dev.collect is not None:
                groups.setdefault(dev.collect, []).append((inst, dev, socket))
    if not groups:
        return []

    out = ["/ {"]
    for compat in sorted(groups):
        node = _sanitize(compat)
        out += [f"\t{node}: {node} {{", f'\t\tcompatible = "{compat}";']
        for inst, dev, socket in sorted(groups[compat], key=lambda m: m[0].name):
            out += ["\t" + line for line in _collection_entry(s, types, inst, dev, socket)]
        out.append("\t};")
    out += ["};", ""]
    return out


def _collection_entry(s: Solved, types: Dict[str, ConnectorType], inst: Instance,
                      dev: Device, socket: BoardSocket) -> List[str]:
    """One child of a collection node: the module's gpio signal. Node name and
    label are the composed <instance>_<shield label> -- unique per (instance,
    device), so an instance may contribute several entries (a shield with two
    LEDs). The entry keeps its identity -- aggregation, not S3 collapse."""
    lbl = f"{inst.name}_{dev.label}"
    lines = [f"\t{lbl}: {lbl} {{", f'\t\tlabel = "{lbl}";']
    # Carry through the device's passthrough properties -- a collected child
    # is still a real device node and its driver may require them (e.g. the
    # gpio-keys driver mandates zephyr,code). Same emission as _device_node;
    # aggregation only composes the label/gpio, it must not drop the rest.
    for _pname, rendered in _instance_extra_props(inst, dev):
        lines.append(f"\t\t{rendered}")
    ctype = types[socket.type_name]
    for ref in dev.gpio_refs:
        pos = s.positions.get((inst.name, dev.name, ref.prop), ref.position)
        # The analyzer resolves every gpio ref's position (fixed or
        # jumper-routed) before an accepted rig ever reaches the emitter;
        # None here would mean that guarantee broke, not a rig-author
        # mistake -- narrows the type for posname() below rather than
        # silently rendering the literal text "None".
        assert pos is not None
        flags = ref.flags ^ 0x1 if inst.invert else ref.flags
        lines.append(
            f"\t\t{ref.prop} = <&{_nexus(socket)} {pos} {flags:#x}>;"
            f"\t/* {ctype.posname(pos)}{' inverted' if inst.invert else ''} */")
    lines.append("\t};")
    return lines


def _bus_devices(rig: Rig, s: Solved, bus: str, bus_path: str,
                 ) -> Iterator[Tuple[Instance, Device, BoardSocket]]:
    for inst in rig.instances:
        socket = s.sockets.get(inst.name)
        if socket is None or bus not in socket.buses:
            continue
        if socket.buses[bus].path != bus_path:
            continue
        for dev in inst.shield.devices:
            if dev.bus == bus:
                yield inst, dev, socket


def _mux_node(rig: Rig, s: Solved, types: Dict[str, ConnectorType], inst: Instance,
             dev: Device, socket: BoardSocket, addr: int,
             channels: List[Tuple[object, str]]) -> List[str]:
    """A scope-creating interposer device (S8 I2C mux): the device node on the
    parent bus, with one child channel bus per scope, each hosting that scope's
    modules. Per-scope address uniqueness means 0x48 can recur across channels."""
    label = f"{inst.name}_{dev.label}"
    lines = [f"\t{label}: {dev.name}@{addr:x} {{"]
    for _pname, rendered in _instance_extra_props(inst, dev):   # compatible, ...
        lines.append(f"\t\t{rendered}")
    lines += [f"\t\treg = <{addr:#04x}>;", "\t\t#address-cells = <1>;",
              "\t\t#size-cells = <0>;"]
    # channel is an int at runtime (shield,channel, model.ExposedSocket's
    # own comment) behind the model's loose `object` annotation -- sort
    # key casts rather than widening the annotation, so this stays the
    # SAME (channel, scope_path) ordering the blueprint's bare sorted()
    # produces for the only shape channel ever takes.
    for channel, scope_path in sorted(
            channels, key=lambda cp: (cast(int, cp[0]), cp[1])):
        lines += [f"\t\tchannel@{channel} {{", f"\t\t\treg = <{channel}>;",
                  "\t\t\t#address-cells = <1>;", "\t\t\t#size-cells = <0>;"]
        members = sorted(_bus_devices(rig, s, "i2c", scope_path),
                         key=lambda m: s.addr[(m[0].name, m[1].name)])
        for si, sd, ss in members:
            sa = s.addr[(si.name, sd.name)]
            lines += ["\t\t" + ln for ln in _device_node(
                s, types, si, sd, ss, unit=f"{sa:x}", reg=f"<{sa:#04x}>")]
        lines.append("\t\t};")
    lines.append("\t};")
    return lines


def _device_node(s: Solved, types: Dict[str, ConnectorType], inst: Instance,
                 dev: Device, socket: BoardSocket, unit: Optional[str] = None,
                 reg: Optional[str] = None) -> List[str]:
    label = f"{inst.name}_{dev.label}"
    name = f"{dev.name}@{unit}" if unit is not None else dev.name
    lines = [f"\t{label}: {name} {{"]
    for _pname, rendered in _instance_extra_props(inst, dev):
        lines.append(f"\t\t{rendered}")
    if reg is not None:
        lines.append(f"\t\treg = {reg};")
    ctype = types[socket.type_name]
    for ref in dev.gpio_refs:
        if ref.function == "gpio":
            # Conv. 3: rewrite &plug (or the routing jumper, R6) to the socket's
            # nexus -- a real board node, or a synthesized carrier nexus (R19,
            # Option C). dtc chases the (multi-level) gpio-map to the pin.
            pos = s.positions.get((inst.name, dev.name, ref.prop), ref.position)
            assert pos is not None   # see _collection_entry's own assert
            flags = ref.flags ^ 0x1 if inst.invert else ref.flags   # bridle _inv axis
            lines.append(
                f"\t\t{ref.prop} = <&{_nexus(socket)} {pos} {flags:#x}>;"
                f"\t/* {ctype.posname(pos)}{' inverted' if inst.invert else ''} */")
        else:
            # pwm/adc: socket-relative, unified with the gpio idiom above --
            # dtc chases the socket's real pwm-map/io-channel-map nexus to
            # the controller and channel; the expander does not resolve the
            # channel itself.
            #
            # PWM cells: the nexus's own #pwm-cells is 2 (position, period)
            # -- matching upstream atmel,sam0-tcc-pwm's flags-less 2-cell
            # convention (channel, period). pwm-map-pass-thru
            # <0x0 0xffffffff> carries exactly ONE cell through: period.
            # There is NO cell for flags -- a 3rd cell here is not absorbed
            # by the map at all; dtlib parses it as the start of a BOGUS
            # trailing phandle-array element (silently a spurious null
            # entry when it happens to be 0, a hard EDTError otherwise).
            # So flags must never be emitted here; see below.
            _fn, _ctrl, _ch, period, flags, _pos = s.channels[
                (inst.name, dev.name, ref.prop)]
            pos = s.positions.get((inst.name, dev.name, ref.prop), ref.position)
            assert pos is not None   # see _collection_entry's own assert
            if ref.function == "pwm":
                # Nonzero PWM flags are rejected upstream, by the analyzer
                # (analyzer/gpio.py, category phys-function) -- a device
                # with such a ref never earns a solved.channels entry, so
                # cli.py exits on diags.errors before emitter.emit() is
                # ever called (its "cannot fail" contract would otherwise
                # be violated by a raised ValueError here). This assert
                # documents the invariant rather than re-deriving the
                # diagnostic; tripping it means the analyzer's guarantee
                # broke, not that a rig author did something wrong.
                if flags:   # not assert -- must survive python -O
                    raise AssertionError(
                        f"{inst.name}/{dev.name}: {ref.prop} reached the "
                        f"emitter with nonzero PWM flags {flags:#x} — the "
                        "analyzer should have rejected this (phys-function) "
                        "before emission")
                lines.append(
                    f"\t\t{ref.prop} = <&{_nexus(socket)} {pos} {period}>;"
                    f"\t/* {ctype.posname(pos)} */")
            else:  # adc
                lines.append(
                    f"\t\t{ref.prop} = <&{_nexus(socket)} {pos}>;"
                    f"\t/* {ctype.posname(pos)} */")
    # Every device the analyzer accepted is, by definition, installed
    # hardware -- match the legacy shield convention of an explicit
    # status = "okay" on each instantiated device (not just its parent bus,
    # which the board DT already enables unconditionally).
    lines.append('\t\tstatus = "okay";')
    # An SD card on SPI needs its zephyr,sdmmc-disk child node (the legacy
    # adafruit_data_logger.overlay nests this under every sdhc-spi-slot
    # device) -- fixed, generic shape, no rig-specific data, so the
    # expander is the natural place to author it rather than duplicating
    # it in every shield that carries an SD slot.
    if dev.compatible == "zephyr,sdhc-spi-slot":
        lines += [
            "\t\tsdmmc {",
            '\t\t\tcompatible = "zephyr,sdmmc-disk";',
            '\t\t\tdisk-name = "SD";',
            '\t\t\tstatus = "okay";',
            "\t\t};",
        ]
    lines.append("\t};")
    return lines


def _synth_nexus_nodes(s: Solved) -> List[str]:
    """Emit a gpio-nexus node for each carrier-exported socket in use (R19,
    Option C), chaining to its parent's nexus. Matches hand-written nested
    overlays: a click's <&carrier_nexus pos> resolves through the carrier to
    the host board pin, keeping the routing visible in the artifact."""
    synth: Dict[str, BoardSocket] = {}

    def visit(sock: Optional[BoardSocket]) -> None:
        # skip board sockets (nexus_rows None) and gpio-less exposed sockets
        # (empty rows -- e.g. an I2C-only mux channel, S8): nothing to route
        if sock is None or not sock.nexus_rows or sock.nexus_label in synth:
            return
        assert sock.nexus_label is not None
        synth[sock.nexus_label] = sock
        visit(sock.parent)                 # a carrier stacked on a carrier

    for sock in s.sockets.values():
        visit(sock)
    if not synth:
        return []

    out = ["/* carrier-exported sockets, synthesized as gpio-nexus nodes */",
           "/ {"]
    for label in sorted(synth):
        sock = synth[label]
        assert sock.nexus_rows is not None
        rows = ",\n\t\t\t   ".join(
            f"<{child} 0 &{parent} {ppos} 0>"
            for child, parent, ppos in sock.nexus_rows)
        out += [f"\t{label}: {label} {{",
                "\t\t#gpio-cells = <2>;",
                # Match on the position cell only; mask the GPIO flag bits out
                # of matching and pass them through to the parent -- the same
                # nexus idiom the board's own typed socket uses. Without this
                # edtlib demands an exact specifier match, so a consumer's
                # <&nexus pos GPIO_ACTIVE_LOW> would fail against the stored
                # <pos 0> row (the bug that blocked nested-carrier rigs).
                "\t\tgpio-map-mask = <0xffffffff 0xffffffc0>;",
                "\t\tgpio-map-pass-thru = <0 0x3f>;",
                f"\t\tgpio-map = {rows};",
                "\t};"]
    out += ["};", ""]
    return out
