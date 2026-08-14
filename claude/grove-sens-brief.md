# Grove environmental sensors — the first I²C Grove shield

**Status:** briefed 2026-08-14, **ruled, ready to dispatch.** First of the
three grove-completion slices (`grove_sens` → `grove_pwm_led` → the base
carriers), sequence confirmed by Tobi 2026-08-14.

Ports bridle's `boards/shields/grove_sens/` — three overlays — as template
shields, and in doing so becomes the **first real user of the Grove
socket's I²C bus proxy**, which `dts/bindings/connectors/grove.yaml` has
declared and nothing has ever exercised.

## 1. The ruling (Tobi, 2026-08-14)

**The address strap is modelled exactly like `temp_click`'s**: a
two-value `shield,domain`, allocated when the rig is silent, with the
config sheet naming the required state. The alternative — a strap
learning an "as-shipped default" so a silent rig takes 0x76 without
allocating — was weighed and **rejected for this slice**: it is a real
model change (`Strap`, the allocator, the sheet, and the "who resolves it
when the rig is silent" table) and would be its own slice, not a
passenger on this one.

Consequence to state in the report rather than discover: a user who never
touches the solder bridge may still be told by the sheet to move it, when
the allocator picks the non-default state. That is the accepted cost.

## 2. What bridle has

| overlay | compatible | reg | friendly-name |
|---|---|---|---|
| `grove_sens_bme280` | `bosch,bme280` | `0x76` | Grove THP Sensor V1.0 (BME280) |
| `grove_sens_bmp280` | `bosch,bme280` | `0x77` | Grove TP Sensor V1.0 (BMP280) |
| `grove_sens_dps310` | `infineon,dps310` | `0x77` | Grove High Precision TP Sensor V1.0 |

Every one carries the same comment: *"Device address 0x76 is assumed per
default. Your device may have a different address; check solder bridge on
your device if unsure."* That sentence is why these are straps and not
fixed `reg` values — the choice is real, and a human realizes it with
their hands.

**BME280 and BMP280 share the compatible `bosch,bme280`** (Zephyr's
bme280 driver serves both parts) and differ only in default address and
friendly-name. They are still two distinct products and stay two shields.

**Only the DEFAULT address is sourced from bridle.** The second domain
value is the part's standard alternate (SDO/solder-bridge pulled the
other way): 0x77 for BME280, 0x76 for BMP280 and DPS310. **Verify each
against the driver binding and the part before authoring it** — do not
copy this table on trust; it is a prediction, and an address is exactly
the kind of fact this project has been wrong about before.

## 3. Shape — one folder, three shields (plurality)

`boards/shields/grove_sens/` declares all three, following
`arduino_lcd`'s precedent exactly: one `shield.yml` with a `shields:`
list, one `.shield` per shield, one `Kconfig.shield` carrying one
`SHIELD_<NAME>` symbol per declared name. Zero new fixture shield.yml.

```dts
/ {
	shield-templates {
		grove_sens_bme280: grove_sens_bme280 {
			shield,plugs = "grove";
			gs_plug: plug { #gpio-cells = <2>; };

			i2c {
				gs_bme: sensor@addr_strap {
					compatible = "bosch,bme280";
					shield,addr-from = <&gs_addr_strap>;
				};
			};

			config {
				gs_addr_strap: addr-strap {
					shield,domain = <0x76 0>, <0x77 1>;
					shield,sheet-label = "ADDR solder bridge";
				};
			};
		};
	};
};
```

Note what the shield does NOT declare: no `reg`, no real unit-address.
The symbolic `@addr_strap` is the deferral marker and `shield,addr-from`
is the checked reference; the expander authors both (address authority
rule, `temp_click`'s own comment says it).

**Every label is mandatory now** — item 29 landed 2026-08-14 (`33e5e49`)
and an unlabeled device, pad, strap or jumper is a loud
`lang-shield-label` error. A rig assigns the strap by its LABEL:
`config: { gs_addr_strap: 0x77 }`.

## 4. The board side — one line, and it is already true in copper

The Grove socket on `m5stack_nanoc6` **is** the I²C port, and the
evidence is in the upstream tree rather than in this brief's opinion:

- `zephyr/boards/m5stack/m5stack_nanoc6/grove_connectors.dtsi` maps the
  connector to `&gpio0 1` and `&gpio0 2`.
- `m5stack_nanoc6_hpcore-pinctrl.dtsi`'s `i2c0_default` is
  `I2C0_SCL_GPIO1` + `I2C0_SDA_GPIO2`.
- the board `.dts` already declares `&i2c0 { status = "okay"; }`.

So SIG0 = SCL and SIG1 = SDA, matching bridle's own
`grove_i2c_connector.dtsi` convention (`<0 0 … A5 / I2C-SCL>`,
`<1 0 … A4 / I2C-SDA>`). `boards/extend/m5stack/m5stack_nanoc6/grove_socket.dtsi`
gains one property:

```dts
	socket,i2c = <&i2c0>;
```

and its "Digital-only" comment needs correcting in the same edit — it is
about the absent pwm/adc maps, and will read as stale the moment a bus
appears next to it.

**`seeeduino_lotus` cannot serve here.** Its nine `socket,grove` nodes
are `grove_d2..d7` + `grove_a0..a2` — it declares **no I²C Grove socket
at all**, though bridle's lotus does. Adding one is out of scope; name it
in the report as owed, since it is where a second, multi-socket witness
for this path would come from.

## 5. Corpus and twister

- **A corpus rig** exercising an authored (non-allocated) address, so the
  `config:` assignment path has a real user: two sensors on the one
  `grove_1` socket is impossible (one socket, one plug), so the rig is
  one instance with `config: { gs_addr_strap: 0x77 }` pinning the
  non-default state. Model it on `quail_temp_farm`'s pinned half.
- **A twister suite**, `tests/shields/grove_sens/`, in the shape every
  existing suite uses (`tests.yaml` + `CMakeLists.txt` + `prj.conf` +
  `src/main.c` + `README.rst`):

  ```yaml
  tests:
    shields.grove_sens:
      platform_allow: m5stack_nanoc6/esp32c6/hpcore/rig
      tags: shields
      extra_args:
        - RIG=grove_sens_bme280
  ```

  No `:socket=` — the NanoC6 offers exactly one Grove socket, so
  promotion is unambiguous (contrast `temp_click` on quail, which needs
  `:socket=quail_sock1` because quail offers four mikroBUS).

  `prj.conf` needs `CONFIG_I2C=y` + `CONFIG_ZTEST=y` (the `temp_click`
  suite's shape) **plus whatever the real driver requires** —
  `CONFIG_SENSOR=y` is the prediction, since Zephyr's `BME280` symbol
  defaults `y` on `DT_HAS_BOSCH_BME280_ENABLED`. **Confirm by building,
  not by reading the Kconfig.** This is the first suite in the tree with
  a REAL sensor driver behind it; every prior one is a `vnd,*` test
  binding or a driverless GPIO shape, so no existing suite proves the
  driver path works.

  If a driver's requirements turn out to drag in more than one line of
  `prj.conf`, that is a finding worth its own paragraph — `i2c_mux`'s
  `CONFIG_I2C_TCA954X=n` wall is the standing warning that a real driver
  can refuse to compile against a rig-shaped devicetree.

## 6. What this slice must NOT do

- **No change to the strap model.** §1 ruled it out. If allocation-vs-
  default starts to look like it needs solving here, stop and report.
- **No widening of the i2c proxy machinery.** It exists and mikroBUS
  uses it (`registry.py`, `shields.py`'s bus-proxy validation). If a
  grove i2c group needs new code in `shields.py`, the premise is wrong —
  report rather than widen.
- **No `socket,i2c` on `seeeduino_lotus`** (§4).

## 7. The singleton identity law — the strongest evidence available, free

`test_singleton_identity_law.py` derives its domain from the shield
census. Three new promotable shields enter it **with that module
byte-unchanged** — that is exactly how the plurality slice got its best
evidence (14 cases → 16). Expect it to grow by three and stay green.

If any of the three cannot promote on any board, it belongs in
`EXPECTED_REJECTING` **with the reason stated**, not quietly excluded —
`adafruit_winc1500` is the sole existing member and it earns its place by
a diagnostic nobody can work around.

## 8. Acceptance criteria

1. Three shields in one folder, discovered by name, `shield.yml` plural
   form, one Kconfig symbol each.
2. A rig assigning the strap **by label** (`config: { gs_addr_strap: … }`)
   loads, and the emitted overlay carries the authored `reg` and matching
   unit-address.
3. A rig that is SILENT about the strap allocates, and the config sheet
   renders the `shield,sheet-label` instruction naming the state.
4. `socket,i2c` on the NanoC6 grove socket; the digital-only comment
   corrected.
5. The twister suite builds a real `zephyr.elf` on
   `m5stack_nanoc6/esp32c6/hpcore/rig` — verified with
   `west twister --build-only`, not inferred from the pattern match.
6. The singleton identity law grows by three with its module
   byte-unchanged (§7).
7. Existing goldens byte-unchanged; new golden dirs are pure additions.
   State it as a checked result. `RIGC_REFREEZE=1` is BLOCKED — hand-edit
   and verify BOTH ways.
8. Full gate green, driver-run. The last driver-verified numbers are
   **mypy clean, unit 715, integration 254, coverage 93%** (2026-08-14,
   `33e5e49`) — re-derive rather than carry them.

## 9. Reduced verification contract

Implementor: mypy + unit + non-build integration + **ONE named build
module — `test_emitted_corpus.py`** (it observes criterion 2/3 via the
new corpus rig). **Confirm its `@pytest.mark.build` marking before
claiming it.** Observing modules: the loader/analyzer unit tests,
`test_emitted_corpus.py`, `test_singleton_identity_law.py`. The driver
runs the full gate once, after review.

Brief the reviewer to MUTATION-CHECK: delete the `shield,addr-from`
reference (the address must fail to resolve, and the test must fail on
the SENTENCE); change the domain's second value (the allocation test
must notice); remove `socket,i2c` from the board fragment (the shield
must be refused for want of a bus, and the refusal must name the bus,
not merely fail). A green gate proves nothing about whether these are
contracts.

Standing rules: an implementor's report is a HYPOTHESIS — the driver
re-runs it. Trace every reader by grep AND run; this brief's file list is
a prediction. Run negative controls IN-TREE. Purge `__pycache__` after
any mutate-and-restore. Never store anything in a `west build -d`
directory. Dispatch as `general-purpose` on **sonnet** with the role
rules folded into the prompt from a session rooted at `/wrk/z/ws-up`.
