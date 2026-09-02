"""Corpus-level property: no frozen golden carries a machine-specific path.

A `zephyr.dts` golden's provenance comments name the build directory the
file was generated in. `harness.normalize_dts_provenance` rewrites that
to `<RIGC_BUILD>/…`, but its regex matches only pytest's DEFAULT basetemp
shape (`../../tmp/pytest-of-<user>/pytest-<n>/<name>/build/rig/…`). A
golden produced under ANY other build directory -- a hand-run
a hand-run `west build -d`, a custom `--basetemp`, an agent's scratch dir --
keeps that directory's absolute path verbatim.

Nothing else catches it. `dts_equiv.py` compares STRUCTURE and ignores
comments entirely, so such a golden passes its own test forever while
carrying a path that exists on exactly one machine, in one session. Two
goldens (`quail_can_span`, `quail_eth_span`) were committed that way
before this test existed, each naming a different throwaway build dir.

This is a law about the CORPUS rather than about any one module, so it
lives here beside the other corpus-level laws rather than in a
`test_<module>.py` mirroring a production unit -- the same reason
`test_singleton_identity_law.py` is not named after a module either.
"""
from pathlib import Path

GOLDENS_DIR = Path(__file__).resolve().parents[1] / "goldens"

#: Fragments that can only come from a real filesystem path on somebody's
#: machine. `<RIGC_BUILD>` and `<REPO_ROOT>` are the sanctioned
#: placeholders; a repo-relative path (`btr-shields/boards/…`,
#: `zephyr/dts/…`) is legitimate provenance and stays.
_FORBIDDEN = (
    "/tmp/",            # any throwaway build dir, however it was made
    "pytest-of-",       # an unnormalized pytest basetemp
    "/home/",           # a home-directory absolute path
    "scratchpad",       # an agent scratch dir
)


def _offending_lines(path: Path) -> list[tuple[int, str]]:
    """Every (1-based line number, line) in `path` carrying a forbidden
    fragment. Returns a fresh list the caller owns; empty means clean."""
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        if any(fragment in line for fragment in _FORBIDDEN):
            hits.append((n, line.strip()))
    return hits


def test_no_golden_carries_a_machine_specific_path() -> None:
    """Every frozen golden, of every kind -- not just `zephyr.dts`, since
    `stderr.txt` and `context.cmake` quote paths too."""
    offenders = {}
    for golden in sorted(GOLDENS_DIR.rglob("*")):
        if not golden.is_file():
            continue
        hits = _offending_lines(golden)
        if hits:
            offenders[golden.relative_to(GOLDENS_DIR)] = hits

    assert not offenders, (
        "golden(s) carry a machine-specific path -- regenerate them under "
        "pytest's DEFAULT basetemp so harness.normalize_dts_provenance "
        "rewrites the build dir to <RIGC_BUILD>, or normalize by hand:\n"
        + "\n".join(
            f"  {name}:{n}: {line}"
            for name, hits in sorted(offenders.items())
            for n, line in hits[:3]))
