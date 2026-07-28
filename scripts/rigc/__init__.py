"""rigc -- the rig compiler, built from scratch against rigexp's frozen
golden corpus (claude/rigs/rigc-mission-brief.md; rigexp is the FROZEN
blueprint, the goldens are the specification).

R1 state: the CLI front door (cli.py, the frozen argv surface), the
diagnostics core (diag.py, diagnostics as return values + the one
renderer), and a thin loader sliver (loader.py) covering the first
proof-of-life rejects. Everything beyond that fails loudly and
distinctly -- `rigc: not implemented: <what>`, exit 3 (unimplemented.py)
-- so a differential run under RIG_EXPAND_COMPILE=rigc is never
mistakable for a wrong diagnostic or a silent fallback to rigexp."""
