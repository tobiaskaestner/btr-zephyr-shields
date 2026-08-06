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
    ("nucleo_datalogger", "nucleo_f401re/stm32f401xe/rig"),
    ("lotus_buttons", "seeeduino_lotus/samd21g18a/rig"),
    ("quail_temp_farm", "mikroe_quail/stm32f427xx/rig"),
])
def test_boards_for_the_criterion_answers(rig_target: str, expected_board: str) -> None:
    """Acceptance criterion 3, verbatim."""
    result = _run("--boards-for", rig_target)
    assert result.returncode == 0, (
        f"--boards-for {rig_target}: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == expected_board


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
