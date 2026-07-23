"""The ANALYZER (architecture.md): rig model + board DT -> solved rig.

Computes the derived facts (net identity, scopes), runs the checks
(mating R20, roles R22/R23, realizability R9) and the allocator (addresses,
CS pools — deterministic, order-independent, pinnable, R18). Everything that
can reject a rig lives here; diagnostics are worded at the copper level
(C6), never as merge mechanics. The emitter never fails on a rig this
module accepted (the strong contract) — so label namespacing and emission
feasibility are checked HERE.

Prototype stopgap, flagged for the design docs: endpoint roles for device
gpio properties are INFERRED from property names (int*/irq* = device
drives; everything else = device listens). Pads carry authored roles;
device gpio claims should eventually declare theirs too (R23 authoring gap,
next to the drive-type refinement).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .boarddt import load_board
from .ctypes_registry import load_types
from .diag import Depends, Diagnostics
from .edt_build import BuildRecipe
from .model import Board, BoardSocket, BusRef, Device, Instance, Rig

_DRIVER_HINTS = ("int", "irq")


def _role_of(prop_name: str) -> str:
    stem = prop_name[:-6] if prop_name.endswith("-gpios") else prop_name
    if any(h in stem for h in _DRIVER_HINTS):
        return "driver"       # device output (interrupt line etc.)
    return "listener"         # MCU-driven towards the device


@dataclass
class NetClaim:
    instance: Instance
    device: Device | None
    what: str            # "rtc@…: int1-gpios" / "sdhc: CS (copper-fixed)" / pad name
    role: str            # driver | listener | dedicated
    socket: Optional[BoardSocket] = None
    position: Optional[int] = None
    src: object = None


@dataclass
class Solved:
    rig: Rig
    board: Board
    sockets: dict[str, BoardSocket] = field(default_factory=dict)       # instance -> socket
    addr: dict[tuple[str, str], int] = field(default_factory=dict)      # (inst, dev) -> address
    straps: list = field(default_factory=list)  # (inst, strap, state, addr) for the config sheet
    cs: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)  # -> (index, position)
    cs_gpios: dict[str, list] = field(default_factory=dict)             # bus path -> [(ctrl,pin)]
    bus_label: dict[str, str] = field(default_factory=dict)             # bus path -> label
    nets: dict = field(default_factory=dict)                            # net key -> [NetClaim]
    positions: dict = field(default_factory=dict)      # (inst, dev, prop) -> resolved position
    jumpers_set: list = field(default_factory=list)    # (inst, jumper, state, position) config sheet
    channels: dict = field(default_factory=dict)       # (inst, dev, prop) -> (fn, ctrl, channel, period, flags)
    controllers: dict = field(default_factory=dict)    # ctrl label -> function (timer/adc to enable)
    scopes: dict = field(default_factory=dict)         # scope bus path -> (mux output label, channel) [R26]


def _key(inst: Instance, dev: Device):
    """Stable allocation order: R18 — never rig-file declaration order."""
    return (inst.socket, inst.name, dev.name)


def analyze(rig: Rig, workdir: str, diags: Diagnostics,
            board_dts: str | None = None,
            recipe: BuildRecipe | None = None,
            deps: Depends | None = None) -> Solved | None:
    board = load_board(rig.board, workdir, diags, board_dts, recipe, deps)
    if board is None:
        return None
    solved = Solved(rig=rig, board=board)
    types = load_types(deps)

    _check_matings(rig, board, types, solved, diags)
    # instances whose mating failed are absent from solved.sockets; every
    # later pass skips them individually rather than aborting the whole rig
    _collect_gpio_nets(rig, solved, types, diags)
    _allocate_addresses(rig, solved, diags)
    _allocate_cs(rig, solved, types, diags)
    _check_wires(rig, solved, types, diags)
    _check_nets(solved, types, diags)
    _check_labels(rig, diags)
    return solved


# ---------------------------------------------------------------- mating (R19/R20)

def _check_matings(rig, board, types, solved, diags):
    by_name = {i.name: i for i in rig.instances}
    per_socket: dict[str, list[Instance]] = {}
    for inst in rig.instances:
        socket = _resolve_socket(inst, by_name, board, types, solved, diags, ())
        if socket is None:
            continue
        if socket.type_name != inst.shield.plugs:
            diags.error(
                "phys-mating",
                f"instance '{inst.name}': shield '{inst.shield.name}' plugs "
                f"'{inst.shield.plugs}' but socket '{socket.label}' is a "
                f"'{socket.type_name}' socket — the connectors do not mate",
                [inst.src, socket.src])
            continue
        per_socket.setdefault(inst.socket, []).append(inst)

        # subset exposure (R20/S6): used proxies vs offered socket,<bus>
        used = {d.bus for d in inst.shield.devices if d.bus}
        for bus in sorted(used - set(socket.buses)):
            diags.error(
                "phys-subset",
                f"instance '{inst.name}': shield '{inst.shield.name}' needs the "
                f"socket's {bus.upper()} but '{socket.label}' does not expose "
                f"socket,{bus} (subset exposure is declared by absence)",
                [inst.src, socket.src])

    for ref, insts in sorted(per_socket.items()):
        if len(insts) < 2:
            continue
        ctype = types[solved.sockets[insts[0].name].type_name]
        if not ctype.stackable:
            diags.error(
                "phys-mating",
                f"{len(insts)} instances mate socket '{ref}' but connector type "
                f"'{ctype.name}' takes exactly one module (not stackable): "
                + ", ".join(i.name for i in insts),
                [i.src for i in insts])


def _resolve_socket(inst, by_name, board, types, solved, diags, stack):
    """The effective socket an instance mates — a board socket, or a socket
    RE-EXPORTED by a carrier instance (R19), composed down the nesting chain
    so its gpio-map lands on real SoC pins and its buses on real controllers.
    Memoized in solved.sockets."""
    if inst.name in solved.sockets:
        return solved.sockets[inst.name]

    ref = inst.socket
    if "." not in ref:                                  # board socket
        socket = board.sockets.get(ref)
        if socket is None:
            diags.error(
                "phys-socket",
                f"instance '{inst.name}': board '{board.name}' has no socket "
                f"'{ref}'\n"
                f"sockets of {board.name}: "
                + ", ".join(f"{s.label} ({s.type_name})"
                            for s in board.sockets.values()),
                [inst.src])
            return None
        solved.sockets[inst.name] = socket
        return socket

    # carrier-exported socket: "<carrier instance>.<exposed socket>"
    carrier_name, _, exp_name = ref.partition(".")
    if inst.name in stack or carrier_name in stack:
        diags.error("phys-socket",
                    f"instance '{inst.name}': socket nesting is cyclic ({ref})",
                    [inst.src])
        return None
    carrier = by_name.get(carrier_name)
    if carrier is None:
        diags.error(
            "phys-socket",
            f"instance '{inst.name}': socket '{ref}' names no instance "
            f"'{carrier_name}' in this rig\n"
            f"instances: {', '.join(sorted(by_name))}", [inst.src])
        return None
    parent = _resolve_socket(carrier, by_name, board, types, solved, diags,
                             stack + (inst.name,))
    if parent is None:
        return None
    exposed = carrier.shield.exposes.get(exp_name)
    if exposed is None:
        diags.error(
            "phys-socket",
            f"instance '{inst.name}': carrier '{carrier_name}' (shield "
            f"'{carrier.shield.name}') exposes no socket '{exp_name}'\n"
            f"exposed sockets: {', '.join(sorted(carrier.shield.exposes)) or 'none'}",
            [inst.src, carrier.src])
        return None
    socket = _compose_socket(inst, carrier, exposed, parent, solved, diags)
    solved.sockets[inst.name] = socket
    return socket


def _compose_socket(inst, carrier, exposed, parent, solved, diags):
    """Pass-through composition: exposed positions resolve to the parent's
    SoC pins, exposed buses to the parent's controllers (ontology §1)."""
    gpio_map = {}
    for pos, (parent_pos, _flags) in exposed.gpio_map.items():
        if parent_pos in parent.gpio_map:
            gpio_map[pos] = parent.gpio_map[parent_pos]
        # else: parent fragment doesn't route it -> stays socket-local (net key)
    buses = {}
    for kind, marker in exposed.buses.items():
        if marker == "plug":                            # pass-through (S6)
            if kind in parent.buses:
                buses[kind] = parent.buses[kind]
            else:
                diags.error(
                    "phys-subset",
                    f"carrier '{carrier.name}' passes {kind.upper()} through socket "
                    f"'{exposed.name}', but its parent socket '{parent.label}' offers "
                    f"no socket,{kind} (R19 pass-through needs the parent to provide it)",
                    [exposed.src, parent.src, inst.src])
        else:                                           # new scope (S8): ("scope", dev-label)
            root = f"{carrier.name}_{marker[1]}"
            scope_path = inst.socket                     # per (carrier, channel); shared by co-plugged modules
            buses[kind] = BusRef(label=f"{root}_ch{exposed.channel}", path=scope_path)
            solved.scopes[scope_path] = (root, exposed.channel)
    parent_nexus = parent.nexus_label or parent.label
    nexus_rows = [(child_pos, parent_nexus, parent_pos)
                  for child_pos, (parent_pos, _f) in exposed.gpio_map.items()]
    return BoardSocket(
        label=inst.socket, path=f"{parent.path}/{exposed.name}",
        type_name=exposed.type_name, gpio_map=gpio_map, buses=buses,
        cs_pool=exposed.cs_pool, src=exposed.src,
        nexus_label=f"{carrier.name}_{exposed.name}", nexus_rows=nexus_rows,
        parent=parent)


# ---------------------------------------------------------------- nets (R22/R23)

def _soc_net(socket: BoardSocket, position: int):
    """Net IDENTITY (ontology §2, derived): resolve the socket position through
    the gpio-map down to the actual SoC pin. Two DIFFERENT sockets whose
    positions map to the same SoC pin are the SAME net (Grove 5/6 → gpio0 26,
    R13). Positions not in the gpio-map (per-socket dedicated lines the trial
    fragment doesn't route, e.g. mikroBUS INT) stay socket-local."""
    mapping = socket.gpio_map.get(position)
    if mapping is not None:
        ctrl, pin, _flags = mapping
        return ("soc", ctrl, pin)
    return ("pos", socket.path, position)


def _register(solved, key, socket, position, claim):
    claim.socket = socket
    claim.position = position
    solved.nets.setdefault(key, []).append(claim)


def _net(solved, socket: BoardSocket, position: int, claim: NetClaim):
    _register(solved, _soc_net(socket, position), socket, position, claim)


def _collect_gpio_nets(rig, solved, types, diags):
    for inst in rig.instances:
        socket = solved.sockets.get(inst.name)
        if socket is None:
            continue
        ctype = types[socket.type_name]
        for dev in inst.shield.devices:
            for ref in dev.gpio_refs:
                if ref.function == "gpio":
                    _collect_gpio(inst, dev, ref, socket, ctype, solved, diags)
                else:
                    _collect_channel(inst, dev, ref, socket, ctype, solved, diags)


def _collect_gpio(inst, dev, ref, socket, ctype, solved, diags):
    pos = ref.position
    if ref.jumper is not None:
        pos = _resolve_jumper(inst, dev, ref, ctype, solved, diags)
        if pos is None:
            return
        solved.positions[(inst.name, dev.name, ref.prop)] = pos
    _net(solved, socket, pos, NetClaim(
        instance=inst, device=dev, what=f"{dev.name}: {ref.prop}",
        role=_role_of(ref.prop), src=ref.src))


def _collect_channel(inst, dev, ref, socket, ctype, solved, diags):
    """PWM/ADC (Slice A): the same position is reachable as a channel of a
    controller. Register TWO net claims — the PIN (exclusive: the pin can't
    also be GPIO or another function) and the CHANNEL (exclusive: two
    consumers can't share one timer/adc channel). Both fall out of net
    identity. Emit resolved + enable the controller (pinctrl noted, stubbed)."""
    fn = ref.function
    fmap = socket.pwm_map if fn == "pwm" else socket.adc_map
    resolved = fmap.get(ref.position)
    if resolved is None:
        diags.error(
            "phys-function",
            f"'{inst.name}/{dev.name}: {ref.prop}' uses position "
            f"{ctype.posname(ref.position)} as {fn.upper()}, but socket "
            f"'{socket.label}' offers no {fn} on it (no socket,{fn}-map entry)",
            [ref.src, socket.src])
        return
    if fn == "pwm" and ref.flags:
        # The expander's PWM emission (Bridge-A rewrite step 2b) is
        # flags-less by design: the socket-relative pwm-map nexus carries
        # only (position, period) -- matching the board's own
        # #pwm-cells=2 (atmel,sam0-tcc-pwm has no flags cell at all). A
        # nonzero flags value here is real wiring information (e.g.
        # polarity) that has nowhere to go, so reject rather than silently
        # drop it -- moved from the emitter (which must never fail, cli.py
        # never calls it inside a try/except) into this physically-worded
        # diagnostic, the one place `ref.flags` is visible before emission.
        diags.error(
            "phys-function",
            f"'{inst.name}/{dev.name}: {ref.prop}' authors PWM flags "
            f"{ref.flags:#x} at position {ctype.posname(ref.position)}, "
            "but the expander's PWM emission carries only (position, "
            "period) — there is no cell for flags",
            [ref.src, socket.src])
        return
    ctrl, channel = resolved
    solved.channels[(inst.name, dev.name, ref.prop)] = (
        fn, ctrl, channel, ref.period, ref.flags, ref.position)
    solved.controllers[ctrl] = fn
    label = "PWM" if fn == "pwm" else "ADC"
    # PIN net — exclusive use of the physical pin
    _net(solved, socket, ref.position, NetClaim(
        instance=inst, device=dev,
        what=f"{dev.name}: {ref.prop} ({label} pin)", role="dedicated", src=ref.src))
    # CHANNEL net — exclusive use of the controller channel
    _register(solved, ("chan", ctrl, channel), socket, ref.position, NetClaim(
        instance=inst, device=dev,
        what=f"{dev.name}: {ref.prop} ({label} {ctrl} ch{channel})",
        role="dedicated", src=ref.src))


def _resolve_jumper(inst, dev, ref, ctype, solved, diags):
    """A routing jumper's position must be pinned by the rig (explicit pin;
    non-CS positions are never auto-allocated). Returns the resolved index or
    None (+ diagnostic)."""
    jmp = inst.shield.jumpers[ref.jumper]
    dom = ", ".join(ctype.posname(p) for p in jmp.positions())
    sel = inst.jumpers.get(ref.jumper)
    if sel is None:
        diags.error(
            "phys-position",
            f"'{inst.name}/{dev.name}: {ref.prop}' routes through jumper "
            f"'{ref.jumper}' whose position must be selected — add "
            f"pin: {{ {ref.jumper}: <position> }} to the instance "
            f"(domain: {dom})", [ref.src, jmp.src])
        return None
    pos = ctype.positions[sel].index if sel in ctype.positions else sel
    if pos not in jmp.positions():
        diags.error(
            "phys-position",
            f"instance '{inst.name}': jumper '{ref.jumper}' selection '{sel}' is "
            f"not in its position domain ({dom}) — the copper cannot route it",
            [inst.jumper_refs.get(ref.jumper), jmp.src])
        return None
    solved.jumpers_set.append((inst, jmp, jmp.state_of(pos), pos))
    return pos


def _net_descr(key, claims, types) -> str:
    """Describe where a net lives, from its identity key: a controller channel
    (pwm/adc), a single socket position, or a SoC pin shared across sockets
    (R13)."""
    if key[0] == "chan":
        return f"{key[1]} channel {key[2]}"
    where = {(c.socket.label, c.position) for c in claims}
    if len(where) == 1:
        c = claims[0]
        return f"position {types[c.socket.type_name].posname(c.position)} of socket '{c.socket.label}'"
    if key[0] == "soc":
        return f"the shared SoC net {key[1]} pin {key[2]}"
    return "a shared net"


def _claim_line(c, types) -> str:
    pos = types[c.socket.type_name].posname(c.position)
    return f"- {c.instance.name} (socket {c.socket.label}, {pos}): {c.what}"


def _check_nets(solved, types, diags):
    for key, claims in sorted(solved.nets.items(), key=lambda kv: str(kv[0])):
        descr = _net_descr(key, claims, types)

        dedicated = [c for c in claims if c.role == "dedicated"]
        if len(dedicated) > 1:
            _exclusive_conflict(key, descr, dedicated, types, diags)
            continue
        if dedicated and len(claims) > 1:
            others = [c for c in claims if c.role != "dedicated"]
            diags.error(
                "phys-net",
                f"{descr} is claimed exclusively "
                f"({dedicated[0].instance.name}: {dedicated[0].what}) but is also "
                "claimed as a signal by:\n"
                + "\n".join(_claim_line(c, types) for c in others),
                [c.src for c in claims if c.src])
            continue

        drivers = [c for c in claims if c.role == "driver"]
        if len(drivers) > 1:
            diags.error(
                "phys-net",
                f"{len(drivers)} drivers on one net — {descr}:\n"
                + "\n".join(_claim_line(c, types) + " (device output)"
                            for c in drivers)
                + "\nnote: if these outputs are open-drain, wired-AND sharing is "
                "physically legal — drive-type on roles is a pending refinement "
                "(would downgrade this to a warning).",
                [c.src for c in drivers if c.src])
        # 1 driver + N listeners, or MCU-driven + N listeners: a net, legal (R22)


def _exclusive_conflict(key, descr, claims, types, diags):
    """Two exclusive claims on one resource. The resource kind (from the net
    key) tailors the code and the fix hint."""
    if key[0] == "chan":
        code, tail = "phys-channel", (
            "\ntwo consumers need the same controller channel — it cannot drive "
            "both independently. Use a different socket/channel, or one device.")
    else:
        code, tail = "phys-cs", (
            "\ntwo exclusive claims resolve to the same pin — shorted together, "
            "not realizable. If a CS is copper-fixed the pool cannot route around "
            "it: use different sockets, positions, or rework the copper.")
    diags.error(
        code,
        f"exclusive-resource conflict at {descr}:\n"
        + "\n".join(_claim_line(c, types) for c in claims) + tail,
        [c.src for c in claims if c.src])


# ---------------------------------------------------------------- addresses (R9/R17/R18)

def _allocate_addresses(rig, solved, diags):
    scopes: dict[str, list] = {}
    for inst in rig.instances:
        socket = solved.sockets.get(inst.name)
        if socket is None:
            continue
        for dev in inst.shield.devices:
            if dev.bus != "i2c" or "i2c" not in socket.buses:
                continue
            bus = socket.buses["i2c"]
            solved.bus_label[bus.path] = bus.label
            scopes.setdefault(bus.path, []).append((inst, dev, socket))

    for bus_path, members in sorted(scopes.items()):
        _allocate_scope(bus_path, members, solved, diags)


def _allocate_scope(bus_path, members, solved, diags):
    bus_label = solved.bus_label[bus_path]
    taken: dict[int, tuple] = {}

    def claim(addr, inst, dev, socket, how, src):
        if addr in taken:
            o_inst, o_dev, o_socket, o_how = taken[addr]
            diags.error(
                "phys-addr",
                f"I2C address {addr:#04x} is required twice on bus &{bus_label} "
                "(one address space per scope):\n"
                f"- {o_inst.name} (socket {o_socket.label}): {o_dev.name} — {o_how}\n"
                f"- {inst.name} (socket {socket.label}): {dev.name} — {how}\n"
                "two devices cannot share one address on one bus. This topology is "
                "not realizable as assembled: use a second I2C bus, put one device "
                "behind an I2C mux (scope creation, S8), or drop one instance.",
                [o_dev.src, o_inst.src, dev.src, inst.src])
            return False
        taken[addr] = (inst, dev, socket, how)
        solved.addr[(inst.name, dev.name)] = addr
        return True

    fixed, pinned, free = [], [], []
    for inst, dev, socket in members:
        if dev.reg is not None:
            fixed.append((inst, dev, socket))
        elif dev.addr_from and dev.addr_from in inst.pins:
            pinned.append((inst, dev, socket))
        else:
            free.append((inst, dev, socket))

    for inst, dev, socket in sorted(fixed, key=lambda m: _key(m[0], m[1])):
        claim(dev.reg, inst, dev, socket,
              f"address domain {{{dev.reg:#04x}}}, fixed by copper "
              "(no address-select)", dev.src)

    for inst, dev, socket in sorted(pinned, key=lambda m: _key(m[0], m[1])):
        strap = inst.shield.straps[dev.addr_from]
        want = inst.pins[dev.addr_from]
        match = [(a, s) for a, s in strap.domain if a == want]
        if not match:
            diags.error(
                "phys-pin",
                f"instance '{inst.name}': pinned address {want:#04x} is not in the "
                f"domain of strap '{strap.name}' "
                f"({{{', '.join(f'{a:#04x}' for a, _ in strap.domain)}}}) — "
                "the copper cannot select it",
                [inst.pin_refs.get(dev.addr_from), strap.src])
            continue
        if claim(want, inst, dev, socket,
                 f"pinned via rig (strap '{strap.name}')",
                 inst.pin_refs.get(dev.addr_from)):
            solved.straps.append((inst, strap, match[0][1], want))

    for inst, dev, socket in sorted(free, key=lambda m: _key(m[0], m[1])):
        strap = inst.shield.straps.get(dev.addr_from) if dev.addr_from else None
        if strap is None:
            continue  # loader already reported the addr-authority violation
        pick = next(((a, s) for a, s in strap.domain if a not in taken), None)
        if pick is None:
            diags.error(
                "phys-addr",
                f"address domain of '{inst.name}/{dev.name}' is exhausted on bus "
                f"&{bus_label}: every selectable address "
                f"{{{', '.join(f'{a:#04x}' for a, _ in strap.domain)}}} is already "
                "taken by:\n"
                + "\n".join(f"- {t[0].name}: {t[1].name} at {a:#04x}"
                            for a, t in sorted(taken.items())),
                [dev.src, inst.src])
            continue
        if claim(pick[0], inst, dev, socket, f"allocated (strap '{strap.name}')",
                 dev.src):
            solved.straps.append((inst, strap, pick[1], pick[0]))


# ---------------------------------------------------------------- CS pools (R4/R16)

def _allocate_cs(rig, solved, types, diags):
    scopes: dict[str, list] = {}
    for inst in rig.instances:
        socket = solved.sockets.get(inst.name)
        if socket is None:
            continue
        for dev in inst.shield.devices:
            if dev.bus != "spi" or "spi" not in socket.buses:
                continue
            bus = socket.buses["spi"]
            solved.bus_label[bus.path] = bus.label
            scopes.setdefault(bus.path, []).append((inst, dev, socket))

    for bus_path, members in sorted(scopes.items()):
        members.sort(key=lambda m: _key(m[0], m[1]))

        # 1) CS net per member: copper-fixed pins the position; else first
        #    free position from the socket's ordered pool (Conv. 1).
        placed = []
        for inst, dev, socket in members:
            ctype = types[socket.type_name]
            if dev.cs_position is not None:
                pos = dev.cs_position
                _net(solved, socket, pos, NetClaim(
                    instance=inst, device=dev,
                    what=f"{dev.name}: CS copper-fixed at {ctype.posname(pos)} "
                         "(shield,cs-position)",
                    role="dedicated", src=dev.src))
                placed.append((inst, dev, socket, pos))
                continue
            # cs_pool None-if-absent merge: inert for a REAL board socket
            # whose connector type declares a `socket,cs-pool` default
            # (board_edt.py backfills it, so `socket.cs_pool` is never None
            # there) -- but still LIVE for a shield-SYNTHESIZED socket
            # (carrier/mux `ExposedSocket`, composed into a `BoardSocket` by
            # `_compose_exposed_socket` above): those come from a plain
            # dtlib parse of the carrier `.shield` template (shields.py) with
            # no binding-default backfill, so `cs_pool` stays None unless the
            # carrier authors `socket,cs-pool` itself (arduino_uno_click,
            # i2c_mux do not) -- the ctype fallback is what supplies their
            # pool. Keep this merge; do not assume it is now dead.
            pool = socket.cs_pool if socket.cs_pool is not None else ctype.cs_pool
            pos = next((p for p in pool
                        if _soc_net(socket, p) not in solved.nets), None)
            if pos is None:
                diags.error(
                    "phys-cs",
                    f"CS pool of socket '{socket.label}' is exhausted for "
                    f"'{inst.name}/{dev.name}': candidates "
                    f"{', '.join(ctype.posname(p) for p in pool)} are all claimed",
                    [dev.src, inst.src])
                continue
            _net(solved, socket, pos, NetClaim(
                instance=inst, device=dev,
                what=f"{dev.name}: CS allocated at {ctype.posname(pos)}",
                role="dedicated", src=dev.src))
            placed.append((inst, dev, socket, pos))

        # 2) bus-wide index allocation: cs-gpios entries and child reg are
        #    written together, atomically, whatever socket contributed them.
        entries = []
        for index, (inst, dev, socket, pos) in enumerate(placed):
            solved.cs[(inst.name, dev.name)] = (index, pos)
            if socket.gpio_map.get(pos) is None:      # must resolve to a real SoC pin
                diags.error(
                    "phys-cs",
                    f"socket '{socket.label}' has no gpio-map entry for position "
                    f"{types[socket.type_name].posname(pos)} — the board fragment "
                    "cannot route this CS",
                    [socket.src, dev.src])
                continue
            entries.append((socket, pos))             # emitted through the nexus
        solved.cs_gpios[bus_path] = entries


# ---------------------------------------------------------------- wires (R22)

def _check_wires(rig, solved, types, diags):
    for wire in rig.wires:
        roles = []
        for end in (wire.frm, wire.to):
            pad = end.instance.shield.pads.get(end.node)
            if pad is None:
                diags.error(
                    "phys-wire",
                    f"wire end '{end.instance.name}.{end.node}' is not a pad — "
                    "only pads (arity-1 connectors) are wireable in the prototype",
                    [end.src])
                continue
            roles.append((end, pad.role))
        if len(roles) < 2:
            continue
        drivers = [e for e, r in roles if r == "driver"]
        if len(drivers) != 1:
            claims = ", ".join(
                f"{e.instance.name}.{e.node} ({r})" for e, r in roles)
            diags.error(
                "phys-wire",
                f"a net needs exactly one driver and ≥1 listener (R22); "
                f"wire has {len(drivers)} drivers: {claims}",
                [wire.src])
        if isinstance(wire.route, str) and wire.route != "adhoc":
            # candidate-2 spells route-via as a position NAME
            socket = solved.sockets.get(wire.frm.instance.name)
            ctype = types[socket.type_name] if socket else None
            if ctype and wire.route in ctype.positions:
                wire.route = ctype.positions[wire.route].index
            else:
                diags.error(
                    "phys-wire",
                    f"route 'via {wire.route}': no such position on connector type "
                    f"'{ctype.name if ctype else '?'}'", [wire.src])


# ---------------------------------------------------------------- emission feasibility

def _check_labels(rig, diags):
    """Strong contract: the emitter never fails — so the deterministic label
    scheme <instance>_<shield label> must be collision-free HERE."""
    seen = {}
    for inst in rig.instances:
        for dev in inst.shield.devices:
            label = f"{inst.name}_{dev.label}"
            if label in seen:
                diags.error(
                    "phys-label",
                    f"generated label '{label}' collides (instances '{inst.name}' "
                    "twice in one rig?) — deterministic naming (R10) cannot "
                    "disambiguate", [inst.src])
            seen[label] = inst
