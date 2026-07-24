# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's `boards` build module.
#
# btr-shields' cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# `build: cmake-modules: cmake`), so zephyr_default.cmake's `include(boards)`
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/boards.cmake.
#
# TWO jobs now (cmake-alone-rig-entry-brief.md, ratified 2026-07-24, design
# rule 3 amended same day to mutual exclusivity — supersedes an earlier
# canonical-mismatch-check design that briefly lived here and is gone
# without a trace below):
#
#   1. -DRIG rig->board inference + the RIG/BOARD exclusivity guard, BEFORE
#      the real include (this inverts the fork's OLD top-of-file order): RIG
#      and BOARD are MUTUALLY EXCLUSIVE — BOARD is DERIVED data of the rig
#      coordinate, so a user-passed BOARD is a category error even when it
#      happens to match (never compared/canonicalized against anything). If
#      RIG is defined and BOARD is not, ask the resolver
#      (scripts/list_rigs.py's new query mode) for the FULL, verbatim
#      `${RIG}` target string and `set(BOARD ...)` from its answer — the real
#      module below needs BOARD defined before its own
#      `zephyr_check_cache(BOARD REQUIRED)`, which is exactly where a
#      `-DRIG=<name>`-only build (no `-DBOARD`, west absent) used to fail.
#   2. the REAL boards module, unconditionally (rig build or plain -- this
#      fork never dispatches away from it; every build needs BOARD/BOARD_DIR/
#      BOARD_DIRECTORIES resolved the stock way), reached by absolute path
#      (NOT `include(boards)`, which would recurse back into this file via
#      the prepended module path).
#
# After that, this fork (unchanged by this slice) owns the rig-specific
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

include(extensions)

# ---------------------------------------------------------------------------
# Step 1: -DRIG rig->board inference + the RIG/BOARD exclusivity guard
# (cmake-alone-rig-entry-brief.md, design rule 3). One resolver call serves
# both outcomes below (the exclusivity check when BOARD is already given, the
# CACHE assignment when it is not), so -DRIG resolves via list_rigs.py
# exactly once per configure.
if(DEFINED RIG)
  list(TRANSFORM BOARD_ROOT PREPEND "--board-root=" OUTPUT_VARIABLE _rig_broot_args)
  execute_process(
    COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/../scripts/list_rigs.py
      ${_rig_broot_args} --rig=${RIG} --cmakeformat={NAME}\;{DIR}\;{BOARD}
    OUTPUT_VARIABLE _rig_resolve_out
    ERROR_VARIABLE _rig_resolve_err
    RESULT_VARIABLE _rig_resolve_rv)
  if(_rig_resolve_rv)
    message(FATAL_ERROR "rig: -DRIG=${RIG} did not resolve:\n${_rig_resolve_err}")
  endif()
  string(STRIP "${_rig_resolve_out}" _rig_resolve_out)
  # `_RIG_RESOLVED_*` (cmake_parse_arguments' own prefix-derived names) is a
  # DELIBERATE cross-file handoff surface, not internal scratch: this is a
  # plain (non-cache, non-function-scoped) variable, so it survives at
  # FILE/directory scope for the rest of THIS configure -- the dts.cmake
  # fork's step 3 consumes `_RIG_RESOLVED_DIR` to kill the double resolution
  # that used to run list_rigs.py a second time for the exact same `${RIG}`
  # target (see that file).
  cmake_parse_arguments(_RIG_RESOLVED "" "NAME;DIR;BOARD" "" ${_rig_resolve_out})

  # Exclusivity guard (design rule 3, ratified/amended 2026-07-24, FATAL not
  # warned): RIG and BOARD are mutually exclusive, so this does NOT compare
  # the two board strings for agreement (there is no canonicalization
  # anywhere in this file any more) -- it only asks "did the USER pass
  # BOARD", which is not the same question as "is BOARD defined": BOARD is
  # legitimately in the CACHE on a reconfigure of an existing rig build dir,
  # re-supplied by cmake itself from the FIRST configure's own inference
  # below, with no -DBOARD on the command line at all. `RIG_INFERRED_BOARD`
  # (a CACHE INTERNAL marker set alongside BOARD, below) records exactly the
  # value WE inferred, so "BOARD is defined but does not equal the marker" is
  # the precise test for "a user gave BOARD" that survives reconfigures:
  #   - fresh dir, both given: BOARD defined, no marker yet -> FATAL.
  #   - fresh dir, RIG only: BOARD undefined -> infer + set the marker.
  #   - reconfigure, no -DBOARD repeated: BOARD defined FROM THE CACHE, equal
  #     to the marker (both are our own old inferred value) -> passes.
  #   - reconfigure, user repeats the SAME -DBOARD value: indistinguishable
  #     from the cache case above -- accepted residual (not fixed; the
  #     brief's own call).
  #   - reconfigure with a CONFLICTING -DBOARD: BOARD differs from the
  #     marker -> the both-given FATAL below.
  #   - reconfigure with a CHANGED -DRIG: the rig-swap guard just below.

  # Rig-swap guard: the marker also pins the BUILD DIR to the rig's board.
  # zephyr_check_cache(BOARD) makes BOARD immutable per build dir, but RIG
  # is not cache-watched -- without this check, changing -DRIG in an
  # existing dir sails past the exclusivity guard (cached BOARD == marker,
  # both stale) with inference SKIPPED, and the expander then reads the OLD
  # board's dts under the NEW rig's declared board name: phys-socket
  # diagnostics that blame the wrong board (verified live: swapping
  # lotus-buttons into a nucleo-datalogger dir reported the OLD board name
  # missing the NEW rig's socket -- it did), or, for two boards whose
  # socket names coincide, a clean build against the wrong hardware. A swap
  # to another rig on the SAME board stays legal (the marker still matches).
  if(DEFINED RIG_INFERRED_BOARD
     AND NOT "${_RIG_RESOLVED_BOARD}" STREQUAL "${RIG_INFERRED_BOARD}")
    message(FATAL_ERROR
      "rig: -DRIG=${RIG} resolves to board '${_RIG_RESOLVED_BOARD}', but "
      "this build directory was configured for '${RIG_INFERRED_BOARD}'. "
      "Changing to a rig on a different board requires a pristine build "
      "(-p always).")
  endif()

  if(DEFINED BOARD)
    if(NOT DEFINED RIG_INFERRED_BOARD OR NOT "${BOARD}" STREQUAL "${RIG_INFERRED_BOARD}")
      message(FATAL_ERROR
        "rig: -DRIG=${RIG} and -DBOARD=${BOARD} were both given. BOARD is "
        "derived data of the rig coordinate, never a separate one to pass "
        "yourself -- even a MATCHING value is rejected. Drop -DBOARD; the "
        "rig owns the board (it resolves to '${_RIG_RESOLVED_BOARD}' here).")
    endif()
  else()
    set(BOARD "${_RIG_RESOLVED_BOARD}" CACHE STRING
      "Board inferred from -DRIG=${RIG} (rig.yml's board:, no -DBOARD given)")
    set(RIG_INFERRED_BOARD "${_RIG_RESOLVED_BOARD}" CACHE INTERNAL
      "Exclusivity-guard marker: the board value this fork inferred from \
-DRIG=${RIG}. Compared against a later cache-carried BOARD so a \
reconfigure of the SAME build dir is not mistaken for a user-passed \
-DBOARD (cmake-alone-rig-entry-brief.md, design rule 3).")
  endif()

  # Provenance line, mirroring the real module's own "Board:" message that
  # follows just below: WHICH rig file won the -DRIG resolution and what
  # board it projected to -- the two facts a reader of the configure log
  # cannot otherwise reconstruct (BOARD arrives with no visible source).
  message(STATUS "Rig: ${_RIG_RESOLVED_NAME} (${_RIG_RESOLVED_DIR}/rig.yml), board: ${_RIG_RESOLVED_BOARD}")
endif()
# ---------------------------------------------------------------------------

# Step 2: the real boards module, unconditionally (rig build or plain).
include(${ZEPHYR_BASE}/cmake/modules/boards.cmake)

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
# Guarded so this is a total no-op for every OTHER build (plain, non-rig
# boards, and even a PLAIN build of an EXTENDED board's base target):
# resolve the CURRENT target's own `.dts` (the shared
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
