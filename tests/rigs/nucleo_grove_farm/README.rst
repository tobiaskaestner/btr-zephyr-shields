Grove Base Carrier Nested Promotion Testing
############################################

The first suite under ``tests/rigs/`` (grove-carriers-brief.md Sec 7) --
every earlier suite in the tree (``tests/shields/*``) exercises
``RIG=<shield>[:opts]``, a single shield PROMOTED to a rig on the fly. This
one instead builds a PERSISTED, checked-in rig
(``boards/rigs/nucleo_grove_farm``) via ``RIG=nucleo_grove_farm``, because
the topology under test needs more than one instance: a
``seeed_grove_base_v2`` carrier on the Nucleo/FRDM Arduino header
re-exports typed Grove sockets, and one I2C shield
(``grove_sens_bme280``) plus one digital shield (``grove_btn``) plug
straight into two of THOSE exposed sockets -- the first shield-on-a-
carrier-exposed-socket build to reach twister (every earlier carrier
corpus rig, e.g. ``nucleo_mux_farm``, is exercised only through the
expander's own emitted/resolved goldens, never a real toolchain build).

``platform_allow`` lists both boards this carrier can mate on
(``arduino_r3``, the conventional alias both carry --
grove-carriers-brief.md Sec 5): the rig's own content names no board at
all, so either builds it unmodified.

``prj.conf`` carries only ``CONFIG_ZTEST=y`` -- the subsystem umbrellas
(``CONFIG_SENSOR``, ``CONFIG_INPUT``, ``CONFIG_GPIO``) this rig's two real
shields need come from the persisted rig's own
``boards/rigs/nucleo_grove_farm/nucleo_grove_farm_defconfig`` (Convention
7: no per-instance driver config in Kconfig, but a subsystem umbrella is
the rig's own job), applied automatically by cmake for any build naming
this rig -- unlike a promoted single shield, which carries no rig
directory of its own to hold one, hence why every other suite in
``tests/shields/`` sets these directly in its own ``prj.conf``.
