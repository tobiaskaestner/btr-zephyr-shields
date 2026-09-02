# Copyright (c) 2026 TiaC Systems
# SPDX-License-Identifier: Apache-2.0
"""Unit: promote -- the two census tests that are TETHERED to this
repository's own shield corpus.

They live here rather than in tests/unit/ for the same reason
tests/integration_stay/ exists: what they assert is a fact about
`boards/shields/` itself. The census enumerates today's real corpus by
name and count; the mutation control edits a real shield.yml on disk and
puts it back. Neither can travel with the transpiler, and neither should
be rewritten against vendored fixtures -- a fixture census would assert
that the fixtures are the fixtures, which is not a fact about anything.

Every OTHER unit test of promote.py is hermetic and lives in
tests/unit/test_promote.py: it threads `rigc.tests.roots`' vendored
connector bindings and shield library, so it exercises the same code
against data that travels. That split is what the seam means on the unit
side, and this module is deliberately small -- a test belongs here only
when the production corpus IS the subject.

Run by scripts/check-extended.sh, never by scripts/check.sh.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from rigc.dtsio import MODULE_ROOT
from rigc.promote import discover_shields


def test_discover_shields_finds_the_real_corpus_and_agrees_with_template_flag() -> None:
    """Census: every discovered name (marker file present) whose
    shield.yml declares `template: true` shows up as promotable, and
    every one of today's 25 corpus shields does -- 15 one-per-folder plus
    four plurality folders: lcd_char_1602/lcd_tft_24
    (boards/shields/arduino_lcd/, named neither),
    grove_sens_bme280/grove_sens_bmp280/grove_sens_dps310
    (boards/shields/grove_sens/, named neither -- three shields, one
    `.shield` per name, following arduino_lcd's own precedent),
    grove_led/grove_pwm_led/grove_pwm_led_inv (boards/shields/grove_led/,
    sharing the folder bridle's own grove_led/ keeps both LED kinds in --
    the one plurality folder actually named after one of its own members;
    grove_pwm_led_inv is NOT a bridle port and joins this same folder
    rather than a new one, since it is grove_pwm_led's own
    inverted-polarity sibling), and seeed_grove_base_v1/seeed_grove_base_v2
    (boards/shields/grove/, named neither -- the `arduino_lcd` falsifier
    shape again); can_span_click and mikrobus_span_adapter (the
    multi-plug corpus shields) are two of the 15 -- DISCOVERABLE,
    `template: true`, and genuinely promotable too, this census
    predicate having no plurality concept at all.
    Falsified by mutating a real shield.yml, not by editing this
    assertion (see the mutation test below) -- this one just proves the
    real tree is clean today."""
    shields = discover_shields()
    assert len(shields) == 25
    for info in shields.values():
        assert info.has_yml, f"{info.name}: discovered but no shield.yml"
        assert info.template, f"{info.name}: shield.yml omits template: true"
    assert shields["lcd_char_1602"].dir == shields["lcd_tft_24"].dir
    assert os.path.basename(shields["lcd_char_1602"].dir) not in ("lcd_char_1602", "lcd_tft_24")


def test_discover_shields_census_is_falsified_by_a_real_mutation(tmp_path: Path) -> None:
    """Mutation-verified negative control: drop `template: true`
    from a REAL shield.yml (i2c_sensor, copied first, hashed before
    mutating, restored from the copy, verified against that hash) and
    confirm exactly that one shield stops being promotable -- nothing
    else about discovery changes."""
    shield_yml = Path(MODULE_ROOT) / "boards" / "shields" / "i2c_sensor" / "shield.yml"
    original = shield_yml.read_bytes()
    backup = tmp_path / "shield.yml.orig"
    backup.write_bytes(original)
    original_hash = hashlib.sha256(original).hexdigest()
    try:
        mutated = original.decode().replace("template: true\n", "")
        assert "template: true" not in mutated
        shield_yml.write_bytes(mutated.encode())
        _purge_pycache()
        shields = discover_shields()
        assert "i2c_sensor" in shields
        assert shields["i2c_sensor"].has_yml
        assert not shields["i2c_sensor"].template
        for name, info in shields.items():
            if name != "i2c_sensor":
                assert info.template, f"{name}: collateral damage from the mutation"
    finally:
        restored = backup.read_bytes()
        assert hashlib.sha256(restored).hexdigest() == original_hash
        shield_yml.write_bytes(restored)
        _purge_pycache()
        assert shield_yml.read_bytes() == original


def _purge_pycache() -> None:
    shields_root = os.path.join(MODULE_ROOT, "boards", "shields")
    for root, dirs, _files in os.walk(shields_root):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"))
