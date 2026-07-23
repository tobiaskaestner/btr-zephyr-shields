"""Bridge-A rewrite, phase 1 -- the edtlib READ side, POST-FLIP
(`claude/rigs/implementation-plan.md`, "Bridge-A deconstruction / edtlib
rewrite"). Renamed from test_board_dualread.py: THE FLIP retired the
`common-dts` scaffold this file used to compare against (saferail 8 --
deleted in full), so there is no more "dual" to read. What remains, and what
this file now guards:

  * saferail 11: a real, PLAIN (no shield, no rig) `west build --cmake-only`
    per board must configure clean -- the safety net a board conversion must
    never break. `plain_build` (session-cached via `conftest.plain_build_for`)
    performs + asserts this.

  * saferail 3: the edt.pickle cross-check. The standalone `edtlib.EDT` this
    reader builds -- now read through the PRODUCTION entry point,
    `boarddt.load_board`, exactly as the expander itself calls it -- must
    agree with pass-2's OWN `edt.pickle` from the same board: proof that
    `cmake/rig.cmake`'s mirrored recipe (saferail 13) is equivalent to
    `dts.cmake`'s real one.

  * `test_recipe_from_build_info`: a pure-function unit test for
    `edt_build.recipe_from_build_info`.

  * the production-plumbing guard that REPLACED the shadow dual-read
    (saferail 2/6): for every board, `boarddt.load_board` (given the same
    `--board-dts` + recipe rig.cmake would pass) must produce the exact same
    `model.Board` as a DIRECT `board_edt.load_board` call -- the flip
    changed WHO calls board_edt, never what it returns.
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


# ---------------------------------------------------------------- fast unit test


def test_recipe_from_build_info(tmp_path: Path) -> None:
    """Pure-function unit, no cmake: `recipe_from_build_info` reads exactly
    the `cmake.devicetree.include-dirs` / `bindings-dirs` keys a real
    `build_info.yml` carries (shape verified against an actual build --
    see the handoff report), against a tiny hand-written fixture."""
    build_info = tmp_path / "build_info.yml"
    build_info.write_text(
        "cmake:\n"
        "  devicetree:\n"
        "    include-dirs:\n"
        "      - /a/include\n"
        "      - /b/include\n"
        "    bindings-dirs:\n"
        "      - /a/dts/bindings\n"
        "      - /b/dts/bindings\n")
    recipe = edt_build.recipe_from_build_info(str(build_info))
    assert recipe.include_dirs == ["/a/include", "/b/include"]
    assert recipe.bindings_dirs == ["/a/dts/bindings", "/b/dts/bindings"]


# ---------------------------------------------------------------- plain-build fixture


@pytest.fixture(params=BOARDS, ids=BOARDS)
def plain_build(request: "pytest.FixtureRequest",
                tmp_path_factory: "pytest.TempPathFactory") -> PlainBuild:
    """Per-board plain build, session-memoized by `conftest.plain_build_for`
    -- other test files (test_tier1_goldens.py) request the SAME cached
    build for their own rigs naming this board, rather than configuring it
    again."""
    return plain_build_for(request.param, tmp_path_factory)


@pytest.mark.build
def test_plain_build_configures_clean(plain_build: PlainBuild) -> None:
    """The fixture performs + asserts the configure; this test exists so a
    plain-build failure is its own reported item (saferail 11), not just an
    error while setting up the tests below."""
    assert (plain_build.build_dir / "zephyr" / "zephyr.dts").is_file()
    assert plain_build.build_info.is_file()
    assert plain_build.edt_pickle.is_file()


# ---------------------------------------------------------------- saferail 3: edt.pickle


@pytest.mark.build
def test_edt_pickle_cross_check(plain_build: PlainBuild, tmp_path: Path) -> None:
    """Pass-1, read through the PRODUCTION path (`boarddt.load_board`, with
    the recipe recovered out of the SAME build's `build_info.yml`) must
    agree with pass-2's OWN `edt.pickle`, for the rig-relevant projection:
    socket node paths, gpio-map entries, bus phandle targets, cs-pool
    values. Follows the nucleo spike's comparison approach, generalized to
    all four boards -- now exercising the wired-up production entry point
    rather than calling board_edt directly (that narrower guard is
    test_production_matches_direct_read below)."""
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
    """The guard that REPLACED the shadow dual-read (saferail 2/6): THE FLIP
    means `boarddt.load_board` (what the expander actually calls) now IS
    `board_edt.load_board` plus board resolution -- assert they produce the
    identical `model.Board`, given the same board-dts + recipe, proving the
    flip changed WHO calls board_edt, never what it returns."""
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
