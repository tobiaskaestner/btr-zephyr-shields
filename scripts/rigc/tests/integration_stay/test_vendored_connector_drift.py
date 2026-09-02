"""The production half of what used to be
test_connector_bindings.py::test_fixture_nexus_type_is_registry_visible
(tests/integration/), plus the drift guard that keeps
tests/fixtures/dts/unified-connectors/ -- the vendored copy of the four
real connector-type bindings that module reads instead -- honest.

dts/bindings/connectors/ stays with the hardware definitions when
scripts/rigc/ (and its own tests/ tree) migrates out to bridle; the
travelling test_connector_bindings.py therefore validates a vendored copy,
not the production originals, and cannot itself assert anything about
production content (a module may not mix fixture-only and production-
tethered assertions -- see its own docstring). This module is where both
kinds of that leftover production-facing work live:

  - the real four-type census and BINDINGS' own default path (moved here
    verbatim, unchanged in substance);
  - the drift guard: every vendored .yaml/.h is byte-identical to its
    production original, AND the two sets have the same membership -- so
    a fifth connector type landing under dts/bindings/connectors/ with no
    matching vendored copy fails HERE, rather than leaving
    test_connector_bindings.py silently testing three-quarters of the
    vocabulary forever.

See tests/fixtures/dts/unified-connectors/README.md for the full
provenance note. NOT the same arrangement as
tests/fixtures/dts/singleton-law-connectors/ (an older, unguarded vendored
copy used only by test_singleton_identity_law.py, which has since drifted
from production on three of its four files -- see that directory's own
comments) -- that copy predates this guard and is deliberately out of
scope for it (see its own comments for why refreshing it is not a
cleanup)."""
from __future__ import annotations

import sys
from pathlib import Path

from harness import FIXTURES_DIR, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.registry import BINDINGS, load_types  # noqa: E402

#: The domain this guard claims to cover -- pinned, not derived from either
#: side being compared, so a guard that silently compared two EMPTY sets
#: (both directories deleted, say) cannot pass by construction.
_EXPECTED_TYPES = {"arduino-r3", "grove", "i2c-port", "mikrobus"}

_PRODUCTION_YAML_DIR = Path(BINDINGS)
_PRODUCTION_HEADER_DIR = REPO_ROOT / "include" / "dt-bindings" / "connector"
_VENDORED_YAML_DIR = FIXTURES_DIR / "dts" / "unified-connectors"
_VENDORED_HEADER_DIR = FIXTURES_DIR / "include" / "dt-bindings" / "connector"


def _yaml_stems(directory: Path) -> set[str]:
    """Every *.yaml basename (extension stripped) directly under
    directory -- a fresh set the caller owns."""
    return {p.stem for p in directory.glob("*.yaml")}


def test_registry_default_root_is_the_real_four_types() -> None:
    """Production-tethered (unlike test_connector_bindings.py's own
    fixture-nexus check, which stays on the travelling side): the real
    registry default (no connector_dirs override) sees exactly the four
    production types, and BINDINGS resolves to dts/bindings/connectors/
    under REPO_ROOT -- the same two assertions
    test_connector_bindings.py::test_fixture_nexus_type_is_registry_visible
    used to close with, before that module started reading a vendored
    copy instead."""
    real_types, _deps = load_types()
    assert set(real_types) == _EXPECTED_TYPES
    assert str(REPO_ROOT / "dts" / "bindings" / "connectors") == BINDINGS


def test_vendored_connector_membership_matches_production() -> None:
    """A fifth connector type landing under dts/bindings/connectors/ with
    no matching file under tests/fixtures/dts/unified-connectors/ must
    fail here -- not leave test_connector_bindings.py silently exercising
    an incomplete vocabulary forever. Derived from the real directory
    listing, never hand-duplicated as a second literal set, so the two
    sides of this comparison cannot both drift the same way and still
    agree."""
    production = _yaml_stems(_PRODUCTION_YAML_DIR)
    assert production == _EXPECTED_TYPES, (
        f"dts/bindings/connectors/ now holds {sorted(production)}, expected "
        f"{sorted(_EXPECTED_TYPES)} -- a connector type was added or removed; "
        "update _EXPECTED_TYPES deliberately, and vendor (or un-vendor) the "
        f"matching copy under {_VENDORED_YAML_DIR}")
    vendored = _yaml_stems(_VENDORED_YAML_DIR)
    assert vendored == production, (
        f"vendored connector set {sorted(vendored)} != production "
        f"{sorted(production)} under {_PRODUCTION_YAML_DIR} -- a connector "
        f"type was added to production with no matching vendored copy under "
        f"{_VENDORED_YAML_DIR} (see that directory's own README.md)")


def test_vendored_connector_bindings_are_byte_identical_to_production() -> None:
    """The drift guard proper: every vendored .yaml and its matching .h
    header (tests/fixtures/include/dt-bindings/connector/) must still be
    byte-identical to the production original it was copied from. Pinned
    against _EXPECTED_TYPES (not the vendored directory's own listing) so
    an accidentally-emptied vendored directory compares nothing and still
    fails, rather than vacuously passing an empty loop."""
    for name in sorted(_EXPECTED_TYPES):
        prod_yaml = _PRODUCTION_YAML_DIR / f"{name}.yaml"
        vend_yaml = _VENDORED_YAML_DIR / f"{name}.yaml"
        assert vend_yaml.read_bytes() == prod_yaml.read_bytes(), (
            f"{vend_yaml} has drifted from {prod_yaml} -- refresh the "
            "vendored copy deliberately, or investigate why production "
            "changed")

        prod_header = _PRODUCTION_HEADER_DIR / f"{name}.h"
        vend_header = _VENDORED_HEADER_DIR / f"{name}.h"
        assert vend_header.read_bytes() == prod_header.read_bytes(), (
            f"{vend_header} has drifted from {prod_header} -- refresh the "
            "vendored copy deliberately, or investigate why production "
            "changed")
