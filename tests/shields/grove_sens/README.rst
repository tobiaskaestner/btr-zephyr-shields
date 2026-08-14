Grove Environmental Sensors Shield Testing
###########################################

The shield plugs a ``grove`` socket and carries one I2C environmental
sensor behind the Grove socket's I2C bus proxy
(``dts/bindings/connectors/grove.yaml``'s ``socket,i2c``, first
exercised by this shield). No ``:socket=`` is needed -- the NanoC6
offers exactly one Grove socket, so promotion is unambiguous (contrast
``temp_click`` on quail, which needs ``:socket=quail_sock1`` because
quail offers four mikroBUS).

This is the first suite in the tree backed by a REAL sensor driver
(Zephyr's ``bme280``/``dps310``) rather than a ``vnd,*`` test binding or
a driverless GPIO shape -- ``RIG=grove_sens_bme280`` is picked as the
representative of the three (``grove_sens_bmp280``/``grove_sens_dps310``
share the identical plug/strap shape; only the compatible and the
address domain differ, see ``boards/shields/grove_sens/``).

``prj.conf`` needs ``CONFIG_SENSOR=y`` on top of the ``temp_click``
suite's own ``CONFIG_I2C=y``/``CONFIG_ZTEST=y`` shape: the BME280
driver's own Kconfig (``drivers/sensor/bosch/bme280/Kconfig``) sits
inside ``drivers/sensor/Kconfig``'s ``if SENSOR`` block, so the SENSOR
umbrella must be turned on explicitly -- it is not derived from any one
devicetree compatible the way ``CONFIG_I2C`` is
(``select I2C if $(dt_compat_on_bus,$(DT_COMPAT_BOSCH_BME280),i2c)``).
Confirmed by building (``west twister ... --build-only``), not by
reading the Kconfig alone, per this suite's own brief.
