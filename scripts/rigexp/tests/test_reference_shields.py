"""The reference shield set (rigs test suite): fixtures/reference-shields
demonstrates the four main shield-authoring patterns as ACCEPTED material —
the opposite of every other fixture in this suite, which is named for the
defect it triggers. A reference implementation nobody exercises is
documentation, and documentation drifts, so this test runs the whole
pipeline (load -> analyze -> emit) end to end through the CLI and asserts
on the accepted result, the same way the corpus tier-1 goldens do for real
rigs.

This is also the connector-type registry's own proof of configurability
(ctypes_registry.load_types's connector_dirs/header_dirs parameters,
threaded through cli.py's --connector-dir plus the existing
--include-dir): fixtures/connectors/bindings/fixture-nexus.yaml is
registry-complete (plug,positions, plug,bus-proxies, socket facts) and
mates a synthetic shield exactly as a real shield mates
dts/bindings/connectors/arduino-r3.yaml — something T0's fixture connector
type could not do (it was invisible to shields.py's plug-type check; see
that module's own docstring history before this slice).

Board + registry pieces are fixture-local (assert_fixture_local, below); the
per-instance parameter values are plain integers rather than zephyr,code
macros specifically so the WHOLE fixture tree stays free of any dependency
outside itself — see fixture_button.shield's own comment for why a .shield
template cannot reach this fixture tree's own connector header via
#include, unlike the board .dts.

The honest limit, worth repeating here rather than only in the fixtures'
own comments: this proves the SHAPE is right — that a shield authored
against a registry-complete connector type mates, and that its devices
resolve to the right positions/buses/addresses. It proves nothing about
whether any REAL board's binding agrees with what its schema promises; it
could not have caught the sam0 two-cell PWM bug (test_pwm_nonzero_flags_
golden, test_tier1_goldens.py), which only surfaced against a real
binding. The corpus rigs under boards/rigs/ remain the proof that real
hardware works.
"""
from __future__ import annotations

import sys
from pathlib import Path

from conftest import FIXTURES_DIR, REPO_ROOT, assert_fixture_local, run_expand

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigexp.ctypes_registry import BINDINGS, load_types  # noqa: E402

_FIXTURE = FIXTURES_DIR / "reference-shields"
_CONNECTORS = FIXTURES_DIR / "connectors"


def test_reference_shields_accept(tmp_path: Path) -> None:
    board_dts = _FIXTURE / "board.dts"
    bindings_dirs = [_CONNECTORS / "bindings"]
    include_dirs = [_CONNECTORS / "include"]
    connector_dirs = [_CONNECTORS / "bindings"]
    shield_dirs = [_FIXTURE / "shields"]
    assert_fixture_local(
        [board_dts, *bindings_dirs, *include_dirs, *connector_dirs, *shield_dirs])

    out_dir = tmp_path / "out"
    result = run_expand(
        _FIXTURE / "rig.yml", out_dir,
        shield_dirs=shield_dirs,
        board_dts=board_dts,
        bindings_dirs=bindings_dirs,
        include_dirs=include_dirs,
        connector_dirs=connector_dirs)

    assert result.returncode == 0, (
        f"reference-shields: expected accept\n--- stderr ---\n{result.stderr}")

    overlay = (out_dir / "rig-gen.overlay").read_text()

    # Fixed-address I2C device: reg authored verbatim, address-authority
    # rule satisfied (reg present, shield,addr-from absent).
    assert "&fixture_i2c {" in overlay
    assert "sensor@50" in overlay
    assert 'compatible = "vnd,fixture-sensor";' in overlay
    assert "reg = <0x50>;" in overlay

    # CS-position device: shield,cs-position (FIXTURE_CS, index 4) resolved
    # to a copper-fixed CS net on the SPI bus, not the CS pool.
    assert "&fixture_spi {" in overlay
    assert "cs-gpios = <&fixture_socket_a 4 1" in overlay
    assert "flash@0" in overlay
    assert 'compatible = "vnd,fixture-flash";' in overlay

    # GPIO collection + per-instance parameter: ONE shared collection node,
    # two entries, each carrying its OWN assigned zephyr,code (emitted
    # verbatim) and each resolved against its OWN socket's position.
    assert 'compatible = "vnd,fixture-keys";' in overlay
    assert "button_a_fb_key" in overlay
    assert "button_b_fb_key" in overlay
    assert "zephyr,code = <1>;" in overlay
    assert "zephyr,code = <2>;" in overlay
    assert "&fixture_socket_b 2 0x0" in overlay
    assert "&fixture_socket_c 2 0x0" in overlay

    config_sheet = (out_dir / "config-sheet.md").read_text()
    assert "fixture_socket_a" in config_sheet
    assert "fixture_socket_b" in config_sheet
    assert "fixture_socket_c" in config_sheet


def test_fixture_nexus_type_is_registry_visible() -> None:
    """The ceiling T0 hit, lifted: ctypes_registry.load_types can see the
    fixture connector type when pointed at its directory explicitly, and
    still sees the four real types when it is not — the same function, two
    different roots, proving the default-preserving fallback rather than
    merely asserting it."""
    fixture_types = load_types(
        connector_dirs=[str(_CONNECTORS / "bindings")],
        header_dirs=[str(_CONNECTORS / "include")])
    assert set(fixture_types) == {"fixture-nexus"}
    ctype = fixture_types["fixture-nexus"]
    assert set(ctype.positions) == {"D0", "D1", "CS"}
    assert ctype.bus_proxies == ["i2c", "spi"]
    assert ctype.cs_pool == [4]

    real_types = load_types()
    assert set(real_types) == {"arduino-r3", "grove", "i2c-port", "mikrobus"}
    assert BINDINGS == str(REPO_ROOT / "dts" / "bindings" / "connectors")
