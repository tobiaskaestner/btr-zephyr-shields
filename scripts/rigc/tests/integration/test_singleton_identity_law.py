"""The singleton identity law (board-coordinate-s4-brief.md, S4):

    --board b --rig <shield-name>
      ≡
    --board b --rig <checked-in rig with one socket-less instance of that
                     shield>

checked at EXPAND level -- `rigc expand` run twice (once given a fixture
rig.yml by PATH, once via `--promote <shield>`) and every emitted
artifact compared, so the desugaring (promote.promote_shield, fixed by
S3a) can never silently drift from the persisted form it claims to stand
for. NOT build-marked: no configure, no toolchain -- the one build-marked
cross-check (Sec 2.5, whether cmake/dts.cmake's own promoted branch feeds
the analyzer the same thing) lives in test_cmake_alone_entry.py, which
already owns configure-level rig comparisons.

Sec 2.1's RULING is why this module never touches list_rigs.py's
namespace resolver at all: the fixture side is given by PATH straight to
`rigc expand` (which performs no namespace resolution), so the fixture
rig may legally be named after a real shield with no both-paths
collision -- there is nothing here for that rule to ever see.

Sec 2.3's RULING is why the domain below is DERIVED, never hand-listed:
every `template: true` shield discover_shields() finds is resolved
through the real shield library and tested against promote.
shield_declares_required_params (the exact rule params.
check_param_invariant applies per instance, factored so this census and
that invariant can never drift apart) -- never a literal name list.

Sec 2.2's RULING is why RIG_DEPENDS compares as a set with exactly one
exemption: each side's own two rig documents (a real path on one side, a
synthesized path inside rigc's own workdir on the other) are genuinely
different files, dropped by basename ("rig.yml" / "<shield>.yml" is not a
name any OTHER dependency in this corpus ever carries) before the
remaining sets are compared -- everything else in RIG_DEPENDS, the
shield's own `.shield` template, its shield.yml, connector-type YAML,
index headers, must be identical.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pytest

from conftest import REPO_ROOT, RIG_EXPAND_COMPILE, zephyr_base

# This module carries no __init__.py (see conftest.py's own docstring on
# the frozen suite's import idiom) -- an in-process rigc import needs
# scripts/ on sys.path explicitly, exactly like test_reference_shields.py
# and test_board_read.py already do.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.diag import SourceRef  # noqa: E402
from rigc.loader.library import SHIELDS_DIR, load_shield_library  # noqa: E402
from rigc.promote import (discover_shields,  # noqa: E402
                          shield_declares_required_params)
from rigc.registry import load_types  # noqa: E402
from rigc.tests.compare import (compare_context_cmake,  # noqa: E402
                                parse_context_cmake, split_dependency_set)

_FIXTURES_DIR = REPO_ROOT / "scripts" / "rigc" / "tests" / "fixtures"
_TEMPLATE_DIR = _FIXTURES_DIR / "boards" / "rigs" / "singleton-law-template"
_BOARD_DTS = _FIXTURES_DIR / "boards" / "mainboards" / "singleton_law_board.dts"
# edtlib's own board-side schema for the fixture board's socket nodes.
# NOT the production dts/bindings/ tree -- a fixture copy of all four real
# connector types, arduino-r3/mikrobus/grove byte-identical, i2c-port
# patched with the one property (socket,i2c) its own production docstring
# already implies every i2c-port socket needs but that binding has never
# had to declare (no real board node ever carried this compatible before
# this test -- see singleton-law-connectors/i2c-port.yaml's own comment).
_CONNECTOR_BINDINGS = _FIXTURES_DIR / "dts" / "singleton-law-connectors"
_MODULE_INCLUDE = REPO_ROOT / "include"
_BOARD_LABEL = "singleton_law_board"

# The law's domain is THIS module's own vendored shield library, passed
# EXPLICITLY rather than left to discover_shields()'s default. Ruling 4
# claims `a -> [a]` for "OUR .shield template shields", which is exactly
# this root -- but S3a shipped a defect from relying on that same default
# implicitly (a cross-module shield was invisible to the namespace rule,
# which then failed OPEN), so the narrowness here is a deliberate,
# stated scope rather than an inherited accident. A shield under some
# OTHER module's board root is out of the law's claimed domain, not
# silently forgotten by it -- and `load_shield_library` is given the same
# list, so the census and the resolver can never disagree about what the
# domain contains.
_SHIELD_DIRS = [SHIELDS_DIR]

# Which eligible shields are expected to REJECT on both sides rather than
# emit comparable artifacts. Today exactly one: adafruit_winc1500 needs a
# routing-jumper selection (`pin:`) that neither side supplies, so both
# reject identically -- a real instance of the law (a promoted rig fails
# exactly the way the checked-in rig it stands for would), but one that
# compares STDERR and no artifact at all. Pinned because the reject
# branch is the law's weak path: if it ever silently widened, the suite
# would stay green while comparing nothing. See
# test_singleton_law_holds's own verdict assertion.
EXPECTED_REJECTING = {"adafruit_winc1500"}

# `--promote`'s materialized pair lives inside rigc's OWN ephemeral
# workdir (cli.py's `tempfile.mkdtemp(prefix="rigc-")`, kept on a reject --
# D10), a DIFFERENT absolute path every run and on every side; the
# fixture rig's own materialized pair (_materialize_fixture, below) is
# equally ephemeral (pytest's tmp_path). A rejected rig's diagnostic may
# quote either one verbatim (a "lang-*" finding anchored to the rig's own
# source), so a REJECT comparison needs both stripped before stderr
# compares meaningfully -- an ACCEPT never has this problem (Sec 2.1: the
# emitted artifacts' own RIG_NAME/instance name are the same STRING on
# both sides, never a path).
_RIGC_WORKDIR_RE = re.compile(r"/tmp/rigc-[^/\s]+")


def _normalize_reject_paths(text: str, fixture_rig_dir: Path) -> str:
    text = _RIGC_WORKDIR_RE.sub("<RIGC_WORKDIR>", text)
    return text.replace(str(fixture_rig_dir), "<FIXTURE_RIG_DIR>")


EMITTED_FILES = ("rig-gen.overlay", "config-sheet.md", "expectations.yml",
                 "rig-gen-includes.dtsi")


def _census() -> Tuple[List[str], Set[str]]:
    """Every discovered, promotable (`template: true`) shield, split into
    the singleton law's own domain (Sec 2.3): ELIGIBLE (no device
    declares a required, no-default `shield,params`) vs EXCLUDED --
    resolved through the REAL shield library, never hand-listed. Returns
    (sorted eligible names, excluded names) -- fresh values this module
    owns, computed once at collection time (a dozen cheap dtlib parses,
    no cpp of any real board or app -- "nearly free" per Sec 2.3)."""
    infos = discover_shields(_SHIELD_DIRS)
    templated = sorted(name for name, info in infos.items() if info.template)
    types, _deps = load_types()
    eligible: List[str] = []
    excluded: Set[str] = set()
    # The workdir is this census's OWN scratch space for the shield
    # library's cpp output, and nothing outside the loop reads it: a
    # resolved Shield carries its devices as values. Removed on the way
    # out (D10 -- the expander leaking a workdir per invocation was its
    # own slice, and /tmp is tmpfs here, so a leak is charged to RAM);
    # this runs at COLLECTION time, so a mkdtemp with no cleanup would
    # leak one directory per pytest run of the whole integration suite.
    with tempfile.TemporaryDirectory(
            prefix="rigc-singleton-law-census-") as workdir:
        lib, _diags, _deps2 = load_shield_library(
            workdir, _SHIELD_DIRS, types=types)
        for name in templated:
            shield, diags, _d = lib.resolve(
                name, "singleton-law census",
                SourceRef("<singleton-law-census>", 0))
            assert shield is not None, (
                f"{name}: failed to resolve for the singleton-law census -- "
                f"{diags}")
            if shield_declares_required_params(shield):
                excluded.add(name)
            else:
                eligible.append(name)
    return eligible, excluded


ELIGIBLE, EXCLUDED = _census()


def test_excluded_set_is_exactly_the_required_param_shields() -> None:
    """Criterion 3: the domain is DERIVED (Sec 2.3), never hand-listed --
    this pins only what today's derivation yields. grove_btn and
    pilot_alt_button each declare a `shield,params` `zephyr,code` name
    with no authored default; a promoted rig has no CLI slot to supply
    `params:` with at all (parent brief Sec 9.6, the ad-hoc params token
    exit -- still unruled), so the law's two sides could never be
    compared for either one. This assertion can only SHRINK, never grow,
    the day Sec 9.6's grammar lands and gives a promoted rig a way to
    satisfy a required param."""
    assert EXCLUDED == {"grove_btn", "pilot_alt_button"}, (
        f"excluded set is {sorted(EXCLUDED)}, expected exactly "
        "['grove_btn', 'pilot_alt_button'] -- both excluded because "
        "neither shield's required shield,params name has an authored "
        "default and a promoted rig has no --params CLI slot to supply "
        "one (parent brief Sec 9.6, still unruled); a drift here means "
        "either a new required-param shield landed (real) or Sec 9.6's "
        "grammar landed and one of these two now has a way to be "
        "satisfied (update this assertion, don't paper over it)")


def _materialize_fixture(name: str, tmp_path: Path) -> Path:
    """Write the singleton-law fixture TEMPLATE (Sec 4: "one file pair
    under tests/fixtures/boards/rigs/"), substituted for `name`, into a
    fresh directory under tmp_path -- never under tests/fixtures/boards/
    rigs/ itself, so no folder named after a real shield is ever checked
    in (Sec 2.1's caveat: nothing here is reachable from a live namespace
    scan of the fixtures root, since no such folder exists on disk at
    all outside a test's own tmp_path). Declares no board: (Sec 2.1
    parity with the promoted side) and no dt-includes: (Sec 2.2), and
    exactly one socket-less instance named after the shield (S3a's own
    desugaring convention, board-coordinate-s3-brief.md Sec 3).

    Returns the written rig.yml's path; the content file
    (`<name>.yml`, matching promote.PromotedRig's own naming) sits
    alongside it."""
    rig_dir = tmp_path / "fixture-rig"
    rig_dir.mkdir()
    rig_tmpl = (_TEMPLATE_DIR / "rig.yml.tmpl").read_text()
    content_tmpl = (_TEMPLATE_DIR / "content.yml.tmpl").read_text()
    rig_yml = rig_dir / "rig.yml"
    rig_yml.write_text(rig_tmpl.format(name=name))
    (rig_dir / f"{name}.yml").write_text(content_tmpl.format(name=name))
    return rig_yml


def _run(*args: str, out_dir: Path) -> "subprocess.CompletedProcess[str]":
    """`python -m rigc expand`, common board/bindings/include recipe
    shared by both sides of the law -- the fixture board's own sockets
    need edtlib bindings for the connector types themselves
    (_CONNECTOR_BINDINGS, see its own comment) and for gpio-nexus.yaml/
    base.yaml (only defined under Zephyr's own dts/bindings/, never
    duplicated into this module), hence both bindings dirs; --include-dir
    is this module's own include/, which the fixture board's own
    `#include <dt-bindings/connector/*.h>` needs (edt_build.preprocess,
    unlike shield-template parsing, adds no implicit search path of its
    own -- dtsio.MODULE_INC is a DIFFERENT code path's default, not this
    one's)."""
    zb = zephyr_base()
    env = dict(os.environ)
    env["ZEPHYR_BASE"] = zb
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")
    cmd = [sys.executable, "-m", RIG_EXPAND_COMPILE, "expand", *args,
          "--board-dts", str(_BOARD_DTS),
          "--bindings-dir", str(_CONNECTOR_BINDINGS),
          "--bindings-dir", str(Path(zb) / "dts" / "bindings"),
          "--include-dir", str(_MODULE_INCLUDE),
          "--board", _BOARD_LABEL,
          "--out-dir", str(out_dir)]
    return subprocess.run(cmd, env=env, cwd=str(REPO_ROOT),
                          capture_output=True, text=True, timeout=60)


def _context_cmake_mismatch(expected: str, actual: str, name: str) -> Optional[str]:
    """compare_context_cmake's own contract (RIG_DEPENDS as a set, every
    other key exact), PLUS Sec 2.2's one declared exemption: each side's
    own two rig documents (rig.yml / f"{name}.yml") dropped from ITS OWN
    RIG_DEPENDS by basename before the sets are compared -- the files are
    genuinely different (a real path on the fixture side, a path inside
    rigc's own workdir on the promoted side), and no OTHER dependency in
    the corpus is ever named exactly "rig.yml" or f"{name}.yml", so
    filtering by basename cannot silently absorb an unrelated file."""
    own = {"rig.yml", f"{name}.yml"}
    try:
        expected_vars = parse_context_cmake(expected)
        actual_vars = parse_context_cmake(actual)
    except Exception as exc:  # pragma: no cover - defensive, mirrors compare.py
        return f"context.cmake failed to parse: {exc}"

    def _drop_own(raw: str) -> Set[str]:
        return {p for p in split_dependency_set(raw)
               if os.path.basename(p) not in own}

    expected_deps = _drop_own(expected_vars.get("RIG_DEPENDS", ""))
    actual_deps = _drop_own(actual_vars.get("RIG_DEPENDS", ""))
    problems = []
    if expected_deps != actual_deps:
        missing = sorted(expected_deps - actual_deps)
        unexpected = sorted(actual_deps - expected_deps)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if unexpected:
            parts.append("unexpected: " + ", ".join(unexpected))
        problems.append("RIG_DEPENDS (own rig documents exempted): " + "; ".join(parts))
    expected_rest = dict(expected_vars)
    actual_rest = dict(actual_vars)
    expected_rest.pop("RIG_DEPENDS", None)
    actual_rest.pop("RIG_DEPENDS", None)
    rest_report = compare_context_cmake(
        "\n".join(f'set({k} "{v}")' for k, v in expected_rest.items()),
        "\n".join(f'set({k} "{v}")' for k, v in actual_rest.items()))
    if rest_report:
        problems.append(rest_report)
    if not problems:
        return None
    return "\n".join(problems)


@pytest.mark.parametrize("shield", ELIGIBLE, ids=lambda s: s)
def test_singleton_law_holds(shield: str, tmp_path: Path) -> None:
    """Criterion 2: for every eligible shield, `--board b --rig <shield>`
    (via --promote) and `--board b --rig <the fixture rig containing one
    socket-less instance of that shield>` (via the path directly) behave
    IDENTICALLY -- same verdict, and either the same rejection (e.g.
    adafruit_winc1500: both sides reject identically on its own required
    routing-jumper selection, `pin:`, an axis outside Sec 2.3's own
    required-PARAM domain but one the law still holds for -- a promoted
    rig fails exactly the way the checked-in rig it stands for would) or
    every emitted artifact byte-for-byte plus context.cmake (Sec 2.2)."""
    fixture_out = tmp_path / "fixture-out"
    promoted_out = tmp_path / "promoted-out"
    fixture_rig = _materialize_fixture(shield, tmp_path)

    fixture_result = _run(str(fixture_rig), out_dir=fixture_out)
    promoted_result = _run("--promote", shield, out_dir=promoted_out)

    assert fixture_result.returncode == promoted_result.returncode, (
        f"{shield}: verdict differs -- fixture exit "
        f"{fixture_result.returncode}, promoted exit "
        f"{promoted_result.returncode}\n--- fixture stderr ---\n"
        f"{fixture_result.stderr}\n--- promoted stderr ---\n"
        f"{promoted_result.stderr}")

    # Which BRANCH this shield takes is itself pinned. Both sides
    # rejecting identically satisfies the law, but compares stderr and
    # not one emitted artifact -- so without this, the whole census could
    # drift into the reject branch and the module would stay green while
    # checking nothing. The expectation comes from OUTSIDE the run (the
    # EXPECTED_REJECTING literal), never from the verdict it just
    # observed.
    assert (fixture_result.returncode != 0) == (shield in EXPECTED_REJECTING), (
        f"{shield}: took the "
        f"{'reject' if fixture_result.returncode != 0 else 'accept'} branch, "
        f"but EXPECTED_REJECTING says it should "
        f"{'reject' if shield in EXPECTED_REJECTING else 'accept'}. A shield "
        "that newly rejects compares NO artifacts -- the law still holds for "
        "it, but it stops proving what this module exists to prove. Update "
        "EXPECTED_REJECTING deliberately, with the reason, or fix what "
        "started rejecting.\n"
        f"--- fixture stderr ---\n{fixture_result.stderr}")

    if fixture_result.returncode != 0:
        expected_err = _normalize_reject_paths(
            fixture_result.stderr, fixture_rig.parent)
        actual_err = _normalize_reject_paths(
            promoted_result.stderr, fixture_rig.parent)
        assert expected_err == actual_err, (
            f"{shield}: both sides rejected, but for a DIFFERENT reason\n"
            f"--- fixture stderr ---\n{fixture_result.stderr}\n"
            f"--- promoted stderr ---\n{promoted_result.stderr}")
        return

    for fname in EMITTED_FILES:
        fixture_file = fixture_out / fname
        promoted_file = promoted_out / fname
        assert fixture_file.is_file() == promoted_file.is_file(), (
            f"{shield}: {fname} present on one side only "
            f"(fixture={fixture_file.is_file()}, "
            f"promoted={promoted_file.is_file()})")
        if not fixture_file.is_file():
            continue
        expected = fixture_file.read_text()
        actual = promoted_file.read_text()
        # Every emitted artifact compares BYTE-FOR-BYTE (Sec 2.2: "compare
        # every emitted artifact byte-for-byte, plus context.cmake" --
        # RIG_DEPENDS' set exemption is context.cmake's own, handled
        # below, never a reason to weaken any OTHER artifact's own
        # comparison here). Both sides share the same rig name, board
        # label, and instance name (Sec 2.1), so nothing path-dependent
        # ever enters rig-gen.overlay's or config-sheet.md's own banner.
        assert expected == actual, (
            f"{shield}: {fname} mismatch\n--- fixture ---\n{expected}\n"
            f"--- promoted ---\n{actual}")

    context_report = _context_cmake_mismatch(
        (fixture_out / "context.cmake").read_text(),
        (promoted_out / "context.cmake").read_text(),
        shield)
    assert context_report is None, f"{shield}: context.cmake mismatch\n{context_report}"
