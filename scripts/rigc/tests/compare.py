"""Structural comparison of generated artifacts against their actual
contracts, never their bytes.

context.cmake's contract is a key -> value mapping cmake/dts.cmake
include()s. RIG_DEPENDS denotes a SET of dependency paths --
cmake/dts.cmake only ever appends the whole list to
CMAKE_CONFIGURE_DEPENDS, which cares which files it depends on, never in
what order the eager scan visited them. RIG_SHIELDS stays an ORDERED
list (documented as distinct-in-rig-order, and dts.cmake iterates it);
every other variable is an ordinary scalar. Comment lines carry no
contract for this artifact -- the only comment context.cmake has is the
provenance banner.

config-sheet.md's contract is the facts a human reader relies on: which
instance sits on which socket, which address, which CS index, which
strap state -- never its rendering. Heading wording, table column-header
text, and a section's own surrounding prose are free to change; every
datum (instance, shield, socket, device, address, index, position name,
controller, channel, state, property, value) is pinned, and section
presence is compared as a SET while each section's rows are compared as
an ORDERED list (the emitter sorts them deterministically, so a
reordering is a real regression, not noise).

Every function in this module is pure over the text values it is given;
IO (reading the golden, running the tool under test) stays at the
conftest seam that calls compare_context_cmake / compare_config_sheet,
so this module needs no pytest import and a unit test can exercise it
with no golden file and no subprocess.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
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


# --------------------------------------------------------------------------
# config-sheet.md: a fact sheet, not a byte sequence.


class ConfigSheetParseError(ValueError):
    """Raised by parse_config_sheet when a non-blank line matches none of
    the sheet's recognised shapes (title, banner, board line, section
    heading, table header/separator/row, a section's own bullet form, or
    a single tolerated paragraph between a heading and that section's
    first row). An unrecognised line must never be silently skipped: that
    is exactly how a fact extractor drops a fact while still reporting
    green.

    The prose tolerance is deliberately ASYMMETRIC and bounded to one
    paragraph per section (_parse_section_body enforces both): prose
    BEFORE a section's rows is never compared, prose AFTER them is a
    parse error."""


@dataclass
class ConfigSheetFacts:
    """The facts one config-sheet.md carries: read-only once returned by
    parse_config_sheet, and owned by the caller.

    rig_name/board come from the header block. sections maps a SECTION
    KIND (one of "socket_assignment", "straps_jumpers", "chip_selects",
    "pwm", "wires", "parameters") to its rows, each row a tuple of the
    data fields that section's bullet or table form carries -- in the
    ORDER the document presents them, because the emitter sorts rows
    deterministically and a swap is a real regression. Which kinds are
    present is compared as a SET; only a kind common to both documents
    has its row order compared."""

    rig_name: str
    board: str
    sections: Dict[str, Tuple[Tuple[str, ...], ...]]


_TITLE_RE = re.compile(r"^#\s+.*`(?P<name>[^`]+)`\s*$")
_BANNER_RE = re.compile(r"^<!--.*-->$")
_BOARD_RE = re.compile(r"^Board: \*\*(?P<board>.+)\*\*$")
_HEADING_RE = re.compile(r"^##\s+\S")

_STRAP_RE = re.compile(
    r"^- \*\*(?P<inst>[^*]+)\*\* \((?P<socket>[^)]+)\): set \*\*(?P<label>[^*]+)\*\* "
    r"to state (?P<state>\S+) → device address (?P<addr>0x[0-9a-fA-F]+)$")
_JUMPER_RE = re.compile(
    r"^- \*\*(?P<inst>[^*]+)\*\* \((?P<socket>[^)]+)\): set \*\*(?P<label>[^*]+)\*\* "
    r"to state (?P<state>\S+) → routed to pin (?P<pos>\S+)$")
_PWM_RE = re.compile(
    r"^- (?P<inst>[^/]+)/(?P<dev>\S+) \((?P<socket>\S+) (?P<pos>[^)]+)\) → "
    r"(?P<fn>[A-Z]+) (?P<ctrl>\S+) ch(?P<ch>\d+): mux the pin to the controller$")
_WIRE_RE = re.compile(
    r"^- connect \*\*(?P<frm>[^*]+)\*\* → \*\*(?P<to>[^*]+)\*\* — (?P<route>.+)$")
_CS_RE = re.compile(
    r"^- (?P<inst>[^/]+)/(?P<dev>[^:]+): CS index (?P<index>\d+), (?P<pos>\S+)"
    r"(?: → SoC (?P<ctrl>\S+) pin (?P<pin>\S+))?$")


def _split_table_row(line: str, lineno: int) -> Tuple[str, ...]:
    """Split one "| a | b | c |" line into its cell values, stripped.
    Column HEADER TEXT is never the contract (D1) -- only how many
    columns a row carries, which is what tells socket-assignment's table
    apart from parameters' -- so callers read cell values, never the
    header row's own text."""
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2):
        raise ConfigSheetParseError(f"line {lineno}: not a table row: {line!r}")
    return tuple(cell.strip() for cell in stripped[1:-1].split("|"))


def _is_table_separator(line: str) -> bool:
    """True for a markdown table separator row ("|---|---|---|", any run
    of "-"/":" per cell) -- checked structurally rather than via
    _split_table_row so a malformed line here is "not a separator",
    never a parse exception raised from the wrong call site."""
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2):
        return False
    cells = stripped[1:-1].split("|")
    return all(cell.strip() != "" and set(cell.strip()) <= {"-", ":"} for cell in cells)


def _match_bullet(line: str, lineno: int) -> Tuple[str, Tuple[str, ...]]:
    """Match one bullet line against every recognised shape and return
    (section kind, fact tuple). Raises ConfigSheetParseError when none of
    the shapes match -- an unrecognised bullet is a mismatch, never a
    line the section silently drops."""
    m = _STRAP_RE.match(line)
    if m is not None:
        return "straps_jumpers", (
            "strap", m.group("inst"), m.group("socket"), m.group("label"),
            m.group("state"), m.group("addr"))
    m = _JUMPER_RE.match(line)
    if m is not None:
        return "straps_jumpers", (
            "jumper", m.group("inst"), m.group("socket"), m.group("label"),
            m.group("state"), m.group("pos"))
    m = _PWM_RE.match(line)
    if m is not None:
        return "pwm", (
            m.group("inst"), m.group("dev"), m.group("socket"), m.group("pos"),
            m.group("fn"), m.group("ctrl"), m.group("ch"))
    m = _WIRE_RE.match(line)
    if m is not None:
        return "wires", (m.group("frm"), m.group("to"), m.group("route"))
    m = _CS_RE.match(line)
    if m is not None:
        return "chip_selects", (
            m.group("inst"), m.group("dev"), m.group("index"), m.group("pos"),
            m.group("ctrl") or "", m.group("pin") or "")
    raise ConfigSheetParseError(f"line {lineno}: unrecognised bullet: {line!r}")


def _parse_table_section(
        lines: List[str], i: int, n: int,
        ) -> Tuple[str, Tuple[Tuple[str, ...], ...], int]:
    header_lineno = i + 1
    header_cells = _split_table_row(lines[i], i + 1)
    ncols = len(header_cells)
    i += 1
    if i >= n or not _is_table_separator(lines[i]):
        raise ConfigSheetParseError(
            f"line {i + 1}: expected a table separator row after the header")
    i += 1
    rows: List[Tuple[str, ...]] = []
    while i < n and lines[i].strip() != "" and lines[i].lstrip().startswith("|"):
        row = _split_table_row(lines[i], i + 1)
        if len(row) != ncols:
            raise ConfigSheetParseError(
                f"line {i + 1}: table row carries {len(row)} columns, "
                f"header carries {ncols}: {lines[i]!r}")
        rows.append(row)
        i += 1
    if ncols == 3:
        kind = "socket_assignment"
    elif ncols == 4:
        kind = "parameters"
    else:
        raise ConfigSheetParseError(
            f"line {header_lineno}: unrecognised {ncols}-column table")
    return kind, tuple(rows), i


def _parse_bullet_section(
        lines: List[str], i: int, n: int,
        ) -> Tuple[str, Tuple[Tuple[str, ...], ...], int]:
    kind: Optional[str] = None
    rows: List[Tuple[str, ...]] = []
    while i < n and lines[i].strip() != "" and lines[i].lstrip().startswith("- "):
        bullet_kind, fact = _match_bullet(lines[i].strip(), i + 1)
        if kind is None:
            kind = bullet_kind
        elif bullet_kind != kind:
            raise ConfigSheetParseError(
                f"line {i + 1}: bullet shape {bullet_kind!r} mixed into a "
                f"{kind!r} section: {lines[i]!r}")
        rows.append(fact)
        i += 1
    assert kind is not None  # caller only enters here on a line starting "- "
    return kind, tuple(rows), i


def _skip_blank(lines: List[str], i: int, n: int) -> int:
    while i < n and lines[i].strip() == "":
        i += 1
    return i


def _parse_section_body(
        lines: List[str], i: int, n: int,
        ) -> Tuple[str, Tuple[Tuple[str, ...], ...], int]:
    """Dispatch a section's body by its actual shape, never its heading
    text (heading wording is never the contract). A table starts with
    "|"; bullets start with "- ".

    Prose is tolerated in exactly ONE place and never compared: a single
    paragraph between a heading and that section's first row (the PWM
    section's own intro is the only one the emitter produces today). The
    bound is enforced here rather than merely described -- a SECOND
    paragraph, or prose appearing anywhere after a section's rows, is an
    unmatched line like any other. Without the bound, arbitrary text
    could sit at the head of every section, including a sentence
    contradicting the facts below it, and still compare equal."""
    if lines[i].lstrip().startswith("|"):
        return _parse_table_section(lines, i, n)
    if lines[i].lstrip().startswith("- "):
        return _parse_bullet_section(lines, i, n)

    prose_start = i
    j = i
    while (j < n and lines[j].strip() != ""
           and not lines[j].lstrip().startswith("- ")
           and not lines[j].lstrip().startswith("|")
           and not _HEADING_RE.match(lines[j])):
        j += 1
    j = _skip_blank(lines, j, n)
    if j >= n or _HEADING_RE.match(lines[j]):
        raise ConfigSheetParseError(
            f"line {prose_start + 1}: prose paragraph not followed by any "
            f"recognised table or bullet: {lines[prose_start]!r}")
    if lines[j].lstrip().startswith("|"):
        return _parse_table_section(lines, j, n)
    if lines[j].lstrip().startswith("- "):
        return _parse_bullet_section(lines, j, n)
    raise ConfigSheetParseError(
        f"line {j + 1}: a section tolerates at most ONE intro paragraph "
        f"before its rows: {lines[j]!r}")


def parse_config_sheet(text: str) -> ConfigSheetFacts:
    """Parse config-sheet.md into the facts it carries: the header block
    (rig name from the title's backtick-quoted name, and the board line)
    plus every section's rows, keyed by section KIND rather than its
    (tolerated, reworded-at-will) heading text.

    The provenance banner comment is recognised structurally (it must be
    present, right after the title) but its own text is never read --
    the tool-identity leak this comparator exists to stop mattering.

    Every non-blank line must be consumed by exactly one recogniser;
    anything else raises ConfigSheetParseError rather than being
    dropped, so a truncated or malformed artifact can never compare
    equal to whatever facts the rest of the document happens to carry.

    Returns a fresh ConfigSheetFacts the caller owns; text is read-only."""
    lines = text.splitlines()
    n = len(lines)

    def skip_blank(i: int) -> int:
        return _skip_blank(lines, i, n)

    i = skip_blank(0)
    if i >= n:
        raise ConfigSheetParseError("empty document")
    m = _TITLE_RE.match(lines[i])
    if m is None:
        raise ConfigSheetParseError(
            f"line {i + 1}: expected a title line carrying the rig name in "
            f"backticks: {lines[i]!r}")
    rig_name = m.group("name")
    i = skip_blank(i + 1)

    if i >= n or _BANNER_RE.match(lines[i]) is None:
        raise ConfigSheetParseError(
            "expected the provenance banner comment (<!-- ... -->) after "
            "the title")
    i = skip_blank(i + 1)

    if i >= n:
        raise ConfigSheetParseError("expected a Board: **<board>** line")
    m = _BOARD_RE.match(lines[i])
    if m is None:
        raise ConfigSheetParseError(
            f"line {i + 1}: expected a Board: **<board>** line: {lines[i]!r}")
    board = m.group("board")
    i = skip_blank(i + 1)

    sections: Dict[str, Tuple[Tuple[str, ...], ...]] = {}
    while i < n:
        if not _HEADING_RE.match(lines[i]):
            raise ConfigSheetParseError(
                f"line {i + 1}: expected a ## section heading: {lines[i]!r}")
        heading_lineno = i + 1
        i = skip_blank(i + 1)
        if i >= n:
            raise ConfigSheetParseError(
                f"section heading at line {heading_lineno} has no body")
        kind, rows, i = _parse_section_body(lines, i, n)
        if kind in sections:
            raise ConfigSheetParseError(
                f"section kind {kind!r} appears more than once")
        sections[kind] = rows
        i = skip_blank(i)

    return ConfigSheetFacts(rig_name=rig_name, board=board, sections=sections)


def _describe_section_mismatch(
        kind: str, expected_rows: Tuple[Tuple[str, ...], ...],
        actual_rows: Tuple[Tuple[str, ...], ...]) -> str:
    lines = [f"section {kind!r}: rows differ (order is contract)"]
    for idx, (exp, act) in enumerate(
            itertools.zip_longest(expected_rows, actual_rows, fillvalue=None)):
        if exp != act:
            lines.append(f"  row {idx}: golden {exp!r} != actual {act!r}")
    return "\n".join(lines)


def compare_config_sheet(expected: str, actual: str) -> Optional[str]:
    """Compare two config-sheet.md texts against the sheet's real
    contract -- the facts a reader relies on -- instead of byte-for-byte:

    * the rig name (from the title) and the board line compare exact.
    * which SECTION KINDS are present compares as a SET: a missing or
      extra section is a mismatch regardless of where it would have
      sorted.
    * within a section common to both documents, rows compare as an
      ORDERED list -- the emitter sorts them deterministically, so a
      reordering is a real regression, not noise.
    * heading wording, table column-header text, and the single paragraph
      a section may carry between its heading and its first row are read
      structurally and never compared as text; the provenance banner is
      recognised as present but never read at all. Section ORDER is not
      compared either, since section presence is a set -- a deliberate
      loosening relative to byte comparison.

    Returns None when the two texts are contract-equivalent; otherwise a
    human-readable report of every mismatch found (not just the first).
    Text that fails to parse at all is reported as a mismatch too, never
    raised past this function, so a caller can treat "the golden doesn't
    parse" and "the golden doesn't match" uniformly."""
    try:
        expected_facts = parse_config_sheet(expected)
    except ConfigSheetParseError as exc:
        return f"golden config-sheet.md failed to parse: {exc}"
    try:
        actual_facts = parse_config_sheet(actual)
    except ConfigSheetParseError as exc:
        return f"actual config-sheet.md failed to parse: {exc}"

    problems: List[str] = []
    if expected_facts.rig_name != actual_facts.rig_name:
        problems.append(
            f"rig name: golden {expected_facts.rig_name!r} != actual "
            f"{actual_facts.rig_name!r}")
    if expected_facts.board != actual_facts.board:
        problems.append(
            f"board: golden {expected_facts.board!r} != actual "
            f"{actual_facts.board!r}")

    expected_kinds = set(expected_facts.sections)
    actual_kinds = set(actual_facts.sections)
    for kind in sorted(expected_kinds - actual_kinds):
        problems.append(f"section {kind!r}: present in golden, absent from actual")
    for kind in sorted(actual_kinds - expected_kinds):
        problems.append(f"section {kind!r}: absent from golden, present in actual")
    for kind in sorted(expected_kinds & actual_kinds):
        expected_rows = expected_facts.sections[kind]
        actual_rows = actual_facts.sections[kind]
        if expected_rows != actual_rows:
            problems.append(
                _describe_section_mismatch(kind, expected_rows, actual_rows))

    if not problems:
        return None
    return "\n".join(problems)
