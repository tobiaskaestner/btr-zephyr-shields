The rig corpus
################

**Every rig in this directory is part of the frozen test corpus.** Each
one exists to hold a specific behaviour still under
``scripts/rigc/tests/goldens/<rig-name>/`` — an emitted overlay, a
config sheet, a resolved ``zephyr.dts``, compared byte-for-byte or
structurally on every gate run. They are real, buildable topologies, but
they were chosen to pin coverage, not to be a curated example set.

Read them accordingly: a rig here is a *witness*, and its comment header
usually says what it witnesses.

Where to start
==============

If you are looking for the shape of a rig rather than for coverage,
these four are the ones worth reading, in order:

``ard_datalogger``
   The simplest shape there is — one shield, one socket, no
   configuration. Also the corpus's only rig genuinely built on two
   boards, which is why its content names the conventional
   ``arduino_r3`` alias rather than a board-specific label.

``nucleo_wifi_logger_ok``
   Two shields stacked on one Arduino header, with the interesting part
   visible: a ``config:`` block moving a routing jumper off a pin the
   other shield already claims, and a chip-select the allocator places
   for you.

``nucleo_mux_farm``
   A carrier — an I²C mux re-exporting four typed sockets — with
   instances plugged into the sockets it exposes.

``nucleo_grove_farm``
   The same idea one level deeper: a Grove base carrier on the Arduino
   header, with I²C, digital, ADC and PWM shields on the sockets *it*
   exposes. The most complete single example in the tree.

Subdirectories
==============

``clash/``
   Rigs that are expected to FAIL to expand, each proving one
   physical-layer diagnostic. Never build these; never copy one as a
   template. See that directory's own README.

Rig discovery does not care about the layout: a rig's identity comes
from its own ``rig.yml``'s ``rig.name``, never from its folder path, and
``scripts/list_rigs.py`` recurses to find rigs however deep they sit. A
directory containing ``rig.yml`` IS a rig and is not descended into; any
other directory is a grouping folder.

What is NOT here
================

**A rig is not the way to build a single shield.** That is promotion:

.. code-block:: console

   $ west build-rig --rig adafruit_data_logger -b nucleo_f401re/stm32f401xe/rig <app>
   $ west build-rig --rig 'temp_click:socket=quail_sock1' -b mikroe_quail/stm32f427xx/rig <app>
   $ west build-rig --rig 'adafruit_winc1500:config.w_irq_jmp=D2' -b nucleo_f401re/stm32f401xe/rig <app>

No rig file is involved — the shield is desugared into a one-instance
rig in memory. ``west rigs --explain <target>`` prints exactly what that
desugaring produces, and ``west rigs --boards-for <target>`` reports
which boards it resolves against. The suites under ``tests/shields/``
are that path in CI, one per promotable shield.

So a rig earns its place here only when it holds something promotion
cannot: several instances interacting, a carrier, an axis (variants or
revisions), or a state that needs its bytes frozen rather than merely
built.
