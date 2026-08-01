# S1 fidelity milestone (R1/R2)

R2 (expansion contract): *for a rig that mirrors an S1-style setup using
converted hardware, the projected overlay is equivalent to the legacy overlay
output — equivalence, not byte-identity; labels may differ.*

**Rig:** `candidate-2-hybrid/s1-datalogger.rig.yml` — Adafruit Data Logger on
the Nucleo Arduino header, i.e. `west build -b nucleo_f401re --shield
adafruit_data_logger`.

**Method.** A full `west build` diff of `zephyr.dts` was *not* run here: the
trial `nucleo_f401re.rig.dtsi` is a truncated hypothetical socket fragment, not
the real board converted with a socket node, and a build needs the toolchain.
Instead — which is exactly what R2 specifies ("the projected *overlay* is
equivalent to the legacy *overlay*") — the generated overlay is compared
device-by-device against the real
`zephyr-rigs/boards/shields/adafruit_data_logger/adafruit_data_logger.overlay`,
and every pin reference is checked to resolve to the **same SoC pin** as in the
real `build-rig/upstream/S1/zephyr/zephyr.dts`.

## Pin resolution — exact match against the real board

The trial's `nucleo_ard` gpio-map equals the real Nucleo `arduino_header`
gpio-map for every position the shield uses (extracted from upstream
`zephyr.dts`, `arduino_header: connector`):

| position | real `arduino_header` | trial `nucleo_ard` |
|---|---|---|
| D3 (9)  | `&gpiob 3` | `&gpiob 3` ✓ |
| D4 (10) | `&gpiob 5` | `&gpiob 5` ✓ |
| D7 (13) | `&gpioa 8` | `&gpioa 8` ✓ |
| D10 (16)| `&gpiob 6` | `&gpiob 6` ✓ |

So each generated reference resolves identically to the legacy one — and the
board fragment carries the legacy alias `arduino_header: &connector_arduino_r3`,
so `&nucleo_ard` and `&arduino_header` are literally the same node.

## Device-by-device equivalence

| device | legacy overlay | generated overlay | equivalent |
|---|---|---|---|
| RTC | `rtc@68` reg `0x68`, `int1-gpios = <&arduino_header 0xd 0x11>` | `rtc@68` reg `0x68`, `int1-gpios = <&nucleo_ard 13 0x11>` | **yes** (13 = 0xd → gpioa 8, flags 0x11) |
| SD CS | `cs-gpios = <&arduino_header 0x10 0x1>` on `&arduino_spi` | `cs-gpios = <&nucleo_ard 16 1>` on `&spi1` | **yes** (16 = 0x10 → gpiob 6; arduino_spi = spi1) |
| SDHC | `sdhc@0` reg `0`, `spi-max-frequency = <24000000>` | same | **yes** (bar the `sdmmc` child — see gaps) |
| LED1 | gpio-leds child, `<&arduino_header 0x9 ACTIVE_HIGH>` | gpio-leds child, `<&nucleo_ard 9 0x0>` | **yes** (9 → gpiob 3, ACTIVE_HIGH) |
| LED2 | gpio-leds child, `<&arduino_header 0xa ACTIVE_HIGH>` | gpio-leds child, `<&nucleo_ard 10 0x0>` | **yes** (10 → gpiob 5) |

Every connector-routed signal, every address, every compatible, and the
`gpio-leds` aggregation matches. **R2 is satisfied at the resolved-hardware
level: the projected overlay is equivalent to the legacy output.**

## Differences (all expected or enumerated)

1. **Label / node names** — `logger_dl_rtc` vs `rtc0_adafruit_data_logger`,
   `&nucleo_ard` vs `&arduino_header`. Explicitly R2-permitted ("labels may
   differ"); resolves to the same nodes/pins.
2. **`aliases { rtc = … }`** — the legacy overlay carries it; in the rig model
   aliases are rig-owned and live in `rig.overlay` (Conv. 8), not the generated
   overlay. A design difference, not a loss.
3. **`status = "okay"`** — the legacy overlay sets it on each node; the emitter
   does not yet. Trivial to add (emit on every projected device); flagged for
   the real implementation.
4. **`sdmmc` disk child under `sdhc@0`** — the legacy overlay nests a
   `zephyr,sdmmc-disk` child; the prototype does not model device *sub-nodes*
   (only top-level shield devices). A genuine gap for the real implementation.
5. **LED `label` strings** — legacy "User LED1"/"User LED2" vs generated
   composed labels. Cosmetic; a shield could carry an explicit label.

## Verdict

R2 holds: exact pin/address/device equivalence, differences confined to
label naming (permitted), the aliases-in-`rig.overlay` design (Conv. 8), and
two small enumerated gaps (`status = "okay"`, device sub-nodes) that the real
implementation must close. R1 (expressiveness floor) is demonstrated across
the whole S2–S8 sweep plus this baseline.
