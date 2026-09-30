"""nor_2x with laygo2_safe connect()."""
from laygo2_safe import Cell

c = Cell("nor_2x")
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")   # OUT-B-VSS
n1 = c.nmos("MN1", nf=2, tie="S", ref="XM2")   # OUT-A-VSS
p1 = c.pmos("MP1", nf=2, ref="XM3")            # OUT-A-net1
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM4")   # net1-B-VDD
c.place_rows([n0, n1], [p0, p1])

c.connect("OUT", [(n0, "D", "right"), (n1, "D")], "r12")                   # nfet drains, same row
w_out = c.connect("OUT", [(n1, "D", "right"), (p1, "D", "right")], "r23")
w_a = c.connect("A", [(n1, "G"), (p1, "G")], "r23")
w_b = c.connect("B", [(n0, "G"), (p0, "G")], "r23")
c.connect("net1", [(p0, "D"), (p1, "S")], "r12")
w_vss = c.connect("VSS", [(n0, "RAIL"), (n1, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p1, "RAIL", "right")], "r12")

for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check("../../ref/netlist/nor.spice")
assert not problems, problems
c.export()
