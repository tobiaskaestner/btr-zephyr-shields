"""`python -m rigc ...` entry point — deliberate hard failure until R1
lands the real CLI. Exit status 1 (POSIX has no -1; the wait status would
wrap to 255 and read like a crash rather than a refusal)."""
from __future__ import annotations

import sys

if __name__ == "__main__":
    print("rigc: not implemented yet — this stub exists so the "
          "RIG_EXPAND_COMPILE differential harness fails loudly instead of "
          "raising ModuleNotFoundError (rigc-mission-brief.md, R0/R1)",
          file=sys.stderr)
    sys.exit(1)
