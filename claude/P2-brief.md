# P2 — Walking Skeleton: S1 End-to-End (Hand-off Brief)

Self-contained brief for the P2 phase of `implementation-plan.md`. Turns the
recorded P0/P1 **decisions** into an executable **build sheet** a sub-agent can
run. Read `implementation-plan.md` §P2 and `NEXT-SESSION.md` first for context;
this document is the authority on *where* and *how* for P2.

## Goal

One full pipeline on real hardware: `s1.rig.yml` → `rigexp expand` (run at
configure time, before DT) → generated overlay → `west build` on
`nucleo_f401re` → **`zephyr.dts` equivalent to the `--shield` baseline**
(R2, equivalence not byte-identity). Plus the P1 seam proven and the legacy
`--shield` path provably unbroken.

## Decisions locked this session (do not re-litigate)

1. **Do not touch bridle.** Use the **per-application** `ZephyrAppConfiguration`
   hook, *not* the workspace-singleton `ZephyrBuild` slot (bridle owns that in
   this workspace). `zephyr-rigs/cmake/modules/zephyr_default.cmake` runs
   `find_package(ZephyrAppConfiguration NAMES ZephyrApp PATHS
   ${APPLICATION_SOURCE_DIR} …)` **before `dts`** — that is our seam.
2. **Build against `zephyr-rigs`**, not `zephyr`. The active `.west/config`
   points `base = zephyr`, but the S1 golden was built against
   `/wrk/z/ws-up/zephyr-rigs`. Every P2 build **must** set
   `ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs`.
3. **Clone and own** the board and shield downstream. Copy the upstream
   `nucleo_f401re` board and the `adafruit_data_logger` assets into a
   downstream tree we own; make **all** edits there. Upstream `zephyr-rigs`
   stays pristine (verify with `git -C zephyr-rigs status --porcelain` = empty).
4. **Equivalence is the bar**, not byte-identity — labels/ordering may differ
   (see §Equivalence method).
5. **Upstreaming is out of scope** — it becomes its own package much later
   (parked; see `implementation-plan.md` §Parked).
6. The workspace is **fully functional**: Zephyr SDK (`~/zephyr-sdk-1.0.1`) and
   the full module set (`/wrk/z/ws-up/modules/`) are installed and known to
   build. No environment setup is needed beyond `ZEPHYR_BASE` (decision 2).

## Downstream ownership tree  (`btr-shields`)

Create a single downstream tree named **`btr-shields`** (deliberately *not*
"rigs", to avoid confusion with `claude/rigs` and the rig concept), **outside**
both `zephyr-rigs` and `claude/`:

> **FINAL LAYOUT (restructured to match upstream Zephyr conventions).** The
> tree below is canonical; the inline paths in tasks T1–T5 further down predate
> this restructure (shields/rigs moved under `boards/`, the expander under
> `scripts/`, the app under `samples/rigs/`) — read them against this block.

```
/wrk/z/ws-up/btr-shields/               # our downstream root (a real Zephyr module)
  zephyr/module.yml                      # module manifest: board_root/dts_root=. (load via EXTRA_ZEPHYR_MODULES)
  cmake/rig_expand.cmake                 # reusable rig_expand() seam fn (self-locating)
  boards/st/nucleo_f401re_btr/          # CLONE of the upstream board (renamed)
    nucleo_f401re_btr.dts               #   + arduino_r3_socket.dtsi (socket node + legacy aliases, Conv. 4)
    nucleo_f401re_btr.yaml, *_defconfig, Kconfig.* …   # cloned verbatim, board id renamed
  boards/shields/adafruit-data-logger.shield   # the .shield template (owned here, ported from the trial)
  boards/rigs/s1.rig.yml                 # the rig file  (-DRIG=s1 resolves here)
  dts/bindings/connector/arduino-r3.yaml # connector-type binding, authored for real
  scripts/rigexp/                        # the real expander package (see T1)  (+ vendored common-dts/)
  scripts/dts_equiv.py                   # R2 equivalence normaliser (durable — not in the build dir)
  samples/rigs/scenario-1/               # OUR app (copy of hello_world) — holds ZephyrAppConfig.cmake
    CMakeLists.txt, prj.conf, src/main.c, ZephyrAppConfig.cmake
```

The rig spike (T5) builds **our own** `btr-shields/app/s1-app` — the `ZephyrApp`
hook must sit in `APPLICATION_SOURCE_DIR`, and upstream `hello_world` must stay
pristine (decision 3). The legacy baseline (T4) uses the upstream sample
unchanged (it needs no hook).

The board is **cloned under a new id** (`nucleo_f401re_btr`) so it coexists with
the pristine upstream board and is reached via
`-DBOARD_ROOT=/wrk/z/ws-up/btr-shields`. No west-module registration is needed
for P2 — board/shield/binding roots are passed as cache vars (`BOARD_ROOT`,
`SHIELD_ROOT`, `DTS_ROOT`). Packaging the tree as a proper west module is
deferred (P2.5/P3).

## Tasks

Ordered. T4 (baseline capture) **must precede** any edit that could touch the
legacy path. T1–T3 are independent of the builds and can proceed in parallel.

### T1 — `rigexp expand` CLI  (prereq for the seam)

**Input.** `frontend-trial/scripts/rigexp/*.py`; the reference pipeline is
`run_trials.py:run_one` — `loader_yml.load(path, workdir, diags)` →
`analyzer.analyze(rig, workdir, diags)` → `emitter.emit(solved)`, which returns
`{ "overlay": …, "config-sheet.md": …, "expectations.yml": … }`.
**Deliverable.** A real CLI: `python -m rigexp expand <rig.yml> --shield-dir
<dir> --out-dir <dir>` that runs that pipeline and writes each returned file
into `--out-dir` (at minimum the `overlay`; also the `.conf`/config sheet when
present — see §Kconfig). Non-zero exit + rendered diagnostics on reject
(`diags.render()`), mirroring `investigate`. Copy the P0-blessed rigexp into the
downstream tree (§Tree) — do **not** import from `claude/`.
**Exit.** `python -m rigexp expand btr-shields/rigs/s1.rig.yml --shield-dir
btr-shields/shields --out-dir /tmp/rigout` writes an `overlay` identical to the
trial's `scripts/out/s1-datalogger-c2/overlay`.

### T2 — Downstream board + shield + bindings  (clone & own)

**Input.** Upstream `zephyr-rigs/boards/st/nucleo_f401re/`,
`zephyr-rigs/boards/shields/adafruit_data_logger/`; the trial's S1 rig
(`candidate-2-hybrid/s1-datalogger.rig.yml`) and its data-logger `.shield`.
**Work.** (a) Clone the board to `btr-shields/boards/st/nucleo_f401re_btr/`,
rename the board id, add the **arduino-r3 socket node + legacy aliases** (Conv. 4
— additive: real socket phandles alongside the existing arduino header labels, so
`--shield` still resolves). (b) Author
`btr-shields/dts/bindings/connector/arduino-r3.yaml` for real. (c) Port the
data-logger `.shield` template into `btr-shields/shields/`. (d) Author
`btr-shields/rigs/s1.rig.yml`.
**Exit.** `git -C zephyr-rigs status --porcelain` is empty (upstream pristine);
the clone board builds bare (`west build … -b nucleo_f401re_btr` with no shield,
no rig, configure-clean).

### T3 — ZephyrApp seam  (the P1 spike, no bridle)

**Input.** P1 outcome; the `find_package(ZephyrAppConfiguration … NAMES
ZephyrApp PATHS ${APPLICATION_SOURCE_DIR} …)` call in
`zephyr-rigs/cmake/modules/zephyr_default.cmake`.
**Work.** In our app dir (`btr-shields/app/s1-app/`), add a
`ZephyrAppConfig.cmake` that, when `-DRIG=<name>` is set: resolves `<name>` to
`btr-shields/rigs/<name>.rig.yml`,
`execute_process`es the T1 CLI to write `${CMAKE_BINARY_DIR}/rig/<name>.overlay`
(+ `.conf` if any), then `set(EXTRA_DTC_OVERLAY_FILE … CACHE …)` (and
`OVERLAY_CONFIG` if a `.conf` exists), and registers
`CMAKE_CONFIGURE_DEPENDS` on the rig file **and** `rigexp/*.py` so edits
re-trigger configure. Fail the configure with the CLI's diagnostics on reject.
**Exit.** `west build … -DRIG=s1` shows `dts.cmake` "Found devicetree overlay"
for the generated file; touching `btr-shields/rigs/s1.rig.yml` forces a reconfigure.

### T4 — Legacy-path baseline  (CAPTURE BEFORE ANY BOARD EDIT)

**Work.** Reproduce the recorded golden, then prove the clone is faithful.
1. Baseline (upstream board + legacy shield):
   ```sh
   export ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs
   /wrk/z/ws-up/.venv/bin/west build -p always -b nucleo_f401re \
     -d /wrk/z/ws-up/build-rig/proposal/S1-legacy-upstream \
     /wrk/z/ws-up/zephyr-rigs/samples/hello_world \
     --cmake-only -- -DSHIELD=adafruit_data_logger
   ```
   Save `build/zephyr/zephyr.dts` as the **legacy golden**. (This mirrors the
   `build_info.yml` command that produced `build-rig/upstream/S1`.)
2. After T2's clone: same build with `-b nucleo_f401re_btr -DSHIELD_ROOT=…
   -DBOARD_ROOT=/wrk/z/ws-up/btr-shields`. Assert **equivalent** to the legacy golden
   (only the board node's name/compatible differ). This is the
   convert-the-board safety net.
**Exit.** Legacy `--shield` build on the clone is equivalent to the upstream
golden — the socket-node addition provably did not disturb the legacy path.

### T5 — The spike build  (seam end-to-end)

**Work.**
```sh
export ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs
/wrk/z/ws-up/.venv/bin/west build -p always -b nucleo_f401re_btr \
  -d /wrk/z/ws-up/build-rig/proposal/S1 \
  /wrk/z/ws-up/btr-shields/app/s1-app \
  --cmake-only -- -DBOARD_ROOT=/wrk/z/ws-up/btr-shields -DDTS_ROOT=/wrk/z/ws-up/btr-shields -DRIG=s1
```
**Exit.** Configure is clean; the generated overlay is ingested; the shield's
nodes appear in `build/zephyr/zephyr.dts`.

### T6 — S1 R2 equivalence  (the deferred build diff)

**Work.** Diff the **rig-generated** `zephyr.dts` (T5) against the **legacy
golden** (T4) by the equivalence method below. Close the enumerated S1 gaps to
reach equivalence: `status = "okay"` on instantiated devices and the `sdmmc`
device sub-node (see `FIDELITY.md`).
**Exit.** Real R2 pass on S1: the two `zephyr.dts` files are equivalent.

## Build command reference

All P2 builds: **`export ZEPHYR_BASE=/wrk/z/ws-up/zephyr-rigs`** first, use the
venv west (`/wrk/z/ws-up/.venv/bin/west`), `-p always`, `--cmake-only` (DT is
resolved at configure — no need to compile for a `zephyr.dts` diff). SDK
auto-discovers (`~/zephyr-sdk-1.0.1`). **Sanity step 0:** build stock
`hello_world` with no rig/shield and confirm `build/build_info.yml` shows
`zephyr-rigs` paths — proves `ZEPHYR_BASE` took effect before anything else.

## Equivalence method (R2)

Compare `zephyr.dts`, not raw text. Normalise both sides, then diff:
- resolve/strip labels (compare by **node path**, not label spelling);
- compare each node's `compatible`, `reg`, `status`, and phandle-target
  **paths** (not phandle integers);
- ignore node/property **ordering** and whitespace;
- the board root node legitimately differs (clone id) — exclude it.
A small normaliser script (reuse dtlib to parse both) beats eyeballing. Keep
BOTH the script and the writeup in the **source tree**, never in a `west build
-d` output dir (a `-p always` rebuild wipes it): the normaliser lives at
`btr-shields/scripts/dts_equiv.py`, the result at `claude/rigs/P2-S1-equivalence.md`.

## Kconfig at P2

The Kconfig activation manifest is deferred to P3-3a. For P2 the config feed is
a **stub**: if `emitter.emit()` yields no `.conf`, the seam sets no
`OVERLAY_CONFIG` and that is correct. Do not block on Kconfig.

## Execution model

Driver delegates each task to a sub-agent on **sonnet** (`Agent` tool, `model:
sonnet`) with the task's Input/Deliverable/Exit as the brief. Human review gates
between tasks. T1/T2/T3 parallelisable; T4 before board edits; T5→T6 sequential.

## Open points — resolved

- **O1 — resolved.** Downstream tree is **`/wrk/z/ws-up/btr-shields/`** (named
  to avoid the "rigs" clash); board clone lives under `btr-shields/boards/` as
  a **new id** `nucleo_f401re_btr` (coexists with pristine upstream).
- **O2 — resolved.** Cache-var delivery (`BOARD_ROOT`/`DTS_ROOT`/`SHIELD_ROOT`)
  for P2; real west module deferred to P2.5/P3.
- **O3 — resolved.** `-DRIG=<name>` resolves to `btr-shields/rigs/<name>.rig.yml`
  for P2. Generalisation (search-path list, app-local rigs) revisited in P3.
- **O4 — resolved.** The `.shield` template is **owned in-repo** at
  `btr-shields/shields/` (ported from `frontend-trial/`), not referenced back.
- **O5 — resolved.** Our own app at `btr-shields/app/s1-app` (copy of
  hello_world) holds `ZephyrAppConfig.cmake`; upstream `hello_world` untouched.
