I2C Mux Shield Testing
######################

The shield plugs an ``arduino-r3`` socket and offers four ``socket,i2c-port``
channels rooted in its own TCA9548A rather than in the parent bus. Promoted
on its own it carries the mux and no downstream device.
