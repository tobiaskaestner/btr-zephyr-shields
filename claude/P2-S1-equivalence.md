# P2 / S1 — R2 build equivalence result

The walking-skeleton milestone: the rig-generated devicetree, built for real on
`nucleo_f401re_btr`, compared to the legacy `--shield` build on pristine
upstream. **Equivalence, not byte-identity** (R2): labels, phandle integers, and
ordering are irrelevant; nodes (keyed by path) and their properties must match,
with references resolved to target node **paths**.

- **golden**: `build-rig/proposal/S1-legacy-upstream/zephyr/zephyr.dts`
  — `west build -b nucleo_f401re --shield adafruit_data_logger` (upstream).
- **candidate**: `build-rig/proposal/S1/zephyr/zephyr.dts`
  — `west build -b nucleo_f401re_btr -DBOARD_ROOT=btr-shields -DDTS_ROOT=btr-shields -DRIG=s1`
  (our app `btr-shields/samples/rigs/scenario-1`, expander via the ZephyrApp seam).
- **tool**: `btr-shields/scripts/dts_equiv.py` (dtlib-based; path-keyed;
  phandle/path refs → target path; ordering/whitespace/label-independent; the
  root node is excluded — its id legitimately differs for the clone).

  > The normaliser lives in the **source tree** (`btr-shields/scripts/`), not in
  > a `west build -d` output dir. (The first copy was written into the build dir
  > and a `-p always` rebuild wiped it — build dirs are not durable.)

## Result (regenerated 2026-07-21b)

```
golden nodes: 134   candidate nodes: 136
nodes present in both with IDENTICAL properties: 129
nodes only in golden (candidate is missing): 2
    - /leds/led_1__adafruit_data_logger
    - /leds/led_2_adafruit_data_logger
nodes only in candidate (added by the rig): 4
    + /connector_arduino_r3
    + /gpio_leds
    + /gpio_leds/logger_dl_led1
    + /gpio_leds/logger_dl_led2
shared nodes with property differences: 3
    ~ /aliases  'rtc'
        golden:    ('ref', '/soc/i2c@40005400/rtc@68')
        candidate: ('ref', '/soc/rtc@40002800')
    ~ /soc/i2c@40005400/rtc@68  'int1-gpios'
        golden:    ('mix', (('ref', '/connector'), 13, 17))
        candidate: ('mix', (('ref', '/connector_arduino_r3'), 13, 17))
    ~ /soc/spi@40013000  'cs-gpios'
        golden:    ('mix', (('ref', '/connector'), 16, 1))
        candidate: ('mix', (('ref', '/connector_arduino_r3'), 16, 1))
```

## Verdict: **S1 R2 met**, modulo justified divergences + one deferred gap

**129 nodes byte-match.** The remainder decompose into:

### Justified divergences (by design — NOT gaps)
1. **`+ /connector_arduino_r3`** — the typed socket node itself. Present by
   design (Conv. 4); the legacy build has no typed socket.
2. **`int1-gpios` / `cs-gpios` → `/connector_arduino_r3` vs `/connector`** — the
   rig routes through the typed socket instead of the legacy connector. The
   **cell values are identical** (`13 17` and `16 1`), i.e. *same physical
   pins* — purely a reference-target difference, which is exactly what the rig
   model intends.
3. **`/aliases rtc`** — golden repoints `rtc` to the shield's PCF8523
   (`.../rtc@68`); the rig leaves it on the board's native RTC
   (`/soc/rtc@40002800`). Per **Conv. 8** aliases are rig-owned and belong in an
   (out-of-scope for P2) `rig.overlay` — matches what `FIDELITY.md` predicted.

### Real gap — DEFERRED to P3 (aggregation slice)
- **LEDs: `/gpio_leds/*` (rig) vs `/leds/*` (legacy)** — the shield's two LEDs
  land in a new top-level `/gpio_leds` node instead of merging into the board's
  existing `/leds` collection. Functionally harmless (both individually
  addressable) but structurally real. This is the `implementation-plan.md`
  §Backlog item *"aggregation refinements — merge into board-provided
  collections"*; closing it needs a merge-target mechanism (a compatible→
  node-name convention table, or a board-side declaration), decided in P3-3a.
  Deferred with the user's agreement.

## Reproduce

```sh
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs
python3 /wrk/z/ws-up/btr-shields/scripts/dts_equiv.py \
  /wrk/z/ws-up/build-rig/proposal/S1-legacy-upstream/zephyr/zephyr.dts \
  /wrk/z/ws-up/build-rig/proposal/S1/zephyr/zephyr.dts
```
