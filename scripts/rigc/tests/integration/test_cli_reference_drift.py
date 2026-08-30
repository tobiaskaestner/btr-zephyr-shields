"""Corpus-level property: doc/reference/commands.rst and the three real
argument parsers agree on what options exist, in BOTH directions.

The three surfaces the page documents:

  `rigc expand`          -- rigc.cli.build_parser(), the REAL parser,
                            imported and interrogated (it is importable
                            with no Zephyr tree present, which is the
                            whole reason cli.py keeps build_parser
                            public).
  `west build-rig`       -- scripts/west_commands/rig.py
  `west rigs`            -- scripts/west_commands/rigs.py, plus the
                            options `list_rigs.add_args()` contributes to
                            it (that ONE function, not the whole module:
                            `add_args_formatting`'s `--json`/
                            `--cmakeformat` belong to the standalone
                            resolver cmake calls, which `west rigs` does
                            not expose and this page does not document)

The two west surfaces are scanned as TEXT (a regex over `add_argument(`
calls) rather than imported: `rigs.py` locates the Zephyr script tree at
import time and `rig.py` subclasses upstream's own `west build` command,
so importing either drags a whole Zephyr checkout into a test whose
subject is a documentation page. The regex is crude in the same way
test_dts_vocabulary_drift.py's literal scan is crude, and sufficient for
the same reason: an option is declared exactly one way in these files.

Two directions, both checked:

  forward  -- every LONG option (`--thing`) any of the three parsers
              declares has its OWN ENTRY on the page: a definition-list
              term, or the first cell of a list-table row. A passing
              mention in someone else's prose does not count -- that is
              test_dts_vocabulary_drift.py's own hard-won rule (it scans
              heading text for exactly this reason), and it earns its
              keep here immediately: this page's prose names `--explain`
              and `--boards-for` while describing what they do to `-f`,
              so a whole-page scan would keep passing after either one's
              entry was renamed away.

  reverse  -- every `--thing` token ON the page (prose included, this
              time) is a real option of one of the three, or a member of
              the inherited-from-`west build` allowlist below. This is the
              direction that catches the actual historical failure mode:
              the page (like the help strings before it) describing a flag
              that was renamed or retired.

Short options are deliberately not checked. `-b`, `-s`, `-p`, `-f`, `-n`,
`-v` are one character and appear inside ordinary prose constantly; the
long form is the one an option is identified by here.

A pure file/text scan plus one in-process import -- no cmake, no
toolchain, no `@pytest.mark.build`.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from typing import Set

from harness import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.cli import build_parser  # noqa: E402

DOC_PAGE = REPO_ROOT / "doc" / "reference" / "commands.rst"
WEST_COMMANDS = (REPO_ROOT / "scripts" / "west_commands" / "rig.py",
                 REPO_ROOT / "scripts" / "west_commands" / "rigs.py")
LIST_RIGS = REPO_ROOT / "scripts" / "list_rigs.py"

#: The one `list_rigs.py` function `west rigs` actually calls on its own
#: parser. Scanned by name so that an option added to a DIFFERENT function
#: in that module -- one only cmake's resolver ever sees -- does not start
#: demanding a place on a page about human-facing commands.
LIST_RIGS_SHARED_FUNC = "add_args"

#: A long option as declared in an `add_argument("--thing", ...)` call,
#: either quoting style.
_DECL_RE = re.compile(r"""add_argument\(\s*["'](--[a-z][a-z0-9-]*)["']""")

#: The same, as it appears anywhere on the page: inside double backticks,
#: since this page writes every option as an inline literal.
_DOC_RE = re.compile(r"``(--[a-z][a-z0-9-]*)")

#: A list-table row whose first cell is an option: `   * - ``--thing```.
_DOC_CELL_RE = re.compile(r"^\s*\* - ``(--[a-z][a-z0-9-]*)")

#: A definition-list TERM: the option at the very start of a line. Not
#: sufficient on its own -- a paragraph that merely BEGINS with an option
#: literal looks identical, and this page has two of those ("``--explain``
#: alike — is either the name of..."), so `_documented_entries` also
#: requires the next line to be indented, which is what makes a term a
#: term in reST. Without that second condition the forward check silently
#: accepted a renamed entry, observed by mutating the page.
_DOC_TERM_RE = re.compile(r"^``(--[a-z][a-z0-9-]*)")

#: Options `west build-rig` INHERITS from upstream's `west build` parser
#: (it subclasses that command), documented by Zephyr rather than here.
#: The page names these where a rig build changes what they mean -- the
#: board becoming mandatory, `--shield` becoming an error -- so the
#: reverse check has to admit them without this repo declaring them.
#: Spelled out rather than pattern-matched: an unknown `--flag` on the
#: page should have to be added HERE, deliberately, with this comment in
#: view.
_INHERITED_FROM_WEST_BUILD = {"--board", "--source-dir", "--shield", "--pristine"}


def _declared_options() -> Set[str]:
    """Every long option the three real surfaces declare: rigc's own
    parser (interrogated), plus the two west commands and the shared
    resolver argument block (scanned). A fresh set the caller owns."""
    found: Set[str] = set()
    for action in _expand_parser()._actions:
        found.update(opt for opt in action.option_strings if opt.startswith("--"))
    for path in WEST_COMMANDS:
        found.update(_DECL_RE.findall(path.read_text()))
    found.update(_DECL_RE.findall(_shared_resolver_args()))
    found.discard("--help")
    return found


def _expand_parser() -> argparse.ArgumentParser:
    """The `expand` SUBparser out of rigc's own real parser. argparse
    offers no public route to a registered subparser, so this reaches for
    `_SubParsersAction.choices` -- the narrowest private touch available,
    and preferable to a second text scan: what this test wants is the
    surface argv is actually checked against, not the surface cli.py's
    source appears to declare."""
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices["expand"]
    raise AssertionError("rigc.cli.build_parser() registers no subcommands")


def _shared_resolver_args() -> str:
    """The source text of list_rigs.LIST_RIGS_SHARED_FUNC alone. An AST
    walk rather than a line-range slice, so moving the function inside its
    module cannot silently reduce this to an empty scan (which would make
    the forward check below pass by finding nothing)."""
    tree = ast.parse(LIST_RIGS.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == LIST_RIGS_SHARED_FUNC:
            segment = ast.get_source_segment(LIST_RIGS.read_text(), node)
            assert segment, f"could not recover the source of {LIST_RIGS_SHARED_FUNC}"
            return segment
    raise AssertionError(
        f"{LIST_RIGS.name} declares no {LIST_RIGS_SHARED_FUNC}() any more -- "
        "west rigs shares its parser arguments with something else now, and "
        "this test is scanning nothing")


def _documented_options() -> Set[str]:
    """Every option token anywhere on the page, prose included."""
    return set(_DOC_RE.findall(DOC_PAGE.read_text()))


def _documented_entries() -> Set[str]:
    """Every option with an ENTRY of its own on the page: a list-table
    row's first cell, or a definition-list term (an option at column 0
    whose next line is indented -- reST's own definition of one). A subset
    of `_documented_options()`."""
    found: Set[str] = set()
    lines = DOC_PAGE.read_text().splitlines()
    for i, line in enumerate(lines):
        cell = _DOC_CELL_RE.match(line)
        if cell:
            found.add(cell.group(1))
            continue
        term = _DOC_TERM_RE.match(line)
        if not term:
            continue
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if following.strip() and following[:1].isspace():
            found.add(term.group(1))
    return found


def test_commands_page_documents_something_at_all() -> None:
    """The negative control: an empty or renamed page would make the
    reverse check below trivially true. Both real parsers contribute a
    dozen options between them, so a page naming a handful is already
    wrong."""
    entries = _documented_entries()
    assert len(entries) >= 10, (
        f"doc/reference/commands.rst gives an entry to only {sorted(entries)}")


def test_cli_reference_forward_every_option_is_documented() -> None:
    """Every long option of `rigc expand`, `west build-rig` and
    `west rigs` has its own entry on doc/reference/commands.rst -- not
    merely a mention somewhere in its prose."""
    missing = sorted(_declared_options() - _documented_entries())
    assert not missing, (
        "option(s) declared by a real parser and absent from "
        f"doc/reference/commands.rst: {missing}")


def test_cli_reference_reverse_every_documented_option_is_real() -> None:
    """Every option the page names is one a real parser declares, or one
    inherited from `west build`. Catches a page that outlived a rename."""
    invented = sorted(_documented_options()
                      - _declared_options()
                      - _INHERITED_FROM_WEST_BUILD)
    assert not invented, (
        "doc/reference/commands.rst names option(s) no parser declares: "
        f"{invented}")
