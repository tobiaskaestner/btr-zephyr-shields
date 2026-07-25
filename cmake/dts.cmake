# SPDX-License-Identifier: Apache-2.0
#
# Downstream FORK POINT for Zephyr's `dts` build module.
#
# btr-shields' cmake-modules dir is prepended to CMAKE_MODULE_PATH (module.yml
# `build: cmake-modules: cmake`), so zephyr_default.cmake's `include(dts)`
# resolves to THIS file, shadowing ${ZEPHYR_BASE}/cmake/modules/dts.cmake.
#
# Plain build (no -DRIG): defer to the ORIGINAL dts.cmake unchanged, so
# every other build behaves exactly as upstream.
#
# Rig build (-DRIG set): this is where the whole rig story lives — expand
# the rig into a devicetree overlay (+ Kconfig fragment), resolve the
# shields it instantiated, and hand both off to the REAL dts.cmake, which
# this file includes as its own last act (zephyr_default.cmake then calls
# the real module's own `dts_init`, as usual — this fork never wraps
# anything in a function, since dts.cmake/kconfig.cmake read the variables
# steps 5-7 below set from FILE scope).
#
# Nine steps, in order:
#   1. include(pre_dt)         -- the real one, first run (SHIELD_DIRS still
#                                  empty; harmless, see step 6)
#   2. pass-1 recipe           -- --include-dir/--bindings-dir args from the
#                                  REAL DTS_ROOT / DTS_ROOT_SYSTEM_INCLUDE_DIRS
#                                  (step 1's output) + BOARD_DIRECTORIES;
#                                  board dts via _rig_resolve_board_dts()
#                                  (boards.cmake fork)
#   3. run the expander        -- rig->folder resolution (reuses the
#                                  boards.cmake fork's _RIG_RESOLVED_DIR
#                                  stash, kill-the-double-resolution,
#                                  cmake-alone-rig-entry-brief.md; falls back
#                                  to its own list_rigs.py --json run if that
#                                  stash is absent), VERBOSE render,
#                                  rerun-expand.sh, RIG_EXPAND_COMMAND knob,
#                                  error reporting
#   4. context.cmake handoff   -- RIG_NAME/RIG_BOARD/RIG_SHIELDS, RIG_DEPENDS
#                                  + static CMAKE_CONFIGURE_DEPENDS
#   5. shield resolution       -- list_shields discovery, rig-template-marker
#                                  collision preference, SHIELD_DIRS,
#                                  pre_dt_shield.cmake includes,
#                                  shield_conf_files, SHIELD_AS_LIST
#   6. pre_dt_module_run()     -- SECOND run, now with SHIELD_DIRS known:
#                                  recomputes DTS_ROOT / DTS_ROOT_SYSTEM_
#                                  INCLUDE_DIRS for pass 2 (shield bindings
#                                  included)
#   7. overlay/conf handoff    -- prepend to EXTRA_DTC_OVERLAY_FILE; APPEND
#                                  to shield_conf_files (see the asymmetry
#                                  note at step 7 below)
#   8. build_info provenance
#   9. include(real dts.cmake) -- LAST line

include_guard(GLOBAL)

include(extensions)
include(python)

if(NOT DEFINED RIG)
  include(${ZEPHYR_BASE}/cmake/modules/dts.cmake)
  return()
endif()

# ===========================================================================
# Rig build: everything below runs at FILE scope (zephyr_default's include
# scope) -- never wrap this in a function; steps 5-7 set variables
# (shield_conf_files, SHIELD_AS_LIST, EXTRA_*) that dts.cmake/kconfig.cmake
# read from that scope.
# ===========================================================================

# `_RIG_BTR_ROOT` is this module's root (btr-shields/cmake/.. == btr-shields).
get_filename_component(_RIG_BTR_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

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

# ---------------------------------------------------------------------------
# Step 1: pre_dt, first run. `include(pre_dt)` resolves to the real
# ${ZEPHYR_BASE}/cmake/modules/pre_dt.cmake (no fork of it exists — its
# global include_guard trips here, the FIRST time it is ever included in
# this configure) and, per its own file-scope `pre_dt_module_run()` call,
# folds APPLICATION_SOURCE_DIR/BOARD_DIR/SHIELD_DIRS/ZEPHYR_BASE into
# DTS_ROOT and derives DTS_ROOT_SYSTEM_INCLUDE_DIRS (needs
# ARCH_V2_NAME_LIST, which hwm_v2 -- a module that runs BEFORE this fork in
# the module chain, slot 13 < slot 17 -- has already set). SHIELD_DIRS is
# still empty at this point (shields are resolved in step 5, below); step 6
# re-runs pre_dt_module_run() directly once they are known.
include(pre_dt)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 2: pass-1 recipe. The board .dts + the cpp include dirs / edtlib
# bindings dirs the expander's OWN edtlib.EDT needs to read the REAL board
# devicetree (boarddt.py / board_edt.py / edt_build.py) -- derived directly
# from step 1's real DTS_ROOT / DTS_ROOT_SYSTEM_INCLUDE_DIRS, no hand-rolled
# mirror: this fork runs AFTER hwm_v2, so ARCH_V2_NAME_LIST is set and
# pre_dt's own computation is already correct for pass 1.
#
# Known, accepted delta vs the old mirror: pre_dt folds
# APPLICATION_SOURCE_DIR into DTS_ROOT, so the app dir's include/bindings
# subpaths (if any exist) now appear in this recipe too. The old mirror
# excluded them citing saferail 12; that exclusion was about *reading app DT
# content*, which an unused `-I`/bindings-dir does not do -- and the test
# harness already runs pass 1 with recipes from cached plain-build
# build_info.yml, which include an app dir. Making pass-1's recipe
# derivation literally the same code path as pass-2's makes saferail 3's
# edt.pickle cross-check (test_board_dualread.py) strictly stronger.
set(_rig_include_dir_args)
foreach(_rig_dts_dir ${DTS_ROOT_SYSTEM_INCLUDE_DIRS})
  list(APPEND _rig_include_dir_args --include-dir "${_rig_dts_dir}")
endforeach()
# BOARD_DIRECTORIES themselves (not just the fixed subpaths pre_dt.cmake
# derives, mirrored into DTS_ROOT_SYSTEM_INCLUDE_DIRS above) so an hwmv2
# board EXTENSION variant's own dts (which lives in a DIFFERENT directory
# than the base board it `#include`s) can resolve that quoted include via
# the ordinary cpp search-path fallback -- pass 1's own analog of the
# boards.cmake fork's DTS_EXTRA_CPPFLAGS fix for pass 2 (see that file for
# the full gap description). A no-op for a plain, unextended board
# (BOARD_DIRECTORIES == [BOARD_DIR], already covered by
# DTS_ROOT_SYSTEM_INCLUDE_DIRS's own BOARD_DIR entry).
foreach(_rig_bdir ${BOARD_DIRECTORIES})
  list(APPEND _rig_include_dir_args --include-dir "${_rig_bdir}")
endforeach()

# Bindings dirs: the same `<dts_root>/dts/bindings` rule dts.cmake's own
# dts_configuration_files() uses to derive DTS_ROOT_BINDINGS (that function
# does not run until step 9, so it is not available here -- it is one
# `EXISTS` check per DTS_ROOT entry, not a rule worth waiting for).
set(_rig_bindings_dir_args)
foreach(_rig_dts_root_dir ${DTS_ROOT})
  if(EXISTS "${_rig_dts_root_dir}/dts/bindings")
    list(APPEND _rig_bindings_dir_args --bindings-dir "${_rig_dts_root_dir}/dts/bindings")
  endif()
endforeach()

# The board's own devicetree (Conv. 4), via the shared helper
# (boards.cmake's `_rig_resolve_board_dts` -- also used by that fork's own
# -isystem guard, so the naming logic is never duplicated between them):
# for a PLAIN, unextended board (BOARD_DIRECTORIES has one entry) this is
# exactly the previous `${BOARD_DIR}/${BOARD}.dts` result; for an hwmv2
# board EXTENSION variant (e.g. `nucleo_f401re/stm32f401xe/rig` --
# boards/extend/st/nucleo_f401re/) BOARD_DIRECTORIES also carries the
# extension dir(s) registered against the base board by list_boards.py's
# own `extend_v2_boards()`, so the variant's own
# `nucleo_f401re_stm32f401xe_rig.dts` is found there.
_rig_resolve_board_dts(_rig_board_dts)

if(NOT _rig_board_dts)
  message(FATAL_ERROR
    "rig: could not locate a board .dts for BOARD=${BOARD} "
    "BOARD_QUALIFIERS=${BOARD_QUALIFIERS} in any of: ${BOARD_DIRECTORIES}")
endif()
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 3: run the expander.

# Resolve -DRIG=<name> to a rig folder. THE DOUBLE RESOLUTION KILL
# (cmake-alone-rig-entry-brief.md): the boards.cmake fork (slot 10, runs
# before this file in the normal module chain) already resolved -DRIG once —
# to infer BOARD (or reject a user-given -DBOARD, the exclusivity guard) —
# and stashes the rig directory it found in
# `_RIG_RESOLVED_DIR` (a plain, non-cache, file/directory-scope variable that
# is still in scope here: `include()` does not introduce a new variable
# scope, so a `set()` in one included file is visible to a later one in the
# same configure, exactly like BOARD_DIRECTORIES itself). Reuse it instead of
# asking list_rigs.py the same question a second time per configure.
#
# Fall back to a fresh list_rigs.py --json enumeration (unchanged from
# before this slice) only if that stash is absent — e.g. a standalone
# SUB_COMPONENTS configure that reaches `dts` without ever loading `boards`.
if(DEFINED _RIG_RESOLVED_DIR AND NOT "${_RIG_RESOLVED_DIR}" STREQUAL "")
  set(_rig_dir "${_RIG_RESOLVED_DIR}")
  set(_rig_name "${_RIG_RESOLVED_NAME}")
else()
  message(VERBOSE
    "rig: _RIG_RESOLVED_DIR is unset -- boards.cmake's fork did not run "
    "before this file in this configure; resolving -DRIG=${RIG} again via "
    "list_rigs.py --json.")

  # Mirrors exactly how the shield resolution step below resolves shield
  # names via list_shields.py --json.
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
        set(_rig_name ${_rig_entry_name})
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
endif()

set(_rig_yml "${_rig_dir}/rig.yml")
if(NOT EXISTS "${_rig_yml}")
  message(FATAL_ERROR
    "rig: -DRIG=${RIG} resolved to '${_rig_dir}' but it has no rig.yml:\n"
    "  Expected: ${_rig_yml}")
endif()

set(_rig_out_dir "${CMAKE_BINARY_DIR}/rig")
file(MAKE_DIRECTORY "${_rig_out_dir}")
# The CLI writes the literal emitter keys into --out-dir: "rig-gen.overlay",
# "config-sheet.md", "expectations.yml" (rig-gen.* = generated counterparts
# of the rig folder's own hand-authored `<RIG>_defconfig`/`<RIG>.overlay`).
set(_rig_overlay "${_rig_out_dir}/rig-gen.overlay")
set(_rig_conf "${_rig_out_dir}/rig-gen.conf")

# The rig folder's own hand-authored fragments -- named from the rig itself
# (board/shield symmetry: `<board>_defconfig`, `<shield>.conf`, `<rig>_
# defconfig`/`<rig>.overlay`), so a `-DRIG` reconfigure to a different rig
# in the SAME dir naturally picks up that rig's OWN fragments, never a
# stale one left over from the previous rig's basename. Paths only --
# existence is checked wherever each is used: the static
# CMAKE_CONFIGURE_DEPENDS registration in step 4, and the overlay/conf
# handoff in step 7.
#
# Derived from the RESOLVED rig name, never from `${RIG}`: `${RIG}` is the
# user's target string, which carries the `name[@rev][/variant]` qualifiers
# (list_rigs.py:_RIG_TARGET_RE) that V1/V2 will start accepting, while these
# filenames are keyed on the bare name. Both are identical only while
# qualifiers are still rejected -- and both fragments are OPTIONAL, so
# deriving from `${RIG}` would degrade to a silently unapplied defconfig the
# day a qualifier appears, not to an error.
set(_rig_user_overlay "${_rig_dir}/${_rig_name}.overlay")
set(_rig_conf_file "${_rig_dir}/${_rig_name}_defconfig")

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

# _rig_debug_env / _rig_debug_argv split out the env-prefix from the argv
# (rather than composing _rig_cmd's `cmake -E env ...` tokens directly) so
# BOTH the VERBOSE render below AND rerun-expand.sh can show the invocation
# in native shell syntax (`NAME=val NAME=val exe args...`), not cmake's own
# `-E env` spelling — that's what's actually copy-pasteable into zsh with a
# debugger prepended (e.g. `python3 -m pdb -m rigexp expand ...`). _rig_cmd
# (what execute_process actually runs) is composed FROM them.
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
  "# Re-runs cmake/dts.cmake's pass-1 expander invocation standalone (e.g. under"
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
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 4: context.cmake handoff.
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
# (RIG_NAME / RIG_BOARD / RIG_SHIELDS). Step 5 drives its Kconfig/bookkeeping
# loop over RIG_SHIELDS instead of -DSHIELD.
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
# Step 5: shield resolution (P3 3a rewrite of the stock shields.cmake tail).
#
# Unlike stock shields.cmake, shields here are never selected via -DSHIELD;
# they come from the rig's own instances (RIG_SHIELDS, set by context.cmake
# above). DT is entirely the expander's domain — it already emitted the
# overlay set (step 3's ${_rig_overlay}, handed off in step 7) — so this
# step's job is Kconfig + bookkeeping only:
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
#     it never runs for a rig build (the shields.cmake fork dispatches away
#     from it whenever -DRIG is set), so there is no double-overlay risk.
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

# Collect every candidate dir per shield name first (list_shields.py's own
# output is unfiltered stock-Zephyr content: BOARD_ROOT commonly contains
# BOTH btr-shields and the ZEPHYR_BASE tree it builds against, and a name
# collision is real -- e.g. zephyr-rigs ships its own stock
# boards/shields/adafruit_data_logger, a plain upstream shield with no
# <name>.shield rig-template marker, alongside btr-shields' rig-template
# shield of the same name). A single overwriting pass (last-wins) would
# silently resolve to whichever root happens to sort last, with no relation
# to which one is actually a rig template.
set(SHIELD_LIST)
if(shields_length GREATER 0)
  math(EXPR shields_length "${shields_length} - 1")

  foreach(i RANGE ${shields_length})
    string(JSON shield GET "${shields_json}" "${i}")
    string(JSON shield_name GET ${shield} name)
    string(JSON shield_dir GET ${shield} dir)
    if(NOT shield_name IN_LIST SHIELD_LIST)
      list(APPEND SHIELD_LIST ${shield_name})
    endif()
    list(APPEND _rig_shield_candidate_dirs_${shield_name} ${shield_dir})
  endforeach()
endif()
list(SORT SHIELD_LIST)

# Resolve each name's candidate(s) to ONE dir. Discovery rule (matches the
# expander's own `load_shield_library`, loader_yml.py): a folder is a rig
# TEMPLATE iff it holds `<name>.shield`, so on a collision that marker is
# what the expander actually used to build the overlay -- prefer it. A
# single dir needs no resolution; report an ambiguity (0 or >=2 marked
# candidates) so it's visible instead of silently picking whichever root
# came last.
foreach(shield_name ${SHIELD_LIST})
  set(_rig_shield_candidates ${_rig_shield_candidate_dirs_${shield_name}})
  list(REMOVE_DUPLICATES _rig_shield_candidates)
  list(LENGTH _rig_shield_candidates _rig_shield_ncand)
  if(_rig_shield_ncand EQUAL 1)
    list(GET _rig_shield_candidates 0 _rig_shield_chosen)
  else()
    set(_rig_shield_marked)
    foreach(_rig_shield_cand ${_rig_shield_candidates})
      if(EXISTS "${_rig_shield_cand}/${shield_name}.shield")
        list(APPEND _rig_shield_marked "${_rig_shield_cand}")
      endif()
    endforeach()
    list(LENGTH _rig_shield_marked _rig_shield_nmarked)
    if(_rig_shield_nmarked EQUAL 1)
      # Exactly one candidate is a rig template -- the unambiguous, expected
      # case for a same-named stock/rig-template collision. No warning.
      list(GET _rig_shield_marked 0 _rig_shield_chosen)
    else()
      # 0 or >=2 candidates carry the marker: genuinely ambiguous. Choose
      # deterministically (alphabetically first among the marked dirs if
      # any are marked, else alphabetically first among all candidates) and
      # say so loudly, naming every candidate.
      if(_rig_shield_nmarked GREATER 0)
        set(_rig_shield_pool ${_rig_shield_marked})
      else()
        set(_rig_shield_pool ${_rig_shield_candidates})
      endif()
      list(SORT _rig_shield_pool)
      list(GET _rig_shield_pool 0 _rig_shield_chosen)
      string(REPLACE ";" "\n  " _rig_shield_candidates_str "${_rig_shield_candidates}")
      if(_rig_shield_nmarked GREATER 0)
        set(_rig_shield_pool_desc "alphabetically first among the marked candidates")
      else()
        set(_rig_shield_pool_desc "alphabetically first among all candidates (none marked)")
      endif()
      message(WARNING
        "rig: shield name '${shield_name}' is offered by ${_rig_shield_ncand} "
        "different BOARD_ROOT directories, and ${_rig_shield_nmarked} of them "
        "carry the rig-template marker '${shield_name}.shield' (expected "
        "exactly 1):\n  ${_rig_shield_candidates_str}\n"
        "rig: choosing (${_rig_shield_pool_desc}): ${_rig_shield_chosen}")
    endif()
  endif()
  set(SHIELD_DIR_${shield_name} ${_rig_shield_chosen})
endforeach()

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

  # Provenance: which folder won for this shield name — non-obvious whenever
  # the rig-template-marker collision preference above had a choice to make.
  message(STATUS "rig: shield '${s}' <- ${SHIELD_DIR_${s}}")

  include(${SHIELD_DIR_${s}}/pre_dt_shield.cmake OPTIONAL)

  # Search for shield/shield.conf file (DT collection intentionally dropped —
  # the expander already emitted the overlay set, handed off in step 7).
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

# ---------------------------------------------------------------------------
# Step 6: pre_dt_module_run(), second run. SHIELD_DIRS is now known (step 5),
# so calling the function directly (NOT `include(pre_dt)` again -- its
# global include_guard already tripped in step 1 and would make a second
# include a silent no-op) recomputes DTS_ROOT / DTS_ROOT_SYSTEM_INCLUDE_DIRS
# for pass 2 with shield bindings folded in, exactly as a plain --shield
# build gets them. This is the amendment that retires the old saferail-13
# mirror: pre_dt_module_run() is a plain function, not include-guarded
# itself, so it can be called as many times as needed.
pre_dt_module_run()
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 7: overlay/conf handoff. DT and Kconfig ride DIFFERENT slots, and that
# asymmetry is deliberate, not an oversight: the expander is the SOLE author
# of DT (step 5's shield loop drops every shield's own `<name>.overlay`
# entirely), so the rig's own DT fragments have no existing slot to join and
# must PREPEND onto EXTRA_DTC_OVERLAY_FILE instead. Kconfig, by contrast, DOES
# have an existing slot every rig build already populates -- shield_conf_files
# (step 5) -- so the rig's own Kconfig fragments simply APPEND onto it, no
# separate prepend mechanism needed. Should the expander ever start
# authoring DT the shield loop currently drops (a rig-level shield overlay
# override), this asymmetry is the first thing to revisit.
#
# EXTRA_DTC_OVERLAY_FILE handoff (unchanged): by this point in the module
# chain (slot 17), configuration_files.cmake (slot 14) has already finalized
# EXTRA_DTC_OVERLAY_FILE as a plain variable (zephyr_get(... MERGE)), folding
# in any user `-DEXTRA_DTC_OVERLAY_FILE=`/`-DOVERLAY_CONFIG=`. A cache-FORCE
# write here would silently clobber that user value; instead we PREPEND our
# rig fragments onto the existing plain variable -- user extras WIN, since a
# user-passed value applies after all rig fragments (EXTRA_DTC_OVERLAY_FILE
# applies its files in list order, later files taking precedence) and can
# override them. Internal ordering: the expander's generated overlay first,
# then the rig folder's own hand-authored `<RIG>.overlay` (if present) --
# the DT counterpart of `<RIG>_defconfig`, a rig author supplying DT the
# expander cannot emit, notably the board pinctrl pinmux fragment a function
# needs to route on real silicon (R21 deep half): the expander only enables
# the controller (status="okay") and names the pin in the config sheet; it
# does not author SoC pinmux. Applied after the expander overlay so it can
# augment nodes the expander created.
set(_rig_overlay_files "${_rig_overlay}")
if(EXISTS "${_rig_user_overlay}")
  list(APPEND _rig_overlay_files "${_rig_user_overlay}")
  message(STATUS "rig: applying ${_rig_user_overlay}")
endif()
set(EXTRA_DTC_OVERLAY_FILE ${_rig_overlay_files} ${EXTRA_DTC_OVERLAY_FILE})

# shield_conf_files handoff: the expander's generated fragment (${_rig_conf},
# e.g. Kconfig facts derived from the topology) first, then the rig folder's
# own hand-authored `<RIG>_defconfig` (option A — the umbrella-subsystem
# activation layer a rig author writes so the instantiated shields' DRIVERS
# actually build; the expander cannot know this, it only knows topology) --
# appended onto shield_conf_files (step 5 populates it per shield; this adds
# the rig's OWN two fragments after every shield's own .conf, same relative
# order the old EXTRA_CONF_FILE prepend produced). No cache-FORCE risk here
# and no prepend of ours to get right: precedence instead falls out of
# upstream's own merge ordering (kconfig.cmake's `merge_config_files`:
# BOARD_DEFCONFIG -> BOARD_REVISION_CONFIG -> board_extension_conf_files ->
# CONF_FILE_AS_LIST (prj.conf) -> shield_conf_files -> EXTRA_CONF_FILE_AS_LIST
# -> EXTRA_KCONFIG_OPTIONS_FILE -> a glob of ${APPLICATION_BINARY_DIR}/*.conf,
# each slot's LATER files overriding earlier ones): the rig's fragments,
# riding the shield_conf_files slot, still land after prj.conf (the rig still
# overrides the app) and after every shield's own .conf (the rig still
# overrides shield type-level defaults) -- and because shield_conf_files is
# an EARLIER slot than EXTRA_CONF_FILE_AS_LIST, a user's own
# `-DEXTRA_CONF_FILE` still wins over the rig, with no prepend of ours
# enforcing it (test_tier2_goldens.py:test_tier2_user_extra_conf_wins_over_rig
# pins this). This fork no longer touches EXTRA_CONF_FILE at all.
if(EXISTS "${_rig_conf}")
  list(APPEND shield_conf_files "${_rig_conf}")
else()
  message(STATUS "rig: no Kconfig fragment produced")
endif()

if(EXISTS "${_rig_conf_file}")
  list(APPEND shield_conf_files "${_rig_conf_file}")
  message(STATUS "rig: applying ${_rig_conf_file}")
endif()
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 8: build-info provenance (rig-build provenance requirement): record
# what THIS rig build looked at, via zephyr's own build_info()
# (cmake/modules/extensions.cmake) — the same mechanism
# dts_build_info_output() (real dts.cmake, run via step 9's dts_init) uses
# for its own devicetree section. "rig" is not one of build-schema.yaml's own
# cmake.* tags, and that file is upstream (zephyr/scripts/schemas/
# build-schema.yaml) — not ours to extend — so this rides the schema's own
# downstream-owned escape hatch, `vendor-specific`, whose own schema entry is
# `cmake.vendor-specific.<key>.<subkey>: string` (exactly two levels, string
# leaves only). Verified empirically: this lands at
# cmake.vendor-specific.rig.* in build_info.yml, NOT the naively-expected
# cmake.rig.*. Multi-valued facts (shields, their resolved dirs) are JOINed
# into ONE string before the call: build_info()'s vendor-specific path always
# forces its underlying yaml_set() KEY type to VALUE (never LIST), and an
# un-joined CMake list silently truncates to its first element there
# (verified: a 2-shield rig recorded only the first shield until joined).
#
# Key names under `rig.*` never repeat the `rig` word themselves (`yml`, not
# `rig-yml`; `defconfig`/`overlay`, not `rig-conf`/`rig-overlay`) -- the
# nesting under `cmake.vendor-specific.rig.*` already scopes them, so a
# `rig-` prefix inside it would be redundant, and every OTHER key here
# (name/board/board-dts/shields/shield-dirs/out-dir) was already prefix-free.
# `defconfig`/`overlay` track the current hand-authored filenames
# (`<rigname>_defconfig`/`<rigname>.overlay`); the generated counterparts
# get their OWN keys (`defconfig-gen`/`overlay-gen`, mirroring the `-gen`
# infix the emitted `rig-gen.conf`/`rig-gen.overlay` filenames themselves
# carry) so a build stays fully self-describing without the reader needing
# to know those basenames are fixed. `overlay-gen` is unconditional (the
# expander always produces it, checked in step 3); `defconfig-gen` is
# EXISTS-guarded like the hand-authored keys, since the emitter does not yet
# ever produce `rig-gen.conf` (parked.md "Kconfig layering" -- the fourth
# emitter output is designed but unimplemented).
list(JOIN RIG_SHIELDS ", " _rig_shields_joined)
list(JOIN SHIELD_DIRS ", " _rig_shield_dirs_joined)

build_info(vendor-specific rig name VALUE "${RIG_NAME}")
build_info(vendor-specific rig board VALUE "${RIG_BOARD}")
build_info(vendor-specific rig yml VALUE "${_rig_yml}")
build_info(vendor-specific rig board-dts VALUE "${_rig_board_dts}")
build_info(vendor-specific rig shields VALUE "${_rig_shields_joined}")
build_info(vendor-specific rig shield-dirs VALUE "${_rig_shield_dirs_joined}")
build_info(vendor-specific rig out-dir VALUE "${_rig_out_dir}")
build_info(vendor-specific rig overlay-gen VALUE "${_rig_overlay}")
if(EXISTS "${_rig_conf}")
  build_info(vendor-specific rig defconfig-gen VALUE "${_rig_conf}")
endif()
if(EXISTS "${_rig_conf_file}")
  build_info(vendor-specific rig defconfig VALUE "${_rig_conf_file}")
endif()
if(EXISTS "${_rig_user_overlay}")
  build_info(vendor-specific rig overlay VALUE "${_rig_user_overlay}")
endif()
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 9: delegate to the real dts.cmake, last line. zephyr_default.cmake's
# module loop calls `dts_init` right after `include(dts)` returns (the
# `<module>_init` convention) — dts_init is defined by the real dts.cmake
# included here, so it is ready by the time control returns to that loop.
include(${ZEPHYR_BASE}/cmake/modules/dts.cmake)
# ---------------------------------------------------------------------------
