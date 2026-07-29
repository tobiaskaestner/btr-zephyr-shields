"""Unit: loader.documents -- the document model.

Three contracts live here: content/fragment filename CONSTRUCTION
(construct-don't-parse, the Q6 discipline: filenames derive from the
rig's own declared name: and a selected axis value, NEVER from the
folder the rig happens to live in), the metadata/content key split
(board:/sockets: are rig.yml metadata; a content document carrying
either is rejected), and require()'s missing-key structure (a stable
contract -- code, severity, anchor -- even though the wording itself is
a no-golden diagnostic, hand-differentialed separately, not duplicated
here).

The anchor-line contract rides along: an anchor carries the VALUE node's
start line (a scalar value sits on its key's line; a nested mapping
starts on the first entry's line, one below its key).
"""
from __future__ import annotations

from pathlib import Path

from rigc.diag import Diagnostic
from rigc.loader.documents import (Val, content_file_name, parse_marked,
                                   reject_metadata_keys, require)


def _doc(tmp_path: Path, text: str, name: str = "content.yml") -> Val:
    path = tmp_path / name
    path.write_text(text)
    return parse_marked(str(path))


# --------------------------------------------------- filename construction

def test_content_file_is_name_dot_yml() -> None:
    assert content_file_name("nucleo_datalogger") == "nucleo_datalogger.yml"


def test_construction_uses_the_name_value_alone() -> None:
    """No hidden inputs: same name, same result -- there is no folder
    parameter to parse a name out of. (Fragment-stem construction lives
    in axes.py -- the hwmv2 seam -- and is tested in test_axes.py.)"""
    assert content_file_name("other") == "other.yml"


# ----------------------------------------------- metadata/content key split

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
    """Ordering contract: board: before sockets:, regardless of the
    document's own key order -- rigexp's own fixed scan order."""
    doc = _doc(tmp_path,
               "sockets:\n  ard: x\nboard: some_board/soc/rig\n"
               "instances: []\n")
    diags = reject_metadata_keys(doc)
    assert [d.refs[0].key for d in diags] == ["board", "sockets"]
    assert all(d.code == "lang-schema" for d in diags)


# ------------------------------------------------------------- require()

def test_require_present_key_returns_it_with_no_diagnostics(tmp_path: Path) -> None:
    doc = _doc(tmp_path, "name: x\n")
    val, diags = require(doc, "name", "rig")
    assert val is not None and val.value == "x"
    assert diags == []


def test_require_missing_key_is_a_lang_schema_error_anchored_at_container(
        tmp_path: Path) -> None:
    doc = _doc(tmp_path, "other: 1\n")
    val, diags = require(doc, "name", "rig")
    assert val is None
    assert len(diags) == 1
    d = diags[0]
    assert d.severity == "error"
    assert d.code == "lang-schema"
    assert d.refs == (doc.src,)        # anchored at the CONTAINER, not a key
