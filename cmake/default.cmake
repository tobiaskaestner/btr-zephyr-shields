# Auto-included by Zephyr's module machinery because btr-shields' module.yml
# declares `build: cmake-modules: cmake` (see the zephyr-rigs commit that added
# that key). It runs inside zephyr_module — BEFORE boards/dts/kconfig/soc — for
# EVERY build in the workspace, which is exactly early enough to feed a
# generated devicetree overlay into `dts`.
#
# This is the rigs seam. When -DRIG=<name> is set it expands the rig into an
# overlay (+ Kconfig fragment, once emitted) and wires it in via
# EXTRA_DTC_OVERLAY_FILE / OVERLAY_CONFIG. When -DRIG is unset it is a no-op, so
# ordinary builds (and the legacy --shield path) are unaffected.
#
# Replaces the retired per-app btr-shields/samples/rigs/scenario-1/
# ZephyrAppConfig.cmake: module-global, not tied to one application.

if(DEFINED RIG)
  # rig_expand.cmake sits next to this file; btr-shields/cmake is already on
  # CMAKE_MODULE_PATH (prepended by the cmake-modules handler before we run).
  include(rig_expand)
  rig_expand("${RIG}")
endif()
