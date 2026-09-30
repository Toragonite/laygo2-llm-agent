"""nand3_2x with laygo2_safe connect()."""
from laygo2_safe import Cell

c = Cell("nand3_2x", netlist="../../ref/netlist/nand3.spice")
n2 = c.nmos("MN2", nf=2, tie="S", ref="XM3")   # net2-C-VSS
n1 = c.nmos("MN1", nf=2, ref="XM2")            # net1-B-net2
n0 = c.nmos("MN0", nf=2, ref="XM1")            # Y-A-net1
p2 = c.pmos("MP2", nf=2, tie="S", ref="XM6")   # Y-C-VDD
p1 = c.pmos("MP1", nf=2, tie="S", ref="XM5")   # Y-B-VDD
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM4")   # Y-A-VDD
c.place_rows([n2, n1, n0], [p2, p1, p0])

w_vss = c.connect("VSS", [(n2, "RAIL"), (n0, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p2, "RAIL"), (p0, "RAIL", "right")], "r12")
c.connect("net2", [(n2, "D"), (n1, "S")], "r12")
c.connect("net1", [(n1, "D"), (n0, "S")], "r23")   # li1 would be too close to MN0.D at the pin row: metal1
c.connect("Y", [(p2, "D", "right"), (p1, "D"), (p0, "D")], "r12")
w_y = c.connect("Y", [(n0, "D"), (p0, "D")], "r23")
w_a = c.connect("A", [(n0, "G"), (p0, "G")], "r23")
w_b = c.connect("B", [(n1, "G"), (p1, "G")], "r23")
w_c = c.connect("C", [(n2, "G"), (p2, "G")], "r23")
for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("C", "r23", w_c), ("Y", "r23", w_y), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
