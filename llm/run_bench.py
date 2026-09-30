"""llm/run_bench.py — run llm/generate.py for every task and attempt in bench/tasks.yaml.

This is only the automatic part (the 6 context turns and one check per attempt). Fix instructions are
added afterwards per attempt with llm/chat.py, following docs/protocol.md.

Usage:
  uv run python llm/run_bench.py --tag 20260930 [--only inv,nand] [--jobs 3] [--dry-run]
Output: runs/bench/<tag>/<cell>/a<i>/ (one generate.py run directory per attempt).
An attempt whose meta.json already exists is skipped, so an interrupted run can be resumed.
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", default=str(REPO / "bench" / "tasks.yaml"))
    ap.add_argument("--tag", required=True, help="name of this benchmark run, e.g. a date")
    ap.add_argument("--only", help="comma-separated task ids")
    ap.add_argument("--jobs", type=int, default=3, help="attempts run in parallel")
    ap.add_argument("--dry-run", action="store_true", help="pass --dry-run to generate.py (no API calls)")
    a = ap.parse_args()

    spec = yaml.safe_load(Path(a.tasks).read_text())
    d = spec["defaults"]
    only = set(a.only.split(",")) if a.only else None
    jobs = []
    for t in spec["tasks"]:
        if only and t["id"] not in only:
            continue
        for i in range(1, d["attempts"] + 1):
            out = REPO / "runs" / "bench" / a.tag / t["cell"] / f"a{i}"
            if (out / "meta.json").exists() and not a.dry_run:
                continue
            cmd = [sys.executable, str(REPO / "llm" / "generate.py"), "--cell", t["cell"],
                   "--netlist", str(REPO / t["netlist"]), "--model", d["model"], "--attempt", str(i),
                   "--placement-rules", d["placement_rules"], "--routing-rules", d["routing_rules"],
                   "--out", str(out)]
            if d.get("temperature") is not None:
                cmd += ["--temperature", str(d["temperature"])]
            if a.dry_run:
                cmd.append("--dry-run")
            jobs.append((t["cell"], i, cmd))

    def run(job):
        cell, i, cmd = job
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        last = (p.stdout.strip().splitlines() or ["{}"])[-1]
        try:
            r = json.loads(last)
        except json.JSONDecodeError:
            r = {"error": p.stderr[-500:]}
        print(f"{cell} a{i}: gen_ok={r.get('gen_ok')} drc={r.get('drc_errors')} lvs={r.get('lvs_result')} "
              f"err={r.get('llm_error') or r.get('error')}", flush=True)
        return r

    print(f"{len(jobs)} attempts to run")
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(run, jobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
