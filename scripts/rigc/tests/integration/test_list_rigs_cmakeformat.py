"""list_rigs.py's own CLI (board-coordinate-s3b-brief.md ruling 3): the
`--rig=<target> --cmakeformat=...` line cmake/boards.cmake's and
cmake/dts.cmake's forks actually read via `execute_process`, driven here
as a real subprocess -- resolution only, no cmake, no cpp, no board, so
NOT build-marked.

`resolve_target` supersedes a bare `resolve_rig_target` as this module's
own `-DRIG=<target>` entry point; these tests are the falsifier that the
`{PROMOTED}` key it adds, and the "one namespace rule" it shares with
`west rigs --explain` (test_explain.py), actually reach the literal bytes
a cmake `execute_process` call sees -- never exercised by an in-process
call to `resolve_target` alone.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import REPO_ROOT, WEST_TOPDIR, subprocess_timeout

_LIST_RIGS = REPO_ROOT / "scripts" / "list_rigs.py"
_VENV_PYTHON = WEST_TOPDIR / ".venv" / "bin" / "python3"
_CMAKEFORMAT = "{NAME};{DIR};{BOARD};{REVISION};{VARIANT};{PROMOTED}"


def _run(*args: str) -> "subprocess.CompletedProcess[str]":
    cmd = [str(_VENV_PYTHON), str(_LIST_RIGS),
           f"--board-root={REPO_ROOT}", *args]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                          text=True, timeout=subprocess_timeout(60))


def test_cmakeformat_line_for_a_promoted_shield() -> None:
    result = _run("--rig=adafruit_data_logger", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "NAME;adafruit_data_logger;DIR;NOTFOUND;BOARD;NOTFOUND;"
        "REVISION;NOTFOUND;VARIANT;NOTFOUND;PROMOTED;adafruit_data_logger")


def test_cmakeformat_line_for_a_revved_promoted_shield() -> None:
    result = _run("--rig=i2c_sensor@2", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "NAME;i2c_sensor;DIR;NOTFOUND;BOARD;NOTFOUND;"
        "REVISION;2;VARIANT;NOTFOUND;PROMOTED;i2c_sensor")


def test_cmakeformat_line_for_a_persisted_rig_is_unchanged() -> None:
    """Criterion 4: a real rig's own line carries PROMOTED;NOTFOUND and is
    otherwise byte-identical to what this same CLI printed before
    promoted shields existed."""
    result = _run("--rig=nucleo_datalogger", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    line = result.stdout.strip()
    assert line.endswith(";PROMOTED;NOTFOUND")
    assert line.startswith("NAME;nucleo_datalogger;DIR;")
    assert "DIR;NOTFOUND" not in line
    assert ";BOARD;nucleo_f401re/stm32f401xe/rig;" in line


def test_a_variant_qualified_shield_target_is_refused() -> None:
    result = _run("--rig=adafruit_data_logger/some_variant",
                  f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "variant" in result.stderr


def test_a_name_that_is_both_a_rig_and_a_shield_is_the_explain_message(
        tmp_path: Path) -> None:
    """Criterion 5: the SAME message `west rigs --explain` renders for the
    identical collision (test_explain.py's own fixture, reproduced here
    against this module's CLI instead) -- one namespace rule, not two
    independently-worded ones."""
    rig_dir = tmp_path / "boards" / "rigs" / "adafruit_data_logger"
    rig_dir.mkdir(parents=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: adafruit_data_logger\n")

    result = subprocess.run(
        [str(_VENV_PYTHON), str(_LIST_RIGS), f"--board-root={REPO_ROOT}",
         f"--board-root={tmp_path}", "--rig=adafruit_data_logger",
         f"--cmakeformat={_CMAKEFORMAT}"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        timeout=subprocess_timeout(60))
    assert result.returncode != 0
    assert "both" in result.stderr
    assert str(rig_dir) in result.stderr


def test_a_name_that_is_neither_reuses_the_existing_message() -> None:
    result = _run("--rig=no_such_target_at_all", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "does not resolve to a rig" in result.stderr


def test_bare_rig_flag_with_no_cmakeformat_still_prints_just_the_name() -> None:
    """The other query mode (no --cmakeformat): unaffected by any of the
    above, for both a rig and a promoted shield."""
    rig_result = _run("--rig=nucleo_datalogger")
    assert rig_result.returncode == 0, rig_result.stderr
    assert rig_result.stdout.strip() == "nucleo_datalogger"

    shield_result = _run("--rig=adafruit_data_logger")
    assert shield_result.returncode == 0, shield_result.stderr
    assert shield_result.stdout.strip() == "adafruit_data_logger"
