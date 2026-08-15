Rigs that cannot build, on purpose
####################################

Every rig under this directory is expected to FAIL to expand. Each one
exists to prove that one specific physical-layer diagnostic fires —
never to be built, and never a template to copy.

The authority for what each one proves is ``REJECT_CASES`` in
``scripts/rigc/tests/integration/conftest.py``. That table is what pins
the expected verdict below; if the two ever disagree, the table wins —
re-derive from it rather than trusting this README.

======================== =================
rig                      expected verdict
======================== =================
``nucleo_wifi_logger``   ``phys-net``
``quail_dup_th``         ``phys-addr``
``frdm_cs_clash``        ``phys-cs``
``nucleo_mux_clash``     ``phys-addr``
``lotus_pwm_clash``      ``phys-channel``
======================== =================

Two of the five (``nucleo_wifi_logger``, ``quail_dup_th``) are not named
``*_clash`` — the folder groups them by BEHAVIOR (they all reject), not
by a shared name pattern.

This is a move, not a rewrite: each rig keeps its own name, its own
content file, and its frozen goldens under
``scripts/rigc/tests/goldens/<rig-name>/`` exactly as before — only the
directory changed, from ``boards/rigs/<rig-name>/`` to
``boards/rigs/clash/<rig-name>/`` (clash-rigs-folder-brief.md). ``RIG=
<rig-name>`` still resolves each one: a rig's identity comes from its own
``rig.yml``'s ``rig.name``, never from its folder path, and
``scripts/list_rigs.py``'s rig discovery recurses to find rigs regardless
of how deep they sit under ``boards/rigs/``.
