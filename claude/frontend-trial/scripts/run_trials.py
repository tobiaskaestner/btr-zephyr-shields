#!/usr/bin/env python3
"""Drive the expander prototype.

  no args              run the full corpus + seeded mistakes; write
                       scripts/out/ (one dir per rig) + comparison.md.
  <rig>                investigate ONE rig: print its diagnostics and the
                       emitter's outputs (overlay / config sheet / expectations)
                       to stdout. e.g.  python3 run_trials.py lotus-pwm
  <rig> -c c1          use the candidate-1 (DTS) front-end (default: c2/yml).
  -l / --list          list the rig names you can investigate.

  pass A: every corpus rig through its loader(s) -> analyzer -> emitter;
          each rig is marked clean/reject per its expectation.
  pass B: seeded loader mistakes (scripts/seeded/) -> side-by-side diagnostics.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rigexp import analyzer, emitter, loader_dts, loader_yml  # noqa: E402
from rigexp.diag import Diagnostics, LoadError, ROOT  # noqa: E402

SCRIPTS = os.path.join(ROOT, "scripts")
OUT = os.path.join(SCRIPTS, "out")
WORK = os.path.join(OUT, "work")
SEEDED = os.path.join(SCRIPTS, "seeded")

LOADERS = {
    "c1": (loader_dts, os.path.join(ROOT, "candidate-1-dts"), ".rig.dts"),
    "c2": (loader_yml, os.path.join(ROOT, "candidate-2-hybrid"), ".rig.yml"),
}

TRIALS = {                      # trial -> must expand clean?
    "s1-datalogger": True,         # fidelity baseline: 1 board + 1 shield (R1/R2)
    "s5-temp-farm": True,
    "s7-sqw-counter": True,
    "s3-stacked-loggers": False,   # the seeded-ERROR showcase: analyzer rejects
    "s2-wifi-logger": False,       # IRQ jumper left at D7 -> phys-net reject (CS allocates)
    "s2-wifi-logger-ok": True,     # IRQ jumper moved to D2 -> realizable (R6)
    "s4a-grove": True,             # Grove modules in distinct sockets (R11/R12)
    "s4a-shared": False,           # cross-socket net share -> phys-net (R13)
    "s4b-sockets": True,           # socket selection picks the controller (R14/R15)
    "s4b-dup-addr": False,         # two fixed 0x5f on the shared i2c1 -> phys-addr (R9)
    "s6-eth-click": True,          # nested carrier: clicks resolve through the chain (R19)
    "s6-cross-layer": False,       # cross-layer CS clash through the nesting (R21)
    "lotus-buttons": True,         # bridle port: 64 overlays -> 1 shield + socket/invert
    "lotus-pwm": True,             # multi-function positions: PWM + ADC (Slice A)
    "lotus-pwm-clash": False,      # two PWM on one timer channel -> phys-channel
    "s8-mux": True,                # active interposer: 4x 0x48 behind a mux (R26/R27)
    "s8-mux-collision": False,     # two 0x48 in one channel scope -> phys-addr
}
# Candidate #1 (pure-DTS) is retired (verdict ratified); its files exist only
# for s3/s5/s7 as the historical comparison. New scenarios are candidate-2
# only — the runner simply skips a (trial, candidate) whose file is absent.


def run_one(loader, path: str) -> tuple[Diagnostics, dict | None]:
    """Full pipeline on one rig file. Returns (diags, outputs|None)."""
    diags = Diagnostics()
    try:
        rig = loader.load(path, WORK, diags)
    except LoadError as e:
        diags.append(e.diag)
        return diags, None
    if rig is None or diags.errors:
        return diags, None
    solved = analyzer.analyze(rig, WORK, diags)
    if solved is None or diags.errors:
        return diags, None
    return diags, emitter.emit(solved)     # strong contract: cannot fail here


def pass_a() -> tuple[bool, list[str]]:
    ok, report = True, ["# Trial corpus results", ""]
    for trial, expect_clean in TRIALS.items():
        per_cand = {}
        for cand, (loader, cdir, ext) in LOADERS.items():
            path = os.path.join(cdir, trial + ext)
            if not os.path.isfile(path):
                continue                 # retired candidate / not authored
            diags, outputs = run_one(loader, path)
            per_cand[cand] = diags
            clean = outputs is not None and not diags.errors
            status = "clean" if clean else f"{len(diags.errors)} error(s)"
            good = clean == expect_clean
            ok &= good
            mark = "ok" if good else "UNEXPECTED"
            print(f"[{mark:>10}] {trial} / {cand}: {status}")
            report.append(f"## {trial} / {cand} — {status} ({mark})")
            if diags:
                report += ["", "```", diags.render(), "```", ""]
            if outputs:
                d = os.path.join(OUT, f"{trial}-{cand}")
                os.makedirs(d, exist_ok=True)
                for fname, content in outputs.items():
                    with open(os.path.join(d, fname), "w") as f:
                        f.write(content)
                report.append(f"outputs: `out/{trial}-{cand}/`")
                report.append("")

        # candidate-independence of physics: same phys-* error codes both
        # sides — only meaningful where BOTH candidates were authored
        if "c1" in per_cand and "c2" in per_cand:
            phys = {c: sorted(d.code for d in per_cand[c].errors
                              if d.code.startswith("phys-")) for c in per_cand}
            if phys["c1"] != phys["c2"]:
                ok = False
                print(f"[ MISMATCH ] {trial}: phys errors differ c1={phys['c1']} "
                      f"c2={phys['c2']}")
                report.append(f"**MISMATCH**: phys errors differ: {phys}")
        report.append("")
    return ok, report


def pass_b() -> list[str]:
    """Seeded loader mistakes: the same authoring error in both candidates,
    verbatim messages side by side."""
    report = ["# Seeded-mistake comparison (front-end verdict input)", ""]
    mistakes = sorted({f.rsplit(".rig.", 1)[0] for f in os.listdir(SEEDED)})
    for m in mistakes:
        report.append(f"## {m}")
        for cand, (loader, _cdir, ext) in LOADERS.items():
            path = os.path.join(SEEDED, m + ext)
            if not os.path.isfile(path):
                continue
            diags, _outputs = run_one(loader, path)
            errs = diags.render() if diags else "(no diagnostics — NOT CAUGHT)"
            print(f"[  seeded  ] {m} / {cand}: "
                  f"{len(diags.errors)} error(s)")
            report += ["", f"### {cand}", "```", errs, "```"]
        report.append("")
    return report


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    ok, rep_a = pass_a()
    rep_b = pass_b()
    with open(os.path.join(OUT, "comparison.md"), "w") as f:
        f.write("\n".join(rep_a + [""] + rep_b) + "\n")
    print(f"\nreport: {os.path.relpath(os.path.join(OUT, 'comparison.md'))}")
    return 0 if ok else 1


def available_rigs() -> list[str]:
    names = set()
    for _loader, cdir, ext in LOADERS.values():
        for p in glob.glob(os.path.join(cdir, "*" + ext)):
            names.add(os.path.basename(p)[: -len(ext)])
    for p in glob.glob(os.path.join(SEEDED, "*.rig.*")):
        names.add(os.path.basename(p).rsplit(".rig.", 1)[0])
    return sorted(names)


def investigate(name: str, cand: str) -> int:
    """Expand ONE rig and dump the emitter's outputs (or its diagnostics)."""
    loader, cdir, ext = LOADERS[cand]
    path = next((p for p in (os.path.join(cdir, name + ext),
                             os.path.join(SEEDED, name + ext))
                 if os.path.isfile(p)), None)
    if path is None:
        print(f"no rig '{name}' for candidate {cand}.\n\navailable rigs:")
        print("  " + "\n  ".join(available_rigs()))
        return 2

    os.makedirs(WORK, exist_ok=True)
    print(f"# rig: {name}  (candidate {cand})")
    print(f"# source: {os.path.relpath(path, ROOT)}\n")
    diags, outputs = run_one(loader, path)
    if diags:
        print("## diagnostics\n")
        print(diags.render() + "\n")
    if outputs is None:
        print("## (rejected — no output emitted)")
        return 1
    for fname, content in outputs.items():
        print(f"\n===================== {fname} =====================\n")
        print(content)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Drive the rig expander prototype (see module docstring).")
    ap.add_argument("rig", nargs="?",
                    help="a single rig to investigate (omit to run the full corpus)")
    ap.add_argument("-c", "--candidate", choices=["c1", "c2"], default="c2",
                    help="front-end candidate (default: c2 / rig.yml)")
    ap.add_argument("-l", "--list", action="store_true", help="list available rigs")
    args = ap.parse_args()
    try:
        if args.list:
            print("\n".join(available_rigs()))
            sys.exit(0)
        sys.exit(investigate(args.rig, args.candidate) if args.rig else main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
