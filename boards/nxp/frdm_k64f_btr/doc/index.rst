.. zephyr:board:: frdm_k64f_btr

Overview
********
The Freedom-K64F is an ultra-low-cost development platform for Kinetis K64,
K63, and K24 MCUs, form-factor compatible with the Arduino R3 pin layout.

This is the **btr-shields clone** (board id ``frdm_k64f_btr``) of the
upstream ``frdm_k64f`` board (zephyr), adding a typed
``socket,arduino-r3`` node (rigs Convention 4) alongside the untouched
legacy ``arduino_header`` / ``arduino_i2c`` / ``arduino_spi`` /
``arduino_serial`` nodes.

Hardware
********
See the upstream ``frdm_k64f`` board documentation for full hardware
details. Nothing in the underlying SoC/board hardware is changed by this
clone.

Supported Features
===================

.. zephyr:board-supported-hw::

Connections and IOs
====================

The Arduino R3 header is exposed both as the legacy ``arduino_header``
connector node (upstream shape, unmodified) and as a typed
``socket,arduino-r3`` node (``frdm_ard``) for the rigs expander — same
pins, same controllers (``&i2c0`` / ``&spi0`` / ``&uart3``).

Programming and Debugging
**************************

.. zephyr:board-supported-runners::

Applications for the ``frdm_k64f_btr`` board can be built and flashed in
the usual way (see :ref:`build_an_application` and :ref:`application_run`
for more details).

.. zephyr-app-commands::
   :zephyr-app: samples/hello_world
   :board: frdm_k64f_btr
   :goals: build flash

References
**********

.. target-notes::
