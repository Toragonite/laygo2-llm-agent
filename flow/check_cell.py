"""Run one laygo2 generator through the whole flow and print a one-line JSON verdict.

    uv run python flow/check_cell.py --gen ref/golden/inv.py --cell inv_2x --ref ref/netlist/inv.spice \
        [--ref-cell inv_2x] [--out runs/inv_2x]

Stages (each writes its raw log into the out dir):
  1. gen    generator -> <out>/<cell>.tcl        (cwd = workspace root, PYTHONPATH=.:<repo> so laygo2_safe imports, LAYOUT_OUT_DIR=<out>)
  2. magic  flow/magic_drc_extract.tcl -> DRC count, bbox area, <out>/<cell>.spice      (magic.log, drc.txt)
  3. lvs    flow/lvs.sh extracted vs reference netlist                                   (lvs.log)
A stage that cannot run to completion stops the flow and leaves later fields null. DRC violations do not
stop it: extraction still works, so LVS runs and both results are recorded.
Exit code: 0 if gen_ok and drc_errors == 0 and lvs_match, else 1.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKSPACE = REPO / "third_party" / "laygo2_workspace_sky130"
FLOW = REPO / "flow"
TIMEOUT_S = {"gen": 300, "magic": 300, "lvs": 300}
TAIL_LINES = 40


def tail(text, n=TAIL_LINES):
    return "\n".join(text.strip().splitlines()[-n:])


def run(stage, cmd, cwd, env, log_path):
    """Run cmd, save stdout+stderr to log_path. Returns (returncode or None on timeout, output)."""
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           timeout=TIMEOUT_S[stage])
        rc, out = p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, out = None, out + f"\n[check_cell] {stage} timed out after {TIMEOUT_S[stage]}s\n"
    Path(log_path).write_text(out)
    return rc, out


def find_tcl(out, cell, since):
    """The generator's TCL: <out>/<cell>.tcl, else the only *.tcl in out. Must be newer than `since`."""
    fresh = [p for p in out.glob("*.tcl") if p.stat().st_mtime >= since]
    if (out / f"{cell}.tcl") in fresh:
        return out / f"{cell}.tcl", None
    if len(fresh) == 1:
        return fresh[0], None
    names = ", ".join(p.name for p in fresh) or "none"
    return None, f"expected {out / (cell + '.tcl')} (fresh *.tcl files in out: {names})"


def check_cell(gen, cell, ref, ref_cell, out):
    res = {"cell": cell, "gen_ok": False, "gen_error": None,
           "drc_errors": None, "drc_detail": None, "magic_error": None,
           "lvs_match": None, "lvs_result": None, "lvs_error": None,
           "area_um2": None, "runtime_s": None, "stage_s": {}, "failed_stage": None,
           "topcell": None, "gen": str(gen), "ref": str(ref), "ref_cell": ref_cell, "out_dir": str(out)}
    out.mkdir(parents=True, exist_ok=True)
    spice = out / f"{cell}.spice"
    for stale in (spice, out / "drc.txt", out / "result.json"):
        stale.unlink(missing_ok=True)
    env = dict(os.environ)
    env.setdefault("PDK_ROOT", str(Path.home() / "pdk"))
    t0 = time.time()

    def finish(failed_stage=None):
        res["failed_stage"] = failed_stage
        res["runtime_s"] = round(time.time() - t0, 2)
        return res

    # 1. gen: same interpreter as `uv run` (the project .venv), run from the workspace root.
    t = time.time()
    rc, log = run("gen", [sys.executable, gen], WORKSPACE,
                  {**env, "PYTHONPATH": f".{os.pathsep}{REPO}", "LAYOUT_OUT_DIR": str(out)}, out / "gen.log")
    res["stage_s"]["gen"] = round(time.time() - t, 2)
    if rc != 0:
        res["gen_error"] = tail(log)
        return finish("gen")
    tcl, err = find_tcl(out, cell, t0 - 1)
    if tcl is None:
        res["gen_error"] = f"generator exited 0 but wrote no TCL: {err}\n" + tail(log, 10)
        return finish("gen")
    res["gen_ok"] = True

    # 2. magic: one process for this cell; cwd = out so every .ext file lands in out.
    t = time.time()
    rc, log = run("magic", ["magic", "-dnull", "-noconsole", "-rcfile", FLOW / "maginit.tcl",
                            FLOW / "magic_drc_extract.tcl"], out,
                  {**env, "MAG_TCL": str(tcl), "MAG_OUT": str(out), "MAG_CELL": cell}, out / "magic.log")
    res["stage_s"]["magic"] = round(time.time() - t, 2)
    kv = dict(m.groups() for m in re.finditer(r"^(TOPCELL|AREA_UM2|DRC_COUNT|FLOW_ERROR) (.*)$", log, re.M))
    res["topcell"] = kv.get("TOPCELL")
    if "AREA_UM2" in kv:
        res["area_um2"] = float(kv["AREA_UM2"])
    if "DRC_COUNT" in kv:
        res["drc_errors"] = int(kv["DRC_COUNT"])
        if res["drc_errors"] > 0 and (out / "drc.txt").exists():
            res["drc_detail"] = (out / "drc.txt").read_text().strip()
    if rc != 0 or "FLOW_ERROR" in kv or not re.search(r"^FLOW_DONE$", log, re.M) or not spice.exists():
        head = f"FLOW_ERROR {kv['FLOW_ERROR']}\n" if "FLOW_ERROR" in kv else f"magic exit={rc}, no FLOW_DONE\n"
        res["magic_error"] = head + tail(log)
        return finish("magic")

    # 3. lvs: extracted top cell (e.g. logic_ver2_inv_2x) vs reference subckt.
    t = time.time()
    rc, log = run("lvs", [FLOW / "lvs.sh", spice, res["topcell"], ref, ref_cell, out / "lvs.log"],
                  out, env, out / "lvs_run.log")
    res["stage_s"]["lvs"] = round(time.time() - t, 2)
    m = re.search(r"^LVS_RESULT (\w+)$", log, re.M)
    res["lvs_result"] = m.group(1) if m else "error"
    if res["lvs_result"] == "error":
        res["lvs_error"] = tail(log)
        return finish("lvs")
    res["lvs_match"] = res["lvs_result"] == "match"
    if not res["lvs_match"]:
        report = (out / "lvs.log").read_text(errors="replace") if (out / "lvs.log").exists() else log
        res["lvs_error"] = tail(report, 60)
    return finish()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gen", required=True, type=Path, help="generator .py (laygo2 script)")
    ap.add_argument("--cell", required=True, help="cell name, e.g. inv_2x (TCL = <out>/<cell>.tcl)")
    ap.add_argument("--ref", required=True, type=Path, help="reference SPICE netlist")
    ap.add_argument("--ref-cell", help="subckt name in --ref (default: --cell)")
    ap.add_argument("--out", type=Path, help="output dir (default: runs/<cell>/)")
    a = ap.parse_args()
    gen, ref = a.gen.resolve(), a.ref.resolve()
    for p in (gen, ref):
        if not p.is_file():
            ap.error(f"file not found: {p}")
    out = (a.out or REPO / "runs" / a.cell).resolve()

    res = check_cell(gen, a.cell, ref, a.ref_cell or a.cell, out)
    (out / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(res, ensure_ascii=False))
    ok = res["gen_ok"] and res["drc_errors"] == 0 and res["lvs_match"]
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
