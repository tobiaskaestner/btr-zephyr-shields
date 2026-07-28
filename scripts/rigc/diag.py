"""Diagnostics core: diagnostics are DATA, returned upward.

The three unit-test-hostile shapes are banned here by construction
(rigc-mission-brief.md Sec 6): no mutable accumulator threaded in and
written to, no whole-model parameters where a value would do, no side
channel. A function that finds something wrong RETURNS Diagnostic values
(alone or beside its result); composition is list concatenation at the
caller.

ONE renderer produces the frozen stderr format the goldens specify:

    error[<code>]: <message first line>
        <message continuation lines, four-space indented>
        at <path>:<line> (<key>)

Anchor-path rule (rigc-r1-brief.md Sec 3, RATIFIED): module-agnostic --
if the path lies under a `scripts/<module>/` component, it renders
relative to that component; otherwise it renders absolute. On the frozen
corpus this is byte-identical to rigexp's own-package-dir rule (all
reject fixtures live under scripts/rigexp/), and at cutover fixture
anchors survive the move to scripts/rigc/ unchanged. anchor_path() is a
pure function of the path value alone -- deliberately no module-scope
dirname(__file__) constant -- so unit tests exercise it with synthetic
roots.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Sequence

#: Severity vocabulary. The taxonomy carries over from the goldens:
#: "lang-*" codes come from the loader, "phys-*" codes from the analyzer.
ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class SourceRef:
    """One source anchor: file path (absolute as loaded), 1-based line,
    and the human key label (YAML key path, node path, or DTS label)."""

    file: str
    line: int
    key: str = ""


@dataclass(frozen=True)
class Diagnostic:
    """One finding, as a value. message's first line is the claim;
    following lines are detail (rendered indented)."""

    severity: str                       # ERROR | WARNING
    code: str                           # "lang-*" | "phys-*"
    message: str
    refs: tuple[SourceRef, ...] = ()


def error(code: str, message: str,
          refs: Sequence[SourceRef] = ()) -> Diagnostic:
    return Diagnostic(ERROR, code, message, tuple(refs))


def has_errors(diags: Iterable[Diagnostic]) -> bool:
    return any(d.severity == ERROR for d in diags)


def anchor_path(path: str) -> str:
    """The RATIFIED anchor-path rule, module-agnostic: render a path under
    a `scripts/<module>/` component relative to that component (the
    DEEPEST such component wins, the most specific reading), otherwise
    render it unchanged. A file directly under a `scripts/` component has
    no module below it and stays unchanged."""
    parts = path.split(os.sep)
    # Need parts[i] == "scripts", a module at i+1, and content below it.
    for i in range(len(parts) - 3, -1, -1):
        if parts[i] == "scripts":
            return os.sep.join(parts[i + 2:])
    return path


def _render_one(diag: Diagnostic) -> str:
    head, *rest = diag.message.splitlines()
    lines = [f"{diag.severity}[{diag.code}]: {head}"]
    lines += [f"    {line}" for line in rest]
    seen: set[str] = set()
    for ref in diag.refs:
        anchor = f"{anchor_path(ref.file)}:{ref.line}"
        if ref.key:
            anchor = f"{anchor} ({ref.key})"
        if anchor not in seen:          # duplicates render once, order kept
            seen.add(anchor)
            lines.append(f"    at {anchor}")
    return "\n".join(lines)


def render(diags: Iterable[Diagnostic]) -> str:
    """THE renderer -- the only place diagnostics become text. One line
    block per diagnostic, joined by newlines (no trailing newline; the
    caller's print() supplies it)."""
    return "\n".join(_render_one(d) for d in diags)
