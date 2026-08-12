"""`west rigs --explain` driven as a subprocess (board-coordinate-
s3-brief.md, S3a). NOT build-marked: this command touches no cmake, no
cpp, no board -- a promoted shield's two documents are pure text and a
persisted rig's are read verbatim off disk.
"""
from __future__ import annotations

import os
import subprocess
import textwrap

import yaml

from conftest import REPO_ROOT, WEST_EXE, WEST_TOPDIR, subprocess_timeout


def _run(*args: str) -> "subprocess.CompletedProcess[str]":
    env = dict(os.environ)
    return subprocess.run(
        [WEST_EXE, "rigs", *args], cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(60))


def test_explain_a_promoted_shield_prints_the_desugared_pair() -> None:
    """Criterion 2: the synthesized rig.yml has no board:, the content
    file has exactly one instance named after the shield, no socket:."""
    result = _run("--explain", "adafruit_data_logger")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: adafruit_data_logger

        # adafruit_data_logger.yml
        instances:
          - name: adafruit_data_logger
            shield: adafruit_data_logger
        """)


def test_explain_a_persisted_rig_prints_its_two_files_verbatim() -> None:
    """Criterion 3."""
    rig_dir = REPO_ROOT / "boards" / "rigs" / "nucleo_datalogger"
    rig_yml_text = (rig_dir / "rig.yml").read_text().rstrip("\n")
    content_text = (rig_dir / "nucleo_datalogger.yml").read_text().rstrip("\n")

    result = _run("--explain", "nucleo_datalogger")
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"# rig.yml\n{rig_yml_text}\n"
        "\n"
        f"# nucleo_datalogger.yml\n{content_text}\n")


def test_explain_a_name_that_is_neither_a_rig_nor_a_shield_reuses_the_existing_message() -> None:
    """Criterion 4, the "neither" branch: the message list_rigs.
    resolve_rig_target already owns for an unresolved -DRIG target, never
    a second one invented for --explain."""
    result = _run("--explain", "no_such_target_at_all")
    assert result.returncode != 0
    assert "does not resolve to a rig" in result.stderr


def test_explain_a_name_that_is_both_a_rig_and_a_shield_is_an_error_naming_both(
        tmp_path) -> None:
    """Criterion 4, the "both" branch. No natural collision exists in the
    tree, so this constructs one: a scratch --board-root carrying a rig
    folder named after a REAL shield (adafruit_data_logger) -- additive
    only, never a mutation of tracked content, so no restore is needed."""
    rig_dir = tmp_path / "boards" / "rigs" / "adafruit_data_logger"
    rig_dir.mkdir(parents=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: adafruit_data_logger\n")

    result = _run("--explain", "adafruit_data_logger",
                  "--board-root", str(tmp_path))
    assert result.returncode != 0
    assert "adafruit_data_logger" in result.stderr
    assert "both" in result.stderr
    assert str(rig_dir) in result.stderr


def test_explain_a_variant_on_a_promoted_shield_is_refused() -> None:
    result = _run("--explain", "adafruit_data_logger/some_variant")
    assert result.returncode != 0
    assert "variant" in result.stderr


def test_west_rigs_with_no_flag_is_unaffected_by_explain_landing() -> None:
    """Criterion 5, the cheap half: plain `west rigs` still lists every
    corpus rig's own rig.yml name, one per line -- --boards-for's own
    test already covers this in depth; this is --explain's own
    confirmation that adding a THIRD short-circuiting flag changed
    nothing about the default path."""
    result = _run()
    assert result.returncode == 0
    expected = sorted(
        yaml.safe_load(p.read_text())["rig"]["name"]
        for p in (REPO_ROOT / "boards" / "rigs").glob("*/rig.yml"))
    assert sorted(result.stdout.split()) == expected


def test_explain_a_promoted_shield_with_a_socket_shows_it_on_the_instance() -> None:
    """The promotion-option grammar, printed: --explain is the oracle for
    what `--rig <shield>:socket=<label>` actually desugars to, exactly as
    it is for the bare form above."""
    result = _run("--explain", "flash_click:socket=quail_sock1")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: flash_click

        # flash_click.yml
        instances:
          - name: flash_click
            shield: flash_click
            socket: quail_sock1
        """)


def test_explain_a_promoted_shield_with_params_shows_them_on_the_instance() -> None:
    """The dotted `<device>.<prop>=<value>` promotion-option grammar (Sec
    9.6 part 2), printed the same way the fixed-keyword `socket=` case
    above is: --explain is the oracle for what a promoted shield's
    params: block actually desugars to."""
    result = _run("--explain", "grove_btn:gb_key.zephyr,code=INPUT_KEY_0")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: grove_btn

        # grove_btn.yml
        instances:
          - name: grove_btn
            shield: grove_btn
            params:
              gb_key:
                zephyr,code: INPUT_KEY_0
        """)


def test_explain_a_promoted_plural_shield_with_slot_options_shows_the_sockets_map() -> None:
    """The slot-qualified `socket.<slot>=<label>` promotion-option grammar
    (multi-plug-promotion-brief.md Sec 2), printed the same way the
    single-plug `socket=` case above is: --explain is the oracle for what
    a plural shield's sockets: block actually desugars to -- and this is
    the one caller of that threading (`_explain`'s own promote_shield
    call) the other query-surface tests do not reach."""
    result = _run("--explain",
                 "can_span_click:socket.left=quail_sock2:socket.right=quail_sock3")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: can_span_click

        # can_span_click.yml
        instances:
          - name: can_span_click
            shield: can_span_click
            sockets:
              left: quail_sock2
              right: quail_sock3
        """)


def test_explain_a_bare_socket_on_a_plural_shield_is_refused_naming_the_slots() -> None:
    """The bare-on-plural refusal, through --explain's own path: the
    sentence names both the dotted form and the shield's real slots."""
    result = _run("--explain", "can_span_click:socket=quail_sock2")
    assert result.returncode != 0
    assert "use socket.<slot>=<label> (slots: left, right)" in result.stderr
    assert "not bare socket=<label>" in result.stderr


def test_explain_promotion_options_on_a_persisted_rig_are_refused() -> None:
    """Decision 1, on the other query surface -- and it must be the SAME
    refusal: the message comes from list_rigs, which the cmake seam uses
    too, never a second wording owned by this command."""
    result = _run("--explain", "nucleo_datalogger:socket=arduino_r3")
    assert result.returncode != 0
    assert "persisted rig" in result.stderr


# --------------------------------------------------- list promotion (slice 4)

def test_explain_a_list_target_prints_the_desugared_n_instance_pair() -> None:
    """multi-plug-list-brief.md Sec 3: --explain prints the N-instance
    desugared pair -- the rig's own name is every element's shield name
    joined with `+`, and the content file carries one instance per
    element, each with its own socket, in order."""
    result = _run(
        "--explain",
        "eth_click:socket=quail_sock1;flash_click:socket=quail_sock2")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: eth_click+flash_click

        # eth_click+flash_click.yml
        instances:
          - name: eth_click
            shield: eth_click
            socket: quail_sock1
          - name: flash_click
            shield: flash_click
            socket: quail_sock2
        """)


def test_explain_a_list_target_with_a_duplicate_element_is_refused() -> None:
    """Ruling 2 (Sec 1): [a, a] is refused first, with its own sentence."""
    result = _run("--explain", "eth_click;eth_click")
    assert result.returncode != 0
    assert "eth_click" in result.stderr
    assert "more than once" in result.stderr


def test_explain_a_list_target_with_a_persisted_rig_element_is_refused() -> None:
    """Every element must be a SHIELD (Sec 2): a persisted rig inside a
    list is refused with its own sentence naming it."""
    result = _run("--explain", "eth_click;nucleo_datalogger")
    assert result.returncode != 0
    assert "nucleo_datalogger" in result.stderr
    assert "names a persisted rig" in result.stderr
    assert "every element of a list promotion target must be a shield" in result.stderr


def test_explain_a_list_target_with_a_multiplug_element_composes() -> None:
    """The per-element grammar (multi-plug-promotion-brief.md Sec 2)
    composes over N list elements unchanged: can_span_click's own
    socket.<slot>= sockets: map, alongside a single-plug shield's bare
    socket:."""
    result = _run(
        "--explain",
        "can_span_click:socket.left=quail_sock2:socket.right=quail_sock3;"
        "flash_click:socket=quail_sock1")
    assert result.returncode == 0, result.stderr
    assert result.stdout == textwrap.dedent("""\
        # rig.yml
        rig:
          name: can_span_click+flash_click

        # can_span_click+flash_click.yml
        instances:
          - name: can_span_click
            shield: can_span_click
            sockets:
              left: quail_sock2
              right: quail_sock3
          - name: flash_click
            shield: flash_click
            socket: quail_sock1
        """)
