"""Meta: the test-tree conventions, enforced structurally.

The one test module whose subject is not a production unit but the tests
tree itself (recorded exemption in _META_MODULES below). It enforces:

  - every test module lives under exactly one of tests/unit/ or
    tests/integration/;
  - unit test modules NAME THEIR UNIT (Tobi's ruling, 2026-07-28): a
    test_<name>.py directly under tests/unit/ must name a python module
    of the rigc package (or the tests' own conftest); when one unit needs
    several test modules they live in a sub-folder tests/unit/<name>/
    that itself names the unit. Tests may USE other units, but the named
    unit is the subject;
  - no module under tests/unit/ imports subprocess (the structural proxy
    for "a unit test uses NO subprocess");
  - no pytest markers anywhere in rigc's tree -- the directory IS the
    classification;
  - no module-scope environment lookup of the Zephyr tree variable
    anywhere in the package or its tests (the dtsio.py:27 collection
    trap, designed out: pytest imports every module before deselection).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List

import rigc

RIGC_DIR = Path(rigc.__file__).resolve().parent
TESTS_DIR = RIGC_DIR / "tests"

#: Test modules whose subject is the tests tree / conventions themselves,
#: not a production unit -- the recorded exemption from unit naming.
_META_MODULES = {"test_layer_discipline"}


def _python_files(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_every_test_module_is_layer_classified() -> None:
    offenders = []
    for path in _python_files(RIGC_DIR):
        if not path.name.startswith("test_"):
            continue
        rel = path.relative_to(RIGC_DIR)
        if rel.parts[:2] not in (("tests", "unit"), ("tests", "integration")):
            offenders.append(str(rel))
    assert not offenders, (
        "test modules outside tests/unit/ and tests/integration/ "
        f"(the directory IS the layer classification): {offenders}")


def _top_level_units() -> set[str]:
    """Every valid unit NAME directly under the rigc package: a bare
    module (cli.py -> "cli") or a SUB-PACKAGE (loader/ -> "loader",
    R2's package-shaped loader) -- either way, a name a test module or a
    tests/unit/<name>/ sub-folder may claim as its subject."""
    units = {p.stem for p in RIGC_DIR.glob("*.py")}
    units |= {p.name for p in RIGC_DIR.iterdir()
             if p.is_dir() and (p / "__init__.py").is_file()
             and p.name != "tests"}
    return units | {"conftest"}


def test_unit_test_modules_name_their_unit() -> None:
    """test_<name>.py names a rigc module (or conftest); a sub-folder
    under tests/unit/ names the unit its modules share -- a PACKAGE
    (e.g. loader/) is as valid a unit name here as a bare module."""
    units = _top_level_units()
    offenders = []
    for path in _python_files(TESTS_DIR / "unit"):
        if not path.name.startswith("test_"):
            continue
        rel = path.relative_to(TESTS_DIR / "unit")
        if len(rel.parts) == 1:                       # directly under unit/
            subject = path.stem.removeprefix("test_")
            if subject not in units and path.stem not in _META_MODULES:
                offenders.append(f"{rel}: no unit named '{subject}'")
        else:                                         # unit/<subject>/...
            subject = rel.parts[0]
            if subject not in units:
                offenders.append(f"{rel}: no unit named '{subject}'")
    assert not offenders, (
        "unit test modules must name the unit under test "
        f"(test_<module>.py, or a tests/unit/<module>/ sub-folder): "
        f"{offenders}")


def test_unit_modules_import_no_subprocess() -> None:
    offenders = []
    for path in _python_files(TESTS_DIR / "unit"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "subprocess" or n.startswith("subprocess.")
                   for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "tests/unit/ modules importing subprocess (reaching code through "
        f"the CLI front door is integration by definition): {offenders}")


def test_no_pytest_markers_under_tests_unit() -> None:
    """Markers are banned in the UNIT tree, where the directory is the
    classification. The integration tree keeps exactly one marker, `build`,
    because the fast gate selects on it (`pytest -m "not build"`) -- a
    layer marker there would be the second mechanism for a fact the
    directory already states, which is what made the two enforcement
    regimes contradict each other before they were split this way."""
    offenders = []
    for path in _python_files(TESTS_DIR / "unit"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "mark"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "pytest"):
                offenders.append(f"{path.relative_to(RIGC_DIR)}:{node.lineno}")
    assert not offenders, (
        "pytest markers found under tests/unit/ -- there the directory is "
        f"the classification, markers are banned: {offenders}")


def _import_time_constants(tree: ast.Module) -> Iterator[ast.Constant]:
    """Constants evaluated at import time: module body and class bodies,
    with function/method bodies skipped (code inside them runs only when
    called) and bare-string docstring statements skipped."""

    def visit(body: List[ast.stmt]) -> Iterator[ast.Constant]:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(stmt, ast.ClassDef):
                yield from visit(stmt.body)
                continue
            if (isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)):
                continue               # docstring
            for node in ast.walk(stmt):
                if isinstance(node, ast.Constant):
                    yield node

    return visit(tree.body)


def test_no_module_scope_zephyr_tree_lookup() -> None:
    forbidden = "ZEPHYR" + "_BASE"     # split so this file's own module
    offenders = []                     # scope never carries the literal
    for path in _python_files(RIGC_DIR):
        tree = ast.parse(path.read_text(), filename=str(path))
        for const in _import_time_constants(tree):
            if const.value == forbidden:
                offenders.append(f"{path.relative_to(RIGC_DIR)}:{const.lineno}")
    assert not offenders, (
        f"module-scope {forbidden} reference (breaks collection for "
        f"selections that never run it -- keep lookups inside functions): "
        f"{offenders}")
