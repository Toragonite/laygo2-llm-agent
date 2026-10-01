"""llm/selfheal.py — automatic repair loop: feed the tool results back to the LLM, no human in between.

For each attempt made by llm/generate.py, while the last script fails and rounds remain:
  1. build a feedback message from the tool outputs only (L1 information): the traceback / SafeError
     line when the script crashed, the script's own CHECK lines, DRC rule names with boxes, the netgen
     net/device counts and pin mismatches
  2. send it as the next user turn, save the reply's python block, judge it with flow/check_cell.py
Rounds are recorded in chat.json exactly like llm/chat.py (kind "other", level "L1", instructor
"auto-feedback-v1"), so llm/summarize.py aggregates them the same way.

Feedback variants (--feedback):
  v1  tool output only
  v2  v1 plus a list of every problem seen so far (open / fixed / back again)  -> no effect (v3b)
  v3  v1 plus, only when the failure state flipped (crash -> LVS mismatch or back), the unified diff
      between the previous script and the latest one, so the fix for the new problem keeps the old fix

Usage:
  uv run python llm/selfheal.py --tag v3_selfheal [--max-rounds 8] [--only inv,nand]
  uv run python llm/selfheal.py --run runs/bench/<tag>/<cell>/a1
"""
import argparse
import datetime
import difflib
import glob
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import OpenAIChat, extract_python, run_check  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FEEDBACK = "v1"   # set from --feedback


def facts_of(chk, check_dir: Path) -> list:
    """Short normalized problem lines of one check, used as the constraint memory (feedback v2)."""
    out = []
    if not chk or chk.get("error"):
        return out
    if not chk.get("gen_ok"):
        err = [ln for ln in (chk.get("gen_error") or "").strip().splitlines() if ln.strip()]
        if err:
            out.append("crash: " + err[-1].strip()[:160])
        return out
    gen_log = check_dir / "gen.log"
    if gen_log.exists():
        out += [ln.strip()[:160] for ln in gen_log.read_text().splitlines() if ln.startswith("CHECK:")][:8]
    if chk.get("drc_errors"):
        drc = (check_dir / "drc.txt").read_text().splitlines() if (check_dir / "drc.txt").exists() else []
        out += ["DRC: " + ln.strip()[:120] for ln in drc if ln and not ln.startswith("    box")][:4]
    if not chk.get("lvs_match"):
        out.append(f"LVS: {chk.get('lvs_result')}")
    return out


def passed(chk):
    return bool(chk) and chk.get("gen_ok") and chk.get("drc_errors") == 0 and bool(chk.get("lvs_match"))


def state_of(chk) -> str:
    """The failure state of one check: crash / drc / lvs / pass."""
    if passed(chk):
        return "pass"
    if not chk or chk.get("error") or not chk.get("gen_ok"):
        return "crash"
    if chk.get("drc_errors"):
        return "drc"
    return "lvs"


STATE_WORDS = {"crash": "a crash while running", "drc": "DRC errors", "lvs": "an LVS mismatch", "pass": "a pass"}
DIFF_MAX_LINES = 120


def feedback_v3(chk, check_dir: Path, run: Path, k: int, prev_chk):
    """v1 message plus, only when the failure state flipped between the last two scripts, the unified
    diff between them. Returns (text, diff_included). Script of round j is gen_j.py (gen.py for j = 0);
    at round k the last script is gen_{k-1} and the previous one gen_{k-2}."""
    base = feedback(chk, check_dir)
    if k < 2 or prev_chk is None:
        return base, False
    s_prev, s_last = state_of(prev_chk), state_of(chk)
    if s_prev == s_last:
        return base, False
    prev_path = run / ("gen.py" if k - 2 == 0 else f"gen_{k - 2}.py")
    last_path = run / f"gen_{k - 1}.py"
    if not prev_path.exists() or not last_path.exists():
        return base, False
    diff = list(difflib.unified_diff(prev_path.read_text().splitlines(), last_path.read_text().splitlines(),
                                     fromfile="previous script", tofile="latest script", lineterm="", n=1))
    if len(diff) > DIFF_MAX_LINES:
        diff = diff[:DIFF_MAX_LINES] + [f"... ({len(diff) - DIFF_MAX_LINES} more diff lines)"]
    head = base.rsplit("\n\n", 1)[0]
    text = (head + f"\n\nYour latest script changed the failure from {STATE_WORDS[s_prev]} to {STATE_WORDS[s_last]}. "
            "This is what you changed between the previous script and the latest one:\n```diff\n"
            + "\n".join(diff) + "\n```\n"
            "Do not undo what the previous script already had right, and keep the change that fixed the earlier problem; "
            "fix the current problems on top of that.\n\n"
            "Fix the problems and output the complete corrected script.")
    return text, True


def feedback(chk, check_dir: Path) -> str:
    """The feedback message: tool facts only, then a fixed request."""
    parts = []
    if not chk or chk.get("error"):
        parts.append("The checker could not run your script: " + str((chk or {}).get("error", ""))[-600:])
    elif not chk.get("gen_ok"):
        err = (chk.get("gen_error") or "").strip().splitlines()
        tail = [ln for ln in err if ln.strip()][-4:]
        parts.append("The script failed while running:\n" + "\n".join(tail))
    else:
        checks = []
        gen_log = check_dir / "gen.log"
        if gen_log.exists():
            checks = [ln for ln in gen_log.read_text().splitlines() if ln.startswith("CHECK:")]
        if checks:
            parts.append("The script's own check() reported:\n" + "\n".join(checks[:12]))
        if chk.get("drc_errors"):
            drc = (check_dir / "drc.txt").read_text().splitlines() if (check_dir / "drc.txt").exists() else []
            parts.append(f"DRC: {chk['drc_errors']} error(s):\n" + "\n".join(drc[:10]))
        if not chk.get("lvs_match"):
            lvs = (check_dir / "lvs.log").read_text() if (check_dir / "lvs.log").exists() else ""
            lines = [ln for ln in lvs.splitlines() if re.search(r"Number of (nets|devices)|Mismatch|no matching|Property error", ln)]
            parts.append(f"LVS result: {chk.get('lvs_result')}.\n" + "\n".join(lines[:14]))
            ext = check_dir / f"{chk.get('cell')}.spice"
            if ext.exists():
                sub = ext.read_text()
                m = re.search(r"\.subckt logic_ver2_\S+.*?\.ends", sub, re.S)
                if m:
                    parts.append("Extracted netlist of your layout (template subcells flattened by netgen):\n" + m.group(0)[:1500])
    parts.append("Fix the problems and output the complete corrected script.")
    return "\n\n".join(parts)


def feedback_v2(chk, check_dir: Path, memory: list, k: int) -> str:
    """v1 message plus a constraint memory: everything found in earlier rounds, marked as still open,
    fixed, or back again, so that a fix does not undo an earlier one."""
    now = facts_of(chk, check_dir)
    base = feedback(chk, check_dir)
    lines = []
    for item in memory:
        if item["fact"] in now:
            status = "STILL OPEN" if item["last_seen"] == k - 1 else "BACK AGAIN (it was fixed before)"
        else:
            status = "fixed, keep it that way"
        lines.append(f"- [{status}] {item['fact']}")
    for f in now:
        if not any(m["fact"] == f for m in memory):
            memory.append({"fact": f, "first_seen": k, "last_seen": k})
        else:
            next(m for m in memory if m["fact"] == f)["last_seen"] = k
    if not lines:
        return base
    head = base.rsplit("\n\n", 1)[0]
    return (head + "\n\nHistory of problems in this conversation (do not reintroduce a fixed one):\n" + "\n".join(lines)
            + "\n\nFix the open problems while keeping everything that already works, and output the complete corrected script.")


def heal(run: Path, max_rounds: int) -> dict:
    meta = json.loads((run / "meta.json").read_text())
    tr = json.loads((run / "transcript.json").read_text())
    system, messages = tr["system"], tr["messages"]
    cell, netlist = meta["cell"], meta["netlist"]
    log_path = run / "chat.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {
        "cell": cell, "model": meta["model"], "context_version": meta["context_version"], "instructor": f"auto-feedback-{FEEDBACK}",
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "prompts": {"placement": 0, "routing": 0, "other": 0}, "rounds": [], "labels": {},
        "usage": {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}}
    last = log["rounds"][-1]["check"] if log["rounds"] else meta.get("check")
    last_dir = run / (f"check_{log['rounds'][-1]['k']}" if log["rounds"] else "check")
    chat = OpenAIChat(meta["model"], meta["temperature"], meta["max_tokens"])
    memory = log.setdefault("memory", [])
    if FEEDBACK == "v2" and not log["rounds"]:
        for f in facts_of(last, last_dir):
            memory.append({"fact": f, "first_seen": 0, "last_seen": 0})
    while not passed(last) and len(log["rounds"]) < max_rounds:
        k = len(log["rounds"]) + 1
        diff_included = False
        if FEEDBACK == "v2":
            text = feedback_v2(last, last_dir, memory, k)
        elif FEEDBACK == "v3":
            rounds = log["rounds"]
            prev = rounds[-2]["check"] if len(rounds) >= 2 else (meta.get("check") if len(rounds) == 1 else None)
            text, diff_included = feedback_v3(last, last_dir, run, k, prev)
        else:
            text = feedback(last, last_dir)
        messages.append({"role": "user", "content": text})
        (run / f"auto_{k}_user.md").write_text(text)
        t0 = time.time()
        try:
            reply, usage = chat.send(system, messages)
        except Exception as e:
            messages.pop()
            print(f"  {cell} round {k}: LLM error {type(e).__name__}: {e}")
            break
        messages.append({"role": "assistant", "content": reply})
        (run / f"chat_{k}_llm.md").write_text(reply)
        for key in usage:
            log["usage"][key] = log["usage"].get(key, 0) + usage[key]
        log["prompts"]["other"] += 1
        code = extract_python(reply)
        chk = None
        if code is not None:
            gen = run / f"gen_{k}.py"
            gen.write_text(code)
            chk = run_check(gen, cell, netlist, run / f"check_{k}")
            last, last_dir = chk, run / f"check_{k}"
        log["rounds"].append({"k": k, "kind": "other", "level": "L1", "auto": True, "instruction": text,
                              "diff_included": diff_included,
                              "code_found": code is not None, "llm_s": round(time.time() - t0, 2), "check": chk})
        log["final"] = {"verdict": "pass" if passed(last) else "fail", "passed": passed(last)}
        log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
        (run / "transcript.json").write_text(json.dumps({"system": system, "messages": messages}, indent=2, ensure_ascii=False) + "\n")
        state = "PASS" if passed(chk) else ("gen" if not (chk or {}).get("gen_ok") else f"drc={chk.get('drc_errors')} lvs={chk.get('lvs_result')}")
        print(f"  {cell} {run.name} round {k}: {state}", flush=True)
    if not log["rounds"] and passed(last):
        log["final"] = {"verdict": "pass", "passed": True}
        log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
    return {"cell": cell, "attempt": run.name, "rounds": len(log["rounds"]), "passed": passed(last)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="heal every attempt under runs/bench/<tag>/")
    ap.add_argument("--run", help="one attempt directory")
    ap.add_argument("--only", help="comma-separated cell names (with --tag)")
    ap.add_argument("--max-rounds", type=int, default=8)
    ap.add_argument("--feedback", choices=["v1", "v2", "v3"], default="v1",
                    help="v1: tool output only; v2: plus a history of problems; v3: plus the script diff when the failure state flips")
    a = ap.parse_args()
    global FEEDBACK
    FEEDBACK = a.feedback
    runs = [Path(a.run).resolve()] if a.run else sorted(Path(p) for p in glob.glob(str(REPO / "runs" / "bench" / a.tag / "*" / "a*")))
    only = set(a.only.split(",")) if a.only else None
    results = []
    for r in runs:
        if only and json.loads((r / "meta.json").read_text())["cell"].split("_")[0] not in only:
            continue
        results.append(heal(r, a.max_rounds))
    n_pass = sum(r["passed"] for r in results)
    print(json.dumps({"attempts": len(results), "passed": n_pass, "rounds": sum(r["rounds"] for r in results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
