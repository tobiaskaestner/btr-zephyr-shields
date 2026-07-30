"""Unit: emitter (the package's own `__init__.py`) -- `emit()`'s artifact
SET as a function of input, and the ONE writer. This module's subject is
the ASSEMBLY, not any one artifact's content (those are covered where
they are named: test_overlay.py, test_sheet.py, test_expectations.py,
test_context.py).
"""
from __future__ import annotations

from pathlib import Path

from rigc.analyzer import Solved
from rigc.emitter import emit, write_artifacts
from rigc.model import BoardSocket, ConnectorType, Device, Instance, Rig, Shield


def test_rig_gen_includes_dtsi_present_iff_dt_includes_declared() -> None:
    with_includes = Rig(name="r", board="b", instances=[],
                        dt_includes=["dt-bindings/input/input-event-codes.h"])
    without = Rig(name="r", board="b", instances=[])

    out_with = emit(with_includes, Solved(), {}, workdir="/does-not-matter")
    out_without = emit(without, Solved(), {}, workdir="/does-not-matter")

    assert "rig-gen-includes.dtsi" in out_with
    assert "rig-gen-includes.dtsi" not in out_without


def test_rig_gen_includes_dtsi_keeps_declaration_order() -> None:
    """The PRODUCER side of the ordered-header contract. dt-includes: order
    is the rig author's, and cpp include order can matter, so the emitter
    must not sort or otherwise reorder. Asserted on the exact decoded text,
    which pins the order, the angle-bracket form and the banner together --
    the comparator's own ordering guard is on the consuming side and cannot
    notice the emitter losing this."""
    # Three headers whose declared order differs from BOTH ascending and
    # descending sort order, so any reordering the emitter might introduce
    # changes the rendered text. Two names alone are not enough: a pair can
    # coincide with one sort direction and make the assertion vacuous.
    rig = Rig(name="r", board="b", instances=[],
              dt_includes=["mmm/mid.h", "aaa/first.h", "zzz/last.h"])

    out = emit(rig, Solved(), {}, workdir="/does-not-matter")
    text = out["rig-gen-includes.dtsi"].decode("utf-8")

    assert text.splitlines()[2:5] == [
        "#include <mmm/mid.h>",
        "#include <aaa/first.h>",
        "#include <zzz/last.h>"], text


def test_rig_gen_conf_is_never_emitted() -> None:
    rig = Rig(name="r", board="b", instances=[])
    out = emit(rig, Solved(), {}, workdir="/does-not-matter")
    assert "rig-gen.conf" not in out


def test_expectations_yml_is_always_emitted() -> None:
    rig = Rig(name="r", board="b", instances=[])
    out = emit(rig, Solved(), {}, workdir="/does-not-matter")
    assert "expectations.yml" in out


def test_every_artifact_is_utf8_encoded_bytes() -> None:
    """config-sheet.md's own banner carries an em dash -- a real
    multi-byte UTF-8 decision, not a formality (rigc-r5-brief.md Sec 1's
    ratified reading of "artifacts as {filename: bytes}")."""
    rig = Rig(name="r", board="b", instances=[])
    out = emit(rig, Solved(), {}, workdir="/does-not-matter")

    for name, content in out.items():
        assert isinstance(content, bytes), name
    assert "—".encode("utf-8") in out["config-sheet.md"]


def test_emit_is_deterministic_under_a_shuffled_instance_order() -> None:
    ctype = ConnectorType(name="t", positions={}, index2name={}, bus_proxies=[],
                          stackable=False, cs_pool=[])

    def make(order: list[str]) -> dict:
        insts = []
        sockets = {}
        for name in order:
            dev = Device(name="d", label="d", compatible=None, bus=None,
                        group=None, reg=None, addr_from=None, cs_position=None)
            shield = Shield(name="sh", label="sh", plugs="t", devices=[dev])
            insts.append(Instance(name=name, shield=shield, socket="sock"))
            sockets[name] = BoardSocket(label="sock", path="/s", type_name="t",
                                        gpio_map={}, buses={}, cs_pool=None)
        rig = Rig(name="r", board="b", instances=insts)
        s = Solved(sockets=sockets)
        return emit(rig, s, {"t": ctype}, workdir="/does-not-matter")

    assert make(["alpha", "bravo"]) == make(["bravo", "alpha"])


def test_write_artifacts_writes_every_entry_in_binary_mode(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    write_artifacts(str(out_dir), {"a.txt": b"hello", "b.bin": b"\x00\x01\xff"})

    assert (out_dir / "a.txt").read_bytes() == b"hello"
    assert (out_dir / "b.bin").read_bytes() == b"\x00\x01\xff"


def test_write_artifacts_creates_out_dir_if_missing(tmp_path: Path) -> None:
    out_dir = tmp_path / "nested" / "out"
    write_artifacts(str(out_dir), {"f": b"x"})
    assert out_dir.is_dir()
    assert (out_dir / "f").read_bytes() == b"x"
