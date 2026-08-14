# `grove_pwm_led` — finishing `grove_led`, and the collect path's PWM gap

**Status:** briefed 2026-08-14, ready to dispatch. Second of the three
grove-completion slices (`grove_sens` landed `3c6eb98`/`ad5092a`; the
base carriers are third and want their own brief).

Bridle's `grove_led/` folder is **64 overlays, not 32**: `grove_led_dN`
(32, `gpio-leds`) and `grove_pwm_led_dN` (32, `pwm-leds`). This project
ported the GPIO half only. This slice ports the other half — and the
template is the small part.

## 1. The real content: `shield,collect` cannot emit a PWM entry

`shield,collect` is an open string (`shields.py:420` reads it as a plain
compatible), so `shield,collect = "pwm-leds"` parses today. The EMITTER
is where it breaks, and it breaks silently:

- **`_device_node`** (`emitter/overlay.py:303+`) branches on
  `ref.function`. The gpio branch renders `<&nexus pos flags>` and
  applies the `inst.invert` XOR; the pwm/adc branch reads
  `s.channels[...]`, renders `<&nexus pos period>` — **two cells, no
  flags** — and raises rather than emit nonzero PWM flags (the analyzer
  rejects those upstream as `phys-function`).
- **`_collection_entry`** (`emitter/overlay.py:202+`) has **no such
  branch**. Every ref goes through the gpio render.

So a `pwm-leds` entry emits a gpio-shaped three-cell `pwms` against a
socket whose `#pwm-cells` is 2, and XORs a polarity bit on `invert:`.
The emitter's own comment at line 330 says what a third cell does: it is
not absorbed by the map at all — dtlib reads it as the start of a bogus
trailing phandle-array element, "silently a spurious null entry when it
happens to be 0, a hard EDTError otherwise". A wrong-but-quiet overlay is
the likeliest outcome, which is why this is the slice's real content.

**Recommended fix: extract ONE renderer.** `_device_node`'s per-ref block
and `_collection_entry`'s are now near-duplicates that have already
drifted once — that drift IS this bug. Lift the per-ref rendering into a
single helper both call, rather than copying the branch into
`_collection_entry`. The 18 existing overlay goldens protect the
refactor: any behaviour drift on the gpio path shows up immediately and
byte-exactly.

**Flagged for veto**: copying the branch instead is smaller and more
obviously safe. Whichever way it goes, say so in the report — do not let
it be silently absorbed.

## 2. The template — a second shield in the `grove_led` FOLDER

Plurality (`arduino_lcd`, and now `grove_sens`): `boards/shields/grove_led/`
declares both names, `shield.yml` becomes a `shields:` list, and
`Kconfig.shield` gains a second symbol. Bridle keeps both LED kinds in
one folder too.

```dts
grove_pwm_led: grove_pwm_led {
	shield,plugs = "grove";
	gpl_plug: plug { #gpio-cells = <2>; #pwm-cells = <3>; };

	pwm {
		gpl_led: led {
			shield,collect = "pwm-leds";
			pwms = <&gpl_plug GROVE_SIG0 20000000 PWM_POLARITY_NORMAL>;	/* 20 ms */
		};
	};
};
```

`#pwm-cells = <3>` on the PLUG mirrors `grove_servo` — the shield-side
claim is (position, period, flags). The SOCKET's own cell count is a
board fact and differs (lotus is 2); that asymmetry is the existing
design, not a mistake to fix here. Bridle's own period is `PWM_MSEC(20)`.

**Every label is mandatory** (item 29, `33e5e49`) — an unlabeled device
is a loud `lang-shield-label` error.

## 3. Where it can run — and where it CANNOT

`grove_pwm_led` needs a Grove socket with a `pwm-map`. Exactly one board
in the tree has one:

| board | grove sockets | pwm-map? |
|---|---|---|
| `seeeduino_lotus` | `grove_d2..d7`, `grove_a0..a2` | **yes** — d2/d3/d4 reach `&tcc0` |
| `m5stack_nanoc6` | `grove_1` | **no** — upstream declares none |

So the corpus rig goes on lotus, next to `lotus_pwm` (which already runs
`grove_servo` on `grove_d2` and `grove_light` on `grove_a0`).

**There is NO twister suite for this shield, and that is a fact about the
platform, not an omission.** `seeeduino_lotus`'s base board lives in the
bridle module, which this workspace's `west.yml` does not import, so it
is not a twister platform — the same reason `grove_btn`'s lotus rig never
got a suite. **Record it in the report and in the shield's own comment
rather than leaving a reader to wonder.** Adding a `pwm-map` to the
NanoC6 socket to manufacture a suite is OUT OF SCOPE: upstream declares
none, and inventing an ESP32-C6 LEDC mapping is board work with no
upstream fact behind it.

Note `lotus_pwm`'s own warning, which applies to any build of this rig:
every build of that target must pass
`-DEXTRA_ZEPHYR_MODULES=<west-topdir>/bridle` explicitly.

## 4. The `d2`/`d4` channel clash is free evidence, if you want it

lotus's `grove_d2` and `grove_d4` both reach `&tcc0` channel 0 — a real
bridle fact the corpus already exercises through `lotus_pwm_clash`. Two
`grove_pwm_led` instances on those two sockets would collide the same
way. **Optional**: if it costs nothing, it is a genuine second witness
for the collision diagnostic on a COLLECTED device rather than a plain
one. If it costs a new fixture board or a golden rewrite, skip it and say
so.

## 5. Acceptance criteria

1. `grove_led/` declares two shields; both discovered, one Kconfig symbol
   each; `shield.yml` in plural form.
2. A `pwm-leds` collection entry emits `pwms = <&nexus pos period>` —
   two cells, no flags — into a `pwm_leds` collection node, verified
   against a real emitted overlay, not reasoned about.
3. `invert:` does NOT touch a PWM ref (it is a gpio-flags concept). State
   what happens if a rig sets it on a `grove_pwm_led` instance — refused,
   or ignored with a reason.
4. A corpus rig on `seeeduino_lotus` with its goldens.
5. **Every existing golden byte-unchanged** — this is the load-bearing
   criterion if §1's shared-renderer refactor is taken, since it is what
   proves the gpio path did not drift. State it as a checked result.
   `RIGC_REFREEZE=1` is BLOCKED — hand-edit and verify BOTH ways.
6. The singleton identity law grows by one with its module byte-unchanged
   — OR `grove_pwm_led` is in `EXPECTED_REJECTING` **with its reason
   stated**, if no census board offers a PWM-capable Grove socket. Check
   which; do not assume.
7. Full gate green, driver-run. Last driver-verified: mypy clean, unit
   **715**, integration **264**, coverage **93%** (2026-08-14, `ad5092a`).
   Re-derive rather than carry.

## 6. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criteria 2/4/5).
Confirm its `@pytest.mark.build` marking before claiming it.

Brief the reviewer to MUTATION-CHECK: emit the third (flags) cell on a
PWM collection entry — a test must fail on the CELL COUNT, not merely
somewhere; apply the `invert` XOR to a PWM ref — criterion 3's test must
fail; revert the shared renderer to two copies — nothing should fail,
and if something does, the refactor changed behaviour and that is the
report's headline.

Standing rules: an implementor's report is a HYPOTHESIS. Trace every
caller by grep AND run — this brief's file list is a prediction. Run
negative controls IN-TREE. Purge `__pycache__` after any
mutate-and-restore. Never `git checkout`/`reset`/`stash` — copy a file
aside and copy it back. Never store anything in a `west build -d`
directory. Dispatch as `general-purpose` on **sonnet** from a session
rooted at `/wrk/z/ws-up`.
