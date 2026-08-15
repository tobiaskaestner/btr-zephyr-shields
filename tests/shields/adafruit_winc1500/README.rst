Adafruit WINC1500 Shield Testing
#################################

The shield plugs an ``arduino-r3`` socket and carries one SPI WiFi
device with a REQUIRED routing-jumper selection (``config:``): its
IRQ line has a ``{D7, D2}`` position domain and no default the
allocator may pick (non-CS positions are never auto-allocated), so a
rig must choose. This is the config-element promotion grammar's own
precedent (promotion-config-brief.md): ``RIG=adafruit_winc1500:
config.w_irq_jmp=D2``.

``D2`` matches ``boards/rigs/nucleo_wifi_logger_ok/
nucleo_wifi_logger_ok.yml``'s own choice; ``D7`` (the domain's default
position) would ALSO be a legal selection on this platform, since
nothing else here claims D7 -- ``D2`` is used so this promoted rig
stays comparable to the checked-in one, which is the point of the
singleton identity law.

``nucleo_f401re/stm32f401xe/rig`` offers exactly one ``arduino-r3``
socket with both ``socket,spi`` and a ``socket,cs-pool`` (the shield's
own CS is pool-allocated, not copper-fixed), so no explicit ``socket=``
is needed -- unique-by-type inference resolves it.
