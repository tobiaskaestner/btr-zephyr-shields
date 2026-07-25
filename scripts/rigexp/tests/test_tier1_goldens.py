"""Tier-1 goldens: freeze the observed behavior of `python -m rigexp expand`
for every rig in `boards/rigs/`.

For each rig this pins: the verdict (exit code), the full rendered
diagnostics (warnings on accepts too, not only reject errors), and whatever
of `overlay` / `context.cmake` / `config-sheet.md` / `conf` the emitter
produced. `expectations.yml` is deliberately excluded — it is emitted but
never gated (see `claude/hw-expectations/`).

Pass 1 reads the REAL board devicetree (boarddt/board_edt/edt_build), which
needs a real recipe (cpp include dirs + edtlib bindings dirs) — the
cached-plain-build pattern (`conftest.plain_build_for`) supplies it via one
real `west build --cmake-only` PER BOARD, memoized for the whole test
session (4 boards, not 13 rigs) rather than 13 independent configures.
`test_tier1_golden` is therefore `@pytest.mark.build`; `test_unknown_board_golden`
stays UNMARKED — an unknown board is rejected by name-discovery alone
(list_boards.py), before any recipe would even be needed, so it needs no
build at all.

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
import yaml

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
    run_expand,
    zephyr_base,
)

# The artifact filenames the emitter may produce. Order is stable so a
# refreeze's `git diff` stays readable. `rig-gen-includes.dtsi` is emitted
# only when a rig declares `dt-includes:` (today, only lotus_buttons) —
# `assert_absent_or_refreeze` covers the "correctly absent" case for every
# other corpus rig, the same way it already does for `rig-gen.conf`.
_EMITTED_FILES = ("rig-gen.overlay", "rig-gen-includes.dtsi", "context.cmake",
                  "config-sheet.md", "rig-gen.conf")


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_corpus_rig_identity(case: RigCase) -> None:
    """Guard the corpus table against drift: a rig's folder under
    `boards/rigs/` and its rig.yml `rig.name` must be the identical string
    (Ground rule elsewhere in the front-end spec) — `RigCase.name` serves
    as both."""
    with open(RIGS_DIR / case.name / "rig.yml") as f:
        doc = yaml.safe_load(f)
    assert doc["rig"]["name"] == case.name


def test_corpus_complete() -> None:
    """Every rig folder under boards/rigs/ must be in the corpus table — a
    newly added rig must be frozen into the goldens, never silently skipped."""
    live = {d.name for d in RIGS_DIR.iterdir() if (d / "rig.yml").is_file()}
    assert live == {c.name for c in ALL_CASES}


@pytest.mark.build
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_tier1_golden(case: RigCase, tmp_path: Path,
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
    """Synthetic fixture: a rig naming a nonexistent board must be rejected
    with a `phys-board` diagnostic before pass 1 ever tries to read any
    devicetree. No corpus rig exercises this path (every corpus rig names a
    real, existing board)."""
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
    """Synthetic fixture: a wire `route:` that is a mapping without a `via:`
    key must be rejected by the LOADER with a `lang-schema` diagnostic --
    an ambiguous route is a loader-level authoring error, never a silently
    resolved default. No corpus rig uses wires, so only this fixture locks
    that path. Fast: the loader rejects before any board recipe is needed."""
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


def test_param_undeclared_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 1 — a `params:` entry
    naming a property the device did not declare via `shield,params` (typo
    protection) must be rejected. Fast: the loader rejects before any board
    recipe is needed."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-undeclared" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an undeclared params: property must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "declares no parameter" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-undeclared"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_required_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 2 — a declared,
    REQUIRED (no default authored) parameter an instance never assigns must
    be rejected, not left as a silently-inert missing property."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-required" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unassigned required parameter must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "required" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-required"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_unknown_device_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 3 — a `params:` entry
    naming a device label the shield has no device for must be rejected."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-unknown-device" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unknown params: device label must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "names no device" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-unknown-device"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_unresolvable_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 4 — an assigned token
    that does not resolve against the rig's own declared `dt-includes:`
    must be rejected, naming the fix."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-unresolvable" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unresolvable parameter token must be rejected"
    assert "[lang-dt-include]" in result.stderr, result.stderr
    assert "does not resolve" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-unresolvable"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_no_vocabulary_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 5 — a symbolic token
    assigned by a rig that declares no `dt-includes:` at all. Distinct from
    rule 4: there is no vocabulary to resolve against, so the diagnostic must
    say that rather than blame the token, or the author is sent looking for a
    typo that is not there."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-no-vocabulary" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a symbolic token with no declared vocabulary must be rejected")
    assert "[lang-dt-include]" in result.stderr, result.stderr
    assert "dt-includes" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-no-vocabulary"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_missing_header_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 6 — a `dt-includes:`
    entry naming a header that is not on the include path must be rejected at
    expand time, naming the searched dirs. Guards the vocabulary declaration
    itself: without this the failure would surface later as an unresolvable
    token (rule 4), blaming the assignment instead of the include."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "param-missing-header" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a dt-includes header that does not exist must be rejected")
    assert "[lang-dt-include]" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-missing-header"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_not_rig_enabled_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a board whose devicetree EXISTS but declares no
    `socket,*` node must be rejected with the DISTINCT "exists, but is not
    rig-enabled" phys-board diagnostic — the other half of the pair
    test_unknown_board_golden covers. Fast (no build): the fixture .dts is
    include-free, so the recipe is just zephyr's bindings dir passed
    explicitly — no configured board context needed."""
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
    """Synthetic fixture: a servo shield authoring a nonzero PWM flags value
    (PWM_POLARITY_INVERTED) on a real PWM-capable Grove socket -- every
    corpus shield authors flags=0, so this is the only fixture locking the
    analyzer's `phys-function` rejection (analyzer.py:_collect_channel): the
    expander's PWM emission carries only (position, period), so a nonzero
    flags value must be rejected before emission ever runs, preserving the
    emitter's "never fails on an analyzer-accepted rig" contract (cli.py).
    Needs a real board recipe (the seeeduino_lotus extension), like the
    corpus cases -- hence @pytest.mark.build, unlike the loader-level
    fixtures above."""
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
