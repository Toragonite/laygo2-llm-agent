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

bad = [x for x in cases if x[1] != "raised"]
for label, st, msg in cases:
    print(f"{'ok ' if st == 'raised' else 'FAIL'} {label:32s} {msg}")
sys.exit(1 if bad else 0)
