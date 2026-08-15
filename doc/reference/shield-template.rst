Shield template properties
============================

Every ``shield,*`` and ``plug,*`` property a ``.shield`` file may declare —
what it means, whether it may be absent, and what refuses it if it is
misused. The authority is the loader itself,
``scripts/rigc/shields.py``; every example below is copied verbatim (only
re-indented for this page) from a real ``.shield`` file in this tree.

This page is reference, not narrative — :doc:`../tutorials/write-a-shield-template`
teaches the concept; this page looks up the facts. See
:doc:`board-socket` for the ``socket,*`` vocabulary a shield's bus proxies
and exposed sockets resolve against.

.. note::

   Every node a rig, or another part of the same shield, may reference by
   name — a device, a pad, a strap, a jumper, an exposed socket — must
   carry a DTS label. A node with none is refused
   (``lang-shield-label``, naming the node and what it needs) rather than
   silently falling back to its node name: rig-facing references
   (``config:``/``wires:``/``socket:``) resolve by label only.

Declaring the connector
--------------------------

A shield names the :term:`connector type` it plugs, in one of two
mutually exclusive shapes, discriminated by presence or absence of a
template-level ``shield,plugs``.

``shield,plugs`` (single form)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: the template root node (the shield's own node under
   ``shield-templates``).
:Type: string — a connector type name (``"arduino-r3"``, ``"grove"``,
   ``"mikrobus"``, ``"i2c-port"``).
:Required or optional: this is the **single-plug form**. Present at
   template level, it requires a child node literally named ``plug`` (see
   below); absent, the shield must instead declare one or more
   ``shield,plug``-compatible children (the plural form, next entry) — a
   shield with *neither* shape is refused.
:Refuses: ``lang-shield-type`` (names a connector type the registry does
   not know); ``lang-shield-plug`` (neither ``shield,plugs`` nor a
   ``shield,plug`` child is present); ``lang-shield-plurality`` (both a
   template-level ``shield,plugs`` **and** one or more ``shield,plug``
   children are present at once — a shield is one shape or the other,
   never both).

Example — ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   shield,plugs = "arduino-r3";

``compatible = "shield,plug"`` / per-plug ``shield,plugs`` (plural form)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a child node of the template root, one per plug the shield
   declares.
:Type: the child's ``compatible`` is the literal string ``"shield,plug"``;
   its own ``shield,plugs`` property is a string naming *that plug's*
   connector type, exactly like the single form's template-level property.
:Required or optional: this is the **plural form** — a shield with more
   than one plug (two mikroBUS sockets at once, say). The child node's own
   name is the **slot name** other properties reference it by; it may be
   anything except the reserved name ``plug``. Absent entirely (no
   ``shield,plug`` children, no template-level ``shield,plugs``), the
   shield declares no connector at all and is refused.
:Refuses: ``lang-shield-plurality`` (a plug child is named ``plug`` — that
   name is reserved for the single form's own default slot);
   ``lang-shield-type`` (a plug child declares no ``shield,plugs`` of its
   own, or names an unknown connector type).

Example — ``boards/shields/can_span_click/can_span_click.shield`` (two
mikroBUS plugs on one shield):

.. code-block:: devicetree

   left_plug: left {
           compatible = "shield,plug";
           shield,plugs = "mikrobus";
           #gpio-cells = <2>;
   };
   right_plug: right {
           compatible = "shield,plug";
           shield,plugs = "mikrobus";
           #gpio-cells = <2>;
   };

The plug node
~~~~~~~~~~~~~~~

:Where: a child of the template root — named exactly ``plug`` for the
   single form, or the slot's own chosen name for a plural shield's
   ``shield,plug`` child.
:Type: not a property but a node: the :term:`plug` itself, the position
   reference frame every ``gpios``/``pwms``/``io-channels`` property on
   this shield's devices resolves a phandle against. Its own
   ``#gpio-cells`` / ``#pwm-cells`` / ``#io-channel-cells`` declare how
   many cells a position reference through it carries per function;
   absent, the expander assumes the generic Zephyr default for that
   function (2 for gpio, 3 for pwm, 1 for adc —
   ``scripts/rigc/shields.py::_FUNCTION_DEFAULT_CELLS``).
:Required or optional: required for the single form (a shield with
   ``shield,plugs`` but no ``plug`` child node is refused). A plural
   shield's plug nodes are themselves required by construction — they are
   what ``shield,plug`` children are.
:Refuses: ``lang-shield-plug`` (single form names ``shield,plugs`` but has
   no ``plug`` child).

Example — ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   dl_plug: plug { #gpio-cells = <2>; };

Devices
---------

A device is any node under a bus-proxy group (``i2c``/``spi``/``uart``,
named after the connector type's ``plug,bus-proxies``) or a plain,
plug-agnostic group (``gpio``, or any other non-reserved group name). Its
own gpio/pwm/adc references are documented in
:doc:`../tutorials/write-a-shield-template` and
:doc:`../tutorials/add-a-second-socket`; the properties below are this
project's own address, chip-select and parameter vocabulary.

``reg`` / ``shield,addr-from`` (address authority)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a device on an addressable (I2C) bus.
:Type: ``reg`` is the standard devicetree unit address; ``shield,addr-from``
   is a phandle to a config strap (see "Config elements" below) of the
   same shield.
:Required or optional: **exactly one of the two is required** on an I2C
   device — never both, never neither (the address authority rule).
   Authoring ``reg`` means the address is fixed by copper: the device's
   unit-address must equal it. Authoring ``shield,addr-from`` instead
   means the address is **deferred**: which of the strap's domain values
   applies is a rig-time or config-sheet-time decision, not this file's.
   A symbolic unit-address (``sensor@addr_strap`` rather than
   ``sensor@48``) is the readable marker for the deferred case; it is
   linted against the ``shield,addr-from`` target's own name.
:Refuses: ``lang-addr-authority`` (both or neither of ``reg`` /
   ``shield,addr-from`` present on an I2C device); ``lang-addr-from``
   (the phandle does not point at a config strap of this shield);
   ``lang-unit-addr`` (an authored ``reg`` disagrees with the numeric
   unit-address, or a symbolic unit-address is paired with an authored
   ``reg`` instead of ``shield,addr-from``, or does not match its
   resolver's own name — the last one a warning, not an error).

Example — fixed (``reg``), ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   dl_rtc: rtc@68 {
           compatible = "nxp,pcf8523";
           reg = <0x68>;            /* fixed: 1-element domain */
   };

Example — deferred (``shield,addr-from``), ``boards/shields/temp_click/temp_click.shield``:

.. code-block:: text

   tc_sensor: sensor@addr_strap {
           compatible = "vnd,temp1234";
           shield,addr-from = <&tc_addr_strap>;
   };

``shield,cs-position``
~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a device (semantically, one that will end up on a SPI bus).
:Type: ``<u32>`` — one connector-type position index (a ``#define`` from
   the connector type's own header, e.g. ``ARDUINO_HEADER_R3_D10``).
:Required or optional: optional. **Absence means the device's chip-select
   is pool-allocated** — the analyzer draws it from the mated socket's (or
   connector type's default) ``socket,cs-pool`` candidates, in allocation
   order, skipping positions already claimed. Presence means the CS is
   **copper-fixed** at that exact position: allocated outright, never
   drawn from the pool, and checked that the position actually resolves to
   a real SoC pin on the socket the device ends up on.
:Refuses: ``phys-cs`` (the pool is exhausted for a pool-allocated device;
   or a copper-fixed position has no ``gpio-map`` entry on the resolved
   socket, so there is no pin to route it to).

Example — copper-fixed, ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``
(SD-card CS):

.. code-block:: devicetree

   dl_sd: sdhc {
           compatible = "zephyr,sdhc-spi-slot";
           shield,cs-position = <ARDUINO_HEADER_R3_D10>;
           spi-max-frequency = <24000000>;
   };

Contrast ``boards/shields/adafruit_winc1500/adafruit_winc1500.shield``'s
``w_wifi`` device, which authors no ``shield,cs-position`` at all — its own
comment states the consequence directly: "no shield,cs-position -> CS
pool-allocated".

``shield,collect``
~~~~~~~~~~~~~~~~~~~~

:Where: a device.
:Type: string — the ``compatible`` of a shared collection parent
   (``"gpio-leds"``, ``"gpio-keys"``, ...).
:Required or optional: optional. Absence means the device emits as its own
   standalone node. Presence means the device is instead **one entry**
   merged into a board-wide node of that ``compatible`` — so several
   shield instances contribute LEDs or buttons to one shared
   ``gpio-leds``/``gpio-keys`` parent instead of each fighting over its
   own. The string is emitted verbatim as the collection's ``compatible``;
   nothing in the loader restricts it to a fixed set of known collection
   names.
:Refuses: nothing at parse time — an unrecognized collection compatible
   is not diagnosed, it simply produces its own (unusual) collection node.

Example — ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   dl_led1: led-1 { shield,collect = "gpio-leds";
           gpios = <&dl_plug ARDUINO_HEADER_R3_D3 GPIO_ACTIVE_HIGH>; };

``shield,params`` / ``shield,param-includes``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a device; ``shield,param-includes`` is always a sibling of
   ``shield,params`` on the same node.
:Type: both are string arrays. ``shield,params`` lists property names this
   device instance's rig placement may (or must) assign
   (``params: {<device>: {<name>: <value>}}``). ``shield,param-includes``
   lists header paths the assigned value's tokens are allowed to resolve
   against.
:Required or optional: both optional; a device with neither accepts no
   per-instance parameters. Once ``shield,params`` names a property with
   **no default authored** in the template itself (no matching entry
   among the device's other properties), assigning it becomes
   **required** — every rig instantiating this shield must supply it, or
   the per-stage invariant fails. ``shield,param-includes`` is the
   contract for what a *non-literal* assigned value is allowed to name: a
   macro-only header (say, an event-code header) contributes no node or
   property of its own, so the vocabulary it defines cannot be recovered
   from the template's own ``#include``\ s and must be declared here,
   explicitly, on the same device the parameter belongs to.
:Refuses: ``lang-param`` (a rig assigns a property the device does not
   declare in ``shield,params``; a rig names a device the shield does not
   have; a required, no-default parameter is left unassigned by every
   stage); ``lang-dt-include`` (a header in ``shield,param-includes`` is
   missing or fails to preprocess; an assigned non-literal token does not
   resolve against any declared header).

Example — ``boards/shields/grove_btn/grove_btn.shield``:

.. code-block:: devicetree

   gb_key: button {
           shield,collect = "gpio-keys";
           shield,params = "zephyr,code";
           shield,param-includes = "zephyr/dt-bindings/input/input-event-codes.h";
           gpios = <&gb_plug GROVE_SIG0 (GPIO_PULL_DOWN | GPIO_ACTIVE_HIGH)>;
   };

``shield,channel``
~~~~~~~~~~~~~~~~~~~~

:Where: an exposed socket node (see "Carriers and exposed sockets" below)
   whose bus proxy is a **new scope** rather than a pass-through.
:Type: ``<u32>`` — a mux/interposer channel index.
:Required or optional: optional. Absence is the ordinary case for a
   pass-through exposed socket. Presence marks this exposed socket as one
   channel of a multiplexer or similar interposer device on this shield —
   paired with a ``socket,<bus> = <&device>`` reference naming that
   device rather than a plug (see :doc:`board-socket`'s ``socket,<bus>``
   entry for the pass-through-versus-new-scope distinction).
:Refuses: nothing directly — a malformed or missing pairing with the bus
   proxy surfaces as ``lang-exposed`` instead (documented on
   :doc:`board-socket`).

Example — ``boards/shields/i2c_mux/i2c_mux.shield`` (four channels of one
TCA9548A mux, each its own scope):

.. code-block:: devicetree

   ch0: ch0 { compatible = "socket,i2c-port"; socket,i2c = <&mux>; shield,channel = <0>; };
   ch1: ch1 { compatible = "socket,i2c-port"; socket,i2c = <&mux>; shield,channel = <1>; };

Pads
------

A pad is an arity-1 connector: a signal that belongs to a device but is
not itself claimable through any plug — an RTC's square-wave output, say.
Pads live under a ``pads`` group at template level, regardless of
plurality.

``shield,role``
~~~~~~~~~~~~~~~~~

:Where: a pad node, under ``pads``.
:Type: string enum — one of ``"driver"``, ``"listener"``, ``"bidir"``.
:Required or optional: optional. **Absence defaults to** ``"bidir"``. The
   role governs how the net-conflict checker treats signals reaching this
   pad: a driver pad may not share its net with another driver, a listener
   never drives.
:Refuses: ``lang-pad-role`` (any value outside the three-way enum).

Example — ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   dl_sq: sq { shield,role = "driver"; shield,of = <&dl_rtc>; };

``shield,of``
~~~~~~~~~~~~~~~

:Where: a pad node.
:Type: phandle to a device of the same shield.
:Required or optional: optional. Absence means the pad is not associated
   with any particular device of this shield. Presence records which
   device the pad belongs to (its node name, unit-address stripped) —
   this is bookkeeping only; nothing in the loader currently checks the
   phandle resolves to a real device, so a ``shield,of`` naming a
   non-device node is accepted silently rather than refused.
:Refuses: nothing — see the note above.

Example — the same ``dl_sq`` pad, one entry above (RTC square-wave output
belonging to the RTC device), ``boards/shields/adafruit_data_logger/adafruit_data_logger.shield``:

.. code-block:: devicetree

   dl_sq: sq { shield,role = "driver"; shield,of = <&dl_rtc>; };

Config elements
-----------------

A config element is a strap or a jumper: something a rig, or the
allocator, selects a value for. Both live under a ``config`` group at
template level; which one a child node becomes is decided by presence or
absence of ``shield,position-domain``.

``shield,domain`` (config strap)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a config-group child with **no** ``shield,position-domain`` — this
   absence is what makes it a strap rather than a jumper.
:Type: an array of ``(address, strap-state)`` ``<u32>`` pairs —
   ``<addr0 state0>, <addr1 state1>, ...``.
:Required or optional: required to make the node parse as a strap at all;
   a config child authoring neither ``shield,domain`` nor
   ``shield,position-domain`` is not a documented shape (see the note
   below).
:Refuses: nothing named — see the note below.

Example — ``boards/shields/temp_click/temp_click.shield`` (a
strap-selectable I2C address, referenced by ``shield,addr-from`` above):

.. code-block:: devicetree

   tc_addr_strap: addr-strap {
           shield,domain = <0x48 0>, <0x49 1>;  /* (address, strap) */
           shield,sheet-label = "ADDR jumper";
   };

.. note::

   A real defect found while re-deriving this page, reported rather than
   fixed (this is a docs slice): ``scripts/rigc/shields.py::_parse_strap``
   reads ``node.props["shield,domain"]`` unconditionally, with no presence
   check. A config-group child authoring neither
   ``shield,position-domain`` nor ``shield,domain`` is routed to
   ``_parse_strap`` (the "else" branch of the jumper/strap dispatch in
   ``_parse_shield``) and raises a raw ``KeyError`` there instead of a
   ``Diagnostic`` — a crash, not a rejected rig.

``shield,position-domain`` (config jumper)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a config-group child. Its presence, not its value, is the
   discriminator: a config child that has it is a jumper; one that lacks
   it is a strap.
:Type: an array of ``(connector-position index, jumper-state)`` ``<u32>``
   pairs — the position-side twin of a strap's address domain.
:Required or optional: presence itself makes the node a jumper. **On a
   plural shield, declaring one at all is refused outright** — the
   position domain has no plug axis to resolve through, so a jumper only
   makes sense on a single-plug shield.
:Refuses: ``lang-shield-plurality`` (a plural shield declares a routing
   jumper).

Example — ``boards/shields/adafruit_winc1500/adafruit_winc1500.shield``
(IRQ routed to D7 by default, or D2 via a solder jumper):

.. code-block:: devicetree

   w_irq_jmp: irq-jmp {
           #gpio-cells = <1>;      /* supplies the position; flags stay on the signal */
           shield,position-domain = <ARDUINO_HEADER_R3_D7 0>,       /* default */
                                    <ARDUINO_HEADER_R3_D2 1>;       /* alt */
           shield,sheet-label = "IRQ select (SJ2)";
   };

``shield,sheet-label``
~~~~~~~~~~~~~~~~~~~~~~~~~

:Where: a strap or jumper node.
:Type: string.
:Required or optional: optional. **Absence means the emitted**
   :term:`config sheet` **carries an empty label** for that element
   (``scripts/rigc/shields.py::_sheet_label`` returns ``""`` when the
   property is absent) — the element still functions, but the human-facing
   wiring instructions have nothing readable to call it. Presence supplies
   that label (a silkscreen name, typically).
:Refuses: nothing.

Example — the same ``w_irq_jmp`` node above,
``boards/shields/adafruit_winc1500/adafruit_winc1500.shield``:
``shield,sheet-label = "IRQ select (SJ2)";``.

Carriers and exposed sockets
-------------------------------

A shield with no devices of its own that instead re-exports one or more
sockets — an I2C multiplexer, a click-adapter — is a :term:`carrier`. Its
exposed sockets are ordinary nodes with a ``compatible = "socket,<type>"``,
authored *inside* the ``.shield`` file: they carry the identical
vocabulary a real board socket does (``gpio-map``, ``socket,<bus>``,
``socket,cs-pool``, ...), documented in full on :doc:`board-socket`, plus
this shield-only ``shield,channel`` above. A plural carrier's exposed
socket may compose its rows from *any* of the carrier's own plugs, exactly
as a device's own cross-plug references do.

Example — pass-through, ``boards/shields/arduino_uno_click/arduino_uno_click.shield``
(an Arduino R3 shield re-exporting two mikroBUS sockets, SPI/I2C passed
through the carrier's own plug):

.. code-block:: devicetree

   mb1: mb1 {
           compatible = "socket,mikrobus";
           #gpio-cells = <2>;
           gpio-map = <MIKROBUS_CS  0 &auc_plug ARDUINO_HEADER_R3_D10 0>,
                      <MIKROBUS_RST 0 &auc_plug ARDUINO_HEADER_R3_D6  0>,
                      <MIKROBUS_INT 0 &auc_plug ARDUINO_HEADER_R3_D2  0>;
           socket,spi = <&auc_plug>;
           socket,i2c = <&auc_plug>;
   };

Example — new scope, ``boards/shields/i2c_mux/i2c_mux.shield`` (a TCA9548A
mux; each channel is its own scope rooted on the mux device, so a fixed
I2C address may repeat behind different channels) — see ``shield,channel``
above for the same snippet.
