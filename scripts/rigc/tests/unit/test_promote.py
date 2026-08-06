"""Unit: promote -- the `--rig <shield>` desugaring (board-coordinate-
s3-brief.md), the namespace rule that decides when a bare name resolves
as a shield at all, and the census tying discovery's own marker-file
authority to shield.yml's `template:` flag (Sec 4: two facts about one
thing, on purpose).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import textwrap
from pathlib import Path

from rigc import loader
from rigc.diag import has_errors
from rigc.dtsio import MODULE_ROOT
from rigc.promote import (ShieldInfo, both_paths_error, check_promotable,
                          discover_shields, promote_shield)
from rigc.registry import load_types

# ---------------------------------------------------------------- promote_shield

def test_bare_name_desugars_to_a_boardless_socketless_singleton() -> None:
    promoted = promote_shield("adafruit_data_logger")
    assert promoted.rig_yml == textwrap.dedent("""\
        rig:
          name: adafruit_data_logger
        """)
    assert "board:" not in promoted.rig_yml
    assert promoted.content == textwrap.dedent("""\
        instances:
          - name: adafruit_data_logger
            shield: adafruit_data_logger
        """)
    assert "socket:" not in promoted.content


def test_content_filename_is_constructed_from_the_rig_name() -> None:
    assert promote_shield("adafruit_data_logger").content_name == \
        "adafruit_data_logger.yml"
    assert promote_shield("i2c_sensor").content_name == "i2c_sensor.yml"


def test_rev_desugars_to_the_shield_own_revision_and_leaves_rig_yml_alone() -> None:
    bare = promote_shield("i2c_sensor")
    revved = promote_shield("i2c_sensor", revision="2")
    assert revved.rig_yml == bare.rig_yml
    assert "shield: i2c_sensor@2" in revved.content
    assert revved.content_name == bare.content_name


# ---------------------------------------------------------------- check_promotable

def test_a_variant_on_a_promoted_shield_is_refused_naming_why() -> None:
    info = ShieldInfo(name="adafruit_data_logger", dir="/m/boards/shields/adafruit_data_logger", template=True, has_yml=True)
    err = check_promotable("adafruit_data_logger", info, variant="foo")
    assert err is not None
    assert "variant" in err
    assert "adafruit_data_logger/foo" in err


def test_a_shield_with_no_yml_at_all_is_not_promotable() -> None:
    info = ShieldInfo(name="legacy_click", dir="/m/boards/shields/legacy_click", template=False, has_yml=False)
    err = check_promotable("legacy_click", info, variant=None)
    assert err is not None
    assert "no shield.yml" in err


def test_a_shield_yml_without_the_flag_is_not_promotable() -> None:
    info = ShieldInfo(name="quiet_click", dir="/m/boards/shields/quiet_click", template=False, has_yml=True)
    err = check_promotable("quiet_click", info, variant=None)
    assert err is not None
    assert "template: true" in err
    assert "no shield.yml" not in err


def test_a_promotable_shield_with_no_variant_passes() -> None:
    info = ShieldInfo(name="adafruit_data_logger", dir="/m/boards/shields/adafruit_data_logger", template=True, has_yml=True)
    assert check_promotable("adafruit_data_logger", info, variant=None) is None


# ---------------------------------------------------------------- namespace rule

def test_both_paths_error_names_both_offending_locations() -> None:
    """Both paths must be the DISCOVERED ones, so a shield living outside
    the vendored library is reported where it actually is. The shield
    directory here is deliberately not the conventional
    `<root>/boards/shields/<name>` -- a message that reconstructed the
    path from the name would still contain the name and still look right,
    and would be wrong for exactly the cross-module case that makes two
    namespaces collide."""
    msg = both_paths_error("adafruit_data_logger", Path("/some/boards/rigs/x"),
                          "/other/module/vendor_shields/adafruit_data_logger")
    assert "/some/boards/rigs/x" in msg
    assert "/other/module/vendor_shields/adafruit_data_logger" in msg


# ---------------------------------------------------------------- discover_shields

def test_discover_shields_finds_the_real_corpus_and_agrees_with_template_flag() -> None:
    """Census (Sec 4): every discovered name (marker file present) whose
    shield.yml declares `template: true` shows up as promotable, and
    every one of today's 14 corpus shields does. Falsified by mutating a
    real shield.yml, not by editing this assertion (see the mutation test
    below) -- this one just proves the real tree is clean today."""
    shields = discover_shields()
    assert len(shields) == 14
    for info in shields.values():
        assert info.has_yml, f"{info.name}: discovered but no shield.yml"
        assert info.template, f"{info.name}: shield.yml omits template: true"


def test_discover_shields_census_is_falsified_by_a_real_mutation(tmp_path: Path) -> None:
    """Mutation-verified negative control (Sec 8): drop `template: true`
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


# ---------------------------------------------------------------- round trip (criterion 2.2)

def test_promoted_shield_round_trips_through_the_loader_with_no_diagnostics(
        tmp_path: Path) -> None:
    """Criterion 2.2, the anti-decoration guard: --explain's synthesized
    pair, written verbatim into a tmp rig folder, must load through
    rigc.loader.load as one instance of the right shield with NO
    diagnostics. The printed rig.yml declares no board of its own (Sec 3:
    "a board reaches this rig only by injection") -- loader.load's own
    `board` argument is exactly that injection point, a bare STRING the
    loader never dereferences against a real board devicetree (no
    --board-dts, no subprocess, no analyzer) -- so supplying one here
    stays "no board" in the sense this test's docstring cares about (no
    real board data), while still exercising the actual invocation shape
    a build gives this rig."""
    promoted = promote_shield("adafruit_data_logger")
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(promoted.rig_yml)
    (rig_dir / promoted.content_name).write_text(promoted.content)

    types, _deps = load_types()
    workdir = tmp_path / "workdir"
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(workdir), types=types, board="some_board")

    assert not has_errors(diags)
    assert diags == []
    assert rig is not None
    assert [inst.name for inst in rig.instances] == ["adafruit_data_logger"]
    assert rig.instances[0].shield.name == "adafruit_data_logger"
    assert rig.instances[0].socket is None


def test_a_revved_promoted_shield_round_trips_to_the_named_revision(
        tmp_path: Path) -> None:
    promoted = promote_shield("i2c_sensor", revision="2")
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(promoted.rig_yml)
    (rig_dir / promoted.content_name).write_text(promoted.content)

    types, _deps = load_types()
    workdir = tmp_path / "workdir"
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(workdir), types=types, board="some_board")

    assert diags == []
    assert rig is not None
    assert rig.instances[0].shield.revision == "2"
