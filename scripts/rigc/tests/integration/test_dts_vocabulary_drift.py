"""Corpus-level property: the DTS reference pages
(doc/reference/shield-template.rst, doc/reference/board-socket.rst) and
scripts/rigc/'s own production code agree on the `shield,*`/`plug,*`/
`socket,*` vocabulary, in BOTH directions.

A reference page that silently falls behind the code is worse than
none -- a reader trusts it. This
is a law about the CORPUS (docs + production source, together) rather
than about any one module, so it lives here beside the other
corpus-level laws (test_singleton_identity_law.py,
test_golden_path_hygiene.py) rather than in a test_<module>.py mirroring
no single unit. It is a pure file/text scan -- no cmake, no toolchain, no
`@pytest.mark.build`.

Two directions, both checked:

  forward  -- every `shield,*`/`plug,*`/`socket,*` property STRING
              LITERAL found in scripts/rigc/'s PRODUCTION source (every
              *.py under scripts/rigc/, excluding anything under a
              `tests/` directory) must be documented (appear as a
              backtick-quoted token) on one of the two reference pages.

  reverse  -- every `shield,*`/`plug,*`/`socket,*`-shaped token that
              appears on either reference page must be a REAL one: a
              production literal, a real connector-type socket compatible
              (from `rigc.registry.load_types`), a bare bus-kind proxy
              (from `rigc.buskind.BUS_KINDS`), or a legally-shaped
              qualified name (`rigc.buskind.BUS_PROP_RE` /
              `CS_POOL_PROP_RE`) -- so a documented property that does
              not exist anywhere real is caught too.

Qualified families (`socket,<kind>-<role>`, `socket,<kind>-<role>-cs-pool`)
are never enumerated instance-by-instance -- scripts/rigc/'s own
`BUS_KINDS`/`BUS_PROP_RE`/`CS_POOL_PROP_RE` are imported and matched
against, exactly as board/project.py/shields.py/registry.py themselves do,
plus one placeholder-notation substring check per family (the docs must
spell the family's own shape at least once, in the same
`socket,<kind>-<role>[-cs-pool]` notation buskind.py's own comments use)
so a family is not silently un-mentioned entirely.

Scanning string literals is crude -- a regex over raw file text, not a
real Python/reST parse -- but sufficient and robust here: every property
name in this schema is exactly the shape `(shield|plug|socket),<ident>`
and never appears any other way,
confirmed while re-deriving this page's own vocabulary from the parsers.
"""

from __future__ import annotations

import re
import sys

from harness import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from rigc.buskind import BUS_KINDS, BUS_PROP_RE, CS_POOL_PROP_RE  # noqa: E402
from rigc.registry import load_types  # noqa: E402

PROD_ROOT = REPO_ROOT / "scripts" / "rigc"
DOC_DIR = REPO_ROOT / "doc" / "reference"
DOC_PAGES = (DOC_DIR / "shield-template.rst", DOC_DIR / "board-socket.rst")

#: A `shield,*`/`plug,*`/`socket,*` string literal, exactly as it appears
#: between a matching pair of quote characters in real source -- the
#: production-code side.
_LITERAL_RE = re.compile(r'''["']((?:shield|plug|socket),[A-Za-z][A-Za-z0-9_-]*)["']''')

#: The identical name shape, unanchored to quoting -- the reference-page
#: side, where a name is written as a backtick-quoted inline literal
#: rather than a Python string. Deliberately requires a real identifier
#: character right after the comma, so a PLACEHOLDER notation
#: (`socket,<kind>-<role>`, `socket,<type>`, `socket,<bus>`) -- which
#: starts with `<`, never a letter -- is never mistaken for a documented
#: concrete property.
_DOC_TOKEN_RE = re.compile(r'\b((?:shield|plug|socket),[A-Za-z][A-Za-z0-9_-]*)\b')

#: A reST section-title underline this project's own two pages use
#: (`=`/`-`/`~`, each repeated 4+ times) -- used to recover HEADING text
#: only, separately from body prose. A property that is only ever
#: mentioned in passing (a cross-reference from the OTHER page's body
#: text, say) does not count as having "an entry" of its own -- only a
#: property with a real heading does, which is what makes deleting one
#: property's own entry (heading + body) reliably fail the forward check
#: even when another page's prose still happens to name it in passing.
_HEADING_UNDERLINE_RE = re.compile(r'^([=\-~])\1{3,}$')


def _production_py_files():
    for path in sorted(PROD_ROOT.rglob("*.py")):
        if "tests" in path.relative_to(PROD_ROOT).parts:
            continue
        yield path


def _code_literals() -> set[str]:
    """Every `shield,*`/`plug,*`/`socket,*` string literal in scripts/rigc/'s
    own PRODUCTION source (never tests/) -- a fresh set the caller owns."""
    found: set[str] = set()
    for path in _production_py_files():
        found.update(_LITERAL_RE.findall(path.read_text()))
    return found


def _doc_text() -> str:
    return "\n".join(p.read_text() for p in DOC_PAGES)


def _heading_text() -> str:
    """Every section-heading TITLE line (never body text) across both
    reference pages, joined -- one line per real heading, regardless of
    which page it lives on or how many properties one combined heading
    names."""
    headings = []
    for page in DOC_PAGES:
        lines = page.read_text().splitlines()
        for i in range(1, len(lines)):
            if _HEADING_UNDERLINE_RE.match(lines[i]) and lines[i - 1].strip():
                headings.append(lines[i - 1])
    return "\n".join(headings)


def _doc_tokens(text: str) -> set[str]:
    return set(_DOC_TOKEN_RE.findall(text))


def _known_qualified(token: str, connector_types: set[str]) -> bool:
    """Whether `token` is a legitimately-shaped qualified/pattern member --
    a real connector-type socket compatible, a bare bus-kind proxy, or a
    name matching one of buskind.py's own two qualified-family regexes --
    rather than a literal this test enumerates itself."""
    if token in {f"socket,{name}" for name in connector_types}:
        return True
    if token in {f"socket,{kind}" for kind in BUS_KINDS}:
        return True
    if BUS_PROP_RE.fullmatch(token):
        return True
    if CS_POOL_PROP_RE.fullmatch(token):
        return True
    return False


def test_dts_vocabulary_forward_every_code_literal_is_documented() -> None:
    """Every `shield,*`/`plug,*`/`socket,*` literal scripts/rigc/'s own
    production code reads or writes has its own dedicated HEADING entry on
    one of the two reference pages -- not merely a passing mention in the
    other page's body prose (a cross-reference), which is why this checks
    heading text specifically rather than the whole page."""
    code = _code_literals()
    documented = _doc_tokens(_heading_text())
    missing = sorted(code - documented)
    assert not missing, (
        "propert(y/ies) used by scripts/rigc/ but with no dedicated entry "
        f"on doc/reference/{{shield-template,board-socket}}.rst: {missing}"
    )


def test_dts_vocabulary_reverse_every_documented_property_is_real() -> None:
    """Every `shield,*`/`plug,*`/`socket,*`-shaped token on either
    reference page is a real one -- a production literal, a registered
    connector-type compatible, a bare bus-kind proxy, or a legally-shaped
    qualified name -- never an invented property."""
    code = _code_literals()
    types, _deps = load_types()
    documented = _doc_tokens(_doc_text())
    invented = sorted(
        tok for tok in documented if tok not in code and not _known_qualified(tok, set(types))
    )
    assert not invented, (
        "doc/reference/{shield-template,board-socket}.rst documents "
        f"propert(y/ies) that do not exist anywhere real: {invented}"
    )


def test_dts_vocabulary_qualified_families_are_documented_by_pattern() -> None:
    """The two qualified families (`socket,<kind>-<role>`,
    `socket,<kind>-<role>-cs-pool`) are never enumerable -- every
    concrete instance is legal-by-pattern, not by a fixed list -- so
    what's checked here is that each family's own SHAPE is actually
    spelled out, with its own heading, on the reference pages (the
    placeholder notation buskind.py's own comments use) -- not any
    particular instance of it, and not merely a passing body-text
    mention."""
    headings = _heading_text()
    assert "socket,<kind>-<role>-cs-pool" in headings, (
        "the socket,<kind>-<role>-cs-pool qualified CS-pool family has no "
        "dedicated heading on either reference page"
    )
    assert "socket,<kind>-<role>" in headings, (
        "the socket,<kind>-<role> qualified bus-proxy family has no "
        "dedicated heading on either reference page"
    )
    documented = _doc_tokens(headings)
    for kind in BUS_KINDS:
        bare = f"socket,{kind}"
        assert bare in documented, (
            f"bare bus proxy '{bare}' (rigc.buskind.BUS_KINDS) has no "
            "dedicated heading on either reference page"
        )


# ------------------------------------------------- the retired plug spelling
# The vocabulary scan above cannot see this one: `shield,plugs` is a real
# production literal either way, so a page still showing it on the TEMPLATE
# node passes every check above while teaching a form the loader refuses.
# This is the law that catches that, over
# EVERY doc page rather than the two reference ones -- a tutorial's example
# is the copy a reader actually pastes.

_DEVICETREE_BLOCK = re.compile(
    r"^([ \t]*)\.\. code-block:: devicetree[ \t]*\n(.*?)(?=\n\1\S|\Z)", re.S | re.M
)


def _devicetree_blocks():
    """(page, block text) for every `.. code-block:: devicetree` under
    doc/, tutorials and how-tos included."""
    for page in sorted((REPO_ROOT / "doc").rglob("*.rst")):
        if "_build" in page.parts:
            continue
        for m in _DEVICETREE_BLOCK.finditer(page.read_text()):
            yield page, m.group(2)


def test_no_doc_example_shows_the_retired_template_level_shield_plugs() -> None:
    """A plug declares its own connector type, so every documented
    `shield,plugs` sits beside a `compatible = "shield,plug"` in the same
    example. A block naming the property without the compatible is either
    the retired template-level spelling or an excerpt that cannot be
    pasted -- both mislead the reader the same way."""
    offenders = [
        str(page.relative_to(REPO_ROOT))
        for page, block in _devicetree_blocks()
        if "shield,plugs" in block and 'compatible = "shield,plug"' not in block
    ]
    assert offenders == [], (
        "doc example(s) show shield,plugs without the plug node's own "
        f"compatible = \"shield,plug\": {offenders}"
    )


def test_no_doc_example_declares_cells_on_a_plug_node() -> None:
    """And the cells ruling, in the same place: a plug node declares no
    `#<fn>-cells` (`lang-shield-plug-cells`). A jumper's own
    `#gpio-cells = <1>` is fine and must stay documented, so this looks
    only inside the plug node's own braces."""
    cells = ("#gpio-cells", "#pwm-cells", "#io-channel-cells")
    offenders = []
    for page, block in _devicetree_blocks():
        lines = block.split("\n")
        for i, line in enumerate(lines):
            if 'compatible = "shield,plug"' not in line:
                continue
            # walk back to the node's opening brace, then forward to its close
            start = next(j for j in range(i, -1, -1) if "{" in lines[j])
            depth = 0
            for j in range(start, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if any(c in lines[j] for c in cells):
                    offenders.append(f"{page.relative_to(REPO_ROOT)}: {lines[j].strip()}")
                if depth <= 0 and j > start:
                    break
    assert offenders == [], f"doc example(s) declare cell counts on a plug node: {offenders}"


def test_the_devicetree_block_scan_finds_something() -> None:
    """The control for the two laws above: both assert an EMPTY offender
    list, so a block regex that matched nothing would let them pass
    vacuously -- run the mutation; do
    not reason about it. Fixed floors, deliberately well under the real
    counts so ordinary doc growth never trips them."""
    blocks = list(_devicetree_blocks())
    assert len(blocks) >= 15, f"only {len(blocks)} devicetree blocks found"
    pages = {page for page, _ in blocks}
    assert len(pages) >= 4, f"only {len(pages)} pages carry one"
    with_plug = [b for _, b in blocks if 'compatible = "shield,plug"' in b]
    assert len(with_plug) >= 3, (
        f"only {len(with_plug)} block(s) show a plug node -- the cells law "
        "has nothing to look inside"
    )
