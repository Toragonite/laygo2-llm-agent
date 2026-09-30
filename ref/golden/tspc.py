##########################################################
#                                                        #
#      Ratioed TSPC Flip-Flop Layout Generator           #
#   Golden reference written for this repo (no laygo2    #
#   workspace example exists). Topology: arXiv:2408.07279 #
#   Fig. 9(e). See ref/golden/README_hs.md.              #
#                                                        #
##########################################################

import os
import numpy as np
import laygo2
import laygo2.interface
import laygo2_tech as tech
# Parameter definitions #############
# Design Variables
cell_type = 'tspc'
nf = 2  # golden: single cell tspc_2x, every device nf=2
# Templates
tpmos_name = 'pmos'
tnmos_name = 'nmos'
# Grids
pg_name = 'placement_basic'
r12_name = 'routing_12_cmos'
r23_name = 'routing_23_cmos'
# Design hierarchy
libname = 'logic_ver2'
cellname = cell_type + '_' + str(nf) + 'x'
# Output contract: everything goes to $LAYOUT_OUT_DIR (default <repo>/runs/golden/tspc_2x/),
# nothing is written into the laygo2_workspace_sky130 submodule.
_repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
out_dir = os.path.abspath(os.environ.get('LAYOUT_OUT_DIR', os.path.join(_repo_root, 'runs', 'golden', cellname)))
os.makedirs(os.path.join(out_dir, libname), exist_ok=True)  # magic saves .mag into <out_dir>/<libname>/
# End of parameter definitions ######

# Generation start ##################
# 1. Load templates and grids.
print("Load templates")
templates = tech.load_templates()
tpmos, tnmos = templates[tpmos_name], templates[tnmos_name]

print("Load grids")
grids = tech.load_grids(templates=templates)
pg, r12, r23 = grids[pg_name], grids[r12_name], grids[r23_name]

print('--------------------')
print('Now Creating ' + cellname)

# 2. Create a design hierarchy
lib = laygo2.object.database.Library(name=libname)
dsn = laygo2.object.database.Design(name=cellname, libname=libname)
lib.append(dsn)

# 3. Create instances.
#   stage 1 (dynamic, precharged by CLK=0): MP0 (G=IN), MN1 (G=CLK), MN0 (G=IN)   -> net1
#   stage 2 (ratioed):                      MP1 (G=net1), MN2 (G=CLK)            -> net3
#   stage 3 (ratioed):                      MP2 (G=CLK),  MN3 (G=net3)           -> OUT
print("Create instances")
in0 = tnmos.generate(name='MN0', params={'nf': nf, 'tie': 'S'})               # D=net2 G=IN   S=VSS
in1 = tnmos.generate(name='MN1', params={'nf': nf})                           # D=net1 G=CLK  S=net2
in2 = tnmos.generate(name='MN2', params={'nf': nf, 'tie': 'S'})               # D=net3 G=CLK  S=VSS
in3 = tnmos.generate(name='MN3', params={'nf': nf, 'tie': 'S'})               # D=OUT  G=net3 S=VSS
ip0 = tpmos.generate(name='MP0', transform='MX', params={'nf': nf, 'tie': 'S'})  # D=net1 G=IN   S=VDD
ip1 = tpmos.generate(name='MP1', transform='MX', params={'nf': nf, 'tie': 'S'})  # D=net3 G=net1 S=VDD
ip2 = tpmos.generate(name='MP2', transform='MX', params={'nf': nf, 'tie': 'S'})  # D=OUT  G=CLK  S=VDD
# the pmos row has one device fewer: fill the last slot with two 2-column spacers
pspace0 = templates['pmos130_fast_space_2x'].generate(name='pspace0', transform='MX')
pspace1 = templates['pmos130_fast_space_2x'].generate(name='pspace1', transform='MX')

# 4. Place instances. Each nf=2 device is 4 routing columns wide: block k spans columns 4k..4k+4,
#    its G and D pins sit on column 4k+2 and its S pin spans 4k+1..4k+3.
#      pmos row:  MP0  | MP1  | MP2 | space
#      nmos row:  MN0  | MN1  | MN2 | MN3
dsn.place(grid=pg, inst=in0, mn=[0, 0])
dsn.place(grid=pg, inst=in1, mn=pg.mn.bottom_right(in0))
dsn.place(grid=pg, inst=in2, mn=pg.mn.bottom_right(in1))
dsn.place(grid=pg, inst=in3, mn=pg.mn.bottom_right(in2))
dsn.place(grid=pg, inst=ip0, mn=pg.mn.top_left(in0) + pg.mn.height_vec(ip0))
dsn.place(grid=pg, inst=ip1, mn=pg.mn.top_right(ip0))
dsn.place(grid=pg, inst=ip2, mn=pg.mn.top_right(ip1))
dsn.place(grid=pg, inst=pspace0, mn=pg.mn.top_right(ip2))
dsn.place(grid=pg, inst=pspace1, mn=pg.mn.top_right(pspace0))

# 5. Create and place wires. r23: vertical wires on metal1, horizontal wires on locali.
print("Create wires")
# IN: MN0.G and MP0.G share column 2 -> one vertical wire.
_mn = [r23.mn(in0.pins['G'])[0], r23.mn(ip0.pins['G'])[0]]
vin0, rin0, vin1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])

# net2 (MN0.D - MN1.S, series stack): locali track on the block boundary column (as in nand).
_mn = [r12.mn(in0.pins['D'])[0], r12.mn(in1.pins['S'])[0]]
_track = [r12.mn(in1.pins['S'])[0][0] - 1, None]
rn2 = dsn.route_via_track(grid=r12, mn=_mn, track=_track)

# net1 (MP0.D, MN1.D, MP1.G): column 6 carries MN1.G (CLK) and MP1.D (net3), so use column 5.
_mn = [r23.mn(ip0.pins['D'])[0], r23.mn(in1.pins['D'])[0], r23.mn(ip1.pins['G'])[0]]
_track = [r23.mn(in1.pins['D'])[0][0] - 1, None]
rn1 = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# CLK (MN1.G, MN2.G, MP2.G): the two nmos gates are joined on the gate row (locali), then MN2.G and
# MP2.G go up on column 9 because column 10 carries MN2.D (net3) and MP2.D (OUT).
_mn = [r23.mn(in1.pins['G'])[0], r23.mn(in2.pins['G'])[0]]
rclk0 = dsn.route(grid=r23, mn=_mn)
_mn = [r23.mn(in2.pins['G'])[0], r23.mn(ip2.pins['G'])[0]]
_track = [r23.mn(in2.pins['G'])[0][0] - 1, None]
rclk1 = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# net3 (MP1.D, MN2.D, MN3.G): MP1.D -> MN2.D on column 7, then MN2.D -> MN3.G on column 12.
_mn = [r23.mn(ip1.pins['D'])[0], r23.mn(in2.pins['D'])[0]]
_track = [r23.mn(ip1.pins['D'])[0][0] + 1, None]
rn3a = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
_mn = [r23.mn(in2.pins['D'])[0], r23.mn(in3.pins['G'])[0]]
_track = [r23.mn(in3.pins['G'])[0][0] - 2, None]
rn3b = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# OUT (MP2.D, MN3.D): column 13, between net3 (column 12) and the MN3 pins (column 14).
_mn = [r23.mn(ip2.pins['D'])[0], r23.mn(in3.pins['D'])[0]]
_track = [r23.mn(in3.pins['D'])[0][0] - 1, None]
rout = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# VSS
rvss0 = dsn.route(grid=r12, mn=[r12.mn(in0.pins['RAIL'])[0], r12.mn(in3.pins['RAIL'])[1]])
# VDD (runs over the spacer slot so both rails have the same length)
_mn_end = [r12.mn(in3.pins['RAIL'])[1][0], r12.mn(ip0.pins['RAIL'])[0][1]]
rvdd0 = dsn.route(grid=r12, mn=[r12.mn(ip0.pins['RAIL'])[0], _mn_end])

# 6. Create pins.
pin0 = dsn.pin(name='IN', grid=r23, mn=r23.mn.bbox(rin0))
pclk0 = dsn.pin(name='CLK', grid=r23, mn=r23.mn.bbox(rclk1[-1]))
pout0 = dsn.pin(name='OUT', grid=r23, mn=r23.mn.bbox(rout[-1]))
pvss0 = dsn.pin(name='VSS', grid=r12, mn=r12.mn.bbox(rvss0))
pvdd0 = dsn.pin(name='VDD', grid=r12, mn=r12.mn.bbox(rvdd0))

# 7. Export to physical database.
print("Export design")
print("")
# tech_library pinned to 'sky130A': tech.name is 'sky130B' and would silently load the sky130B tech in magic
laygo2.interface.magic.export(lib, filename=os.path.join(out_dir, cellname + '.tcl'), cellname=None, libpath=out_dir, scale=0.5, reset_library=False, tech_library='sky130A')

# 8. Export to a template database file (out_dir only; the shared submodule yaml is not touched).
nat_temp = dsn.export_to_template()
laygo2.interface.yaml.export_template(nat_temp, filename=os.path.join(out_dir, libname + '_templates.yaml'), mode='append')
