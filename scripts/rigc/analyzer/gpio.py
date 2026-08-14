"""Net identity, GPIO/PWM/ADC claims, jumper resolution, and the final net
conflict report (rigc-r4-brief.md Sec 4). Ported from rigexp/analyzer.py's
`_collect_gpio_nets`/`_collect_gpio`/`_collect_channel`/`_resolve_jumper`/
`_check_nets`/`_exclusive_conflict` (`analyzer.py:263-440`), value-shaped.

Net IDENTITY is sharing (ontology Sec 2): `soc_net` resolves a socket
position through the board's own gpio-map down to the actual SoC pin, so
two DIFFERENT sockets whose positions map to the same pin are the SAME net
(R13) -- a pure function of (socket, position), directly unit-testable.
`role_of` is the other already-value-shaped contract this module keeps
(mission brief Sec 6 lists both by name).

`collect_gpio_nets` is the pass: it walks every resolved instance's
device gpio/pwm/adc refs, building the net-claim map plus jumper-resolved
positions and pwm/adc channel resolutions, entirely as a RETURNED value
(`GpioNets`) -- `check_nets` is a SEPARATE, later function (the blueprint's
own pass ordering: net collection happens before CS allocation, but net
CONFLICT checking happens after, since CS allocation contributes further
claims into the same net-claim map -- see analyzer/cs.py and
analyzer/__init__.py's composer, which merges the two claim sets before
calling check_nets)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..diag import Diagnostic, SourceRef, error
from ..model import (BoardSocket, ConnectorType, Device, GpioRef, Instance,
                     Jumper, Rig)
from .socketmap import Sockets, for_ref

_DRIVER_HINTS = ("int", "irq")

#: A net's identity: ("soc", controller label, pin) for a position the
#: board's gpio-map actually routes to a real SoC pin (R13 -- shared
#: across sockets); ("pos", socket path, position) for a per-socket
#: dedicated line the board fragment doesn't route; ("chan", controller
#: label, channel) for a PWM/ADC controller CHANNEL (exclusive use of one
#: timer/adc channel, independent of which pin reaches it).
NetKey = Tuple[object, ...]


@dataclass(frozen=True)
class NetClaim:
    instance: Instance
    device: Optional[Device]
    what: str                       # "rtc@…: int1-gpios" / "sdhc: CS (copper-fixed)" / pad name
    role: str                       # driver | listener | dedicated
    socket: BoardSocket
    position: int
    src: Optional[SourceRef] = None


#: Every net's claims, keyed by NetKey -- composed upward by simple dict
#: merge (`merge_nets`), the same way diagnostic lists compose by
#: concatenation.
Nets = Dict[NetKey, List[NetClaim]]


def merge_nets(*nets: Nets) -> Nets:
    """Compose several Nets values into one, preserving claim order within
    each key (earlier collections' claims first) -- the net-claim analogue
    of `deps.union`/list-concatenating diagnostics.

    Returns a FRESH map with fresh lists: neither the input maps nor
    their claim lists are shared with the result (R4's D1 is the
    cautionary tale for anyone tempted to alias here)."""
    result: Nets = {}
    for n in nets:
        for key, claims in n.items():
            result.setdefault(key, []).extend(claims)
    return result


def role_of(prop_name: str) -> str:
    """Endpoint role, inferred from the property name (prototype stopgap,
    carried from the blueprint: int*/irq* = device drives; everything
    else = device listens; pads/CS claims are always 'dedicated', never
    routed through this function)."""
    stem = prop_name[:-6] if prop_name.endswith("-gpios") else prop_name
    if any(h in stem for h in _DRIVER_HINTS):
        return "driver"       # device output (interrupt line etc.)
    return "listener"         # MCU-driven towards the device


def soc_net(socket: BoardSocket, position: int) -> NetKey:
    """Net IDENTITY (ontology Sec 2, derived): resolve the socket position
    through the gpio-map down to the actual SoC pin. Two DIFFERENT sockets
    whose positions map to the same SoC pin are the SAME net (Grove 5/6 ->
    gpio0 26, R13). Positions not in the gpio-map (per-socket dedicated
    lines the trial fragment doesn't route, e.g. mikroBUS INT) stay
    socket-local."""
    mapping = socket.gpio_map.get(position)
    if mapping is not None:
        ctrl, pin, _flags = mapping
        return ("soc", ctrl, pin)
    return ("pos", socket.path, position)


@dataclass
class GpioNets:
    nets: Nets = field(default_factory=dict)
    positions: Dict[Tuple[str, str, str], int] = field(default_factory=dict)
    jumpers_set: List[Tuple[Instance, Jumper, Optional[int], int]] = field(
        default_factory=list)
    channels: Dict[Tuple[str, str, str], Tuple[str, str, int, Optional[int], int, int]] = \
        field(default_factory=dict)
    controllers: Dict[str, str] = field(default_factory=dict)


def collect_gpio_nets(rig: Rig, sockets: Sockets,
                      types: Dict[str, ConnectorType],
                      ) -> Tuple[GpioNets, List[Diagnostic]]:
    """The gpio/pwm/adc claim-collection pass (R22/R23): every device
    ref resolves through ITS OWN plug's socket (`ref.plug`, PER-REFERENCE
    granularity, multi-plug-shield-brief.md Sec 2 ruling 2) into net
    claims -- a device sitting on one plug's bus may still carry a
    cross-plug reference to another.

    Returns (nets, diagnostics): a fresh claim map the caller owns --
    later passes read it but must never append into its lists (R4
    review, D1)."""
    diags: List[Diagnostic] = []
    result = GpioNets()

    def claim(key: NetKey, socket: BoardSocket, position: int,
             inst: Instance, device: Optional[Device], what: str, role: str,
             src: Optional[SourceRef]) -> None:
        result.nets.setdefault(key, []).append(NetClaim(
            instance=inst, device=device, what=what, role=role,
            socket=socket, position=position, src=src))

    for inst in rig.instances:
        for dev in inst.shield.devices:
            for ref in dev.gpio_refs:
                socket = for_ref(sockets, inst, ref)
                if socket is None:
                    continue
                ctype = types[socket.type_name]
                if ref.function == "gpio":
                    _collect_gpio(inst, dev, ref, socket, ctype, result, claim, diags)
                else:
                    _collect_channel(inst, dev, ref, socket, ctype, result, claim, diags)
    return result, diags


def _collect_gpio(inst: Instance, dev: Device, ref: GpioRef, socket: BoardSocket,
                  ctype: ConnectorType, result: GpioNets, claim, diags: List[Diagnostic],
                  ) -> None:
    pos = ref.position
    if ref.jumper is not None:
        resolved = _resolve_jumper(inst, dev, ref, ctype, result, diags)
        if resolved is None:
            return
        pos = resolved
        result.positions[(inst.name, dev.name, ref.prop)] = pos
    assert pos is not None
    claim(soc_net(socket, pos), socket, pos, inst, dev,
         f"{dev.name}: {ref.prop}", role_of(ref.prop), ref.src)


def _collect_channel(inst: Instance, dev: Device, ref: GpioRef, socket: BoardSocket,
                     ctype: ConnectorType, result: GpioNets, claim,
                     diags: List[Diagnostic]) -> None:
    """PWM/ADC: the same position is reachable as a channel of a
    controller. Register TWO net claims -- the PIN (exclusive: the pin
    can't also be GPIO or another function) and the CHANNEL (exclusive:
    two consumers can't share one timer/adc channel)."""
    fn = ref.function
    # pwm/adc refs always carry a fixed position at parse time (shields.py):
    # jumper deferral is a gpio-only shape (Sec 4/R6).
    assert ref.position is not None
    pos = ref.position
    fmap = socket.pwm_map if fn == "pwm" else socket.adc_map
    resolved = fmap.get(pos)
    if resolved is None:
        diags.append(error(
            "phys-function",
            f"'{inst.name}/{dev.name}: {ref.prop}' uses position "
            f"{ctype.posname(pos)} as {fn.upper()}, but socket "
            f"'{socket.label}' offers no {fn} on it (no socket,{fn}-map entry)",
            tuple(x for x in (ref.src, socket.src) if x)))
        return
    if fn == "pwm" and ref.flags:
        diags.append(error(
            "phys-function",
            f"'{inst.name}/{dev.name}: {ref.prop}' authors PWM flags "
            f"{ref.flags:#x} at position {ctype.posname(pos)}, "
            "but the expander's PWM emission carries only (position, "
            "period) — there is no cell for flags",
            tuple(x for x in (ref.src, socket.src) if x)))
        return
    ctrl, channel = resolved
    result.channels[(inst.name, dev.name, ref.prop)] = (
        fn, ctrl, channel, ref.period, ref.flags, pos)
    result.controllers[ctrl] = fn
    label = "PWM" if fn == "pwm" else "ADC"
    # PIN net -- exclusive use of the physical pin
    claim(soc_net(socket, pos), socket, pos, inst, dev,
         f"{dev.name}: {ref.prop} ({label} pin)", "dedicated", ref.src)
    # CHANNEL net -- exclusive use of the controller channel
    claim(("chan", ctrl, channel), socket, pos, inst, dev,
         f"{dev.name}: {ref.prop} ({label} {ctrl} ch{channel})", "dedicated",
         ref.src)


def _resolve_jumper(inst: Instance, dev: Device, ref: GpioRef, ctype: ConnectorType,
                    result: GpioNets, diags: List[Diagnostic]) -> Optional[int]:
    """A routing jumper's position must be pinned by the rig (explicit
    config:; non-CS positions are never auto-allocated). Returns the
    resolved index or None (+ diagnostic)."""
    assert ref.jumper is not None      # only called when the caller already checked
    jmp = inst.shield.jumpers[ref.jumper]
    dom = ", ".join(ctype.posname(p) for p in jmp.positions())
    sel = inst.jumpers.get(ref.jumper)
    if sel is None:
        diags.append(error(
            "phys-position",
            f"'{inst.name}/{dev.name}: {ref.prop}' routes through jumper "
            f"'{ref.jumper}' whose position must be selected — add "
            f"config: {{ {jmp.label}: <position> }} to the instance "
            f"(domain: {dom})", tuple(x for x in (ref.src, jmp.src) if x)))
        return None
    pos = ctype.positions[sel].index if sel in ctype.positions else sel
    if pos not in jmp.positions():
        diags.append(error(
            "phys-position",
            f"instance '{inst.name}': jumper '{ref.jumper}' selection '{sel}' is "
            f"not in its position domain ({dom}) — the copper cannot route it",
            tuple(x for x in (inst.jumper_refs.get(ref.jumper), jmp.src) if x)))
        return None
    result.jumpers_set.append((inst, jmp, jmp.state_of(pos), pos))
    return pos


def _net_descr(key: NetKey, claims: List[NetClaim], types: Dict[str, ConnectorType]) -> str:
    """Describe where a net lives, from its identity key: a controller
    channel (pwm/adc), a single socket position, or a SoC pin shared
    across sockets (R13)."""
    if key[0] == "chan":
        return f"{key[1]} channel {key[2]}"
    where = {(c.socket.label, c.position) for c in claims}
    if len(where) == 1:
        c = claims[0]
        return f"position {types[c.socket.type_name].posname(c.position)} of socket '{c.socket.label}'"
    if key[0] == "soc":
        return f"the shared SoC net {key[1]} pin {key[2]}"
    return "a shared net"


def _claim_line(c: NetClaim, types: Dict[str, ConnectorType]) -> str:
    pos = types[c.socket.type_name].posname(c.position)
    return f"- {c.instance.name} (socket {c.socket.label}, {pos}): {c.what}"


def check_nets(nets: Nets, types: Dict[str, ConnectorType]) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    for key, claims in sorted(nets.items(), key=lambda kv: str(kv[0])):
        descr = _net_descr(key, claims, types)

        dedicated = [c for c in claims if c.role == "dedicated"]
        if len(dedicated) > 1:
            diags.append(_exclusive_conflict(key, descr, dedicated, types))
            continue
        if dedicated and len(claims) > 1:
            others = [c for c in claims if c.role != "dedicated"]
            diags.append(error(
                "phys-net",
                f"{descr} is claimed exclusively "
                f"({dedicated[0].instance.name}: {dedicated[0].what}) but is also "
                "claimed as a signal by:\n"
                + "\n".join(_claim_line(c, types) for c in others),
                tuple(c.src for c in claims if c.src)))
            continue

        drivers = [c for c in claims if c.role == "driver"]
        if len(drivers) > 1:
            diags.append(error(
                "phys-net",
                f"{len(drivers)} drivers on one net — {descr}:\n"
                + "\n".join(_claim_line(c, types) + " (device output)"
                            for c in drivers)
                + "\nnote: if these outputs are open-drain, wired-AND sharing is "
                "physically legal — drive-type on roles is a pending refinement "
                "(would downgrade this to a warning).",
                tuple(c.src for c in drivers if c.src)))
        # 1 driver + N listeners, or MCU-driven + N listeners: a net, legal (R22)
    return diags


def _exclusive_conflict(key: NetKey, descr: str, claims: List[NetClaim],
                        types: Dict[str, ConnectorType]) -> Diagnostic:
    """Two exclusive claims on one resource. The resource kind (from the
    net key) tailors the code and the fix hint."""
    if key[0] == "chan":
        code, tail = "phys-channel", (
            "\ntwo consumers need the same controller channel — it cannot drive "
            "both independently. Use a different socket/channel, or one device.")
    else:
        code, tail = "phys-cs", (
            "\ntwo exclusive claims resolve to the same pin — shorted together, "
            "not realizable. If a CS is copper-fixed the pool cannot route around "
            "it: use different sockets, positions, or rework the copper.")
    return error(
        code,
        f"exclusive-resource conflict at {descr}:\n"
        + "\n".join(_claim_line(c, types) for c in claims) + tail,
        tuple(c.src for c in claims if c.src))
