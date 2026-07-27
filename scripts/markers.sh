#!/bin/sh
# Lists every collected test with its markers -- pytest has no built-in for
# this. One line per test: node id, a tab, then its unit/integration/build
# markers (space-separated, empty for none of the three); a test carrying
# NEITHER unit nor integration is prefixed UNMARKED, so a classification gap
# (marker discipline forbids it, but this listing's whole job is showing
# classification, so it must not silently omit the exact case that means
# classification broke) cannot disappear from the output.
#
# The listing comes from one pytest collection (conftest.py's
# --markers-report, itself built on the same collection hook
# test_marker_discipline.py reads) rather than separate `-m <expr>` passes
# per marker -- it walks the full collected item list directly, so it cannot
# miss an unmarked test by construction.
#
# Usage:  ZEPHYR_BASE=<zephyr tree> scripts/markers.sh [pytest args...]
#   Extra args are passed straight through to pytest, so this can be scoped
#   to a file (scripts/markers.sh scripts/rigexp/tests/test_board_read.py)
#   or a -k expression, same as scripts/check.sh's pytest invocation.
set -e
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

if [ -z "$ZEPHYR_BASE" ]; then
    echo "markers.sh: ZEPHYR_BASE is not set — export it (the zephyr tree, rig branch)." >&2
    echo "  It locates dtlib/edtlib the same way scripts/check.sh's pytest run needs." >&2
    exit 2
fi

# grep '::' strips pytest's own banner/summary lines (e.g. "no tests ran in
# 0.14s") -- every real report line contains "::" (it is a node id), no
# banner line does. The final sort is belt-and-suspenders: conftest.py
# already prints in node-id order, but a caller-supplied -p/plugin could in
# principle interleave output ahead of it.
"$PY" -m pytest --markers-report -q "$@" 2>/dev/null | grep '::' | sort
