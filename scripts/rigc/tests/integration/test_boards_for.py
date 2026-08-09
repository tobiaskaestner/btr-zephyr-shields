"""`west rigs --boards-for` driven as a subprocess (board-coordinate-
s2-brief.md). NOT build-marked: `west rigs` itself runs in 0.3s, and
nothing this command reaches configures cmake -- it censuses board
rig-extension SOURCES (board_census.py), never a real board devicetree.
"""
from __future__ import annotations

import os
import subprocess

import pytest
import yaml

from conftest import (REPO_ROOT, WEST_EXE, WEST_TOPDIR, subprocess_timeout,
                      zephyr_base)


def _run(*args: str) -> "subprocess.CompletedProcess[str]":
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zephyr_base()
    return subprocess.run(
        [WEST_EXE, "rigs", *args], cwd=str(WEST_TOPDIR), env=env,
        capture_output=True, text=True, timeout=subprocess_timeout(60))


@pytest.mark.parametrize("rig_target, expected_board", [
    ("lotus_buttons", "seeeduino_lotus/samd21g18a/rig"),
    ("quail_temp_farm", "mikroe_quail/stm32f427xx/rig"),
])
def test_boards_for_the_criterion_answers(rig_target: str, expected_board: str) -> None:
    """Acceptance criterion 3, verbatim. nucleo_datalogger used to be a
    third case here, back when every corpus rig answered exactly its
    declared board (board-coordinate-s2-brief.md's own state of the
    world) -- it moved out to
    test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards
    below once S5's content migration made it answer two boards, which a
    single-`expected_board` parametrization cannot express. grove
    (lotus_buttons) and mikrobus (quail_temp_farm) stay here because only
    one corpus board offers each of those connector types, so migrating
    THEIR content to the conventional label (already true for grove, and
    done in S5 for mikrobus) does not, by itself, open a second answer."""
    result = _run("--boards-for", rig_target)
    assert result.returncode == 0, (
        f"--boards-for {rig_target}: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == expected_board


def test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards() -> None:
    """board-coordinate-s5-brief.md Sec 5.3, ruled as an ACCEPTANCE
    CRITERION: at least one corpus rig's `--boards-for` answer must
    contain more than one board once content migrates off board-prefixed
    labels. Before S5, nucleo_datalogger's content named `nucleo_ard`
    directly, so only nucleo_f401re could ever satisfy it even though
    frdm_k64f's own arduino_r3 socket offers the identical i2c/spi subset,
    mating and stackability adafruit_data_logger needs -- the "helpful"
    board-agnostic reuse board-as-coordinate exists to unlock. Migrating
    nucleo_datalogger.yml to the conventional `arduino_r3` alias is the
    whole fix: no code in board_census.py or analyzer/sockets.py changed,
    only what the content itself is willing to reference against."""
    result = _run("--boards-for", "nucleo_datalogger")
    assert result.returncode == 0, (
        f"--boards-for nucleo_datalogger: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.split() == sorted([
        "frdm_k64f/mk64f12/rig", "nucleo_f401re/stm32f401xe/rig"]), (
        "nucleo_datalogger must now conform to BOTH arduino_r3 boards -- "
        f"the S5 migration's own falsifier\n--- stdout ---\n{result.stdout}")


def test_boards_for_an_unresolved_rig_target_is_a_nonzero_exit_with_list_rigs_own_message() -> None:
    result = _run("--boards-for", "no_such_rig_at_all")
    assert result.returncode != 0
    assert "does not resolve to a rig" in result.stderr


def test_boards_for_a_promoted_shield_answers_the_same_boards_as_the_rig_it_stands_for() -> None:
    """--boards-for resolves BOTH namespaces (the Sec 5 rule --explain
    already applied), and the expectation comes from OUTSIDE this query:
    `ard_datalogger` is the corpus rig that is one adafruit_data_logger on
    an arduino_r3 socket, so the promoted shield -- one SOCKET-LESS
    instance of the same shield, inferring that socket -- must answer
    exactly the same boards. This is the singleton identity law's shape
    at query level: asserting a hand-written board list instead would
    pass just as well against a promotion that silently resolved
    something else, and would have to be re-edited every time a board
    gains an arduino_r3 socket.

    Both answers are also asserted NON-EMPTY: "" == "" is what this
    comparison degrades to the moment promotion stops resolving at all,
    which is precisely the regression it exists to catch."""
    promoted = _run("--boards-for", "adafruit_data_logger")
    assert promoted.returncode == 0, (
        f"--boards-for adafruit_data_logger: exit {promoted.returncode}\n"
        f"{promoted.stderr}")

    persisted = _run("--boards-for", "ard_datalogger")
    assert persisted.returncode == 0, persisted.stderr

    assert promoted.stdout.split(), (
        "the promoted shield answered NO board -- the comparison below "
        f"would be vacuous\n--- stderr ---\n{promoted.stderr}")
    assert promoted.stdout.split() == persisted.stdout.split()


def test_boards_for_a_promoted_shield_whose_socket_is_ambiguous_answers_nothing() -> None:
    """An empty answer is a fact, not an error -- and it must stay
    reachable for a SHIELD, not just a rig. flash_click plugs mikrobus;
    the only mikrobus board (mikroe_quail) offers FOUR such sockets, and a
    promotion desugars to a socket-less instance, so the existing
    unique-by-type inference rule correctly refuses to pick one.

    The control is what makes this mean anything: quail must be censused
    and answering in the same run, or an empty answer would prove only
    that the board went missing. quail_temp_farm (a persisted mikrobus
    rig, socket named explicitly) is that control."""
    result = _run("--boards-for", "flash_click")
    assert result.returncode == 0, (
        f"--boards-for flash_click: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == ""

    control = _run("--boards-for", "quail_temp_farm")
    assert control.stdout.strip() == "mikroe_quail/stm32f427xx/rig", (
        "the mikrobus board is not being censused at all, so flash_click's "
        f"empty answer proves nothing\n--- stdout ---\n{control.stdout}")


def test_boards_for_a_promoted_shield_naming_its_socket_answers_that_board() -> None:
    """The promotion-option grammar's own falsifier, and the exact pair
    that motivated it: the SAME shield answers nothing bare (above) and
    mikroe_quail once the target names which of the four mikrobus sockets
    it means. Asserted as a pair rather than in isolation, because either
    half alone is satisfiable by a stub -- "always empty" passes the test
    above, "always quail" passes this one, and only both together say the
    socket is what made the difference."""
    bare = _run("--boards-for", "flash_click")
    socketed = _run("--boards-for", "flash_click:socket=quail_sock1")

    assert socketed.returncode == 0, (
        f"exit {socketed.returncode}\n{socketed.stderr}")
    assert bare.stdout.strip() == ""
    assert socketed.stdout.strip() == "mikroe_quail/stm32f427xx/rig"


def test_boards_for_a_promoted_shield_with_a_required_param_answers_once_assigned() -> None:
    """The dotted `<device>.<prop>=<value>` promotion-option grammar's own
    falsifier (Sec 9.6 part 2), the same shape the socket= pair above
    uses: grove_btn declares zephyr,code required with no authored
    default (grove_btn.shield), so the bare shield fails rule 2
    (check_param_invariant) exactly as an authored rig.yml omitting the
    assignment would, and assigning it via the dotted grammar clears that
    failure. Asserted as a pair for the same reason the socket= test is:
    either half alone is satisfiable by a stub.

    The "after" answer names exactly one board, `m5stack_nanoc6` --
    seeeduino_lotus offers eight grove sockets (grove_sockets.dtsi), so
    unique-by-type inference cannot pick one there; that ambiguity is a
    separate fact from the params grammar this pair exists to prove, and
    the compose test below is what pins the socket= pairing that resolves
    it. m5stack_nanoc6 offers exactly one (boards/extend/m5stack/
    m5stack_nanoc6/grove_socket.dtsi), so it alone answers unambiguously."""
    bare = _run("--boards-for", "grove_btn")
    assigned = _run("--boards-for", "grove_btn:gb_key.zephyr,code=INPUT_KEY_0")

    assert bare.returncode != 0
    assert "zephyr,code" in bare.stderr

    assert assigned.returncode == 0, (
        f"--boards-for grove_btn:gb_key.zephyr,code=INPUT_KEY_0: exit "
        f"{assigned.returncode}\n{assigned.stderr}")
    assert assigned.stdout.strip() == "m5stack_nanoc6/esp32c6/hpcore/rig"


def test_boards_for_a_promoted_shield_with_socket_and_dotted_param_composes() -> None:
    """A single target string carrying BOTH promotion-option grammar
    categories in one `:`-separated chain -- the fixed keyword `socket=`
    and a dotted `<device>.<prop>=<value>` -- exactly as
    parse_promotion_opts documents the two composing.
    `socket=grove_d2` breaks the eight-way ambiguity the test above hits,
    so this answers exactly the one board that socket lives on."""
    result = _run(
        "--boards-for",
        "grove_btn:socket=grove_d2:gb_key.zephyr,code=INPUT_KEY_0")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "seeeduino_lotus/samd21g18a/rig"


def test_boards_for_promotion_options_on_a_persisted_rig_are_refused() -> None:
    """Decision 1: promotion options are promotion-only. A persisted rig
    has N instances, so `socket=` could not say which one it means --
    refused rather than silently dropped, which would answer a question
    the target did not ask."""
    result = _run("--boards-for", "quail_temp_farm:socket=quail_sock1")
    assert result.returncode != 0
    assert "persisted rig" in result.stderr


def test_boards_for_a_malformed_promotion_option_is_refused_before_any_census() -> None:
    result = _run("--boards-for", "flash_click:sockets=quail_sock1")
    assert result.returncode != 0
    assert "unknown promotion option" in result.stderr


def test_boards_for_a_variant_on_a_promoted_shield_is_refused() -> None:
    """A promoted shield has no variant axis to select, and --boards-for
    refuses one for the same reason --explain does -- the SAME
    check_promotable call, reached through the shared namespace
    resolution rather than a second copy of the rule.

    Asserting only `returncode != 0` and the word "variant" would be
    VACUOUS here, and mutation-checking showed it: delete the
    check_promotable call and this path still exits non-zero with
    "variant" in stderr, because the LOADER then rejects a variant
    selection on a rig that declares no variants: axis. Two different
    refusals, one of which is the wrong one -- the loader's fires only
    after a workdir, a shield-library scan and a full parse, and says
    nothing about promotion. So the assertion is check_promotable's own
    sentence, which no other code path in the tree emits."""
    result = _run("--boards-for", "adafruit_data_logger/some_variant")
    assert result.returncode != 0
    assert "a promoted shield has no variant axis to select from" in result.stderr, (
        "refused, but not by check_promotable -- see this test's docstring"
        f"\n--- stderr ---\n{result.stderr}")


def test_boards_for_a_name_that_is_both_a_rig_and_a_shield_is_an_error_naming_both(
        tmp_path) -> None:
    """The Sec 5 collision, now that --boards-for resolves both
    namespaces: it must ERROR rather than silently pick one. Constructed
    the same way test_explain.py constructs it -- a scratch --board-root
    carrying a rig folder named after a REAL shield, additive only, never
    a mutation of tracked content."""
    rig_dir = tmp_path / "boards" / "rigs" / "adafruit_data_logger"
    rig_dir.mkdir(parents=True)
    (rig_dir / "rig.yml").write_text("rig:\n  name: adafruit_data_logger\n")

    result = _run("--boards-for", "adafruit_data_logger",
                  "--board-root", str(tmp_path))
    assert result.returncode != 0
    assert "both" in result.stderr
    assert str(rig_dir) in result.stderr


def test_west_rigs_with_no_flag_still_lists_every_rig_unchanged() -> None:
    """Acceptance criterion 2: --boards-for absent behaves exactly as
    today -- the same rig NAMES, one per line. Asserting the count alone
    would hold just as well if the listing started printing board targets
    instead, so the expectation is the names themselves, taken from
    list_rigs (the module `west rigs` renders from) rather than from this
    command's own output."""
    result = _run()
    assert result.returncode == 0
    expected = sorted(
        yaml.safe_load(p.read_text())["rig"]["name"]
        for p in (REPO_ROOT / "boards" / "rigs").glob("*/rig.yml"))
    assert sorted(result.stdout.split()) == expected
