"""The edtlib READ side: guards over boarddt/board_edt/edt_build, the
layer that projects a real board's own devicetree onto model.Board.

  * a real, PLAIN (no shield, no rig) west build --cmake-only per board
    must configure clean -- the safety net a rig-enabling board change must
    never break. plain_build (session-cached via conftest.plain_build_for)
    performs + asserts this.

  * the edt.pickle cross-check: the standalone edtlib.EDT this reader
    builds -- read through the PRODUCTION entry point, boarddt.load_board,
    exactly as the expander itself calls it -- must agree with pass-2's OWN
    edt.pickle from the same board, on every rig-relevant projection
    (socket paths, gpio-map, bus phandles, cs-pool). This is the proof that
    the pass-1 recipe (cmake/dts.cmake's fork derives it from the real
    pre_dt outputs; standalone runs derive it from a cached build's
    build_info.yml) is equivalent to pass 2's real one -- if it weren't,
    pass 1 could read a socket that pass 2 never actually builds against.

  * the production-plumbing guard: for every board, boarddt.load_board
    (given the same --board-dts + recipe the dts.cmake fork would pass)
    must produce the exact same model.Board as a DIRECT
    board_edt.load_board call -- boarddt.load_board is a thin board-
    resolution wrapper over board_edt, and this pins that the wrapping
    introduces no divergence.

A pure-function unit test of edt_build.recipe_from_build_info itself lives
in test_edt_build.py instead -- it has no rigexp product dependency at all,
so it travels with the BSD-3 reader layer rather than this file's
product-layer guards.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pytest

from conftest import BOARD_DTS, BOARDS, REPO_ROOT, PlainBuild, plain_build_for

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import board_edt, boarddt, edt_build  # noqa: E402
from rigexp.diag import Diagnostics  # noqa: E402

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- plain-build fixture


@pytest.fixture(params=BOARDS, ids=BOARDS)
def plain_build(request: "pytest.FixtureRequest",
                tmp_path_factory: "pytest.TempPathFactory") -> PlainBuild:
    """Per-board plain build, session-memoized by conftest.plain_build_for
    -- other test files (test_emitted_corpus.py) request the SAME cached
    build for their own rigs naming this board, rather than configuring it
    again."""
    return plain_build_for(request.param, tmp_path_factory)


@pytest.mark.build
def test_plain_build_configures_clean(plain_build: PlainBuild) -> None:
    """The fixture performs + asserts the configure; this test exists so a
    plain-build failure is its own reported item, not just an error while
    setting up the tests below."""
    assert (plain_build.build_dir / "zephyr" / "zephyr.dts").is_file()
    assert plain_build.build_info.is_file()
    assert plain_build.edt_pickle.is_file()


# ---------------------------------------------------------------- edt.pickle cross-check


@pytest.mark.build
def test_edt_pickle_cross_check(plain_build: PlainBuild, tmp_path: Path) -> None:
    """Pass-1, read through the PRODUCTION path (boarddt.load_board, with
    the recipe recovered out of the SAME build's build_info.yml) must
    agree with pass-2's OWN edt.pickle, for every board, on the
    rig-relevant projection: socket node paths, gpio-map entries, bus
    phandle targets, cs-pool values. A divergence here would mean pass 1 can
    read a socket, controller, or cs-pool default that pass 2's real build
    never actually sees -- exercises the wired-up production entry point,
    complementing the narrower guard in test_production_matches_direct_read
    below."""
    with open(plain_build.edt_pickle, "rb") as f:
        pass2_edt = pickle.load(f)
    pass2_board = board_edt.project_edt(pass2_edt, plain_build.board)

    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])
    diags = Diagnostics()
    standalone_board = boarddt.load_board(
        plain_build.board, str(tmp_path / "boarddt"), diags,
        board_dts=dts_path, recipe=recipe)
    assert standalone_board is not None, (
        f"boarddt.load_board({plain_build.board!r}) failed:\n{diags.render()}")

    assert standalone_board.sockets.keys() == pass2_board.sockets.keys()
    for label, standalone_socket in standalone_board.sockets.items():
        pass2_socket = pass2_board.sockets[label]
        assert standalone_socket.path == pass2_socket.path, (
            f"{plain_build.board}/{label}: socket node path differs "
            f"(standalone={standalone_socket.path} pass2={pass2_socket.path})")
        assert standalone_socket.gpio_map == pass2_socket.gpio_map, (
            f"{plain_build.board}/{label}: gpio-map entries differ from "
            f"pass-2's edt.pickle")
        assert standalone_socket.buses == pass2_socket.buses, (
            f"{plain_build.board}/{label}: bus phandle targets differ from "
            f"pass-2's edt.pickle")
        assert standalone_socket.cs_pool == pass2_socket.cs_pool, (
            f"{plain_build.board}/{label}: cs-pool differs from pass-2's "
            f"edt.pickle (standalone={standalone_socket.cs_pool} "
            f"pass2={pass2_socket.cs_pool})")


# ---------------------------------------------------------------- production-plumbing guard


@pytest.mark.build
def test_production_matches_direct_read(plain_build: PlainBuild,
                                        tmp_path: Path) -> None:
    """boarddt.load_board (what the expander actually calls) is a thin
    board-resolution wrapper over board_edt.load_board -- assert they
    produce the identical model.Board, given the same board-dts + recipe,
    so that wrapping can never introduce a divergence between what the
    expander sees and what a direct board_edt read would see."""
    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])

    diags = Diagnostics()
    production = boarddt.load_board(
        plain_build.board, str(tmp_path / "production"), diags,
        board_dts=dts_path, recipe=recipe)
    assert production is not None, (
        f"boarddt.load_board({plain_build.board!r}) failed:\n{diags.render()}")

    direct = board_edt.load_board(
        plain_build.board, dts_path, recipe, str(tmp_path / "direct"))

    assert production == direct
