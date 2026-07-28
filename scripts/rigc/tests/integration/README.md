# rigc integration tests — deliberately empty

This directory stays EMPTY until cutover. During construction the frozen
rigexp suite (`scripts/rigexp/tests/`, run under `RIG_EXPAND_COMPILE=rigc`
through the R0 differential harness) IS rigc's integration coverage — the
43 reject goldens plus the corpus goldens are the executable specification
(rigc-mission-brief.md §2). Adding tests here before the frozen suite is
green under rigc would fork the spec into two drifting suites, which is
exactly what the harness exists to prevent (rigc-r1-brief.md §4).

At cutover the frozen suite's fixtures and integration tests MOVE here
(moved, not copied), and this file goes away.
