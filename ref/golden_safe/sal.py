"""sal_2x with laygo2_safe connect() (strong-arm latch, paper Fig. 9(d))."""
from laygo2_safe import Cell

c = Cell("sal_2x", netlist="../../ref/netlist/sal.spice")
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")   # net1-CLK-VSS  tail
n1 = c.nmos("MN1", nf=2, ref="XM2")            # net2-INP-net1
n3 = c.nmos("MN3", nf=2, ref="XM4")            # OUTM-OUTP-net2
n4 = c.nmos("MN4", nf=2, ref="XM5")            # OUTP-OUTM-net3
n2 = c.nmos("MN2", nf=2, ref="XM3")            # net3-INM-net1
p9 = c.pmos("MP9", nf=2, tie="S", ref="XM10")  # net2-CLK-VDD
p5 = c.pmos("MP5", nf=2, tie="S", ref="XM6")   # OUTM-OUTP-VDD
p7 = c.pmos("MP7", nf=2, tie="S", ref="XM8")   # OUTM-CLK-VDD
p8 = c.pmos("MP8", nf=2, tie="S", ref="XM9")   # OUTP-CLK-VDD
p6 = c.pmos("MP6", nf=2, tie="S", ref="XM7")   # OUTP-OUTM-VDD
p10 = c.pmos("MP10", nf=2, tie="S", ref="XM11")  # net3-CLK-VDD
c.place_rows([n0, n1, n3, n4, n2], [p9, p5, p7, p8, p6, p10])

w_vss = c.connect("VSS", [(n0, "RAIL"), (n2, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p9, "RAIL"), (p10, "RAIL", "right")], "r12")
# in-row connections first (they have the fewest options), then the verticals between the rows
c.connect("net2", [(n1, "D"), (n3, "S")], "r23")
c.connect("net3", [(n2, "D"), (n4, "S", "right")], "r23")
c.connect("net1", [(n0, "D"), (n1, "S")], "r12")
c.connect("net1", [(n1, "S", "right"), (n2, "S", "right")], "r23")   # long tail net: metal, escapes on metal2 if needed
c.connect("net2", [(n1, "D"), (p9, "D")], "r23")
c.connect("net3", [(n2, "D"), (p10, "D")], "r23")
w_outm = c.connect("OUTM", [(n3, "D"), (p7, "D")], "r23")
c.connect("OUTM", [(p5, "D"), (p7, "D")], "r12")
c.connect("OUTM", [(n3, "D"), (n4, "G")], "r23")
c.connect("OUTM", [(p7, "D"), (p6, "G")], "r23")
w_outp = c.connect("OUTP", [(n4, "D"), (p8, "D")], "r23")
c.connect("OUTP", [(p8, "D"), (p6, "D")], "r12")
c.connect("OUTP", [(n4, "D"), (n3, "G")], "r23")
c.connect("OUTP", [(p8, "D"), (p5, "G")], "r23")
w_inp = c.connect("INP", [(n1, "G")], "r23")
w_inm = c.connect("INM", [(n2, "G")], "r23")
w_clk = c.connect("CLK", [(n0, "G"), (p9, "G")], "r23")
c.connect("CLK", [(p9, "G"), (p7, "G")], "r23")   # crosses other gates: metal2 escape
c.connect("CLK", [(p7, "G"), (p8, "G")], "r23")
c.connect("CLK", [(p8, "G"), (p10, "G")], "r23")
for name, g, w in [("INP", "r23", w_inp), ("INM", "r23", w_inm), ("CLK", "r23", w_clk), ("OUTP", "r23", w_outp), ("OUTM", "r23", w_outm), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
