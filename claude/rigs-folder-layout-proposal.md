# `boards/rigs/` layout — the single-shield-rig question

**Status:** PROPOSAL, 2026-08-14. Needs Tobi's ruling before any code.
Written because the ruling asked for something the evidence does not
support, and saying so is cheaper than doing it and reporting a
regression.

## 1. What was asked, and what is actually there

**Asked** (Tobi, 2026-08-14): "remove the single shield rigs, that's
somewhat superseded by the rig promotion."

**The premise is right.** Rig promotion did supersede the "one shield on
one socket" purpose — and that supersession has ALREADY happened. It
lives in `tests/shields/`, which now holds 15 twister suites, each
building a shield with no rig file at all
(`RIG=adafruit_data_logger`, `RIG=temp_click:socket=quail_sock1`, and as
of `0246554` `RIG=adafruit_winc1500:config.w_irq_jmp=D2`). Nothing in
`boards/rigs/` is needed for that job any more.

**But no rig in `boards/rigs/` is still there FOR that job.** Five rigs
declare a single instance. Every one carries coverage that promotion
does not reach:

| rig | what it holds | promotion covers it? |
|---|---|---|
| `quail_can_span` | `can_span_click` plugging **two** mikroBUS sockets — one instance, but the multi-plug corpus witness | no |
| `pilot_variants` | the variants axis, across **five** golden sets (`_2`, `_variant_b`, `_variant_b_2`, `_variant_c`) | no |
| `grove_sens_pinned` | the PINNED half of a two-state strap, frozen as goldens — see §2a, this row was WRONG in the first draft | **partly — corrected** |
| `ard_datalogger` | the corpus's only rig genuinely built on **two** boards, with its own `ARD_DATALOGGER_FRDM_BOARD` constant | no |
| `nucleo_datalogger` | see §2 | partly |

Deleting any of the first four removes coverage, not duplication.

## 2a. CORRECTION — a non-default strap address IS promotable

**The first draft of this file claimed promotion could not express
`grove_sens_pinned`'s pinned address. That was wrong.** It carried an
analysis made BEFORE `0246554` landed `config.<label>=` and did not
re-check it afterwards. `config.` serves straps exactly as it serves
routing jumpers — `rigc/loader/params.py::apply_config_block` resolves
both by label and never distinguishes them.

Verified, not reasoned:

```
$ west rigs --explain "grove_sens_bme280:config.gsbme_addr_strap=0x77"
instances:
  - name: grove_sens_bme280
    shield: grove_sens_bme280
    config:
      gsbme_addr_strap: 0x77

$ west rigs --boards-for "grove_sens_bme280:config.gsbme_addr_strap=0x77"
m5stack_nanoc6/esp32c6/hpcore/rig
```

That is the same board `grove_sens_pinned` uses, resolving through the
real analyzer, and the printed content differs from the checked-in rig
only in the instance NAME — which is precisely what the singleton
identity law exists to normalise.

**So what actually distinguishes the rig is narrower, and it is real.**
A strap has TWO states and each needs a witness:

- the **allocated** half (rig silent, allocator picks the default 0x76),
  covered today by the singleton-law census promoting this shield with
  no `config:` at all;
- the **pinned** half (0x77 authored), covered today by
  `grove_sens_pinned` — **with frozen goldens**, which a twister suite
  does not give: a suite proves it BUILDS, the corpus freezes the bytes
  of the emitted overlay and the config sheet.

The law gives exactly ONE promotion per shield, so adding
`grove_sens_bme280` to `_CONFIG_ASSIGNMENTS` would SWAP which half is
covered, not add to it. Deleting the rig therefore trades frozen-byte
coverage of the pinned path for nothing, unless the law grows a way to
promote one shield twice.

That is a much weaker reason to keep it than "promotion cannot reach
it", and it is the true one. If frozen goldens for the pinned half are
not wanted, the rig is genuinely deletable — that is a call, not a fact.

## 2. `nucleo_datalogger` — the one real duplicate, and why it is not free

Its `instances:` block is **byte-identical** to `ard_datalogger`'s: same
shield, same socket, same instance name `logger`. Only the comment
differs. It is the S1 cutover-era baseline; `ard_datalogger` (S5,
board-agnostic, dual-host) supersedes it as CONTENT completely.

It is nonetheless load-bearing, because six test modules use it as the
canonical stand-in for "an ordinary rig":

- `test_cmake_alone_entry.py` — `_RIG = "nucleo_datalogger"`, the whole
  module
- `test_list_rigs_cmakeformat.py` — several tests
- `test_explain.py` — reads its directory and content file
- `test_resolved_corpus.py` — the plain-build-ordering test
- `test_compare.py`, `loader/test_documents.py` — unit tests naming it

Deleting it means repointing all six at `ard_datalogger`. That is
achievable and not risky, but it is a refactor, not a cleanup, and it
buys one fewer rig at the cost of making `ard_datalogger` serve double
duty as both the dual-host witness and the generic fixture.

## 3. The real complaint, restated

The `clash/` move (`15b8710`) fixed the sharp version of this: rigs that
CANNOT BUILD no longer sit beside ones that can. What remains is softer
— `boards/rigs/` is simultaneously the **test corpus** and the closest
thing to a **sample set**, and nothing tells a reader which rig is which.
That is a labelling problem, and deletion is the wrong lever for it:
every candidate for deletion is load-bearing precisely because it is
corpus.

## 4. Three ways to fix the labelling

**A. A README, and nothing else.** `boards/rigs/README.rst` states that
this folder is the frozen test corpus, that `clash/` holds the
deliberately-unbuildable ones, and names the three or four rigs a
newcomer should actually read first (`ard_datalogger` for the simplest
shape, `nucleo_mux_farm` for a carrier, `nucleo_grove_farm` for a nested
one). **Cost: one file. Deletes nothing. Reversible.**

**B. A second folder split**, mirroring `clash/` — e.g.
`boards/rigs/corpus/` for the fixture-ish rigs, leaving genuine examples
at the top. The machinery already supports it: `list_rigs.py::_find_rigs_under`
recurses to unlimited depth as of `15b8710`, so this is now just
`git mv` plus the goldens that quote paths. **The problem is the
criterion** — nearly every rig exists to freeze a golden, so the split
line is taste, not fact, and a reader would face the same question one
level down.

**C. Metadata, not folders.** A `kind:`/`role:` key in `rig.yml`, read by
`west rigs --list`. This is the architecturally right answer and it has
a natural home already queued: backlog item 7, `rig-schema.yaml`,
metadata-only. **Cost: real, and it should ride with that item rather
than being invented here.**

## 5. Recommendation

**A now, C when item 7 lands. Not B, and no deletions.**

A costs one file and addresses the actual complaint. C is where the
distinction belongs permanently, and item 7 is already the place that
decides what `rig.yml` may declare. B spends golden churn on a split
line nobody can define.

If deleting `nucleo_datalogger` is wanted anyway — for tidiness rather
than for coverage — it is a clean, self-contained slice (§2: repoint six
modules at `ard_datalogger`), and it should be ruled as its own thing
rather than folded into a cleanup, because the six modules are what make
it non-trivial.

**Open for Tobi**: A / B / C, and separately yes/no on
`nucleo_datalogger`.
