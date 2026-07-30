"""Structural comparison of context.cmake against its actual contract: a
key -> value mapping cmake/dts.cmake include()s, not a byte sequence.
RIG_DEPENDS denotes a SET of dependency paths -- cmake/dts.cmake only
ever appends the whole list to CMAKE_CONFIGURE_DEPENDS, which cares
which files it depends on, never in what order the eager scan visited
them. RIG_SHIELDS stays an ORDERED list (documented as distinct-in-rig-
order, and dts.cmake iterates it); every other variable is an ordinary
scalar. Comment lines carry no contract for this artifact -- the only
comment context.cmake has is the provenance banner.

Both functions here are pure over the two text values they are given;
IO (reading the golden, running the tool under test) stays at the
conftest seam that calls compare_context_cmake, so this module needs no
pytest import and a unit test can exercise it with no golden file and no
subprocess.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Tuple

_SET_HEAD_RE = re.compile(r'set\((\w+)\s*"')


class ContextCmakeParseError(ValueError):
    """Raised by parse_context_cmake when a line is neither a comment nor
    a set(VAR "value") assignment. An unrecognized shape must never be
    silently skipped: dropping it would let a truncated or malformed
    artifact compare equal to whatever mapping the rest of the file
    happened to produce."""


def _scan_quoted_value(line: str, start: int) -> Tuple[str, int]:
    """Scan a set(VAR "...")'s quoted value, starting right after the
    opening quote, honoring CMake's backslash escaping so an escaped
    quote never terminates the value early.

    Returns the value's raw text (escapes left intact -- unescaping is
    the concern of whoever interprets a specific variable's contract,
    not of finding where the literal ends) and the index of the line
    immediately after the closing quote."""
    chars: List[str] = []
    i = start
    escaped = False
    while i < len(line):
        ch = line[i]
        if escaped:
            chars.append(ch)
            escaped = False
        elif ch == "\\":
            chars.append(ch)
            escaped = True
        elif ch == '"':
            return "".join(chars), i + 1
        else:
            chars.append(ch)
        i += 1
    raise ContextCmakeParseError(f"unterminated quoted value: {line!r}")


def parse_context_cmake(text: str) -> Dict[str, str]:
    """Parse context.cmake source into {VAR: raw value}, one entry per
    set(VAR "value") line. VAR is verbatim; value is the literal quoted
    content with CMake's list-escaping (backslash-backslash, backslash-
    quote, backslash-semicolon) left INTACT -- only RIG_DEPENDS' contract
    needs it interpreted as a list (split_dependency_set, below, is the
    one caller that does), every other variable's contract is the raw
    string itself.

    Comment lines (leading "#", after stripping surrounding whitespace)
    and blank lines are ignored. Every other line must be exactly one
    set(VAR "value") assignment; anything else raises
    ContextCmakeParseError rather than being dropped.

    Returns a fresh dict the caller owns; text is read-only and never
    mutated."""
    mapping: Dict[str, str] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SET_HEAD_RE.match(line)
        if match is None:
            raise ContextCmakeParseError(
                f"line {lineno}: not a comment or a set(VAR \"value\") "
                f"assignment: {raw_line!r}")
        name = match.group(1)
        value, end = _scan_quoted_value(line, match.end())
        if line[end:] != ")":
            raise ContextCmakeParseError(
                f"line {lineno}: trailing content after the closing quote: "
                f"{raw_line!r}")
        mapping[name] = value
    return mapping


def split_dependency_set(raw_value: str) -> FrozenSet[str]:
    """Split RIG_DEPENDS' raw (still list-escaped) value into its
    dependency-path elements, undoing emitter/context.py's
    _cmake_list_escape per element in one left-to-right scan -- so an
    escaped semicolon inside a path is never mistaken for a delimiter,
    and the delimiters themselves never leak into an element.

    Returned as a frozenset: RIG_DEPENDS is a SET by contract, and a
    dependency listed twice is exactly as satisfied as one listed once."""
    elements: List[str] = []
    current: List[str] = []
    escaped = False
    for ch in raw_value:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ";":
            elements.append("".join(current))
            current = []
        else:
            current.append(ch)
    elements.append("".join(current))
    return frozenset(elements)


# The one variable whose contract is a SET rather than a scalar (or, for
# RIG_SHIELDS, an order-sensitive list compared as the plain string it
# is -- see the module docstring).
_UNORDERED_SET_VARS = frozenset({"RIG_DEPENDS"})


def compare_context_cmake(expected: str, actual: str) -> Optional[str]:
    """Compare two context.cmake texts against the artifact's real
    contract instead of byte-for-byte:

    * RIG_DEPENDS compares as a SET -- reordering its entries is not a
      mismatch; a missing or an extra entry is.
    * every other variable (RIG_NAME, RIG_BOARD, RIG_SHIELDS,
      RIG_REVISION, RIG_VARIANT, RIG_SHIELD_REVISIONS) compares as an
      ordinary scalar, exact-match -- RIG_SHIELDS included: it is
      documented as distinct-in-rig-order and dts.cmake iterates it, so
      treating it as a set would hide a real ordering regression.
    * a variable declared on one side and absent on the other is always
      a mismatch. RIG_REVISION/RIG_VARIANT/RIG_SHIELD_REVISIONS follow
      the "no declaration, no artifact" rule (emitter/context.py), so
      their absence is meaningful, never incidental.

    Returns None when the two texts are contract-equivalent; otherwise a
    human-readable report of every mismatch found (not just the first),
    with RIG_DEPENDS' own mismatch broken down into missing/unexpected
    entries. Text that fails to parse at all is reported as a mismatch
    too, never raised past this function, so a caller can treat "the
    golden doesn't parse" and "the golden doesn't match" uniformly."""
    try:
        expected_vars = parse_context_cmake(expected)
    except ContextCmakeParseError as exc:
        return f"golden context.cmake failed to parse: {exc}"
    try:
        actual_vars = parse_context_cmake(actual)
    except ContextCmakeParseError as exc:
        return f"actual context.cmake failed to parse: {exc}"

    problems: List[str] = []
    for name in sorted(set(expected_vars) | set(actual_vars)):
        if name not in actual_vars:
            problems.append(f"{name}: present in golden, absent from actual")
            continue
        if name not in expected_vars:
            problems.append(
                f"{name}: absent from golden, present in actual "
                f"({actual_vars[name]!r})")
            continue
        if name in _UNORDERED_SET_VARS:
            expected_set = split_dependency_set(expected_vars[name])
            actual_set = split_dependency_set(actual_vars[name])
            if expected_set != actual_set:
                missing = sorted(expected_set - actual_set)
                unexpected = sorted(actual_set - expected_set)
                parts = []
                if missing:
                    parts.append("missing: " + ", ".join(missing))
                if unexpected:
                    parts.append("unexpected: " + ", ".join(unexpected))
                problems.append(f"{name}: " + "; ".join(parts))
        elif expected_vars[name] != actual_vars[name]:
            problems.append(
                f"{name}: golden {expected_vars[name]!r} != actual "
                f"{actual_vars[name]!r}")
    if not problems:
        return None
    return "\n".join(problems)
