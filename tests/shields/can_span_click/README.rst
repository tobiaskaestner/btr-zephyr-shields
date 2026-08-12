CAN Span Click Shield Testing
##############################

The shield plugs TWO mikroBUS sockets at once (multi-plug-shield-brief.md):
``can0`` (``microchip,mcp2515``) on the LEFT plug's SPI bus with its INT
line copper on the RIGHT plug, and ``log_flash`` (``jedec,spi-nor``)
entirely on the RIGHT plug.

mikroe_quail offers FOUR mikrobus sockets, so per-slot inference is
ambiguous for BOTH slots (multi-plug-promotion-brief.md Sec 3) -- the
promotion names both explicitly via the slot-optioned grammar,
``socket.left=``/``socket.right=``. ``quail_sock2``/``quail_sock3`` are
the same pair the corpus rig ``quail_can_span`` and this shield's own
build-marked integration tests already pin.

``CONFIG_CAN``/``CAN_MCP2515`` are deliberately left unselected -- see
prj.conf's own comment for the probe this suite's Kconfig level rests on.
