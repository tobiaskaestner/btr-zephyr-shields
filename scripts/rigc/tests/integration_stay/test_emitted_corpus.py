# Copyright (c) 2026 TiaC Systems
# SPDX-License-Identifier: Apache-2.0
"""Emitted goldens: the corpus sweep, plus the synthetic fixtures whose
own behavior still depends on real repo content.

For each rig under boards/rigs/ (test_emitted_golden, @pytest.mark.build)
this pins: the verdict (exit code), the full rendered diagnostics
(warnings on accepts too, not only reject errors), and whatever of
overlay / context.cmake / config-sheet.md / conf the emitter
produced. expectations.yml is deliberately excluded — it is emitted but
never gated (see claude/hw-expectations/).

Pass 1 reads the REAL board devicetree (board/), which
needs a real recipe (cpp include dirs + edtlib bindings dirs) — the
cached-plain-build pattern (corpus.plain_build_for) supplies it via one
real west build --cmake-only PER BOARD, memoized for the whole test
session (4 boards, not 13 rigs) rather than 13 independent configures.

test_corpus_rig_identity / test_corpus_complete need no build at all (they
only read rig.yml / list boards/rigs/), but they exist to check the REAL
corpus's own shape, exactly the reason test_connector_bindings.py is
integration despite being fast: a test that exists to validate repo-
production content is integration by PURPOSE, not by speed.

test_unknown_board_golden and test_not_rig_enabled_golden are similarly
unmarked (no build) yet integration: the former's diagnostic is reached by
scanning the real board tree (board/resolve.py/list_boards.py, "no such board
directory under ./boards" -- a real dependency on production board-tree
content, unlike every fixture in test_emitted_rejects.py, none of which
ever reaches board resolution at all); the latter explicitly passes
--bindings-dir under $ZEPHYR_BASE, a real Zephyr bindings directory.

Refreeze: set RIGC_REFREEZE=1 in the environment to rewrite the fixtures
under tests/goldens/<rig-name>/ instead of asserting against them, e.g.:

    RIGC_REFREEZE=1 ZEPHYR_BASE=<zephyr-rigs tree> \\
        <venv>/bin/python3 -m pytest tests/test_emitted_corpus.py

Always inspect git diff tests/goldens before committing a refreeze — it
must reflect an INTENTIONAL, understood behavior change, never silent drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from corpus import (
    ALL_CASES,
    ARD_DATALOGGER_FRDM_BOARD,
    BOARD_DTS,
    RIG_BOARD,
    RIGS_DIR,
    RigCase,
    plain_build_for,
    rig_dir,
    run_expand,
)
from harness import (
    EMITTED_FILES,
    FIXTURES_DIR,
    GOLDENS_DIR,
    REPO_ROOT,
    assert_absent_or_refreeze,
    freeze_or_assert,
    normalize,
    overlay_is_byte_compared,
    zephyr_base,
)

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc import board  # noqa: E402


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_corpus_rig_identity(case: RigCase) -> None:
    """Guard the corpus table against drift: a rig's folder under
    boards/rigs/ and its rig.yml rig.name must be the identical
    string — RigCase.name serves as both."""
    with open(rig_dir(case.name) / "rig.yml") as f:
        doc = yaml.safe_load(f)
    assert doc["rig"]["name"] == case.name


def test_corpus_complete() -> None:
    """Every rig folder under boards/rigs/ must be in the corpus table — a
    newly added rig must be frozen into the goldens, never silently skipped.

    Recursive (rglob, not a flat iterdir): five rigs live one level deeper,
    under boards/rigs/clash/ -- a flat scan
    would silently drop them from `live`, and this test exists precisely
    to catch a rig going missing, so it must not itself be blind to one
    that moved."""
    live = {d.name for d in RIGS_DIR.rglob("*") if d.is_dir() and (d / "rig.yml").is_file()}
    assert live == {c.name for c in ALL_CASES}


def test_no_rig_declares_a_board() -> None:
    """board leaves rig.yml entirely -- a rig describes a topology; the
    invocation supplies the board. Scans every rig.yml under boards/
    rigs/ for a literal `board` key in EITHER legal declaration shape
    binding.resolve_board still accepts (a top-level rig.board:, or one
    beside each variants: list: entry) -- walked generically over the
    whole parsed document, not keyed to either shape specifically, so a
    THIRD shape (or a board: nested somewhere unexpected) would still be
    caught rather than silently missed.

    binding.resolve_board itself still ACCEPTS a declared board (a
    default, not a removed grammar) -- this test
    is a fact about what the CORPUS currently declares, not a schema-
    level prohibition the loader enforces.

    Census-style: falsified by mutating the WORLD it observes -- add a
    board: key back to any rig's rig.yml -- never by editing this
    assertion (test_no_rig_content_names_a_board_prefixed_socket,
    just below, is the shape this follows).

    rglob, not a flat glob("*/rig.yml") -- five rigs live one level
    deeper, under boards/rigs/clash/."""

    def _board_key_paths(node: object, path: str) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                sub_path = f"{path}.{key}" if path else str(key)
                if key == "board":
                    found.append(sub_path)
                found.extend(_board_key_paths(value, sub_path))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                found.extend(_board_key_paths(item, f"{path}[{i}]"))
        return found

    offenders = []
    for rig_yml in sorted(RIGS_DIR.rglob("rig.yml")):
        doc = yaml.safe_load(rig_yml.read_text()) or {}
        keys = _board_key_paths(doc, "")
        if keys:
            offenders.append(f"{rig_yml.relative_to(RIGS_DIR)}: {', '.join(keys)}")
    assert not offenders, (
        "board: is not part of rig.yml's grammar -- "
        f"the invocation supplies it, never the declaration: {offenders}"
    )


def test_no_rig_content_names_a_board_prefixed_socket() -> None:
    """Once
    a board's socket carries a CONVENTIONAL alias, a rig's own content
    naming the board-prefixed DEFINING label
    directly is a portability bug, not a style choice -- it can only ever
    build against that one board, exactly what board-as-coordinate exists
    to undo.

    "board-prefixed" is derived, not hardcoded: board.census_boards
    builds each real board's Board.aliases as {conventional_alias:
    defining_label}, so the set of defining labels that have at least one
    alias pointing to them is exactly what content must not name. A board
    whose socket carries only ONE label that is already conventional
    (seeeduino_lotus's grove_d2/d4/...) contributes nothing to this set --
    Board.aliases only ever holds a node's SECOND-and-later labels -- so
    lotus's own content is never flagged.

    ard_datalogger's content now names the conventional arduino_r3 alias
    directly (both its boards carry the SAME alias), so it is covered by
    the same census as every other rig's content, with no exclusion.

    Census-style: falsified by mutating the WORLD it observes -- add a
    board-prefixed socket: to any OTHER rig's content file -- never by
    editing this assertion.

    rglob("*.yml"), not a flat glob("*/*.yml") -- five rigs live one level
    deeper, under boards/rigs/clash/."""
    forbidden = {defining for cb in board.census_boards() for defining in cb.board.aliases.values()}

    offenders = []
    for content_path in sorted(RIGS_DIR.rglob("*.yml")):
        if content_path.name == "rig.yml":
            continue
        doc = yaml.safe_load(content_path.read_text()) or {}
        for inst in doc.get("instances") or []:
            if not isinstance(inst, dict):
                continue
            socket = inst.get("socket")
            if not isinstance(socket, str):
                continue
            base = socket.split(".", 1)[0]
            if base in forbidden:
                offenders.append(f"{content_path.relative_to(RIGS_DIR)}: socket: {socket}")
    assert not offenders, (
        "content names a board-prefixed socket label directly -- migrate "
        f"to the connector type's conventional alias instead: {offenders}"
    )


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
        d.name
        for d in sorted(GOLDENS_DIR.iterdir())
        if (d / "rig-gen.overlay").is_file()
        and not (d / "zephyr.dts").is_file()
        and not overlay_is_byte_compared(d.name)
    ]
    assert not unchecked, (
        f"rig-gen.overlay neither byte-compared nor backed by a zephyr.dts "
        f"golden, so its devicetree is unchecked: {unchecked}"
    )


@pytest.mark.build
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_emitted_golden(
    case: RigCase, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    board = case.board
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        rig_dir(case.name) / "rig.yml",
        out_dir,
        board=board,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
    )

    assert (result.returncode == 0) == case.accept, (
        f"{case.name}: expander exited {result.returncode}, expected "
        f"{'0 (accept)' if case.accept else 'nonzero (reject)'} per the "
        f"corpus's expected-verdict table — this is a real behavior "
        f"mismatch to STOP and report, never something to paper over by "
        f"adjusting the golden.\n--- stderr ---\n{result.stderr}"
    )

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
            f"in stderr\n{result.stderr}"
        )


def test_unknown_board_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a rig INJECTED with a nonexistent board must be
    rejected with a phys-board diagnostic before pass 1 ever tries to
    read any devicetree. No corpus rig exercises this path (every corpus
    rig names a real, existing board). An injected unknown board is
    still a real error -- the diagnostic is unchanged by where the name
    came from, load_board never learns the difference."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "unknown-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir, board="nonexistent_board_xyz")

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
    result = run_expand(
        fixture / "rig.yml",
        out_dir,
        board="socketless_board",
        board_dts=FIXTURES_DIR / "boards" / "mainboards" / "socketless_board.dts",
        bindings_dirs=[Path(zb) / "dts" / "bindings"],
    )

    assert result.returncode != 0, "a socket-less board must be rejected"
    assert "[phys-board]" in result.stderr, result.stderr
    assert "not rig-enabled" in result.stderr, result.stderr

    golden_dir = GOLDENS_DIR / "not-rig-enabled"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)


@pytest.mark.build
def test_pwm_nonzero_flags_golden(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
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
        fixture / "rig.yml",
        out_dir,
        board=board,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
    )

    assert result.returncode != 0, "nonzero PWM flags must be rejected"
    assert "[phys-function]" in result.stderr, result.stderr
    assert "PWM flags" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "pwm-nonzero-flags"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)


# ---------------------------------------------------------------- qualifier accepts


def _pilot_golden(tmp_path, tmp_path_factory, golden_name, revision, variant):
    """Shared body for the pilot rig family's three NON-default qualifier
    tuples (the bare/default tuple already rides the standard
    test_emitted_golden via ACCEPT_CASES's pilot_variants entry, above) --
    same board/build for every tuple, since variants/revisions carry no
    delta engine and never change the board."""
    board = RIG_BOARD["pilot_variants"]
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "pilot_variants" / "rig.yml",
        out_dir,
        board=board,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        revision=revision,
        variant=variant,
    )

    assert result.returncode == 0, (
        f"pilot_variants (revision={revision!r} variant={variant!r}): "
        f"expected accept\n--- stderr ---\n{result.stderr}"
    )

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
def test_pilot_variant_b_golden(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """variant_b @ revision 1 (the declared default revision, explicit
    variant): variant_b supplies BOTH a .overlay and a _defconfig, so this
    tuple exercises the DT collection chain the bare/default tuple
    (variant_a, no .overlay) does not."""
    _pilot_golden(
        tmp_path, tmp_path_factory, "pilot_variants_variant_b", revision=None, variant="variant_b"
    )


@pytest.mark.build
def test_pilot_revision_2_golden(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """variant_a (default) @ revision 2: exercises the revision Kconfig
    chain stacking onto the (still default) variant's own."""
    _pilot_golden(tmp_path, tmp_path_factory, "pilot_variants_2", revision="2", variant=None)


@pytest.mark.build
def test_shield_rev_family_revision_2_golden(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The two revision axes composing: rig revision 2's delta moves the
    sensor instance to the SHIELD's revision 2, so the emitted overlay must
    carry revision 2's own compatible where the bare (revision 1) tuple
    carries the base one. An
    instance patch's shield: resolves through the same resolver a base
    reference does -- so the point of the golden is to keep that true."""
    board = RIG_BOARD["shield_rev_family"]
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "shield_rev_family" / "rig.yml",
        out_dir,
        board=board,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
        revision="2",
    )

    assert result.returncode == 0, (
        f"shield_rev_family@2: expected accept\n--- stderr ---\n{result.stderr}"
    )
    overlay = (out_dir / "rig-gen.overlay").read_text()
    assert "vnd,temp0x48v2" in overlay, (
        "the shield's revision-2 compatible is missing from the overlay -- "
        f"the rig revision's delta did not select it\n{overlay}"
    )

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
def test_pilot_variant_b_revision_2_golden(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """variant_b @ revision 2 -- the fully qualified tuple, both chains and
    both axes stacking in the same build: variant_b's .overlay + _defconfig
    AND revision 2's _defconfig all collected together."""
    _pilot_golden(
        tmp_path, tmp_path_factory, "pilot_variants_variant_b_2", revision="2", variant="variant_b"
    )


@pytest.mark.build
def test_pilot_variant_c_golden(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """variant_c @ revision 1 -- the TOPOLOGY-differing tuple: its own
    delta (pilot_variants_variant_c.yml) substitutes the logger instance's
    shield entirely (Adafruit Data Logger -> pilot_alt_button), the case
    that forces wholesale params replace, since the base names no
    params: for 'logger' at all. rig-gen.overlay must show
    logger_pab_key/zephyr,code, never anything from the original shield."""
    _pilot_golden(
        tmp_path, tmp_path_factory, "pilot_variants_variant_c", revision=None, variant="variant_c"
    )


# ---------------------------------------------------------------- board-per-variant


@pytest.mark.build
def test_ard_datalogger_frdm_golden(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """ard_datalogger on its SECOND board: this is not a variant --
    ard_datalogger declares no variants: axis at all, just a
    DIFFERENT --board injected against the identical rig.yml/content
    pair ACCEPT_CASES's ard_datalogger entry already builds on its
    primary (nucleo) board. NO fragment of any kind on disk for frdm --
    the evidence that content is genuinely reused across hosts rather
    than merely declared reusable."""
    board = ARD_DATALOGGER_FRDM_BOARD
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / "ard_datalogger" / "rig.yml",
        out_dir,
        board=board,
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
    )

    assert result.returncode == 0, (
        f"ard_datalogger@frdm-board: expected accept\n--- stderr ---\n{result.stderr}"
    )

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
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A shield needing socket,uart, mated on the injected nucleo board:
    its Arduino socket deliberately exposes no socket,uart (subset
    exposure, declared by absence), so this must reject -- the same
    content that test_shield_uart_subset_accept_on_frdm below builds
    clean on the OTHER host, which is the property this fixture pair
    exists to freeze. One variant-less rig built twice, on two different
    injected boards -- not two variants of one rig."""
    board = "nucleo_f401re/stm32f401xe/rig"
    plain_build = plain_build_for(board, tmp_path_factory)
    fixture = FIXTURES_DIR / "boards" / "rigs" / "shield-uart-subset"
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml",
        out_dir,
        board=board,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
    )

    assert result.returncode != 0, (
        "a shield needing socket,uart on a socket that offers none must be rejected"
    )
    assert "[phys-subset]" in result.stderr, result.stderr
    assert "socket,uart" in result.stderr, result.stderr
    assert "nucleo_ard" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-uart-subset-nucleo"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


@pytest.mark.build
def test_shield_uart_subset_accept_on_frdm_golden(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The other half of the pair above: the IDENTICAL rig, injected
    against frdm instead -- its Arduino socket exposes socket,uart
    (uart3), so the same rig accepts here. Proves the subset-exposure
    check runs against the board's own typed socket, not only a single
    fixed board mapping. No variant selected: this rig declares none --
    a different --board is the only thing
    that changes between this test and the one above."""
    board = "frdm_k64f/mk64f12/rig"
    plain_build = plain_build_for(board, tmp_path_factory)
    fixture = FIXTURES_DIR / "boards" / "rigs" / "shield-uart-subset"
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml",
        out_dir,
        board=board,
        shield_dirs=[fixture / "shields"],
        board_dts=REPO_ROOT / BOARD_DTS[board],
        build_info=plain_build.build_info,
    )

    assert result.returncode == 0, (
        f"shield-uart-subset/frdm: expected accept\n--- stderr ---\n{result.stderr}"
    )

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
