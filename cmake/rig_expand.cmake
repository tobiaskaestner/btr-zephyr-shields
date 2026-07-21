# rig_expand() — run the rigexp expander at configure time and feed its
# generated devicetree overlay (+ Kconfig fragment, once emitted) into the
# current Zephyr build.
#
# Extracted from the per-app ZephyrAppConfig.cmake so the seam logic lives in
# the module (btr-shields/cmake/) and any app can `include(rig_expand)` after
# adding this dir to CMAKE_MODULE_PATH.
#
# Self-locating: the module root is derived from THIS file's location
# (btr-shields/cmake/rig_expand.cmake -> root is one dir up), captured at
# include time. We cannot use ZEPHYR_<MODULE>_MODULE_DIR here because the
# ZephyrAppConfiguration hook that calls us runs BEFORE zephyr_module has
# processed module.yml.

set(_RIG_EXPAND_MODULE_DIR "${CMAKE_CURRENT_LIST_DIR}")
get_filename_component(_RIG_BTR_ROOT "${_RIG_EXPAND_MODULE_DIR}/.." ABSOLUTE)

# Overrideable knobs (callers/probe builds can substitute a stub).
set(RIG_EXPAND_PYTHON "/wrk/z/ws-up/.venv/bin/python"
  CACHE FILEPATH "Python interpreter used to run the rigexp expander")
set(RIG_EXPAND_PYTHONPATH "${_RIG_BTR_ROOT}/scripts"
  CACHE PATH "PYTHONPATH so 'python -m rigexp' finds btr-shields/scripts/rigexp")
set(RIG_EXPAND_SHIELD_DIR "${_RIG_BTR_ROOT}/boards/shields"
  CACHE PATH "--shield-dir passed to the rigexp expander")
set(RIG_EXPAND_COMMAND ""
  CACHE STRING "Override: full command (semicolon list) to run instead of the rigexp CLI")

# rig_expand(<rig-name>): resolve the rig, run the expander, wire the outputs.
function(rig_expand rig_name)
  set(rig_yml "${_RIG_BTR_ROOT}/boards/rigs/${rig_name}.rig.yml")
  if(NOT EXISTS "${rig_yml}")
    message(FATAL_ERROR
      "rig_expand: -DRIG=${rig_name} does not resolve to a rig file.\n"
      "  Expected: ${rig_yml}\n"
      "  (rigs live under ${_RIG_BTR_ROOT}/boards/rigs/<name>.rig.yml)")
  endif()

  set(out_dir "${CMAKE_BINARY_DIR}/rig")
  file(MAKE_DIRECTORY "${out_dir}")
  # The CLI writes the literal emitter keys into --out-dir: "overlay",
  # "config-sheet.md", "expectations.yml" (no rig-name prefix, no extension).
  set(overlay "${out_dir}/overlay")
  set(conf "${out_dir}/conf")

  if(RIG_EXPAND_COMMAND)
    set(cmd ${RIG_EXPAND_COMMAND})
  else()
    set(cmd
      "${CMAKE_COMMAND}" -E env "PYTHONPATH=${RIG_EXPAND_PYTHONPATH}"
      "${RIG_EXPAND_PYTHON}" -m rigexp expand "${rig_yml}"
      --shield-dir "${RIG_EXPAND_SHIELD_DIR}"
      --out-dir "${out_dir}")
  endif()

  message(STATUS "rig_expand: expanding ${rig_yml} -> ${out_dir}")
  execute_process(
    COMMAND ${cmd}
    RESULT_VARIABLE result
    OUTPUT_VARIABLE stdout
    ERROR_VARIABLE stderr)

  if(NOT result EQUAL 0)
    message(FATAL_ERROR
      "rig_expand: rigexp expand failed for -DRIG=${rig_name} (exit ${result})\n"
      "--- command ---\n${cmd}\n--- stdout ---\n${stdout}\n--- stderr ---\n${stderr}")
  endif()
  if(stdout OR stderr)
    message(STATUS "rig_expand: expander output:\n${stdout}${stderr}")
  endif()
  if(NOT EXISTS "${overlay}")
    message(FATAL_ERROR
      "rig_expand: expand reported success but wrote no overlay:\n  ${overlay}")
  endif()

  # Feed the generated files into this build.
  set(EXTRA_DTC_OVERLAY_FILE "${overlay}" CACHE STRING
    "Rig-generated devicetree overlay (set by rig_expand)" FORCE)
  if(EXISTS "${conf}")
    set(OVERLAY_CONFIG "${conf}" CACHE STRING
      "Rig-generated Kconfig fragment (set by rig_expand)" FORCE)
  else()
    message(STATUS "rig_expand: no Kconfig fragment produced (expected at P2)")
  endif()

  # Re-trigger configure when the rig file or the expander sources change.
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${rig_yml}")
  file(GLOB expander_sources "${_RIG_BTR_ROOT}/scripts/rigexp/*.py")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${expander_sources})
endfunction()
