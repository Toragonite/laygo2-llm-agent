"""tspc_2x with laygo2_safe connect() (ratioed TSPC FF, paper Fig. 9(e))."""
from laygo2_safe import Cell

c = Cell("tspc_2x", netlist="../../ref/netlist/tspc.spice")
n2 = c.nmos("MN2", nf=2, tie="S", ref="XM3")   # net2-IN-VSS
n1 = c.nmos("MN1", nf=2, ref="XM2")            # net1-CLK-net2
n4 = c.nmos("MN4", nf=2, tie="S", ref="XM5")   # net3-CLK-VSS
n6 = c.nmos("MN6", nf=2, tie="S", ref="XM7")   # OUT-net3-VSS
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM1")   # net1-IN-VDD
p3 = c.pmos("MP3", nf=2, tie="S", ref="XM4")   # net3-net1-VDD
p5 = c.pmos("MP5", nf=2, tie="S", ref="XM6")   # OUT-CLK-VDD
c.place_rows([n2, n1, n4, n6], [p0, p3, p5])

w_vss = c.connect("VSS", [(n2, "RAIL"), (n6, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p5, "RAIL", "right")], "r12")
c.connect("net2", [(n2, "D"), (n1, "S")], "r12")
c.connect("net1", [(n1, "D"), (p0, "D")], "r23")
c.connect("net1", [(p0, "D"), (p3, "G")], "r23")
c.connect("net3", [(n4, "D"), (p3, "D")], "r23")
c.connect("net3", [(n4, "D"), (n6, "G")], "r23")
w_out = c.connect("OUT", [(n6, "D"), (p5, "D")], "r23")
w_in = c.connect("IN", [(n2, "G"), (p0, "G")], "r23")
w_clk = c.connect("CLK", [(n1, "G"), (n4, "G")], "r12")
c.connect("CLK", [(n4, "G"), (p5, "G")], "r23")
for name, g, w in [("IN", "r23", w_in), ("CLK", "r23", w_clk), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, "r12" if name == "CLK" else g, w)
problems = c.check()
assert not problems, problems
c.export()
