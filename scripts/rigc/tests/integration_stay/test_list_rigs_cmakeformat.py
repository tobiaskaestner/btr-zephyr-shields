"""list_rigs.py's own CLI: the
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

from harness import REPO_ROOT, WEST_TOPDIR, subprocess_timeout


def _cmake_list_escape(value: str) -> str:
    """A test-local copy of `list_rigs._cmake_list_escape` -- duplicated
    rather than imported so this module (analyzed by mypy under `scripts/
    rigc`) never pulls the untyped `list_rigs.py` script into mypy's
    graph; this file already drives that module as a real subprocess for
    everything else, so a bare-bones copy of its one pure helper is the
    lowest-risk way to compute the SAME expected escaped bytes without a
    second authority for what escaping means -- both must produce
    identical output for `test_cmakeformat_line_for_a_list_target`'s own
    assertion to mean anything, which is exactly what this docstring pins
    down as the contract between the two copies."""
    escaped = value
    for _ in range(2):
        escaped = escaped.replace(";", "\\;")
    return escaped


_LIST_RIGS = REPO_ROOT / "scripts" / "list_rigs.py"
_VENV_PYTHON = WEST_TOPDIR / ".venv" / "bin" / "python3"
_CMAKEFORMAT = "{NAME};{DIR};{BOARD};{REVISION};{VARIANT};{PROMOTED}"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
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


def test_cmakeformat_line_for_a_slot_optioned_plural_shield_target() -> None:
    """The `{PROMOTED}` line for a
    plural shield's slot-optioned target -- whole-line pin, following
    the revved-promoted precedent above (test_cmakeformat_line_for_a_
    revved_promoted_shield's own docstring: it caught a real desugaring
    bug once, which is why whole-line). `resolve_target` forwards the
    raw opts text VERBATIM into `PromotedTarget.promotion_target`
    (cmake never parses the option grammar -- rigc's own --promote does,
    once), so the socket.<slot>= spelling survives this seam untouched."""
    result = _run("--rig=can_span_click:socket.left=quail_sock2:"
                 "socket.right=quail_sock3",
                 f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "NAME;can_span_click;DIR;NOTFOUND;BOARD;NOTFOUND;"
        "REVISION;NOTFOUND;VARIANT;NOTFOUND;"
        "PROMOTED;can_span_click:socket.left=quail_sock2:"
        "socket.right=quail_sock3")


def test_cmakeformat_line_for_a_bare_socket_on_a_plural_shield_is_refused() -> None:
    """The cmake seam's own refusal for the same malformed target
    test_boards_for.py pins at query level -- `resolve_target` reaches
    `parse_promotion_opts` with the resolved shield's real slots, so the
    plural-shield sentence fires here too, before any expander runs."""
    result = _run("--rig=can_span_click:socket=quail_sock2",
                  f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "plugs 2 sockets" in result.stderr


def test_cmakeformat_line_for_a_persisted_rig_is_unchanged() -> None:
    """A real rig's own line
    carries PROMOTED;NOTFOUND and is otherwise byte-identical to what this
    same CLI printed before promoted shields existed -- true of NAME/DIR/
    REVISION/VARIANT/PROMOTED, all still resolved from rig.yml alone.

    BOARD is the one field that differs: no corpus rig.yml declares a
    board at all, so this bare `list_rigs.py --rig=` query (no --board
    injection -- it has none to give) reads it back the same way it
    already does for a promoted shield: NOTFOUND. This is the same fact
    boards.cmake's own fork hits for every persisted rig, which is
    what makes its "no board of its own to fall back to" FATAL fire for a
    real rig, not just a promoted shield."""
    result = _run("--rig=nucleo_datalogger", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    line = result.stdout.strip()
    assert line.endswith(";PROMOTED;NOTFOUND")
    assert line.startswith("NAME;nucleo_datalogger;DIR;")
    assert "DIR;NOTFOUND" not in line
    assert ";BOARD;NOTFOUND;" in line


def test_a_variant_qualified_shield_target_is_refused() -> None:
    result = _run("--rig=adafruit_data_logger/some_variant",
                  f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "variant" in result.stderr


def test_a_name_that_is_both_a_rig_and_a_shield_is_the_explain_message(
        tmp_path: Path) -> None:
    """The SAME message `west rigs --explain` renders for the
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


# --------------------------------------------------- list promotion

def test_cmakeformat_line_for_a_list_target() -> None:
    """The `{PROMOTED}` value for a list
    target is the raw `;`-joined text, escaped via `_cmake_list_escape`
    (the ONE field this hazard ever touches -- NAME is the `+`-joined
    desugared rig name, which never contains a `;`). Whole-line pin,
    following the revved-promoted precedent (it caught a real
    desugaring bug once, which is why whole-line)."""
    result = _run("--rig=eth_click;flash_click", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "NAME;eth_click+flash_click;DIR;NOTFOUND;BOARD;NOTFOUND;"
        "REVISION;NOTFOUND;VARIANT;NOTFOUND;"
        f"PROMOTED;{_cmake_list_escape('eth_click;flash_click')}")


def test_cmakeformat_line_for_a_list_target_with_per_element_options() -> None:
    raw = "eth_click:socket=quail_sock1;flash_click:socket=quail_sock2"
    result = _run(f"--rig={raw}", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "NAME;eth_click+flash_click;DIR;NOTFOUND;BOARD;NOTFOUND;"
        "REVISION;NOTFOUND;VARIANT;NOTFOUND;"
        f"PROMOTED;{_cmake_list_escape(raw)}")


def test_a_list_target_with_a_duplicate_element_is_refused() -> None:
    result = _run("--rig=eth_click;eth_click", f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "eth_click" in result.stderr
    assert "more than once" in result.stderr


def test_a_list_target_with_a_persisted_rig_element_is_refused() -> None:
    """Every element must be a SHIELD: naming a real, persisted
    rig inside a list gets its own sentence, distinct from the ordinary
    "promotion options on a persisted rig" refusal a bare rig target
    hits (that refusal is about OPTIONS on a single rig target; this one
    is about a rig appearing as one element of a list at all)."""
    result = _run("--rig=eth_click;nucleo_datalogger",
                  f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "nucleo_datalogger" in result.stderr
    assert "names a persisted rig" in result.stderr
    assert "every element of a list promotion target must be a shield" in result.stderr


def test_a_list_target_with_an_unknown_element_is_refused() -> None:
    result = _run("--rig=eth_click;no_such_shield_at_all",
                  f"--cmakeformat={_CMAKEFORMAT}")
    assert result.returncode != 0
    assert "no_such_shield_at_all" in result.stderr
    assert "does not name a discoverable shield" in result.stderr
