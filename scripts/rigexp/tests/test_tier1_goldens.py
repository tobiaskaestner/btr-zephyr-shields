"""Tier-1 goldens: freeze the CURRENT observed behavior of `python -m rigexp
expand` for every rig in the corpus (Bridge-A saferail 1, amended
2026-07-23 — see `claude/rigs/implementation-plan.md`).

For each rig this pins: the verdict (exit code), the full rendered
diagnostics (warnings on accepts too, not only reject errors), and whatever
of `overlay` / `context.cmake` / `config-sheet.md` / `conf` the emitter
produced. `expectations.yml` is deliberately excluded — parked to
`claude/hw-expectations/`, never gated (see `claude/rigs/parked.md`).

THE FLIP changed what "fast" means here: pass 1 now reads the REAL board
devicetree (boarddt/board_edt/edt_build), which needs a real recipe (cpp
include dirs + edtlib bindings dirs) — the cached-plain-build pattern
(`conftest.plain_build_for`) supplies it via one real `west build
--cmake-only` PER BOARD, memoized for the whole test session (4 boards, not
13 rigs) rather than 13 independent configures. `test_tier1_golden` is
therefore `@pytest.mark.build` now; `test_unknown_board_golden` stays
UNMARKED — an unknown board is rejected by name-discovery alone (list_boards.py),
before any recipe would even be needed, so it needs no build at all.

Refreeze: set RIGEXP_REFREEZE=1 in the environment to rewrite the fixtures
under tests/goldens/<rig-name>/ instead of asserting against them, e.g.:

    RIGEXP_REFREEZE=1 ZEPHYR_BASE=<zephyr-rigs tree> \\
        <venv>/bin/python3 -m pytest tests/test_tier1_goldens.py

Always inspect `git diff tests/goldens` before committing a refreeze — it
must reflect an INTENTIONAL, understood behavior change, never silent drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (
    ALL_CASES,
    BOARD_DTS,
    FIXTURES_DIR,
    GOLDENS_DIR,
    REPO_ROOT,
    RIGS_DIR,
    RigCase,
    assert_absent_or_refreeze,
    freeze_or_assert,
    normalize,
    plain_build_for,
    rig_board_name,
    rig_yml_name,
    run_expand,
    zephyr_base,
)

# The artifact filenames the emitter may produce, per saferail 1. Order is
# stable so a refreeze's `git diff` stays readable.
_EMITTED_FILES = ("rig-gen.overlay", "context.cmake", "config-sheet.md", "rig-gen.conf")


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_corpus_rig_identity(case: RigCase) -> None:
    """Guard the corpus table against drift: rig identity is rig.yml's
    `rig.name`, never the folder basename (task instructions, and Ground
    rule elsewhere in the front-end spec)."""
    assert rig_yml_name(case.folder) == case.name


def test_corpus_complete() -> None:
    """Every rig folder under boards/rigs/ must be in the corpus table — a
    newly added rig must be frozen into the goldens, never silently skipped."""
    live = {d.name for d in RIGS_DIR.iterdir() if (d / "rig.yml").is_file()}
    assert live == {c.folder for c in ALL_CASES}


@pytest.mark.build
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_tier1_golden(case: RigCase, tmp_path: Path,
                      tmp_path_factory: "pytest.TempPathFactory") -> None:
    board = rig_board_name(case.folder)
    plain_build = plain_build_for(board, tmp_path_factory)
    out_dir = tmp_path / "out"
    result = run_expand(
        RIGS_DIR / case.folder / "rig.yml", out_dir,
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

    for fname in _EMITTED_FILES:
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
    """Synthetic fixture (saferail 1): a rig naming a nonexistent board — a
    rewrite-touched path (pass 1 will read the real board DT/bindings, step 1
    of the rewrite) that the real corpus does not otherwise exercise, since
    every corpus rig names a real, existing board."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "unknown-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unknown board must be rejected"
    assert "[phys-board]" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "unknown-board"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_route_no_via_golden(tmp_path: Path) -> None:
    """Synthetic fixture (cmake-debug review finding): a wire `route:` that
    is a mapping without a `via:` key must be rejected by the LOADER with
    the lang-schema diagnostic that replaced Wire.route's None-leak. No
    corpus rig uses wires, so only this fixture locks that path. Fast: the
    loader rejects before any board recipe is needed."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "route-no-via" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "route:{} without via: must be rejected"
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "names no 'via' key" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "route-no-via"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_not_rig_enabled_golden(tmp_path: Path) -> None:
    """Synthetic fixture (flip review finding 3): a board whose devicetree
    EXISTS but declares no `socket,*` node must be rejected with the DISTINCT
    "exists, but is not rig-enabled" phys-board diagnostic — the other half
    of the pair test_unknown_board_golden covers. Fast (no build): the
    fixture .dts is include-free, so the recipe is just zephyr's bindings dir
    passed explicitly — no configured board context needed."""
    out_dir = tmp_path / "out"
    fixture = FIXTURES_DIR / "not-rig-enabled"
    zb = zephyr_base()
    result = run_expand(fixture / "rig.yml", out_dir,
                        board_dts=fixture / "socketless_board.dts",
                        bindings_dirs=[Path(zb) / "dts" / "bindings"])

    assert result.returncode != 0, "a socket-less board must be rejected"
    assert "[phys-board]" in result.stderr, result.stderr
    assert "not rig-enabled" in result.stderr, result.stderr

    golden_dir = GOLDENS_DIR / "not-rig-enabled"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))

    for fname in _EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)


@pytest.mark.build
def test_pwm_nonzero_flags_golden(tmp_path: Path,
                                  tmp_path_factory: "pytest.TempPathFactory") -> None:
    """Synthetic fixture (analyzer bundle, 2026-07-23): a servo shield
    authoring a nonzero PWM flags value (PWM_POLARITY_INVERTED) on a real
    PWM-capable Grove socket -- every corpus shield authors flags=0, so this
    is the only fixture locking the analyzer's `phys-function` rejection
    (analyzer.py:_collect_channel), moved from the emitter's former
    `ValueError` (which violated the emitter's "cannot fail" contract,
    cli.py). Needs a real board recipe (the seeeduino_lotus extension --
    repointed here in E4 off its now-deleted board clone), like the corpus
    cases -- hence @pytest.mark.build, unlike the loader-level fixtures
    above."""
    fixture = FIXTURES_DIR / "pwm-nonzero-flags"
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

    for fname in _EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)
