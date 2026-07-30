"""Shared helpers for rigc's own tests.

Only the hermeticity enforcement lives here (R1): the boundary decays if
the enforcement arrives late (rigc-r1-brief.md Sec 4), so
assert_fixture_local exists from day one even though R1's tests barely
needed it. Golden/corpus plumbing lives in tests/integration/conftest.py
instead (the frozen suite's own conftest, moved here at cutover) -- this
file must never grow a second copy of it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Union

#: rigc's own fixture tree (created by the slice that first needs it).
#: A value derived from this file's location -- no environment lookup at
#: module scope anywhere in this package (the dtsio.py:27 collection trap,
#: designed out).
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def assert_fixture_local(paths: Iterable[Union[Path, str]],
                         fixtures_dir: Path = FIXTURES_DIR) -> None:
    """Structural proof of hermeticity: every path a test hands to the
    code under test resolves under fixtures_dir -- never a real Zephyr
    tree, never repo-production devicetree content. Hermetic means "no
    foreign DATA", proven from what the test actually references, not
    from the absence of an environment variable. fixtures_dir is a
    parameter (default: rigc's own tree) so the enforcement itself is
    unit-testable against synthetic roots."""
    root = fixtures_dir.resolve()
    for p in paths:
        resolved = Path(p).resolve()
        assert resolved == root or str(resolved).startswith(
            str(root) + os.sep), (
            f"{resolved} is outside {root} -- a test asserting hermeticity "
            "must reference only its own fixture-tree paths")
