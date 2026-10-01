# laygo2-llm-agent

Reproduction of *"Interactive and Automatic Generation of Primitive Custom Circuit Layout Using LLMs"*
(You, Byun, Lim, Han — Hanyang Univ., MLCAD 2024 WIP, [arXiv:2408.07279](https://arxiv.org/abs/2408.07279))
on a fully open-source stack, followed by a measured improvement of the LLM↔framework interface.

| | paper | this repo |
|---|---|---|
| layout engine | LAYGO2 (template-and-grid) | public [laygo2](https://github.com/niftylab/laygo2) `cc6276a` + SKY130 workspace |
| process | not stated | SkyWater SKY130 (open_pdks `6d4d117`) |
| verification | DRC / LVS (tools not stated) | Magic 8.3.460 DRC + netgen 1.5.133 LVS, fully scripted |
| LLM | ChatGPT-4 (web, 2024) | `gpt-4o-2024-05-13` (reproduction) / `gpt-4o-2024-08-06` (improvement) via API |
| human in the loop | the designer | measured protocol: instruction levels L1–L4, failure types A–E, ≤ 8 instructions |

**한 줄 요약 (KR):** 논문 방식 그대로 LLM이 laygo2 generator 코드를 쓰게 하고 사람이 수정 지시를 주는 흐름을 재현해 baseline을 잰 뒤(8셀 × 5회: 21/40 통과), 실패를 유형별로 분석해 LLM이 쓰기 어려운 API 지점을 얇은 층 `laygo2_safe`로 고쳤다. 같은 과제에서 40/40 통과, 사람 없이 도구 출력만 되먹여도 40/40.

## Results (8 cells × 5 attempts each, same tasks, same judge)

| condition | API | who fixes | pass | pass on first try | fix rounds | cost |
|---|---|---|---|---|---|---|
| v1 baseline (paper method) | original laygo2 | human-style instructions ≤ L3 | 21 / 40 | 0 / 40 | 225 | ≈ $19 |
| v2 | `laygo2_safe` | human-style instructions ≤ L3 | **40 / 40** | 13 / 40 | 41 | ≈ $2 |
| v3 | `laygo2_safe` (+fixes) | **none — tool output fed back automatically** | **40 / 40** | 24 / 40 | 56 | ≈ $2.4 |

Cells: INV, TINV, NOR, NAND2, NAND3, 2-to-1 MUX (paper), ratioed TSPC FF and strong-arm latch (paper Fig. 9).
Failure labels over all failed rounds, v1 → v2: API misuse 134 → 7, routing conflicts 127 → 5, geometry
misunderstanding 85 → 0, circuit-reading errors 79 → 31. Caveats: model, library and context wording changed
together between v1 and v2; the instructions were written by Claude teammates acting as the designer (see
`docs/protocol.md`). Full numbers and per-attempt logs: `results/`, `docs/PROGRESS.md`.

## What is in the repo

```
flow/            check_cell.py (generator → Magic DRC/extract → netgen LVS → JSON), plot_layout.py, layout3d.py, metrics.py
laygo2_safe/     strict, net-aware layer over laygo2: validated inputs, occupancy table, connect() with track search,
                 netlist-aware checks (tie / net / ports / split nets), rails(), port() label placement
llm/             context/ (v1) and context_safe/ (v2) multi-turn prompts, generate.py, chat.py (human loop),
                 selfheal.py (automatic loop), run_bench.py, summarize.py
ref/             golden generators (patched workspace examples + 2 written from the paper), golden_safe rewrites, reference netlists
bench/tasks.yaml benchmark tasks and conditions      results/   CSV summaries      docs/   progress log, protocol, notes
third_party/     laygo2 and the SKY130 workspace as pinned submodules (never modified)
```

## Run it

```bash
# environment (uv, Magic 8.3.460 from source, netgen-lvs, ciel sky130A) — see docs/PROGRESS.md "환경 메모"
scripts/check_env.sh                                                       # 9 checks must PASS

# judge one golden cell
uv run python flow/check_cell.py --gen ref/golden_safe/nand.py --cell nand_2x --ref ref/netlist/nand.spice

# LLM: six context turns, one judgement (needs OPENAI_API_KEY in .env)
uv run python llm/generate.py --cell nand_2x --netlist ref/netlist/nand.spice --model gpt-4o-2024-08-06 --context llm/context_safe
uv run python llm/chat.py --run runs/llm/nand_2x/<run>          # human instructions, tagged p:/r: and [L1]-[L3]
uv run python llm/selfheal.py --run runs/llm/nand_2x/<run>      # or: automatic feedback, up to 8 rounds

# whole benchmark
uv run python llm/run_bench.py --tag <tag> --context llm/context_safe && uv run python llm/selfheal.py --tag <tag>
uv run python llm/summarize.py --tag <tag>
```

## How the pieces fit

1. **Golden path first.** Human-written generators for all 8 cells pass DRC 0 / LVS match, which proves the judge
   (`flow/check_cell.py`) before any LLM is involved. Along the way: netgen prints "match" even for wrong widths or
   swapped pins (`lvs.sh` checks property errors and the pin table), hierarchical `drc count` counts template-internal
   errors (we count on a flattened copy), and Magic 8.3.460 silently drops deviceless sub-cells in hierarchical
   extraction (worked around for the gate-level goldens).
2. **Reproduction.** The paper's Fig. 2–4 flow is a six-turn conversation (netlist → dict, placement rules,
   placement, routing commands, track strategy, routing + full script), then human "modification instructions".
   `docs/protocol.md` fixes what an instruction may contain (L1 tool output … L4 concrete coordinates; baseline ≤ L3)
   and how failures are labelled (A API misuse, B circuit reading, C routing conflict, D geometry, E spacing).
3. **Improvement.** The baseline labels say most failures are tool friction, not circuit knowledge. `laygo2_safe`
   keeps laygo2's architecture (templates, grids) and adds what an LLM needs: one return type per function, points
   that remember their grid, refusal of non-collinear "wires", an occupancy table of every pin/wire with its net,
   `connect(net, pins, grid)` that searches straight → between-pin tracks → L/Z paths → metal2 escape and rejects
   shorts and spacing violations, and netlist-aware checks that fail at the offending line.
4. **Automation.** With every failure now a precise tool message, `selfheal.py` feeds it back verbatim: no human.

## Credits and scope

Paper and LAYGO2 by Prof. Jaeduk Han's group (Hanyang Univ.); the paper's prompt logs were no longer available,
so the context was reconstructed from the paper's text and figures. SKY130 PDK by SkyWater/Google/efabless.
Built with Claude Code as the implementation partner; design decisions and their reasons are logged in
`docs/paper_notes.md` ("우리 선택").
