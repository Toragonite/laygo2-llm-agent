"""tinv_2x with laygo2_safe connect(): EN and ENB are single-pin ports."""
from laygo2_safe import Cell

c = Cell("tinv_2x", netlist="../../ref/netlist/tinv.spice")
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")   # net1-I-VSS
n1 = c.nmos("MN1", nf=2, ref="XM2")            # O-EN-net1
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM3")   # net2-I-VDD
p1 = c.pmos("MP1", nf=2, ref="XM4")            # O-ENB-net2
c.place_rows([n0, n1], [p0, p1])

w_vss = c.connect("VSS", [(n0, "RAIL"), (n1, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p1, "RAIL", "right")], "r12")
c.connect("net1", [(n0, "D"), (n1, "S")], "r12")
c.connect("net2", [(p0, "D"), (p1, "S")], "r12")
w_o = c.connect("O", [(n1, "D"), (p1, "D")], "r23")
w_i = c.connect("I", [(n0, "G"), (p0, "G")], "r23")
w_en = c.connect("EN", [(n1, "G")], "r23")
w_enb = c.connect("ENB", [(p1, "G")], "r23")
for name, g, w in [("I", "r23", w_i), ("EN", "r23", w_en), ("ENB", "r23", w_enb), ("O", "r23", w_o), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
