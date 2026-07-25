"""Regression coverage for the controller-label determinism invariant
(`board_edt._controller_label`): a `*-map` target's identity must be its
DEFINING label (`node.labels[0]`), stable no matter what else composes onto
the same node afterward. This is what makes the choice safe across module
composition -- a socket file or an unrelated board extension attaching a
further alias to a shared controller must never perturb what a pwm/adc
consumer (emission, or an analyzer diagnostic) reports for it.

Fast, no build: `fixtures/controller-label/socket.dts` is a standalone
board-shaped fixture (like `fixtures/not-rig-enabled/socketless_board.dts`)
carrying one real `socket,grove` node (the project's own binding) whose
pwm-map/gpio-map both resolve to a controller node with two labels attached
in a fixed textual order -- the primary one on the node itself, a second
one appended via a bare label-ref afterward, mirroring how a later-included
module attaches a legacy alias to a node it does not own.
"""
from __future__ import annotations

import sys
from pathlib import Path

from conftest import REPO_ROOT, zephyr_base

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp import board_edt  # noqa: E402
from rigexp.edt_build import BuildRecipe  # noqa: E402

_FIXTURE = REPO_ROOT / "scripts" / "rigexp" / "tests" / "fixtures" / "controller-label"


def _recipe() -> BuildRecipe:
    zb = zephyr_base()
    return BuildRecipe(
        include_dirs=[str(REPO_ROOT / "include")],
        bindings_dirs=[str(Path(zb) / "dts" / "bindings"),
                       str(REPO_ROOT / "dts" / "bindings")])


def test_controller_label_is_the_defining_label(tmp_path: Path) -> None:
    board = board_edt.load_board(
        "controller-label-fixture", str(_FIXTURE / "socket.dts"), _recipe(),
        str(tmp_path))

    socket = board.sockets["grove_x"]
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
    `legacy_alias` so the fixture's second label is provably inert rather
    than merely absent."""
    board = board_edt.load_board(
        "controller-label-fixture", str(_FIXTURE / "socket.dts"), _recipe(),
        str(tmp_path))
    label, _channel = board.sockets["grove_x"].pwm_map[0]
    assert label == "defining_ctrl"
    assert label != "legacy_alias"
