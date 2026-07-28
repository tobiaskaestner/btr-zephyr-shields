"""Unit: loader — the R1 sliver.

Two contracts, both loader.py's own: content/fragment filename
construction (construct-don't-parse, the Q6 discipline: filenames derive
from the rig's own declared name: and a selected axis value, NEVER from
the folder the rig happens to live in), and the metadata/content key
split (board:/sockets: are rig.yml metadata; a content document carrying
either is rejected — asserted as DATA against synthetic documents: code,
severity, anchor file/line/key, ordering; the WORDING belongs to the
frozen goldens alone).

The anchor-line contract rides along with the split: an anchor carries
the VALUE node's start line (a scalar value sits on its key's line; a
nested mapping starts on the first entry's line, one below its key).
"""
from __future__ import annotations

from pathlib import Path

from rigc.diag import Diagnostic
from rigc.loader import (Val, content_file_name, fragment_file_name,
                         parse_marked, reject_metadata_keys)


# --------------------------------------------------- filename construction

def test_content_file_is_name_dot_yml() -> None:
    assert content_file_name("nucleo_datalogger") == "nucleo_datalogger.yml"


def test_fragment_file_is_name_underscore_value() -> None:
    assert fragment_file_name("pilot", "2") == "pilot_2.yml"


def test_fragment_normalizes_dotted_revision_to_underscores() -> None:
    """hwmv2's own normalization: 1.2 -> 1_2 in the CONSTRUCTED filename
    (the selected value itself stays the raw declared string)."""
    assert fragment_file_name("pilot", "1.2") == "pilot_1_2.yml"


def test_construction_uses_the_name_value_alone() -> None:
    """No hidden inputs: same name, same result -- there is no folder
    parameter to parse a name out of."""
    assert content_file_name("other") == "other.yml"
    assert fragment_file_name("other", "b") == "other_b.yml"


# ----------------------------------------------- metadata/content key split

def _doc(tmp_path: Path, text: str) -> Val:
    path = tmp_path / "content.yml"
    path.write_text(text)
    return parse_marked(str(path))


def test_clean_content_document_returns_no_diagnostics(tmp_path: Path) -> None:
    assert reject_metadata_keys(_doc(tmp_path, "instances: []\n")) == []


def test_board_key_is_rejected_anchored_at_its_value(tmp_path: Path) -> None:
    doc = _doc(tmp_path, "board: some_board/soc/rig\ninstances: []\n")
    diags = reject_metadata_keys(doc)
    assert len(diags) == 1
    d = diags[0]
    assert isinstance(d, Diagnostic)
    assert d.severity == "error"
    assert d.code == "lang-schema"
    assert len(d.refs) == 1
    ref = d.refs[0]
    assert ref.file == str(tmp_path / "content.yml")
    assert ref.line == 1               # scalar value: the key's own line
    assert ref.key == "board"


def test_sockets_key_anchors_at_the_value_node_line(tmp_path: Path) -> None:
    doc = _doc(tmp_path, "sockets:\n  ard: nucleo_ard\ninstances: []\n")
    diags = reject_metadata_keys(doc)
    assert len(diags) == 1
    ref = diags[0].refs[0]
    assert ref.line == 2               # nested mapping: first entry's line
    assert ref.key == "sockets"


def test_both_keys_reject_in_declaration_order(tmp_path: Path) -> None:
    doc = _doc(tmp_path,
               "sockets:\n  ard: x\nboard: some_board/soc/rig\n"
               "instances: []\n")
    diags = reject_metadata_keys(doc)
    assert [d.refs[0].key for d in diags] == ["board", "sockets"]
    assert all(d.code == "lang-schema" for d in diags)
