"""Emitted goldens: the fixture-only rejects. HERMETIC, and INTEGRATION.

Every test here freezes python -m rigc expand's verdict + rendered
diagnostics against a SYNTHETIC fixture under tests/fixtures/, never a real
corpus rig, and none reaches analyzer.analyze (boarddt/board_edt/edt_build,
which needs a real board recipe) -- each one is rejected by loader_yml.load
alone, on YAML/schema shape, before any board devicetree would even be
read.

Both labels above are true at once, and the distinction is the point. These
are HERMETIC: no $ZEPHYR_BASE bindings/includes, no real board .dts, no
cmake/west build, nothing from REPO_ROOT/dts or REPO_ROOT/include
(conftest.assert_fixture_local is the structural proof for the handful of
tests that pass an explicit board/bindings/include recipe at all; most pass
none, since the rejection fires before board resolution is attempted). They
are nonetheless INTEGRATION, for two reasons that have nothing to do with
hermeticity:

  - they reach the code through the FRONT DOOR, as a subprocess running the
    real CLI, and a unit reached through the CLI is being integration-tested
    whatever the test is labelled;
  - what each one pins is a REJECT -- an outcome against a scenario. A
    scenario does not exist at unit level; it is consumed by the system
    (rigexp, later rigc). There is no unit whose specification says "this
    assembly is unrealizable".

So hermetic-and-fast is a property of the COST axis, not of the unit
boundary. These stay exactly as they are: what they uniquely protect is the
user-facing WORDING of a system verdict, which no unit test asserts.

Some of these fixtures name a real production shield (e.g.
adafruit_data_logger, i2c_sensor, flash_click) as ordinary instance
content, or a fixture shield that itself plugs one of the four real
connector types (arduino-r3, i2c-port) -- inherited from before the T0
hermetic vocabulary existed. That is a real, reported coupling risk (a
change to that shield's own declared shape could churn a golden here for
reasons unrelated to what the test names), but it does not move a test out
of this file: none of it is BOARD data, the loader never builds an EDT to
reach these diagnostics, and the shield-library scan itself is unconditional
plumbing every invocation performs regardless of override (see
test_no_board_declared_golden below, which touches no shield at all and
still incurs the same scan) -- not something a test's own recipe can
control, the same way $ZEPHYR_BASE may be set purely to locate the
devicetree package without that counting as a DATA dependency.

test_unknown_board_golden is the sibling case that reads the opposite way:
its own fixture rig.yml is just as synthetic, but its diagnostic is reached
by NAME DISCOVERY scanning the real board tree (boarddt/list_boards.py,
"no such board directory under ./boards") -- a genuine dependency on
production board-tree content, which is why it lives in
test_emitted_corpus.py instead, marked integration despite never running a
build.

Refreeze: set RIGC_REFREEZE=1 in the environment to rewrite the fixtures
under tests/goldens/<rig-name>/ instead of asserting against them. Always
inspect git diff tests/goldens before committing a refreeze -- it must
reflect an INTENTIONAL, understood behavior change, never silent drift.
"""
from __future__ import annotations

from pathlib import Path

from conftest import (
    FIXTURES_DIR,
    GOLDENS_DIR,
    SHIELD_DIR,
    assert_fixture_local,
    freeze_or_assert,
    normalize,
    run_expand,
    zephyr_base,
)


def test_route_no_via_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a wire route: that is a mapping without a via:
    key must be rejected by the LOADER with a lang-schema diagnostic --
    an ambiguous route is a loader-level authoring error, never a silently
    resolved default. No corpus rig uses wires, so only this fixture locks
    that path. Fast: the loader rejects before any board recipe is needed."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "route-no-via" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "route:{} without via: must be rejected"
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "names no 'via' key" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "route-no-via"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_undeclared_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 1 — a params: entry
    naming a property the device did not declare via shield,params (typo
    protection) must be rejected. Fast: the loader rejects before any board
    recipe is needed."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-undeclared" / "rig.yml"
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
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-required" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an unassigned required parameter must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "required" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-required"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_param_unknown_device_golden(tmp_path: Path) -> None:
    """Synthetic fixture: per-instance-parameters rule 3 — a params: entry
    naming a device label the shield has no device for must be rejected."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-unknown-device" / "rig.yml"
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
    that does not resolve against the rig's own declared dt-includes:
    must be rejected, naming the fix."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-unresolvable" / "rig.yml"
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
    assigned by a rig that declares no dt-includes: at all. Distinct from
    rule 4: there is no vocabulary to resolve against, so the diagnostic must
    say that rather than blame the token, or the author is sent looking for a
    typo that is not there."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-no-vocabulary" / "rig.yml"
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
    """Synthetic fixture: per-instance-parameters rule 6 — a dt-includes:
    entry naming a header that is not on the include path must be rejected at
    expand time, naming the searched dirs. Guards the vocabulary declaration
    itself: without this the failure would surface later as an unresolvable
    token (rule 4), blaming the assignment instead of the include."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "param-missing-header" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a dt-includes header that does not exist must be rejected")
    assert "[lang-dt-include]" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "param-missing-header"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


# ---------------------------------------------------------------- V1a: qualifier rejects

def test_unknown_revision_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 1 -- a --revision naming a value outside the
    declared revisions: list. Loader-level (fires before any board recipe
    is needed), like the other synthetic fixtures above."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "unknown-revision" / "rig.yml"
    result = run_expand(rig_yml, out_dir, revision="99")

    assert result.returncode != 0, "an undeclared revision must be rejected"
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "not declared" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "unknown-revision"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_unknown_variant_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 2 -- a --variant naming a value outside the
    declared variants: list."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "unknown-variant" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="nope")

    assert result.returncode != 0, "an undeclared variant must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "not declared" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "unknown-variant"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_no_default_variant_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 3 -- a bare target (no --variant) against a
    declared axis with values but no declared default, naming the axis and
    listing its values (Q5)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "no-default-variant" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "no selection + no default must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "no default variant" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "no-default-variant"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_variant_revision_collision_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 4 -- a declared variant name equal to a
    declared revision id, so the constructed fragment filenames
    (<rigname>_<id>...) would be ambiguous between the two axes (Q6).
    Checked unconditionally once both axes are declared, so a bare
    invocation already triggers it."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "variant-revision-collision" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "a variant/revision id collision must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "construct the same fragment stem" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "variant-revision-collision"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_variant_no_fragment_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 10 -- a selected NON-DEFAULT axis value none of
    whose constructed fragment files (.overlay/_defconfig/.yml, V1b's third
    kind) exist, naming the files that were looked for. A value that
    changes nothing is meaningless, so it is an authoring error. The value
    must be non-default to reach this check: the declared default is
    exempt, since the base rig file is that value's content (the pilot
    family covers the exempt half, where revision 1 carries no fragment
    and is accepted)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "variant-no-fragment" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="ghost")

    assert result.returncode != 0, "a variant contributing nothing must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "contributes nothing" in result.stderr, result.stderr
    assert "variant-no-fragment_ghost.overlay" in result.stderr, result.stderr
    assert "variant-no-fragment_ghost_defconfig" in result.stderr, result.stderr
    assert "variant-no-fragment_ghost.yml" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "variant-no-fragment"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_widened_variant_revision_collision_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 4 WIDENED (design-log 2026-07-26d) -- a
    variant literally named 'variant_a_2' constructs the SAME fragment
    stem as variant 'variant_a' + revision '2' combined, even though
    neither axis value equals the other outright (the original, narrower
    rule 4 would have missed this entirely)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "combined-fragment-collision" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "a combined-fragment stem collision must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "construct the same fragment stem" in result.stderr, result.stderr
    assert "combined-fragment-collision_variant_a_2" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "combined-fragment-collision"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_no_such_axis_golden(tmp_path: Path) -> None:
    """Synthetic fixture: the declares-no-such-axis wording (item 5, P's
    rule-5 precedent) -- a target naming an axis (--variant) this rig does
    not declare AT ALL gets a DISTINCT message from rule 2's "not a
    declared member", pointing the author at the missing declaration
    itself rather than implying a typo in an existing one."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "no-such-axis" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="anything")

    assert result.returncode != 0, "a qualifier against an undeclared axis must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "declares no variants:" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "no-such-axis"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


# ---------------------------------------------------------------- V1b: delta engine rejects

def test_revision_carries_board_golden(tmp_path: Path) -> None:
    """Synthetic fixture: board: moved into rig.yml's own axis declaration
    (the metadata/content split's per-variant board), so a revision
    fragment still carrying it is now rejected as a CONTENT file carrying
    a METADATA key -- a real authoring error, just a differently-
    explained one than the old variant-only-key wording."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "revision-carries-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir, revision="2")

    assert result.returncode != 0, "a revision fragment carrying board: must be rejected"
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "'board:' is rig.yml metadata" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "revision-carries-board"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_instances_delta_unknown_instance_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 6 -- an instances: delta naming an instance
    the effective topology does not have (additions are never implicit)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "instances-delta-unknown-instance" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="b")

    assert result.returncode != 0, "instances: naming an unknown instance must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "does not have" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "instances-delta-unknown-instance"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_add_instances_already_exists_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 7 -- add-instances: naming an instance that
    already exists."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "add-instances-already-exists" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="b")

    assert result.returncode != 0, "add-instances: naming an existing instance must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "already exists" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "add-instances-already-exists"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_remove_instance_drift_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 8 -- remove-instances: naming an absent
    instance. variant 'b' removes 'logger' first; the family-wide revision
    '2' delta then tries removing it again -- the message must NAME the
    variant that already removed it, so drift cannot hide."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "remove-instance-drift" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="b", revision="2")

    assert result.returncode != 0, "remove-instances: naming an absent instance must be rejected"
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "does not exist" in result.stderr, result.stderr
    assert "variant 'b' already removed it" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "remove-instance-drift"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_remove_wire_missing_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 9 -- remove-wires: naming an endpoint pair
    that does not exist (the real wire is x.sq -> y.led-1; the delta tries
    x.sq -> y.led-2)."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "remove-wire-missing" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="b")

    assert result.returncode != 0, "remove-wires: naming a nonexistent pair must be rejected"
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "remove-wires:" in result.stderr, result.stderr
    assert "does not exist" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "remove-wire-missing"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_restate_check_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 11 -- the params restate-check. variant b
    does not change sensor_1's shield but supplies params: for it,
    forgetting to restate vnd,threshold -- which wholesale replace would
    otherwise silently revert to the shield's authored default."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "restate-check" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="b",
                        shield_dirs=[FIXTURES_DIR / "boards" / "shields"])

    assert result.returncode != 0, "an un-restated optional parameter must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "without restating" in result.stderr, result.stderr
    assert "vnd,threshold" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "restate-check"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_revision_crosses_variant_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 12 -- a family-wide revision whose params
    names a device the POST-VARIANT topology does not have (variant hpm
    substituted sensor_1's shield, so 'rf_sensor' no longer exists) --
    unavoidable by construction, so the error must name the variant."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "revision-crosses-variant" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="hpm", revision="2",
                        shield_dirs=[FIXTURES_DIR / "boards" / "shields", SHIELD_DIR])

    assert result.returncode != 0, "a revision crossing a variant's shield swap must be rejected"
    assert "[lang-param]" in result.stderr, result.stderr
    assert "names no device 'rf_sensor'" in result.stderr, result.stderr
    assert "because of variant 'hpm'" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "revision-crosses-variant"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_dotted_revision_no_fragment_golden(tmp_path: Path) -> None:
    """Synthetic fixture: hwmv2's revision dot-normalization
    (design-log 2026-07-26d) -- a dotted revision id ('1.5') constructs a
    fragment filename with the dot replaced by an underscore
    (..._1_5_defconfig), never the literal dot. Rule 10 fires since no
    such fragment exists, naming the NORMALIZED filename -- proof the
    normalization happened, not just that rule 10 still works."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "dotted-revision-no-fragment" / "rig.yml"
    result = run_expand(rig_yml, out_dir, revision="1.5")

    assert result.returncode != 0, "a dotted revision contributing nothing must be rejected"
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "dotted-revision-no-fragment_1_5_defconfig" in result.stderr, result.stderr
    assert "dotted-revision-no-fragment_1.5_defconfig" not in result.stderr, (
        "the dot must be NORMALIZED to an underscore, per hwmv2's own "
        f"convention, not left literal\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "dotted-revision-no-fragment"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


# ---------------------------------------------------------------- V1c: shield revisions

def test_shield_undeclared_revision_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 13 -- shield: <name>@<rev> naming a revision
    shield.yml does not declare. i2c_sensor (a production shield,
    rig-variants-revisions.md V1c pilot) declares "1"/"2" only. Loader-level
    (shield resolution fires before any board recipe is needed), like the
    other synthetic fixtures above."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-undeclared-revision" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "an undeclared shield revision must be rejected"
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "is not declared" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-undeclared-revision"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_no_revisions_declared_golden(tmp_path: Path) -> None:
    """Synthetic fixture: @rev against a shield declaring no revisions: at
    all -- the shield-side analogue of the rig axis "declares no such
    axis" wording (P's rule-5 precedent, mirrored via _resolve_axis's own
    three failure shapes). flash_click is a production shield with no
    revisions: block."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-no-revisions-declared" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "an @rev against a shield declaring no revisions: must be rejected")
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "declares no revisions: at all" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-no-revisions-declared"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_missing_fragment_golden(tmp_path: Path) -> None:
    """Synthetic fixture: the missing non-default shield-revision fragment
    check -- the shield-side analogue of rule 10, same default exemption
    (the default MAY carry a fragment, it just must not be REQUIRED to).
    rev_fixture (fixture-only shield) declares revision "2" but ships
    neither rev_fixture_2.shield nor rev_fixture_2.conf."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-missing-fragment" / "rig.yml"
    result = run_expand(rig_yml, out_dir,
                        shield_dirs=[FIXTURES_DIR / "boards" / "rigs" /
                                     "shield-missing-fragment" / "shields"])

    assert result.returncode != 0, (
        "a shield revision contributing nothing must be rejected")
    assert "[lang-rev]" in result.stderr, result.stderr
    assert "contributes nothing" in result.stderr, result.stderr
    assert "rev_fixture_2.shield" in result.stderr, result.stderr
    assert "rev_fixture_2.conf" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-missing-fragment"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_revision_param_invariant_golden(tmp_path: Path) -> None:
    """Proves the per-stage parameter invariant claim (rig-variants-
    revisions.md V1c step 4) BY TEST rather than by inspection: a shield
    REVISION (not a rig delta) introduces a new required parameter
    (paramrev_2.shield adds shield,params with no default to pr_dev), and
    _check_param_invariant -- already re-checked fresh after resolving
    each instance's shield, with no special case for a shield-revision-
    introduced requirement -- must still reject an instance that never
    assigns it."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-revision-param-invariant" / "rig.yml"
    result = run_expand(rig_yml, out_dir,
                        shield_dirs=[FIXTURES_DIR / "boards" / "rigs" /
                                     "shield-revision-param-invariant" / "shields"])

    assert result.returncode != 0, (
        "a shield-revision-introduced required parameter must be rejected "
        "when unassigned")
    assert "[lang-param]" in result.stderr, result.stderr
    assert "declares 'vnd,threshold' as" in result.stderr, result.stderr
    assert "required" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-revision-param-invariant"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_missing_content_file_golden(tmp_path: Path) -> None:
    """Synthetic fixture: metadata that resolves with NO content file beside
    it. The content file is REQUIRED, and the distinction the diagnostic has
    to keep is between a rig whose instances: list is EMPTY (legal, and how
    the axis-rule fixtures are written) and a rig whose content file is
    absent (an authoring mistake). The message names the path that was
    constructed from the rig's own identity, since that name is never
    parsed from the folder and is therefore not obvious from the layout."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "missing-content-file" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "a missing content file must be rejected"
    assert "[lang-content]" in result.stderr, result.stderr
    assert "missing-content-file.yml" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "missing-content-file"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_bad_revisions_block_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a malformed revisions: block in a SHIELD's own
    shield.yml is blamed on that shield, BY NAME. One parser serves both
    rig.yml and shield.yml (the same {default:, list: []} shape, learned
    once), so it has to be told which file it is reading -- otherwise every
    shield.yml shape defect reports "rig revisions: ...", blaming the rig for
    a declaration it has no part in and naming no shield at all.

    Its own exclusive shield-library scan root, because a shape defect is
    reported at library-scan time for every folder scanned: sharing a root
    with any other shield would add this diagnostic to every other
    fixture's output too."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-bad-revisions-block" / "rig.yml"
    result = run_expand(rig_yml, out_dir,
                        shield_dirs=[FIXTURES_DIR / "boards" / "rigs" / "shield-bad-revisions-block" / "shields"])

    assert result.returncode != 0, (
        "a malformed shield.yml revisions: block must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "shield 'badyml_fixture' revisions:" in result.stderr, result.stderr
    assert "rig revisions:" not in result.stderr, (
        f"a shield.yml defect must not be blamed on the rig\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-bad-revisions-block"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_node_name_mismatch_golden(tmp_path: Path) -> None:
    """Synthetic fixture: a .shield template whose node name disagrees with
    the folder it lives in. Shield.name remains the DT node name, but the
    RESOLUTION key is the folder basename -- it is what <name>.shield
    discovery constructs, what shield.yml is read beside, and what an
    instance's shield: reference carries into RIG_SHIELDS. The two must
    agree, nothing else in the tree enforces it, and resolving to whichever
    single shield the file happened to define would leave the folder name
    and the node name disagreeing about what was built."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-node-name-mismatch" / "rig.yml"
    result = run_expand(rig_yml, out_dir,
                        shield_dirs=[FIXTURES_DIR / "boards" / "rigs" / "shield-node-name-mismatch" / "shields"])

    assert result.returncode != 0, (
        "a .shield node name not matching its folder must be rejected")
    assert "[lang-shield-name]" in result.stderr, result.stderr
    assert "misnamed_fixture" in result.stderr, result.stderr
    assert "other_name" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-node-name-mismatch"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


# ---------------------------------------------------------------- board-per-variant

def test_variant_board_restated_golden(tmp_path: Path) -> None:
    """Synthetic fixture: rule 10 widened -- a non-default variant
    declaring its OWN board and socket map, but restating the default's
    verbatim, with no fragment file either. Presence of a board: key is
    not itself contribution; this is the case the weaker (presence-only)
    reading of the widened rule would have missed. Purely loader-level
    (no board recipe needed): board/socket resolution here never touches
    a real board.yml, only rig.yml's own declared strings."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "variant-board-restated" / "rig.yml"
    result = run_expand(rig_yml, out_dir, variant="nucleo_again")

    assert result.returncode != 0, (
        "a variant restating the default's board/sockets with no fragment "
        "must be rejected")
    assert "[lang-variant]" in result.stderr, result.stderr
    assert "contributes nothing" in result.stderr, result.stderr
    assert "does not differ from the default variant's" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "variant-board-restated"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_unmapped_socket_golden(tmp_path: Path) -> None:
    """Synthetic fixture: the DEGENERATE shape's own top-level sockets:
    map (rig-metadata-content-split-brief.md), with an instance naming a
    socket the map does not cover -- it passes through unresolved, and the
    board simply has no socket by that literal name (the pre-existing
    phys-socket diagnostic, exercised here through the metadata-sourced
    resolution path rather than a raw board-socket label).

    The board is incidental to this: any board with any socket set
    demonstrates the same "unresolved name falls through to a real-socket
    lookup" property. So this uses a mainboards/ fixture board (built
    against the fixture connector type under fixtures/dts/connectors/,
    never a real one) instead of a real corpus board -- no plain build,
    hence unmarked like fixtures/boards/rigs/not-rig-enabled's sibling
    test."""
    fixture = FIXTURES_DIR / "boards" / "rigs" / "unmapped-socket"
    board_dts = FIXTURES_DIR / "boards" / "mainboards" / "unmapped_socket_board.dts"
    bindings_dirs = [FIXTURES_DIR / "dts" / "connectors"]
    include_dirs = [FIXTURES_DIR / "include"]
    assert_fixture_local([board_dts, *bindings_dirs, *include_dirs])
    out_dir = tmp_path / "out"
    result = run_expand(
        fixture / "rig.yml", out_dir,
        board_dts=board_dts,
        bindings_dirs=bindings_dirs, include_dirs=include_dirs)

    assert result.returncode != 0, (
        "an instance socket name absent from the declared map must be "
        "rejected against the board's own socket set")
    assert "[phys-socket]" in result.stderr, result.stderr
    assert "no socket 'other'" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "unmapped-socket"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


# ---------------------------------------------------------------- _resolve_board shape rules
#
# Every lang-schema rejection _resolve_board (loader_yml.py) and its
# _parse_axis_decl/_reject_metadata_keys neighbours can raise, pinned one
# case at a time. All are pure loader-level shape defects -- none reaches
# the analyzer, so none needs a real board recipe (no @pytest.mark.build).


def test_revision_mapping_entry_golden(tmp_path: Path) -> None:
    """A mapping entry ({name:, board:}) in a NON-variant axis's list: is
    rejected -- only a rig's variants: axis may take that shape; a
    revision is a change within one physical family, never a move to a
    different host board, so revisions: (and every shield.yml revisions:)
    takes bare names only."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "revision-mapping-entry" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a mapping entry in a non-variant axis list must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "legal only in a rig's variants: list" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "revision-mapping-entry"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_board_declared_twice_golden(tmp_path: Path) -> None:
    """A top-level board: alongside a variants: axis that ALSO declares
    its own boards is rejected: two legal shapes exist (one board once at
    the top level, or one per variant), and a rig taking both would make
    "which board won" unanswerable from the file alone."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "board-declared-twice" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a top-level board: alongside per-variant boards must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "never both" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "board-declared-twice"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_variant_board_partial_golden(tmp_path: Path) -> None:
    """Only SOME declared variants carrying a board: is rejected: a
    partial declaration would leave the other variant resolving to no
    board at all, which is not a silent fallback this split permits --
    every variant must declare a board, or none should."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "variant-board-partial" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "only some variants declaring board: must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "every variant must declare a board, or none should" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "variant-board-partial"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_sockets_with_variant_board_golden(tmp_path: Path) -> None:
    """A top-level sockets: map is rejected once every variant declares
    its own board: a top-level map only makes sense paired with a
    top-level board in the degenerate single-board shape; once boards are
    per-variant, a top-level map has no single board to be a map for."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "sockets-with-variant-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a top-level sockets: map alongside per-variant boards must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "declares a top-level sockets: map" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "sockets-with-variant-board"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_no_board_declared_golden(tmp_path: Path) -> None:
    """A rig declaring no board at all -- neither a top-level board: nor
    one per variant -- is rejected: every rig must name at least one host
    board, in one of the two legal shapes."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "no-board-declared" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, "a rig with no board declared at all must be rejected"
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "declares no board:" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "no-board-declared"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_content_file_carries_board_golden(tmp_path: Path) -> None:
    """The BASE content file (<rigname>.yml), not a delta fragment,
    carrying board: is rejected -- the hole the metadata/content split
    left in its first slice: a content file is topology only, so board:
    surviving there is a defect regardless of whether it arrives via a
    fragment or the base file itself."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "content-file-carries-board" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a base content file carrying board: must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "'board:' is rig.yml metadata" in result.stderr, result.stderr
    assert "content-file-carries-board.yml" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "content-file-carries-board"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_content_file_carries_sockets_golden(tmp_path: Path) -> None:
    """The other half of the same rejection: the base content file
    carrying sockets: instead of board:. Both keys are rig.yml metadata;
    neither is legal in a content file of any kind."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "content-file-carries-sockets" / "rig.yml"
    result = run_expand(rig_yml, out_dir)

    assert result.returncode != 0, (
        "a base content file carrying sockets: must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "'sockets:' is rig.yml metadata" in result.stderr, result.stderr
    assert "content-file-carries-sockets.yml" in result.stderr, result.stderr

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "content-file-carries-sockets"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))


def test_shield_revisions_mapping_entry_golden(tmp_path: Path) -> None:
    """The identical mapping-entry rejection, raised from a SHIELD's own
    shield.yml revisions: list rather than a rig's: blamed on the shield,
    BY NAME, since the axis parser is shared with rig.yml and would
    otherwise report "rig revisions: ...", naming no shield at all. Its
    own fixture shields root, because the defect is reported at
    library-scan time for every folder scanned."""
    out_dir = tmp_path / "out"
    rig_yml = FIXTURES_DIR / "boards" / "rigs" / "shield-revisions-mapping-entry" / "rig.yml"
    result = run_expand(rig_yml, out_dir,
                        shield_dirs=[FIXTURES_DIR / "boards" / "rigs" / "shield-revisions-mapping-entry" / "shields"])

    assert result.returncode != 0, (
        "a mapping entry in a shield's own revisions: list must be rejected")
    assert "[lang-schema]" in result.stderr, result.stderr
    assert "shield 'mapentry_fixture' revisions:" in result.stderr, result.stderr
    assert "legal only in a rig's variants: list" in result.stderr, result.stderr
    assert "rig revisions:" not in result.stderr, (
        f"a shield.yml defect must not be blamed on the rig\n{result.stderr}")

    zb = zephyr_base()
    golden_dir = GOLDENS_DIR / "shield-revisions-mapping-entry"
    freeze_or_assert(golden_dir / "exit_code", f"{result.returncode}\n")
    freeze_or_assert(golden_dir / "stderr.txt", normalize(result.stderr, zb))
