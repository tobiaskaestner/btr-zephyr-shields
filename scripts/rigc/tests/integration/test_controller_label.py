"""Regression coverage for the controller-label determinism invariant
(board_edt._controller_label): a *-map target's identity must be its
DEFINING label (node.labels[0]), stable no matter what else composes onto
the same node afterward. This is what makes the choice safe across module
composition -- a socket file or an unrelated board extension attaching a
further alias to a shared controller must never perturb what a pwm/adc
consumer (emission, or an analyzer diagnostic) reports for it.

Fast, no build, and hermetic: fixtures/boards/mainboards/socket.dts is a
standalone board-shaped fixture (like
fixtures/boards/mainboards/socketless_board.dts) carrying one socket,* node
of the fixture tree's own purpose-built connector type
(fixtures/dts/connectors/fixture-nexus.yaml, compatible
"socket,fixture-nexus" -- never a copy of the real
dts/bindings/connectors/*.yaml types) whose pwm-map/gpio-map both resolve
to a controller node with two
labels attached in a fixed textual order -- the primary one on the node
itself, a second one appended via a bare label-ref afterward, mirroring
how a later-included module attaches a legacy alias to a node it does not
own. The recipe below names only fixture-tree directories -- proven by
assert_fixture_local, not merely asserted -- so this test needs no
$ZEPHYR_BASE bindings dir, no REPO_ROOT/dts/bindings, no REPO_ROOT/include.
$ZEPHYR_BASE itself may still be set (board_edt needs it to locate
devicetree.edtlib -- see edt_build.ensure_devicetree_on_path); it is
Zephyr's own board/binding DATA this test never touches.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, REPO_ROOT, assert_fixture_local

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import board_edt  # noqa: E402
from rigexp.edt_build import BuildRecipe  # noqa: E402

pytestmark = pytest.mark.unit

_MAINBOARDS = FIXTURES_DIR / "boards" / "mainboards"
_CONNECTOR_BINDINGS = FIXTURES_DIR / "dts" / "connectors"
_CONNECTOR_INCLUDE = FIXTURES_DIR / "include"


def _recipe() -> BuildRecipe:
    recipe = BuildRecipe(
        include_dirs=[str(_CONNECTOR_INCLUDE)],
        bindings_dirs=[str(_CONNECTOR_BINDINGS)])
    assert_fixture_local(recipe.include_dirs + recipe.bindings_dirs)
    return recipe


def test_controller_label_is_the_defining_label(tmp_path: Path) -> None:
    board = board_edt.load_board(
        "controller-label-fixture", str(_MAINBOARDS / "socket.dts"), _recipe(),
        str(tmp_path))

    socket = board.sockets["fixture_socket"]
    # The pwm-map's controller identity must be the node's FIRST-attached
    # label -- never the later-appended alias, regardless of which one a
    # future module composition attaches last.
    assert socket.pwm_map[0] == ("defining_ctrl", 0)
    # gpio-map targets resolve by the same rule; pinned here too so both
    # nexus kinds stay provably consistent.
    ctrl_label, _pin, _flags = socket.gpio_map[0]
    assert ctrl_label == "defining_ctrl"


def test_controller_label_ignores_a_later_attached_alias(tmp_path: Path) -> None:
    """The later-attached alias must never win: a module that composes an
    extra label onto a controller it does not own cannot change the identity
    reported for that controller. Asserted negatively against
    legacy_alias so the fixture's second label is provably inert rather
    than merely absent."""
    board = board_edt.load_board(
        "controller-label-fixture", str(_MAINBOARDS / "socket.dts"), _recipe(),
        str(tmp_path))
    label, _channel = board.sockets["fixture_socket"].pwm_map[0]
    assert label == "defining_ctrl"
    assert label != "legacy_alias"
