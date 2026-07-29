"""Unit: deps -- dependency data as a RETURNED/threaded value (ratified
ruling 3, rigc-r3-brief.md Sec 4): never a mutable accumulator passed in
and written to (rigexp's own `Depends` is exactly that banned shape,
mission brief Sec 6). `touch`/`union` are the two primitives every
recording point (registry.py, loader/library.py) composes upward with.
"""
from __future__ import annotations

import os

from rigc.deps import EMPTY, touch, union


def test_touch_normalizes_to_an_absolute_path() -> None:
    result = touch("relative/path.yaml")
    assert result == frozenset({os.path.abspath("relative/path.yaml")})


def test_touch_is_already_absolute_for_an_absolute_input() -> None:
    assert touch("/a/b.yaml") == frozenset({"/a/b.yaml"})


def test_union_of_nothing_is_empty() -> None:
    assert union() == EMPTY


def test_union_combines_and_dedups() -> None:
    a = touch("/a.yaml")
    b = touch("/b.yaml")
    assert union(a, b, a) == frozenset({"/a.yaml", "/b.yaml"})


def test_union_never_mutates_its_inputs() -> None:
    a = touch("/a.yaml")
    b = touch("/b.yaml")
    union(a, b)
    assert a == frozenset({"/a.yaml"})
    assert b == frozenset({"/b.yaml"})


def test_deps_value_is_immutable() -> None:
    """Deps is a frozenset -- a VALUE, with no `.add`/`.see` mutator (the
    structural difference from rigexp's own `Depends(set)`)."""
    d = touch("/a.yaml")
    assert not hasattr(d, "add")
    assert not hasattr(d, "see")
