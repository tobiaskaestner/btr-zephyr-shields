"""cmake-alone rig entry: cmake -B <dir> -S <app> -DRIG=<name> with NO
-DBOARD and west absent entirely must configure a build equivalent to the
west build-rig path — the rig is the primary build coordinate; BOARD has a
per-rig DEFAULT inferred from it when not given (cmake/boards.cmake's
fork), and SHIELD is derived from the rig's own instances
(cmake/shields.cmake's fork).

This file covers the properties exercised entirely through direct cmake
invocations (no west subprocess at all):

  * a fresh cmake-alone configure resolves the SAME board target, a
    structurally-equivalent zephyr.dts, and the same rig provenance in
    build_info.yml (modulo the build directory itself) as west
    build-rig.
  * BOARD is an independent coordinate with a per-rig default
    (board-coordinate-s1-brief.md): a fresh configure with BOTH -DRIG and
    -DBOARD given configures, and the GIVEN board is the one built, even
    when it differs from the rig's own declared board; a RECONFIGURE of an
    existing rig build dir (BOARD cache-carried from our own earlier
    inference, not user-passed) proceeds unchanged.
  * a rig declaring no board: anywhere requires -DBOARD -- given, it
    builds; absent, a configure-time FATAL_ERROR names both the rig and
    the missing flag.
  * the rig-swap guard still fires for INFERRED builds: swapping -DRIG to
    a different-board rig in an existing build dir is a configure-time
    FATAL_ERROR (a build dir is pinned to the board it inferred, not to
    one a user separately supplied).
  * a qualified rig target (name@rev / name/variant) gets a loud
    not-yet-supported diagnostic from the resolver — a placeholder until rig
    variants/revisions land, never silent/partial resolution.
  * SHIELD keeps its OWN exclusion, unaffected by the board coordinate
    change: -DSHIELD alongside -DRIG on a fresh configure is a
    FATAL_ERROR (never a silent no-op); a plain --shield build (no RIG)
    is untouched.

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
    WEST_EXE,
    WEST_TOPDIR,
    board_extra_defines,
    render_argv,
    rig_board_name,
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
                    extra_defines: Optional[List[str]] = None) -> "subprocess.CompletedProcess[str]":
    """The reference path: west build-rig --cmake-only for one rig — same
    invocation shape as test_resolved_corpus.py's _run_build. extra_defines
    is threaded after --, e.g. the lotus board's
    -DEXTRA_ZEPHYR_MODULES=<bridle_root>."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, _APP,
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
    """The bare cmake invocation a rig build must support: -S/-B,
    NO -DBOARD, and an explicit -DPython3_EXECUTABLE (this venv's own
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
    """cmake -DRIG=<name> alone (no -DBOARD, west absent from PATH) must
    resolve the SAME board target, a structurally-equivalent zephyr.dts,
    and the same rig provenance in build_info.yml (modulo the build
    directory's own path) as west build-rig --rig <name>."""
    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig(_RIG, reference_dir)
    assert result_ref.returncode == 0, (
        f"west build-rig --rig {_RIG} --cmake-only failed\n"
        f"--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, [f"-DRIG={_RIG}"])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG={_RIG} (no -DBOARD, west absent) failed to configure\n"
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
    """BOARD is an independent coordinate with a per-rig default
    (board-coordinate-s1-brief.md): -DBOARD + -DRIG on a fresh configure
    now CONFIGURES, and the GIVEN board is the one built -- inverts the
    old exclusivity FATAL this test used to assert. The value here
    MATCHES the rig's own declared board (nucleo_datalogger's is
    nucleo_f401re/stm32f401xe/rig, passed back verbatim), which is
    exactly the byte-inert case the slice's own acceptance criterion
    rests on: today's inferred board already equals the rig's declared
    one, so this must be indistinguishable from a bare -DRIG configure."""
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


# no_board_datalogger declares NO board: at all -- the real corpus
# (boards/rigs/) has no such rig (test_corpus_complete requires every
# registered corpus rig to resolve a board, an invariant this fixture is
# specifically here to violate), so it lives in its OWN board_root
# instead, added via -DBOARD_ROOT alongside the module's default one
# (BOARD_ROOT is a zephyr_get(... MERGE ...) list -- verified empirically
# that an extra -DBOARD_ROOT augments rather than replaces the module's
# own, so the rig resolves from the fixture root while its shield
# (adafruit_data_logger) and both boards still resolve from btr-shields'
# own default root). Its content names the shared arduino_r3 socket alias
# (Ruling 1, board-as-invocation-coordinate-brief.md Sec 2 -- already
# landed on both real boards' own devicetree) rather than a board-
# prefixed label, so the SAME rig resolves on either real board.
#
# Deviation from the brief's own suggestion (reuse ard_datalogger, the
# corpus's dual-host rig, for the cross-board falsifier): ard_datalogger's
# per-variant sockets: maps are board-prefixed (nucleo_ard/frdm_ard), so
# crossing its OWN two declared variants to each OTHER's board fails at
# socket resolution (a real content/board mismatch per Sec 4's "sockets:
# handling is unchanged in every case" rule, not a mechanism bug) -- it
# would make the falsifier assert a rejection instead of a clean build.
# Building the SAME boardless rig against two DIFFERENT real boards and
# asserting each build actually used the one it was given is at least as
# strong a falsifier as crossing a rig's own declared board would be.
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
    """The real falsifier (board-coordinate-s1-brief.md Sec 5): building
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


def test_cmake_alone_reconfigure_of_rig_build_dir_proceeds(tmp_path: Path) -> None:
    """The other half of BOARD/RIG exclusivity: a RECONFIGURE of an
    EXISTING rig build dir must proceed even though BOARD is DEFINED on
    the second cmake invocation -- it is cache-carried from OUR OWN
    inference on the first
    configure (recorded via the RIG_INFERRED_BOARD marker), never a
    user-passed value the second time around. Reruns cmake against the SAME
    build dir with no -D flags at all, exactly like an incremental west
    build/ninja would trigger."""
    build_dir = tmp_path / "reconfigure"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- argv ---\n{render_argv(first)}\n--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", str(build_dir)], cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(300))
    assert second.returncode == 0, (
        "reconfigure of an existing rig build dir (no -D flags repeated) "
        "must proceed -- BOARD is legitimately cache-carried from our own "
        f"earlier inference\n--- argv ---\n{render_argv(second)}\n--- stdout ---\n{second.stdout}\n"
        f"--- stderr ---\n{second.stderr}")


def test_cmake_alone_qualified_target_resolves(tmp_path: Path) -> None:
    """rig-variants-revisions.md V1a, end-to-end at the cmake-alone entry
    point specifically (not just west build-rig): a FULLY qualified target
    (name@rev/variant) must resolve to the SAME board and rig provenance
    (including the SELECTED revision/variant themselves, and the applied
    fragment list) as west build-rig with the identical target string --
    same shape as test_cmake_alone_entry_equivalent_to_build_rig, but
    proving the qualifier axes specifically survive both entry points."""
    target = "pilot_variants@2/variant_b"
    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig(target, reference_dir)
    assert result_ref.returncode == 0, (
        f"west build-rig --rig {target} --cmake-only failed\n"
        f"--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, [f"-DRIG={target}"])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG={target} (no -DBOARD, west absent) failed to configure\n"
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
    """rig-variants-revisions.md V1a: qualifiers now RESOLVE (the old
    unconditional not-yet-supported placeholder is gone) — list_rigs.py's
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
    result = _run_cmake_alone(build_dir, [
        f"-DRIG={_RIG}", "-DSHIELD=adafruit_data_logger",
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


def test_cmake_alone_rig_swap_to_other_board_is_fatal(tmp_path: Path) -> None:
    """Rig-swap guard: changing -DRIG in an EXISTING build dir to a rig on a
    DIFFERENT board must FATAL at the boards.cmake fork. Without the guard,
    the stale cache-carried BOARD passes the exclusivity check (it equals
    the marker --
    both are the OLD rig's inference), inference is skipped, and the expander
    reads the OLD board's dts under the NEW rig's declared board name --
    phys-socket diagnostics blaming the wrong board, or a clean build against
    the wrong hardware when two boards' socket names coincide."""
    build_dir = tmp_path / "rig-swap"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- argv ---\n{render_argv(first)}\n--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    # lotus_buttons declares seeeduino_lotus/samd21g18a/rig -- a different
    # board than nucleo_datalogger's nucleo_f401re/stm32f401xe/rig. The guard
    # fires from the rig->board STRING resolved by list_rigs.py (reading
    # rig.yml), before any board-dts lookup -- no EXTRA_ZEPHYR_MODULES needed
    # for this configure to reach (and FATAL at) the guard.
    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", "-DRIG=lotus_buttons", str(build_dir)],
        cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(300))
    assert second.returncode != 0, (
        "expected swapping -DRIG to a different-board rig in an existing "
        "build dir to FATAL, but configure succeeded")
    combined = f"{render_argv(second)}\n" + second.stdout + second.stderr
    assert "seeeduino_lotus/samd21g18a/rig" in combined, combined
    assert "pristine" in combined, combined


def test_cmake_alone_rig_swap_with_explicit_board_still_fatal(
        tmp_path: Path) -> None:
    """The rig-swap guard fires even when the SECOND configure ALSO gives
    an explicit -DBOARD (here, matching the new rig's own declared board
    exactly) -- giving -DBOARD does not make an existing build dir's
    board mutable. Without this, upstream's own zephyr_check_cache(BOARD)
    would only WARN and silently revert to the ORIGINAL board, so the
    build would proceed against the WRONG hardware under the new rig's
    name -- worse than this guard's FATAL, not an alternative to it. This
    is the scenario the message differentiates: naming the -DBOARD given
    this time rather than blaming inference for a board change the user
    tried to make directly (verified empirically that cmake applies a -D
    override to BOARD before this file runs, so the value compared here
    is the FRESH one, not the stale cached one)."""
    build_dir = tmp_path / "rig-swap-explicit-board"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- argv ---\n{render_argv(first)}\n--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", "-DRIG=lotus_buttons",
         "-DBOARD=seeeduino_lotus/samd21g18a/rig", str(build_dir)],
        cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(300))
    assert second.returncode != 0, (
        "expected swapping -DRIG with an explicit, matching -DBOARD in an "
        "existing build dir to STILL FATAL, but configure succeeded")
    output = second.stdout + second.stderr
    assert "seeeduino_lotus/samd21g18a/rig" in output, output
    assert "was also given" in output, output
    assert "pristine" in output, output


def test_cmake_alone_rig_swap_same_board_proceeds(tmp_path: Path) -> None:
    """Rig-swap guard, the legal half: swapping to another rig on the SAME
    board (nucleo_mux_farm shares nucleo_datalogger's extension target) must
    proceed -- the marker still matches the new rig's resolved board, so the
    build dir's pinned board remains valid."""
    build_dir = tmp_path / "rig-swap-same-board"
    first = _run_cmake_alone(build_dir, [f"-DRIG={_RIG}"])
    assert first.returncode == 0, (
        f"initial cmake -DRIG={_RIG} configure failed\n"
        f"--- argv ---\n{render_argv(first)}\n--- stdout ---\n{first.stdout}\n--- stderr ---\n{first.stderr}")

    env = _cmake_alone_env()
    second = subprocess.run(
        ["cmake", "-DRIG=nucleo_mux_farm", str(build_dir)],
        cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(300))
    assert second.returncode == 0, (
        "swapping -DRIG to a SAME-board rig in an existing build dir must "
        f"proceed\n--- argv ---\n{render_argv(second)}\n--- stdout ---\n{second.stdout}\n"
        f"--- stderr ---\n{second.stderr}")


# ---------------------------------------------------------------- cross-module lotus board


def test_cmake_alone_lotus_needs_bridle_module(tmp_path: Path) -> None:
    """The DOCUMENTED failure mode: cmake -DRIG=lotus_pwm WITHOUT
    -DEXTRA_ZEPHYR_MODULES=<bridle> must fail. seeeduino_lotus/samd21g18a/rig's
    base board lives entirely in the bridle Zephyr module, which the west
    manifest does NOT carry -- without the module define, hwmv2 board
    discovery never sees bridle's board_root, so the board plainly does not
    exist. This is the accepted cost of keeping bridle out of the manifest,
    not something to fix."""
    build_dir = tmp_path / "lotus-no-module"
    result = _run_cmake_alone(build_dir, ["-DRIG=lotus_pwm"])
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
    extra = board_extra_defines(rig_board_name("lotus_pwm"))
    assert extra, "lotus_pwm's board must need EXTRA_ZEPHYR_MODULES (bridle)"

    reference_dir = tmp_path / "build-rig-reference"
    result_ref = _run_build_rig("lotus_pwm", reference_dir, extra)
    assert result_ref.returncode == 0, (
        f"west build-rig --rig lotus_pwm --cmake-only (with bridle module) "
        f"failed\n--- argv ---\n{render_argv(result_ref)}\n--- stdout ---\n{result_ref.stdout}\n"
        f"--- stderr ---\n{result_ref.stderr}")

    cmake_dir = tmp_path / "cmake-alone"
    result_cmake = _run_cmake_alone(cmake_dir, ["-DRIG=lotus_pwm", *extra])
    assert result_cmake.returncode == 0, (
        f"cmake -DRIG=lotus_pwm {' '.join(extra)} (no -DBOARD, west absent) "
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


# ---------------------------------------------------------- promoted shield (S3b)
#
# board-coordinate-s3b-brief.md's own criteria 2.2 and 2.3. The slice's
# headline capability is a -DRIG that names a SHIELD rather than a rig
# folder, and without these two it is guarded by nothing: every other test
# in this file names a real rig, so a regression that broke promotion
# alone would leave the whole suite green.


@pytest.mark.build
def test_cmake_alone_promoted_shield_configures_with_a_given_board(
        tmp_path: Path) -> None:
    """Criterion 2.2: -DRIG naming a SHIELD configures, given a board.
    adafruit_data_logger plugs arduino-r3 and nucleo's rig extension
    declares exactly one socket of that type, so the socket resolves by
    inference with nothing named -- the promoted form has no socket: to
    name (S3a).

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
def test_cmake_alone_promoted_shield_without_a_board_is_fatal(
        tmp_path: Path) -> None:
    """Criterion 2.3: a promoted shield declares no board and has no axis
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
