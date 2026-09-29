"""llm/generate.py — SPICE netlist -> laygo2 generator code through a multi-turn LLM conversation.

Sends llm/context/system.md and llm/context/turns/*.md in order (paper Fig. 3-4), saves every turn,
takes the python block of the last reply as gen.py and judges it once with flow/check_cell.py.
A failed check is only recorded. Nothing is sent back to the LLM (automatic feedback is out of scope).

Usage:
  uv run python llm/generate.py --cell nand_2x --netlist ref/netlist/nand.spice --model <gpt model id>
  uv run python llm/generate.py --cell nand_2x --netlist ref/netlist/nand.spice --dry-run
  uv run python llm/generate.py --cell nand_2x --netlist ref/netlist/nand.spice \
      --provider mock --mock-reply ref/golden/nand.py        # pipeline test, not an experiment

Output: runs/llm/<cell>/<timestamp>_<model>/ with system.md, turn_<i>_user.md, turn_<i>_llm.md,
gen.py, check/ (check_cell output), meta.json. The last stdout line is one JSON summary.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTEXT = REPO / "llm" / "context"
# Turns 1-3 teach and perform placement, 4-6 routing (see llm/context/README.md).
PLACEMENT_TURNS = {1, 2, 3}


def strip_comments(netlist: str) -> str:
    """Drop SPICE comment lines: the reference netlists carry layout hints in comments."""
    keep = [ln for ln in netlist.splitlines() if ln.strip() and not ln.lstrip().startswith("*")]
    return "\n".join(keep)


def render(text: str, values: dict) -> str:
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        raise ValueError(f"unfilled placeholders: {left}")
    return text


def context_version() -> str:
    """Last commit that touched llm/context, plus '-dirty' if it has uncommitted changes."""
    h = subprocess.run(["git", "log", "-1", "--format=%h", "--", "llm/context"],
                       cwd=REPO, capture_output=True, text=True).stdout.strip() or "none"
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "llm/context"],
                           cwd=REPO, capture_output=True, text=True).stdout.strip()
    return h + ("-dirty" if dirty else "")


def extract_python(reply: str):
    blocks = re.findall(r"```python\s*\n(.*?)```", reply, re.S)
    return blocks[-1] if blocks else None


class OpenAIChat:
    """OpenAI Chat Completions. The key comes from OPENAI_API_KEY (environment or the repo's .env)."""
    def __init__(self, model, temperature, max_tokens):
        import openai
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
        self.client = openai.OpenAI()
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens

    def send(self, system, messages):
        kw = dict(model=self.model, max_completion_tokens=self.max_tokens,
                  messages=[{"role": "system", "content": system}] + messages)
        if self.temperature is not None:  # some reasoning models reject temperature, so only send it when set
            kw["temperature"] = self.temperature
        resp = self.client.chat.completions.create(**kw)
        text = resp.choices[0].message.content or ""
        return text, {"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens}


class MockChat:
    """Answers 'OK' to every turn and returns a given file as the final script. For pipeline tests only."""
    def __init__(self, reply_file, n_turns):
        self.code, self.n_turns, self.calls = Path(reply_file).read_text(), n_turns, 0

    def send(self, system, messages):
        self.calls += 1
        if self.calls == self.n_turns:
            return "```python\n" + self.code + "```", {"input_tokens": 0, "output_tokens": 0}
        return "OK", {"input_tokens": 0, "output_tokens": 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", required=True, help="cell name, e.g. nand_2x")
    ap.add_argument("--netlist", required=True, help="reference SPICE netlist (also the LVS reference)")
    ap.add_argument("--placement-rules", default="(none)", help="design-specific placement rules text")
    ap.add_argument("--routing-rules", default="(none)", help="design-specific routing rules text")
    ap.add_argument("--provider", choices=["openai", "mock"], default="openai")
    ap.add_argument("--model", default=None, help="model id (required for --provider openai)")
    ap.add_argument("--temperature", type=float, default=None, help="omit to use the provider default")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--attempt", type=int, default=1, help="index of this run when repeating a task")
    ap.add_argument("--mock-reply", help="file returned as the final script by --provider mock")
    ap.add_argument("--out", help="run directory (default runs/llm/<cell>/<timestamp>_<model>/)")
    ap.add_argument("--dry-run", action="store_true", help="write the rendered prompts and stop")
    a = ap.parse_args()

    netlist_path = Path(a.netlist).resolve()
    values = {"cell": a.cell, "netlist": strip_comments(netlist_path.read_text()),
              "task_placement_rules": a.placement_rules, "task_routing_rules": a.routing_rules}
    system = render((CONTEXT / "system.md").read_text(), values)
    turn_files = sorted((CONTEXT / "turns").glob("*.md"))
    turns = [render(f.read_text(), values) for f in turn_files]

    model = a.model or ("mock" if a.provider == "mock" else None)
    if model is None and not a.dry_run:
        ap.error("--model is required for --provider openai")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run = Path(a.out).resolve() if a.out else REPO / "runs" / "llm" / a.cell / f"{stamp}_{model or 'dry'}"
    run.mkdir(parents=True, exist_ok=True)
    (run / "system.md").write_text(system)
    for i, t in enumerate(turns, 1):
        (run / f"turn_{i}_user.md").write_text(t)

    meta = {"cell": a.cell, "netlist": str(netlist_path), "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "provider": a.provider, "model": model, "temperature": a.temperature, "max_tokens": a.max_tokens,
            "context_version": context_version(), "attempt": a.attempt,
            "placement_rules": a.placement_rules, "routing_rules": a.routing_rules,
            "prompts": {"placement": sum(1 for i in range(1, len(turns) + 1) if i in PLACEMENT_TURNS),
                        "routing": sum(1 for i in range(1, len(turns) + 1) if i not in PLACEMENT_TURNS)},
            "turn_files": [f.name for f in turn_files], "usage": {"input_tokens": 0, "output_tokens": 0},
            "llm_error": None, "code_found": None, "check": None, "run_dir": str(run)}

    def save():
        (run / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    if a.dry_run:
        save()
        print(json.dumps({"cell": a.cell, "dry_run": True, "run_dir": str(run), "turns": len(turns)}))
        return 0

    try:
        chat = MockChat(a.mock_reply, len(turns)) if a.provider == "mock" else \
            OpenAIChat(model, a.temperature, a.max_tokens)
    except Exception as e:  # e.g. OPENAI_API_KEY not set
        meta["llm_error"] = f"client setup: {type(e).__name__}: {e}"
        save()
        print(json.dumps({"cell": a.cell, "model": model, "llm_error": meta["llm_error"], "run_dir": str(run)}))
        return 2

    t0 = time.time()
    messages, reply = [], ""
    for i, t in enumerate(turns, 1):
        messages.append({"role": "user", "content": t})
        try:
            reply, usage = chat.send(system, messages)
        except Exception as e:  # keep the turns done so far
            meta["llm_error"] = f"turn {i}: {type(e).__name__}: {e}"
            break
        messages.append({"role": "assistant", "content": reply})
        (run / f"turn_{i}_llm.md").write_text(reply)
        for k in usage:
            meta["usage"][k] += usage[k]
    meta["llm_s"] = round(time.time() - t0, 2)
    (run / "transcript.json").write_text(json.dumps({"system": system, "messages": messages},
                                                    indent=2, ensure_ascii=False) + "\n")

    code = None if meta["llm_error"] else extract_python(reply)
    meta["code_found"] = code is not None
    if code is not None:
        (run / "gen.py").write_text(code)
        proc = subprocess.run([sys.executable, str(REPO / "flow" / "check_cell.py"), "--gen", str(run / "gen.py"),
                               "--cell", a.cell, "--ref", str(netlist_path), "--out", str(run / "check")],
                              cwd=REPO, capture_output=True, text=True)
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        meta["check"] = json.loads(lines[-1]) if lines else {"error": proc.stderr[-2000:]}
    save()

    chk = meta["check"] or {}
    print(json.dumps({"cell": a.cell, "model": model, "context_version": meta["context_version"],
                      "llm_error": meta["llm_error"], "code_found": meta["code_found"],
                      "gen_ok": chk.get("gen_ok"), "drc_errors": chk.get("drc_errors"),
                      "lvs_result": chk.get("lvs_result"), "run_dir": str(run)}, ensure_ascii=False))
    return 0 if chk.get("gen_ok") and chk.get("drc_errors") == 0 and chk.get("lvs_match") else 1


if __name__ == "__main__":
    sys.exit(main())
