"""Board resolution's own value-shaped decision points (rigc-r4-brief.md
Sec 1): board.load_board's early-exit shapes (a --board-dts naming no
real file; no usable recipe) need no real devicetree or edtlib call at
all to reach, so they are asserted directly. The success / not-rig-
enabled outcomes DO need board_edt.load_board's own result -- stubbed via
monkeypatch here rather than a real board .dts + cpp, exactly like
cli.py's own `test_accept_path_refuses_rather_than_accepting` does: board
reading invokes cpp, so it is integration-only by construction
(rigc-r3-brief.md Sec 2's cpp/unit-test seam applies to the board side
just as it does to the shield side) -- `_discover_board_dts` itself
(zephyr's list_boards.py over a real MODULE_ROOT scan) is exercised only
by the frozen suite's own unknown-board golden, never here.

Wording stays out of these tests (mission brief Sec 6); code, return
shape, and which branch fired are what's asserted -- the hand-differential
rule (rigc-r4-brief.md Sec 7) is what verifies wording for the two shapes
with no frozen golden (no-recipe, missing-file), recorded in the slice
report."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from rigc import boarddt
from rigc.edt_build import BuildRecipe
from rigc.model import Board, BoardSocket


def test_missing_board_dts_file_is_phys_board_with_no_edtlib_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A --board-dts naming a file that does not exist is caught before
    ANY devicetree machinery runs -- board_edt.load_board is never even
    imported down to a call, proven by monkeypatching it to explode if
    reached."""
    def _boom(*a: object, **kw: object) -> Board:
        raise AssertionError("board_edt.load_board must not be called")

    monkeypatch.setattr("rigc.board_edt.load_board", _boom)

    board, diags, deps = boarddt.load_board(
        "some_board", str(tmp_path),
        board_dts=str(tmp_path / "no-such-file.dts"),
        recipe=BuildRecipe(include_dirs=[], bindings_dirs=[]))

    assert board is None
    assert deps == frozenset()
    assert len(diags) == 1
    assert diags[0].code == "phys-board"


def test_no_recipe_is_phys_board_with_no_edtlib_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """recipe=None (a caller-configuration gap: neither --build-info nor
    --include-dir/--bindings-dir was usable) is its own phys-board
    diagnostic, reached before any devicetree read is attempted."""
    def _boom(*a: object, **kw: object) -> Board:
        raise AssertionError("board_edt.load_board must not be called")

    monkeypatch.setattr("rigc.board_edt.load_board", _boom)

    real_dts = tmp_path / "board.dts"
    real_dts.write_text("/dts-v1/;\n/ {};\n")

    board, diags, deps = boarddt.load_board(
        "some_board", str(tmp_path), board_dts=str(real_dts), recipe=None)

    assert board is None
    assert deps == frozenset()
    assert len(diags) == 1
    assert diags[0].code == "phys-board"


def test_a_board_with_no_socket_nodes_is_not_rig_enabled(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Conv. 4's opt-in mechanism: a board .dts that exists and reads
    clean but declares no socket,* node is the DISTINCT "exists, but is
    not rig-enabled" diagnostic -- never confused with "unknown board"."""
    real_dts = tmp_path / "board.dts"
    real_dts.write_text("/dts-v1/;\n/ {};\n")
    monkeypatch.setattr(
        "rigc.board_edt.load_board",
        lambda name, dts_path, recipe, workdir: Board(name=name, sockets={}))

    board, diags, deps = boarddt.load_board(
        "socketless_board", str(tmp_path), board_dts=str(real_dts),
        recipe=BuildRecipe(include_dirs=[], bindings_dirs=[]))

    assert board is None
    assert len(diags) == 1
    assert diags[0].code == "phys-board"
    assert "not rig-enabled" in diags[0].message
    # dependency data is recorded even on THIS rejection -- the board's
    # own .dts was genuinely read.
    assert deps == frozenset({os.path.abspath(str(real_dts))})


def test_a_board_with_sockets_loads_clean(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_dts = tmp_path / "board.dts"
    real_dts.write_text("/dts-v1/;\n/ {};\n")
    fake_board = Board(name="b", sockets={
        "ard": BoardSocket(label="ard", path="/ard", type_name="t",
                          gpio_map={}, buses={}, cs_pool=None)})
    monkeypatch.setattr(
        "rigc.board_edt.load_board",
        lambda name, dts_path, recipe, workdir: fake_board)

    board, diags, deps = boarddt.load_board(
        "some_board", str(tmp_path), board_dts=str(real_dts),
        recipe=BuildRecipe(include_dirs=[], bindings_dirs=[]))

    assert board is fake_board
    assert diags == []
    assert deps == frozenset({os.path.abspath(str(real_dts))})
