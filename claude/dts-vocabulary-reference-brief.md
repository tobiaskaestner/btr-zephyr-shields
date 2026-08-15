# The DTS vocabulary reference — `shield,*`, `plug,*`, `socket,*`

**Status:** briefed 2026-08-15, ready to dispatch. Discharges item 29
§8's debt, scoped up by Tobi 2026-08-15 to "the thing the tree needs
now" rather than the minimum owed page.

Slice **1 of 3**. Later slices (NOT here): the YAML layer
(`rig-file.rst` + `promotion.rst`), then the diagnostic catalogue
(42 codes).

## 1. The gap

`doc/reference/` contains exactly one page, `glossary.rst`. Every
devicetree property this project defines is undocumented — a shield
author has nothing to look up and must read `scripts/rigc/shields.py`.

Diátaxis **reference**: precise, factual, complete, no narrative. The
tutorials already carry the narrative; do not repeat it.

## 2. Two pages, and the split

**`doc/reference/shield-template.rst`** — the shield side, everything a
`.shield` file may declare.

**`doc/reference/board-socket.rst`** — the board side, everything a
typed socket node may declare, plus the connector-type binding's own
keys (`plug,positions`, `plug,bus-proxies`).

They cross-reference constantly (a `shield,plugs` names a connector
type; a `socket,i2c` is what a shield's bus proxy resolves against), so
they are one slice even though they are two files. Add both to
`doc/reference/index.rst`'s toctree.

## 3. The vocabulary — RE-DERIVE, this list is a prediction

Measured 2026-08-15 by grep over `boards/`, `dts/` and the fixtures.
**Counts are usage, not authority** — `scripts/rigc/shields.py`,
`::_parse_exposed`, `rigc/board_edt.py::_project_socket` and
`rigc/registry.py` are the authority for what is actually READ.

Shield side: `shield,plugs`, `shield,params`, `shield,param-includes`,
`shield,cs-position`, `shield,collect`, `shield,channel`,
`shield,addr-from`, `shield,sheet-label`, `shield,domain`,
`shield,position-domain`, `shield,role`, `shield,of`.

Board/connector side: `socket,<type>` compatibles (`socket,arduino-r3`,
`socket,grove`, `socket,mikrobus`, `socket,i2c-port`), the bus proxies
`socket,i2c` / `socket,spi` / `socket,uart` and their
`socket,<kind>-<role>` qualified forms, `socket,cs-pool` and
`socket,<kind>-<role>-cs-pool`, `socket,stackable`, plus the standard
nexus properties a socket may carry (`gpio-map`, `pwm-map`,
`io-channel-map`, their `-mask`/`-pass-thru` and `#…-cells`).

Connector binding: `plug,positions`, `plug,bus-proxies`.

**Two are rare and easy to miss** — `shield,role` and `shield,of` appear
exactly once, on `adafruit_data_logger`'s `dl_sq` pad
(`shield,role = "driver"; shield,of = <&dl_rtc>;`). They are real
vocabulary. Do not skip a property because the corpus uses it once.

## 4. What each entry must state

For every property, in a consistent shape:

1. **Where it may appear** — which node (template root, plug, device,
   pad, config element, exposed socket, board socket, connector
   binding).
2. **Type**, in the devicetree sense, and its cell shape where it has
   one.
3. **Required or optional**, and **what absence MEANS** — this project
   uses declared-by-absence deliberately (a socket without
   `socket,uart` does not offer UART; a device without
   `shield,cs-position` gets a pool-allocated one), so "optional" alone
   is not an answer.
4. **What refuses it** — the diagnostic code, by name. Slice 3 will
   turn those into links; here they are just named.
5. **One real example**, copied from the tree, with the file it came
   from. Not invented.

## 5. Rulings

1. **Reference, not tutorial.** No "first, do X". If a property needs a
   worked narrative, link the tutorial that has it.
2. **Every example must be REAL** — copied from a file in this repo and
   attributed. An invented example that does not parse is worse than no
   example, and this vocabulary has changed twice recently.
3. **`-W` clean**, per `doc/howto/build-the-docs.rst`.
4. **Do NOT resolve the venv question.** Whether Sphinx deps belong in
   the workspace `.venv` or a throwaway `.docvenv` is an open question
   for Tobi (`NEXT-SESSION.md`). Build the docs whichever way works
   today, and **state in your report which you used** — do not edit
   `build-the-docs.rst` to match what you did.

## 6. A DRIFT GUARD, and it is half the value

A reference page that silently falls behind the code is worse than
none — a reader trusts it. **Add a test** asserting the two sets agree:

- every `"shield,…"` / `"plug,…"` / `"socket,…"` property literal that
  appears in `scripts/rigc/` (production, not tests) is documented on
  one of the two pages;
- every property documented on those pages appears in `scripts/rigc/`.

Scanning string literals is crude but sufficient and robust — these
names only ever appear as literals. Handle the qualified families
(`socket,<kind>-<role>`, `socket,…-cs-pool`) by pattern rather than
enumerating every instance; state how you did it.

Where the test lives: this is a property of the CORPUS, not of a
production module, so it belongs beside the other corpus-level laws
(`test_singleton_identity_law.py`, `test_golden_path_hygiene.py`), NOT
in a `test_<module>.py` that mirrors no unit. It must NOT be
build-marked — it is a file scan.

**Verify it both ways**: it must FAIL if you delete one property's entry
from a page, and FAIL if you document a property that does not exist.

## 7. Fold in one real wart

`boards/rigs/lotus_pwm/lotus_pwm.yml`'s comment says the board declares
a "per-function nexus (`socket,pwm-map` / `socket,adc-map`)". **Neither
property exists.** The real spellings are `pwm-map` and
`io-channel-map` — the same fabrication that was fixed in
`rigc/analyzer/gpio.py::_collect_channel`'s diagnostic (`88e53fc`) and
missed here. Fix the comment. Grep for other instances of both strings
while you are there.

## 8. Acceptance criteria

1. Both pages exist, are in `doc/reference/index.rst`'s toctree, and
   the docs build **`-W` clean**.
2. Every property in §3 documented to §4's shape — re-derived from the
   code, not copied from §3's list.
3. Every example real and attributed to its source file.
4. The drift guard exists, is not build-marked, and is verified BOTH
   ways (§6).
5. §7's wart fixed.
6. No production code changed except §7's comment. This is a docs
   slice; if you find a real defect, REPORT it rather than fixing it.
7. Every golden byte-unchanged. State as a checked result.
8. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **771**, integration **284**, coverage **94%** (2026-08-15, `c0f776c`).
   Re-derive rather than carry.

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + the docs build.
**No build module is named for this slice** — it touches no emitted
artifact, so the build tier observes nothing. If you believe otherwise,
say why. (Two previous briefs named a build module that turned out not
to be build-marked; check rather than assume.)

Brief the reviewer to MUTATION-CHECK: delete one property's entry from
a page — the drift guard must fail naming that property; add a
documented property that does not exist in the code — it must fail the
other way.

Standing rules: an implementor's report is a HYPOTHESIS. §3's list is a
PREDICTION — re-derive it from the parsers. Run negative controls
IN-TREE. Purge `__pycache__` after any mutate-and-restore. **Never `git
checkout`/`reset`/`stash`** — copy a file aside and copy it back. Never
store anything in a `west build -d` directory. When you name a function
in your report, qualify it as `path/to/module.py::function_name`.
Dispatch as `general-purpose` on **sonnet** from a session rooted at
`/wrk/z/ws-up`.
