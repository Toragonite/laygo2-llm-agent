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
CONTEXT = REPO / "llm" / "context"        # default; --context selects another directory (e.g. llm/context_safe)
# Turns 1-3 teach and perform placement, 4-6 routing (see llm/context/README.md).
PLACEMENT_TURNS = {1, 2, 3}


def strip_comments(netlist: str) -> str:
    """Drop SPICE comment lines: the reference netlists carry layout hints in comments."""
    keep = [ln for ln in netlist.splitlines() if ln.strip() and not ln.lstrip().startswith("*")]
    return "\n".join(keep)


def normalize_devices(netlist: str) -> str:
    """Rename device instances to XM1, XM2, ... in order, so no task leaks layout instance names
    (some reference netlists use the golden layout's names such as XMN0). LVS still uses the original file."""
    out, i = [], 0
    for ln in netlist.splitlines():
        if ln[:1] in ("X", "x", "M", "m") and not ln.lower().startswith(".model"):
            i += 1
            ln = f"XM{i} " + ln.split(None, 1)[1]
        out.append(ln)
    return "\n".join(out)


def tool_version() -> str:
    """Last commit that touched the generation/judging code, plus '-dirty' if uncommitted."""
    paths = ["llm/generate.py", "llm/chat.py", "flow"]
    h = subprocess.run(["git", "log", "-1", "--format=%h", "--", *paths],
                       cwd=REPO, capture_output=True, text=True).stdout.strip() or "none"
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *paths],
                           cwd=REPO, capture_output=True, text=True).stdout.strip()
    return h + ("-dirty" if dirty else "")


def render(text: str, values: dict) -> str:
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        raise ValueError(f"unfilled placeholders: {left}")
    return text


def context_version(context_dir=None) -> str:
    """Last commit that touched the context directory, plus '-dirty' if it has uncommitted changes."""
    rel = str((context_dir or CONTEXT).resolve().relative_to(REPO))
    h = subprocess.run(["git", "log", "-1", "--format=%h", "--", rel],
                       cwd=REPO, capture_output=True, text=True).stdout.strip() or "none"
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel],
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
        # The account's rate limit is 30k tokens/min for gpt-4o: let the SDK wait and retry on 429
        # (it honours the retry-after header) instead of failing the attempt.
        self.client = openai.OpenAI(max_retries=10)
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens

    def send(self, system, messages):
        kw = dict(model=self.model, max_completion_tokens=self.max_tokens,
                  messages=[{"role": "system", "content": system}] + messages,
                  store=False)   # do not keep prompts/replies on OpenAI's side (dashboard "Logs")
        if self.temperature is not None:  # some reasoning models reject temperature, so only send it when set
            kw["temperature"] = self.temperature
        resp = self.client.chat.completions.create(**kw)
        text = resp.choices[0].message.content or ""
        # Prompt caching (gpt-4o-2024-08-06 and later): the unchanged prefix of a multi-turn conversation is
        # billed at the cached rate. cached_tokens is part of prompt_tokens, recorded here to check hits.
        det = getattr(resp.usage, "prompt_tokens_details", None)
        cached = getattr(det, "cached_tokens", 0) or 0
        return text, {"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens,
                      "cached_tokens": cached}


class MockChat:
    """Answers 'OK' and returns a given file as the script on call n_turns (every call if None).
    For pipeline tests only."""
    def __init__(self, reply_file, n_turns=None):
        self.code, self.n_turns, self.calls = Path(reply_file).read_text(), n_turns, 0

    def send(self, system, messages):
        self.calls += 1
        if self.n_turns is None or self.calls == self.n_turns:
            return "```python\n" + self.code + "```", {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
        return "OK", {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}


def run_check(gen, cell, netlist, out):
    """Judge one generator with flow/check_cell.py and return its JSON result."""
    proc = subprocess.run([sys.executable, str(REPO / "flow" / "check_cell.py"), "--gen", str(gen),
                           "--cell", cell, "--ref", str(netlist), "--out", str(out)],
                          cwd=REPO, capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    return json.loads(lines[-1]) if lines else {"error": proc.stderr[-2000:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", required=True, help="cell name, e.g. nand_2x")
    ap.add_argument("--netlist", required=True, help="reference SPICE netlist (also the LVS reference)")
    ap.add_argument("--placement-rules", default="(none)", help="design-specific placement rules text")
    ap.add_argument("--routing-rules", default="(none)", help="design-specific routing rules text")
    ap.add_argument("--provider", choices=["openai", "mock"], default="openai")
    ap.add_argument("--model", default=None, help="model id (required for --provider openai)")
    ap.add_argument("--temperature", type=float, default=None, help="omit to use the provider default")
    ap.add_argument("--max-tokens", type=int, default=4096, help="gpt-4o-2024-05-13 allows at most 4096")
    ap.add_argument("--attempt", type=int, default=1, help="index of this run when repeating a task")
    ap.add_argument("--mock-reply", help="file returned as the final script by --provider mock")
    ap.add_argument("--out", help="run directory (default runs/llm/<cell>/<timestamp>_<model>/)")
    ap.add_argument("--dry-run", action="store_true", help="write the rendered prompts and stop")
    ap.add_argument("--context", default=str(CONTEXT), help="context directory (system.md + turns/)")
    a = ap.parse_args()
    context = Path(a.context).resolve()

    netlist_path = Path(a.netlist).resolve()
    values = {"cell": a.cell, "netlist": normalize_devices(strip_comments(netlist_path.read_text())),
              "netlist_path": str(netlist_path),
              "task_placement_rules": a.placement_rules, "task_routing_rules": a.routing_rules}
    system = render((context / "system.md").read_text(), values)
    turn_files = sorted((context / "turns").glob("*.md"))
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
            "context_dir": str(context.relative_to(REPO)), "context_version": context_version(context),
            "tool_version": tool_version(), "netlist_normalized": True,
            "attempt": a.attempt,
            "placement_rules": a.placement_rules, "routing_rules": a.routing_rules,
            "prompts": {"placement": sum(1 for i in range(1, len(turns) + 1) if i in PLACEMENT_TURNS),
                        "routing": sum(1 for i in range(1, len(turns) + 1) if i not in PLACEMENT_TURNS)},
            "turn_files": [f.name for f in turn_files], "usage": {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
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
            meta["usage"][k] = meta["usage"].get(k, 0) + usage[k]
    meta["llm_s"] = round(time.time() - t0, 2)
    (run / "transcript.json").write_text(json.dumps({"system": system, "messages": messages},
                                                    indent=2, ensure_ascii=False) + "\n")

    code = None if meta["llm_error"] else extract_python(reply)
    meta["code_found"] = code is not None
    if code is not None:
        (run / "gen.py").write_text(code)
        meta["check"] = run_check(run / "gen.py", a.cell, netlist_path, run / "check")
    save()

    chk = meta["check"] or {}
    print(json.dumps({"cell": a.cell, "model": model, "context_version": meta["context_version"],
                      "llm_error": meta["llm_error"], "code_found": meta["code_found"],
                      "gen_ok": chk.get("gen_ok"), "drc_errors": chk.get("drc_errors"),
                      "lvs_result": chk.get("lvs_result"), "run_dir": str(run)}, ensure_ascii=False))
    return 0 if chk.get("gen_ok") and chk.get("drc_errors") == 0 and chk.get("lvs_match") else 1


if __name__ == "__main__":
    sys.exit(main())
