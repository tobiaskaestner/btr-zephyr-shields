# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's boards build module.
#
# cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# build: cmake-modules: cmake), so zephyr_default.cmake's include(boards)
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/boards.cmake.
#
#
#   1. -DRIG rig->board resolution + the rig-swap guard: BOARD is an
#      INDEPENDENT coordinate with a per-rig DEFAULT (board-coordinate-
#      s1-brief.md) — a user-passed -DBOARD wins unconditionally; absent,
#      it is inferred from the rig exactly as before this existed. If RIG
#      is defined and BOARD is not, ask the resolver (scripts/list_rigs.py's
#      query mode) for the FULL, verbatim ${RIG} target string and
#      set(BOARD ...) from its answer — the real module below needs BOARD
#      defined before its own zephyr_check_cache(BOARD REQUIRED). A rig
#      declaring no board at all with no -DBOARD given has nothing to
#      fall back to and is a configure-time FATAL_ERROR.
#   2. the REAL boards module, unconditionally (rig build or plain), reached
#      by absolute path — include(boards) would recurse back into this file
#      via the prepended module path.
#
# After that, this module owns the rig-specific
# board-DTS resolution mechanics that gets consumed later (shields, dts):
#
#   - _rig_resolve_board_dts(): resolve the current board target's own
#     .dts file, including hwmv2 board-EXTENSION variants.
#
#   - the hwmv2 board-EXTENSION cpp include-path fix (DTS_EXTRA_CPPFLAGS),
#     which runs for EVERY build, rig or plain.

include_guard(GLOBAL)

include(extensions)

# ---------------------------------------------------------------------------
# Step 1: -DRIG rig->board resolution + the rig-swap guard. One resolver
# call serves both outcomes below (the rig-swap comparison, the CACHE
# assignment when BOARD is not given), so -DRIG resolves via list_rigs.py
# exactly once per configure.
if(DEFINED RIG)
  list(TRANSFORM BOARD_ROOT PREPEND "--board-root=" OUTPUT_VARIABLE _rig_broot_args)
  execute_process(
    COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/../scripts/list_rigs.py
      ${_rig_broot_args} --rig=${RIG}
      --cmakeformat={NAME}\;{DIR}\;{BOARD}\;{REVISION}\;{VARIANT}
    OUTPUT_VARIABLE _rig_resolve_out
    ERROR_VARIABLE _rig_resolve_err
    RESULT_VARIABLE _rig_resolve_rv)
  if(_rig_resolve_rv)
    message(FATAL_ERROR "Rig: -DRIG=${RIG} did not resolve:\n${_rig_resolve_err}")
  endif()
  string(STRIP "${_rig_resolve_out}" _rig_resolve_out)

  # REVISION/VARIANT are the SELECTED qualifier axes (rig-variants-
  # revisions.md V1a) -- list_rigs.py already validated them against the
  # rig's own declarations and applied defaults for a bare target, so what
  # comes back here is either NOTFOUND (axis undeclared / not selected) or
  # the concrete string every fragment filename downstream is built from.
  cmake_parse_arguments(_RIG_RESOLVED "" "NAME;DIR;BOARD;REVISION;VARIANT" "" ${_rig_resolve_out})
  if(_RIG_RESOLVED_REVISION STREQUAL "NOTFOUND")
    set(_RIG_RESOLVED_REVISION "")
  endif()
  if(_RIG_RESOLVED_VARIANT STREQUAL "NOTFOUND")
    set(_RIG_RESOLVED_VARIANT "")
  endif()
  # BOARD is the one RESOLVED key that can legitimately come back NOTFOUND
  # now (board-coordinate-s1-brief.md Sec 3): a rig declaring no board:
  # anywhere (no top-level, none for the selected variant) is no longer a
  # list_rigs.py failure -- it renders empty here, same as an unselected
  # REVISION/VARIANT above, and this file alone decides whether that is
  # fatal (below), since only THIS file knows whether -DBOARD filled in
  # for it.
  if(_RIG_RESOLVED_BOARD STREQUAL "NOTFOUND")
    set(_RIG_RESOLVED_BOARD "")
  endif()

  # Rig-swap guard: the marker pins the BUILD DIR to the board we INFERRED
  # for this rig. zephyr_check_cache(BOARD) makes BOARD immutable per build
  # dir, but RIG is not cache-watched, so swapping -DRIG to a rig that
  # infers a DIFFERENT board must be caught here -- left unguarded, the
  # stale cache-carried BOARD would pass through unchanged and the
  # expander would read the OLD board's dts under the NEW rig's name.
  # Fires only when RIG_INFERRED_BOARD is defined: an INJECTED build (BOARD
  # given, nothing inferred, no marker set below) sets no marker, so a rig
  # swap there is judged only by the given-vs-declared comparison below,
  # same as any other -DBOARD build -- there is no "board this build dir
  # was pinned to" to protect.
  #
  # This ALSO fires when the user gives a fresh -DBOARD alongside the
  # rig-swap, even a matching one -- verified empirically: cmake applies a
  # -D override to the BOARD cache entry before this file ever runs, so
  # "${BOARD}" already reads the FRESH value here (upstream's own
  # zephyr_check_cache(BOARD), which would otherwise warn and silently
  # discard it back to the pinned one, has not run yet -- that is step 2,
  # below). Giving -DBOARD does not make this dir's board mutable: without
  # this guard, upstream's own mechanism would silently keep building the
  # OLD board and only WARN, never stop -- exactly the wrong-hardware
  # footgun this guard exists to prevent, so it is intentionally NOT
  # narrowed to skip when a fresh -DBOARD is present. Comparing "${BOARD}"
  # (not just "${RIG}") against the marker is what lets the message below
  # name the ACTUAL reason in that case instead of blaming inference for
  # a board change the user tried to make directly.
  if(DEFINED RIG_INFERRED_BOARD
     AND NOT "${_RIG_RESOLVED_BOARD}" STREQUAL "${RIG_INFERRED_BOARD}")
    if(NOT "${BOARD}" STREQUAL "${RIG_INFERRED_BOARD}")
      message(FATAL_ERROR
        "Rig: -DRIG=${RIG} resolves to board '${_RIG_RESOLVED_BOARD}', and "
        "-DBOARD=${BOARD} was also given -- neither changes anything: "
        "this build directory's board ('${RIG_INFERRED_BOARD}') is "
        "immutable once configured, whether a rig or a board is trying to "
        "change it. A pristine build (-p always) is required either way.")
    else()
      message(FATAL_ERROR
        "Rig: -DRIG=${RIG} resolves to board '${_RIG_RESOLVED_BOARD}', but "
        "this build directory was configured for '${RIG_INFERRED_BOARD}'. "
        "Changing to a rig on a different board requires a pristine build "
        "(-p always).")
    endif()
  endif()

  # BOARD given -> it wins, unconditionally, whatever the rig declares (or
  # declares none of); no marker is set for it, since a user-supplied value
  # is never our own inference (kept out of RIG_INFERRED_BOARD so the
  # rig-swap guard above never mistakes it for one). BOARD absent -> infer
  # from the rig exactly as before -DBOARD existed, and record the marker;
  # a rig with nothing to infer (_RIG_RESOLVED_BOARD empty) then has
  # nothing left to fall back to, so it is a FATAL naming both the rig and
  # the missing flag.
  #   - fresh dir, both given: BOARD defined, no marker set -> BOARD wins.
  #   - fresh dir, RIG only: BOARD undefined -> infer + set the marker.
  #   - reconfigure, no -DBOARD repeated: BOARD defined FROM THE CACHE,
  #     equal to the marker (both are our own old inference) -> re-infers
  #     the same value, passes silently.
  #   - reconfigure, user repeats the SAME -DBOARD value: indistinguishable
  #     from the cache case above -- accepted residual, not fixed.
  #   - reconfigure with a CHANGED -DRIG: the rig-swap guard above.
  if(DEFINED BOARD)
    if(_RIG_RESOLVED_BOARD AND NOT "${BOARD}" STREQUAL "${_RIG_RESOLVED_BOARD}")
      message(STATUS
        "Rig: -DBOARD=${BOARD} given for -DRIG=${RIG}, overriding its own "
        "board '${_RIG_RESOLVED_BOARD}'")
    endif()
  elseif(_RIG_RESOLVED_BOARD)
    set(BOARD "${_RIG_RESOLVED_BOARD}" CACHE STRING
      "Board inferred from -DRIG=${RIG} (rig.yml's board:, no -DBOARD given)")
    set(RIG_INFERRED_BOARD "${_RIG_RESOLVED_BOARD}" CACHE INTERNAL
      "Rig-swap-guard marker: the board value this fork inferred from \
-DRIG=${RIG}. Compared against a later cache-carried BOARD so a \
reconfigure of the SAME build dir is not mistaken for a user-passed \
-DBOARD")
  else()
    message(FATAL_ERROR
      "Rig: -DRIG=${RIG} declares no board: (neither a top-level one nor "
      "one for its selected variant) and no -DBOARD was given -- this rig "
      "has no board of its own to fall back to; pass -DBOARD=<name>.")
  endif()

  set(_rig_boards_qualifiers_desc "")
  if(_RIG_RESOLVED_REVISION)
    string(APPEND _rig_boards_qualifiers_desc " revision: ${_RIG_RESOLVED_REVISION}")
  endif()
  if(_RIG_RESOLVED_VARIANT)
    string(APPEND _rig_boards_qualifiers_desc " variant: ${_RIG_RESOLVED_VARIANT}")
  endif()
  message(STATUS "Rig: ${_RIG_RESOLVED_NAME} (${_RIG_RESOLVED_DIR}/rig.yml), board: ${_RIG_RESOLVED_BOARD}${_rig_boards_qualifiers_desc}")
endif()
# ---------------------------------------------------------------------------

# Step 2: the real boards module, unconditionally (rig build or plain).
include(${ZEPHYR_BASE}/cmake/modules/boards.cmake)

# ---------------------------------------------------------------------------
# _rig_resolve_board_dts(<out-var>): resolve the CURRENT board target's own
# .dts file. Defined here because BOTH this fork's own use just below (the
# plain-build -isystem guard) AND the dts.cmake fork (its pass-1 recipe)
# need it; a single definition means the two never duplicate zephyr's own
# board-target naming logic between them.
#
# Sets <out-var>, in the caller's scope, to the resolved absolute path, or
# to an empty string if no candidate exists in any BOARD_DIRECTORIES
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
# An extension variant's own .dts (board.yml extend:, e.g.
# boards/extend/st/nucleo_f401re/nucleo_f401re_stm32f401xe_rig.dts) wants to
# #include the REAL base board's own top-level .dts -- the whole point
# of an extension over a clone: inherit upstream content instead of
# duplicating it. But the C-preprocessor include search path pre_dt.cmake
# builds only ever adds FIXED SUBPATHS of each DTS_ROOT entry (include,
# dts, ...) -- never a board directory's own root -- so a bare
# #include "nucleo_f401re.dts" from a SIBLING directory (the extension's
# own dir) cannot resolve via the ordinary search path (verified
# empirically: cmake configure fails "No such file or directory").
#
# Fix: append every OTHER BOARD_DIRECTORIES entry (at minimum the base
# board's own dir, directories[0]) as an extra -isystem to
# DTS_EXTRA_CPPFLAGS -- an EXISTING, documented dts.cmake extension point
# ("DTS_EXTRA_CPPFLAGS: extra command line options ... to the C
# preprocessor", cmake/modules/dts.cmake). This module (the fork point) runs
# for EVERY build -- rig or plain -- and runs after the real boards.cmake
# include above (BOARD_DIRECTORIES already resolved) but before dts.cmake
# (still in time for DTS_EXTRA_CPPFLAGS to be picked up), so a genuinely
# plain -b nucleo_f401re/stm32f401xe/rig build is covered too, not just a
# -DRIG one.
#
# Guarded so this is a total no-op for every OTHER build (plain, non-rig
# boards, and even a PLAIN build of an EXTENDED board's base target):
# resolve the CURRENT target's own .dts (the shared
# _rig_resolve_board_dts helper above) and act only if it lives in a
# directory OTHER than BOARD_DIRECTORIES's first entry (the base board's
# own directory -- always directories[0], per list_boards.py's
# extend_v2_boards()). A plain nucleo_f401re build's own BOARD_DIRECTORIES
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
