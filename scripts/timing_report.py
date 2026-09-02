#!/usr/bin/env python3
"""Diff a pytest --junitxml run against a stored baseline, flagging any
test whose SHARE of the suite's wall time grew past a threshold.

Absolute seconds are machine-dependent -- comparing share of the suite
total instead is the same signal on a faster or slower machine, since a
uniform speed change moves every test's numerator and denominator
together. The baseline file still records each test's absolute seconds
(for the slowest-N table, and for a human reading the file), but the DIFF
that flags a regression looks only at share-of-total.

Usage:
    scripts/timing_report.py .reports/junit-full.xml \
        --update-baseline .reports/timing-baseline.json
    scripts/timing_report.py .reports/junit-full.xml \
        --baseline .reports/timing-baseline.json

The baseline file is expected to live under .reports/ (gitignored) --
keep it local rather than committing it, since it is a per-machine
artifact, not a project one.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_junit(path: Path) -> dict[str, float]:
    """nodeid -> wall time (seconds), one entry per <testcase>. nodeid is
    reconstructed as classname::name -- junitxml's own two-field split of
    what pytest otherwise renders as a single node id -- so it matches
    across runs regardless of how the suite was invoked."""
    tree = ET.parse(path)
    times: dict[str, float] = {}
    for case in tree.getroot().iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        nodeid = f"{classname}::{name}" if classname else name
        times[nodeid] = float(case.get("time", "0"))
    return times


def slowest(times: dict[str, float], n: int) -> list[tuple[str, float]]:
    return sorted(times.items(), key=lambda kv: kv[1], reverse=True)[:n]


def write_baseline(path: Path, times: dict[str, float]) -> None:
    total = sum(times.values()) or 1.0
    baseline = {
        "total_seconds": total,
        "tests": {
            nodeid: {"seconds": secs, "share": secs / total} for nodeid, secs in times.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")


def diff_against_baseline(times: dict[str, float], baseline_path: Path, threshold: float) -> bool:
    """Print every test whose share of the suite total grew by more than
    threshold (a fraction of the suite -- 0.02 means 2 percentage points)
    relative to the stored baseline. A test absent from the baseline (new
    since it was recorded) is skipped -- there is nothing to diff it
    against. Returns True iff at least one regression was flagged, so the
    caller can turn that into a nonzero exit code."""
    baseline = json.loads(baseline_path.read_text())
    base_tests = baseline.get("tests", {})
    total = sum(times.values()) or 1.0
    regressed = False
    for nodeid, secs in sorted(times.items()):
        share = secs / total
        base = base_tests.get(nodeid)
        if base is None:
            continue
        delta = share - base["share"]
        if delta > threshold:
            regressed = True
            print(
                f"REGRESSION  {nodeid}: share {base['share']:.4f} -> "
                f"{share:.4f} (+{delta:.4f}), {base['seconds']:.2f}s -> "
                f"{secs:.2f}s"
            )
    return regressed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("junitxml", type=Path)
    parser.add_argument("--baseline", type=Path, help="baseline json to diff the run against")
    parser.add_argument(
        "--update-baseline",
        type=Path,
        help="write (overwrite) the baseline json instead of diffing",
    )
    parser.add_argument(
        "--slowest", type=int, default=10, help="always print the N slowest tests (default 10)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.02,
        help="share-of-total delta (fraction of the suite) that "
        "counts as a regression (default 0.02 = 2 "
        "percentage points)",
    )
    args = parser.parse_args(argv)

    times = parse_junit(args.junitxml)
    total = sum(times.values())
    print(f"{len(times)} tests, {total:.2f}s total")
    print(f"slowest {args.slowest}:")
    for nodeid, secs in slowest(times, args.slowest):
        share = secs / total if total else 0.0
        print(f"  {secs:7.3f}s  {share:6.2%}  {nodeid}")

    if args.update_baseline:
        write_baseline(args.update_baseline, times)
        print(f"baseline written: {args.update_baseline}")
        return 0

    if args.baseline:
        if not args.baseline.is_file():
            print(
                f"no baseline at {args.baseline} yet -- run --update-baseline first",
                file=sys.stderr,
            )
            return 2
        regressed = diff_against_baseline(times, args.baseline, args.threshold)
        return 1 if regressed else 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
