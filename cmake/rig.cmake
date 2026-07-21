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

# Resolve -DRIG=<name> to a rig folder via list_rigs.py — mirrors exactly how
# the shield tail below resolves shield names via list_shields.py --json.
list(TRANSFORM BOARD_ROOT PREPEND "--board-root=" OUTPUT_VARIABLE _rig_board_root_args)

set(_list_rigs_commands
  COMMAND ${PYTHON_EXECUTABLE} ${_RIG_BTR_ROOT}/scripts/list_rigs.py
  ${_rig_board_root_args} --json
)

execute_process(${_list_rigs_commands}
  OUTPUT_VARIABLE _rigs_json
  ERROR_VARIABLE _err_rigs
  RESULT_VARIABLE _ret_val_rigs
)

if(_ret_val_rigs)
  message(FATAL_ERROR "Error finding rigs\nError message: ${_err_rigs}")
endif()

string(JSON _rigs_length LENGTH ${_rigs_json})

set(_rig_dir)
set(RIG_LIST)
if(_rigs_length GREATER 0)
  math(EXPR _rigs_length "${_rigs_length} - 1")

  foreach(i RANGE ${_rigs_length})
    string(JSON _rig_entry GET "${_rigs_json}" "${i}")
    string(JSON _rig_entry_name GET ${_rig_entry} name)
    string(JSON _rig_entry_dir GET ${_rig_entry} dir)
    list(APPEND RIG_LIST ${_rig_entry_name})
    if(_rig_entry_name STREQUAL RIG)
      set(_rig_dir ${_rig_entry_dir})
    endif()
  endforeach()
endif()
list(SORT RIG_LIST)

if(NOT _rig_dir)
  string(REPLACE ";" "\n" _rig_string "${RIG_LIST}")
  message(FATAL_ERROR
    "rig: -DRIG=${RIG} does not resolve to a rig.\n"
    "Please choose from among the following rigs:\n${_rig_string}")
endif()

set(_rig_yml "${_rig_dir}/rig.yml")
if(NOT EXISTS "${_rig_yml}")
  message(FATAL_ERROR
    "rig: -DRIG=${RIG} resolved to '${_rig_dir}' but it has no rig.yml:\n"
    "  Expected: ${_rig_yml}")
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

# OVERLAY_CONFIG is a list: the expander's generated fragment (${_rig_conf},
# e.g. Kconfig facts derived from the topology) first, then the rig folder's
# own hand-authored rig.conf (option A — the umbrella-subsystem activation
# layer a rig author writes so the instantiated shields' DRIVERS actually
# build; the expander cannot know this, it only knows topology).
set(_rig_overlay_config "")
if(EXISTS "${_rig_conf}")
  list(APPEND _rig_overlay_config "${_rig_conf}")
else()
  message(STATUS "rig: no Kconfig fragment produced (expected at P2)")
endif()

set(_rig_conf_file "${_rig_dir}/rig.conf")
if(EXISTS "${_rig_conf_file}")
  list(APPEND _rig_overlay_config "${_rig_conf_file}")
  message(STATUS "rig: applying ${_rig_conf_file}")
endif()

if(_rig_overlay_config)
  set(OVERLAY_CONFIG "${_rig_overlay_config}" CACHE STRING
    "Rig-generated + rig-authored Kconfig fragments (set by rig.cmake)" FORCE)
endif()

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_rig_yml}")
if(EXISTS "${_rig_conf_file}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_rig_conf_file}")
endif()
file(GLOB _rig_expander_sources "${_RIG_BTR_ROOT}/scripts/rigexp/*.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${_rig_expander_sources})

# Handoff: the expander wrote context.cmake telling us what the rig instantiated
# (RIG_NAME / RIG_BOARD / RIG_SHIELDS). The cloned shield-processing tail below
# will drive its Kconfig/bookkeeping loop over RIG_SHIELDS instead of -DSHIELD.
include(${_rig_out_dir}/context.cmake OPTIONAL)
message(STATUS "rig: '${RIG_NAME}' board=${RIG_BOARD} shields=[${RIG_SHIELDS}]")
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shield processing, RIG_SHIELDS-driven (P3 3a rewrite of the stock tail).
#
# Unlike stock shields.cmake, shields here are never selected via -DSHIELD;
# they come from the rig's own instances (RIG_SHIELDS, set by context.cmake
# above). DT is entirely the expander's domain — it already emitted the
# overlay set as EXTRA_DTC_OVERLAY_FILE earlier in this file — so this tail's
# job is Kconfig + bookkeeping only:
#   - keep the list_shields.py discovery block (SHIELD_LIST/SHIELD_DIR_<name>)
#     unchanged: our shield folders have matching shield.yml names, so it
#     finds them exactly as it would for a stock shield;
#   - validate each rig shield resolves to a real shield folder, else
#     FATAL_ERROR (retargeted from the stock "invalid SHIELD" error);
#   - collect each shield's <name>.conf plus board-specific CONF_FILES (KCONF
#     only — the <name>.overlay / DTS collection is dropped entirely, the
#     expander owns DT);
#   - set SHIELD_AS_LIST so kconfig.cmake's `shields_list_contains` (which
#     every shield's Kconfig.shield calls) turns SHIELD_<NAME> on. Reusing
#     SHIELD_AS_LIST here is safe: stock shields.cmake's DTS-collection use of
#     it never runs in this file (that's the whole point of the shields.cmake
#     fork), so there is no double-overlay risk.
#   - drop the stock zephyr_check_cache(SHIELD WATCH) / SHIELD-from-cache
#     seeding entirely: shields come from the rig file, already tracked via
#     CMAKE_CONFIGURE_DEPENDS on the .rig.yml above.
# ---------------------------------------------------------------------------

# Prepare list shields command.
# This command is used for locating the shield dir as well as printing all shields
# in the system in the following cases:
# - A rig names a shield with no matching folder
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
list(SORT SHIELD_LIST)

# Process the rig's shields (RIG_SHIELDS from context.cmake, not -DSHIELD).
foreach(s ${RIG_SHIELDS})
  if(NOT s IN_LIST SHIELD_LIST)
    string(REPLACE ";" "\n" shield_string "${SHIELD_LIST}")
    message("No shield named '${s}' found")
    message("Please choose from among the following shields:\n"
            "${shield_string}"
    )
    message(FATAL_ERROR
      "rig: '${RIG_NAME}' names shield '${s}', which has no matching shield "
      "folder; see above.")
  endif()

  # Add the shield's directory to the SHIELD_DIRS output variable.
  list(APPEND
    SHIELD_DIRS
    ${SHIELD_DIR_${s}}
    )

  include(${SHIELD_DIR_${s}}/pre_dt_shield.cmake OPTIONAL)

  # Search for shield/shield.conf file (DT collection intentionally dropped —
  # the expander already emitted the overlay set above).
  if(EXISTS ${SHIELD_DIR_${s}}/${s}.conf)
    list(APPEND
      shield_conf_files
      ${SHIELD_DIR_${s}}/${s}.conf
      )
  endif()

  # Add board-specific .conf files to shield_conf_files (KCONF only).
  zephyr_file(CONF_FILES ${SHIELD_DIR_${s}}/boards
              KCONF shield_conf_files
  )
  zephyr_file(CONF_FILES ${SHIELD_DIR_${s}}/boards/${s}
              KCONF shield_conf_files
  )
endforeach()

# The Kconfig activation trigger: kconfig.cmake passes SHIELD_AS_LIST into
# Kconfig, and each shield's Kconfig.shield (`def_bool
# $(shields_list_contains,<name>)`) makes SHIELD_<NAME> true, firing its
# Kconfig.defconfig.
set(SHIELD_AS_LIST "${RIG_SHIELDS}")

# Prepend each shield with COMMAND <cmake> -E echo <shield>" for printing.
# Each shield is printed as new command because build files are not fond of newlines.
list(TRANSFORM SHIELD_LIST PREPEND "COMMAND;${CMAKE_COMMAND};-E;echo;"
     OUTPUT_VARIABLE shields_target_cmd
)

add_custom_target(shields ${shields_target_cmd} USES_TERMINAL)
