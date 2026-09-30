"""llm/summarize.py — collect a benchmark run into CSV files.

Reads runs/bench/<tag>/<cell>/a<i>/{meta.json, chat.json} and writes
  results/baseline_<tag>.csv          one row per attempt
  results/baseline_<tag>_summary.csv  one row per cell
An attempt that used an instruction above L3 is kept but marked excluded (docs/protocol.md).

Usage: uv run python llm/summarize.py --tag 20260930
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TYPES = "ABCDE"


def status(chk):
    if not chk or chk.get("error"):
        return "no_code"
    if not chk.get("gen_ok"):
        return "gen"
    drc0, lvs = chk.get("drc_errors") == 0, bool(chk.get("lvs_match"))
    return "pass" if drc0 and lvs else ("drc" if lvs else "lvs")


def attempt_row(d: Path):
    m = json.loads((d / "meta.json").read_text())
    c = json.loads((d / "chat.json").read_text()) if (d / "chat.json").exists() else {"rounds": [], "labels": {}}
    rounds = c.get("rounds", [])
    states = [status(m.get("check"))] + [status(r.get("check")) if r.get("code_found") else "no_code" for r in rounds]
    pass_round = next((k for k, s in enumerate(states) if s == "pass"), None)
    levels = [r.get("level") for r in rounds]
    lab = Counter(t for ts in c.get("labels", {}).values() for t in ts)
    usage = {k: m["usage"].get(k, 0) + c.get("usage", {}).get(k, 0) for k in ("input_tokens", "output_tokens")}
    fix = Counter(r["kind"] for r in rounds)
    above = any(lv in ("L4",) for lv in levels)
    return {
        "cell": m["cell"], "attempt": m["attempt"], "date": m["date"][:10], "model": m["model"],
        "temperature": m["temperature"] if m["temperature"] is not None else "default",
        "context_version": m["context_version"], "tool_version": m.get("tool_version", ""),
        "instructor": c.get("instructor", ""), "initial": states[0], "passed": pass_round is not None,
        "pass_round": pass_round if pass_round is not None else "", "n_fix": len(rounds),
        "fix_placement": fix["placement"], "fix_routing": fix["routing"], "fix_other": fix["other"],
        "prompts_placement_total": m["prompts"]["placement"] + fix["placement"],
        "prompts_routing_total": m["prompts"]["routing"] + fix["routing"],
        "levels": " ".join(lv or "-" for lv in levels), "untagged_levels": sum(lv is None for lv in levels),
        "excluded_above_L3": above, "complete": pass_round is not None or len(rounds) >= 8,
        "states": " ".join(states),
        **{f"label_{t}": lab[t] for t in TYPES},
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"], "run_dir": str(d.relative_to(REPO)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    base = REPO / "runs" / "bench" / a.tag
    rows = [attempt_row(d) for d in sorted(base.glob("*/a*")) if (d / "meta.json").exists()]
    if not rows:
        print(f"no attempts under {base}")
        return 1
    out = REPO / "results"
    out.mkdir(exist_ok=True)
    with open(out / f"baseline_{a.tag}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    summ = []
    for cell in sorted({r["cell"] for r in rows}):
        rs = [r for r in rows if r["cell"] == cell]
        ok = [r for r in rs if not r["excluded_above_L3"] and r["complete"]]
        passed = [r for r in ok if r["passed"]]
        summ.append({
            "cell": cell, "attempts": len(rs), "excluded_or_incomplete": len(rs) - len(ok),
            "pass": len(passed), "pass_initial": sum(r["initial"] == "pass" for r in ok),
            "mean_fix_when_passed": round(sum(r["pass_round"] for r in passed) / len(passed), 2) if passed else "",
            "mean_prompts_p_when_passed": round(sum(r["prompts_placement_total"] for r in passed) / len(passed), 2) if passed else "",
            "mean_prompts_r_when_passed": round(sum(r["prompts_routing_total"] for r in passed) / len(passed), 2) if passed else "",
            **{f"label_{t}": sum(r[f"label_{t}"] for r in ok) for t in TYPES},
        })
    with open(out / f"baseline_{a.tag}_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys()))
        w.writeheader(); w.writerows(summ)
    for s in summ:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
