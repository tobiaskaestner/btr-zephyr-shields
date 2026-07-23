"""Bridge-A rewrite, phase 1 -- the edtlib READ side (`claude/rigs/
implementation-plan.md`, "Bridge-A deconstruction / edtlib rewrite").

Two things live here:

  * saferail 2 (AMENDED): SHADOW dual-read. For each of the four board
    clones, load the SAME board through both `boarddt.load_board`
    (common-dts scaffold, today's production authority) and
    `rigexp.board_edt.load_board` (a standalone `edtlib.EDT` over the
    board's OWN `.dts` -- the new reader), and assert the two `model.Board`
    projections agree on every rig-relevant fact, comparing EFFECTIVE
    values (e.g. cs-pool after the ctype-default merge -- see
    `_effective_cs_pool_common`/`_effective_cs_pool_edt` below).

  * saferail 3: edt.pickle cross-check. The standalone `edtlib.EDT` this
    reader builds must agree with pass-2's OWN `edt.pickle` from the exact
    same board -- proof that phase 1's cpp/bindings recipe (recovered from
    a real build's `build_info.yml`) is equivalent to what `dts.cmake`
    itself used.

Both need a real, PLAIN (no shield, no rig) `west build --cmake-only`
per board -- which doubles as saferail 11 (a board conversion must never
break the plain/legacy build path): see the `plain_build` fixture.

Nothing here changes `boarddt.py`, `model.py`, or the production expander
path -- `boarddt.load_board` stays the sole authority until the whole corpus
passes dual-read (saferail 2/6). The gpio_map (quail, frdm) and buses (frdm)
axes were `xfail(strict=True)` pending common-dts fixes; those fixes landed
(the two scaffold `.rig.dtsi` files were corrected/un-truncated against the
real board clones -- see the handoff report for the full position-by-position
table), so those axes are now hard asserts like every other axis.
"""
from __future__ import annotations

import dataclasses
import os
import pickle
import subprocess
import sys
from pathlib import Path
from typing import Dict

import pytest

from conftest import REPO_ROOT, WEST_EXE, WEST_TOPDIR, zephyr_base

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import board_edt, boarddt, ctypes_registry, edt_build  # noqa: E402
from rigexp.diag import Diagnostics  # noqa: E402
from rigexp.model import Board  # noqa: E402

# Any app works for a cmake-only PLAIN configure; hello_world is the corpus's
# own reference app (see conftest.py / test_tier2_goldens.py).
_APP = "zephyr/samples/hello_world"

# board name -> its OWN .dts, relative to the repo root (Conv. 4: typed
# socket nodes live in the board's own devicetree).
BOARD_DTS: Dict[str, str] = {
    "nucleo_f401re_btr": "boards/st/nucleo_f401re_btr/nucleo_f401re_btr.dts",
    "mikroe_quail_btr": "boards/mikroe/mikroe_quail_btr/mikroe_quail_btr.dts",
    "frdm_k64f_btr": "boards/nxp/frdm_k64f_btr/frdm_k64f_btr.dts",
    "seeeduino_lotus_btr": "boards/seeed/seeeduino_lotus_btr/seeeduino_lotus_btr.dts",
}
BOARDS = list(BOARD_DTS)

CTYPES = ctypes_registry.load_types()


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


@dataclasses.dataclass(frozen=True)
class PlainBuild:
    """One board's plain (no shield, no rig) `west build --cmake-only`."""
    board: str
    build_dir: Path

    @property
    def build_info(self) -> Path:
        return self.build_dir / "build_info.yml"

    @property
    def edt_pickle(self) -> Path:
        return self.build_dir / "zephyr" / "edt.pickle"


def _run_plain_build(board: str, build_dir: Path) -> "subprocess.CompletedProcess[str]":
    """`west build --cmake-only -b <board>` of `hello_world` -- deliberately
    PLAIN: no `--shield`, no `-DRIG`, so this exercises the legacy/plain
    board path a board conversion must never break (saferail 11). Sets the
    subprocess's `ZEPHYR_BASE` explicitly from `zephyr_base()` so the tree
    under test is deterministic (the gate mandates the env var; this does
    not re-resolve it the way `build-rig`'s override chain does)."""
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    cmd = [WEST_EXE, "build", "--cmake-only", "-b", board, _APP,
           "-p", "always", "-d", str(build_dir)]
    return subprocess.run(cmd, cwd=str(WEST_TOPDIR), env=env,
                           capture_output=True, text=True, timeout=600)


@pytest.fixture(scope="session", params=BOARDS, ids=BOARDS)
def plain_build(request: "pytest.FixtureRequest",
                 tmp_path_factory: "pytest.TempPathFactory") -> PlainBuild:
    board = request.param
    build_dir = tmp_path_factory.mktemp(f"plain-{board}")
    result = _run_plain_build(board, build_dir)
    assert result.returncode == 0, (
        f"{board}: plain `west build --cmake-only` (no shield, no rig) must "
        f"configure clean -- saferail 11\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}")
    return PlainBuild(board=board, build_dir=build_dir)


@pytest.mark.build
def test_plain_build_configures_clean(plain_build: PlainBuild) -> None:
    """The fixture performs + asserts the configure; this test exists so a
    plain-build failure is its own reported item (saferail 11), not just an
    error while setting up the dual-read tests below."""
    assert (plain_build.build_dir / "zephyr" / "zephyr.dts").is_file()
    assert plain_build.build_info.is_file()
    assert plain_build.edt_pickle.is_file()


# ---------------------------------------------------------------- shared helpers


def _common_dts_board(board: str, tmp_path: Path) -> Board:
    diags = Diagnostics()
    board_model = boarddt.load_board(board, str(tmp_path / "boarddt"), diags)
    assert board_model is not None, (
        f"boarddt.load_board({board!r}) failed:\n{diags.render()}")
    return board_model


def _edtlib_board(plain_build: PlainBuild, tmp_path: Path) -> Board:
    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])
    return board_edt.load_board(plain_build.board, dts_path, recipe,
                                 str(tmp_path / "edt"))


def _effective_cs_pool_common(socket) -> list:
    """The analyzer's own merge (analyzer.py:533): an authored override, else
    the connector type's default -- `ctype.cs_pool` is `[]` for a type that
    doesn't offer CS pooling at all (grove)."""
    ctype = CTYPES[socket.type_name]
    return socket.cs_pool if socket.cs_pool is not None else ctype.cs_pool


def _effective_cs_pool_edt(socket) -> list:
    """The edtlib side's "effective" value: for a type whose (real) binding
    DECLARES `socket,cs-pool` (arduino-r3, mikrobus), edtlib always
    back-fills the default when unauthored, so the raw value already IS the
    effective one. For a type with NO such property in its binding at all
    (grove), there is nothing to back-fill (`None`) -- normalized to `[]`
    here, matching `ConnectorType.cs_pool`'s own "no candidates"
    representation, for a fair comparison against `ctype.cs_pool` on the
    common-dts side."""
    return socket.cs_pool if socket.cs_pool is not None else []


# ---------------------------------------------------------------- saferail 2: dual-read


@pytest.mark.build
def test_dualread_socket_set_and_type(plain_build: PlainBuild,
                                       tmp_path: Path) -> None:
    """Socket set (labels) and per-socket `type_name` must match exactly --
    no known gap on this axis for any of the four boards."""
    common = _common_dts_board(plain_build.board, tmp_path)
    edtb = _edtlib_board(plain_build, tmp_path)
    assert set(edtb.sockets) == set(common.sockets)
    for label, socket in common.sockets.items():
        assert edtb.sockets[label].type_name == socket.type_name


@pytest.mark.build
def test_dualread_gpio_map(plain_build: PlainBuild, tmp_path: Path) -> None:
    common = _common_dts_board(plain_build.board, tmp_path)
    edtb = _edtlib_board(plain_build, tmp_path)
    for label, socket in common.sockets.items():
        edt_socket = edtb.sockets[label]
        assert edt_socket.gpio_map == socket.gpio_map, (
            f"{plain_build.board}/{label}: gpio_map mismatch\n"
            f"  edtlib:    {sorted(edt_socket.gpio_map.items())}\n"
            f"  common-dts:{sorted(socket.gpio_map.items())}")


@pytest.mark.build
def test_dualread_buses(plain_build: PlainBuild, tmp_path: Path) -> None:
    """Buses compared by (kind -> controller LABEL) -- the emission target
    (`&i2c1`, `&spi1`, ...); dtlib paths are expected to differ between the
    common-dts scaffold's `_soc-stubs.dtsi` and the real SoC tree (nucleo
    spike finding), so path is deliberately not part of this comparison."""
    common = _common_dts_board(plain_build.board, tmp_path)
    edtb = _edtlib_board(plain_build, tmp_path)
    for label, socket in common.sockets.items():
        common_labels = {k: v.label for k, v in socket.buses.items()}
        edt_labels = {k: v.label for k, v in edtb.sockets[label].buses.items()}
        assert edt_labels == common_labels, (
            f"{plain_build.board}/{label}: bus labels mismatch\n"
            f"  edtlib:    {edt_labels}\n  common-dts:{common_labels}")


@pytest.mark.build
def test_dualread_stackable_equivalent(plain_build: PlainBuild,
                                        tmp_path: Path) -> None:
    """Stackable is a TYPE-level fact (`ConnectorType.stackable`, presence
    of `socket,stackable` in the connector-type schema) -- `model.BoardSocket`
    carries no per-socket field for it, so this compares the common-dts
    ctype fact against the real socket NODE's own authored presence of
    `socket,stackable` (both corpora happen to author it uniformly per type:
    every arduino-r3 socket has it, no mikrobus/grove socket does)."""
    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])
    edt = edt_build.build_edt(dts_path, recipe, str(tmp_path / "edt"))
    common = _common_dts_board(plain_build.board, tmp_path)
    for label, socket in common.sockets.items():
        ctype_stackable = CTYPES[socket.type_name].stackable
        node = edt.label2node[label]
        stackable_prop = node.props.get("socket,stackable")
        node_stackable = bool(stackable_prop is not None and stackable_prop.val)
        assert node_stackable == ctype_stackable, (
            f"{plain_build.board}/{label}: stackable mismatch "
            f"(edtlib node={node_stackable} ctype={ctype_stackable})")


@pytest.mark.build
def test_dualread_cs_pool_effective(plain_build: PlainBuild,
                                     tmp_path: Path) -> None:
    """EFFECTIVE cs_pool (saferail 2, AMENDED): the analyzer's own merge on
    the common-dts side (`socket.cs_pool if not None else ctype.cs_pool`,
    analyzer.py:533) vs the binding-default-backfilled value on the edtlib
    side. Matches for every socket in the corpus (arduino-r3: [16, 15, 14];
    mikrobus: [2]; grove: no cs-pool concept at all, both sides normalize to
    `[]`) -- no known gap on this axis."""
    common = _common_dts_board(plain_build.board, tmp_path)
    edtb = _edtlib_board(plain_build, tmp_path)
    for label, socket in common.sockets.items():
        common_effective = _effective_cs_pool_common(socket)
        edt_effective = _effective_cs_pool_edt(edtb.sockets[label])
        assert edt_effective == common_effective, (
            f"{plain_build.board}/{label}: effective cs_pool mismatch "
            f"(edtlib={edt_effective} common-dts={common_effective})")


@pytest.mark.build
def test_dualread_pwm_adc_known_phase2_gap(plain_build: PlainBuild,
                                            tmp_path: Path) -> None:
    """pwm_map/adc_map: the real board sockets carry no standard `pwm-map`/
    `io-channel-map` nexus yet -- that is Bridge-A phase 2 ("PWM/ADC via real
    nexuses"), explicitly NOT in this task's scope. Assert equality wherever
    common-dts already has them empty (nucleo, quail, frdm, and lotus's
    non-multi-function grove sockets); where common-dts is non-empty (lotus's
    PWM/ADC-capable grove sockets, grove_d2-4/grove_a0-1), assert the edtlib
    side is the documented, EXPECTED empty phase-2 gap -- not a surprise."""
    common = _common_dts_board(plain_build.board, tmp_path)
    edtb = _edtlib_board(plain_build, tmp_path)
    for label, socket in common.sockets.items():
        edt_socket = edtb.sockets[label]
        if socket.pwm_map:
            assert edt_socket.pwm_map == {}, (
                f"{plain_build.board}/{label}: expected the documented "
                f"phase-2 pwm_map gap (empty), got {edt_socket.pwm_map}")
        else:
            assert edt_socket.pwm_map == {}
        if socket.adc_map:
            assert edt_socket.adc_map == {}, (
                f"{plain_build.board}/{label}: expected the documented "
                f"phase-2 adc_map gap (empty), got {edt_socket.adc_map}")
        else:
            assert edt_socket.adc_map == {}


# ---------------------------------------------------------------- saferail 3: edt.pickle


@pytest.mark.build
def test_edt_pickle_cross_check(plain_build: PlainBuild, tmp_path: Path) -> None:
    """Pass-1 (this reader's standalone `edtlib.EDT`, built from the recipe
    recovered out of the SAME build's `build_info.yml`) must agree with
    pass-2's OWN `edt.pickle`, for the rig-relevant projection: socket node
    paths, gpio-map entries, bus phandle targets, cs-pool values. Follows the
    nucleo spike's comparison approach, generalized to all four boards."""
    with open(plain_build.edt_pickle, "rb") as f:
        pass2_edt = pickle.load(f)
    pass2_board = board_edt.project_edt(pass2_edt, plain_build.board)

    recipe = edt_build.recipe_from_build_info(str(plain_build.build_info))
    dts_path = str(REPO_ROOT / BOARD_DTS[plain_build.board])
    standalone_edt = edt_build.build_edt(dts_path, recipe,
                                          str(tmp_path / "standalone"))
    standalone_board = board_edt.project_edt(standalone_edt, plain_build.board)

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
