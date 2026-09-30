"""nor_2x with laygo2_safe (same layout as ref/golden/nor.py)."""
from laygo2_safe import Cell

c = Cell("nor_2x")
n0 = c.nmos("MN0", nf=2, tie="S")   # gate B
n1 = c.nmos("MN1", nf=2, tie="S")   # gate A
p0 = c.pmos("MP0", nf=2, tie="S")   # gate B, drain = internal node
p1 = c.pmos("MP1", nf=2)            # gate A, source = internal node
c.place_rows([n0, n1], [p0, p1])

gA_n, gA_p = c.pt(n1, "G", "r23"), c.pt(p1, "G", "r23")
w_a = c.track("r23", [gA_n, gA_p], ("v", gA_n[0] - 1))
w_b = c.wire("r23", c.pt(n0, "G", "r23"), c.pt(p0, "G", "r23"), vias=(True, True))

s1 = c.pt(p1, "S", "r12")                                                  # internal node MP0.D - MP1.S
c.track("r12", [c.pt(p0, "D", "r12"), s1], ("v", s1[0] - 1))

c.wire("r12", c.pt(n0, "D", "r12", "right"), c.pt(n1, "D", "r12"))          # OUT: nfet drains
w_out = c.wire("r23", c.pt(n1, "D", "r23", "right"), c.pt(p1, "D", "r23", "right"), vias=(True, True))

w_vss = c.wire("r12", c.pt(n0, "RAIL", "r12"), c.pt(n1, "RAIL", "r12", "right"))
w_vdd = c.wire("r12", c.pt(p0, "RAIL", "r12"), c.pt(p1, "RAIL", "r12", "right"))

for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
c.export()
