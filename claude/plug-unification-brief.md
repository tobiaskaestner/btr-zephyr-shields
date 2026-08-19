# One plug form — the single/plural asymmetry removed

**Status:** briefed 2026-08-19, in progress. Ruled by Tobi 2026-08-19,
from a review of the docs and the corpus: *"note how the
adafruit_datalogger defines the i2c and spi nodes as sibling of the plug
node, whereas the can_span_click has these nodes as child nodes of the
left_plug and right_plug nodes respectively. It would be much more
consistent if the single plug syntax would work the same"*, plus *"for
what the #gpio-cells property is actually needed on a plug node"*.

Two rulings, taken after the probe evidence in Sec 1/2:

1. **Full unification.** One authored form: N plug nodes, N ≥ 1, each
   declaring `compatible = "shield,plug"` and its own `shield,plugs`.
   Bus groups always nest under their owning plug; plain groups always
   stay at template level. **Template-level `shield,plugs` is retired**
   and the reserved-slot-name rule goes with it. Plurality becomes what
   the rest of rigc already thought it was: a count.
2. **Cell counts leave the plug node.** `#gpio-cells` / `#pwm-cells` /
   `#io-channel-cells` are **stripped from every plug node and refused
   there**. `_ncells` and `_FUNCTION_DEFAULT_CELLS` stay — a routing
   jumper's own `<1>` is genuinely load-bearing.

## 1. The asymmetry is a silent-failure trap, not a style wart

Probed against `parse_shields` directly (synthetic cpp-free DT, the
`test_shields.py` harness shape). **Run this again before trusting the
table** — it is four parses, not an argument:

| authored shape | result today |
|---|---|
| bus group SIBLING of `plug` (single form, 12 corpus files) | 1 device, `bus='i2c'`, `plug='plug'` |
| **bus group NESTED under `plug`** | **0 devices, 0 diagnostics** |
| plain group NESTED under `plug` | **0 devices, 0 diagnostics** |

Cause: `_RESERVED = {"plug", "pads", "config"}` (shields.py:71) and the
single-form group walk skipping every reserved name (shields.py:262), so
the plug node's children are never visited. The plural form *refuses*
both misplacements with `lang-shield-proxy` (shields.py:315, :330). So
the two forms do not merely differ in where a bus group goes — one of
them silently discards a whole authored group and everything under it.
That is item 41's defect shape (`rig.yml` ignoring unknown keys under
`rig:`) one level up, and the tutorial's own reader is the one who hits
it.

## 2. THE KEY FACT — nothing downstream knows there are two forms

Every consumer of plurality below `shields.py` already discriminates on a
**count**, never on the authored form:

| site | test |
|---|---|
| `analyzer/sockets.py:103` | `is_plural = len(parents) > 1` |
| `analyzer/sockets.py:275` | `len(inst.shield.plugs) > 1` |
| `emitter/sheet.py:109` | `len(inst.shield.plugs) <= 1` |
| `promote.py:522` | `len(shield.plugs) > 1` |

And `_parse_shield`'s single branch (shields.py:207–217) already
normalizes to the same three structures the plural walk consumes —
`shield.plugs`, `ctypes_by_slot`/`nodes_by_slot`, `plugs_by_path` — with
the slot name `"plug"` taken from the node's own literal name.
`shields.py` is also the ONLY module that reads `shield,plugs` at all
(`grep -rn 'shield,plugs' scripts/rigc` outside tests hits shields.py and
one model.py comment). Verify both before relying on them; they are what
makes this slice a parse-layer change plus a mechanical migration, not a
refactor of the pipeline.

**The consequence for the emitted output:** a migrated single-plug shield
keeps its plug node named `plug`, so its slot name stays `"plug"`, so
every `Device.plug`, every sheet row and every overlay line is unchanged.
**Goldens are expected byte-identical.** That is a HYPOTHESIS — item 30's
own cost estimate was wrong in this same file's history. Measure it.

## 3. The end state, authored

```devicetree
adafruit_data_logger {
        dl_plug: plug {
                compatible = "shield,plug";
                shield,plugs = "arduino-r3";

                i2c { dl_rtc: rtc@68 { ... }; };
                spi { dl_sd: sdhc { ... }; };
        };

        gpio { dl_led1: led-1 { ... }; };   /* plain: plug-agnostic, template level */
        pads { dl_sq: sq { ... }; };
        config { ... };
};
```

`plug` is now an ordinary slot NAME, conventional for a one-plug shield,
no longer reserved and no longer refused on a plug node. Nothing about a
one-plug shield is special-cased.

## 4. What changes in `shields.py`

- `_parse_shield`: delete the `is_plural` fork. Plugs come from
  `plug_children` only. `plugs_prop is not None` becomes a **retirement
  diagnostic** (`lang-shield-plug`) naming the move, so the old spelling
  fails loudly rather than being read as a device group named `plug`.
- Delete the `named_plug` refusal (a plug named `plug` is now normal).
- `_RESERVED` loses `"plug"`; plug nodes are skipped by identity
  (`group in plug_children`), as the plural walk already does.
- One group walk, both levels, the plural rules for everybody:
  template-level bus-shaped group → `lang-shield-proxy`; plain group
  nested under a plug → `lang-shield-proxy`.
- Plain-group devices get `plug = the only slot when there is exactly
  one, else None` — NOT the hardcoded `"plug"` of the single branch.
  Same value for every migrated shield, and correct for a one-plug
  shield that names its plug something else.
- The routing-jumper refusal becomes `len(shield.plugs) > 1`.
- NEW refusal: `#gpio-cells`/`#pwm-cells`/`#io-channel-cells` on a plug
  node (ruling 2), code `lang-shield-plug-cells`.

## 5. Why the cells go, and why the mechanism stays

`#<fn>-cells` on a plug is read in exactly one place, `_ncells`
(shields.py:554, called from `_parse_pos_ref` and the exposed-socket
walk), which already falls back to `_FUNCTION_DEFAULT_CELLS =
{"gpio": 2, "pwm": 3, "adc": 1}`. **Every plug-level declaration in the
corpus equals that default** — a probe with the property removed entirely
parses identically. The plug node is never emitted, so no dtc and no
binding ever validates it. Two supporting facts:

- `grove_light.shield:14` declares `#gpio-cells = <2>` on a plug whose
  only reference is `io-channels`. Pure noise.
- The one load-bearing declaration in the corpus is not on a plug:
  `adafruit_winc1500.shield:27`, `#gpio-cells = <1>` on the `irq-jmp`
  routing jumper, where 1 really differs from 2.

It is also an **unvalidated knob** today: a probe with
`#gpio-cells = <3>` on a plug was accepted silently and changed the ref
arity. Refusing the property on plugs closes that without keeping ~30
lines that restate a default. `doc/reference/shield-template.rst:100`
already documented the properties as optional-with-defaults, so the
corpus was the half that disagreed with the reference — the same shape as
the `.docvenv` blocker.

## 6. Migration surface

| what | count |
|---|---|
| corpus shield files, single form with a bus group | 12 |
| corpus shield files, single form without one (cells strip + plug-node move only) | 8 |
| corpus shield files, plural (cells strip only) | 2 |
| integration fixture `.shield` files | ~20 |
| `test_shields.py` inline fixtures | ~40 templates |

Carriers with exposed sockets (`grove/seeed_grove_base_v{1,2}`,
`i2c_mux`, `mikrobus_span_adapter`) keep every `#gpio-cells` /
`#pwm-cells` / `#io-channel-cells` on their **socket** nodes — those are
emitted for real and read by `_ncells`'s exposed-socket caller. Only
**plug** nodes are stripped.

## 7. Sequencing — why now

Item 9, the bridle migration, is the next slice. Every shield ported from
bridle would otherwise be authored in the form being retired, so the
migration cost is 20 files now versus 20 + N later.

## 8. What implementation corrected in this brief

Three things above turned out to be wrong or incomplete. They are left in
place, with the correction here, because the wrongness is the useful part.

**Sec 1's cause is right about the OLD code and wrong as a fix
description.** Removing `"plug"` from `_RESERVED` was mutation-tested by
restoring it: **the mutation SURVIVED**. Plug nodes are now skipped by
identity (`group in plug_children`) and their children are reached by the
per-plug walk over `nodes_by_slot`, which consults `_RESERVED` not at all —
so that entry is inert and its removal is a cleanup. What actually
unswallows a nested group is the per-plug walk's existence; mutating THAT
kills the test. The retired single form had no such walk, which is why a
reserved NAME was the only thing between those groups and the parser. The
code comment on `_RESERVED` says so, and names the mutation.

**Sec 5's "every plug-level declaration equals the default" is true of
`boards/shields/` and FALSE of one fixture.**
`carrier-analog-passthrough`'s `fixture_analog_carrier` declared
`#pwm-cells = <2>` on its plug — the one non-default plug value anywhere —
and its `pwm-map` rows were shaped to a 2-cell parent side accordingly.
Four integration tests red on `truncated entry` until the rows gained a
third parent cell. Every REAL carrier already used three
(`seeed_grove_base_v2`), so the fixture was the outlier and the fix aligned
it with the corpus.

**The consequence worth stating, which the brief did not anticipate:** a
pass-through map row's two halves now differ in kind. The CHILD side
carries whatever count the exposed socket declares for itself; the PARENT
side is a plug, so it is always the generic count for that function — 2
gpio, 3 pwm, 1 adc — with nothing left to vary. That is documented on
`shield-template.rst` and in the fixture's own header.

**Sec 2's "goldens byte-identical" was half right, and the wrong half is
the interesting one.** Every OVERLAY comparison passed untouched — that
part held. But **six stderr goldens changed**, and the full gate is what
found them (`test_emitted_golden` for the five `REJECT_CASES` plus
`test_pwm_nonzero_flags_golden`): a diagnostic cites its source location,
and moving a bus group under the plug moved both halves of it —

- **line numbers** shifted in every migrated file (the plug node grew from
  a one-liner to a block, `shield,plugs` moved into it);
- **DTS node paths gained a `plug/` segment** for bus devices:
  `/shield-templates/adafruit_winc1500/spi/wifi` became
  `/shield-templates/adafruit_winc1500/plug/spi/wifi`.

Refrozen, and the refrozen diff is itself the evidence the change was
placement-only: **every changed line is a source location** — no verdict,
no message body, no exit code, no overlay. Two details in that diff are
worth keeping:

- `grove_servo`'s path stayed `/shield-templates/grove_servo/pwm/servo`.
  `pwm` is a PLAIN group, so it did not move — the goldens confirm the
  placement rule discriminates bus from plain exactly as intended, on real
  output rather than on a fixture.
- The `plug/` segment is a genuine improvement to the diagnostic: the path
  now says which plug a conflicting reference resolves through, which on a
  two-plug shield is information the old path could not carry.

The lesson generalizes past this slice: **a byte-compared stderr golden
makes every source line number part of the contract.** Any edit that moves
lines in a `.shield` file changes goldens, however semantically inert it
is. That is a property of the golden design, not a defect — but it means
"no behavior change" never implies "no golden change", and the fast gate
(`CHECK_FAST=1`) checks none of them.

**Also done, beyond the brief:** two new doc laws in
`test_dts_vocabulary_drift.py` (no doc example shows template-level
`shield,plugs`; no doc example declares cells on a plug node) plus a
vacuity control, since the existing vocabulary scan cannot see either
change — `shield,plugs` is a real production literal wherever it sits, and
`#<fn>-cells` is not in the `shield,*`/`plug,*`/`socket,*` families at all.
Both laws were mutation-checked against real doc pages. `glossary.rst`
gained **routing jumper**, the term the cells ruling needs in order to say
what a plug is not.

## 9. Acceptance

1. A one-plug shield with its bus groups nested parses its devices —
   the probe's failing case (Sec 1) becomes a test.
2. A bus group at template level is refused for a one-plug shield, with
   the plural form's own diagnostic.
3. A plain group nested under a plug is refused for a one-plug shield.
4. Template-level `shield,plugs` is refused, and the message says where
   it moved.
5. Any `#<fn>-cells` on a plug node is refused; a routing jumper's own
   `#gpio-cells = <1>` still parses and still resolves.
6. `adafruit_winc1500` (jumper + strap + promotion) and
   `mikrobus_span_adapter` (plural + exposed socket) both still expand.
7. Every golden accounted for (Sec 2's hypothesis, MEASURED and
   half wrong -- see Sec 8: overlays byte-identical, six stderr
   goldens refrozen for source locations only).
8. Docs: `shield-template.rst`'s two form sections collapse to one; the
   three tutorials teach the new shape; the DTS-vocabulary drift guard
   still passes and still fails under mutation.
