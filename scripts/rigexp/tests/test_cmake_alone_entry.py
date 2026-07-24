"""cmake-alone rig entry (claude/rigs/cmake-alone-rig-entry-brief.md,
ratified 2026-07-24, design rules 3/4 amended same day to mutual
exclusivity): `cmake -B <dir> -S <app> -DRIG=<name>` with NO `-DBOARD` and
west absent entirely must configure a build equivalent to the `west
build-rig` path — the rig is the primary build coordinate, BOARD (and
SHIELD) are derived from it (`cmake/boards.cmake` / `cmake/shields.cmake`'s
forks), never a separate coordinate the user also supplies.

This file covers the acceptance criteria exercised entirely through direct
`cmake` invocations (no `west` subprocess at all):

  * criterion 2 -- a fresh cmake-alone configure resolves the SAME board
    target, a structurally-equivalent `zephyr.dts`, and the same rig
    provenance in `build_info.yml` (modulo the build directory itself) as
    `west build-rig`.
  * criterion 3 -- RIG and BOARD are mutually exclusive: a fresh configure
    with BOTH given is a configure-time FATAL_ERROR regardless of whether
    the values agree (BOARD is derived data, never a separate coordinate);
    a RECONFIGURE of an existing rig build dir (BOARD cache-carried from our
    own earlier inference, not user-passed) proceeds.
  * criterion 4 -- a qualified rig target (`name@rev` / `name/variant`) gets
    a loud not-yet-supported diagnostic from the resolver (V1/V2 placeholder).
  * criterion 7 -- SHIELD gets the same exclusion: `-DSHIELD` alongside
    `-DRIG` on a fresh configure is a FATAL_ERROR (previously a SILENT
    no-op); a plain `--shield` build (no RIG) is untouched.

All run a real CMake configure -- marked `@pytest.mark.build`; `CHECK_FAST=1`
(scripts/check.sh) deselects them via `pytest -m "not build"`.
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
    WEST_EXE,
    WEST_TOPDIR,
    board_extra_defines,
    rig_board_name,
    zephyr_base,
)

pytestmark = pytest.mark.build

# Relative to WEST_TOPDIR — any app works for a cmake-only configure;
# hello_world is the corpus's own reference app (see test_tier2_goldens.py).
_APP = "zephyr/samples/hello_world"

# nucleo-datalogger (E1 extension target, nucleo_f401re/stm32f401xe/rig) is
# the corpus rig this brief's own examples use for the cmake-only entry.
_RIG = "nucleo-datalogger"


def _run_build_rig(rig_name: str, build_dir: Path,
                    extra_defines: Optional[List[str]] = None) -> "subprocess.CompletedProcess[str]":
    """The reference path: `west build-rig --cmake-only` for one rig — same
    invocation shape as test_tier2_goldens.py's `_run_build`. `extra_defines`
    (E3-brief.md) is threaded after `--`, e.g. the lotus board's
    `-DEXTRA_ZEPHYR_MODULES=<bridle_root>`."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, _APP,
        "--cmake-only", "-p", "always", "-d", str(build_dir),
    ]
    if extra_defines:
        cmd += ["--", *extra_defines]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=dict(os.environ),
                           capture_output=True, text=True, timeout=600)


def _cmake_alone_env() -> Dict[str, str]:
    """A subprocess environment with `west` unresolvable on PATH — the literal
    reading of acceptance criterion 2 ("no west on PATH for the invocation"):
    strip the directory hosting the `west` console-script from PATH (in this
    venv layout nothing else needed by the build lives ONLY there — `python3`
    is passed explicitly instead, see `_run_cmake_alone`), leaving cmake/
    ninja/the toolchain reachable exactly as for any other build.

    `west` the PYTHON PACKAGE staying importable is irrelevant here: Zephyr
    module discovery (zephyr_module.py) resolves the workspace manifest via
    west's manifest API directly, never by shelling out to a `west`
    executable. This test's job is to prove the CMAKE-SIDE rig->board
    resolution (cmake/boards.cmake's fork + scripts/list_rigs.py) never
    shells out to `west` either — not to uninstall the west package from the
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
    """The bare `cmake` invocation acceptance criterion 2 requires: `-S`/`-B`,
    NO `-DBOARD`, and an explicit `-DPython3_EXECUTABLE` (this venv's own
    interpreter) so CMake's Python discovery does not fall back to whatever a
    stripped PATH might still turn up — mirrors what `west build` itself
    effectively guarantees by setting `WEST_PYTHON`."""
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
                           capture_output=True, text=True, timeout=300)


def test_cmake_alone_entry_equivalent_to_build_rig(tmp_path: Path) -> None:
    """Criterion 2: `cmake -DRIG=<name>` alone (no -DBOARD, west absent from
    PATH) must resolve the SAME board target, a structurally-equivalent
    `zephyr.dts`, and the same rig provenance in `build_info.yml` (modulo the
    build directory's own path) as `west build-rig --rig <name>`."""
    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig(_RIG, reference_dir)
    assert result_ref.returncode == 0, (
        f"west build-rig --rig {_RIG} --cmake-only failed\n"
        f"--- stdout ---\n{result_ref.stdout}\n--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, [f"-DRIG={_RIG}"])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG={_RIG} (no -DBOARD, west absent) failed to configure\n"
        f"--- stdout ---\n{result_cmake.stdout}\n--- stderr ---\n{result_cmake.stderr}")

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
    # (name/board/rig-yml/board-dts/shields/shield-dirs/rig-conf) names the
    # SAME source-tree files regardless of entry point, so must match
    # byte-for-byte.
    for key in ("name", "board", "rig-yml", "board-dts", "shields",
                "shield-dirs", "rig-conf"):
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
        f"the build-rig reference (dts_equiv.py):\n{check.stdout}\n{check.stderr}")


def test_cmake_alone_board_rig_both_given_is_fatal(tmp_path: Path) -> None:
    """Criterion 3: RIG and BOARD are mutually exclusive on a FRESH configure
    -- FATAL even when the value MATCHES the rig's own board exactly
    (nucleo-datalogger's board is nucleo_f401re/stm32f401xe/rig, passed back
    verbatim here), because BOARD is derived data of the rig coordinate, not
    a separate one the user may also supply (design rule 3, amended
    2026-07-24 -- supersedes an earlier mismatch-only check)."""
    build_dir = tmp_path / "both-given"
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_RIG}", "-DBOARD=nucleo_f401re/stm32f401xe/rig",
    ])
    assert result.returncode != 0, (
        "expected -DBOARD + -DRIG on a fresh configure to FATAL (even a "
        "matching value), but configure succeeded")
    combined = result.stdout + result.stderr
    assert "both given" in combined, combined
    assert _RIG in combined, combined
    assert "drop -dboard" in combined.lower(), combined


def test_cmake_alone_reconfigure_of_rig_build_dir_proceeds(tmp_path: Path) -> None:
    """Criterion 3, the other half: a RECONFIGURE of an EXISTING rig build
    dir must proceed even though BOARD is `DEFINED` on the second cmake
    invocation -- it is cache-carried from OUR OWN inference on the first
    configure (recorded via the `RIG_INFERRED_BOARD` marker), never a
    user-passed value the second time around. Reruns cmake against the SAME
    build dir with no -D flags at all, exactly like an incremental `west
    build`/`ninja` would trigger."""
    build_dir = tmp_path / "reconfigure"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", str(build_dir)], cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=300)
    assert second.returncode == 0, (
        "reconfigure of an existing rig build dir (no -D flags repeated) "
        "must proceed -- BOARD is legitimately cache-carried from our own "
        f"earlier inference\n--- stdout ---\n{second.stdout}\n"
        f"--- stderr ---\n{second.stderr}")


def test_cmake_alone_qualified_rig_target_rejected(tmp_path: Path) -> None:
    """Criterion 4: a qualified target (@rev or /variant) gets a loud
    not-yet-supported diagnostic from the resolver — a placeholder until
    V1/V2, never silent/partial resolution."""
    build_dir = tmp_path / "qualified-revision"
    result = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}@1"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "not yet supported" in combined, combined
    assert "revision" in combined, combined

    build_dir = tmp_path / "qualified-variant"
    result = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}/foo"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "not yet supported" in combined, combined
    assert "variant" in combined, combined


def test_cmake_alone_shield_rig_both_given_is_fatal(tmp_path: Path) -> None:
    """Criterion 7: SHIELD gets the same exclusion as BOARD (design rule 4,
    ratified 2026-07-24) -- `-DSHIELD` alongside `-DRIG` on a fresh configure
    is a FATAL_ERROR from the shields.cmake fork, never the SILENT no-op it
    used to be (that fork's early-exit never looked at SHIELD at all, and
    the dts.cmake fork's rig block unconditionally overwrites
    SHIELD_AS_LIST from the rig's own instances). adafruit_data_logger is
    the shield nucleo-datalogger's own s1 instance already names."""
    build_dir = tmp_path / "shield-rig-clash"
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_RIG}", "-DSHIELD=adafruit_data_logger",
    ])
    assert result.returncode != 0, (
        "expected -DSHIELD + -DRIG on a fresh configure to FATAL, but "
        "configure succeeded")
    combined = result.stdout + result.stderr
    assert "adafruit_data_logger" in combined, combined
    assert _RIG in combined, combined
    assert "come from the rig" in combined, combined


def test_cmake_alone_plain_shield_build_untouched(tmp_path: Path) -> None:
    """Criterion 7, the other half: a plain `--shield` build (no -DRIG at
    all) must be completely untouched by the new guard -- it never even
    reads SHIELD in that branch (the real shields.cmake module owns it, via
    the unconditional `include()` in the fork's `else()`)."""
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
                             capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, (
        "a plain (no -DRIG) --shield-equivalent configure must remain "
        f"untouched\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")


def test_cmake_alone_rig_swap_to_other_board_is_fatal(tmp_path: Path) -> None:
    """Rig-swap guard (review finding on this slice, verified live before the
    fix): changing -DRIG in an EXISTING build dir to a rig on a DIFFERENT
    board must FATAL at the boards.cmake fork. Without the guard, the stale
    cache-carried BOARD passes the exclusivity check (it equals the marker --
    both are the OLD rig's inference), inference is skipped, and the expander
    reads the OLD board's dts under the NEW rig's declared board name --
    phys-socket diagnostics blaming the wrong board, or a clean build against
    the wrong hardware when two boards' socket names coincide."""
    build_dir = tmp_path / "rig-swap"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    # lotus-buttons declares seeeduino_lotus/samd21g18a/rig -- a different
    # board than nucleo-datalogger's nucleo_f401re/stm32f401xe/rig. The guard
    # fires from the rig->board STRING resolved by list_rigs.py (reading
    # rig.yml), before any board-dts lookup -- no EXTRA_ZEPHYR_MODULES needed
    # for this configure to reach (and FATAL at) the guard.
    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", "-DRIG=lotus-buttons", str(build_dir)],
        cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=300)
    assert second.returncode != 0, (
        "expected swapping -DRIG to a different-board rig in an existing "
        "build dir to FATAL, but configure succeeded")
    combined = second.stdout + second.stderr
    assert "seeeduino_lotus/samd21g18a/rig" in combined, combined
    assert "pristine" in combined, combined


def test_cmake_alone_rig_swap_same_board_proceeds(tmp_path: Path) -> None:
    """Rig-swap guard, the legal half: swapping to another rig on the SAME
    board (nucleo-mux-farm shares nucleo-datalogger's extension target) must
    proceed -- the marker still matches the new rig's resolved board, so the
    build dir's pinned board remains valid."""
    build_dir = tmp_path / "rig-swap-same-board"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", "-DRIG=nucleo-mux-farm", str(build_dir)],
        cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=300)
    assert second.returncode == 0, (
        "swapping -DRIG to a SAME-board rig in an existing build dir must "
        f"proceed\n--- stdout ---\n{second.stdout}\n"
        f"--- stderr ---\n{second.stderr}")


# ---------------------------------------------------------------- E3: cross-module lotus board


def test_cmake_alone_lotus_needs_bridle_module(tmp_path: Path) -> None:
    """E3-brief.md acceptance criterion 4 -- the DOCUMENTED failure mode:
    `cmake -DRIG=lotus-pwm` WITHOUT `-DEXTRA_ZEPHYR_MODULES=<bridle>` must
    fail. seeeduino_lotus/samd21g18a/rig's base board lives entirely in the
    bridle Zephyr module, which the west manifest deliberately does NOT
    carry (decided 2026-07-24f) -- without the module define, hwmv2 board
    discovery never sees bridle's board_root, so the board plainly does not
    exist. This is the accepted cost of the no-manifest-entry decision, not
    something to fix."""
    build_dir = tmp_path / "lotus-no-module"
    result = _run_cmake_alone(build_dir, ["-DRIG=lotus-pwm"])
    assert result.returncode != 0, (
        "expected cmake -DRIG=lotus-pwm WITHOUT -DEXTRA_ZEPHYR_MODULES to "
        "fail (seeeduino_lotus does not exist without bridle's board_root)\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")
    combined = result.stdout + result.stderr
    assert "seeeduino_lotus" in combined, combined


def test_cmake_alone_lotus_with_bridle_module_configures(tmp_path: Path) -> None:
    """E3-brief.md acceptance criterion 3 -- cmake-alone, west-free, WITH
    `-DEXTRA_ZEPHYR_MODULES=<bridle_root>` must configure clean and resolve
    the SAME cross-module extension target as `west build-rig` with the
    identical define threaded (same shape as
    test_cmake_alone_entry_equivalent_to_build_rig, the E1 board)."""
    extra = board_extra_defines(rig_board_name("lotus-pwm"))
    assert extra, "lotus-pwm's board must need EXTRA_ZEPHYR_MODULES (bridle)"

    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig("lotus-pwm", reference_dir, extra)
    assert result_ref.returncode == 0, (
        f"west build-rig --rig lotus-pwm --cmake-only (with bridle module) "
        f"failed\n--- stdout ---\n{result_ref.stdout}\n"
        f"--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, ["-DRIG=lotus-pwm", *extra])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG=lotus-pwm {' '.join(extra)} (no -DBOARD, west absent) "
        f"failed to configure\n--- stdout ---\n{result_cmake.stdout}\n"
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
        "cmake-alone lotus-pwm's zephyr.dts is not structurally equivalent "
        f"to the build-rig reference (dts_equiv.py):\n{check.stdout}\n{check.stderr}")
