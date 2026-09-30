"""Self-test of the guardrails: each case must raise SafeError with a helpful message.
Run from the workspace root: PYTHONPATH=.:<repo> LAYOUT_OUT_DIR=/tmp/x python -m laygo2_safe.selftest"""
import sys
from laygo2_safe import Cell, SafeError

c = Cell("selftest")
n0, n1, n2 = c.nmos("MN0", 2, "S"), c.nmos("MN1", 2), c.nmos("MN2", 2, "S")
p0, p1 = c.pmos("MP0", 2, "S"), c.pmos("MP1", 2, "S")
cases = []

def expect(label, fn):
    try:
        fn()
    except SafeError as e:
        cases.append((label, "raised", str(e)[:90])); return
    cases.append((label, "NO ERROR", ""))

expect("odd nf", lambda: c.nmos("X", 3))
expect("bad tie", lambda: c.nmos("Y", 2, "G"))
expect("pmos in nmos_row", lambda: c.place_rows([p0], [n0]))
expect("single instance instead of row", lambda: c.place_rows(n0, [p0]))
c.place_rows([n0, n1, n2], [p0, p1])          # ragged rows: allowed
expect("tied S pin", lambda: c.pt(n0, "S", "r12"))
expect("grid mixing", lambda: c.wire("r23", c.pt(n0, "G", "r12"), c.pt(p0, "G", "r23")))
expect("non-collinear wire", lambda: c.wire("r12", c.pt(n0, "D", "r12"), c.pt(n1, "S", "r12")))
expect("track through a pin", lambda: c.track("r23", [c.pt(n1, "G", "r23"), c.pt(p1, "G", "r23")], ("v", int(c.pt(n1, "G", "r23")[0]))))
expect("raw list as point", lambda: c.wire("r23", [2, 3], c.pt(p0, "G", "r23")))
w = c.wire("r23", c.pt(n0, "G", "r23"), c.pt(p0, "G", "r23"), vias=(True, True))
c.port("B", "r23", w)
expect("duplicate port", lambda: c.port("B", "r23", w))
expect("port on a non-wire", lambda: c.port("Z", "r23", [w]))
expect("place twice", lambda: c.place_rows([n0], [p0]))

# ---- stage 2/3: net-aware connect() and check() ----------------------------------------------
c2 = Cell("selftest2")
n1 = c2.nmos("MN1", 2, ref="XM1"); n0 = c2.nmos("MN0", 2, "S", ref="XM2")
p0 = c2.pmos("MP0", 2, "S", ref="XM3"); p1 = c2.pmos("MP1", 2, "S", ref="XM4")
c2.place_rows([n0, n1], [p0, p1])
w_out = c2.connect("OUT", [(n1, "D", "right"), (p1, "D", "right")], "r23")
expect("pin already on another net", lambda: c2.connect("B", [(n1, "D"), (p0, "G")], "r23"))
expect("manual wire touching OUT", lambda: c2.wire("r23", c2.pt(n1, "G", "r23"), c2.pt(p1, "G", "r23"), vias=(True, True), net="A"))
expect("track too close to a drain (spacing)", lambda: c2.track("r12", [c2.pt(n0, "D", "r12"), c2.pt(n1, "S", "r12")], ("v", 3), net="net1"))
expect("track on the tied-source row", lambda: c2.track("r12", [c2.pt(n0, "D", "r12"), c2.pt(n1, "S", "r12")], ("h", 1), net="net1"))
w_a = c2.connect("A", [(n1, "G"), (p1, "G")], "r23")          # must find a free neighbouring column itself
cases.append(("connect A avoided OUT column", "raised" if w_a is not None else "NO ERROR", "ok"))
c2.connect("net1", [(n0, "D"), (n1, "S")], "r12")
probs = c2.check("../../ref/netlist/nand.spice")
cases.append(("check(): reports unconnected B/rails", "raised" if any("MN0.G is not connected" in p for p in probs) else "NO ERROR", "; ".join(probs)[:90]))
w_b = c2.connect("B", [(n0, "G"), (p0, "G")], "r23")
c2.connect("OUT", [(p0, "D", "right"), (p1, "D")], "r12")
w_vss = c2.connect("VSS", [(n0, "RAIL"), (n1, "RAIL", "right")], "r12"); w_vdd = c2.connect("VDD", [(p0, "RAIL"), (p1, "RAIL", "right")], "r12")
for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c2.port(name, g, w)
probs = c2.check("../../ref/netlist/nand.spice")
cases.append(("check(): consistent when complete", "raised" if not probs else "NO ERROR", "; ".join(probs)[:90]))
c3 = Cell("selftest3")
a = c3.nmos("MN0", 2, "D", ref="XM1"); b = c3.pmos("MP0", 2, "S", ref="XM2")   # wrong tie on purpose
c3.place_rows([a], [b])
probs = c3.check("../../ref/netlist/inv.spice")
cases.append(("check(): wrong tie detected", "raised" if any("tied to VSS but the netlist puts it on O" in p for p in probs) else "NO ERROR", "; ".join(probs)[:90]))
bad = [x for x in cases if x[1] != "raised"]
for label, st, msg in cases:
    print(f"{'ok ' if st == 'raised' else 'FAIL'} {label:40s} {msg}")
sys.exit(1 if bad else 0)
