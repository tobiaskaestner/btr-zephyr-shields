"""The rig model: syntax-free semantic representation of a rig, plus the
shield-template model every instance's `shield:` reference resolves
against.

`Instance.shield` is a real, resolved `Shield`: `loader/library.py`
builds the shield library and resolves every reference against it
before an `Instance` ever exists, so nothing downstream carries an
unresolved reference."""
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
    """A connector type IS its binding pair + index header."""

    name: str                          # "arduino-r3"
    positions: Dict[str, Position]     # claimable positions, by name
    index2name: Dict[int, str]         # ALL header indices (incl. bus copper)
    bus_proxies: List[str]             # allowed shield proxy nodes
    stackable: bool                    # mating multiplicity N vs 1
    # default ordered CS candidates, keyed by the QUALIFIED bus name a
    # multi-bus connector type suffixes with a role ("spi" bare, or
    # "spi-sensors"/"spi-motors" once a type offers more than one SPI
    # bus); only spi-kind buses ever populate this, i2c/uart never read it
    cs_pool: Dict[str, List[int]]

    def posname(self, index: int) -> str:
        return self.index2name.get(index, f"position {index}")


# ---------------------------------------------------------------- shield side


@dataclass
class GpioRef:
    """A gpio-spec property on a shield device. Two shapes::

      fixed position -- <&plug POSITION flags>: position is position.
      deferred        -- <&jumper flags>: position selected by a routing
                          jumper, jumper names it and position is None
                          until the analyzer resolves the rig's selection.

    `plug` is the SLOT this reference resolves through -- the shield's own
    plug node the phandle actually named, recorded PER-REFERENCE rather
    than per-device: a device sitting on one plug's bus may still carry a
    gpio ref that names a DIFFERENT plug. For a shield with one plug this
    is that plug's own node name -- `"plug"` by convention, but its NAME,
    not a default."""

    prop: str
    position: Optional[int]
    flags: int
    src: SourceRef
    jumper: Optional[str] = None
    function: str = "gpio"          # gpio | pwm | adc
    period: Optional[int] = None    # pwm only: the period cell, passed through
    plug: str = "plug"


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
    # the slot THIS device's own BUS group nests under -- None for a
    # plain (non-bus) group device, which is plug-agnostic (its own gpio
    # refs each carry their own plug instead); "plug" for any bus device
    # of a single-plug shield. Never consulted for a plain-group device
    # (nothing reads it without first checking `bus` is not None).
    plug: Optional[str] = "plug"
    collect: Optional[str] = None   # collection compatible (gpio-keys/leds): this is an ENTRY
    declared_params: List[str] = field(default_factory=list)  # shield,params: names
    # shield,param-includes: headers -- a macro-only header contributes no
    # node/property of its own, so it cannot be recovered from this
    # device's other DTS content and must be declared explicitly, on the
    # SAME node as the parameter it backs.
    declared_param_includes: List[str] = field(default_factory=list)
    gpio_refs: List[GpioRef] = field(default_factory=list)
    extra_props: List[Tuple[str, str]] = field(default_factory=list)  # rendered passthrough
    src: Optional[SourceRef] = None


@dataclass
class Pad:
    """Arity-1 connector."""

    name: str
    label: str
    role: str                       # driver | listener | bidir
    of: Optional[str]               # device name it belongs to
    src: Optional[SourceRef] = None


@dataclass
class Strap:
    """Configuration element selecting from an ADDRESS domain."""

    name: str
    label: str
    domain: List[Tuple[int, int]]   # (address, strap state) pairs
    sheet_label: str
    src: Optional[SourceRef] = None


@dataclass
class Jumper:
    """Configuration element selecting from a POSITION domain -- the
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
    """A socket a carrier/interposer shield re-exports, potentially
    composed from SEVERAL named parents: a plural carrier's exposed
    socket may pass through or scope-create buses sourced from different
    plugs, and each gpio-map row may resolve through a different plug
    too."""

    name: str                       # node name -- what the rig references after the dot
    label: str
    type_name: str                  # from compatible "socket,<type>"
    # exposed position -> (parent SLOT, parent plug position, flags) --
    # the phandle a gpio-map row carries names WHICH of the carrier's
    # plugs the row resolves through; "plug" for every row of a
    # single-plug carrier.
    gpio_map: Dict[int, Tuple[str, int, int]]
    # kind (bare, or role-suffixed per the multi-bus vocabulary) ->
    # ("plug", parent SLOT) pass-through | ("scope", dev-label) new
    # scope -- the scope root is a device, which already carries its
    # own slot via Device.plug.
    buses: Dict[str, Tuple[str, str]]
    # PWM/ADC pass-through: SAME shape as gpio_map -- position -> (parent
    # SLOT, parent plug position, trailing filler cell). The filler is
    # always 0 (pwm's row carries an unused period placeholder here; adc's
    # row has no such cell in the DTS source at all).
    pwm_map: Dict[int, Tuple[str, int, int]] = field(default_factory=dict)
    adc_map: Dict[int, Tuple[str, int, int]] = field(default_factory=dict)
    # The carrier's OWN declared #pwm-cells / #io-channel-cells: mandatory
    # alongside the corresponding map, read here so compose_socket can
    # refuse a disagreement against the resolved parent's own count
    # without re-deriving it. None when the socket carries no map for
    # that function.
    pwm_cells: Optional[int] = None
    adc_cells: Optional[int] = None
    # per-qualified-bus authored cs-pool override, keyed the same way
    # BoardSocket.buses/ConnectorType.cs_pool are (kind, or kind-role) --
    # a bare "socket,cs-pool" property parses into the "spi" entry, since
    # CS only ever applies to SPI. Absent from the dict = no override.
    cs_pool: Dict[str, List[int]] = field(default_factory=dict)
    channel: Optional[int] = None   # mux channel index (scope-creating interposer)
    src: Optional[SourceRef] = None


@dataclass
class Shield:
    name: str                       # node name: "adafruit-data-logger"
    label: str                      # DTS label: data_logger
    # slot name -> consumed connector type, in AUTHORING order. One entry
    # per plug NODE, keyed by that node's own name (conventionally
    # `"plug"` for a shield with one). Every consumer keys through this
    # rather than assuming a bare string, and `len(plugs) > 1` IS the
    # plurality discriminator every rendering/refusal rule gates on.
    plugs: Dict[str, str]
    devices: List[Device] = field(default_factory=list)
    pads: Dict[str, Pad] = field(default_factory=dict)
    straps: Dict[str, Strap] = field(default_factory=dict)
    jumpers: Dict[str, Jumper] = field(default_factory=dict)
    exposes: Dict[str, ExposedSocket] = field(default_factory=dict)
    by_path: Dict[str, object] = field(default_factory=dict)   # dtlib path -> element
    # shield.yml's declared revision axis, and which one THIS Shield
    # represents -- both None for a shield with no revision: block.
    # `revision` is the RESOLVED value (what constructed this Shield's own
    # stems); `revision_requested` is the raw `<name>@<rev>` a reference
    # actually named, kept only for provenance -- nearest-lower match
    # means the two can differ, and every filename/RIG_SHIELD_REVISIONS
    # entry is built from `revision`, never `revision_requested`.
    revisions: Optional["AxisDecl"] = None
    revision: Optional[str] = None
    revision_requested: Optional[str] = None
    src: Optional[SourceRef] = None

    def by_name(self, name: str) -> List[object]:
        """Dotted-reference scope for `wires:` endpoints: pads UNION
        devices UNION straps, by DTS LABEL -- the naming authority every
        rig->shield string reference shares with `config:` and
        `params:` (a shield's own internal references are already
        phandles, i.e. labels, so this makes the rig-typed string and
        the phandle the same identifier). The node name never resolves
        here, labelless or not: internal dict keys stay node-name
        (`self.pads`/`self.straps` are keyed that way for
        `by_path`/`config_element` lookups that never see a rig
        string), this scan is the only rig-facing surface."""
        hits: List[object] = [p for p in self.pads.values() if p.label == name]
        hits += [d for d in self.devices if d.label == name]
        hits += [s for s in self.straps.values() if s.label == name]
        return hits

    def config_element(self, name: str) -> Optional[Union["Strap", "Jumper"]]:
        """A strap or jumper of this shield, by DTS LABEL (rig `config:`
        targets) -- never by node name, which would let two spellings
        (label and name) address the same element."""
        for strap in self.straps.values():
            if strap.label == name:
                return strap
        for jumper in self.jumpers.values():
            if jumper.label == name:
                return jumper
        return None

    def exposed_socket(self, name: str) -> Optional[ExposedSocket]:
        """An exposed socket of this shield, by DTS LABEL (a rig `socket:
        <carrier>.<exposed>` reference's dotted half) -- never by node
        name, which would let two spellings (label and name) address the
        same socket. `self.exposes` stays keyed by node name internally
        (paths and nexus labels are built from `exposed.name`, never this
        lookup) -- only this rig-facing lookup moves to the label."""
        for exposed in self.exposes.values():
            if exposed.label == name:
                return exposed
        return None

    def names(self) -> List[str]:
        """The `by_name` scope's own labels, for a wire-ref diagnostic's
        "valid names" listing -- pads UNION devices UNION straps, sorted,
        matching `by_name`'s own resolution scope exactly."""
        return sorted([p.label for p in self.pads.values()]
                     + [d.label for d in self.devices]
                     + [s.label for s in self.straps.values()])


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
    # slot name -> authored reference, each already resolved through a
    # SocketBinding. A slot mapped to None means the author declared no
    # reference for that slot: the analyzer infers it iff exactly one
    # board socket mates the slot's own connector type. The loader
    # carries the absence through unresolved rather than picking one
    # itself, since it never sees the board. Keyed exactly as
    # `Shield.plugs` is.
    sockets: Dict[str, Optional[str]]
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


# ---------------------------------------------------------------- board side
# The board DT is analyzer input: the analyzer reads the board DT to find
# socket nodes by compatible. These are READ, never authored, facts --
# populated by board_edt.py, never redefined there.


@dataclass
class BusRef:
    label: str          # "i2c1" -- emission target &i2c1
    path: str           # dtlib path, scope identity
    # CS numbering is a fact of THIS bus, not of the socket as a whole (a
    # socket offering two independent SPI buses gives each its own pool):
    # authored override for this bus, else None (the connector type's own
    # default is the caller's fallback, analyzer/cs.py's effective_cs_pool).
    # Never read for an i2c/uart bus.
    cs_pool: Optional[List[int]] = None


@dataclass
class BoardSocket:
    label: str                                  # "nucleo_ard" -- what rig socket: names
    path: str
    type_name: str                               # from compatible "socket,<type>"
    gpio_map: Dict[int, Tuple[str, int, int]]    # position -> (ctrl label, pin, flags)
    buses: Dict[str, BusRef]                     # qualified bus name (kind, or kind-role) present = offered subset
    pwm_map: Dict[int, Tuple[str, int]] = field(default_factory=dict)  # position -> (ctrl label, channel)
    adc_map: Dict[int, Tuple[str, int]] = field(default_factory=dict)  # position -> (ctrl label, channel)
    # This socket's OWN declared #pwm-cells / #io-channel-cells: for a
    # real board socket, board_edt.py's checked read (never the discarded
    # period cell); for a synthesized carrier socket, compose_socket
    # carries the parent's declared count forward once checked equal to
    # it. A carrier never chooses its own count -- it inherits whatever
    # the board it lands on declares.
    pwm_cells: Optional[int] = None
    adc_cells: Optional[int] = None
    # Every socket is referenced through a nexus. Board sockets are real
    # DT nodes (nexus_label=None -> use label, nothing to synthesize); a
    # carrier's re-exported socket has no DT node of its own, so the
    # analyzer/emitter SYNTHESIZE one that chains to its parent's.
    nexus_label: Optional[str] = None
    nexus_rows: Optional[List[Tuple[int, str, int]]] = None  # [(child_pos, parent_nexus_label, parent_pos)]
    # PWM/ADC twins of nexus_rows above, kept SEPARATE (rather than
    # widening nexus_rows with a function tag) because a gpio-less,
    # analog-only exposed socket must still synthesize a nexus node --
    # emitter/overlay.py's skip guard checks all three, never nexus_rows
    # alone.
    pwm_nexus_rows: Optional[List[Tuple[int, str, int]]] = None
    adc_nexus_rows: Optional[List[Tuple[int, str, int]]] = None
    # parent BoardSocket per SLOT of the carrier that synthesized this
    # socket -- empty for a real board socket. A single-plug carrier's
    # composition still produces exactly one entry; a plural carrier's
    # composition carries one entry per slot it declares. Walked by
    # emitter/overlay.py's transitive `visit` for nexus-chain synthesis
    # (a carrier stacked on a carrier).
    parents: Dict[str, "BoardSocket"] = field(default_factory=dict)
    src: Optional[SourceRef] = None


@dataclass
class Board:
    """sockets is canonical: exactly one entry per physical socket, keyed
    by its DEFINING label (node.labels[0]) -- analyzer/sockets.py iterates
    board.sockets.values() to build the "sockets of <board>: ..." census
    inside the phys-socket diagnostic (wording frozen by the
    unmapped-socket golden), so a second key per socket would list every
    aliased socket twice and churn it. aliases carries every ADDITIONAL
    label a socket node declares (e.g. "arduino_r3" alongside a
    board-prefixed "nucleo_ard"), mapped to that socket's defining label --
    resolve() is the only thing that should widen with it; iteration over
    sockets itself must not."""

    name: str
    sockets: Dict[str, BoardSocket] = field(default_factory=dict)   # by defining label
    aliases: Dict[str, str] = field(default_factory=dict)  # additional label -> defining label

    def resolve(self, ref: str) -> Optional[BoardSocket]:
        """The board socket ref names, through the alias index if ref is
        an additional (non-defining) label, else ref itself -- the same
        lookup-else-identity shape loader/binding.py's SocketBinding.get
        uses for abstract-socket names. Returns None when ref names no
        socket of this board at all (a phys-socket finding is the
        caller's job, not this method's). The board and its sockets are
        read-only to this call; nothing is constructed or owned here."""
        return self.sockets.get(self.aliases.get(ref, ref))


@dataclass
class AxisDecl:
    """One declared qualifier axis: a rig's `variants:` (unchanged
    shape), a rig's `revision:` (hwmv2's own shape), or a shield's
    `revisions:` (its OWN pre-hwmv2 shape, permanently -- `loader.axes.
    parse_legacy_revision_decl`'s own docstring has the external reason).
    `values`/`default` are the values a selection may take and the one a
    bare (unqualified) target takes by default, shared by all three;
    `format`/`exact` are a rig's revision axis only -- always None/False
    for a `variants:` decl (no format concept) AND for a shield's own
    revision axis (pinned to its pre-hwmv2 shape, which has no format:/
    exact: keys either).

    boards/sockets carry, per declared VALUE, the board a rig variant
    selects and its abstract-socket map -- populated only for a rig's
    own `variants:` axis when it uses the per-variant-board shape;
    empty for every other axis.

    `format` (one of "letter"/"number"/"major.minor.patch"/"custom") and
    `exact` govern `loader.axes.resolve_axis_selection`'s revision-only
    behaviour (per-format id validation, nearest-lower match, the
    `exact: true` opt-out) when set; `format is None` (a `variants:` decl
    always, a shield's `revisions:` decl always) instead runs plain
    exact-membership resolution, hwmv2 entirely uninvolved."""

    values: list[str]
    default: Optional[str] = None
    boards: dict[str, str] = field(default_factory=dict)
    sockets: dict[str, dict[str, str]] = field(default_factory=dict)
    format: Optional[str] = None
    exact: bool = False


@dataclass
class Rig:
    name: str
    board: str = ""
    instances: list[Instance] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    revisions: Optional[AxisDecl] = None
    variants: Optional[AxisDecl] = None
    # `revision` is the RESOLVED value (nearest-lower match already
    # applied) -- what every fragment filename, context.cmake entry and
    # RIG_REVISION is built from. `revision_requested` is the raw
    # --revision string a target actually asked for, kept only for
    # provenance: None whenever no --revision was given, equal to
    # `revision` whenever the request matched a declared value exactly.
    revision: Optional[str] = None
    revision_requested: Optional[str] = None
    variant: Optional[str] = None
    src: Optional[SourceRef] = None
