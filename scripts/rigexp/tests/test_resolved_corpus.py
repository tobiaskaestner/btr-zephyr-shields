"""Resolved goldens: the real pass-2 zephyr.dts, via west build-rig
--cmake-only.

This is THE invariant that must hold regardless of how an emitted golden's
exact text is produced: if a future change to the expander legitimately
alters what test_emitted_corpus.py freezes (e.g. how a nexus is wired in
the overlay), this file confirms whether the BUILT devicetree actually
changed; the emitted golden then gets re-frozen with a justification note,
using the resolved tree as the oracle that nothing else moved.

For each ACCEPT rig: west build-rig --cmake-only must configure clean, and
the produced zephyr.dts must be STRUCTURALLY EQUIVALENT (via
scripts/dts_equiv.py, NOT a byte diff — labels/phandle numbers/ordering are
irrelevant, see that script's docstring) to the frozen golden.

For each REJECT rig: the same --cmake-only invocation must FAIL, and its
output must contain the expected phys-* diagnostic category string — the
same diagnostic category must surface through the full west/CMake path, not
just the standalone expander.

These tests run a real CMake configure per rig (several minutes for the full
13-rig corpus) — marked @pytest.mark.build and @pytest.mark.integration;
CHECK_FAST=1 (scripts/check.sh) deselects them via pytest -m "not build".

Refreeze: RIGEXP_REFREEZE=1 rewrites tests/goldens/<rig-name>/zephyr.dts
(ACCEPT rigs only) instead of comparing — inspect the diff before committing,
same rule as an emitted golden.
"""
from __future__ import annotations

import os
import pickle
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest
import yaml

from conftest import (
    ACCEPT_CASES,
    DTS_EQUIV,
    GOLDENS_DIR,
    REFREEZE,
    REJECT_CASES,
    REPO_ROOT,
    RigCase,
    WEST_EXE,
    WEST_TOPDIR,
    board_extra_defines,
    normalize_dts_provenance,
    rig_board_name,
    zephyr_base,
)

# Triggers python-devicetree onto sys.path (from $ZEPHYR_BASE) as an
# import-time side effect, exactly like test_board_read.py -- needed to
# unpickle a real edt.pickle below (its classes live in devicetree.edtlib).
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import edt_build  # noqa: E402,F401

pytestmark = [pytest.mark.build, pytest.mark.integration]

# Relative to WEST_TOPDIR — any app works for a cmake-only configure;
# hello_world is the reference app this suite standardizes on.
_APP = "zephyr/samples/hello_world"


def _run_build(rig_name: str, build_dir: Path,
                extra_defines: Optional[List[str]] = None) -> "subprocess.CompletedProcess[str]":
    """west build-rig --cmake-only for one rig — a temp build dir; -p
    always wipes it, so nothing durable may be read back from build_dir
    beyond this one process's own output. extra_defines is threaded after
    -- -- empty for every rig except the lotus ones, whose board needs
    -DEXTRA_ZEPHYR_MODULES=<bridle_root>."""
    cmd = [
        WEST_EXE, "build-rig", "--rig", rig_name, _APP,
        "--cmake-only", "-p", "always", "-d", str(build_dir),
    ]
    if extra_defines:
        cmd += ["--", *extra_defines]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=dict(os.environ),
                           capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("case", ACCEPT_CASES, ids=lambda c: c.name)
def test_tier2_accept_zephyr_dts(case: RigCase, tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name(case.name))
    result = _run_build(case.name, build_dir, extra)
    assert result.returncode == 0, (
        f"{case.name}: expected `west build-rig --cmake-only` to configure "
        f"clean (an ACCEPT rig)\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    candidate = build_dir / "zephyr" / "zephyr.dts"
    assert candidate.is_file(), f"{case.name}: no zephyr.dts at {candidate}"

    golden = GOLDENS_DIR / case.name / "zephyr.dts"
    if REFREEZE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(normalize_dts_provenance(candidate.read_text()))
        return

    if not golden.is_file():
        pytest.fail(
            f"golden missing: {golden} (run with RIGEXP_REFREEZE=1 to create it)")

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(golden), str(candidate)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        f"{case.name}: zephyr.dts not structurally equivalent to the golden "
        f"(dts_equiv.py):\n{check.stdout}\n{check.stderr}")


# ---------------------------------------------------------------- V1a: qualified pilot builds

def _build_and_freeze_dts(rig_target: str, golden_name: str,
                          tmp_path: Path) -> Path:
    """Shared body for the pilot family's three NON-default qualified tiers
    (the bare tuple already rides test_tier2_accept_zephyr_dts via
    ACCEPT_CASES's pilot_variants entry, above) -- west build-rig --rig
    accepts a FULL qualified target string verbatim (rig.py forwards it,
    zero rig knowledge), so no cmake/west-command change was needed for
    this to work. Returns the build dir for callers that need to inspect
    more than zephyr.dts (e.g. .config)."""
    build_dir = tmp_path / "build"
    result = _run_build(rig_target, build_dir)
    assert result.returncode == 0, (
        f"{rig_target}: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    candidate = build_dir / "zephyr" / "zephyr.dts"
    assert candidate.is_file(), f"{rig_target}: no zephyr.dts at {candidate}"

    golden = GOLDENS_DIR / golden_name / "zephyr.dts"
    if REFREEZE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(normalize_dts_provenance(candidate.read_text()))
        return build_dir

    if not golden.is_file():
        pytest.fail(
            f"golden missing: {golden} (run with RIGEXP_REFREEZE=1 to create it)")

    zb = zephyr_base()
    check = subprocess.run(
        [sys.executable, str(DTS_EQUIV), str(golden), str(candidate)],
        env={**os.environ, "ZEPHYR_BASE": zb},
        capture_output=True, text=True)
    assert check.returncode == 0, (
        f"{rig_target}: zephyr.dts not structurally equivalent to the "
        f"golden (dts_equiv.py):\n{check.stdout}\n{check.stderr}")
    return build_dir


def test_tier2_pilot_variant_b(tmp_path: Path) -> None:
    """variant_b @ revision 1: the variant's own .overlay must actually
    reach the real build (dts_equiv.py's structural comparison is what
    proves it, not just a text diff on the generated overlay)."""
    _build_and_freeze_dts("pilot_variants/variant_b",
                          "pilot_variants_variant_b", tmp_path)


def test_tier2_pilot_revision_2(tmp_path: Path) -> None:
    """variant_a (default) @ revision 2."""
    _build_and_freeze_dts("pilot_variants@2", "pilot_variants_2", tmp_path)


def test_tier2_pilot_variant_b_revision_2(tmp_path: Path) -> None:
    """The fully qualified tuple (variant_b @ revision 2) -- THE EVIDENCE
    this slice's acceptance criteria ask for: STATUS-line claims alone
    don't prove a collected fragment took effect, so this test inspects
    the REAL build's own .config and zephyr.dts directly.

    variant_b's own CONFIG_MAIN_STACK_SIZE (2222), revision 2's own
    CONFIG_HEAP_MEM_POOL_SIZE (256), AND the COMBINED per-(variant,
    revision) fragment's own CONFIG_ISR_STACK_SIZE (3333) must ALL be
    present in .config -- proving base -> variant -> revision -> combined
    really stack, none silently overwriting another -- and BOTH
    variant_b's own overlay marker node AND the combined fragment's own
    marker node must be visible in the generated zephyr.dts."""
    build_dir = _build_and_freeze_dts(
        "pilot_variants@2/variant_b", "pilot_variants_variant_b_2", tmp_path)

    dotconfig = (build_dir / "zephyr" / ".config").read_text()
    assert "CONFIG_MAIN_STACK_SIZE=2222" in dotconfig, (
        "variant_b's own _defconfig symbol is missing from .config -- the "
        f"variant Kconfig fragment was not collected\n--- .config ---\n{dotconfig}")
    assert "CONFIG_HEAP_MEM_POOL_SIZE=256" in dotconfig, (
        "revision 2's own _defconfig symbol is missing from .config -- the "
        f"revision Kconfig fragment was not collected\n--- .config ---\n{dotconfig}")
    assert "CONFIG_ISR_STACK_SIZE=3333" in dotconfig, (
        "the COMBINED (variant, revision) _defconfig symbol is missing "
        f"from .config -- the combined fragment was not collected\n"
        f"--- .config ---\n{dotconfig}")

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    assert "pilot-variant-b-marker" in zephyr_dts, (
        "variant_b's own .overlay marker node is missing from zephyr.dts -- "
        f"the variant DT fragment was not collected\n--- zephyr.dts ---\n{zephyr_dts}")
    assert "pilot-combined-marker" in zephyr_dts, (
        "the COMBINED (variant, revision) .overlay marker node is missing "
        f"from zephyr.dts -- the combined DT fragment was not collected\n"
        f"--- zephyr.dts ---\n{zephyr_dts}")


def test_tier2_shield_rev_family_revision_2(tmp_path: Path) -> None:
    """The two revision axes composing, through a REAL build: rig revision
    2's delta moves the sensor to the shield's revision 2, so revision 2's
    compatible must reach zephyr.dts AND the shield revision's own Kconfig
    fragment must be collected -- the latter proving the composition
    survives the whole handoff (loader resolves the delta, the expander
    reports the resolved shield revision through context.cmake, dts.cmake
    turns that into a collected <name>_<rev>.conf), not just the loader."""
    build_dir = _build_and_freeze_dts(
        "shield_rev_family@2", "shield_rev_family_2", tmp_path)

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    assert "vnd,temp0x48v2" in zephyr_dts, (
        "the shield's revision-2 compatible is missing from zephyr.dts -- "
        f"the rig revision's delta did not select it\n"
        f"--- zephyr.dts ---\n{zephyr_dts}")

    dotconfig = (build_dir / "zephyr" / ".config").read_text()
    assert "CONFIG_MAIN_STACK_SIZE=2600" in dotconfig, (
        "i2c_sensor_2.conf's own symbol is missing from .config -- a shield "
        "revision selected BY A RIG REVISION did not reach the shield "
        f"Kconfig tail\n--- .config ---\n{dotconfig}")


def test_tier2_pilot_variant_c_shield_substitution(tmp_path: Path) -> None:
    """variant_c (V1b): the topology-differing tuple -- its own delta
    substitutes the logger instance's shield (Adafruit Data Logger ->
    pilot_alt_button). THE EVIDENCE this slice's acceptance criteria ask
    for (item 6): asserted on zephyr.dts directly, not on STATUS lines --
    the SUBSTITUTED shield's own node/property must be present, and the
    ORIGINAL shield's devices must be completely gone."""
    build_dir = _build_and_freeze_dts(
        "pilot_variants/variant_c", "pilot_variants_variant_c", tmp_path)

    zephyr_dts = (build_dir / "zephyr" / "zephyr.dts").read_text()
    assert "logger_pab_key" in zephyr_dts, (
        "the substituted shield's own device (logger_pab_key) is missing "
        f"from zephyr.dts\n--- zephyr.dts ---\n{zephyr_dts}")
    # dtc always renders integers as hex in its own output.
    assert "zephyr,code = < 0x5 >;" in zephyr_dts, (
        "the variant delta's own wholesale params replace (zephyr,code=5) "
        f"did not reach the real build\n--- zephyr.dts ---\n{zephyr_dts}")
    assert "logger_dl_rtc" not in zephyr_dts, (
        "the ORIGINAL shield's device (logger_dl_rtc, Adafruit Data "
        "Logger's RTC) is still present -- the shield substitution did "
        f"not actually replace the topology\n--- zephyr.dts ---\n{zephyr_dts}")
    assert "logger_dl_sd" not in zephyr_dts, (
        "the ORIGINAL shield's SD device is still present -- the shield "
        f"substitution did not actually replace the topology\n"
        f"--- zephyr.dts ---\n{zephyr_dts}")


def test_tier2_pilot_build_info_provenance(tmp_path: Path) -> None:
    """Provenance (item 6/7): build_info.yml's cmake.vendor-specific.rig.*
    carries the SELECTED revision/variant and the applied fragment list --
    same assertion shape as test_tier2_build_info_rig_provenance above,
    the established pattern for inspecting this block."""
    build_dir = tmp_path / "build"
    result = _run_build("pilot_variants@2/variant_b", build_dir)
    assert result.returncode == 0, (
        f"pilot_variants@2/variant_b: expected `west build-rig --cmake-only` "
        f"to configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    assert rig["revision"] == "2"
    assert rig["variant"] == "variant_b"
    fragments = rig["fragments"]
    assert fragments.endswith(".overlay") or "_defconfig" in fragments
    assert "pilot_variants_variant_b.overlay" in fragments
    assert "pilot_variants_variant_b_defconfig" in fragments
    assert "pilot_variants_2_defconfig" in fragments


# ---------------------------------------------------------------- V1c: shield revisions

def test_tier2_shield_revision_conf_collected(tmp_path: Path) -> None:
    """THE EVIDENCE the shield-revision Kconfig-collection claim asks for
    (rig-variants-revisions.md V1c step 4): inspects the real build's OWN
    .config, not a STATUS-line claim. shield_rev_pilot selects shield:
    i2c_sensor@2, whose OWN i2c_sensor_2.conf must be collected by
    cmake/dts.cmake's shield Kconfig tail (base .shield/.conf first,
    revision after, matching the DT layering) -- distinguishable from any
    rig-level fragment's own MAIN_STACK_SIZE choice by its value alone."""
    build_dir = tmp_path / "build"
    result = _run_build("shield_rev_pilot", build_dir)
    assert result.returncode == 0, (
        f"shield_rev_pilot: expected `west build-rig --cmake-only` to "
        f"configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    dotconfig = (build_dir / "zephyr" / ".config").read_text()
    assert "CONFIG_MAIN_STACK_SIZE=2600" in dotconfig, (
        "i2c_sensor_2.conf's own symbol is missing from .config -- the "
        f"selected shield revision's Kconfig fragment was not collected\n"
        f"--- .config ---\n{dotconfig}")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]
    assert rig["shield-revisions"] == "i2c_sensor@2", (
        f"build_info rig.shield-revisions must record the selected shield "
        f"revision: {rig!r}")


@pytest.mark.parametrize("case", REJECT_CASES, ids=lambda c: c.name)
def test_tier2_reject_configure_fails(case: RigCase, tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name(case.name))
    result = _run_build(case.name, build_dir, extra)
    assert result.returncode != 0, (
        f"{case.name}: expected `west build-rig --cmake-only` to FAIL (a "
        f"REJECT rig) but it exited 0")

    combined = result.stdout + result.stderr
    assert case.category is not None   # every REJECT case declares one
    assert f"[{case.category}]" in combined, (
        f"{case.name}: expected diagnostic category [{case.category}] in "
        f"the build output -- the same category must surface through the "
        f"full west/CMake path, not just the standalone expander\n{combined}")


def test_tier2_user_extra_conf_wins_over_rig(tmp_path: Path) -> None:
    """The rig's own <rigname>_defconfig rides shield_conf_files (an
    APPEND) rather than prepending onto EXTRA_CONF_FILE -- "user extras
    win" now falls out of upstream's own merge ordering
    (kconfig.cmake's merge_config_files: shield_conf_files lands BEFORE
    EXTRA_CONF_FILE_AS_LIST), not from anything this fork does. Nothing of
    ours enforces that ordering any more, so pin it directly on the real
    outcome: a user-passed -DEXTRA_CONF_FILE overriding a symbol
    nucleo_mux_farm_defconfig also sets must win in the resulting
    .config. Contends over CONFIG_I2C_TCA954X_ROOT_INIT_PRIO (61 in the
    rig's own defconfig); the driver's BUILD_ASSERT(CHANNEL_INIT_PRIO >
    ROOT_INIT_PRIO) only fires on a full compile, never at --cmake-only, but
    55 keeps the override physically sensible regardless (still below the
    channel's 62)."""
    user_conf = tmp_path / "user.conf"
    user_conf.write_text("CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=55\n")

    build_dir = tmp_path / "build"
    result = _run_build("nucleo_mux_farm", build_dir,
                        [f"-DEXTRA_CONF_FILE={user_conf}"])
    assert result.returncode == 0, (
        f"nucleo_mux_farm: expected `west build-rig --cmake-only` with a "
        f"user -DEXTRA_CONF_FILE to configure clean\n--- stdout ---\n"
        f"{result.stdout}\n--- stderr ---\n{result.stderr}")

    dotconfig = (build_dir / "zephyr" / ".config").read_text()
    assert "CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=55" in dotconfig, (
        "user -DEXTRA_CONF_FILE must win over the rig's own "
        "nucleo_mux_farm_defconfig (CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=61)\n"
        f"--- .config ---\n{dotconfig}")
    assert "CONFIG_I2C_TCA954X_ROOT_INIT_PRIO=61" not in dotconfig, (
        f"the rig's own value leaked into .config alongside the user's\n"
        f"--- .config ---\n{dotconfig}")


def test_tier2_lotus_pwm_semantic_pin(tmp_path: Path) -> None:
    """The permanent semantic invariant the expander's socket-relative
    pwm/adc emission must hold: pass-2's own edt.pickle -- the resolved
    ControllerAndData edtlib builds while compiling the real devicetree --
    must show the servo's pwms and the light sensor's io-channels
    landing on the expected (controller, channel/input, period). This is
    real ground truth rather than a text check on the generated overlay:
    vnd,pwm-servo/vnd,light-sensor are typed (dts/bindings/test/), so
    pass 2 actually resolves the socket's pwm-map/io-channel-map nexus
    instead of leaving the props inert -- a text-only check on the emitted
    pwms/io-channels line could pass even if the nexus itself were
    unresolvable."""
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name("lotus_pwm"))
    result = _run_build("lotus_pwm", build_dir, extra)
    assert result.returncode == 0, (
        f"lotus_pwm: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    with open(build_dir / "zephyr" / "edt.pickle", "rb") as f:
        edt = pickle.load(f)
    nodes = {node.path: node for node in edt.nodes}

    servo = nodes["/servo_1/servo"]
    assert len(servo.props["pwms"].val) == 1, (
        "servo pwms must resolve to exactly ONE entry — a trailing bogus "
        "element means a flags cell crept back into the 2-cell emission")
    pwm_spec = servo.props["pwms"].val[0]
    assert "tcc0" in pwm_spec.controller.labels, (
        f"servo pwms resolved to {pwm_spec.controller!r}, expected tcc0")
    assert pwm_spec.data == {"channel": 0, "period": 20000000}, (
        f"servo pwms resolved to {pwm_spec.data!r}, expected "
        "channel 0 / period 20000000ns")

    light = nodes["/light_1/light"]
    assert len(light.props["io-channels"].val) == 1, (
        "light io-channels must resolve to exactly ONE entry")
    adc_spec = light.props["io-channels"].val[0]
    assert "adc0" in adc_spec.controller.labels, (
        f"light io-channels resolved to {adc_spec.controller!r}, expected adc0")
    assert adc_spec.data == {"input": 0}, (
        f"light io-channels resolved to {adc_spec.data!r}, expected input 0")


def test_tier2_build_info_rig_provenance(tmp_path: Path) -> None:
    """A rig build must record what it looked at into build_info.yml, via
    zephyr's own build_info() (cmake/dts.cmake). It lands under
    cmake.vendor-specific.rig.* -- build-schema.yaml is upstream and not
    ours to extend, so this rides the schema's own downstream-owned escape
    hatch rather than the naively-expected cmake.rig.*. Deliberately uses
    frdm_eth_nest: it names TWO distinct shields (arduino_uno_click,
    eth_click carried by THREE instances), because build_info()'s
    vendor-specific VALUE silently truncates a multi-element CMake list to
    its first entry unless pre-JOINed -- a single-shield rig would not catch
    a regression in that join."""
    build_dir = tmp_path / "build"
    result = _run_build("frdm_eth_nest", build_dir)
    assert result.returncode == 0, (
        f"frdm_eth_nest: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    assert rig["name"] == "frdm_eth_nest"
    assert rig["board"] == "frdm_k64f/mk64f12/rig"
    assert rig["yml"].endswith("boards/rigs/frdm_eth_nest/rig.yml")
    # The content file (metadata/content split): its path is constructed
    # from the RESOLVED rig name, cmake's own, before the expander ever
    # runs — recorded here even though this rig declares no revisions:/
    # variants: axis at all, unlike RIG_REVISION/RIG_VARIANT's "no
    # declaration, no key" precedent, since every rig has exactly one
    # content file regardless of what axes it declares.
    assert rig["content-yml"].endswith(
        "boards/rigs/frdm_eth_nest/frdm_eth_nest.yml")
    assert rig["board-dts"].endswith(
        "boards/extend/nxp/frdm_k64f/frdm_k64f_mk64f12_rig.dts")

    shields = {s.strip() for s in rig["shields"].split(",")}
    assert shields == {"arduino_uno_click", "eth_click"}, (
        f"rig-provenance 'shields' must list BOTH distinct shields "
        f"(not truncated to the first): {rig['shields']!r}")
    assert "arduino_uno_click" in rig["shield-dirs"]
    assert "eth_click" in rig["shield-dirs"]
    assert Path(rig["out-dir"]).is_dir()

    # The generated overlay is unconditional; frdm_eth_nest also has its own
    # hand-authored frdm_eth_nest_defconfig (one of the corpus's 8 rigs
    # that do), but no rig-gen.conf -- the emitter never produces one
    # today, so defconfig-gen must be absent, not present-but-empty.
    assert Path(rig["overlay-gen"]).is_file()
    assert rig["defconfig"].endswith("frdm_eth_nest_defconfig")
    assert "defconfig-gen" not in rig


def test_tier2_build_info_shield_dir_collision(tmp_path: Path) -> None:
    """Shield name-collision across BOARD_ROOT: BOARD_ROOT holds both
    btr-shields and $ZEPHYR_BASE (zephyr-rigs), and the
    latter ships its own stock boards/shields/adafruit_data_logger -- a
    plain upstream shield (no <name>.shield rig-template marker), same name
    as btr-shields' rig-template shield. cmake/dts.cmake's shield tail must
    resolve the collision to OUR (rig-template) folder, not whichever root
    list_shields.py happened to sort last. nucleo_datalogger is the
    corpus rig naming adafruit_data_logger, so it's the collision witness."""
    build_dir = tmp_path / "build"
    result = _run_build("nucleo_datalogger", build_dir)
    assert result.returncode == 0, (
        f"nucleo_datalogger: expected `west build-rig --cmake-only` to "
        f"configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")
    assert "shield name 'adafruit_data_logger' is offered by" not in (
        result.stdout + result.stderr), (
        "unexpected ambiguity warning -- the marker-preference rule should "
        "have resolved this collision silently")

    with open(build_dir / "build_info.yml") as f:
        build_info = yaml.safe_load(f)
    rig = build_info["cmake"]["vendor-specific"]["rig"]

    shield_dir = rig["shield-dirs"]
    assert "adafruit_data_logger" in shield_dir
    assert str(REPO_ROOT) in shield_dir, (
        f"shield-dirs must record btr-shields' OWN adafruit_data_logger "
        f"folder (the rig-template one, marked by "
        f"adafruit_data_logger.shield), not $ZEPHYR_BASE's stock shield of "
        f"the same name: {shield_dir!r}")
    zb = zephyr_base()
    assert not shield_dir.startswith(zb), (
        f"shield-dirs resolved into $ZEPHYR_BASE ({zb}) -- the stock, "
        f"non-rig-template adafruit_data_logger folder won the collision: "
        f"{shield_dir!r}")


def test_tier2_rig_depends_provenance(tmp_path: Path) -> None:
    """Dependency-tracking handoff (RIG_DEPENDS): cmake/dts.cmake appends
    the expander's own generated context.cmake RIG_DEPENDS list to
    CMAKE_CONFIGURE_DEPENDS, so editing a .shield template or a connector
    binding — not just rig.yml, its <name>.yml content file, or the rig's
    own <name>_defconfig/<name>.overlay, the pre-existing static
    registrations — retriggers configure. What's testable HERE, without
    mutating any corpus file (forbidden — modifying fixtures in a test would
    make the test self-fulfilling): that context.cmake, as ACTUALLY written
    into a real build dir, carries the rig.yml, its content file, at least
    one .shield, one connector plug YAML, and the board .dts. The other
    half — that CMake actually retriggers configure when a
    CMAKE_CONFIGURE_DEPENDS-listed file changes — is CMake's own
    long-standing guarantee for that property, not something this project
    needs to (or reasonably can, without touching corpus files) re-prove;
    set_property(... APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ...) in
    dts.cmake is the whole of our contribution."""
    build_dir = tmp_path / "build"
    extra = board_extra_defines(rig_board_name("lotus_pwm"))
    result = _run_build("lotus_pwm", build_dir, extra)
    assert result.returncode == 0, (
        f"lotus_pwm: expected `west build-rig --cmake-only` to configure "
        f"clean\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")

    context_cmake = (build_dir / "rig" / "context.cmake").read_text()
    depends_line = next(
        (line for line in context_cmake.splitlines() if "RIG_DEPENDS" in line),
        None)
    assert depends_line is not None, (
        f"no RIG_DEPENDS in generated context.cmake:\n{context_cmake}")

    assert "boards/rigs/lotus_pwm/rig.yml" in depends_line
    assert "boards/rigs/lotus_pwm/lotus_pwm.yml" in depends_line
    assert "boards/shields/grove_servo/grove_servo.shield" in depends_line
    assert "dts/bindings/connectors/grove.yaml" in depends_line
    assert ("boards/extend/seeed/seeeduino_lotus/"
            "seeeduino_lotus_samd21g18a_rig.dts") in depends_line


# ---------------------------------------------------------------- board-per-variant


def test_tier2_ard_datalogger_frdm(tmp_path: Path) -> None:
    """ard_datalogger's frdm variant, through a REAL build: the bare/
    default (nucleo) tuple already rides test_tier2_accept_zephyr_dts via
    ACCEPT_CASES; this proves the SAME content also configures clean
    through the OTHER declared board, with no fragment file collected for
    it at all (there is none to collect)."""
    _build_and_freeze_dts("ard_datalogger/frdm", "ard_datalogger_frdm", tmp_path)


def test_tier2_ard_datalogger_dual_host_d10(tmp_path: Path) -> None:
    """THE portability evidence, as real ground truth rather than a
    STATUS-line claim: ARDUINO_HEADER_R3_D10 is index 16 in the SAME
    shared dt-bindings header on both hosts, but nucleo_ard and frdm_ard
    map it to different controllers/pins (gpiob 6 vs gpiod 0, verified
    against both boards' own arduino_r3_socket.dtsi). adafruit_data_logger
    pins its SD card's CS there via shield,cs-position, so the identical
    ard_datalogger.yml content must resolve cs-gpios to DIFFERENT real
    hardware depending on which variant selected the board -- inspected
    via each build's own edt.pickle (pass-2 ground truth), not the
    generated overlay's text."""
    nucleo_dir = tmp_path / "build-nucleo"
    result = _run_build("ard_datalogger", nucleo_dir)
    assert result.returncode == 0, (
        f"ard_datalogger: expected `west build-rig --cmake-only` to "
        f"configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    frdm_dir = tmp_path / "build-frdm"
    result = _run_build("ard_datalogger/frdm", frdm_dir)
    assert result.returncode == 0, (
        f"ard_datalogger/frdm: expected `west build-rig --cmake-only` to "
        f"configure clean\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")

    def cs_pin(build_dir: Path):
        with open(build_dir / "zephyr" / "edt.pickle", "rb") as f:
            edt = pickle.load(f)
        by_label = {label: node for node in edt.nodes for label in node.labels}
        sd = by_label["logger_dl_sd"]
        # cs-gpios is a property of the SPI CONTROLLER (indexed by the
        # device's own reg, its chip-select slot), never of the device
        # node itself -- ordinary SPI/DT convention, unrelated to rigs.
        spi = sd.parent
        spec = spi.props["cs-gpios"].val[0]
        return spec.controller.labels, spec.data["pin"]

    nucleo_labels, nucleo_pin = cs_pin(nucleo_dir)
    frdm_labels, frdm_pin = cs_pin(frdm_dir)

    assert "gpiob" in nucleo_labels, (
        f"nucleo D10 resolved to controller {nucleo_labels!r}, expected gpiob")
    assert nucleo_pin == 6, f"nucleo D10 resolved to pin {nucleo_pin!r}, expected 6"
    assert "gpiod" in frdm_labels, (
        f"frdm D10 resolved to controller {frdm_labels!r}, expected gpiod")
    assert frdm_pin == 0, f"frdm D10 resolved to pin {frdm_pin!r}, expected 0"
    assert (nucleo_labels, nucleo_pin) != (frdm_labels, frdm_pin), (
        "D10 resolved to the SAME (controller, pin) on both hosts -- the "
        "dual-host portability claim is not actually exercised")
