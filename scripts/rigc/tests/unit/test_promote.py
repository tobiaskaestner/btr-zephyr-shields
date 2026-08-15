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
                          check_list_no_duplicate_elements, check_promotable,
                          parse_promotion_opts, discover_shields,
                          list_element_is_a_rig_error,
                          list_element_not_a_shield_error, promote_shield,
                          promote_shield_list,
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


def test_a_multiplug_shield_is_now_promotable() -> None:
    """Ruling 4's plurality gate is RETIRED as of multi-plug-promotion-
    brief.md slice 3 (per-slot promotion, socket.<slot>=<label>) -- this
    test used to pin check_promotable's own plug_count refusal
    (multi-plug-shield-brief.md Sec 6) and flips with it (mechanism and
    tests together) rather than dying outright: check_promotable no
    longer takes a plug_count at all, and never refuses a multi-plug
    shield on that basis. The slot-optioned grammar's own refusals
    (bare socket= on a plural shield, an unknown slot) now live in
    parse_promotion_opts -- see the socket.<slot>= section below."""
    info = ShieldInfo(name="can_span_click", dir="/m/boards/shields/can_span_click",
                     template=True, has_yml=True)
    assert check_promotable("can_span_click", info, variant=None) is None


# ---------------------------------------------------------------- shield_is_multiplug

def test_shield_is_multiplug_true_for_two_plugs() -> None:
    from rigc.promote import shield_is_multiplug

    shield = Shield(name="sh", label="sh", plugs={"left": "t", "right": "t"})
    assert shield_is_multiplug(shield) is True


def test_shield_is_multiplug_false_for_the_single_plug_default_slot() -> None:
    from rigc.promote import shield_is_multiplug

    shield = Shield(name="sh", label="sh", plugs={"plug": "t"})
    assert shield_is_multiplug(shield) is False


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
    every one of today's 25 corpus shields does -- 15 one-per-folder plus
    four plurality folders: lcd_char_1602/lcd_tft_24 (shield-plurality-
    brief.md Sec 5, boards/shields/arduino_lcd/, named neither),
    grove_sens_bme280/grove_sens_bmp280/grove_sens_dps310
    (boards/shields/grove_sens/, named neither -- three shields, one
    `.shield` per name, following arduino_lcd's own precedent),
    grove_led/grove_pwm_led/grove_pwm_led_inv (boards/shields/grove_led/,
    sharing the folder bridle's own grove_led/ keeps both LED kinds in --
    the one plurality folder actually named after one of its own members;
    grove_pwm_led_inv, item 36's own nonzero-flags witness, is NOT a
    bridle port and joins this same folder rather than a new one, since
    it is grove_pwm_led's own inverted-polarity sibling), and
    seeed_grove_base_v1/seeed_grove_base_v2 (grove-carriers-brief.md,
    boards/shields/grove/, named neither -- the `arduino_lcd` falsifier
    shape again, acceptance criterion 1); can_span_click and
    mikrobus_span_adapter (the multi-plug corpus shields --
    multi-plug-shield-brief.md and multi-plug-carrier-brief.md's own
    examples) are two of the 15 -- DISCOVERABLE, `template: true`, and
    (as of multi-plug-promotion-brief.md slice 3) genuinely promotable
    too, this census predicate having no plurality concept at all.
    Falsified by mutating a real shield.yml, not by editing this
    assertion (see the mutation test below) -- this one just proves the
    real tree is clean today."""
    shields = discover_shields()
    assert len(shields) == 25
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
    assert rig.instances[0].sockets["plug"] is None


# ---------------------------------------------------------------- census predicate (Sec 2.3)

def _device(label: str, declared_params: List[str],
           extra_props: List[Tuple[str, str]]) -> Device:
    return Device(name=label, label=label, compatible="vnd,fixture",
                  bus=None, group=None, reg=None, addr_from=None,
                  cs_position=None, declared_params=declared_params,
                  extra_props=extra_props)


def _shield(*devices: Device) -> Shield:
    return Shield(name="fixture_shield", label="fixture_shield",
                 plugs={"plug": "grove"}, devices=list(devices))


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
    assert rig.instances[0].sockets["plug"] == "quail_sock1"


# --------------------- socket.<slot>= per-slot promotion grammar (multi-plug-promotion-brief.md Sec 2)

_PLURAL_SHIELD = Shield(name="can_span_click", label="can_span_click",
                       plugs={"left": "mikrobus", "right": "mikrobus"})
_SINGLE_SHIELD = Shield(name="flash_click", label="flash_click",
                       plugs={"plug": "mikrobus"})


def test_socket_dot_slot_parses_as_a_slot_assignment_not_a_param() -> None:
    """The socket. dotted-key prefix is RESERVED (Sec 2): unlike every
    other dotted key, it never routes to params -- even with no shield
    given to validate the slot name against (the reservation is
    unconditional, purely syntactic)."""
    parsed = parse_promotion_opts("socket.left=quail_sock2", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={}, params={}, sockets={"left": "quail_sock2"})


def test_two_slot_assignments_compose() -> None:
    parsed = parse_promotion_opts(
        "socket.left=quail_sock2:socket.right=quail_sock3", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={}, params={},
        sockets={"left": "quail_sock2", "right": "quail_sock3"})


def test_a_repeated_slot_is_refused_rather_than_last_wins() -> None:
    """Mirrors the fixed-key and dotted-param duplicate refusals above --
    today's `fixed` dict would otherwise silently last-win, and the same
    would be true of a naively-built sockets dict."""
    err = parse_promotion_opts("socket.left=a:socket.left=b", "t")
    assert isinstance(err, str)
    assert "given more than once" in err


def test_a_slot_assignment_with_an_empty_value_is_refused() -> None:
    err = parse_promotion_opts("socket.left=", "t")
    assert isinstance(err, str)
    assert "empty value" in err


def test_a_bare_socket_on_a_plural_shield_is_refused_naming_the_slots() -> None:
    err = parse_promotion_opts("socket=quail_sock2", "t", _PLURAL_SHIELD)
    assert isinstance(err, str)
    assert "plugs 2 sockets" in err
    assert "socket.<slot>=" in err
    assert "left" in err and "right" in err


def test_a_bare_socket_on_a_single_plug_shield_is_unaffected() -> None:
    """Byte-untouched (Sec 2's own criterion): a resolved single-plug
    shield's bare socket= parses exactly as it did before this slice."""
    parsed = parse_promotion_opts("socket=quail_sock1", "t", _SINGLE_SHIELD)
    assert parsed == ParsedPromotionOpts(
        fixed={"socket": "quail_sock1"}, params={}, sockets={})


def test_a_dotted_slot_on_a_single_plug_shield_is_refused_pointing_at_the_bare_form() -> None:
    err = parse_promotion_opts("socket.plug=quail_sock1", "t", _SINGLE_SHIELD)
    assert isinstance(err, str)
    assert "single plug" in err
    assert "socket=<label>" in err


def test_an_unknown_slot_names_the_real_slots() -> None:
    err = parse_promotion_opts("socket.bogus=quail_sock2", "t", _PLURAL_SHIELD)
    assert isinstance(err, str)
    assert "unknown slot 'bogus'" in err
    assert "left" in err and "right" in err


def test_a_slot_assignment_with_no_slot_name_is_malformed() -> None:
    err = parse_promotion_opts("socket.=quail_sock2", "t", _PLURAL_SHIELD)
    assert isinstance(err, str)
    assert "<device>.<prop>" in err


def test_no_shield_given_skips_slot_validation_but_still_parses() -> None:
    """`shield=None` (the default) is the backward-compatible case,
    mirroring check_promotable's own retired plug_count default: a
    caller that has not resolved the shield at all gets neither the
    plural-bare refusal nor the unknown-slot refusal, but the slot
    assignment still parses (routing is unconditional -- only
    VALIDATION against real slot names needs the shield)."""
    parsed = parse_promotion_opts("socket.anything=quail_sock2", "t")
    assert parsed == ParsedPromotionOpts(
        fixed={}, params={}, sockets={"anything": "quail_sock2"})
    bare = parse_promotion_opts("socket=quail_sock2", "t")
    assert bare == ParsedPromotionOpts(
        fixed={"socket": "quail_sock2"}, params={}, sockets={})


def test_promote_shield_with_a_sockets_map_emits_the_plural_form() -> None:
    promoted = promote_shield(
        "can_span_click",
        sockets={"left": "quail_sock2", "right": "quail_sock3"})
    assert promoted.content == (
        "instances:\n"
        "  - name: can_span_click\n"
        "    shield: can_span_click\n"
        "    sockets:\n"
        "      left: quail_sock2\n"
        "      right: quail_sock3\n")


def test_promote_shield_prefers_the_sockets_map_when_both_are_given() -> None:
    """Documented behavior (promote_shield's own docstring), not a
    validated invariant -- parse_promotion_opts is what actually keeps
    the two mutually exclusive by construction; this pins the printer's
    own precedence directly."""
    promoted = promote_shield(
        "can_span_click", socket="ignored_single_form",
        sockets={"left": "quail_sock2", "right": "quail_sock3"})
    assert "socket: ignored_single_form" not in promoted.content
    assert "sockets:" in promoted.content


def test_promote_shield_with_a_sockets_map_and_params_orders_sockets_first() -> None:
    promoted = promote_shield(
        "can_span_click",
        sockets={"left": "quail_sock2", "right": "quail_sock3"},
        params={"can0": {"spi-max-frequency": "1000000"}})
    assert promoted.content == (
        "instances:\n"
        "  - name: can_span_click\n"
        "    shield: can_span_click\n"
        "    sockets:\n"
        "      left: quail_sock2\n"
        "      right: quail_sock3\n"
        "    params:\n"
        "      can0:\n"
        "        spi-max-frequency: 1000000\n")


def test_promote_shield_with_a_sockets_map_round_trips_through_the_loader(
        tmp_path: Path) -> None:
    """The plural counterpart of test_a_socketed_promoted_shield_round_
    trips_through_the_loader: the synthesized sockets: block is not
    merely well-formed, it LOADS, and both slot assignments reach the
    instance the loader builds -- against the REAL can_span_click
    template already in the corpus (slice 1/2), not a fixture stand-in."""
    promoted = promote_shield(
        "can_span_click",
        sockets={"left": "quail_sock2", "right": "quail_sock3"})
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
    assert rig.instances[0].sockets == {
        "left": "quail_sock2", "right": "quail_sock3"}


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


# ------------------------------------------------- list promotion (slice 4)

def test_promote_shield_list_of_one_is_byte_identical_to_promote_shield() -> None:
    """Sec 8 criterion 1, at the unit level: a one-element list renders
    through the IDENTICAL `_render_instance` helper `promote_shield`
    itself uses, so this must be byte-for-byte the same PromotedRig --
    proven directly, not merely asserted by construction."""
    single = promote_shield("flash_click", socket="quail_sock1")
    listed = promote_shield_list(
        [("flash_click", None,
          ParsedPromotionOpts(fixed={"socket": "quail_sock1"}, params={}))])
    assert listed.rig_yml == single.rig_yml
    assert listed.content_name == single.content_name
    assert listed.content == single.content


def test_promote_shield_list_composes_two_elements_under_one_rig() -> None:
    listed = promote_shield_list([
        ("eth_click", None,
         ParsedPromotionOpts(fixed={"socket": "quail_sock1"}, params={})),
        ("flash_click", None,
         ParsedPromotionOpts(fixed={"socket": "quail_sock2"}, params={})),
    ])
    assert listed.rig_yml == "rig:\n  name: eth_click+flash_click\n"
    assert listed.content_name == "eth_click+flash_click.yml"
    assert listed.content == (
        "instances:\n"
        "  - name: eth_click\n"
        "    shield: eth_click\n"
        "    socket: quail_sock1\n"
        "  - name: flash_click\n"
        "    shield: flash_click\n"
        "    socket: quail_sock2\n")


def test_promote_shield_list_threads_revision_sockets_and_params_per_element() -> None:
    """Every element carries its OWN revision/sockets-map/params,
    independently -- the per-element grammar composing over N elements,
    never one axis shared across the whole list."""
    listed = promote_shield_list([
        ("i2c_sensor", "2",
         ParsedPromotionOpts(fixed={}, params={})),
        ("can_span_click", None,
         ParsedPromotionOpts(
             fixed={}, params={},
             sockets={"left": "quail_sock2", "right": "quail_sock3"})),
    ])
    assert listed.content == (
        "instances:\n"
        "  - name: i2c_sensor\n"
        "    shield: i2c_sensor@2\n"
        "  - name: can_span_click\n"
        "    shield: can_span_click\n"
        "    sockets:\n"
        "      left: quail_sock2\n"
        "      right: quail_sock3\n")


def test_promote_shield_list_round_trips_through_the_loader(
        tmp_path: Path) -> None:
    listed = promote_shield_list([
        ("eth_click", None,
         ParsedPromotionOpts(fixed={"socket": "quail_sock1"}, params={})),
        ("flash_click", None,
         ParsedPromotionOpts(fixed={"socket": "quail_sock2"}, params={})),
    ])
    rig_dir = tmp_path / "rig"
    rig_dir.mkdir()
    (rig_dir / "rig.yml").write_text(listed.rig_yml)
    (rig_dir / listed.content_name).write_text(listed.content)

    types, _deps = load_types()
    rig, diags, _load_deps = loader.load(
        str(rig_dir / "rig.yml"), str(tmp_path / "workdir"), types=types,
        board="some_board")

    assert diags == [], diags
    assert rig is not None
    assert rig.name == "eth_click+flash_click"
    assert [inst.name for inst in rig.instances] == ["eth_click", "flash_click"]
    assert rig.instances[0].sockets["plug"] == "quail_sock1"
    assert rig.instances[1].sockets["plug"] == "quail_sock2"


# --------------------------------------------- list duplicate/namespace refusals

def test_check_list_no_duplicate_elements_passes_on_unique_names() -> None:
    assert check_list_no_duplicate_elements(
        ["eth_click", "flash_click"], "eth_click;flash_click") is None


def test_check_list_no_duplicate_elements_names_the_repeated_shield() -> None:
    err = check_list_no_duplicate_elements(
        ["eth_click", "eth_click"], "eth_click;eth_click")
    assert isinstance(err, str)
    assert "eth_click" in err
    assert "more than once" in err


def test_check_list_no_duplicate_elements_names_the_first_repeat() -> None:
    err = check_list_no_duplicate_elements(
        ["a", "b", "a", "b"], "a;b;a;b")
    assert isinstance(err, str)
    assert "'a'" in err


def test_list_element_is_a_rig_error_names_the_element_target_and_rig_dir() -> None:
    msg = list_element_is_a_rig_error(
        "quail_temp_farm", "eth_click;quail_temp_farm",
        Path("/some/boards/rigs/quail_temp_farm"))
    assert "quail_temp_farm" in msg
    assert "eth_click;quail_temp_farm" in msg
    assert "/some/boards/rigs/quail_temp_farm" in msg
    assert "shield" in msg


def test_list_element_not_a_shield_error_names_the_element_and_target() -> None:
    msg = list_element_not_a_shield_error("no_such_thing", "eth_click;no_such_thing")
    assert "no_such_thing" in msg
    assert "eth_click;no_such_thing" in msg
