# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's `shields` build module.
#
# btr-shields' cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# `build: cmake-modules: cmake`), so zephyr_default.cmake's `include(shields)`
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/shields.cmake.
#
# We fork rather than patch, because the rig shield model (shield folders whose
# `.overlay` is replaced by a `.shield` template, instantiated by a rig instead
# of selected via -DSHIELD) does not fit the stock shield-processing flow. This
# gives us design space in rig.cmake without disturbing normal builds:
#
#   - rig build (-DRIG set): run our rig.cmake (a clone of shields.cmake that we
#     adapt to the rig model — discovery via shield.yml marker, `.shield`
#     expansion, our Kconfig facts). rig.cmake starts byte-identical to the
#     upstream module so it can be diffed to show exactly what we change.
#   - otherwise: defer to the ORIGINAL shields.cmake unchanged, so `--shield`
#     and no-shield builds behave exactly as upstream.
#
# NOTE: reach the original by absolute path (NOT `include(shields)`, which would
# recurse back into this file via the prepended module path).

if(DEFINED RIG)
  include(${CMAKE_CURRENT_LIST_DIR}/rig.cmake)
else()
  include(${ZEPHYR_BASE}/cmake/modules/shields.cmake)
endif()
