"""`west rigs --boards-for` driven as a subprocess. NOT build-marked:
`west rigs` itself runs in 0.3s, and
nothing this command reaches configures cmake -- it censuses board
rig-extension SOURCES (board/census.py), never a real board devicetree.
"""
from __future__ import annotations

import os
import subprocess

import pytest
import yaml

from harness import (REPO_ROOT, WEST_EXE, WEST_TOPDIR, subprocess_timeout,
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
def test_boards_for_answers_the_one_board_each_connector_type_offers(
        rig_target: str, expected_board: str) -> None:
    """nucleo_datalogger is not a third case here: its own content
    answers TWO boards (see
    test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards
    below), which a single-`expected_board` parametrization cannot
    express. grove (lotus_buttons) and mikrobus (quail_temp_farm) stay
    here because only one corpus board offers each of those connector
    types, so migrating their content to the conventional label does
    not, by itself, open a second answer."""
    result = _run("--boards-for", rig_target)
    assert result.returncode == 0, (
        f"--boards-for {rig_target}: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == expected_board


def test_boards_for_nucleo_datalogger_now_conforms_to_both_arduino_r3_boards() -> None:
    """At least one corpus rig's `--boards-for` answer must
    contain more than one board once content migrates off board-prefixed
    labels: nucleo_datalogger.yml names the conventional `arduino_r3`
    alias rather than `nucleo_ard` directly, so both nucleo_f401re and
    frdm_k64f's own arduino_r3 socket -- offering the identical i2c/spi
    subset, mating and stackability adafruit_data_logger needs -- answer
    it. No code in board/census.py or analyzer/sockets.py cares which
    label content references; this proves the content's own choice of
    label is what determines the answer."""
    result = _run("--boards-for", "nucleo_datalogger")
    assert result.returncode == 0, (
        f"--boards-for nucleo_datalogger: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.split() == sorted([
        "frdm_k64f/mk64f12/rig", "nucleo_f401re/stm32f401xe/rig"]), (
        "nucleo_datalogger must conform to BOTH arduino_r3 boards -- its "
        f"content names no board-specific label\n--- stdout ---\n{result.stdout}")


def test_boards_for_an_unresolved_rig_target_is_a_nonzero_exit_with_list_rigs_own_message() -> None:
    result = _run("--boards-for", "no_such_rig_at_all")
    assert result.returncode != 0
    assert "does not resolve to a rig" in result.stderr


def test_boards_for_a_promoted_shield_answers_the_same_boards_as_the_rig_it_stands_for() -> None:
    """--boards-for resolves BOTH namespaces (the same rule --explain
    already applies), and the expectation comes from OUTSIDE this query:
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


def test_boards_for_a_bare_plural_shield_answers_empty_the_per_slot_ambiguity() -> None:
    """`can_span_click` plugs two
    mikroBUS slots, and quail offers FOUR mikroBUS sockets -- per-slot
    inference refuses on EACH slot
    independently (several candidates, no tie-break), so a bare target
    answers no board at all. This is the ambiguity refusal working
    correctly, not a gap -- the explicit
    socket.<slot>= form below is the answer, not a smarter inference."""
    result = _run("--boards-for", "can_span_click")
    assert result.returncode == 0, (
        f"--boards-for can_span_click: exit {result.returncode}\n"
        f"{result.stderr}")
    assert result.stdout.strip() == ""


def test_boards_for_a_plural_shield_with_slot_options_answers_the_named_board() -> None:
    """The slot-optioned counterpart of the ambiguity test above -- the
    SAME shield answers nothing bare and mikroe_quail once the target
    names which two of quail's four mikroBUS sockets its slots mean,
    asserted as a pair for the same reason
    test_boards_for_a_promoted_shield_naming_its_socket_answers_that_board
    is: either half alone is satisfiable by a stub."""
    bare = _run("--boards-for", "can_span_click")
    optioned = _run(
        "--boards-for",
        "can_span_click:socket.left=quail_sock2:socket.right=quail_sock3")

    assert optioned.returncode == 0, (
        f"exit {optioned.returncode}\n{optioned.stderr}")
    assert bare.stdout.strip() == ""
    assert optioned.stdout.strip() == "mikroe_quail/stm32f427xx/rig"


def test_boards_for_a_bare_socket_on_a_plural_shield_is_refused() -> None:
    """The slot-form's own negative control at query level: a bare
    socket= (the single-plug spelling) is refused for a plural shield
    with parse_promotion_opts's own sentence, not silently ignored or
    misread as naming one of the two slots."""
    result = _run("--boards-for", "can_span_click:socket=quail_sock2")
    assert result.returncode != 0
    assert "plugs 2 sockets" in result.stderr
    assert "socket.<slot>=" in result.stderr


def test_boards_for_a_promoted_shield_with_a_required_param_answers_once_assigned() -> None:
    """The dotted `<device>.<prop>=<value>` promotion-option grammar's own
    falsifier, the same shape the socket= pair above
    uses: grove_btn declares zephyr,code required with no authored
    default (grove_btn.shield), so the bare shield fails the
    required-param check (check_param_invariant) exactly as an authored
    rig.yml omitting the
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
    """Promotion options are promotion-only. A persisted rig
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
    """The rig/shield name collision, now that --boards-for resolves both
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


def test_boards_for_a_list_target_answers_a_board_hosting_both() -> None:
    """The positive half of the list-target contract: a board
    answers iff the WHOLE desugared rig resolves clean -- mikroe_quail
    hosts eth_click and flash_click on two of its four distinct mikroBUS
    sockets simultaneously, so the list target answers it."""
    result = _run(
        "--boards-for",
        "eth_click:socket=quail_sock1;flash_click:socket=quail_sock2")
    assert result.returncode == 0, (
        f"--boards-for <list>: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == "mikroe_quail/stm32f427xx/rig"


def test_boards_for_a_list_target_answers_nothing_on_socket_exclusivity() -> None:
    """The negative half of the same contract, with the REASON asserted,
    not just the emptiness: two elements naming the SAME
    non-stackable mikroBUS socket refuse via the existing exclusivity
    census message -- mikroe_quail hosts EITHER shield alone (the
    positive test above, and test_boards_for_a_promoted_shield_naming_
    its_socket_answers_that_board), but not both pinned to the same
    physical socket at once."""
    result = _run(
        "--boards-for",
        "eth_click:socket=quail_sock1;flash_click:socket=quail_sock1")
    assert result.returncode == 0, (
        f"--boards-for <list>: exit {result.returncode}\n{result.stderr}")
    assert result.stdout.strip() == ""

    each_alone = _run("--boards-for", "eth_click:socket=quail_sock1")
    assert each_alone.stdout.strip() == "mikroe_quail/stm32f427xx/rig", (
        "mikroe_quail must be censused and answer for eth_click ALONE, or "
        "the empty list answer above proves nothing about exclusivity\n"
        f"--- stdout ---\n{each_alone.stdout}")


def test_boards_for_a_list_target_with_a_duplicate_element_is_refused() -> None:
    result = _run("--boards-for", "eth_click;eth_click")
    assert result.returncode != 0
    assert "eth_click" in result.stderr
    assert "more than once" in result.stderr


def test_boards_for_a_list_target_with_a_persisted_rig_element_is_refused() -> None:
    result = _run("--boards-for", "eth_click;nucleo_datalogger")
    assert result.returncode != 0
    assert "nucleo_datalogger" in result.stderr
    assert "names a persisted rig" in result.stderr


def test_west_rigs_with_no_flag_still_lists_every_rig_unchanged() -> None:
    """--boards-for absent behaves exactly as
    the plain `west rigs` listing -- the same rig NAMES, one per line.
    Asserting the count alone
    would hold just as well if the listing started printing board targets
    instead, so the expectation is the names themselves, taken from
    list_rigs (the module `west rigs` renders from) rather than from this
    command's own output.

    rglob, not a flat glob("*/rig.yml") -- five rigs live one level
    deeper, under boards/rigs/clash/; a flat
    scan here would silently under-count `expected` and let a `find_rigs_
    in` regression that drops those five pass unnoticed."""
    result = _run()
    assert result.returncode == 0
    expected = sorted(
        yaml.safe_load(p.read_text())["rig"]["name"]
        for p in (REPO_ROOT / "boards" / "rigs").rglob("rig.yml"))
    assert sorted(result.stdout.split()) == expected
