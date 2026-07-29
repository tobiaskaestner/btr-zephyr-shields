"""Unit: cli — the frozen front door.

Two contracts live here, both cli.py's own: the frozen argv surface
(`expand <rig_yml>` + the nine options, asserted in-process via
build_parser()/main(), no subprocess) and the loud-refusal behaviour of
unimplemented paths (exit 3, single-line `rigc: not implemented: <what>`
on stderr, never a traceback, never exit 1, never a silent accept).

Every `main([...])` call below passes an EXPLICIT `--shield-dir` pointing
at an empty/nonexistent directory (`_no_shields`) -- R3 makes shield-dir
scanning live (it runs unconditionally, before rig.yml even opens), and
the CLI's own bare-invocation fallback is the vendored PRODUCTION shield
library (`loader/library.py`'s `SHIELDS_DIR`, direct-API/test use only per
its own docstring). Omitting `--shield-dir` here would make these unit
tests silently scan and cpp-parse real repo shield content -- a
subprocess call and a hermeticity violation both, so every call site
supplies one (`glob.glob` on a directory that does not exist just returns
`[]`, no error -- the directory need not exist, only be named).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from rigc.cli import build_parser, main


def _no_shields(tmp_path: Path) -> list[str]:
    """Point EVERY library root that has a production fallback at an
    empty directory -- --shield-dir alone is not enough: --connector-dir
    has the identical None-falls-back-to-the-real-tree shape
    (cli._expand -> load_types -> registry.BINDINGS), so omitting it made
    the unit suite read production connector bindings and headers (R3
    review finding D2). A unit test touches NO production data."""
    empty = tmp_path / "no_library_here"
    return ["--shield-dir", str(empty),
            "--connector-dir", str(empty),
            "--include-dir", str(empty)]


def _parse(extra: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(
        ["expand", "rig.yml", "--out-dir", "out", *extra])


# --------------------------------------------------------- the argv surface

def test_positional_rig_and_out_dir() -> None:
    args = _parse([])
    assert args.command == "expand"
    assert args.rig == "rig.yml"
    assert args.out_dir == "out"


def test_defaults_are_none() -> None:
    args = _parse([])
    assert args.shield_dirs is None
    assert args.board_dts is None
    assert args.build_info is None
    assert args.bindings_dirs is None
    assert args.include_dirs is None
    assert args.connector_dirs is None
    assert args.revision is None
    assert args.variant is None


def test_repeatable_options_accumulate_in_order() -> None:
    args = _parse(["--shield-dir", "s1", "--shield-dir", "s2",
                   "--bindings-dir", "b1", "--bindings-dir", "b2",
                   "--include-dir", "i1", "--include-dir", "i2",
                   "--connector-dir", "c1", "--connector-dir", "c2"])
    assert args.shield_dirs == ["s1", "s2"]
    assert args.bindings_dirs == ["b1", "b2"]
    assert args.include_dirs == ["i1", "i2"]
    assert args.connector_dirs == ["c1", "c2"]


def test_single_valued_options() -> None:
    args = _parse(["--board-dts", "b.dts", "--build-info", "bi.yml",
                   "--revision", "2", "--variant", "b"])
    assert args.board_dts == "b.dts"
    assert args.build_info == "bi.yml"
    assert args.revision == "2"
    assert args.variant == "b"


def test_out_dir_is_required() -> None:
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["expand", "rig.yml"])
    assert e.value.code == 2


def test_subcommand_is_required() -> None:
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args([])
    assert e.value.code == 2


def test_unknown_option_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as e:
        _parse(["--no-such-flag"])
    assert e.value.code == 2


def test_unknown_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["translate", "rig.yml"])
    assert e.value.code == 2


def test_main_is_callable_in_process(tmp_path: Path) -> None:
    """main(argv) -> int -- returns rather than raises for every
    non-usage outcome (here: an unimplemented path, exit code 3)."""
    ret = main(["expand", str(tmp_path / "no-such-rig.yml"),
                "--out-dir", str(tmp_path / "out"), *_no_shields(tmp_path)])
    assert isinstance(ret, int)
    assert ret == 3


def test_inert_options_are_accepted(tmp_path: Path) -> None:
    """--board-dts/--build-info/--bindings-dir have no R3 subsystem yet:
    parse and change nothing. Both calls below pass the SAME (empty)
    --shield-dir/--connector-dir/--include-dir, since those three ARE
    live as of R3 (the shield library + registry) -- this comparison
    isolates the genuinely still-inert three."""
    common = ["--out-dir", str(tmp_path / "out"), *_no_shields(tmp_path),
             "--connector-dir", str(tmp_path / "no_connectors_here"),
             "--include-dir", str(tmp_path / "no_includes_here")]
    rig = tmp_path / "no-such-rig.yml"
    bare = main(["expand", str(rig), *common])
    loaded = main(["expand", str(rig),
                   "--board-dts", "b.dts", "--build-info", "bi.yml",
                   "--bindings-dir", "bd",
                   *common])
    assert bare == loaded == 3


# ------------------------------------------------- loud, distinct refusals

def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str]:
    ret = main(argv)
    captured = capsys.readouterr()
    assert captured.out == ""          # diagnostics and refusals: stderr only
    return ret, captured.err


def test_unreadable_rig_refuses(tmp_path: Path,
                                capsys: pytest.CaptureFixture[str]) -> None:
    ret, err = _run(capsys, ["expand", str(tmp_path / "absent.yml"),
                             "--out-dir", str(tmp_path / "out"),
                             *_no_shields(tmp_path)])
    assert ret == 3
    assert err.startswith("rigc: not implemented: ")
    assert len(err.splitlines()) == 1  # one line -- never a traceback


def test_out_of_scope_feature_refuses(tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    """R3 closes the ShieldRef seam (params:/pin: are fully implemented
    now, the R2-era example this test used to exercise) -- a YAML parse
    failure is the capability that stays Unimplemented (rigc-r2-brief.md
    Sec 2: no frozen golden covers lang-parse wording, so Unimplemented
    remains the deliberate, always-acceptable choice, unrevisited by R3)."""
    (tmp_path / "rig.yml").write_text("rig: [this is not, valid: yaml\n")
    ret, err = _run(capsys, ["expand", str(tmp_path / "rig.yml"),
                             "--out-dir", str(tmp_path / "out"),
                             *_no_shields(tmp_path)])
    assert ret == 3
    assert err.startswith("rigc: not implemented: ")


def test_accept_path_refuses_rather_than_accepting(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Input the R1 sliver finds nothing wrong with must still exit 3:
    with no analyzer/emitter, exit 0 would be a silent lie."""
    (tmp_path / "rig.yml").write_text(
        "rig:\n"
        "  name: r\n"
        "  board: some_board/soc/rig\n")
    (tmp_path / "r.yml").write_text("instances: []\n")
    ret, err = _run(capsys, ["expand", str(tmp_path / "rig.yml"),
                             "--out-dir", str(tmp_path / "out"),
                             *_no_shields(tmp_path)])
    assert ret == 3
    assert err.startswith("rigc: not implemented: ")
