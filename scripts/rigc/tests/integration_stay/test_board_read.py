"""The edtlib READ side: guards over resolve/project/edt_build, the
layer that projects a real board's own devicetree onto model.Board.

  * a real, PLAIN (no shield, no rig) west build --cmake-only per board
    must configure clean -- the safety net a rig-enabling board change must
    never break. plain_build (session-cached via corpus.plain_build_for)
    performs + asserts this.

  * the edt.pickle cross-check: the standalone edtlib.EDT this reader
    builds -- read through the PRODUCTION entry point, resolve.load_board,
    exactly as the expander itself calls it -- must agree with pass-2's OWN
    edt.pickle from the same board, on every rig-relevant projection
    (socket paths, gpio-map, bus phandles, cs-pool). This is the proof that
    the pass-1 recipe (cmake/dts.cmake's fork derives it from the real
    pre_dt outputs; standalone runs derive it from a cached build's
    build_info.yml) is equivalent to pass 2's real one -- if it weren't,
    pass 1 could read a socket that pass 2 never actually builds against.

  * the production-plumbing guard: for every board, resolve.load_board
    (given the same --board-dts + recipe the dts.cmake fork would pass)
    must produce the exact same model.Board as a DIRECT
    project.load_board call -- resolve.load_board is a thin board-
    resolution wrapper over project, and this pins that the wrapping
    introduces no divergence.

  * the census-vs-DT-truth guard: census's text-only scan of a board
    rig-extension's *.dts/*.dtsi
    fragments -- what `west rigs --boards-for` runs against, since a real
    per-board read costs a cmake configure per candidate -- must agree
    with project's own projection of the REAL edtlib.EDT, on every field
    the census actually populates (defining label, DASHED type_name,
    sorted bus KINDS, alias map). This is the only guard keeping a text
    scanner honest against the devicetree it stands in for.

A pure-function unit test of edt_build.recipe_from_build_info itself lives
in tests/unit/test_edt_build.py instead -- it has no rigc product
dependency at all, so it travels with the BSD-3 reader layer rather than
this file's product-layer guards.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pytest
from corpus import BOARD_DTS, BOARDS, PlainBuild, plain_build_for
from harness import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.board import census, edt_build, project, resolve  # noqa: E402
from rigc.diag import render  # noqa: E402

# ---------------------------------------------------------------- plain-build fixture


@pytest.fixture(params=BOARDS, ids=BOARDS)
def plain_build(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> PlainBuild:
    """Per-board plain build, session-memoized by corpus.plain_build_for
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
    """Pass-1, read through the PRODUCTION path (resolve.load_board, with
    the recipe recovered out of the SAME build's build_info.yml) must
    agree with pass-2's OWN edt.pickle, for every board, on the
    rig-relevant projection: socket node paths, gpio-map entries, bus
    phandle targets, cs-pool values. A divergence here would mean pass 1 can
    read a socket, controller, or cs-pool default that pass 2's real build
    never actually sees -- exercises the wired-up production entry point,
    complementing the narrower guard in test_production_matches_direct_read
    below."""
    # pickle.load needs devicetree.edtlib importable to unpickle an
    # edtlib.EDT -- project.py's own runtime reference triggers this as
    # a side effect when the full suite runs, but this module never
    # imports edtlib itself, so a standalone run of this file alone
    # needs it put on sys.path explicitly, same as
    # project.py already does before its own one edtlib reference.
    edt_build.ensure_devicetree_on_path()
    with open(plain_build.edt_pickle, "rb") as f:
        pass2_edt = pickle.load(f)
    pass2_board = project.project_edt(pass2_edt, plain_build.board)

    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])
    standalone_board, diags, _deps = resolve.load_board(
        plain_build.board, str(tmp_path / "resolve"), board_dts=dts_path, recipe=recipe
    )
    assert standalone_board is not None, (
        f"resolve.load_board({plain_build.board!r}) failed:\n{render(diags)}"
    )

    assert standalone_board.sockets.keys() == pass2_board.sockets.keys()
    for label, standalone_socket in standalone_board.sockets.items():
        pass2_socket = pass2_board.sockets[label]
        assert standalone_socket.path == pass2_socket.path, (
            f"{plain_build.board}/{label}: socket node path differs "
            f"(standalone={standalone_socket.path} pass2={pass2_socket.path})"
        )
        assert standalone_socket.gpio_map == pass2_socket.gpio_map, (
            f"{plain_build.board}/{label}: gpio-map entries differ from pass-2's edt.pickle"
        )
        assert standalone_socket.buses == pass2_socket.buses, (
            f"{plain_build.board}/{label}: bus phandle targets (including "
            f"each bus's own cs_pool, a BusRef field) differ from "
            f"pass-2's edt.pickle"
        )


# ---------------------------------------------------------------- production-plumbing guard


@pytest.mark.build
def test_production_matches_direct_read(plain_build: PlainBuild, tmp_path: Path) -> None:
    """resolve.load_board (what the expander actually calls) is a thin
    board-resolution wrapper over project.load_board -- assert they
    produce the identical model.Board, given the same board-dts + recipe,
    so that wrapping can never introduce a divergence between what the
    expander sees and what a direct project read would see."""
    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])

    production, diags, _deps = resolve.load_board(
        plain_build.board, str(tmp_path / "production"), board_dts=dts_path, recipe=recipe
    )
    assert production is not None, (
        f"resolve.load_board({plain_build.board!r}) failed:\n{render(diags)}"
    )

    direct = project.load_board(plain_build.board, dts_path, recipe, str(tmp_path / "direct"))

    assert production == direct


# ---------------------------------------------------------------- census-vs-DT-truth


@pytest.mark.build
def test_census_matches_real_board_devicetree(plain_build: PlainBuild) -> None:
    """census's text-only scan is what `west rigs --boards-for`
    runs against (a real per-board
    read costs a cmake configure per candidate, which is not a query) --
    this is the guard that keeps it honest against the board's REAL
    devicetree, compared only on the fields the census actually
    populates: defining label, DASHED type_name, and the sorted set of
    bus KINDS a socket offers (never a bus's resolved target, which the
    census cannot see), plus the alias map."""
    edt_build.ensure_devicetree_on_path()
    with open(plain_build.edt_pickle, "rb") as f:
        pass2_edt = pickle.load(f)
    pass2_board = project.project_edt(pass2_edt, plain_build.board)

    censused = [cb for cb in census.census_boards() if cb.target == plain_build.board]
    assert len(censused) == 1, (
        f"expected exactly one census entry for board {plain_build.board!r}, "
        f"got targets {[cb.target for cb in censused]}"
    )
    census_board = censused[0].board

    assert set(census_board.sockets) == set(pass2_board.sockets), (
        f"{plain_build.board}: census sockets {sorted(census_board.sockets)} "
        f"!= real sockets {sorted(pass2_board.sockets)}"
    )
    for label, socket in census_board.sockets.items():
        real = pass2_board.sockets[label]
        assert socket.type_name == real.type_name, (
            f"{plain_build.board}/{label}: census type_name "
            f"{socket.type_name!r} != real {real.type_name!r}"
        )
        assert sorted(socket.buses) == sorted(real.buses), (
            f"{plain_build.board}/{label}: census bus kinds "
            f"{sorted(socket.buses)} != real {sorted(real.buses)}"
        )
    assert census_board.aliases == pass2_board.aliases, (
        f"{plain_build.board}: census aliases {census_board.aliases} != "
        f"real aliases {pass2_board.aliases}"
    )
