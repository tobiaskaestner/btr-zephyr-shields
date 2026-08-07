"""`west rigs --boards-for` driven as a subprocess (board-coordinate-
s2-brief.md). NOT build-marked: `west rigs` itself runs in 0.3s, and
nothing this command reaches configures cmake -- it censuses board
rig-extension SOURCES (board_census.py), never a real board devicetree.
"""
from __future__ import annotations

import os
import subprocess

import pytest
import yaml

from conftest import (REPO_ROOT, WEST_EXE, WEST_TOPDIR, subprocess_timeout,
                      zephyr_base)


def _run(*args: str) -> "subprocess.CompletedProcess[str]":
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zephyr_base()
    return subprocess.run(
        [WEST_EXE, "rigs", *args], cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(60))


@pytest.mark.parametrize("rig_target, expected_board", [
    ("lotus_buttons", "seeeduino_lotus/samd21g18a/rig"),
    ("quail_temp_farm", "mikroe_quail/stm32f427xx/rig"),
])
def test_boards_for_the_criterion_answers(rig_target: str, expected_board: str) -> None:
    """Acceptance criterion 3, verbatim. nucleo_datalogger used to be a
    third case here, back when every corpus rig answered exactly its
    declared board (board-coordinate-s2-brief.md's own state of the
    world) -- it moved out to
    test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards
    below once S5's content migration made it answer two boards, which a
    single-`expected_board` parametrization cannot express. grove
    (lotus_buttons) and mikrobus (quail_temp_farm) stay here because only
    one corpus board offers each of those connector types, so migrating
    THEIR content to the conventional label (already true for grove, and
    done in S5 for mikrobus) does not, by itself, open a second answer."""
    result = _run("--boards-for", rig_target)
    assert result.returncode == 0, (
        f"--boards-for {rig_target}: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == expected_board


def test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards() -> None:
    """board-coordinate-s5-brief.md Sec 5.3, ruled as an ACCEPTANCE
    CRITERION: at least one corpus rig's `--boards-for` answer must
    contain more than one board once content migrates off board-prefixed
    labels. Before S5, nucleo_datalogger's content named `nucleo_ard`
    directly, so only nucleo_f401re could ever satisfy it even though
    frdm_k64f's own arduino_r3 socket offers the identical i2c/spi subset,
    mating and stackability adafruit_data_logger needs -- the "helpful"
    board-agnostic reuse board-as-coordinate exists to unlock. Migrating
    nucleo_datalogger.yml to the conventional `arduino_r3` alias is the
    whole fix: no code in board_census.py or analyzer/sockets.py changed,
    only what the content itself is willing to reference against."""
    result = _run("--boards-for", "nucleo_datalogger")
    assert result.returncode == 0, (
        f"--boards-for nucleo_datalogger: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.split() == sorted([
        "frdm_k64f/mk64f12/rig", "nucleo_f401re/stm32f401xe/rig"]), (
        "nucleo_datalogger must now conform to BOTH arduino_r3 boards -- "
        f"the S5 migration's own falsifier\n--- stdout ---\n{result.stdout}")


def test_boards_for_an_unresolved_rig_target_is_a_nonzero_exit_with_list_rigs_own_message() -> None:
    result = _run("--boards-for", "no_such_rig_at_all")
    assert result.returncode != 0
    assert "does not resolve to a rig" in result.stderr


def test_west_rigs_with_no_flag_still_lists_every_rig_unchanged() -> None:
    """Acceptance criterion 2: --boards-for absent behaves exactly as
    today -- the same rig NAMES, one per line. Asserting the count alone
    would hold just as well if the listing started printing board targets
    instead, so the expectation is the names themselves, taken from
    list_rigs (the module `west rigs` renders from) rather than from this
    command's own output."""
    result = _run()
    assert result.returncode == 0
    expected = sorted(
        yaml.safe_load(p.read_text())["rig"]["name"]
        for p in (REPO_ROOT / "boards" / "rigs").glob("*/rig.yml"))
    assert sorted(result.stdout.split()) == expected
