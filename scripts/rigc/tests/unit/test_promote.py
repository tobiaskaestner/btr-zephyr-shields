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
from typing import List, Tuple

from rigc import loader
from rigc.diag import has_errors
from rigc.dtsio import MODULE_ROOT
from rigc.model import Device, Shield
from rigc.promote import (ParsedPromotionOpts, ShieldInfo, both_paths_error,
                          check_promotable, parse_promotion_opts,
                          discover_shields, promote_shield,
                          shield_declares_required_params)
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
    every one of today's 16 corpus shields does -- 14 one-per-folder plus
    lcd_char_1602/lcd_tft_24, the plurality corpus example
    (shield-plurality-brief.md Sec 5), TWO names out of the SAME folder
    (boards/shields/arduino_lcd/, named neither). Falsified by mutating a
    real shield.yml, not by editing this assertion (see the mutation test
    below) -- this one just proves the real tree is clean today."""
    shields = discover_shields()
    assert len(shields) == 16
    for info in shields.values():
        assert info.has_yml, f"{info.name}: discovered but no shield.yml"
        assert info.template, f"{info.name}: shield.yml omits template: true"
    assert shields["lcd_char_1602"].dir == shields["lcd_tft_24"].dir
    assert os.path.basename(shields["lcd_char_1602"].dir) not in (
        "lcd_char_1602", "lcd_tft_24")


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


def test_discover_shields_reports_a_legacy_shield_with_no_marker_file(
        tmp_path: Path) -> None:
    """Sec 3's third consequence: a folder whose shield.yml declares a
    name but omits (or falses) `template:` is discoverable here even
    though it carries no `<name>.shield` at all -- the ONLY way
    `check_promotable`'s 'shield.yml does not declare template: true'
    branch stays reachable once discovery's own pending/axes are
    template-only. Before plurality this name would be invisible to
    discover_shields entirely (it was never in `lib.pending`)."""
    root = tmp_path / "shields"
    legacy_dir = root / "legacy_overlay_shield"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "shield.yml").write_text(textwrap.dedent("""\
        shield:
          name: legacy_overlay_shield
          full_name: A classic Zephyr shield with metadata, never a template
        """))
    shields = discover_shields([str(root)])
    assert shields["legacy_overlay_shield"].has_yml
    assert not shields["legacy_overlay_shield"].template
    err = check_promotable("legacy_overlay_shield",
                           shields["legacy_overlay_shield"], variant=None)
    assert err is not None
    assert "template: true" in err
    assert "no shield.yml" not in err


def test_discover_shields_reports_two_plural_names_independently(
        tmp_path: Path) -> None:
    """Two names sharing ONE folder's `shields:` list answer the
    promotability question SEPARATELY: `promoted` has its own `<name>.
    shield` and `template: true`, `sibling` has neither -- proving
    `template`/`has_yml` are read per NAME, not once per folder."""
    root = tmp_path / "shields"
    plural_dir = root / "plural_folder"
    plural_dir.mkdir(parents=True)
    (plural_dir / "shield.yml").write_text(textwrap.dedent("""\
        shields:
          - name: promoted
            template: true
          - name: sibling
        """))
    (plural_dir / "promoted.shield").write_text("/* fixture */\n")
    shields = discover_shields([str(root)])
    assert shields["promoted"].template and shields["promoted"].has_yml
    assert not shields["sibling"].template
    assert shields["sibling"].has_yml
    assert shields["promoted"].dir == shields["sibling"].dir == str(plural_dir)


def test_discover_shields_reports_a_template_entry_whose_file_is_missing(
        tmp_path: Path) -> None:
    """A `template: true` entry with no `<name>.shield` stays a name this
    census REPORTS, flag and all, and `check_promotable` deliberately
    passes it: the scan's own lang-shield-template finding already says
    precisely what is wrong, and a second vocabulary here would either
    duplicate it or contradict it. Promotion then fails at load, where
    the name genuinely cannot resolve. Pins the fact that `template=True`
    means DECLARED, never resolvable."""
    root = tmp_path / "shields"
    ghost_dir = root / "ghost_folder"
    ghost_dir.mkdir(parents=True)
    (ghost_dir / "shield.yml").write_text(textwrap.dedent("""\
        shields:
          - name: ghost_template
            template: true
        """))
    shields = discover_shields([str(root)])
    assert shields["ghost_template"].template
    assert shields["ghost_template"].has_yml
    assert check_promotable("ghost_template", shields["ghost_template"],
                            variant=None) is None


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


# ---------------------------------------------------------------- census predicate (Sec 2.3)

def _device(label: str, declared_params: List[str],
           extra_props: List[Tuple[str, str]]) -> Device:
    return Device(name=label, label=label, compatible="vnd,fixture",
                  bus=None, group=None, reg=None, addr_from=None,
                  cs_position=None, declared_params=declared_params,
                  extra_props=extra_props)


def _shield(*devices: Device) -> Shield:
    return Shield(name="fixture_shield", label="fixture_shield",
                 plugs="grove", devices=list(devices))


def test_a_device_with_a_required_param_makes_the_shield_ineligible() -> None:
    """Mirrors params.check_param_invariant's own rule: a declared param
    with no authored default (no matching extra_props entry) is
    required -- the shield is not eligible for the singleton law."""
    dev = _device("d0", declared_params=["zephyr,code"], extra_props=[])
    assert shield_declares_required_params(_shield(dev)) is True


def test_a_device_with_an_authored_default_is_not_required() -> None:
    """The SAME declared param name, but with an extra_props entry (the
    shield authored a default) -- check_param_invariant's own "may be
    omitted" branch -- so the shield stays eligible."""
    dev = _device("d0", declared_params=["zephyr,code"],
                 extra_props=[("zephyr,code", "0")])
    assert shield_declares_required_params(_shield(dev)) is False


def test_a_device_with_no_params_at_all_is_not_required() -> None:
    dev = _device("d0", declared_params=[], extra_props=[])
    assert shield_declares_required_params(_shield(dev)) is False


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


# ------------------------------------------- promotion options (Tobi, 2026-08-08)

def test_no_opts_is_an_empty_mapping_not_an_error() -> None:
    """A bare promotion target is the overwhelmingly common case and must
    stay free of the option grammar entirely."""
    assert parse_promotion_opts(None, "flash_click") == \
        ParsedPromotionOpts(fixed={}, params={})
    assert parse_promotion_opts("", "flash_click") == \
        ParsedPromotionOpts(fixed={}, params={})


def test_socket_assignment_parses() -> None:
    assert parse_promotion_opts("socket=quail_sock1", "t") == \
        ParsedPromotionOpts(fixed={"socket": "quail_sock1"}, params={})


def test_a_bare_word_is_refused_rather_than_read_as_a_socket() -> None:
    """Decision 3: explicit `key=value` only. `flash_click:quail_sock1`
    is the shorthand deliberately NOT adopted -- a positional rule would
    have to be re-litigated the moment a second option lands, so it is an
    error today rather than a meaning that changes later."""
    err = parse_promotion_opts("quail_sock1", "flash_click:quail_sock1")
    assert isinstance(err, str)
    assert "<key>=<value>" in err


def test_an_unknown_key_names_the_known_ones() -> None:
    err = parse_promotion_opts("sockets=quail_sock1", "t")
    assert isinstance(err, str)
    assert "sockets" in err and "socket" in err


def test_name_is_not_an_option_key() -> None:
    """Excluded ON PURPOSE, not merely absent: S4's singleton identity
    law pins the desugared instance name to the shield name, and that
    name reaches config-sheet.md, so a CLI slot for it would let a user
    break the law from the command line."""
    err = parse_promotion_opts("name=something_else", "t")
    assert isinstance(err, str)
    assert "unknown promotion option" in err


def test_an_empty_value_is_refused() -> None:
    err = parse_promotion_opts("socket=", "t")
    assert isinstance(err, str)
    assert "empty value" in err


def test_a_repeated_key_is_refused_rather_than_last_wins() -> None:
    """Silently taking the last would build against a socket the target
    also names differently -- ambiguous input, not a preference."""
    err = parse_promotion_opts("socket=a:socket=b", "t")
    assert isinstance(err, str)
    assert "more than once" in err


def test_promote_shield_with_a_socket_emits_it_on_the_one_instance() -> None:
    promoted = promote_shield("flash_click", socket="quail_sock1")
    assert promoted.content == (
        "instances:\n"
        "  - name: flash_click\n"
        "    shield: flash_click\n"
        "    socket: quail_sock1\n")


def test_promote_shield_without_a_socket_stays_socket_less() -> None:
    """The default is unchanged: socket-LESS, so unique-by-type
    inference still resolves it board-agnostically. S4's identity law
    compares against exactly this text."""
    assert "socket:" not in promote_shield("flash_click").content


def test_a_socketed_promoted_shield_round_trips_through_the_loader(
        tmp_path: Path) -> None:
    """The same round-trip proof the revision case above carries: the
    synthesized text is not merely well-formed, it LOADS, and the socket
    reaches the instance the loader builds."""
    promoted = promote_shield("flash_click", socket="quail_sock1")
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(promoted.rig_yml)
    (rig_dir / promoted.content_name).write_text(promoted.content)

    types, _deps = load_types()
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(tmp_path / "workdir"), types=types,
        board="some_board")

    assert diags == []
    assert rig is not None
    assert rig.instances[0].socket == "quail_sock1"


# ---------------------------------- <device>.<prop> parameter assignments (Sec 9.6 part 2)

def test_a_dotted_key_parses_as_a_device_parameter() -> None:
    parsed = parse_promotion_opts("gb_key.zephyr,code=INPUT_KEY_0", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={}, params={"gb_key": {"zephyr,code": "INPUT_KEY_0"}})


def test_a_dotted_key_and_a_fixed_key_coexist() -> None:
    parsed = parse_promotion_opts(
        "socket=quail_sock1:gb_key.zephyr,code=INPUT_KEY_0", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={"socket": "quail_sock1"},
        params={"gb_key": {"zephyr,code": "INPUT_KEY_0"}})


def test_only_the_first_dot_separates_device_from_property() -> None:
    """Negative control: a property name that itself contains a literal
    '.' (legal devicetree, if rare) must not be mis-split -- everything
    after the FIRST dot, dots included, is the property name verbatim.
    Splitting on every dot would instead produce a device 'gb_key' and a
    mangled property 'vnd', silently dropping '.threshold'."""
    parsed = parse_promotion_opts("gb_key.vnd,threshold.sub=5", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={}, params={"gb_key": {"vnd,threshold.sub": "5"}})


def test_a_dotted_key_with_no_device_label_is_malformed() -> None:
    err = parse_promotion_opts(".zephyr,code=INPUT_KEY_0", "t")
    assert isinstance(err, str)
    assert "<device>.<prop>" in err


def test_a_dotted_key_with_no_property_name_is_malformed() -> None:
    err = parse_promotion_opts("gb_key.=INPUT_KEY_0", "t")
    assert isinstance(err, str)
    assert "<device>.<prop>" in err


def test_a_dotted_key_given_more_than_once_is_refused() -> None:
    err = parse_promotion_opts(
        "gb_key.zephyr,code=INPUT_KEY_0:gb_key.zephyr,code=INPUT_KEY_1", "t")
    assert isinstance(err, str)
    assert "more than once" in err


def test_a_dotted_key_with_an_empty_value_is_refused() -> None:
    err = parse_promotion_opts("gb_key.zephyr,code=", "t")
    assert isinstance(err, str)
    assert "empty value" in err


def test_a_repeated_dotted_key_with_an_empty_value_reports_the_duplicate() -> None:
    """When one assignment is both a repeat AND empty-valued, the
    duplicate check fires first -- the same order the fixed-key branch
    below uses, so the two grammar halves refuse identically rather than
    each picking its own order."""
    err = parse_promotion_opts(
        "gb_key.zephyr,code=INPUT_KEY_0:gb_key.zephyr,code=", "t")
    assert isinstance(err, str)
    assert "more than once" in err


def test_a_repeated_fixed_key_with_an_empty_value_reports_the_duplicate_too() -> None:
    """The fixed-key branch's own order, pinned as the oracle the dotted
    branch above now matches: duplicate-check before empty-value-check."""
    err = parse_promotion_opts("socket=a:socket=", "t")
    assert isinstance(err, str)
    assert "more than once" in err


def test_promote_shield_with_params_emits_the_params_block_on_the_instance() -> None:
    """The printed shape must match a real rig.yml's own params: block
    exactly (boards/rigs/lotus_buttons/lotus_buttons.yml:25-27): 4-space
    params:, 6-space device label, 8-space '<prop>: <value>'."""
    promoted = promote_shield(
        "grove_btn", params={"gb_key": {"zephyr,code": "INPUT_KEY_0"}})
    assert promoted.content == (
        "instances:\n"
        "  - name: grove_btn\n"
        "    shield: grove_btn\n"
        "    params:\n"
        "      gb_key:\n"
        "        zephyr,code: INPUT_KEY_0\n")


def test_promote_shield_with_params_and_a_socket_orders_socket_first() -> None:
    promoted = promote_shield(
        "grove_btn", socket="quail_sock1",
        params={"gb_key": {"zephyr,code": "INPUT_KEY_0"}})
    assert promoted.content == (
        "instances:\n"
        "  - name: grove_btn\n"
        "    shield: grove_btn\n"
        "    socket: quail_sock1\n"
        "    params:\n"
        "      gb_key:\n"
        "        zephyr,code: INPUT_KEY_0\n")


def test_promote_shield_with_no_params_omits_the_block() -> None:
    assert "params:" not in promote_shield("grove_btn").content
    assert "params:" not in promote_shield("grove_btn", params={}).content


def test_a_param_carrying_promoted_shield_round_trips_and_satisfies_the_invariant(
        tmp_path: Path) -> None:
    """Criterion 1/2's own unit-level proof: grove_btn's required,
    no-default zephyr,code (declared via shield,params on gb_key) is
    satisfied entirely through the promoted params: block, with NO
    parallel validation in promote.py -- rule 2 (check_param_invariant)
    passes because the printed text reaches the identical loader path an
    authored rig.yml would."""
    promoted = promote_shield(
        "grove_btn", params={"gb_key": {"zephyr,code": "INPUT_KEY_0"}})
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(promoted.rig_yml)
    (rig_dir / promoted.content_name).write_text(promoted.content)

    types, _deps = load_types()
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(tmp_path / "workdir"), types=types,
        board="some_board")

    assert diags == [], diags
    assert rig is not None
    assert rig.instances[0].params == {"gb_key": {"zephyr,code": "INPUT_KEY_0"}}


def test_a_promoted_shield_missing_its_required_param_still_rejects(
        tmp_path: Path) -> None:
    """Criterion 4, the regression control: a promoted grove_btn given NO
    params: block still fails exactly as an authored rig.yml omitting the
    assignment would -- rule 2, fired by the SAME check_param_invariant,
    never a bespoke promote.py check. Proves the params: block is real
    plumbing, not a rubber stamp that always happens to pass."""
    promoted = promote_shield("grove_btn")
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(promoted.rig_yml)
    (rig_dir / promoted.content_name).write_text(promoted.content)

    types, _deps = load_types()
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(tmp_path / "workdir"), types=types,
        board="some_board")

    assert has_errors(diags)
    assert any("required" in d.message for d in diags), diags
