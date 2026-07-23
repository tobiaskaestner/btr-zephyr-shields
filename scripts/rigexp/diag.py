"""Diagnostics. architecture.md: the error taxonomy follows the component
split — 'lang-*' codes come from a loader (candidate-dependent quality, the
open verdict), 'phys-*' codes from the analyzer (candidate-independent,
worded at the copper level per C6). The emitter has no error class.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# btr-shields/scripts/rigexp/ — the vendored package directory itself. Downstream
# vendored copy: unlike the frontend-trial prototype (which sat three levels
# under its tree root, frontend-trial/scripts/rigexp/diag.py), this package
# IS the root — no reference back into claude/ is needed at runtime. Every
# DT-mechanics fact (board sockets, connector-type bindings) is read from the
# REAL trees the module ships alongside this package (boards/, dts/bindings/,
# dts/connectors/, include/dt-bindings/connector/ — see board_edt.py /
# ctypes_registry.py / dtsio.py); the bundled common-dts/{boards,bindings}
# scaffold (Bridge-A rewrite) is gone (saferail 8: deleted in full).
ROOT = os.path.dirname(os.path.abspath(__file__))


def _rel(path: str) -> str:
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


@dataclass
class SrcRef:
    file: str
    line: int
    label: str = ""  # human anchor: node path, DTS label, or YAML key path

    def __str__(self):
        s = f"{_rel(self.file)}:{self.line}"
        return f"{s} ({self.label})" if self.label else s


@dataclass
class Diagnostic:
    severity: str  # 'error' | 'warning'
    code: str      # 'lang-*' | 'phys-*'
    message: str   # first line: the claim; following lines: detail
    refs: list = field(default_factory=list)

    def render(self) -> str:
        head, *rest = self.message.splitlines()
        lines = [f"{self.severity}[{self.code}]: {head}"]
        lines += [f"    {line}" for line in rest]
        seen = set()
        for ref in self.refs:
            if ref is not None and str(ref) not in seen:
                seen.add(str(ref))
                lines.append(f"    at {ref}")
        return "\n".join(lines)


class Diagnostics(list):
    def error(self, code, message, refs=()):
        self.append(Diagnostic("error", code, message, list(refs)))

    def warning(self, code, message, refs=()):
        self.append(Diagnostic("warning", code, message, list(refs)))

    @property
    def errors(self):
        return [d for d in self if d.severity == "error"]

    def render(self) -> str:
        return "\n".join(d.render() for d in self)


class LoadError(Exception):
    """Fatal loader failure (parse error, missing file): loading cannot
    continue at all. Non-fatal loader findings go into Diagnostics."""

    def __init__(self, diag: Diagnostic):
        self.diag = diag
        super().__init__(diag.render())
