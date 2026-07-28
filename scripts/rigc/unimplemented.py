"""The loud-refusal channel for functionality rigc does not have yet.

During the differential period (rigc-mission-brief.md Sec 4) most of the
frozen suite reaches paths rigc has not built. Those paths must fail
DISTINCTLY: `rigc: not implemented: <what>` on stderr and exit status 3 --
never exit 1 (the reject convention: a differential red must never be
mistakable for a wrong diagnostic), never a traceback, and never a silent
accept. Exit 2 stays argparse's own usage-error code, so the full exit
vocabulary is 0 accept / 1 rejected input / 2 usage error / 3 not
implemented (rigc-r1-brief.md Sec 1).

Raised anywhere inside the pipeline, caught ONCE in cli.main().
"""
from __future__ import annotations


class Unimplemented(Exception):
    """A path rigc has not implemented yet. `what` names the missing
    capability in one line; cli.main() renders it as
    `rigc: not implemented: <what>` and exits 3."""

    def __init__(self, what: str) -> None:
        self.what = what
        super().__init__(what)
