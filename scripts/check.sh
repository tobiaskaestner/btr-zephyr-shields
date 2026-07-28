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

targets="scripts/rigexp"

echo "== mypy: $targets =="
"$PY" -m mypy $targets

if [ -d scripts/rigexp/tests ]; then
    echo "== pytest =="
    # .reports/ is gitignored and repo-local -- never a build -d dir, since
    # -p always wipes those on the next configure.
    # --durations=25 is free and always on; --junitxml is per-SUITE (fast vs
    # full are different invocations of this same gate, so different files)
    # so scripts/timing_report.py has machine-readable per-test wall times to
    # diff against a baseline -- see that script's own docstring.
    mkdir -p .reports
    if [ -n "$CHECK_FAST" ]; then
        "$PY" -m pytest -m "not build" --durations=25 \
            --junitxml=.reports/junit-fast.xml
    else
        "$PY" -m pytest --durations=25 --junitxml=.reports/junit-full.xml
    fi
else
    echo "== pytest: SKIPPED — no scripts/rigexp/tests yet =="
fi

echo "check.sh: ALL GREEN"
