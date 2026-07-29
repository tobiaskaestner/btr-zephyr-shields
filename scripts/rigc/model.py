"""The rig model: syntax-free semantic representation of a rig, plus (R3)
the shield-template model every instance's `shield:` reference resolves
against.

Mirrors rigexp/model.py's shape for the same entities (Rig, Instance, Wire,
WireEnd, AxisDecl, and now the shield-side ConnectorType/Shield/Device/
Pad/Strap/Jumper/ExposedSocket family) closely enough that a reviewer
comparing the two trees recognizes the same ontology.

R2's ShieldRef seam is GONE (rigc-r3-brief.md Sec 0): Instance.shield is
now a real, resolved Shield -- rigc's loader/library.py builds the
library and resolves every reference against it before an Instance ever
exists, exactly as rigexp's loader_yml.load_shield_library +
ShieldLibrary.resolve do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from .diag import SourceRef

# ---------------------------------------------------------------- connector types


@dataclass
class Position:
    """One claimable plug position ("D7", "CS") -- name from the plug
    binding, index from the dt-bindings header (the single source of
    truth position.index resolves against)."""

    name: str
    index: int
    function: str          # gpio | analog
    optional: bool = False


@dataclass
class ConnectorType:
    """A connector type IS its binding pair + index header (Conv. 1,
    registry.py's own docstring)."""

    name: str                          # "arduino-r3"
    positions: Dict[str, Position]     # claimable positions, by name
    index2name: Dict[int, str]         # ALL header indices (incl. bus copper)
    bus_proxies: List[str]             # allowed shield proxy nodes
    stackable: bool                    # mating multiplicity N vs 1
    cs_pool: List[int]                 # default ordered CS candidates

    def posname(self, index: int) -> str:
        return self.index2name.get(index, f"position {index}")


# ---------------------------------------------------------------- shield side


@dataclass
class GpioRef:
    """A gpio-spec property on a shield device. Two shapes (Conv. 2):
      fixed position  -- <&plug POSITION flags>: position is position.
      deferred (R6)   -- <&jumper flags>: position selected by a routing
                        jumper, jumper names it and position is None
                        until the analyzer resolves the rig's selection."""

    prop: str
    position: Optional[int]
    flags: int
    src: SourceRef
    jumper: Optional[str] = None
    function: str = "gpio"          # gpio | pwm | adc
    period: Optional[int] = None    # pwm only: the period cell, passed through


@dataclass
class Device:
    name: str                       # node name without unit-address
    label: str                      # shield-local label (dl_rtc)
    compatible: Optional[str]
    bus: Optional[str]              # "i2c" | "spi" | "uart" | None (plain group)
    group: Optional[str]            # non-bus group name ("gpio") for None-bus devices
    reg: Optional[int]              # authored = 1-element domain (address authority rule)
    addr_from: Optional[str]        # strap name -- deferred address, explicit not absent
    cs_position: Optional[int]      # copper-fixed CS (shield,cs-position)
    collect: Optional[str] = None   # collection compatible (gpio-keys/leds): this is an ENTRY
    declared_params: List[str] = field(default_factory=list)  # shield,params: names
    gpio_refs: List[GpioRef] = field(default_factory=list)
    extra_props: List[Tuple[str, str]] = field(default_factory=list)  # rendered passthrough
    src: Optional[SourceRef] = None


@dataclass
class Pad:
    """Arity-1 connector (ontology refinement 2)."""

    name: str
    label: str
    role: str                       # driver | listener | bidir (R23)
    of: Optional[str]               # device name it belongs to
    src: Optional[SourceRef] = None


@dataclass
class Strap:
    """Configuration element selecting from an ADDRESS domain (R17)."""

    name: str
    label: str
    domain: List[Tuple[int, int]]   # (address, strap state) pairs
    sheet_label: str
    src: Optional[SourceRef] = None


@dataclass
class Jumper:
    """Configuration element selecting from a POSITION domain (R6) -- the
    position-side twin of Strap."""

    name: str
    label: str
    domain: List[Tuple[int, int]]   # (connector-position index, jumper state)
    sheet_label: str
    src: Optional[SourceRef] = None

    def positions(self) -> List[int]:
        return [p for p, _ in self.domain]

    def state_of(self, position: int) -> Optional[int]:
        return next((s for p, s in self.domain if p == position), None)


@dataclass
class ExposedSocket:
    """A socket a carrier/interposer shield re-exports (R19)."""

    name: str                       # node name -- what the rig references after the dot
    label: str
    type_name: str                  # from compatible "socket,<type>"
    gpio_map: Dict[int, Tuple[int, int]]   # exposed position -> (parent plug position, flags)
    buses: Dict[str, object]        # kind -> "plug" (pass-through, S6) | ("scope", dev-label) (S8)
    cs_pool: object = None          # authored override, else type default
    channel: object = None          # mux channel index (scope-creating interposer, S8)
    src: Optional[SourceRef] = None


@dataclass
class Shield:
    name: str                       # node name: "adafruit-data-logger"
    label: str                      # DTS label: data_logger
    plugs: str                      # consumed connector type, by string
    devices: List[Device] = field(default_factory=list)
    pads: Dict[str, Pad] = field(default_factory=dict)
    straps: Dict[str, Strap] = field(default_factory=dict)
    jumpers: Dict[str, Jumper] = field(default_factory=dict)
    exposes: Dict[str, ExposedSocket] = field(default_factory=dict)
    by_path: Dict[str, object] = field(default_factory=dict)   # dtlib path -> element
    # shield.yml's declared revisions: axis (V1c) and which one THIS Shield
    # represents -- both None for a shield with no revisions: block.
    revisions: Optional["AxisDecl"] = None
    revision: Optional[str] = None
    src: Optional[SourceRef] = None

    def by_name(self, name: str) -> List[object]:
        """Dotted-reference scope: pads UNION devices UNION straps."""
        hits: List[object] = [p for n, p in self.pads.items() if n == name]
        hits += [d for d in self.devices if d.name == name]
        hits += [s for n, s in self.straps.items() if n == name]
        return hits

    def config_element(self, name: str) -> Optional[Union["Strap", "Jumper"]]:
        """A strap or jumper of this shield, by name (rig pin: targets)."""
        return self.straps.get(name) or self.jumpers.get(name)

    def names(self) -> List[str]:
        return sorted(list(self.pads) + [d.name for d in self.devices] + list(self.straps))


@dataclass
class WireEnd:
    """One `<instance>.<node>` endpoint. `node` stays the raw string (the
    instance's OWN `Shield.by_name(node)` is the resolution scope, checked
    at the point a WireEnd is constructed -- loader/delta.py's
    `resolve_dotted` -- not stored redundantly here)."""

    instance_name: str
    node: str
    src: SourceRef


@dataclass
class Wire:
    frm: WireEnd
    to: WireEnd
    route: Union[str, int]          # "adhoc" | via: position name (raw)
    src: SourceRef


@dataclass
class Instance:
    name: str
    shield: Shield
    socket: str                     # already resolved through a SocketBinding
    invert: bool = False            # flip the active level of the module's gpio signals
    pins: Dict[str, int] = field(default_factory=dict)          # strap name -> pinned address
    pin_refs: Dict[str, SourceRef] = field(default_factory=dict)
    jumpers: Dict[str, object] = field(default_factory=dict)    # jumper name -> raw position
    jumper_refs: Dict[str, SourceRef] = field(default_factory=dict)
    # rig params: -- per-instance property assignments, keyed by
    # shield-local DEVICE LABEL then property name; raw value TEXT
    # (emission is verbatim, never resolved -- resolution is a
    # loader/config-sheet concern only).
    params: Dict[str, Dict[str, str]] = field(default_factory=dict)
    param_refs: Dict[str, Dict[str, SourceRef]] = field(default_factory=dict)
    src: Optional[SourceRef] = None


@dataclass
class AxisDecl:
    """One declared qualifier axis (rig.yml `revisions:` or `variants:`):
    the values a selection may take, and the one a bare (unqualified)
    target takes by default. Ported value-shaped, unchanged in shape,
    from rigexp/model.py's own AxisDecl -- the hwmv2 seam
    (rigc-r2-brief.md Sec 3) keeps resolution a single pure function
    over (decl, selected), so this dataclass is exactly the value that
    swap will later replace the declaration parsing behind.

    boards/sockets carry, per declared VALUE, the board a rig variant
    selects and its abstract-socket map -- populated only for a rig's
    own `variants:` axis when it uses the per-variant-board shape;
    empty for every other axis."""

    values: list[str]
    default: Optional[str] = None
    boards: dict[str, str] = field(default_factory=dict)
    sockets: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Rig:
    name: str
    board: str = ""
    instances: list[Instance] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    dt_includes: list[str] = field(default_factory=list)
    dt_includes_refs: list[SourceRef] = field(default_factory=list)
    revisions: Optional[AxisDecl] = None
    variants: Optional[AxisDecl] = None
    revision: Optional[str] = None
    variant: Optional[str] = None
    src: Optional[SourceRef] = None
