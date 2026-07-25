"""The RIG MODEL (architecture.md): syntax-free semantic representation of a
rig. Schema = ontology.md §1–2. Declared facts ONLY — net-identity closure,
scope tree, conflicts, allocations are computed by the analyzer, never stored
here ("derived, never declared"). Both loaders must fill these structures
identically; that front-end neutrality is what makes the candidate
comparison honest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .diag import SrcRef

# ---------------------------------------------------------------- connector types


@dataclass
class Position:
    name: str          # "D7", "CS" — from the plug binding
    index: int         # from the dt-bindings header (single source of truth)
    function: str      # gpio | analog
    optional: bool = False


@dataclass
class ConnectorType:
    """A connector type IS its binding pair + index header (Conv. 1)."""
    name: str                          # "arduino-r3"
    positions: dict[str, Position]     # claimable positions, by name
    index2name: dict[int, str]         # ALL header indices (incl. bus copper)
    bus_proxies: list[str]             # allowed shield proxy nodes
    stackable: bool                    # mating multiplicity N vs 1
    cs_pool: list[int]                 # default ordered CS candidates (socket may override)

    def posname(self, index: int) -> str:
        return self.index2name.get(index, f"position {index}")


# ---------------------------------------------------------------- shield side


@dataclass
class GpioRef:
    """A gpio-spec property on a shield device. Two shapes (Conv. 2):
      fixed position  — <&plug POSITION flags>: position is `position`.
      deferred (R6)   — <&jumper flags>: position selected by a routing
                        jumper, `jumper` names it and `position` is None
                        until the analyzer resolves the rig's selection."""
    prop: str
    position: Optional[int]
    flags: int
    src: SrcRef
    jumper: Optional[str] = None
    function: str = "gpio"          # gpio | pwm | adc — which function-nexus resolves it
    period: Optional[int] = None    # pwm only: the period cell, passed through


@dataclass
class Device:
    name: str                       # node name without unit-address
    label: str                      # shield-local label (dl_rtc)
    compatible: Optional[str]
    bus: Optional[str]              # 'i2c' | 'spi' | 'uart' | None (plain group)
    group: Optional[str]            # non-bus group name ('gpio') for None-bus devices
    reg: Optional[int]              # authored = 1-element domain (address authority rule)
    addr_from: Optional[str]        # strap name — deferred address, explicit not absent
    cs_position: Optional[int]      # copper-fixed CS (shield,cs-position)
    collect: Optional[str] = None   # collection compatible (gpio-keys/leds): this is an ENTRY
    declared_params: list[str] = field(default_factory=list)  # shield,params: names a rig
    # may/must assign (Conv. entity-scoped naming). A name's PRESENCE among
    # this device's OTHER (non-model) properties is its default — the rig
    # may override it; its ABSENCE means the parameter is REQUIRED.
    gpio_refs: list[GpioRef] = field(default_factory=list)
    extra_props: list[tuple[str, str]] = field(default_factory=list)  # rendered passthrough
    src: Optional[SrcRef] = None


@dataclass
class Pad:
    """Arity-1 connector (ontology refinement 2)."""
    name: str
    label: str
    role: str                       # driver | listener | bidir (R23)
    of: Optional[str]               # device name it belongs to
    src: Optional[SrcRef] = None


@dataclass
class Strap:
    """Configuration element selecting from an ADDRESS domain (R17)."""
    name: str
    label: str
    domain: list[tuple[int, int]]   # (address, strap state) pairs — copper knowledge
    sheet_label: str
    src: Optional[SrcRef] = None


@dataclass
class Jumper:
    """Configuration element selecting from a POSITION domain (R6) — the
    position-side twin of Strap. Domain pairs are (position-index, state)."""
    name: str
    label: str
    domain: list[tuple[int, int]]   # (connector-position index, jumper state)
    sheet_label: str
    src: Optional[SrcRef] = None

    def positions(self) -> list[int]:
        return [p for p, _ in self.domain]

    def state_of(self, position: int):
        return next((s for p, s in self.domain if p == position), None)


@dataclass
class ExposedSocket:
    """A socket a carrier/interposer shield re-exports (R19). Pass-through:
    its positions bind to the carrier's OWN plug positions, its buses to the
    carrier's plug buses — net identity is preserved through the chain
    (ontology §1 interposers). The expander composes these against whatever
    the carrier itself plugs into."""
    name: str                       # node name — what the rig references after the dot
    label: str
    type_name: str                  # from compatible "socket,<type>"
    gpio_map: dict[int, tuple[int, int]]   # exposed position -> (parent plug position, flags)
    buses: dict[str, object]        # kind -> "plug" (pass-through, S6) | ("scope", dev-label) (new scope, S8)
    cs_pool: object = None          # authored override, else type default
    channel: object = None          # mux channel index (scope-creating interposer, S8)
    src: Optional[SrcRef] = None


@dataclass
class Shield:
    name: str                       # node name: "adafruit-data-logger"
    label: str                      # DTS label: data_logger
    plugs: str                      # consumed connector type, by string
    devices: list[Device] = field(default_factory=list)
    pads: dict[str, Pad] = field(default_factory=dict)
    straps: dict[str, Strap] = field(default_factory=dict)
    jumpers: dict[str, Jumper] = field(default_factory=dict)
    exposes: dict[str, ExposedSocket] = field(default_factory=dict)
    by_path: dict[str, object] = field(default_factory=dict)   # dtlib path -> element (candidate-1 lookups)
    src: Optional[SrcRef] = None

    def by_name(self, name: str) -> list:
        """Dotted-reference scope for candidate-2: pads ∪ devices ∪ straps."""
        hits: list = [p for n, p in self.pads.items() if n == name]
        hits += [d for d in self.devices if d.name == name]
        hits += [s for n, s in self.straps.items() if n == name]
        return hits

    def config_element(self, name: str):
        """A strap or jumper of this shield, by name (rig `pin:` targets)."""
        return self.straps.get(name) or self.jumpers.get(name)

    def names(self) -> list[str]:
        return sorted(list(self.pads) + [d.name for d in self.devices] + list(self.straps))


# ---------------------------------------------------------------- board side
# The board DT is expander input (Conv. 4); these are read, not authored, facts.


@dataclass
class BusRef:
    label: str                      # 'i2c1' — emission target &i2c1
    path: str                       # dtlib path, scope identity


@dataclass
class BoardSocket:
    label: str                      # 'nucleo_ard' — what rig,socket names
    path: str
    type_name: str                  # from compatible "socket,<type>"
    gpio_map: dict[int, tuple[str, int, int]]   # position -> (ctrl label, pin, flags)
    buses: dict[str, BusRef]        # 'i2c'/'spi'/'uart' present = offered subset
    cs_pool: Optional[list[int]]    # authored override, else type default
    pwm_map: dict = field(default_factory=dict)   # position -> (timer label, channel) [multi-function nexus]
    adc_map: dict = field(default_factory=dict)   # position -> (adc label, channel)
    # emission (Conv. 3 / R19): every socket is referenced through a nexus.
    # Board sockets are real DT nodes (nexus_label=None -> use label, nothing
    # to synthesize). A carrier's re-exported socket has no DT node, so the
    # emitter SYNTHESIZES one (nexus_label + nexus_rows) that chains to its
    # parent's nexus — matching hand-written nested overlays (Option C).
    nexus_label: Optional[str] = None
    nexus_rows: Optional[list] = None   # [(child_pos, parent_nexus_label, parent_pos)]
    parent: object = None               # parent BoardSocket (for transitive synthesis)
    src: Optional[SrcRef] = None


@dataclass
class Board:
    name: str
    sockets: dict[str, BoardSocket]  # by label


# ---------------------------------------------------------------- rig level


@dataclass
class Instance:
    name: str                       # logger_a
    shield: Shield
    socket: str                     # cross-tree string (Conv. 5)
    pins: dict[str, int] = field(default_factory=dict)  # strap name -> pinned address (R18)
    pin_refs: dict[str, SrcRef] = field(default_factory=dict)
    jumpers: dict[str, object] = field(default_factory=dict)  # jumper name -> raw position (name/index)
    jumper_refs: dict[str, SrcRef] = field(default_factory=dict)
    invert: bool = False            # flip the active level of the module's gpio signals
    # rig `params:` — per-instance property assignments, keyed by shield-local
    # DEVICE LABEL then property name; raw value TEXT (emission is verbatim,
    # never resolved — resolution is a loader/config-sheet concern only).
    params: dict[str, dict[str, str]] = field(default_factory=dict)
    param_refs: dict[str, dict[str, SrcRef]] = field(default_factory=dict)
    src: Optional[SrcRef] = None


@dataclass
class WireEnd:
    instance: Instance
    node: str                       # pad/device name within the instance's shield
    src: Optional[SrcRef] = None


@dataclass
class Wire:
    frm: WireEnd
    to: WireEnd
    route: Union[str, int]          # 'adhoc' | header position index (route-via)
    src: Optional[SrcRef] = None


@dataclass
class Rig:
    name: str
    board: str                      # cross-tree string
    instances: list[Instance] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    # rig `dt-includes:` — headers this rig's assigned param TOKENS resolve
    # against, exactly as they would appear in a DTS `#include <...>`.
    dt_includes: list[str] = field(default_factory=list)
    dt_includes_refs: list[SrcRef] = field(default_factory=list)
    src: Optional[SrcRef] = None
