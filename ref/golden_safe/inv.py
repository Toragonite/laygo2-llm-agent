"""inv_2x with laygo2_safe connect(): the layer finds the free tracks itself."""
from laygo2_safe import Cell

c = Cell("inv_2x", netlist="../../ref/netlist/inv.spice")
n0 = c.nmos("MN0", nf=2, tie="S", ref="XM1")
p0 = c.pmos("MP0", nf=2, tie="S", ref="XM2")
c.place_rows([n0], [p0])

w_o = c.connect("O", [(n0, "D"), (p0, "D")], "r23")          # straight metal1 wire on the drain column
w_i = c.connect("I", [(n0, "G"), (p0, "G")], "r23")          # same column is taken by O -> a neighbouring track
w_vss = c.connect("VSS", [(n0, "RAIL"), (n0, "RAIL", "right")], "r12")
w_vdd = c.connect("VDD", [(p0, "RAIL"), (p0, "RAIL", "right")], "r12")

for name, g, w in [("I", "r23", w_i), ("O", "r23", w_o), ("VSS", "r12", w_vss), ("VDD", "r12", w_vdd)]:
    c.port(name, g, w)
problems = c.check()
assert not problems, problems
c.export()
