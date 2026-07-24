# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's `boards` build module.
#
# btr-shields' cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# `build: cmake-modules: cmake`), so zephyr_default.cmake's `include(boards)`
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/boards.cmake.
#
# Runs the REAL boards module first, unconditionally (rig build or plain —
# this fork never dispatches on -DRIG; every build needs BOARD/BOARD_DIR/
# BOARD_DIRECTORIES resolved the stock way), reached by absolute path (NOT
# `include(boards)`, which would recurse back into this file via the
# prepended module path). After that, this fork owns the rig-specific
# board-DTS resolution mechanics that later forks (shields, dts) need:
#
#   - _rig_resolve_board_dts(): resolve the current board target's own
#     `.dts` file, including hwmv2 board-EXTENSION variants. Used by this
#     file's own -isystem guard below, and by the dts.cmake fork's pass-1
#     recipe (its only two callers) — defined here, once, so the naming
#     logic is never duplicated between them.
#   - the hwmv2 board-EXTENSION cpp include-path fix (DTS_EXTRA_CPPFLAGS),
#     which runs for EVERY build, rig or plain, exactly as before this move.

include_guard(GLOBAL)

include(${ZEPHYR_BASE}/cmake/modules/boards.cmake)

include(extensions)

# ---------------------------------------------------------------------------
# _rig_resolve_board_dts(<out-var>): resolve the CURRENT board target's own
# `.dts` file. Defined here because BOTH this fork's own use just below (the
# plain-build -isystem guard) AND the dts.cmake fork (its pass-1 recipe)
# need it; a single definition means the two never duplicate zephyr's own
# board-target naming logic between them.
#
# Data-driven, zero board names, zero hardcoded paths: consumes only THIS
# module's own outputs (BOARD/BOARD_QUALIFIERS/BOARD_DIRECTORIES, already
# resolved by the real boards.cmake include above) and `zephyr_build_string()`
# (cmake/modules/extensions.cmake) -- the SAME helper `dts.cmake:
# dts_configuration_files()` calls to build the `<board>_<qualifiers>`
# basename it searches `BOARD_DIRECTORIES` for (full form preferred, falling
# back to the SHORT single-SoC form that drops the leading SoC qualifier
# segment). Only the trivial "does this candidate file exist in this dir"
# existence-check loop is repeated here (dts.cmake keeps that loop private)
# -- never the naming RULE itself. For a plain, unextended board
# (BOARD_DIRECTORIES has one entry) this resolves to exactly what dts.cmake
# itself would pick; for an hwmv2 board EXTENSION variant, BOARD_DIRECTORIES
# also carries the extension dir(s) `list_boards.py`'s own
# `extend_v2_boards()` registered against the base board, so the variant's
# own `<board>_<qualifiers>_<variant>.dts` is found there -- wherever that
# directory actually lives (a board_root of ANY Zephyr module, not just
# $ZEPHYR_BASE).
#
# Sets <out-var>, in the caller's scope, to the resolved absolute path, or
# to an empty string if no candidate exists in any `BOARD_DIRECTORIES`
# entry. Mirrors dts.cmake's own per-directory precedence (later
# directories in BOARD_DIRECTORIES win on a match, full form preferred over
# short within one directory) but does NOT reproduce its multi-SoC conflict
# diagnostics -- out of scope for a helper only ever used against
# single-SoC boards/extensions so far; callers needing a hard failure raise
# their own diagnostic.
function(_rig_resolve_board_dts out_var)
  zephyr_build_string(_rbd_board_string SHORT _rbd_board_string_short
    BOARD ${BOARD} BOARD_QUALIFIERS "${BOARD_QUALIFIERS}"
  )

  set(_rbd_board_dts)
  foreach(_rbd_dir ${BOARD_DIRECTORIES})
    if(EXISTS "${_rbd_dir}/${_rbd_board_string}.dts")
      set(_rbd_board_dts "${_rbd_dir}/${_rbd_board_string}.dts")
    elseif(EXISTS "${_rbd_dir}/${_rbd_board_string_short}.dts")
      set(_rbd_board_dts "${_rbd_dir}/${_rbd_board_string_short}.dts")
    endif()
  endforeach()

  set(${out_var} "${_rbd_board_dts}" PARENT_SCOPE)
endfunction()
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# hwmv2 board-EXTENSION cpp include-path fix (data-driven -- consumes only
# this module's own outputs, zero board names/paths hardcoded here).
#
# An extension variant's own `.dts` (board.yml `extend:`, e.g.
# boards/extend/st/nucleo_f401re/nucleo_f401re_stm32f401xe_rig.dts) wants to
# `#include` the REAL base board's own top-level `.dts` -- the whole point
# of an extension over a clone: inherit upstream content instead of
# duplicating it. But the C-preprocessor include search path pre_dt.cmake
# builds only ever adds FIXED SUBPATHS of each DTS_ROOT entry (`include`,
# `dts`, ...) -- never a board directory's own root -- so a bare
# `#include "nucleo_f401re.dts"` from a SIBLING directory (the extension's
# own dir) cannot resolve via the ordinary search path (verified
# empirically: cmake configure fails "No such file or directory").
#
# Fix: append every OTHER `BOARD_DIRECTORIES` entry (at minimum the base
# board's own dir, `directories[0]`) as an extra `-isystem` to
# DTS_EXTRA_CPPFLAGS -- an EXISTING, documented dts.cmake extension point
# ("DTS_EXTRA_CPPFLAGS: extra command line options ... to the C
# preprocessor", cmake/modules/dts.cmake). This module (the fork point) runs
# for EVERY build -- rig or plain -- and runs after the real boards.cmake
# include above (BOARD_DIRECTORIES already resolved) but before dts.cmake
# (still in time for DTS_EXTRA_CPPFLAGS to be picked up), so a genuinely
# plain `-b nucleo_f401re/stm32f401xe/rig` build is covered too, not just a
# `-DRIG` one.
#
# Guarded so this is a total no-op for every OTHER build (plain boards, our
# other still-cloned boards, and even a PLAIN build of an EXTENDED board's
# base target): resolve the CURRENT target's own `.dts` (the shared
# `_rig_resolve_board_dts` helper above) and act only if it lives in a
# directory OTHER than `BOARD_DIRECTORIES`'s first entry (the base board's
# own directory -- always directories[0], per list_boards.py's
# `extend_v2_boards()`). A plain `nucleo_f401re` build's own BOARD_DIRECTORIES
# already lists the extension dir too (list_boards.py registers the
# extension against the base regardless of which qualifier/variant is
# ultimately selected) -- the length check alone would NOT distinguish it,
# hence keying on where the RESOLVED dts actually lives, not on list length.
list(LENGTH BOARD_DIRECTORIES _rig_boards_dir_count)
if(_rig_boards_dir_count GREATER 1)
  _rig_resolve_board_dts(_rig_boards_board_dts)
  if(_rig_boards_board_dts)
    get_filename_component(_rig_boards_dts_dir "${_rig_boards_board_dts}" DIRECTORY)
    list(GET BOARD_DIRECTORIES 0 _rig_boards_base_dir)
    file(REAL_PATH "${_rig_boards_dts_dir}" _rig_boards_dts_dir_real)
    file(REAL_PATH "${_rig_boards_base_dir}" _rig_boards_base_dir_real)
    if(NOT _rig_boards_dts_dir_real STREQUAL _rig_boards_base_dir_real)
      foreach(_rig_boards_dir ${BOARD_DIRECTORIES})
        file(REAL_PATH "${_rig_boards_dir}" _rig_boards_dir_real)
        if(NOT _rig_boards_dir_real STREQUAL _rig_boards_dts_dir_real)
          list(APPEND DTS_EXTRA_CPPFLAGS "-isystem" "${_rig_boards_dir}")
        endif()
      endforeach()
    endif()
  endif()
endif()
# ---------------------------------------------------------------------------
