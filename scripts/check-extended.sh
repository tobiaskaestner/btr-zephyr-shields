#!/bin/sh
# Companion gate for the tests tethered to this repo's own hardware
# definitions (boards/rigs/, boards/shields/, boards/extend/) -- the half
# of the old single gate that does NOT travel when the transpiler
# (scripts/rigc/, doc/, cmake/) migrates out to bridle. scripts/check.sh is
# still the one to run for everything else -- mypy, the unit suite, and
# the travelling integration suite (scripts/rigc/tests/integration/) are
# its job, not this script's, and it never re-runs them here. BOTH
# scripts together are what this repo's full gate means today: run
# check.sh first, then this one.
#
# This script's own suite is no longer in pyproject.toml's `testpaths`
# (that file travels with scripts/rigc/ and must never name a path that
# does not exist at the destination) -- so a bare `pytest` in this repo
# collects ONLY the travelling suite now. To run the stay-side suite by
# hand, outside this script, name it explicitly:
#
#   ZEPHYR_BASE=<zephyr tree> pytest scripts/rigc/tests/integration_stay
#
# Deliberately duplicated from check.sh, not factored together: the
# ZEPHYR_BASE guard, .reports/ handling and junit rendering below are
# copy-pasted rather than shared, because check.sh cannot be SOURCED by
# this script -- check.sh is the half that leaves. A shared helper would
# either have to travel too (stranding this script) or stay behind
# (breaking check.sh at the destination); two small, independently
# readable copies are the correct shape for a seam that is about to be
# cut, not a maintenance smell to clean up.
#
# Usage:  ZEPHYR_BASE=<zephyr tree> scripts/check-extended.sh
#   CHECK_FAST=1   skip tests marked 'build', same meaning as check.sh's
#                  own flag (see that script's usage comment for what
#                  that does and does not check).
#
# Run it with the workspace venv active (or PYTHON=<venv python>) so
# pytest is the pinned one.
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

if [ -z "$ZEPHYR_BASE" ]; then
    echo "check-extended.sh: ZEPHYR_BASE is not set — export it (the zephyr tree, rig branch)." >&2
    echo "  It locates dtlib/edtlib for the tests." >&2
    exit 2
fi
# No MYPYPATH here: this script runs no mypy (that is check.sh's job,
# against the travelling scripts/rigc/ tree only) -- ZEPHYR_BASE alone is
# what the tests themselves need, resolved at runtime by
# board.edt_build.ensure_devicetree_on_path(), never through this env var.

if [ -d scripts/rigc/tests/integration_stay ]; then
    echo "== pytest (stay-side) =="
    # .reports/ is gitignored and repo-local -- never a build -d dir, since
    # -p always wipes those on the next configure.
    # --durations=25 is free and always on; --junitxml carries its OWN
    # filenames (junit-extended-fast.xml / junit-extended-full.xml, never
    # check.sh's junit-fast.xml / junit-full.xml) so a run of both scripts
    # cannot clobber the other's report.
    mkdir -p .reports
    if [ -n "$CHECK_FAST" ]; then
        suite=fast
    else
        suite=full
    fi
    stay_status=0
    if [ -n "$CHECK_FAST" ]; then
        "$PY" -m pytest -m "not build" scripts/rigc/tests/integration_stay \
            --durations=25 \
            --junitxml=.reports/junit-extended-fast.xml || stay_status=$?
    else
        "$PY" -m pytest scripts/rigc/tests/integration_stay \
            --durations=25 \
            --junitxml=.reports/junit-extended-full.xml || stay_status=$?
    fi
    # Same render-then-re-raise shape as check.sh's own blocks: reports are
    # written for a RED run too -- the run you most want a report for --
    # with the status re-raised right after.
    #   $BROWSER .reports/junit-extended-fast.html   (or junit-extended-full.html)
    [ -f ".reports/junit-extended-$suite.xml" ] && \
        "$PY" scripts/junit_html.py ".reports/junit-extended-$suite.xml" \
            ".reports/junit-extended-$suite.html"
    [ "$stay_status" -eq 0 ] || exit "$stay_status"
else
    echo "== pytest: SKIPPED — no scripts/rigc/tests/integration_stay yet =="
fi

echo "check-extended.sh: ALL GREEN"
