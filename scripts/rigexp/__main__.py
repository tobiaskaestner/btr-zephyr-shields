"""`python -m rigexp ...` entry point. See cli.py for the argument surface."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
