"""llm/chat.py — interactive modification of a generated layout (the paper's "Describe Modification
Instructions" loop, Fig. 3-4).

Continues the conversation of a run made by llm/generate.py. You read the result, type an instruction,
the LLM answers, and if the answer contains a python block it is saved and judged with flow/check_cell.py.
chat.py never writes DRC/LVS results into the conversation by itself: only what you type is sent.

Tag each instruction with the operation it is about, so prompts can be counted like the paper's Table II,
and with its specificity level (docs/protocol.md; the baseline allows up to L3):
  p: [L2] <text>   placement instruction, level L2
  r: [L3] <text>   routing instruction, level L3
  <text>           counted as "other"
The level tag is removed before the text is sent to the LLM.
Commands:
  /status                 last result
  /label [k] A,C          failure types of round k (0 = the generate.py result; default: latest round),
                          one or more of A-E from docs/protocol.md
  /quit

Usage:
  uv run python llm/chat.py --run runs/llm/nand_2x/<run_dir>
  uv run python llm/chat.py --run <run_dir> --script instructions.txt     # instructions separated by "---" lines
  uv run python llm/chat.py --run <run_dir> --provider mock --mock-reply ref/golden/nand.py --script s.txt

Output (inside the run directory): chat_<k>_user.md, chat_<k>_llm.md, gen_<k>.py, check_<k>/ and
chat.json (instructions, prompt counts, every check result, the final verdict).
"""
import argparse
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import MockChat, OpenAIChat, extract_python, run_check  # noqa: E402

KINDS = {"p:": "placement", "r:": "routing"}
LEVELS = {"L1", "L2", "L3", "L4"}
FAILURE_TYPES = {"A", "B", "C", "D", "E"}  # docs/protocol.md
MAX_LEVEL = "L3"


def verdict(chk):
    if not chk:
        return "no code yet"
    if chk.get("error"):
        return "check error"
    if not chk.get("gen_ok"):
        return f"gen failed ({chk.get('failed_stage')})"
    return f"drc_errors={chk.get('drc_errors')} lvs={chk.get('lvs_result')}"


def passed(chk):
    return bool(chk) and chk.get("gen_ok") and chk.get("drc_errors") == 0 and chk.get("lvs_match")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run directory made by llm/generate.py")
    ap.add_argument("--provider", choices=["openai", "mock"], default=None, help="default: the run's provider")
    ap.add_argument("--mock-reply", help="file returned as the script by --provider mock")
    ap.add_argument("--script", help="read instructions from this file instead of the keyboard")
    ap.add_argument("--instructor", default="human", help="who writes the instructions (recorded in chat.json)")
    a = ap.parse_args()

    run = Path(a.run).resolve()
    meta = json.loads((run / "meta.json").read_text())
    tr = json.loads((run / "transcript.json").read_text())
    system, messages = tr["system"], tr["messages"]
    cell, netlist = meta["cell"], meta["netlist"]
    provider = a.provider or meta["provider"]
    chat = MockChat(a.mock_reply) if provider == "mock" else \
        OpenAIChat(meta["model"], meta["temperature"], meta["max_tokens"])

    log_path = run / "chat.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {
        "cell": cell, "model": meta["model"], "context_version": meta["context_version"], "instructor": a.instructor,
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "prompts": {"placement": 0, "routing": 0, "other": 0}, "rounds": [], "usage": {"input_tokens": 0, "output_tokens": 0}}
    log.setdefault("labels", {})
    last = log["rounds"][-1]["check"] if log["rounds"] else meta.get("check")
    print(f"[{cell}] model={meta['model']} context={meta['context_version']} | start: {verdict(last)}")

    # Script mode: instructions are separated by lines that contain only "---", so one instruction
    # may span several lines and still counts as one prompt.
    lines = None
    if a.script:
        blocks, cur = [], []
        for ln in Path(a.script).read_text().splitlines():
            if ln.strip() == "---":
                blocks.append("\n".join(cur)); cur = []
            else:
                cur.append(ln)
        blocks.append("\n".join(cur))
        lines = [b.strip() for b in blocks if b.strip()]
    while True:
        if lines is not None:
            if not lines:
                break
            text = lines.pop(0)
            print(f"> {text}")
        else:
            try:
                text = input("> ").strip()
            except EOFError:
                break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/status":
            print(verdict(last))
            continue
        if text.startswith("/label"):
            parts = text.split()
            k_lab = int(parts[1]) if len(parts) == 3 else len(log["rounds"])
            types = sorted({t.strip().upper() for t in parts[-1].split(",") if t.strip()})
            if len(parts) < 2 or not types or not set(types) <= FAILURE_TYPES:
                print(f"usage: /label [k] A,C   (types: {','.join(sorted(FAILURE_TYPES))})")
                continue
            log["labels"][str(k_lab)] = types
            log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
            print(f"round {k_lab}: {types}")
            continue

        kind = next((k for p, k in KINDS.items() if text.startswith(p)), "other")
        body = text.split(":", 1)[1].strip() if kind != "other" else text
        level = None
        if body[:1] == "[" and body[1:4].rstrip("]") in LEVELS and body[3:4] == "]":
            level, body = body[1:3], body[4:].strip()
        if kind != "other" and level is None:
            print("note: no level tag ([L1]-[L4]); recorded as null")
        if level and level > MAX_LEVEL:
            print(f"warning: {level} is above the baseline limit {MAX_LEVEL}")
        k = len(log["rounds"]) + 1
        messages.append({"role": "user", "content": body})
        (run / f"chat_{k}_user.md").write_text(body)
        t0 = time.time()
        try:
            reply, usage = chat.send(system, messages)
        except Exception as e:
            messages.pop()
            print(f"LLM error: {type(e).__name__}: {e}")
            continue
        messages.append({"role": "assistant", "content": reply})
        (run / f"chat_{k}_llm.md").write_text(reply)
        for key in usage:
            log["usage"][key] = log["usage"].get(key, 0) + usage[key]
        log["prompts"][kind] += 1

        code = extract_python(reply)
        chk = None
        if code is not None:
            gen = run / f"gen_{k}.py"
            gen.write_text(code)
            chk = run_check(gen, cell, netlist, run / f"check_{k}")
            last = chk
        print(reply if code is None else f"(code saved: gen_{k}.py) {verdict(chk)}")
        log["rounds"].append({"k": k, "kind": kind, "level": level, "instruction": body, "code_found": code is not None,
                              "llm_s": round(time.time() - t0, 2), "check": chk})
        log["final"] = {"verdict": verdict(last), "passed": passed(last)}
        log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
        (run / "transcript.json").write_text(json.dumps({"system": system, "messages": messages},
                                                        indent=2, ensure_ascii=False) + "\n")
        if passed(chk):
            print("PASS: drc_errors 0, lvs match")

    print(json.dumps({"cell": cell, "prompts": log["prompts"], "final": log.get("final"), "labels": log["labels"],
                      "run_dir": str(run)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
