#!/usr/bin/env python3
"""Structural devicetree equivalence check (rigs R2).

Compares two `zephyr.dts` files for EQUIVALENCE, not byte-identity: labels,
phandle integer identities, and node/property ordering are all irrelevant;
what must match is the structure — each node (keyed by PATH) and its
properties, with phandle/path references resolved to their TARGET node PATH.

  python3 dts_equiv.py <golden.dts> <candidate.dts>

Exit 0 if equivalent (modulo the excluded root node), 1 if differences remain.
Reuses zephyr's dtlib; point PYTHONPATH at
zephyr-rigs/scripts/dts/python-devicetree/src or rely on the sys.path shim
below.

NOTE ON LOCATION: this lives in the source tree (btr-shields/scripts/), NOT in
a `west build -d` output directory — build dirs are wiped by `-p always`.
"""
from __future__ import annotations

import os
import sys

# Locate dtlib without requiring the caller to set PYTHONPATH.
_DTLIB_SRC = "/wrk/z/ws-up/zephyr-rigs/scripts/dts/python-devicetree/src"
if _DTLIB_SRC not in sys.path:
    sys.path.insert(0, _DTLIB_SRC)

from devicetree.dtlib import DT, Type, _MarkerType  # noqa: E402


def _words(value: bytes):
    for i in range(0, len(value) - len(value) % 4, 4):
        yield i, int.from_bytes(value[i:i + 4], "big")


def canon_prop(prop, dt):
    """A label/phandle-spelling-independent canonical value for one property.

    References (phandle or path) resolve to the target node's PATH, so a
    property pointing at the same physical node compares equal regardless of
    which label or phandle number was used to reach it.
    """
    t = prop.type
    if t is Type.EMPTY:
        return ("empty",)
    if t in (Type.NUM, Type.NUMS):
        return ("nums", tuple(prop.to_nums()))
    if t is Type.BYTES:
        return ("bytes", prop.to_bytes())
    if t is Type.STRING:
        return ("str", prop.to_string())
    if t is Type.STRINGS:
        return ("strs", tuple(prop.to_strings()))
    if t is Type.PATH:
        return ("ref", prop.to_path().path)
    if t is Type.PHANDLE:
        return ("refs", (prop.to_node().path,))
    if t is Type.PHANDLES:
        return ("refs", tuple(n.path for n in prop.to_nodes()))
    # PHANDLES_AND_NUMS / COMPOUND: walk the raw cells, resolving the
    # word-offsets that carry a phandle to their target node PATH.
    phandle_offsets = {m[0] for m in prop._markers
                       if m[1] == _MarkerType.PHANDLE}
    seq = []
    for off, word in _words(prop.value):
        if off in phandle_offsets:
            seq.append(("ref", dt.phandle2node[word].path))
        else:
            seq.append(word)
    return ("mix", tuple(seq))


def node_props(node, dt):
    # `phandle` is bookkeeping (the integer identity), never structural.
    return {name: canon_prop(p, dt)
            for name, p in node.props.items() if name != "phandle"}


def index(dt):
    # Key every node by path, except the root (its name/model/compatible
    # legitimately differ for a cloned board id).
    return {n.path: n for n in dt.node_iter() if n.path != "/"}


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    golden, cand = DT(argv[1]), DT(argv[2])
    g, c = index(golden), index(cand)

    only_g = sorted(set(g) - set(c))
    only_c = sorted(set(c) - set(g))
    prop_diffs = []
    for path in sorted(set(g) & set(c)):
        gp, cp = node_props(g[path], golden), node_props(c[path], cand)
        for name in sorted(set(gp) | set(cp)):
            if gp.get(name) != cp.get(name):
                prop_diffs.append((path, name, gp.get(name), cp.get(name)))

    matched = len(set(g) & set(c)) - len({p for p, *_ in prop_diffs})
    print(f"golden nodes: {len(g)}   candidate nodes: {len(c)}")
    print(f"nodes present in both with IDENTICAL properties: {matched}")
    print(f"nodes only in golden (candidate is missing): {len(only_g)}")
    for p in only_g:
        print(f"    - {p}")
    print(f"nodes only in candidate (added by the rig): {len(only_c)}")
    for p in only_c:
        print(f"    + {p}")
    print(f"shared nodes with property differences: "
          f"{len({p for p, *_ in prop_diffs})}")
    for path, name, gv, cv in prop_diffs:
        print(f"    ~ {path}  '{name}'\n        golden:    {gv}\n"
              f"        candidate: {cv}")

    equivalent = not only_g and not only_c and not prop_diffs
    print("\nVERDICT:", "EQUIVALENT" if equivalent else
          "DIFFERENCES REMAIN (see above; some may be justified divergences)")
    return 0 if equivalent else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
