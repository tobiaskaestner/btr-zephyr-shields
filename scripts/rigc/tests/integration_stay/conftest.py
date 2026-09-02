"""pytest wants a conftest.py in this directory too. The corpus-tethered
tests here need harness.py's generic plumbing (path discovery, the
expander subprocess runner, normalization, the freeze/assert primitives),
which still lives in the sibling tests/integration/ directory -- put that
directory on sys.path so `import harness` (and corpus.py's own `from
harness import ...`) resolves.

At actual-migration time (when the mechanics move out to bridle and
integration/ leaves this repo), this stay side vendors its own copy of
harness.py instead of reaching across to a sibling directory that will no
longer exist -- this sys.path insert is a placeholder for that copy, not
a long-term arrangement.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))
