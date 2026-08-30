#!/bin/sh
# Commit gate for the Bridge-A rewrite: mypy clean + pytest green.
# Every commit must pass this (plus reviewer acceptance — see .claude/agents/).
#
# Usage:  ZEPHYR_BASE=<zephyr tree> scripts/check.sh
#   CHECK_FAST=1   skip tests marked 'build' — NOTE: since THE FLIP this
#                  includes the emitted golden comparisons too (pass 1 reads
#                  the real board DT, which needs a configured board recipe),
#                  so the fast gate checks NO overlay goldens at all.
#
# Run it with the workspace venv active (or PYTHON=<venv python>) so mypy and
# pytest are the pinned ones.
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

if [ -z "$ZEPHYR_BASE" ]; then
    echo "check.sh: ZEPHYR_BASE is not set — export it (the zephyr tree, rig branch)." >&2
    echo "  It locates dtlib/edtlib for both mypy (MYPYPATH) and the tests." >&2
    exit 2
fi
export MYPYPATH="$ZEPHYR_BASE/scripts/dts/python-devicetree/src"

targets="scripts/rigc"

echo "== mypy: $targets =="
"$PY" -m mypy $targets

# rigc's tests: a SEPARATE pytest invocation from the frozen suite below,
# in both the fast and full paths, for ONE reason that survives cutover:
# coverage is measured over the in-process tests/unit/ layer only (next
# block). The tests/integration/ suite drives rigc as a SUBPROCESS, which
# `coverage` cannot see inside -- folding the two invocations into one
# would dilute the coverage figure with subprocess work it never measures,
# not raise it. Do not "simplify" this into one pytest call without first
# re-deriving fail_under against whatever the combined run would report.
mkdir -p .reports
echo "== pytest: rigc (with unit coverage) =="
# Coverage rides the unit suite because it is IN-PROCESS (rigc-mission-brief
# Sec 5: no subprocess at unit level) -- `coverage run` sees every line the
# tests exercise, no subprocess plumbing needed. That property the golden
# suite below cannot have: it drives the CLI as a subprocess, so it runs
# unmeasured. Config (source, omit,
# data file) lives in pyproject.toml [tool.coverage.*].
# Failure is captured, not fatal (set -e), so the browsable reports below
# still render for a RED run -- the run you most want a report for. The
# status is re-raised right after them.
rigc_status=0
"$PY" -m coverage run -m pytest scripts/rigc/tests/unit --durations=25 \
    --junitxml=.reports/junit-rigc.xml || rigc_status=$?
# `coverage report` carries fail_under (pyproject [tool.coverage.report]), so
# it EXITS NON-ZERO on a coverage regression. Capture it the same way the test
# run above is captured: under set -e an unguarded call would abort here and
# skip the browsable reports below, which is precisely the run you want them
# for. Both statuses are re-raised after the reports render.
coverage_status=0
"$PY" -m coverage report || coverage_status=$?
# Browsable views, rewritten every run:
#   $BROWSER .reports/coverage-rigc-html/index.html
#   $BROWSER .reports/junit-rigc.html
"$PY" -m coverage html -q -d .reports/coverage-rigc-html
[ -f .reports/junit-rigc.xml ] && \
    "$PY" scripts/junit_html.py .reports/junit-rigc.xml .reports/junit-rigc.html
[ "$rigc_status" -eq 0 ] || exit "$rigc_status"
[ "$coverage_status" -eq 0 ] || {
    echo "check.sh: rigc unit coverage below the fail_under floor" >&2
    exit "$coverage_status"
}

if [ -d scripts/rigc/tests/integration ]; then
    echo "== pytest =="
    # .reports/ is gitignored and repo-local -- never a build -d dir, since
    # -p always wipes those on the next configure.
    # --durations=25 is free and always on; --junitxml is per-SUITE (fast vs
    # full are different invocations of this same gate, so different files)
    # so scripts/timing_report.py has machine-readable per-test wall times to
    # diff against a baseline -- see that script's own docstring.
    #
    # Two directories, one suite: tests/integration/ holds the modules that
    # read nothing outside scripts/rigc/ (these travel to bridle once the
    # mechanics move out); tests/integration_stay/ holds the ones tethered
    # to this repo's own boards/rigs/, boards/shields/, or boards/extend/
    # content (these stay behind). Both run together here, sharing one pair
    # of junit files -- the split is a source-layout concern, not a reason
    # for the gate to report them as two suites.
    if [ -n "$CHECK_FAST" ]; then
        suite=fast
    else
        suite=full
    fi
    frozen_status=0
    if [ -n "$CHECK_FAST" ]; then
        "$PY" -m pytest -m "not build" scripts/rigc/tests/integration \
            scripts/rigc/tests/integration_stay --durations=25 \
            --junitxml=.reports/junit-fast.xml || frozen_status=$?
    else
        "$PY" -m pytest scripts/rigc/tests/integration \
            scripts/rigc/tests/integration_stay --durations=25 \
            --junitxml=.reports/junit-full.xml || frozen_status=$?
    fi
    # Same render-then-re-raise shape as the rigc block above:
    #   $BROWSER .reports/junit-fast.html   (or junit-full.html)
    [ -f ".reports/junit-$suite.xml" ] && \
        "$PY" scripts/junit_html.py ".reports/junit-$suite.xml" \
            ".reports/junit-$suite.html"
    [ "$frozen_status" -eq 0 ] || exit "$frozen_status"
else
    echo "== pytest: SKIPPED — no scripts/rigc/tests/integration yet =="
fi

echo "check.sh: ALL GREEN"
