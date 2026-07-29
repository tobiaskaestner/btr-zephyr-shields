"""Dependency data: the real source-tree files one load actually touched
(rig.yml, its content file, `.shield` templates + their cpp-included
files, connector bindings, index headers) -- eventually the RIG_DEPENDS
handoff, but that serialization is an emitter-slice concern (rigc-r3-
brief.md Sec 4, out of scope here).

Ratified ruling 3: dependency data is a RETURNED/threaded VALUE, never a
mutable accumulator (rigexp's own `Depends` is a mutable `set` passed down
and written into by `.see()` -- exactly the banned shape, mission brief
Sec 6). Every function that opens a real file returns the paths it
touched as part of its own result; callers compose them upward with
`union`, the same way diagnostics compose upward as list concatenation.
"""
from __future__ import annotations

import os
from typing import FrozenSet

#: An immutable set of absolute paths -- deliberately a VALUE type (no
#: `.add`/`.see` mutator), so the only way to grow one is to build a NEW
#: value with `touch`/`union`.
Deps = FrozenSet[str]

EMPTY: Deps = frozenset()


def touch(path: str) -> Deps:
    """One real file this load touched, normalized to absolute -- the
    smallest Deps value, composed upward by the caller exactly like a
    single Diagnostic is."""
    return frozenset((os.path.abspath(path),))


def union(*deps: Deps) -> Deps:
    """Compose several Deps values into one -- the dependency-data
    analogue of concatenating diagnostic lists."""
    if not deps:
        return EMPTY
    result: set = set()
    for d in deps:
        result |= d
    return frozenset(result)
