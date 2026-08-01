"""rigc -- the rig compiler, built from scratch against rigexp's frozen
golden corpus (claude/rigs/rigc-mission-brief.md; rigexp is the FROZEN
blueprint, the goldens are the specification).

R2 state: the CLI front door (cli.py), the diagnostics core (diag.py),
the rig model (model.py), and the loader PROPER (loader/ -- rig.yml
metadata, qualifier axes with the hwmv2 seam, board/SocketBinding
resolution, the required content file, fragment discovery, and the V1b
delta engine). Everything needing the shield library, board devicetree,
or headers stays a loud, distinct refusal -- `rigc: not implemented:
<what>`, exit 3 (unimplemented.py) -- so a differential run under
RIG_EXPAND_COMPILE=rigc is never mistakable for a wrong diagnostic or a
silent fallback to rigexp.

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
