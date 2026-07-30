"""Enforcement for the unit/integration split: without this, the split is
only a convention, not a property the suite can prove about itself.

Tobi's rule is two-sided -- (1) no test module may yield both a unit test
and an integration test (the file boundary itself), and (2) every test
must carry exactly one of the two markers (so a newly added test cannot
silently escape classification, the same reasoning as the enforcement test
Part A of the tests refactor plan calls for once the module split lands).

Reads conftest.pytest_collection_modifyitems's stashed census
(config._rigc_marker_census), built from the FULL collected item list
before any -m deselection narrows it -- request.session.items would
instead only reflect the currently-selected subset, which would make both
checks below pass vacuously under `pytest -m unit` (nothing INTEGRATION-
marked would even be present to conflict with).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Set

import pytest

pytestmark = pytest.mark.unit


def test_marker_discipline(request: "pytest.FixtureRequest") -> None:
    census = request.config._rigc_marker_census  # type: ignore[attr-defined]

    unclassified = {nodeid: sorted(markers) for nodeid, (_module, markers)
                    in census.items() if len(markers) != 1}
    assert not unclassified, (
        "every collected test must carry EXACTLY ONE of unit/integration "
        f"-- these carry zero or both: {unclassified}")

    by_module: Dict[str, Set[str]] = defaultdict(set)
    for _nodeid, (module, markers) in census.items():
        by_module[module] |= markers

    mixed = {module: sorted(markers) for module, markers in by_module.items()
             if len(markers) > 1}
    assert not mixed, (
        "a test module may yield unit tests or integration tests, never "
        f"both -- for a reader looking for one, the other is noise: {mixed}")
