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

from textwrap import dedent

import argparse
import logging
from pathlib import Path

import pytest

from rigc.cli import _configure_logging, build_parser, main


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


def test_board_reading_options_are_now_live(tmp_path: Path) -> None:
    """--board-dts/--build-info/--bindings-dir were inert through R3;
    rigc-r4-brief.md Sec 1 wires them into the board reader. A rig with
    no board-resolution problem of its own (loader accepts cleanly) but
    naming a --board-dts that does not exist on disk must now be rejected
    (exit 1, phys-board) -- proving the option actually reaches
    boarddt.load_board rather than being parsed and discarded. (A rig the
    LOADER itself rejects first -- e.g. unreadable -- still exits 3
    regardless of these options: see test_recipe_resolved_lazily below,
    which is the case that used to make this look inert.)"""
    (tmp_path / "rig.yml").write_text(
        dedent("""\
        rig:
          name: r
          board: some_board/soc/rig
        """))
    (tmp_path / "r.yml").write_text(dedent("""\
        instances: []
        """))
    ret = main(["expand", str(tmp_path / "rig.yml"),
               "--out-dir", str(tmp_path / "out"), *_no_shields(tmp_path),
               "--board-dts", str(tmp_path / "no-such-board.dts")])
    assert ret == 1


def test_recipe_resolved_lazily(tmp_path: Path) -> None:
    """A bogus --build-info path must never crash the run when the rig
    itself is rejected first (here: unreadable) -- the recipe is a
    board-reading concern, resolved only once the loader has already
    accepted, never eagerly alongside the other inputs (cli.py's own
    docstring at the _resolve_recipe call site). Before this was ordered
    correctly, `open()`-ing a nonexistent --build-info path raised an
    unhandled FileNotFoundError -- a traceback, which is never an
    acceptable outcome (rigc-r1-brief.md Sec 1)."""
    ret = main(["expand", str(tmp_path / "no-such-rig.yml"),
               "--out-dir", str(tmp_path / "out"), *_no_shields(tmp_path),
               "--build-info", str(tmp_path / "no-such-build-info.yml")])
    assert ret == 3


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
    (tmp_path / "rig.yml").write_text(dedent("""\
        rig: [this is not, valid: yaml
        """))
    ret, err = _run(capsys, ["expand", str(tmp_path / "rig.yml"),
                             "--out-dir", str(tmp_path / "out"),
                             *_no_shields(tmp_path)])
    assert ret == 3
    assert err.startswith("rigc: not implemented: ")


def test_accept_path_refuses_rather_than_accepting(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Input the loader/analyzer find nothing wrong with must still exit
    3: with no emitter, exit 0 would be a silent lie. Board reading is
    stubbed via monkeypatch rather than a real board .dts + cpp -- board
    reading is integration-only by construction (rigc-r3-brief.md Sec 2's
    cpp/unit-test seam applies here just the same as it does to the
    shield side: reaching real cpp makes a test integration, never unit),
    so THIS invariant (the accept path still refuses) is proven without
    one, and the unit suite stays subprocess-free."""
    import rigc.boarddt
    from rigc.model import Board

    (tmp_path / "rig.yml").write_text(
        dedent("""\
        rig:
          name: r
          board: some_board/soc/rig
        """))
    (tmp_path / "r.yml").write_text(dedent("""\
        instances: []
        """))

    def fake_load_board(name: str, workdir: str, board_dts=None, recipe=None):
        return Board(name=name, sockets={}), [], frozenset()

    monkeypatch.setattr(rigc.boarddt, "load_board", fake_load_board)

    ret, err = _run(capsys, ["expand", str(tmp_path / "rig.yml"),
                             "--out-dir", str(tmp_path / "out"),
                             *_no_shields(tmp_path)])
    assert ret == 3
    assert err.startswith("rigc: not implemented: ")


# --------------------------------------------------- logging (rigc-r45-brief.md Part B)

def test_stderr_carries_only_renderer_bytes_when_rigc_log_is_unset(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The stderr-purity discipline test: with RIGC_LOG unset, the package
    root's NullHandler (rigc/__init__.py) is the only handler on the
    `rigc` tree, so a full main() run over a REJECTING input puts ONLY
    the renderer's own bytes on stderr -- while caplog, which taps
    Python's real root logger independently of our own (silent) handler,
    still observes that the pipeline actually emitted records, proving
    this is a "nothing configured" outcome rather than "nothing
    happened"."""
    monkeypatch.delenv("RIGC_LOG", raising=False)
    caplog.set_level(logging.DEBUG, logger="rigc")

    (tmp_path / "rig.yml").write_text("not-rig: {}\n")
    ret, err = _run(capsys, ["expand", str(tmp_path / "rig.yml"),
                            "--out-dir", str(tmp_path / "out"),
                            *_no_shields(tmp_path)])

    assert ret == 1
    assert "error[lang-schema]" in err
    # ONLY renderer bytes -- none of our own log formatting leaked in.
    assert "INFO" not in err
    assert "DEBUG" not in err
    assert "rigc.cli" not in err
    assert "rigc.loader" not in err
    # ...yet the pipeline really did log: caplog observed the records via
    # propagation, entirely independent of the (silent) handler above.
    assert any("argv" in m for m in caplog.messages)
    assert any(r.name == "rigc.loader" for r in caplog.records)


def test_rigc_log_env_attaches_a_real_stderr_handler(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RIGC_LOG=<level> is the ONLY way a real handler ever reaches the
    `rigc` logger tree -- read fresh at the top of every main() call (not
    at import time), so this is observable without a subprocess."""
    monkeypatch.setenv("RIGC_LOG", "debug")

    main(["expand", str(tmp_path / "no-such-rig.yml"),
         "--out-dir", str(tmp_path / "out"), *_no_shields(tmp_path)])

    root = logging.getLogger("rigc")
    real_handlers = [h for h in root.handlers
                     if isinstance(h, logging.StreamHandler)
                     and not isinstance(h, logging.NullHandler)]
    assert len(real_handlers) == 1
    assert root.getEffectiveLevel() == logging.DEBUG

    # Deterministic cleanup -- a repeated main() call always re-derives
    # its handler state from the CURRENT environment, so unsetting and
    # calling _configure_logging() again leaves the logger tree exactly
    # as every OTHER test in this module expects to find it.
    monkeypatch.delenv("RIGC_LOG")
    _configure_logging()
