"""cmake-alone rig entry: cmake -B <dir> -S <app> -DRIG=<name> -DBOARD=
<target> with west absent entirely must configure a build equivalent to
the west build-rig path. The rig and the board are INDEPENDENT
coordinates: the rig names a topology, the invocation names the board,
and neither is derived from the other.
SHIELD is still derived from the rig's own instances (cmake/shields.cmake's
fork).

This file covers the properties exercised entirely through direct cmake
invocations (no west subprocess at all):

  * a fresh cmake-alone configure resolves the same board target, a
    structurally-equivalent zephyr.dts, and the same rig provenance in
    build_info.yml (modulo the build directory itself) as west build-rig
    given the same two coordinates.
  * a rig with no -DBOARD is a configure-time FATAL_ERROR naming the rig
    and the missing flag -- and that is EVERY rig, since no corpus rig
    declares a board at all.
  * a promoted shield behaves identically on that point, with its own
    wording (a shield never had a board axis; a rig merely stopped having
    one), and the two messages stay distinguishable.
  * a qualified rig target (name@rev/variant) resolves its own axes
    across both entry points -- the RIG's revision/variant, orthogonal to
    the BOARD's own @rev/qualifiers.
  * SHIELD keeps its own exclusion: -DSHIELD alongside -DRIG on a fresh
    configure is a FATAL_ERROR (never a silent no-op); a plain --shield
    build (no RIG) is untouched.

No rig-swap guard exists, and none is needed: a rig declares no board of
its own, so swapping -DRIG in an existing build dir cannot change the
board at all -- there is nothing for a guard to protect against.
zephyr_check_cache(BOARD) only WARNS on a changed BOARD in an existing
build dir and silently reverts; a rig build is exactly as exposed to
that as any other Zephyr build.

All run a real CMake configure -- marked @pytest.mark.build;
CHECK_FAST=1 (scripts/check.sh) deselects them via pytest -m "not build".
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import yaml

from conftest import (
    DTS_EQUIV,
    FIXTURES_DIR,
    RIG_BOARD,
    WEST_EXE,
    WEST_TOPDIR,
    board_extra_defines,
    render_argv,
    subprocess_timeout,
    zephyr_base,
)

pytestmark = pytest.mark.build

# Relative to WEST_TOPDIR — any app works for a cmake-only configure;
# hello_world is the corpus's own reference app (see test_resolved_corpus.py).
_APP = "zephyr/samples/hello_world"

# nucleo_datalogger (nucleo_f401re/stm32f401xe/rig, a board EXTENSION) is
# this file's reference rig for the cmake-only entry tests.
_RIG = "nucleo_datalogger"


def _run_build_rig(rig_name: str, build_dir: Path,
                    extra_defines: Optional[List[str]] = None,
                    *, board: str) -> "subprocess.CompletedProcess[str]":
    """The reference path: west build-rig --cmake-only for one rig — same
    invocation shape as test_resolved_corpus.py's _run_build. extra_defines
    is threaded after --, e.g. the lotus board's
    -DEXTRA_ZEPHYR_MODULES=<bridle_root>.

    `board` is KEYWORD-ONLY and REQUIRED, which is the point: no
    rig declares one, so there is no such thing as "the board this rig
    would have picked". Making it required means a future test cannot
    quietly reintroduce the assumption by omitting it."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, "--board", board, _APP,
        "--cmake-only", "-p", "always", "-d", str(build_dir),
    ]
    if extra_defines:
        cmd += ["--", *extra_defines]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=dict(os.environ),
                           capture_output=True, text=True, timeout=subprocess_timeout(600))


def _cmake_alone_env() -> Dict[str, str]:
    """A subprocess environment with west unresolvable on PATH, so a build
    that succeeds here provably did not reach for west anywhere:
    strip the directory hosting the west console-script from PATH (in this
    venv layout nothing else needed by the build lives ONLY there — python3
    is passed explicitly instead, see _run_cmake_alone), leaving cmake/
    ninja/the toolchain reachable exactly as for any other build.

    west the PYTHON PACKAGE staying importable is irrelevant here: Zephyr
    module discovery (zephyr_module.py) resolves the workspace manifest via
    west's manifest API directly, never by shelling out to a west
    executable. This test's job is to prove the CMAKE-SIDE rig->board
    resolution (cmake/boards.cmake's fork + scripts/list_rigs.py) never
    shells out to west either — not to uninstall the west package from the
    interpreter, which no test here needs.
    """
    west_path = shutil.which("west")
    assert west_path is not None, (
        "west not found on PATH to begin with -- can't prove its absence "
        "means anything")
    west_dir = os.path.dirname(west_path)

    env = dict(os.environ)
    kept = [p for p in env.get("PATH", "").split(os.pathsep)
            if p and os.path.abspath(p) != os.path.abspath(west_dir)]
    env["PATH"] = os.pathsep.join(kept)
    assert shutil.which("west", path=env["PATH"]) is None, (
        "west is still resolvable after stripping its directory from PATH "
        "-- this venv's layout differs from what this test assumes "
        "(west + python3 living in the same bin/ dir)")
    env["ZEPHYR_BASE"] = zephyr_base()
    return env


def _cmake_alone_argv(build_dir: Path, extra_defines: list) -> list:
    """The bare cmake invocation a rig build must support: -S/-B, whatever
    coordinates the caller passes in extra_defines (always
    including -DBOARD -- nothing infers one), and an explicit
    -DPython3_EXECUTABLE (this venv's own
    interpreter) so CMake's Python discovery does not fall back to whatever a
    stripped PATH might still turn up — mirrors what west build itself
    effectively guarantees by setting WEST_PYTHON."""
    venv_python = WEST_TOPDIR / ".venv" / "bin" / "python3"
    app = str(WEST_TOPDIR / _APP)
    return [
        "cmake", "-S", app, "-B", str(build_dir),
        f"-DPython3_EXECUTABLE={venv_python}",
        *extra_defines,
        "-GNinja",
    ]


def _run_cmake_alone(build_dir: Path, extra_defines: list) -> "subprocess.CompletedProcess[str]":
    env = _cmake_alone_env()
    cmd = _cmake_alone_argv(build_dir, extra_defines)
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                           capture_output=True, text=True, timeout=subprocess_timeout(300))


def test_cmake_alone_entry_equivalent_to_build_rig(tmp_path: Path) -> None:
    """cmake -DRIG=<name> -DBOARD=<target> with west absent from PATH must
    resolve the SAME board target, a structurally-equivalent zephyr.dts,
    and the same rig provenance in build_info.yml (modulo the build
    directory's own path) as west build-rig --rig <name>."""
    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig(_RIG, reference_dir, board=RIG_BOARD[_RIG])
    assert result_ref.returncode == 0, (
        f"west build-rig --rig {_RIG} --cmake-only failed\n"
        f"--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, [f"-DRIG={_RIG}", f"-DBOARD={RIG_BOARD[_RIG]}"])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG={_RIG} (west absent) failed to configure\n"
        f"--- argv ---\n{render_argv(result_cmake)}\n--- stdout ---\n{result_cmake.stdout}\n--- stderr ---\n{result_cmake.stderr}")

    with open(reference_dir / "build_info.yml") as f:
        ref_info = yaml.safe_load(f)
    with open(cmake_dir / "build_info.yml") as f:
        cmake_info = yaml.safe_load(f)

    assert cmake_info["cmake"]["board"] == ref_info["cmake"]["board"], (
        "cmake-alone entry resolved a DIFFERENT board target than "
        "west build-rig")

    ref_rig = ref_info["cmake"]["vendor-specific"]["rig"]
    cmake_rig = cmake_info["cmake"]["vendor-specific"]["rig"]
    # out-dir is legitimately build-directory-specific; everything else
    # (name/board/yml/board-dts/shields/shield-dirs/defconfig) names the
    # SAME source-tree files regardless of entry point, so must match
    # byte-for-byte.
    for key in ("name", "board", "yml", "board-dts", "shields",
                "shield-dirs", "defconfig"):
        assert cmake_rig.get(key) == ref_rig.get(key), (
            f"rig provenance {key!r} differs between cmake-alone and "
            f"build-rig: {cmake_rig.get(key)!r} vs {ref_rig.get(key)!r}")

    ref_dts = reference_dir / "zephyr" / "zephyr.dts"
    cmake_dts = cmake_dir / "zephyr" / "zephyr.dts"
    assert ref_dts.is_file(), f"no zephyr.dts at {ref_dts}"
    assert cmake_dts.is_file(), f"no zephyr.dts at {cmake_dts}"

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(ref_dts), str(cmake_dts)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        "cmake-alone entry's zephyr.dts is not structurally equivalent to "
        f"the build-rig reference (dts_equiv.py):\n--- argv ---\n{render_argv(check)}\n{check.stdout}\n{check.stderr}")


def test_cmake_alone_board_rig_both_given_configures_with_given_board(
        tmp_path: Path) -> None:
    """BOARD is an independent coordinate: -DBOARD + -DRIG on a fresh
    configure CONFIGURES, and the GIVEN board is the one built. The
    value here MATCHES nucleo_datalogger's own board
    (nucleo_f401re/stm32f401xe/rig, passed back verbatim), so this must
    be indistinguishable from a bare -DRIG configure."""
    build_dir = tmp_path / "both-given"
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_RIG}", "-DBOARD=nucleo_f401re/stm32f401xe/rig",
    ])
    assert result.returncode == 0, (
        f"expected -DBOARD + -DRIG on a fresh configure to succeed\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")
    with open(build_dir / "build_info.yml") as f:
        info = yaml.safe_load(f)
    assert info["cmake"]["board"]["name"] == "nucleo_f401re"
    assert info["cmake"]["board"]["qualifiers"] == "stm32f401xe/rig"
    assert (info["cmake"]["vendor-specific"]["rig"]["board"]
            == "nucleo_f401re/stm32f401xe/rig")


# no_board_datalogger declares NO board: at all -- the same shape every
# corpus rig now shares. It stays useful as the file's canonical instance
# of "no board, no injection is fatal" -- see
# test_cmake_alone_no_board_declared_without_injection_is_fatal below.
# It lives in its OWN board_root, added via -DBOARD_ROOT alongside the
# module's default one
# (BOARD_ROOT is a zephyr_get(... MERGE ...) list -- verified empirically
# that an extra -DBOARD_ROOT augments rather than replaces the module's
# own, so the rig resolves from the fixture root while its shield
# (adafruit_data_logger) and both boards still resolve from btr-shields'
# own default root). Its content names the shared arduino_r3 socket
# alias (already present on both real boards' own devicetree) rather
# than a board-prefixed label, so the SAME rig resolves on either real
# board.
#
# ard_datalogger, the corpus's own dual-host rig, cannot serve as this
# cross-board falsifier: its per-variant sockets: maps are board-prefixed
# (nucleo_ard/frdm_ard), so crossing its OWN two declared variants to
# each OTHER's board fails at socket resolution (a real content/board
# mismatch, not a mechanism bug) -- it would make the falsifier assert a
# rejection instead of a clean build. Building the SAME boardless rig
# against two DIFFERENT real boards and asserting each build actually
# used the one it was given is at least as strong a falsifier as crossing
# a rig's own declared board would be.
_EXTRA_BOARD_ROOT = str(FIXTURES_DIR / "extra_board_root")
_NO_BOARD_RIG = "no_board_datalogger"


def test_cmake_alone_no_board_declared_without_injection_is_fatal(
        tmp_path: Path) -> None:
    """The "never neither unless injected" rule's negative half: with no
    -DBOARD given and no board declared, there is nothing to fall back
    to, so this is a configure-time FATAL_ERROR naming both the rig and
    the missing flag."""
    build_dir = tmp_path / "no-board-no-injection"
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_NO_BOARD_RIG}", f"-DBOARD_ROOT={_EXTRA_BOARD_ROOT}",
    ])
    assert result.returncode != 0, (
        f"expected -DRIG={_NO_BOARD_RIG} with no -DBOARD to FATAL, but "
        f"configure succeeded\n--- argv ---\n{render_argv(result)}")
    # Asserted against cmake's own OUTPUT only, never the argv: the argv
    # already contains -DRIG=no_board_datalogger and -DBOARD_ROOT=... (which
    # itself lowercases to a string containing "-dboard"), so a check
    # against `render_argv(result) + stdout + stderr` would pass even if
    # the FATAL never fired at all. "no board of its own to fall back to"
    # is OUR wording (no argv could ever contain it), but that alone is
    # STILL not enough: message(STATUS ...) prints the identical text
    # without stopping the configure, and cmake fails moments later anyway
    # at zephyr's own zephyr_check_cache(BOARD REQUIRED) ("BOARD is not
    # being defined ...") -- verified by replacing the FATAL_ERROR in
    # boards.cmake with a STATUS of the same wording: this rejection still
    # exits nonzero and still contains our phrase. The second assertion is
    # the actual discriminator: our FATAL_ERROR halts the configure before
    # that later, generic check ever runs, so its own wording must be
    # ABSENT -- confirmed empirically both ways (present under the STATUS
    # mutation, absent with the real FATAL_ERROR restored).
    output = result.stdout + result.stderr
    assert "no board of its own to fall back to" in output, output
    assert "BOARD is not being defined" not in output, output


def test_cmake_alone_board_injection_is_read_not_ignored(tmp_path: Path) -> None:
    """The real falsifier: building
    the SAME boardless rig with two DIFFERENT real -DBOARD values must
    configure BOTH times, and each build must have actually used the
    board it was given, not a constant or an ignored one -- proven by
    checking build_info.yml's own board fields diverge between the two
    runs exactly as the two -DBOARD values did. A no-op/ignored injection
    would either FATAL both times (nothing to fall back to) or use the
    SAME board regardless of which value was given; neither is
    consistent with what is asserted below."""
    nucleo_dir = tmp_path / "nucleo"
    nucleo = _run_cmake_alone(nucleo_dir, [
        f"-DRIG={_NO_BOARD_RIG}", f"-DBOARD_ROOT={_EXTRA_BOARD_ROOT}",
        "-DBOARD=nucleo_f401re/stm32f401xe/rig",
    ])
    assert nucleo.returncode == 0, (
        f"-DBOARD=nucleo_f401re/stm32f401xe/rig must configure\n"
        f"--- argv ---\n{render_argv(nucleo)}\n--- stdout ---\n{nucleo.stdout}\n"
        f"--- stderr ---\n{nucleo.stderr}")
    with open(nucleo_dir / "build_info.yml") as f:
        nucleo_info = yaml.safe_load(f)

    frdm_dir = tmp_path / "frdm"
    frdm = _run_cmake_alone(frdm_dir, [
        f"-DRIG={_NO_BOARD_RIG}", f"-DBOARD_ROOT={_EXTRA_BOARD_ROOT}",
        "-DBOARD=frdm_k64f/mk64f12/rig",
    ])
    assert frdm.returncode == 0, (
        f"-DBOARD=frdm_k64f/mk64f12/rig must configure\n"
        f"--- argv ---\n{render_argv(frdm)}\n--- stdout ---\n{frdm.stdout}\n"
        f"--- stderr ---\n{frdm.stderr}")
    with open(frdm_dir / "build_info.yml") as f:
        frdm_info = yaml.safe_load(f)

    assert nucleo_info["cmake"]["board"]["name"] == "nucleo_f401re"
    assert frdm_info["cmake"]["board"]["name"] == "frdm_k64f"
    assert (nucleo_info["cmake"]["vendor-specific"]["rig"]["board"]
            == "nucleo_f401re/stm32f401xe/rig")
    assert (frdm_info["cmake"]["vendor-specific"]["rig"]["board"]
            == "frdm_k64f/mk64f12/rig")


def test_cmake_alone_qualified_target_resolves(tmp_path: Path) -> None:
    """End-to-end at the cmake-alone entry
    point specifically (not just west build-rig): a FULLY qualified target
    (name@rev/variant) must resolve to the SAME board and rig provenance
    (including the SELECTED revision/variant themselves, and the applied
    fragment list) as west build-rig with the identical target string --
    same shape as test_cmake_alone_entry_equivalent_to_build_rig, but
    proving the qualifier axes specifically survive both entry points."""
    target = "pilot_variants@2/variant_b"
    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig(target, reference_dir, board=RIG_BOARD["pilot_variants"])
    assert result_ref.returncode == 0, (
        f"west build-rig --rig {target} --cmake-only failed\n"
        f"--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, [f"-DRIG={target}",
                                 f'-DBOARD={RIG_BOARD["pilot_variants"]}'])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG={target} (west absent) failed to configure\n"
        f"--- argv ---\n{render_argv(result_cmake)}\n--- stdout ---\n{result_cmake.stdout}\n--- stderr ---\n{result_cmake.stderr}")

    with open(reference_dir / "build_info.yml") as f:
        ref_info = yaml.safe_load(f)
    with open(cmake_dir / "build_info.yml") as f:
        cmake_info = yaml.safe_load(f)

    ref_rig = ref_info["cmake"]["vendor-specific"]["rig"]
    cmake_rig = cmake_info["cmake"]["vendor-specific"]["rig"]
    for key in ("name", "board", "revision", "variant", "fragments"):
        assert cmake_rig.get(key) == ref_rig.get(key), (
            f"rig provenance {key!r} differs between cmake-alone and "
            f"build-rig: {cmake_rig.get(key)!r} vs {ref_rig.get(key)!r}")
    assert ref_rig["revision"] == "2"
    assert ref_rig["variant"] == "variant_b"


def test_cmake_alone_qualified_rig_target_against_undeclared_axis_rejected(
        tmp_path: Path) -> None:
    """Qualifiers RESOLVE — list_rigs.py's
    own resolve_rig_target validates a selected axis against the rig's OWN
    declarations, so a qualifier against nucleo_datalogger (which declares
    NEITHER axis) is rejected with the declares-no-such-axis wording,
    reached all the way through a real cmake-alone configure (the
    qualified-pilot-build resolved tests exercise the ACCEPT half of this
    same resolution path)."""
    build_dir = tmp_path / "qualified-revision"
    result = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}@1"])
    assert result.returncode != 0
    combined = f"{render_argv(result)}\n" + result.stdout + result.stderr
    assert "declares no revision" in combined, combined

    build_dir = tmp_path / "qualified-variant"
    result = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}/foo"])
    assert result.returncode != 0
    combined = f"{render_argv(result)}\n" + result.stdout + result.stderr
    assert "declares no variants" in combined, combined


def test_cmake_alone_shield_rig_both_given_is_fatal(tmp_path: Path) -> None:
    """SHIELD gets the same exclusion as BOARD: -DSHIELD alongside -DRIG
    on a fresh configure is a FATAL_ERROR from the shields.cmake fork, never
    a silent no-op -- the dts.cmake fork's rig block unconditionally
    overwrites SHIELD_AS_LIST from the rig's own instances, so a
    user-passed -DSHIELD would otherwise vanish with no diagnostic.
    adafruit_data_logger is the shield nucleo_datalogger's own instance
    already names."""
    build_dir = tmp_path / "shield-rig-clash"
    # -DBOARD is given so the configure actually REACHES the shields.cmake
    # fork: boards.cmake FATALs on a missing board first, and
    # without a board this test would pass on the wrong diagnostic
    # entirely -- asserting SHIELD/RIG exclusion while really observing
    # "no -DBOARD was given".
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_RIG}", f"-DBOARD={RIG_BOARD[_RIG]}",
        "-DSHIELD=adafruit_data_logger",
    ])
    assert result.returncode != 0, (
        "expected -DSHIELD + -DRIG on a fresh configure to FATAL, but "
        "configure succeeded")
    combined = f"{render_argv(result)}\n" + result.stdout + result.stderr
    assert "adafruit_data_logger" in combined, combined
    assert _RIG in combined, combined
    assert "come from the rig" in combined, combined


def test_cmake_alone_plain_shield_build_untouched(tmp_path: Path) -> None:
    """The other half of the SHIELD/RIG exclusion: a plain --shield build
    (no -DRIG at all) must be completely untouched by the guard above -- it
    never even reads SHIELD in that branch (the real shields.cmake module
    owns it, via the unconditional include() in the fork's else())."""
    build_dir = tmp_path / "plain-shield"
    venv_python = WEST_TOPDIR / ".venv" / "bin" / "python3"
    env = _cmake_alone_env()
    cmd = [
        "cmake", "-S", str(WEST_TOPDIR / _APP), "-B", str(build_dir),
        f"-DPython3_EXECUTABLE={venv_python}",
        "-DBOARD=nucleo_f401re/stm32f401xe/rig",
        "-DSHIELD=adafruit_data_logger",
        "-GNinja",
    ]
    result = subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                             capture_output=True, text=True, timeout=subprocess_timeout(300))
    assert result.returncode == 0, (
        "a plain (no -DRIG) --shield-equivalent configure must remain "
        f"untouched\n--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")


def test_cmake_alone_lotus_needs_bridle_module(tmp_path: Path) -> None:
    """The DOCUMENTED failure mode: cmake -DRIG=lotus_pwm WITHOUT
    -DEXTRA_ZEPHYR_MODULES=<bridle> must fail. seeeduino_lotus/samd21g18a/rig's
    base board lives entirely in the bridle Zephyr module, which the west
    manifest does NOT carry -- without the module define, hwmv2 board
    discovery never sees bridle's board_root, so the board plainly does not
    exist. This is the accepted cost of keeping bridle out of the manifest,
    not something to fix."""
    build_dir = tmp_path / "lotus-no-module"
    result = _run_cmake_alone(build_dir, ["-DRIG=lotus_pwm",
                                          f'-DBOARD={RIG_BOARD["lotus_pwm"]}'])
    assert result.returncode != 0, (
        "expected cmake -DRIG=lotus_pwm WITHOUT -DEXTRA_ZEPHYR_MODULES to "
        "fail (seeeduino_lotus does not exist without bridle's board_root)\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")
    combined = f"{render_argv(result)}\n" + result.stdout + result.stderr
    assert "seeeduino_lotus" in combined, combined


def test_cmake_alone_lotus_with_bridle_module_configures(tmp_path: Path) -> None:
    """cmake-alone, west-free, WITH -DEXTRA_ZEPHYR_MODULES=<bridle_root>
    must configure clean and resolve the SAME cross-module extension target
    as west build-rig with the identical define threaded (same shape as
    test_cmake_alone_entry_equivalent_to_build_rig, a same-module board)."""
    extra = board_extra_defines(RIG_BOARD["lotus_pwm"])
    assert extra, "lotus_pwm's board must need EXTRA_ZEPHYR_MODULES (bridle)"

    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig("lotus_pwm", reference_dir, extra, board=RIG_BOARD["lotus_pwm"])
    assert result_ref.returncode == 0, (
        f"west build-rig --rig lotus_pwm --cmake-only (with bridle module) "
        f"failed\n--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n"
        f"--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, ["-DRIG=lotus_pwm",
                                          f'-DBOARD={RIG_BOARD["lotus_pwm"]}', *extra])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG=lotus_pwm {' '.join(extra)} (west absent) "
        f"failed to configure\n--- argv ---\n{render_argv(result_cmake)}\n--- stdout ---\n{result_cmake.stdout}\n"
        f"--- stderr ---\n{result_cmake.stderr}")

    with open(reference_dir / "build_info.yml") as f:
        ref_info = yaml.safe_load(f)
    with open(cmake_dir / "build_info.yml") as f:
        cmake_info = yaml.safe_load(f)

    assert cmake_info["cmake"]["board"] == ref_info["cmake"]["board"], (
        "cmake-alone entry resolved a DIFFERENT board target than "
        f"west build-rig: {cmake_info['cmake']['board']!r} vs "
        f"{ref_info['cmake']['board']!r}")
    assert ref_info["cmake"]["board"]["name"] == "seeeduino_lotus"
    assert ref_info["cmake"]["board"]["qualifiers"] == "samd21g18a/rig"

    ref_dts = reference_dir / "zephyr" / "zephyr.dts"
    cmake_dts = cmake_dir / "zephyr" / "zephyr.dts"
    assert ref_dts.is_file(), f"no zephyr.dts at {ref_dts}"
    assert cmake_dts.is_file(), f"no zephyr.dts at {cmake_dts}"

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(ref_dts), str(cmake_dts)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        "cmake-alone lotus_pwm's zephyr.dts is not structurally equivalent "
        f"to the build-rig reference (dts_equiv.py):\n--- argv ---\n{render_argv(check)}\n{check.stdout}\n{check.stderr}")


# ---------------------------------------------------------- promoted shield
#
# A -DRIG that names a SHIELD rather than a rig
# folder, and without these tests it is guarded by nothing: every other test
# in this file names a real rig, so a regression that broke promotion
# alone would leave the whole suite green.


@pytest.mark.build
def test_cmake_alone_promoted_shield_configures_with_a_given_board(
        tmp_path: Path) -> None:
    """-DRIG naming a SHIELD configures, given a board.
    adafruit_data_logger plugs arduino-r3 and nucleo's rig extension
    declares exactly one socket of that type, so the socket resolves by
    inference with nothing named -- the promoted form has no socket: to
    name.

    Asserted through build_info rather than the exit code alone: a
    configure that succeeded while silently building something else is
    the failure this is really guarding against, so the board actually
    built and the promoted-shield provenance key are both checked."""
    build_dir = tmp_path / "promoted"
    result = _run_cmake_alone(build_dir, [
        "-DRIG=adafruit_data_logger",
        "-DBOARD=nucleo_f401re/stm32f401xe/rig",
    ])
    assert result.returncode == 0, (
        "expected -DRIG=<shield> + -DBOARD to configure\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        info = yaml.safe_load(f)
    rig_info = info["cmake"]["vendor-specific"]["rig"]
    assert rig_info["promoted-shield"] == "adafruit_data_logger"
    assert rig_info["board"] == "nucleo_f401re/stm32f401xe/rig"
    assert "adafruit_data_logger" in rig_info["shields"]
    # No rig folder exists, so neither rig-folder provenance key is
    # recorded -- the discriminator between a promoted target and a
    # same-named rig that happened to resolve.
    assert "yml" not in rig_info
    assert "content-yml" not in rig_info


@pytest.mark.build
def test_cmake_alone_promoted_shield_with_a_socket_configures_where_the_bare_form_cannot(
        tmp_path: Path) -> None:
    """The promotion-option grammar through the REAL cmake seam, which is
    the only place it can be falsified end to end: `{PROMOTED}` carries
    the whole target string and dts.cmake forwards it to `--promote`
    opaquely, so nothing between list_rigs and rigc parses it twice. A
    unit test of the parser cannot see that plumbing at all.

    flash_click plugs mikrobus and mikroe_quail offers FOUR, so inference
    is RIGHT to refuse the bare form -- asserted here as the paired
    control, in the same run and on the same board. Either half alone is
    weak: a socket silently ignored would still let the bare case fail
    and, without the second assertion, nothing would notice that the
    socketed case failed for the very same reason."""
    bare = _run_cmake_alone(tmp_path / "bare", [
        "-DRIG=flash_click",
        "-DBOARD=mikroe_quail/stm32f427xx/rig",
    ])
    assert bare.returncode != 0, (
        "flash_click has four candidate mikrobus sockets on quail; the "
        "bare promoted form must still be refused, or the control below "
        f"proves nothing\n--- stdout ---\n{bare.stdout}")
    assert "phys-socket" in bare.stdout + bare.stderr

    build_dir = tmp_path / "socketed"
    result = _run_cmake_alone(build_dir, [
        "-DRIG=flash_click:socket=quail_sock1",
        "-DBOARD=mikroe_quail/stm32f427xx/rig",
    ])
    assert result.returncode == 0, (
        "expected -DRIG=<shield>:socket=<label> to configure\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        info = yaml.safe_load(f)
    rig_info = info["cmake"]["vendor-specific"]["rig"]
    # The WHOLE target, options included: build_info records what was
    # asked for, which is what makes a build reproducible from it.
    assert rig_info["promoted-shield"] == "flash_click:socket=quail_sock1"
    assert rig_info["board"] == "mikroe_quail/stm32f427xx/rig"
    assert "flash_click" in rig_info["shields"]

    # The socket actually reached the emitted overlay -- a configure that
    # succeeded against the wrong socket would satisfy everything above.
    overlay = (build_dir / "rig" / "rig-gen.overlay").read_text()
    assert "quail_sock1" in overlay
    for other in ("quail_sock2", "quail_sock3", "quail_sock4"):
        assert other not in overlay


@pytest.mark.build
def test_cmake_alone_list_target_configures_with_both_shields(
        tmp_path: Path) -> None:
    """The module observing the cmake-
    list hazard, with its own list-target case: `-DRIG='a;b'` carries a
    literal `;` all the way from the invocation, through list_rigs.py's
    own `--rig=` resolution (boards.cmake's Step 1) and its `{PROMOTED}`
    cmakeformat value, to dts.cmake's `--promote` forwarding into the
    real expander subprocess -- EVERY hop an unquoted expansion could
    silently corrupt. A configure that succeeds
    and lands BOTH shields' own labels in the emitted overlay is the
    only proof that the whole chain carried the value intact rather than
    truncating it at the first embedded `;`."""
    raw = "eth_click:socket=quail_sock1;flash_click:socket=quail_sock2"
    build_dir = tmp_path / "list-target"
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={raw}",
        "-DBOARD=mikroe_quail/stm32f427xx/rig",
    ])
    assert result.returncode == 0, (
        "expected -DRIG='<shield-a>;<shield-b>' to configure\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        info = yaml.safe_load(f)
    rig_info = info["cmake"]["vendor-specific"]["rig"]
    # The WHOLE raw target, `;` intact -- build_info records what was
    # asked for, which is exactly the value a corrupted cmake seam would
    # have truncated at the first shield.
    assert rig_info["promoted-shield"] == raw
    assert rig_info["board"] == "mikroe_quail/stm32f427xx/rig"
    assert "eth_click" in rig_info["shields"]
    assert "flash_click" in rig_info["shields"]
    assert "yml" not in rig_info
    assert "content-yml" not in rig_info

    # Both shields' own instance labels, and both named sockets, reached
    # the emitted overlay -- a configure that silently dropped the
    # second element would satisfy every assertion above (build_info's
    # own "shields" key comes from RIG_SHIELDS, populated by context.cmake
    # off the LOADED rig -- a real end-to-end signal, not an echo of RIG).
    overlay = (build_dir / "rig" / "rig-gen.overlay").read_text()
    assert "eth_click" in overlay
    assert "flash_click" in overlay
    assert "quail_sock1" in overlay
    assert "quail_sock2" in overlay


def test_cmake_alone_promoted_shield_without_a_board_is_fatal(
        tmp_path: Path) -> None:
    """A promoted shield declares no board and has no axis
    to fall back to, so omitting -DBOARD must FATAL rather than guess.

    The assertion names the SHIELD wording specifically, not just any
    failure: a boardless RIG reaches a differently-worded FATAL two
    branches away in the same if/elseif chain, and a test satisfied by
    either would not notice the two collapsing into one."""
    build_dir = tmp_path / "promoted-no-board"
    result = _run_cmake_alone(build_dir, ["-DRIG=adafruit_data_logger"])
    assert result.returncode != 0, (
        "expected -DRIG=<shield> with no -DBOARD to fail\n"
        f"--- argv ---\n{render_argv(result)}\n--- stdout ---\n{result.stdout}")
    combined = result.stdout + result.stderr
    assert "names the shield 'adafruit_data_logger'" in combined, (
        "the FATAL did not identify the target as a shield -- a boardless "
        "rig's own wording would be wrong here\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")
    assert "no -DBOARD was given" in combined


# ---------------------------------------------------------- singleton identity law
#
# The ONE build-marked cross-check
# the singleton law needs -- expand-level equality (test_singleton_
# identity_law.py) does not prove the cmake/dts.cmake path feeds the
# analyzer the same thing, and the promoted branch through dts.cmake needs
# its own coverage. One shield is enough here; the census belongs at
# expand level, where it is cheap.

_SINGLETON_LAW_BOARD_ROOT = str(FIXTURES_DIR / "singleton_law_board_root")
_SINGLETON_LAW_RIG = "singleton_law_check"
_SINGLETON_LAW_SHIELD = "adafruit_data_logger"
_SINGLETON_LAW_BOARD = "nucleo_f401re/stm32f401xe/rig"


@pytest.mark.build
def test_cmake_alone_singleton_law_promoted_matches_fixture_rig_build(
        tmp_path: Path) -> None:
    """A promoted adafruit_data_logger build and a fixture rig build
    containing the IDENTICAL topology (one socket-less instance named
    after the shield, the promoted form's own
    convention) must produce a structurally equivalent zephyr.dts.
    Deliberately DIFFERENT rig names: zephyr.dts carries no rig
    name at all, so unlike the expand-level law this half needs no path
    trick to dodge the both-paths namespace rule -- naming the fixture
    rig 'adafruit_data_logger' would collide with the real shield of that
    name in this module's own default board root once
    _SINGLETON_LAW_BOARD_ROOT is added alongside it via -DBOARD_ROOT)."""
    promoted_dir = tmp_path / "promoted"
    promoted = _run_cmake_alone(promoted_dir, [
        f"-DRIG={_SINGLETON_LAW_SHIELD}", f"-DBOARD={_SINGLETON_LAW_BOARD}",
    ])
    assert promoted.returncode == 0, (
        f"promoted {_SINGLETON_LAW_SHIELD} build failed to configure\n"
        f"--- argv ---\n{render_argv(promoted)}\n--- stdout ---\n{promoted.stdout}\n"
        f"--- stderr ---\n{promoted.stderr}")

    fixture_dir = tmp_path / "fixture"
    fixture = _run_cmake_alone(fixture_dir, [
        f"-DRIG={_SINGLETON_LAW_RIG}",
        f"-DBOARD_ROOT={_SINGLETON_LAW_BOARD_ROOT}",
        f"-DBOARD={_SINGLETON_LAW_BOARD}",
    ])
    assert fixture.returncode == 0, (
        f"fixture rig {_SINGLETON_LAW_RIG} build failed to configure\n"
        f"--- argv ---\n{render_argv(fixture)}\n--- stdout ---\n{fixture.stdout}\n"
        f"--- stderr ---\n{fixture.stderr}")

    promoted_dts = promoted_dir / "zephyr" / "zephyr.dts"
    fixture_dts = fixture_dir / "zephyr" / "zephyr.dts"
    assert promoted_dts.is_file(), f"no zephyr.dts at {promoted_dts}"
    assert fixture_dts.is_file(), f"no zephyr.dts at {fixture_dts}"

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(fixture_dts), str(promoted_dts)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        "the singleton identity law's build-marked cross-check failed: "
        f"promoted {_SINGLETON_LAW_SHIELD} is not structurally equivalent "
        f"to the fixture rig's own build (dts_equiv.py):\n--- argv ---\n"
        f"{render_argv(check)}\n{check.stdout}\n{check.stderr}")

    # NEGATIVE CONTROL, and it costs no extra configure -- it perturbs the
    # zephyr.dts already built above. Without it this test would pass
    # identically against a dts_equiv that had stopped discriminating (an
    # unreadable file, a comparator gutted to return 0), which is the one
    # failure mode a pure equality assertion structurally cannot see: the
    # project has found that shape -- "a guard that passes while enforcing
    # less than it claims" -- in every review round it ran.
    #
    # The perturbation must be a real devicetree fact on a NON-ROOT node.
    # dts_equiv ignores comments, formatting, labels, phandle numbering
    # and node ordering by design, and its own docstring excludes the root
    # node outright -- an added root property is invisible to it, verified,
    # so a control built on one would itself prove nothing. Disabling the
    # first enabled node is a fact it does compare.
    perturbed = tmp_path / "perturbed.dts"
    promoted_text = promoted_dts.read_text()
    assert 'status = "okay";' in promoted_text, (
        "no enabled node in the promoted zephyr.dts to perturb -- this "
        "control needs a real devicetree fact to change; pick another "
        "rather than dropping it")
    perturbed.write_text(
        promoted_text.replace('status = "okay";', 'status = "disabled";', 1))
    control = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(fixture_dts), str(perturbed)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert control.returncode != 0, (
        "dts_equiv.py reported a perturbed zephyr.dts (first enabled node "
        "disabled) as EQUIVALENT to the fixture rig's build -- so the "
        "equality assertion above proves nothing about this input. Fix the "
        f"comparator, never this control.\n--- argv ---\n"
        f"{render_argv(control)}\n{control.stdout}\n{control.stderr}")
