"""Tier-1 goldens: freeze the CURRENT observed behavior of `python -m rigexp
expand` for every rig in the corpus (Bridge-A saferail 1, amended
2026-07-23 — see `claude/rigs/implementation-plan.md`).

For each rig this pins: the verdict (exit code), the full rendered
diagnostics (warnings on accepts too, not only reject errors), and whatever
of `overlay` / `context.cmake` / `config-sheet.md` / `conf` the emitter
produced. `expectations.yml` is deliberately excluded — parked to
`claude/hw-expectations/`, never gated (see `claude/rigs/parked.md`).

This is the FAST tier: no `west`/CMake, just the expander subprocess, safe to
run on every commit.

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
    FIXTURES_DIR,
    GOLDENS_DIR,
    RIGS_DIR,
    RigCase,
    assert_absent_or_refreeze,
    freeze_or_assert,
    normalize,
    rig_yml_name,
    run_expand,
    zephyr_base,
)

# The artifact filenames the emitter may produce, per saferail 1. Order is
# stable so a refreeze's `git diff` stays readable.
_EMITTED_FILES = ("overlay", "context.cmake", "config-sheet.md", "conf")


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


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_tier1_golden(case: RigCase, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    result = run_expand(RIGS_DIR / case.folder / "rig.yml", out_dir)

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

    for fname in _EMITTED_FILES:
        assert_absent_or_refreeze(golden_dir / fname)
