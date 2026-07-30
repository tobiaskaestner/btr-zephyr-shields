"""Emitted goldens: the corpus sweep, plus the synthetic fixtures whose
own behavior still depends on real repo content.

For each rig under boards/rigs/ (test_emitted_golden, @pytest.mark.build)
this pins: the verdict (exit code), the full rendered diagnostics
(warnings on accepts too, not only reject errors), and whatever of
overlay / context.cmake / config-sheet.md / conf the emitter
produced. expectations.yml is deliberately excluded — it is emitted but
never gated (see claude/hw-expectations/).

Pass 1 reads the REAL board devicetree (boarddt/board_edt/edt_build), which
needs a real recipe (cpp include dirs + edtlib bindings dirs) — the
cached-plain-build pattern (conftest.plain_build_for) supplies it via one
real west build --cmake-only PER BOARD, memoized for the whole test
session (4 boards, not 13 rigs) rather than 13 independent configures.

test_corpus_rig_identity / test_corpus_complete need no build at all (they
only read rig.yml / list boards/rigs/), but they exist to check the REAL
corpus's own shape, exactly the reason test_connector_bindings.py is
integration despite being fast: a test that exists to validate repo-
production content is integration by PURPOSE, not by speed.

test_unknown_board_golden and test_not_rig_enabled_golden are similarly
unmarked (no build) yet integration: the former's diagnostic is reached by
scanning the real board tree (boarddt/list_boards.py, "no such board
directory under ./boards" -- a real dependency on production board-tree
content, unlike every fixture in test_emitted_rejects.py, none of which
ever reaches board resolution at all); the latter explicitly passes
--bindings-dir under $ZEPHYR_BASE, a real Zephyr bindings directory.

Refreeze: set RIGEXP_REFREEZE=1 in the environment to rewrite the fixtures
under tests/goldens/<rig-name>/ instead of asserting against them, e.g.:

    RIGEXP_REFREEZE=1 ZEPHYR_BASE=<zephyr-rigs tree> \\
        <venv>/bin/python3 -m pytest tests/test_emitted_corpus.py

Always inspect git diff tests/goldens before committing a refreeze — it
must reflect an INTENTIONAL, understood behavior change, never silent drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import (
    ALL_CASES,
    BOARD_DTS,
    EMITTED_FILES,
    FIXTURES_DIR,
    GOLDENS_DIR,
    REPO_ROOT,
    RIGS_DIR,
    RigCase,
    SHIELD_DIR,
    assert_absent_or_refreeze,
    freeze_or_assert,
    normalize,
    overlay_is_byte_compared,
    plain_build_for,
    rig_board_name,
    run_expand,
    zephyr_base,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_corpus_rig_identity(case: RigCase) -> None:
    """Guard the corpus table against drift: a rig's folder under
    boards/rigs/ and its rig.yml rig.name must be the identical string
    (Ground rule elsewhere in the front-end spec) — RigCase.name serves
    as both."""
    with open(RIGS_DIR / case.name / "rig.yml") as f:
        doc = yaml.safe_load(f)
    assert doc["rig"]["name"] == case.name


def test_corpus_complete() -> None:
    """Every rig folder under boards/rigs/ must be in the corpus table — a
    newly added rig must be frozen into the goldens, never silently skipped."""
    live = {d.name for d in RIGS_DIR.iterdir() if (d / "rig.yml").is_file()}
    assert live == {c.name for c in ALL_CASES}


def test_every_overlay_golden_has_semantic_coverage() -> None:
    """The split contract's own invariant, enforced instead of assumed.

    rig-gen.overlay is no longer byte-compared: the devicetree it denotes
    is asserted through that rig's resolved zephyr.dts instead, and only
    the handful of facts resolution destroys are checked on the overlay
    itself. That holds only while every overlay golden HAS a zephyr.dts
    golden — or is one of the deliberate byte-compared exceptions. A rig
    with neither would have its emitted devicetree checked by nothing at
    all, and the suite would stay green while saying nothing about it.

    True of today's corpus, but true by coincidence of its shape rather
    than by construction, so a future golden directory (a synthetic accept
    fixture with no tier-2 build is the obvious way in) needs this to fail
    rather than to pass quietly."""
    unchecked = [
        d.name for d in sorted(GOLDENS_DIR.iterdir())
        if (d / "rig-gen.overlay").is_file()
        and not (d / "zephyr.dts").is_file()
        and not overlay_is_byte_compared(d.name)]
    assert not unchecked, (
        f"rig-gen.overlay neither byte-compared nor backed by a zephyr.dts "
        f"golden, so its devicetree is unchecked: {unchecked}")


@pytest.mark.build
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_emitted_golden(case: RigCase, tmp_path: Path,
                      tmp_path_factory: "pytest.TempPathFactory") -> None:
    board = rig_board_name(case.name)
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / case.name / "rig.yml", out_dir,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info)

    assert (result.returncode == 0) == case.accept, (
        f"{case.name}: expander exited {result.returncode}, expected "
        f"{'0 (accept)' if case.accept else 'nonzero (reject)'} per the "
        f"corpus's expected-verdict table — this is a real behavior "
        f"mismatch to STOP and report, never something to paper over by "
        f"adjusting the golden.\n--- stderr ---\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / case.name

    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in EMITTED_FILES:
        produced = out_dir / fname
        golden_file = golden_dir / fname
        if produced.is_file():
            freeze_or_assert(golden_file, normalize(produced.read_text(), zb))
        else:
            assert_absent_or_refreeze(golden_file)

    if case.category is not None:
        assert f"[{case.category}]" in result.stderr, (
            f"{case.name}: expected diagnostic category [{case.category}] "
            f"in stderr\n{result.stderr}")


def test_unknown_board_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a rig naming a nonexistent board must be rejected
    with a phys-board diagnostic before pass 1 ever tries to read any
    devicetree. No corpus rig exercises this path (every corpus rig names a
    real, existing board)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "unknown-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unknown board must be rejected"
    assert "[phys-board]" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "unknown-board"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_not_rig_enabled_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a board whose devicetree EXISTS but declares no
    socket,* node must be rejected with the DISTINCT "exists, but is not
    rig-enabled" phys-board diagnostic — the other half of the pair
    test_unknown_board_golden covers. Its board .dts is fixture-local, but
    it needs a real edtlib bindings dir (zephyr/dts/bindings) to build an
    EDT at all -- no configured board context needed beyond that."""
    out_dir = tmp_path / "out"
    fixture = FIXTURES_DIR / "boards" / "rigs" / "not-rig-enabled"
    zb = zephyr_base()
    result = run_expand(fixture / "rig.yml", out_dir,
                        board_dts=FIXTURES_DIR / "boards" / "mainboards" / "socketless_board.dts",
                        bindings_dirs=[Path(zb) / "dts" / "bindings"])

    assert result.returncode != 0, "a socket-less board must be rejected"
    assert "[phys-board]" in result.stderr, result.stderr
    assert "not rig-enabled" in result.stderr, result.stderr

    golden_dir = GOLDENS_DIR / "not-rig-enabled"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)


@pytest.mark.build
def test_pwm_nonzero_flags_golden(tmp_path: Path,
                                  tmp_path_factory: "pytest.TempPathFactory") -> None:
    """Synthetic fixture: a servo shield authoring a nonzero PWM flags value
    (PWM_POLARITY_INVERTED) on a real PWM-capable Grove socket -- every
    corpus shield authors flags=0, so this is the only fixture locking the
    analyzer's phys-function rejection (analyzer.py:_collect_channel): the
    expander's PWM emission carries only (position, period), so a nonzero
    flags value must be rejected before emission ever runs, preserving the
    emitter's "never fails on an analyzer-accepted rig" contract (cli.py).
    Needs a real board recipe (the seeeduino_lotus extension), like the
    corpus cases -- hence @pytest.mark.build, unlike the loader-level
    fixtures in test_emitted_rejects.py."""
    fixture = FIXTURES_DIR / "boards" / "rigs" / "pwm-nonzero-flags"
    board = "seeeduino_lotus/samd21g18a/rig"
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml", out_dir,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info)

    assert result.returncode != 0, "nonzero PWM flags must be rejected"
    assert "[phys-function]" in result.stderr, result.stderr
    assert "PWM flags" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "pwm-nonzero-flags"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)


# ---------------------------------------------------------------- V1a: qualifier accepts

def _pilot_golden(tmp_path, tmp_path_factory, golden_name, revision, variant):
    """Shared body for the pilot rig family's three NON-default qualifier
    tuples (the bare/default tuple already rides the standard
    test_emitted_golden via ACCEPT_CASES's pilot_variants entry, above) --
    same board/build for every tuple, since variants/revisions carry no
    delta engine yet (V1a) and never change the board."""
    board = rig_board_name("pilot_variants")
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "pilot_variants" / "rig.yml", out_dir,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        revision=revision, variant=variant)

    assert result.returncode == 0, (
        f"pilot_variants (revision={revision!r} variant={variant!r}): "
        f"expected accept\n--- stderr ---\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / golden_name
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))
    for fname in EMITTED_FILES:
        produced = out_dir / fname
        golden_file = golden_dir / fname
        if produced.is_file():
            freeze_or_assert(golden_file, normalize(produced.read_text(), zb))
        else:
            assert_absent_or_refreeze(golden_file)


@pytest.mark.build
def test_pilot_variant_b_golden(tmp_path: Path,
                                tmp_path_factory: "pytest.TempPathFactory") -> None:
    """variant_b @ revision 1 (the declared default revision, explicit
    variant): variant_b supplies BOTH a .overlay and a _defconfig, so this
    tuple exercises the DT collection chain the bare/default tuple
    (variant_a, no .overlay) does not."""
    _pilot_golden(tmp_path, tmp_path_factory, "pilot_variants_variant_b",
                 revision=None, variant="variant_b")


@pytest.mark.build
def test_pilot_revision_2_golden(tmp_path: Path,
                                 tmp_path_factory: "pytest.TempPathFactory") -> None:
    """variant_a (default) @ revision 2: exercises the revision Kconfig
    chain stacking onto the (still default) variant's own."""
    _pilot_golden(tmp_path, tmp_path_factory, "pilot_variants_2",
                 revision="2", variant=None)


@pytest.mark.build
def test_shield_rev_family_revision_2_golden(
        tmp_path: Path,
        tmp_path_factory: "pytest.TempPathFactory") -> None:
    """The two revision axes composing: rig revision 2's delta moves the
    sensor instance to the SHIELD's revision 2, so the emitted overlay must
    carry revision 2's own compatible where the bare (revision 1) tuple
    carries the base one. Nothing in V1c was written for this -- an
    instance patch's shield: resolves through the same resolver a base
    reference does -- so the point of the golden is to keep that true."""
    board = rig_board_name("shield_rev_family")
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "shield_rev_family" / "rig.yml", out_dir,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        revision="2")

    assert result.returncode == 0, (
        f"shield_rev_family@2: expected accept\n"
        f"--- stderr ---\n{result.stderr}")
    overlay = (out_dir / "rig-gen.overlay").read_text()
    assert "vnd,temp0x48v2" in overlay, (
        "the shield's revision-2 compatible is missing from the overlay -- "
        f"the rig revision's delta did not select it\n{overlay}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield_rev_family_2"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))
    for fname in EMITTED_FILES:
        produced = out_dir / fname
        golden_file = golden_dir / fname
        if produced.is_file():
            freeze_or_assert(golden_file, normalize(produced.read_text(), zb))
        else:
            assert_absent_or_refreeze(golden_file)


@pytest.mark.build
def test_pilot_variant_b_revision_2_golden(tmp_path: Path,
                                           tmp_path_factory: "pytest.TempPathFactory") -> None:
    """variant_b @ revision 2 -- the fully qualified tuple, both chains and
    both axes stacking in the same build: variant_b's .overlay + _defconfig
    AND revision 2's _defconfig all collected together."""
    _pilot_golden(tmp_path, tmp_path_factory, "pilot_variants_variant_b_2",
                 revision="2", variant="variant_b")


@pytest.mark.build
def test_pilot_variant_c_golden(tmp_path: Path,
                                tmp_path_factory: "pytest.TempPathFactory") -> None:
    """variant_c @ revision 1 (V1b) -- the TOPOLOGY-differing tuple: its own
    delta (pilot_variants_variant_c.yml) substitutes the logger instance's
    shield entirely (Adafruit Data Logger -> pilot_alt_button), the case
    that forces wholesale params replace (Sec. 5), since the base names no
    params: for 'logger' at all. rig-gen.overlay must show
    logger_pab_key/zephyr,code, never anything from the original shield."""
    _pilot_golden(tmp_path, tmp_path_factory, "pilot_variants_variant_c",
                 revision=None, variant="variant_c")


# ---------------------------------------------------------------- board-per-variant

@pytest.mark.build
def test_ard_datalogger_frdm_golden(tmp_path: Path,
                                    tmp_path_factory: "pytest.TempPathFactory") -> None:
    """ard_datalogger's frdm variant: a DIFFERENT host board than the bare/
    default nucleo tuple (ACCEPT_CASES's ard_datalogger entry rides the
    standard machinery for that one), the SAME content file, and NO
    fragment of any kind on disk for frdm -- the evidence that content is
    genuinely reused across hosts rather than merely declared reusable."""
    board = rig_board_name("ard_datalogger", variant="frdm")
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "ard_datalogger" / "rig.yml", out_dir,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        variant="frdm")

    assert result.returncode == 0, (
        f"ard_datalogger/frdm: expected accept\n--- stderr ---\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "ard_datalogger_frdm"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))
    for fname in EMITTED_FILES:
        produced = out_dir / fname
        golden_file = golden_dir / fname
        if produced.is_file():
            freeze_or_assert(golden_file, normalize(produced.read_text(), zb))
        else:
            assert_absent_or_refreeze(golden_file)


@pytest.mark.build
def test_shield_uart_subset_reject_on_nucleo_golden(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """A shield needing socket,uart, mated through the DEFAULT (nucleo)
    variant's own socket map: nucleo_ard deliberately exposes no
    socket,uart (subset exposure, declared by absence), so this must
    reject -- the same content that test_shield_uart_subset_accept_on_frdm
    below builds clean on the OTHER host, which is the property this
    fixture pair exists to freeze."""
    board = "nucleo_f401re/stm32f401xe/rig"
    plain_build = plain_build_for(board, tmp_path_factory)
    fixture = FIXTURES_DIR / "boards" / "rigs" / "shield-uart-subset"
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml", out_dir,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info)

    assert result.returncode != 0, (
        "a shield needing socket,uart on a socket that offers none must "
        "be rejected")
    assert "[phys-subset]" in result.stderr, result.stderr
    assert "socket,uart" in result.stderr, result.stderr
    assert "nucleo_ard" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-uart-subset-nucleo"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


@pytest.mark.build
def test_shield_uart_subset_accept_on_frdm_golden(
        tmp_path: Path, tmp_path_factory: "pytest.TempPathFactory") -> None:
    """The other half of the pair above: the IDENTICAL content, mated
    through the frdm variant's socket map instead -- frdm_ard exposes
    socket,uart (uart3), so the same rig accepts here. Proves the subset-
    exposure check runs against metadata-sourced sockets, not only a
    single fixed board mapping."""
    board = "frdm_k64f/mk64f12/rig"
    plain_build = plain_build_for(board, tmp_path_factory)
    fixture = FIXTURES_DIR / "boards" / "rigs" / "shield-uart-subset"
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml", out_dir,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        variant="frdm")

    assert result.returncode == 0, (
        f"shield-uart-subset/frdm: expected accept\n--- stderr ---\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-uart-subset-frdm"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))
    for fname in EMITTED_FILES:
        produced = out_dir / fname
        golden_file = golden_dir / fname
        if produced.is_file():
            freeze_or_assert(golden_file, normalize(produced.read_text(), zb))
        else:
            assert_absent_or_refreeze(golden_file)
