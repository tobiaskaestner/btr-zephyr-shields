Grove Button Shield Testing
############################

The shield plugs a ``grove`` socket and carries one ``gpio-keys`` button
whose ``zephyr,code`` is required with no authored default
(``shield,params``), satisfied via the promotion CLI grammar's
``<device>.<prop>=<value>`` form (Sec 9.6 part 2) --
``gb_key.zephyr,code=INPUT_KEY_0``.

The one real corpus rig using this shield, ``lotus_buttons``, targets
``seeeduino_lotus``, whose base board lives in the ``bridle`` Zephyr
module -- not a west-manifest project in this workspace, so not a
twister platform here (see ``tests/shields/pilot_alt_button/README.rst``).

This suite targets a DIFFERENT, real upstream board instead:
``m5stack_nanoc6`` ships a genuine ``grove-header`` devicetree node
(``boards/m5stack/m5stack_nanoc6/grove_connectors.dtsi``, two digital
GPIO positions on ``&gpio0``) as part of the standard zephyr tree --
found by scanning ``boards/`` for real ``grove`` connector content, not
authored for this test. ``boards/extend/m5stack/m5stack_nanoc6/`` wraps
those SAME pin references under this project's typed ``socket,grove``
contract (``grove_socket.dtsi``), the identical pattern already used for
``seeeduino_lotus``/``frdm_k64f``/``nucleo_f401re``/``mikroe_quail``.

**One real Kconfig quirk, fixed entirely within the extension's own
files, no upstream changes:** the base board's own
``Kconfig.m5stack_nanoc6`` selects ``SOC_ESP32C6_HPCORE`` (and
``boards/m5stack/m5stack_nanoc6/Kconfig`` separately defaults
``HEAP_MEM_POOL_ADD_SIZE_BOARD``) conditionally on the base board's OWN
qualifier-exact symbol, ``BOARD_M5STACK_NANOC6_ESP32C6_HPCORE`` --
which the ``rig`` variant's own, separately-generated
``BOARD_M5STACK_NANOC6_ESP32C6_HPCORE_RIG`` symbol never satisfies.
Without both, the espressif HAL's HPCORE-only sources (systimer, RTC
GPIO, the interrupt controller wrapper) never enter the build, and
every driver that calls into them fails to link -- confirmed by
comparing a plain (non-rig) build's ``.config`` against the rig
variant's. ``boards/extend/m5stack/m5stack_nanoc6/Kconfig.defconfig``
restates both defaults under the rig variant's own symbol.

This is the FIRST rig board extension in this project built on a board
with a multi-level qualifier (SoC + cpucluster, ``esp32c6/hpcore``) --
every prior extension's base board has a single-level qualifier, where
this exact-match pattern cannot arise. Worth checking again if any
FUTURE extension targets another multi-cpucluster SoC (ESP32's other
procpu/appcpu split, RA-series dual-core parts, etc.).
