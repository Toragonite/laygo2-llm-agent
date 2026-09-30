# Stage 3 goldens: strong-arm latch and ratioed TSPC flip-flop

These are high-speed transistor-level cells from arXiv:2408.07279 Fig. 9. The pinned laygo2 workspace
has no example for them, so both generators were written from scratch with the same API and output
contract as the other goldens (`LAYOUT_OUT_DIR`, default `runs/golden/<cell>/`; libname `logic_ver2`;
magic TCL pinned to `sky130A`). Reference netlists are flat and transistor-level: one line per
transistor, neutral names `XM1..`, `m` = fingers.

| cell | generator | reference | pins | transistors / nets |
|---|---|---|---|---|
| `sal_2x` | `sal.py` | `ref/netlist/sal.spice` | INP INM CLK OUTP OUTM VDD VSS | 11 / 10 |
| `tspc_2x` | `tspc.py` | `ref/netlist/tspc.spice` | IN CLK OUT VDD VSS | 7 / 8 |

## Topology source
- **Strong-arm latch = Fig. 9(d), as drawn.** This is the standard clocked comparator with four reset pfets.
  Nothing was added or removed.
- **Ratioed TSPC flip-flop = Fig. 9(e), as drawn.** The figure is readable at the extracted image
  resolution. Three stages: VDD–P(IN)–N(CLK)–N(IN)–VSS, then P(net1)/N(CLK), then P(CLK)/N(net3).
  No published variant had to be substituted.

## Transistor list
`sal_2x` (net1 = tail, net2 / net3 = drains of the INP / INM devices)

| ref | type | D | G | S | layout instance |
|---|---|---|---|---|---|
| XM1 | n | net1 | CLK | VSS | MN0 (tail) |
| XM2 | n | net2 | INP | net1 | MN1 |
| XM3 | n | net3 | INM | net1 | MN4 |
| XM4 | n | OUTM | OUTP | net2 | MN2 |
| XM5 | n | OUTP | OUTM | net3 | MN3 |
| XM6 | p | OUTM | OUTP | VDD | MP2 |
| XM7 | p | OUTP | OUTM | VDD | MP3 |
| XM8 | p | OUTM | CLK | VDD | MP1 (reset) |
| XM9 | p | OUTP | CLK | VDD | MP4 (reset) |
| XM10 | p | net2 | CLK | VDD | MP0 (reset) |
| XM11 | p | net3 | CLK | VDD | MP5 (reset) |

`tspc_2x`

| ref | type | D | G | S | layout instance |
|---|---|---|---|---|---|
| XM1 | p | net1 | IN | VDD | MP0 |
| XM2 | n | net1 | CLK | net2 | MN1 |
| XM3 | n | net2 | IN | VSS | MN0 |
| XM4 | p | net3 | net1 | VDD | MP1 |
| XM5 | n | net3 | CLK | VSS | MN2 |
| XM6 | p | OUT | CLK | VDD | MP2 |
| XM7 | n | OUT | net3 | VSS | MN3 |

## Sizing
- Every device uses `nf=2`: nfet_01v8_lvt W = 0.5 µm per finger and pfet_01v8 W = 1.0 µm per finger,
  L = 0.15 µm, so `m=2` in the reference. There are no exceptions.
- These goldens are **DRC/LVS references, not sized circuits**. The paper gives no sizes. A real
  strong-arm latch uses a wider tail and input pair. A ratioed TSPC depends on the pull-up/pull-down
  strength ratio in stages 2 and 3. Neither was simulated or tuned here.

## Layout notes
- The layout is one nmos row with one pmos row on top (`MX`), as in the other goldens. The shorter row
  is filled with two `*_fast_space_2x` spacers so both rails have the same length
  (SAL: nmos row, right end; TSPC: pmos row, right end).
- SAL puts the cross-coupled pair in the middle (MN2/MP2 and MN3/MP3 share gate and drain columns).
  The cross-coupling uses metal1 verticals and locali on the drain rows, so no metal2 is needed there.
  Two nets cross the whole cell on metal2 (`routing_34_basic`): tail (net1, MN1.S to MN4.S) and CLK
  (column 2 to column 21).
- TSPC uses only locali and metal1 (`routing_12_cmos`, `routing_23_cmos`).
- Pitfall: `dsn.place(inst=[[...]])` with a list of `MX` pmos already accounts for the flip. Adding
  `pg.mn.height_vec(ip0)` to its `mn` (the single-instance idiom) places the pmos row one row too high,
  and LVS then shorts every drain net to VDD. The generators use single-instance placement.

## Checks (2026-09-30)
- `sal_2x`: drc_errors 0, lvs match, area 56.37 µm². `tspc_2x`: drc_errors 0, lvs match, area 36.90 µm².
- Negative controls, run on scratch copies of the references:
  - SAL with OUTP/OUTM swapped: `mismatch`.
  - TSPC with IN/CLK swapped: `pin_mismatch`.
  - Swapping **both** INP/INM and OUTP/OUTM in SAL is *not* a negative control. It describes the same
    circuit (only net2/net3 exchange names), so `match` is the correct result.
