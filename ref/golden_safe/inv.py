"""inv_2x with laygo2_safe (same layout as ref/golden/inv.py). Verifies the safe layer."""
from laygo2_safe import Cell

c = Cell("inv_2x")
n0 = c.nmos("MN0", nf=2, tie="S")
p0 = c.pmos("MP0", nf=2, tie="S")
c.place_rows([n0], [p0])

g_n, g_p = c.pt(n0, "G", "r23"), c.pt(p0, "G", "r23")
w_i = c.track("r23", [g_n, g_p], ("v", g_n[0] - 1))                       # input on the free column left of the gates
w_o = c.wire("r23", c.pt(n0, "D", "r23", "right"), c.pt(p0, "D", "r23", "right"), vias=(True, True))
w_vss = c.wire("r12", *c.span(n0, "RAIL", "r12"))
w_vdd = c.wire("r12", *c.span(p0, "RAIL", "r12"))

c.port("I", "r23", w_i)
c.port("O", "r23", w_o)
c.port("VSS", "r12", w_vss)
c.port("VDD", "r12", w_vdd)
c.export()
