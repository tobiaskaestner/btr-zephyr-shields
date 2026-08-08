Temp&Hum Click Shield Testing
#############################

The shield plugs a ``mikrobus`` socket and carries one
``st,hts221`` temperature/humidity sensor on the socket's I2C.

mikroe_quail offers FOUR mikrobus sockets, so the promotion has to
name one -- socket-less inference is right to refuse an ambiguous
board. ``quail_sock1`` is an arbitrary choice among four equals.

Worth knowing before reading the emitted overlay: this shield carries no
GPIO at all, so the chosen socket does not APPEAR in ``rig-gen.overlay``
-- the device lands on the shared ``&i2c1`` and nothing references the
socket's own label. Naming a socket is still required (resolution has to
be unambiguous), it is simply not observable in the output here, unlike
``temp_click``, whose ``int-gpios`` renders ``&quail_sock1`` directly.
