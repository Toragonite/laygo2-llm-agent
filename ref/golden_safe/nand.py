"""nand_2x with laygo2_safe (same layout as ref/golden/nand.py)."""
from laygo2_safe import Cell

c = Cell("nand_2x")
n0 = c.nmos("MN0", nf=2, tie="S")   # gate B, source on VSS
n1 = c.nmos("MN1", nf=2)            # gate A, source = internal node
p0 = c.pmos("MP0", nf=2, tie="S")   # gate B
p1 = c.pmos("MP1", nf=2, tie="S")   # gate A
c.place_rows([n0, n1], [p0, p1])

gA_n, gA_p = c.pt(n1, "G", "r23"), c.pt(p1, "G", "r23")
w_a = c.track("r23", [gA_n, gA_p], ("v", gA_n[0] - 1))
w_b = c.wire("r23", c.pt(n0, "G", "r23"), c.pt(p0, "G", "r23"), vias=(True, True))

s1 = c.pt(n1, "S", "r12")                                                  # internal node MN0.D - MN1.S
c.track("r12", [c.pt(n0, "D", "r12"), s1], ("v", s1[0] - 1))

c.wire("r12", c.pt(p0, "D", "r12", "right"), c.pt(p1, "D", "r12"))          # OUT: pfet drains
w_out = c.wire("r23", c.pt(n1, "D", "r23", "right"), c.pt(p1, "D", "r23", "right"), vias=(True, True))

w_vss = c.wire("r12", c.pt(n0, "RAIL", "r12"), c.pt(n1, "RAIL", "r12", "right"))
w_vdd = c.wire("r12", c.pt(p0, "RAIL", "r12"), c.pt(p1, "RAIL", "r12", "right"))

for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
c.export()
