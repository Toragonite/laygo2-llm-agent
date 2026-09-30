"""mux2to1_2x with laygo2_safe connect(): EN0/EN1 cross between the rows."""
from laygo2_safe import Cell

c = Cell("mux2to1_2x", netlist="../../ref/netlist/mux2.spice")
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")   # net1-I0-VSS
n1 = c.nmos("MN1", nf=2, ref="XM2")            # net5-EN0-net1
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM3")   # net2-I0-VDD
p1 = c.pmos("MP1", nf=2, ref="XM4")            # net5-EN1-net2
n2 = c.nmos("MN2", nf=2, tie="S", ref="XM5")   # net3-I1-VSS
n3 = c.nmos("MN3", nf=2, ref="XM6")            # net5-EN1-net3
p2 = c.pmos("MP2", nf=2, tie="S", ref="XM7")   # net4-I1-VDD
p3 = c.pmos("MP3", nf=2, ref="XM8")            # net5-EN0-net4
n4 = c.nmos("MN4", nf=2, tie="S", ref="XM9")   # O-net5-VSS
p4 = c.pmos("MP4", nf=2, tie="S", ref="XM10")  # O-net5-VDD
c.place_rows([n0, n1, n2, n3, n4], [p0, p1, p2, p3, p4])

w_vss = c.connect("VSS", [(n0, "RAIL"), (n4, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p4, "RAIL", "right")], "r12")
c.connect("net1", [(n0, "D"), (n1, "S")], "r12")
c.connect("net2", [(p0, "D"), (p1, "S")], "r12")
c.connect("net3", [(n2, "D"), (n3, "S")], "r12")
c.connect("net4", [(p2, "D"), (p3, "S")], "r12")
c.connect("net5", [(n1, "D"), (n3, "D")], "r12")
c.connect("net5", [(p1, "D"), (p3, "D")], "r12")
c.connect("net5", [(n3, "D"), (p3, "D")], "r23")
c.connect("net5", [(n3, "D"), (n4, "G")], "r23")
c.connect("net5", [(p3, "D"), (p4, "G")], "r23")
w_o = c.connect("O", [(n4, "D"), (p4, "D")], "r23")
w_i0 = c.connect("I0", [(n0, "G"), (p0, "G")], "r23")
w_i1 = c.connect("I1", [(n2, "G"), (p2, "G")], "r23")
w_en0 = c.connect("EN0", [(n1, "G"), (p3, "G")], "r23")
w_en1 = c.connect("EN1", [(n3, "G"), (p1, "G")], "r23")
for name, g, w in [("I0", "r23", w_i0), ("I1", "r23", w_i1), ("EN0", "r23", w_en0), ("EN1", "r23", w_en1), ("O", "r23", w_o), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
