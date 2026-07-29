"""Allocation ordering: R18's `_key`, a named unit contract (rigc-r4-brief.md
"Allocation order is R18's `_key` ... never rig-file declaration order").
`allocation_key` needs only a plain Instance/Device pair -- no Shield/Rig/
Board -- so ordering is asserted directly against constructed values, not
a scenario."""
from __future__ import annotations

from rigc.analyzer.ordering import allocation_key
from rigc.model import Device, Instance, Shield


def _inst(name: str, socket: str) -> Instance:
    return Instance(name=name, shield=Shield(name="s", label="s", plugs="t"),
                    socket=socket)


def _dev(name: str) -> Device:
    return Device(name=name, label=name, compatible=None, bus=None,
                 group=None, reg=None, addr_from=None, cs_position=None)


def test_key_is_socket_then_instance_then_device() -> None:
    assert allocation_key(_inst("i", "sock"), _dev("d")) == ("sock", "i", "d")


def test_ordering_is_by_socket_first_regardless_of_declaration_order() -> None:
    """Sorting by allocation_key must ignore the order members are handed
    in -- the stable contract is socket, then instance, then device."""
    late_socket = (_inst("a_inst", "z_sock"), _dev("d"))
    early_socket = (_inst("z_inst", "a_sock"), _dev("d"))
    members = [late_socket, early_socket]

    ordered = sorted(members, key=lambda m: allocation_key(m[0], m[1]))

    assert ordered == [early_socket, late_socket]


def test_ordering_breaks_ties_by_instance_name_then_device_name() -> None:
    same_socket = "sock"
    members = [
        (_inst("b", same_socket), _dev("y")),
        (_inst("b", same_socket), _dev("x")),
        (_inst("a", same_socket), _dev("z")),
    ]

    ordered = sorted(members, key=lambda m: allocation_key(m[0], m[1]))

    assert [(i.name, d.name) for i, d in ordered] == [
        ("a", "z"), ("b", "x"), ("b", "y")]


def test_ordering_never_reads_rig_file_declaration_order() -> None:
    """The key is a pure function of (socket, instance name, device name)
    alone -- it carries no notion of "the order instances appeared in the
    rig file", so two members swapped in declaration order but identical
    in these three fields are genuinely indistinguishable (stable sort
    keeps their relative order, which is the ONLY thing declaration order
    could still influence -- never which one allocates first when the
    keys differ)."""
    a = (_inst("same", "sock"), _dev("dev"))
    b = (_inst("same", "sock"), _dev("dev"))
    assert allocation_key(*a) == allocation_key(*b)
