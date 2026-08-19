"""rigc -- the rig compiler, built from scratch against rigexp's frozen
golden corpus (claude/rigs/rigc-mission-brief.md; rigexp is the FROZEN
blueprint, the goldens are the specification).

The pipeline is COMPLETE as of R5 (rigc-r5-brief.md), five stages in
order: the CLI front door (cli.py) sequences the run; the loader
(loader/, shields.py, registry.py) reads the rig files and the shield
library into the rig model (model.py); the board reader (boarddt.py,
board_edt.py, edt_build.py) reads the board's real devicetree; the
analyzer (analyzer/) decides whether the assembly is physically
possible; the emitter (emitter/) renders the overlay, the config sheet,
the expectations and the build glue. diag.py is the diagnostics core all
five report through.

`unimplemented.py`'s loud refusal (`rigc: not implemented: <what>`, exit
3) is still the channel for a path this tool does not handle, but it no
longer fires on any input the frozen corpus contains -- see that module's
own docstring for what remains behind it.

**Logging** (rigc-r45-brief.md Part B): every module gets its own
`logging.getLogger(__name__)`; this package's ROOT logger gets a
`NullHandler` here, the library convention -- without it, an unconfigured
logging tree falls through to Python's own `lastResort` handler, which
would print any WARNING-or-louder record straight to stderr and corrupt a
golden comparison. `cli.main()` is the ONE place that ever attaches a
REAL handler, and only when asked to: `-v`/`-vv` on the command line
(INFO/DEBUG) or, absent either flag, the environment naming a level
(`RIGC_LOG=<level>`) -- see `_configure_logging`'s own docstring for the
stderr-purity tradeoff either knob makes deliberately."""
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
