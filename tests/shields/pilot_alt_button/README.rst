Pilot Alt Button Shield Testing
################################

The shield plugs an ``arduino-r3`` socket and carries one ``gpio-keys``
button whose ``zephyr,code`` is required with no authored default
(``shield,params``). Both target boards offer exactly one ``arduino-r3``
socket, so promotion needs no explicit ``socket=``.

Satisfying the required parameter is only possible via the promotion CLI
grammar's ``<device>.<prop>=<value>`` form (Sec 9.6 part 2) --
``pab_key.zephyr,code=INPUT_KEY_0`` -- a bare token, not the integer
literal the one real corpus usage (``pilot_variants_variant_c``) assigns,
so this suite exercises the shield's own ``shield,param-includes``
resolution rather than ``is_int_literal``'s short-circuit.

``grove_btn`` has the identical param shape and was unblocked by the same
grammar, but has no suite here: its only real socket, ``seeeduino_lotus``,
lives in the ``bridle`` Zephyr module, which this workspace's ``west.yml``
does not import -- not a twister platform in this workspace at all,
independent of and unaffected by Sec 9.6.
