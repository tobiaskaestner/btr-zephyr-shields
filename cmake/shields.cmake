# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's `shields` build module.
#
# btr-shields' cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# `build: cmake-modules: cmake`), so zephyr_default.cmake's `include(shields)`
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/shields.cmake.
#
# A rig build has NO shields phase: shield selection is a consequence of rig
# expansion, not a standalone phase driven by -DSHIELD. The dts.cmake fork's
# rig block (run later in the module chain, shields@11 < dts@17) resolves
# RIG_SHIELDS from the expander's own output and sets every variable this
# module would otherwise own (shield_conf_files/SHIELD_AS_LIST/SHIELD_DIRS)
# directly. So this fork is pure dispatch:
#
#   - rig build (-DRIG set): early-exit, nothing else. (This is the draft
#     upstream patch for shields.cmake: "rig builds have no shields phase.")
#   - otherwise: defer to the ORIGINAL shields.cmake unchanged, so `--shield`
#     and no-shield builds behave exactly as upstream.
#
# NOTE: reach the original by absolute path (NOT `include(shields)`, which
# would recurse back into this file via the prepended module path).

include_guard(GLOBAL)

if(NOT DEFINED RIG)
  include(${ZEPHYR_BASE}/cmake/modules/shields.cmake)
endif()
