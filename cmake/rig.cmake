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
# Debuggability: render a command line copy-pasteably into a shell (zsh/bash),
# for `message(VERBOSE ...)` below and for rerun-expand.sh. Activate VERBOSE
# output with `west build-rig ... -- -DCMAKE_MESSAGE_LOG_LEVEL=VERBOSE`
# (reuses CMake's own log-level machinery — no new flag of our own).
#
# _rig_shell_quote_argv: wraps every argument in single quotes (POSIX
# '...'-quoting — safe for ANY content, including spaces/globs/embedded
# quotes; an embedded `'` becomes `'\''`), for plain positional arguments.
function(_rig_shell_quote_argv out_var)
  set(_rig_rendered "")
  foreach(_rig_tok ${ARGN})
    string(REPLACE "'" "'\\''" _rig_tok_esc "${_rig_tok}")
    string(APPEND _rig_rendered "'${_rig_tok_esc}' ")
  endforeach()
  string(STRIP "${_rig_rendered}" _rig_rendered)
  set(${out_var} "${_rig_rendered}" PARENT_SCOPE)
endfunction()

# _rig_shell_quote_env: renders a list of "NAME=value" strings as
# `NAME='value'` (value single-quoted, NAME left bare) — a shell only
# recognizes `NAME=value` as an env-assignment prefix when NAME itself is
# UNQUOTED (verified: quoting the whole token, e.g. `'NAME=value'`, makes
# both bash and zsh treat it as the command to run, not an assignment).
function(_rig_shell_quote_env out_var)
  set(_rig_rendered "")
  foreach(_rig_pair ${ARGN})
    string(FIND "${_rig_pair}" "=" _rig_eq_pos)
    string(SUBSTRING "${_rig_pair}" 0 ${_rig_eq_pos} _rig_name)
    math(EXPR _rig_val_start "${_rig_eq_pos} + 1")
    string(SUBSTRING "${_rig_pair}" ${_rig_val_start} -1 _rig_value)
    string(REPLACE "'" "'\\''" _rig_value_esc "${_rig_value}")
    string(APPEND _rig_rendered "${_rig_name}='${_rig_value_esc}' ")
  endforeach()
  string(STRIP "${_rig_rendered}" _rig_rendered)
  set(${out_var} "${_rig_rendered}" PARENT_SCOPE)
endfunction()
# ---------------------------------------------------------------------------

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
# The interpreter is NOT a knob: we use Zephyr's PYTHON_EXECUTABLE (set by the
# `python` module included above, and already used for list_rigs.py below) so
# the expander runs in the same venv as the rest of the build — no hardcoded
# path. RIG_EXPAND_PYTHONPATH is module-relative (derived from _RIG_BTR_ROOT,
# this module's own tree — that is the location of OUR mechanics, the rigexp
# package, which is legitimately ours). The shield LIBRARY, by contrast, is
# discoverable CONTENT, not mechanics: rig shield templates may live in any
# board_root of any Zephyr module (btr-shields ships some as default content,
# but must not be hardcoded as THE source). So it is derived from BOARD_ROOT
# below, exactly as list_shields.py discovers shields — not a fixed knob.
set(RIG_EXPAND_PYTHONPATH "${_RIG_BTR_ROOT}/scripts"
  CACHE PATH "PYTHONPATH so 'python -m rigexp' finds btr-shields/scripts/rigexp")
set(RIG_EXPAND_COMMAND ""
  CACHE STRING "Override: full command (semicolon list) to run instead of the rigexp CLI")

# Resolve -DRIG=<name> to a rig folder via list_rigs.py — mirrors exactly how
# the shield tail below resolves shield names via list_shields.py --json.
list(TRANSFORM BOARD_ROOT PREPEND "--board-root=" OUTPUT_VARIABLE _rig_board_root_args)

set(_rig_list_rigs_argv
  ${PYTHON_EXECUTABLE} ${_RIG_BTR_ROOT}/scripts/list_rigs.py
  ${_rig_board_root_args} --json)

set(_list_rigs_commands COMMAND ${_rig_list_rigs_argv})

# No env prefix applies here (list_rigs.py needs neither PYTHONPATH nor
# ZEPHYR_BASE) — just the plain, copy-pasteable argv.
_rig_shell_quote_argv(_rig_list_rigs_render ${_rig_list_rigs_argv})
message(VERBOSE "rig: list_rigs command:\n${_rig_list_rigs_render}")

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

# Shield-library roots: every board_root's boards/shields, mirroring how
# list_shields.py itself discovers shields (root/boards/shields). The expander
# unions them and self-filters to rig templates (a folder is a template iff it
# holds <name>.shield). btr-shields contributes its own shields via its own
# board_root here, no differently from any other module — mechanics (this
# module's cmake/scripts) stay separate from content (shields, wherever they
# live).
set(_rig_shield_dir_args)
foreach(_root ${BOARD_ROOT})
  if(EXISTS "${_root}/boards/shields")
    list(APPEND _rig_shield_dir_args --shield-dir "${_root}/boards/shields")
  endif()
endforeach()

# ---------------------------------------------------------------------------
# Pass-1 recipe (THE FLIP; Bridge-A saferail 13, AMENDED): the board .dts +
# the cpp include dirs / edtlib bindings dirs the expander's OWN edtlib.EDT
# needs to read the REAL board devicetree (boarddt.py / board_edt.py /
# edt_build.py). A real build's build_info.yml normally carries this
# (dts.cmake:441-442, dts_build_info_output()), but that file does not exist
# yet here — it is written by dts.cmake AFTER this module runs in a fresh
# build dir (chicken-and-egg). `include(pre_dt)` is unsafe here too: its
# arch_include loop needs ARCH_V2_NAME_LIST, which hwm_v2 sets — a module
# that runs AFTER this one (shields@95 < hwm_v2@97 < pre_dt_board@103) — and
# pre_dt.cmake's own include_guard(GLOBAL) would turn dts.cmake's later,
# correct include(pre_dt) into a silent no-op, freezing
# DTS_ROOT_SYSTEM_INCLUDE_DIRS at THIS incomplete result for the rest of the
# configure. So this block COMPUTES the dirs itself, mirroring
# cmake/modules/pre_dt.cmake's derivation by hand (verified against a real
# build's build_info.yml — see the handoff report); saferail 3's edt.pickle
# cross-check (tests/test_board_dualread.py) is the equivalence guard that
# this mirror stays correct against pass-2's real one.
#
# DTS_ROOT already carries every Zephyr module's own `dts_root` setting (set
# by the zephyr_module module, which — like boards — runs before shields).
# pre_dt.cmake also folds in APPLICATION_SOURCE_DIR, BOARD_DIR, SHIELD_DIRS
# and ZEPHYR_BASE; of those, only BOARD_DIR (boards.cmake has already run)
# and ZEPHYR_BASE apply here — APPLICATION_SOURCE_DIR is deliberately
# EXCLUDED (saferail 12: pass 1 reads only the board's own devicetree, with
# no app/overlay context), and SHIELD_DIRS is not yet known at this point in
# the file (RIG_SHIELDS comes from the expander's OWN output, resolved
# below) — moot anyway, since the board-DTS read never needs shield
# bindings.
set(_rig_dts_root ${DTS_ROOT} "${BOARD_DIR}" "${ZEPHYR_BASE}")
set(_rig_dts_root_real)
foreach(_rig_dts_dir ${_rig_dts_root})
  file(REAL_PATH "${_rig_dts_dir}" _rig_dts_real_dir)
  list(APPEND _rig_dts_root_real "${_rig_dts_real_dir}")
endforeach()
list(REMOVE_DUPLICATES _rig_dts_root_real)

# Arch include dirs: pre_dt.cmake builds `dts/<arch>` per entry of
# ARCH_V2_NAME_LIST (unavailable here, see above). Glob
# `${ZEPHYR_BASE}/dts/*` instead: every arch name is itself a subdirectory of
# zephyr's own `dts/` (dts/arm, dts/riscv, …), so this recovers the same
# name set without ARCH_V2_NAME_LIST. It also picks up `dts/common`,
# `dts/vendor`, `dts/bindings` as spurious extra names — already covered
# below by their own fixed entries, or (bindings) simply an unused extra -I
# directory — a harmless superset for a C preprocessor search path.
file(GLOB _rig_dts_arch_candidates LIST_DIRECTORIES true "${ZEPHYR_BASE}/dts/*")
set(_rig_dts_arch_names)
foreach(_rig_dts_arch_dir ${_rig_dts_arch_candidates})
  if(IS_DIRECTORY "${_rig_dts_arch_dir}")
    get_filename_component(_rig_dts_arch_name "${_rig_dts_arch_dir}" NAME)
    list(APPEND _rig_dts_arch_names "${_rig_dts_arch_name}")
  endif()
endforeach()

# Finalize the two lists dts.cmake itself derives from DTS_ROOT: system
# include dirs (DTS_ROOT_SYSTEM_INCLUDE_DIRS, pre_dt.cmake) and bindings dirs
# (DTS_ROOT_BINDINGS, dts.cmake) — existing directories only, per-root.
set(_rig_dts_include_dirs)
set(_rig_dts_bindings_dirs)
foreach(_rig_dts_root_dir ${_rig_dts_root_real})
  foreach(_rig_dts_sub include include/zephyr dts/common dts/vendor dts)
    if(EXISTS "${_rig_dts_root_dir}/${_rig_dts_sub}")
      list(APPEND _rig_dts_include_dirs "${_rig_dts_root_dir}/${_rig_dts_sub}")
    endif()
  endforeach()
  foreach(_rig_dts_arch_name ${_rig_dts_arch_names})
    if(EXISTS "${_rig_dts_root_dir}/dts/${_rig_dts_arch_name}")
      list(APPEND _rig_dts_include_dirs "${_rig_dts_root_dir}/dts/${_rig_dts_arch_name}")
    endif()
  endforeach()
  if(EXISTS "${_rig_dts_root_dir}/dts/bindings")
    list(APPEND _rig_dts_bindings_dirs "${_rig_dts_root_dir}/dts/bindings")
  endif()
endforeach()

# The board's own devicetree (Conv. 4). Our clones are simple hwmv2 boards —
# single SoC, no board revision suffix — so this is exactly
# dts.cmake:dts_configuration_files()'s DTS_SOURCE for this board:
# `${BOARD_DIR}/${BOARD}.dts`. The in-build path always passes this
# explicitly (--board-dts below); boarddt.py's own name->dts discovery
# (list_boards.py) is the standalone/CLI-only fallback for when it isn't.
set(_rig_board_dts "${BOARD_DIR}/${BOARD}.dts")

set(_rig_include_dir_args)
foreach(_rig_dts_dir ${_rig_dts_include_dirs})
  list(APPEND _rig_include_dir_args --include-dir "${_rig_dts_dir}")
endforeach()
set(_rig_bindings_dir_args)
foreach(_rig_dts_dir ${_rig_dts_bindings_dirs})
  list(APPEND _rig_bindings_dir_args --bindings-dir "${_rig_dts_dir}")
endforeach()
# ---------------------------------------------------------------------------

# _rig_debug_env / _rig_debug_argv split out the env-prefix from the argv
# (rather than composing _rig_cmd's `cmake -E env ...` tokens directly) so
# BOTH the VERBOSE render below AND rerun-expand.sh can show the invocation
# in native shell syntax (`NAME=val NAME=val exe args...`), not cmake's own
# `-E env` spelling — that's what's actually copy-pasteable into zsh with a
# debugger prepended (e.g. `python3 -m pdb -m rigexp expand ...`). _rig_cmd
# (what execute_process actually runs) is composed FROM them, unchanged
# behavior-wise from before this split.
if(RIG_EXPAND_COMMAND)
  set(_rig_debug_env "")
  set(_rig_debug_argv ${RIG_EXPAND_COMMAND})
  set(_rig_cmd ${RIG_EXPAND_COMMAND})
else()
  set(_rig_debug_env
    "PYTHONPATH=${RIG_EXPAND_PYTHONPATH}"
    "ZEPHYR_BASE=${ZEPHYR_BASE}")
  set(_rig_debug_argv
    "${PYTHON_EXECUTABLE}" -m rigexp expand "${_rig_yml}"
    ${_rig_shield_dir_args}
    --board-dts "${_rig_board_dts}"
    ${_rig_include_dir_args}
    ${_rig_bindings_dir_args}
    --out-dir "${_rig_out_dir}")
  set(_rig_cmd "${CMAKE_COMMAND}" -E env ${_rig_debug_env} ${_rig_debug_argv})
endif()

_rig_shell_quote_env(_rig_expand_env_render ${_rig_debug_env})
_rig_shell_quote_argv(_rig_expand_argv_render ${_rig_debug_argv})
if(_rig_expand_env_render)
  set(_rig_expand_render "${_rig_expand_env_render} ${_rig_expand_argv_render}")
else()
  set(_rig_expand_render "${_rig_expand_argv_render}")
endif()
message(VERBOSE "rig: expand command:\n${_rig_expand_render}")

# rerun-expand.sh: always written, BEFORE execute_process — so even a FAILED
# expand leaves behind a standalone, executable re-run of the exact pass-1
# invocation (e.g. `python3 -m pdb -m rigexp expand ...`, copied from the
# exec line below). Rewritten every configure; nothing here is durable.
set(_rig_rerun_script "${_rig_out_dir}/rerun-expand.sh")
set(_rig_rerun_lines
  "#!/bin/sh"
  "# regenerate: this file is rewritten on every configure -- edits here do not persist."
  "# Re-runs cmake/rig.cmake's pass-1 expander invocation standalone (e.g. under"
  "# a debugger: copy the env + argv below into 'python3 -m pdb -m rigexp expand ...')."
  "set -e")
foreach(_rig_env_pair ${_rig_debug_env})
  string(FIND "${_rig_env_pair}" "=" _rig_eq_pos)
  string(SUBSTRING "${_rig_env_pair}" 0 ${_rig_eq_pos} _rig_env_name)
  math(EXPR _rig_val_start "${_rig_eq_pos} + 1")
  string(SUBSTRING "${_rig_env_pair}" ${_rig_val_start} -1 _rig_env_value)
  string(REPLACE "'" "'\\''" _rig_env_value_esc "${_rig_env_value}")
  list(APPEND _rig_rerun_lines "export ${_rig_env_name}='${_rig_env_value_esc}'")
endforeach()
list(APPEND _rig_rerun_lines "exec ${_rig_expand_argv_render} \"$@\"")
list(JOIN _rig_rerun_lines "\n" _rig_rerun_content)
file(WRITE "${_rig_rerun_script}" "${_rig_rerun_content}\n")
file(CHMOD "${_rig_rerun_script}" PERMISSIONS
  OWNER_READ OWNER_WRITE OWNER_EXECUTE
  GROUP_READ GROUP_EXECUTE
  WORLD_READ WORLD_EXECUTE)

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

# EXTRA_DTC_OVERLAY_FILE is a list, symmetric with OVERLAY_CONFIG below: the
# expander's generated overlay first, then the rig folder's own hand-authored
# `rig.overlay` (if present). The latter is the DT counterpart of rig.conf — a
# rig author supplies DT the expander cannot emit, notably the board pinctrl
# pinmux fragment a function needs to route on real silicon (R21 deep half):
# the expander only enables the controller (status="okay") and names the pin in
# the config sheet; it does not author SoC pinmux. Applied after the expander
# overlay so it can augment nodes the expander created.
set(_rig_overlay_files "${_rig_overlay}")
set(_rig_user_overlay "${_rig_dir}/rig.overlay")
if(EXISTS "${_rig_user_overlay}")
  list(APPEND _rig_overlay_files "${_rig_user_overlay}")
  message(STATUS "rig: applying ${_rig_user_overlay}")
endif()
set(EXTRA_DTC_OVERLAY_FILE "${_rig_overlay_files}" CACHE STRING
  "Rig-generated + rig-authored devicetree overlays (set by rig.cmake)" FORCE)

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
if(EXISTS "${_rig_user_overlay}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_rig_user_overlay}")
endif()
file(GLOB _rig_expander_sources "${_RIG_BTR_ROOT}/scripts/rigexp/*.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${_rig_expander_sources})
# The -DRIG=<name> resolver itself (list_rigs.py) — an obvious static miss:
# renaming/adding a rig.yml `rig.name` changes what -DRIG resolves to.
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${_RIG_BTR_ROOT}/scripts/list_rigs.py")

# Handoff: the expander wrote context.cmake telling us what the rig instantiated
# (RIG_NAME / RIG_BOARD / RIG_SHIELDS). The cloned shield-processing tail below
# will drive its Kconfig/bookkeeping loop over RIG_SHIELDS instead of -DSHIELD.
include(${_rig_out_dir}/context.cmake OPTIONAL)
message(STATUS "rig: '${RIG_NAME}' board=${RIG_BOARD} shields=[${RIG_SHIELDS}]")

# Dependency-tracking handoff (dynamic half): RIG_DEPENDS is every real
# source-tree file THIS expand actually read — rig.yml, every parsed
# `.shield` template (+ its cpp-included files), connector plug/socket
# bindings, index headers, the board .dts — the expander is the single
# authority on what pass 1 opened, so it is the one that reports this, not a
# glob re-derived here. Appended on top of the static registrations above,
# which cover the PRE-expansion trigger set (rig.yml itself, the expander's
# own sources, list_rigs.py): editing e.g. a .shield template not yet named
# by any instance in this rig is untracked until the rig names it and one
# configure runs to pick it up (a one-configure lag, acceptable — the static
# set guarantees that configure happens whenever the rig FILE itself changes).
if(DEFINED RIG_DEPENDS AND RIG_DEPENDS)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${RIG_DEPENDS})
endif()
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

# ---------------------------------------------------------------------------
# Build-info provenance (rig-build provenance requirement): record what THIS
# rig build looked at, via zephyr's own build_info() (cmake/modules/
# extensions.cmake) — the same mechanism dts.cmake:441-442 uses for its own
# devicetree section. "rig" is not one of build-schema.yaml's own cmake.*
# tags, and that file is upstream (zephyr-rigs/scripts/schemas/
# build-schema.yaml) — not ours to extend — so this rides the schema's own
# downstream-owned escape hatch, `vendor-specific`, whose own schema entry is
# `cmake.vendor-specific.<key>.<subkey>: string` (exactly two levels, string
# leaves only). Verified empirically (see the handoff report): this lands at
# cmake.vendor-specific.rig.* in build_info.yml, NOT the naively-expected
# cmake.rig.*. Multi-valued facts (shields, their resolved dirs) are JOINed
# into ONE string before the call: build_info()'s vendor-specific path always
# forces its underlying yaml_set() KEY type to VALUE (never LIST), and an
# un-joined CMake list silently truncates to its first element there
# (verified: a 2-shield rig recorded only the first shield until joined).
list(JOIN RIG_SHIELDS ", " _rig_shields_joined)
list(JOIN SHIELD_DIRS ", " _rig_shield_dirs_joined)

build_info(vendor-specific rig name VALUE "${RIG_NAME}")
build_info(vendor-specific rig board VALUE "${RIG_BOARD}")
build_info(vendor-specific rig rig-yml VALUE "${_rig_yml}")
build_info(vendor-specific rig board-dts VALUE "${_rig_board_dts}")
build_info(vendor-specific rig shields VALUE "${_rig_shields_joined}")
build_info(vendor-specific rig shield-dirs VALUE "${_rig_shield_dirs_joined}")
build_info(vendor-specific rig out-dir VALUE "${_rig_out_dir}")
if(EXISTS "${_rig_conf_file}")
  build_info(vendor-specific rig rig-conf VALUE "${_rig_conf_file}")
endif()
if(EXISTS "${_rig_user_overlay}")
  build_info(vendor-specific rig rig-overlay VALUE "${_rig_user_overlay}")
endif()
# ---------------------------------------------------------------------------
