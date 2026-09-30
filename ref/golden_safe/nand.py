"""nand_2x with laygo2_safe connect()."""
from laygo2_safe import Cell

c = Cell("nand_2x", netlist="../../ref/netlist/nand.spice")
n1 = c.nmos("MN1", nf=2, ref="XM1")            # OUT-A-net1
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM2")   # net1-B-VSS
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM3")   # OUT-B-VDD
p1 = c.pmos("MP1", nf=2, tie="S", ref="XM4")   # OUT-A-VDD
c.place_rows([n0, n1], [p0, p1])

c.connect("OUT", [(p0, "D", "right"), (p1, "D")], "r12")                 # pfet drains, same row
w_out = c.connect("OUT", [(n1, "D", "right"), (p1, "D", "right")], "r23")  # vertical to the nfet drain
w_a = c.connect("A", [(n1, "G"), (p1, "G")], "r23")                        # gate column is taken by OUT -> track
w_b = c.connect("B", [(n0, "G"), (p0, "G")], "r23")
c.connect("net1", [(n0, "D"), (n1, "S")], "r12")                           # series node through the gap
w_vss = c.connect("VSS", [(n0, "RAIL"), (n1, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p1, "RAIL", "right")], "r12")

for name, g, w in [("A", "r23", w_a), ("B", "r23", w_b), ("OUT", "r23", w_out), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
