Grove LED Shield Testing
#########################

The shield plugs a ``grove`` socket and carries one ``gpio-leds`` entry --
pure digital GPIO, no bus and no required param. Targets the same real
upstream board as ``tests/shields/grove_btn/``, ``m5stack_nanoc6``; see
that suite's README for the board extension itself and the Kconfig
quirk it needed.

Two other grove shields in the corpus, ``grove_light`` (ADC) and
``grove_servo`` (PWM), do NOT get suites here even though they mate this
same socket type: this board's ``grove_socket.dtsi`` is digital-only,
matching the real upstream ``grove_connectors.dtsi`` it wraps (neither
declares a ``pwm-map``/``io-channel-map``). Both fail correctly and
cleanly today -- ``error[phys-function]: '<device>: io-channels|pwms'
uses position SIG0`` -- rather than silently producing wrong output.

Adding either needs a real, verified hardware fact this session did not
establish: ESP32-C6's ADC channels are fixed to specific GPIOs (not
every pin is ADC-capable), and no board or sample anywhere in this
zephyr tree wires up ``adc0`` (present but ``status = "disabled"``) to
cross-reference a channel number against. PWM (``ledc0``) is more
flexible -- ESP32's GPIO matrix can generally route a LEDC channel to
almost any pin -- but still wants the same kind of verification before
declaring it. Guessing at either is worse than leaving the gap open and
named.
