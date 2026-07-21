# SPDX-License-Identifier: Apache-2.0
#
# Copyright (c) 2021, Nordic Semiconductor ASA

# Validate shields and setup shields target.
#
# This module will validate the SHIELD argument.
#
# If a shield implementation is not found for one of the specified shields, an
# error will be raised and a list of valid shields will be printed.
#
# Outcome:
# The following variables will be defined when this module completes:
# - shield_conf_files: List of shield-specific Kconfig fragments
# - shield_dts_files : List of shield-specific devicetree files
# - SHIELD_AS_LIST   : A CMake list of shields created from the SHIELD variable.
# - SHIELD_DIRS      : A CMake list of directories which contain shield definitions
#
# The following targets will be defined when this CMake module completes:
# - shields: when invoked, a list of valid shields will be printed
#
# If the SHIELD variable is changed after this module completes,
# a warning will be printed.
#
# Optional variables:
# - BOARD_ROOT: CMake list of board roots containing board implementations
#
# Variables set by this module and not mentioned above are for internal
# use only, and may be removed, renamed, or re-purposed without prior notice.

include_guard(GLOBAL)

include(extensions)
include(python)

# ---------------------------------------------------------------------------
# Rig expansion (folded in from the former default.cmake seam + rig_expand.cmake).
#
# rig.cmake is reached ONLY for a rig build (the shields.cmake fork dispatches
# here when RIG is set), so RIG is defined and no guard is needed. We expand the
# rig into a devicetree overlay (+ Kconfig fragment) and feed it into this build
# BEFORE dts runs (shields@95 < dts@107 in zephyr_cmake_modules order).
#
# `_RIG_BTR_ROOT` is this module's root (btr-shields/cmake/.. == btr-shields).
get_filename_component(_RIG_BTR_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

# Overrideable knobs (a probe/test can substitute a stub via RIG_EXPAND_COMMAND).
set(RIG_EXPAND_PYTHON "/wrk/z/ws-up/.venv/bin/python"
  CACHE FILEPATH "Python interpreter used to run the rigexp expander")
set(RIG_EXPAND_PYTHONPATH "${_RIG_BTR_ROOT}/scripts"
  CACHE PATH "PYTHONPATH so 'python -m rigexp' finds btr-shields/scripts/rigexp")
set(RIG_EXPAND_SHIELD_DIR "${_RIG_BTR_ROOT}/boards/shields"
  CACHE PATH "--shield-dir passed to the rigexp expander")
set(RIG_EXPAND_COMMAND ""
  CACHE STRING "Override: full command (semicolon list) to run instead of the rigexp CLI")

set(_rig_yml "${_RIG_BTR_ROOT}/boards/rigs/${RIG}.rig.yml")
if(NOT EXISTS "${_rig_yml}")
  message(FATAL_ERROR
    "rig: -DRIG=${RIG} does not resolve to a rig file.\n"
    "  Expected: ${_rig_yml}\n"
    "  (rigs live under ${_RIG_BTR_ROOT}/boards/rigs/<name>.rig.yml)")
endif()

set(_rig_out_dir "${CMAKE_BINARY_DIR}/rig")
file(MAKE_DIRECTORY "${_rig_out_dir}")
# The CLI writes the literal emitter keys into --out-dir: "overlay",
# "config-sheet.md", "expectations.yml" (no rig-name prefix, no extension).
set(_rig_overlay "${_rig_out_dir}/overlay")
set(_rig_conf "${_rig_out_dir}/conf")

if(RIG_EXPAND_COMMAND)
  set(_rig_cmd ${RIG_EXPAND_COMMAND})
else()
  set(_rig_cmd
    "${CMAKE_COMMAND}" -E env "PYTHONPATH=${RIG_EXPAND_PYTHONPATH}"
    "${RIG_EXPAND_PYTHON}" -m rigexp expand "${_rig_yml}"
    --shield-dir "${RIG_EXPAND_SHIELD_DIR}"
    --out-dir "${_rig_out_dir}")
endif()

message(STATUS "rig: expanding ${_rig_yml} -> ${_rig_out_dir}")
execute_process(
  COMMAND ${_rig_cmd}
  RESULT_VARIABLE _rig_result
  OUTPUT_VARIABLE _rig_stdout
  ERROR_VARIABLE _rig_stderr)

if(NOT _rig_result EQUAL 0)
  message(FATAL_ERROR
    "rig: rigexp expand failed for -DRIG=${RIG} (exit ${_rig_result})\n"
    "--- command ---\n${_rig_cmd}\n"
    "--- stdout ---\n${_rig_stdout}\n--- stderr ---\n${_rig_stderr}")
endif()
if(_rig_stdout OR _rig_stderr)
  message(STATUS "rig: expander output:\n${_rig_stdout}${_rig_stderr}")
endif()
if(NOT EXISTS "${_rig_overlay}")
  message(FATAL_ERROR
    "rig: expand reported success but wrote no overlay:\n  ${_rig_overlay}")
endif()

set(EXTRA_DTC_OVERLAY_FILE "${_rig_overlay}" CACHE STRING
  "Rig-generated devicetree overlay (set by rig.cmake)" FORCE)
if(EXISTS "${_rig_conf}")
  set(OVERLAY_CONFIG "${_rig_conf}" CACHE STRING
    "Rig-generated Kconfig fragment (set by rig.cmake)" FORCE)
else()
  message(STATUS "rig: no Kconfig fragment produced (expected at P2)")
endif()

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_rig_yml}")
file(GLOB _rig_expander_sources "${_RIG_BTR_ROOT}/scripts/rigexp/*.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${_rig_expander_sources})

# Handoff: the expander wrote context.cmake telling us what the rig instantiated
# (RIG_NAME / RIG_BOARD / RIG_SHIELDS). The cloned shield-processing tail below
# will drive its Kconfig/bookkeeping loop over RIG_SHIELDS instead of -DSHIELD.
include(${_rig_out_dir}/context.cmake OPTIONAL)
message(STATUS "rig: '${RIG_NAME}' board=${RIG_BOARD} shields=[${RIG_SHIELDS}]")
# ---------------------------------------------------------------------------

# Check that SHIELD has not changed.
zephyr_check_cache(SHIELD WATCH)

if(SHIELD)
  message(STATUS "Shield(s): ${SHIELD}")
endif()

if(DEFINED SHIELD)
  string(REPLACE " " ";" SHIELD_AS_LIST "${SHIELD}")
endif()
# SHIELD-NOTFOUND is a real CMake list, from which valid shields can be popped.
# After processing all shields, only invalid shields will be left in this list.
set(SHIELD-NOTFOUND ${SHIELD_AS_LIST})

# Prepare list shields command.
# This command is used for locating the shield dir as well as printing all shields
# in the system in the following cases:
# - User specifies an invalid SHIELD
# - User invokes '<build-command> shields' target
list(TRANSFORM BOARD_ROOT PREPEND "--board-root=" OUTPUT_VARIABLE board_root_args)

set(list_shields_commands
  COMMAND ${PYTHON_EXECUTABLE} ${ZEPHYR_BASE}/scripts/list_shields.py
  ${board_root_args} --json
)

# Get list of shields in JSON format
execute_process(${list_shields_commands}
  OUTPUT_VARIABLE shields_json
  ERROR_VARIABLE err_shields
  RESULT_VARIABLE ret_val
)

if(ret_val)
  message(FATAL_ERROR "Error finding shields\nError message: ${err_shields}")
endif()

string(JSON shields_length LENGTH ${shields_json})

if(shields_length GREATER 0)
  math(EXPR shields_length "${shields_length} - 1")

  foreach(i RANGE ${shields_length})
    string(JSON shield GET "${shields_json}" "${i}")
    string(JSON shield_name GET ${shield} name)
    string(JSON shield_dir GET ${shield} dir)
    list(APPEND SHIELD_LIST ${shield_name})
    set(SHIELD_DIR_${shield_name} ${shield_dir})
  endforeach()
endif()

# Process shields in-order
if(DEFINED SHIELD)
  foreach(s ${SHIELD_AS_LIST})
    if(NOT ${s} IN_LIST SHIELD_LIST)
      continue()
    endif()

    list(REMOVE_ITEM SHIELD-NOTFOUND ${s})

    # Add <shield>.overlay to the shield_dts_files output variable.
    list(APPEND
      shield_dts_files
      ${SHIELD_DIR_${s}}/${s}.overlay
      )

    # Add the shield's directory to the SHIELD_DIRS output variable.
    list(APPEND
      SHIELD_DIRS
      ${SHIELD_DIR_${s}}
      )

    include(${SHIELD_DIR_${s}}/pre_dt_shield.cmake OPTIONAL)

    # Search for shield/shield.conf file
    if(EXISTS ${SHIELD_DIR_${s}}/${s}.conf)
      list(APPEND
        shield_conf_files
        ${SHIELD_DIR_${s}}/${s}.conf
        )
    endif()

    # Add board-specific .conf and .overlay files to their
    # respective output variables.
    zephyr_file(CONF_FILES ${SHIELD_DIR_${s}}/boards
                DTS   shield_dts_files
                KCONF shield_conf_files
    )
    zephyr_file(CONF_FILES ${SHIELD_DIR_${s}}/boards/${s}
                DTS   shield_dts_files
                KCONF shield_conf_files
    )
  endforeach()
endif()

# Prepare shield usage command printing.
# This command prints all shields in the system in the following cases:
# - User specifies an invalid SHIELD
# - User invokes '<build-command> shields' target
list(SORT SHIELD_LIST)

if(DEFINED SHIELD AND NOT (SHIELD-NOTFOUND STREQUAL ""))
  # Convert the list to pure string with newlines for printing.
  string(REPLACE ";" "\n" shield_string "${SHIELD_LIST}")

  foreach (s ${SHIELD-NOTFOUND})
    message("No shield named '${s}' found")
  endforeach()
  message("Please choose from among the following shields:\n"
          "${shield_string}"
  )
  unset(CACHED_SHIELD CACHE)
  message(FATAL_ERROR "Invalid SHIELD; see above.")
endif()

# Prepend each shield with COMMAND <cmake> -E echo <shield>" for printing.
# Each shield is printed as new command because build files are not fond of newlines.
list(TRANSFORM SHIELD_LIST PREPEND "COMMAND;${CMAKE_COMMAND};-E;echo;"
     OUTPUT_VARIABLE shields_target_cmd
)

add_custom_target(shields ${shields_target_cmd} USES_TERMINAL)
