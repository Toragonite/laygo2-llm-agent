##########################################################
#                                                        #
#        Strong-Arm Latch Layout Generator               #
#   Golden reference written for this repo (no laygo2    #
#   workspace example exists). Topology: arXiv:2408.07279 #
#   Fig. 9(d). See ref/golden/README_hs.md.              #
#                                                        #
##########################################################

import os
import numpy as np
import laygo2
import laygo2.interface
import laygo2_tech as tech
# Parameter definitions #############
# Design Variables
cell_type = 'sal'
nf = 2  # golden: single cell sal_2x, every device nf=2
# Templates
tpmos_name = 'pmos'
tnmos_name = 'nmos'
# Grids
pg_name = 'placement_basic'
r12_name = 'routing_12_cmos'
r23_name = 'routing_23_cmos'
r34_name = 'routing_34_basic'
# Design hierarchy
libname = 'logic_ver2'
cellname = cell_type + '_' + str(nf) + 'x'
# Output contract: everything goes to $LAYOUT_OUT_DIR (default <repo>/runs/golden/sal_2x/),
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
pg, r12, r23, r34 = grids[pg_name], grids[r12_name], grids[r23_name], grids[r34_name]

print('--------------------')
print('Now Creating ' + cellname)

# 2. Create a design hierarchy
lib = laygo2.object.database.Library(name=libname)
dsn = laygo2.object.database.Design(name=cellname, libname=libname)
lib.append(dsn)

# 3. Create instances. net1 = tail, net2 / net3 = drains of the INP / INM input devices.
print("Create instances")
in0 = tnmos.generate(name='MN0', params={'nf': nf, 'tie': 'S'})               # tail:        D=net1 G=CLK  S=VSS
in1 = tnmos.generate(name='MN1', params={'nf': nf})                           # input INP:   D=net2 G=INP  S=net1
in2 = tnmos.generate(name='MN2', params={'nf': nf})                           # latch left:  D=OUTM G=OUTP S=net2
in3 = tnmos.generate(name='MN3', params={'nf': nf})                           # latch right: D=OUTP G=OUTM S=net3
in4 = tnmos.generate(name='MN4', params={'nf': nf})                           # input INM:   D=net3 G=INM  S=net1
ip0 = tpmos.generate(name='MP0', transform='MX', params={'nf': nf, 'tie': 'S'})  # reset net2:  D=net2 G=CLK
ip1 = tpmos.generate(name='MP1', transform='MX', params={'nf': nf, 'tie': 'S'})  # reset OUTM:  D=OUTM G=CLK
ip2 = tpmos.generate(name='MP2', transform='MX', params={'nf': nf, 'tie': 'S'})  # latch left:  D=OUTM G=OUTP
ip3 = tpmos.generate(name='MP3', transform='MX', params={'nf': nf, 'tie': 'S'})  # latch right: D=OUTP G=OUTM
ip4 = tpmos.generate(name='MP4', transform='MX', params={'nf': nf, 'tie': 'S'})  # reset OUTP:  D=OUTP G=CLK
ip5 = tpmos.generate(name='MP5', transform='MX', params={'nf': nf, 'tie': 'S'})  # reset net3:  D=net3 G=CLK
# the nmos row has one device fewer: fill the last slot with two 2-column spacers
nspace0 = templates['nmos130_fast_space_2x'].generate(name='nspace0')
nspace1 = templates['nmos130_fast_space_2x'].generate(name='nspace1')

# 4. Place instances. Each nf=2 device is 4 routing columns wide: block k spans columns 4k..4k+4,
#    its G and D pins sit on column 4k+2 and its S pin spans 4k+1..4k+3.
#    The cross-coupled pair sits in the middle (blocks 2, 3) with each latch nfet under the pfet
#    that shares its gate and drain.
#      pmos row:  MP0 | MP1 | MP2 | MP3 | MP4 | MP5
#      nmos row:  MN0 | MN1 | MN2 | MN3 | MN4 | space
dsn.place(grid=pg, inst=in0, mn=[0, 0])
for _prev, _inst in zip([in0, in1, in2, in3, in4, nspace0], [in1, in2, in3, in4, nspace0, nspace1]):
   dsn.place(grid=pg, inst=_inst, mn=pg.mn.bottom_right(_prev))
dsn.place(grid=pg, inst=ip0, mn=pg.mn.top_left(in0) + pg.mn.height_vec(ip0))
for _prev, _inst in zip([ip0, ip1, ip2, ip3, ip4], [ip1, ip2, ip3, ip4, ip5]):
   dsn.place(grid=pg, inst=_inst, mn=pg.mn.top_right(_prev))

# 5. Create and place wires.
#    r12/r23: horizontal wires on locali; r23 vertical wires on metal1.
#    r34: vertical wires on metal1, horizontal wires on metal2 (only for the two nets that cross the cell).
print("Create wires")
# net1 (tail): MN0.D - MN1.S on a locali track at the block boundary (series-stack idiom of nand) ...
_mn = [r12.mn(in0.pins['D'])[0], r12.mn(in1.pins['S'])[0]]
_track = [r12.mn(in1.pins['S'])[0][0] - 1, None]
rtail0 = dsn.route_via_track(grid=r12, mn=_mn, track=_track)
# ... and MN1.S - MN4.S over metal2 (locali row 1 between them carries net2 and net3).
_mn_a = r23.mn(in1.pins['S'])[1]   # right end of MN1.S
_mn_b = r23.mn(in4.pins['S'])[0]   # left end of MN4.S
dsn.via(grid=r23, mn=_mn_a)        # locali -> metal1
dsn.via(grid=r23, mn=_mn_b)
_mn = [r34.phy2abs[r23.abs2phy[_mn_a]], r34.phy2abs[r23.abs2phy[_mn_b]]]   # same points on r34
rtail1 = dsn.route_via_track(grid=r34, mn=_mn, track=[None, _mn[0][1] + 1])  # metal2 one r34 row up

# net2: MP0.D, MN1.D -> column 5, then MN1.D -> MN2.S on column 9.
_mn = [r23.mn(ip0.pins['D'])[0], r23.mn(in1.pins['D'])[0]]
_track = [r23.mn(in1.pins['D'])[0][0] - 1, None]
rn2a = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
_mn = [r23.mn(in1.pins['D'])[0], r23.mn(in2.pins['S'])[0]]
_track = [r23.mn(in2.pins['S'])[0][0], None]
rn2b = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# net3 (mirror of net2): MP5.D, MN4.D -> column 19, then MN4.D -> MN3.S on column 15.
_mn = [r23.mn(ip5.pins['D'])[0], r23.mn(in4.pins['D'])[0]]
_track = [r23.mn(in4.pins['D'])[0][0] + 1, None]
rn3a = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
_mn = [r23.mn(in4.pins['D'])[0], r23.mn(in3.pins['S'])[1]]
_track = [r23.mn(in3.pins['S'])[1][0], None]
rn3b = dsn.route_via_track(grid=r23, mn=_mn, track=_track)

# OUTM: drains MN2.D / MP2.D on column 10, MP1.D joins on the pmos drain row,
#       gates MN3.G / MP3.G through column 13.
_mn = [r23.mn(in2.pins['D'])[0], r23.mn(ip2.pins['D'])[0]]
voutm0, routm0, voutm1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
_mn_x = r23.mn(in3.pins['G'])[0] + [-1, 0]                       # column 13
_mn_x = np.array([_mn_x[0], r23.mn(ip2.pins['D'])[0][1]])        # ... on the pmos drain row
dsn.route(grid=r23, mn=[r23.mn(ip1.pins['D'])[0], _mn_x])
_mn = [r23.mn(in3.pins['G'])[0], r23.mn(ip3.pins['G'])[0], _mn_x]
routm1 = dsn.route_via_track(grid=r23, mn=_mn, track=[_mn_x[0], None])

# OUTP (mirror): drains MN3.D / MP3.D on column 14, MP4.D joins on the pmos drain row,
#       gates MN2.G / MP2.G through column 11 (reached on the nmos drain row).
_mn = [r23.mn(in3.pins['D'])[0], r23.mn(ip3.pins['D'])[0]]
voutp0, routp0, voutp1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
dsn.route(grid=r23, mn=[r23.mn(ip3.pins['D'])[0], r23.mn(ip4.pins['D'])[0]])
_mn_x = r23.mn(in2.pins['G'])[0] + [1, 0]                        # column 11
_mn_x = np.array([_mn_x[0], r23.mn(in3.pins['D'])[0][1]])        # ... on the nmos drain row
dsn.route(grid=r23, mn=[_mn_x, r23.mn(in3.pins['D'])[0]])
_mn = [r23.mn(in2.pins['G'])[0], r23.mn(ip2.pins['G'])[0], _mn_x]
routp1 = dsn.route_via_track(grid=r23, mn=_mn, track=[_mn_x[0], None])

# INP, INM: short vertical wires on the gate columns.
_mn = [r23.mn(in1.pins['G'])[0], r23.mn(in1.pins['G'])[0] + [0, 1]]
vinp0, rinp0 = dsn.route(grid=r23, mn=_mn, via_tag=[True, False])
_mn = [r23.mn(in4.pins['G'])[0], r23.mn(in4.pins['G'])[0] + [0, 1]]
vinm0, rinm0 = dsn.route(grid=r23, mn=_mn, via_tag=[True, False])

# CLK: MN0.G / MP0.G on column 2, MP0.G - MP1.G and MP4.G - MP5.G on the pmos gate row,
#      left and right groups joined over metal2.
_mn = [r23.mn(in0.pins['G'])[0], r23.mn(ip0.pins['G'])[0]]
vclk0, rclk0, vclk1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
dsn.route(grid=r23, mn=[r23.mn(ip0.pins['G'])[0], r23.mn(ip1.pins['G'])[0]])
dsn.route(grid=r23, mn=[r23.mn(ip4.pins['G'])[0], r23.mn(ip5.pins['G'])[0]])
_mn_r = r23.mn(ip5.pins['G'])[0] + [-1, 0]                       # column 21 on the pmos gate row
dsn.via(grid=r23, mn=_mn_r)                                      # locali -> metal1
_mn_r = r34.phy2abs[r23.abs2phy[_mn_r]]                          # same point on r34
_n_mid = r34.phy2abs[r23.abs2phy[[0, 4]]][1]                     # r34 row at the nmos/pmos boundary
_col_l = r23.mn(in0.pins['G'])[0][0]                             # CLK metal1 wire on column 2
dsn.route(grid=r34, mn=[_mn_r, [_mn_r[0], _n_mid]])              # metal1 down from the gate row
rclk2 = dsn.route(grid=r34, mn=[[_col_l, _n_mid], [_mn_r[0], _n_mid]], via_tag=[True, True])

# VSS (runs over the spacer slot so both rails have the same length)
_mn_end = [r12.mn(ip5.pins['RAIL'])[1][0], r12.mn(in0.pins['RAIL'])[0][1]]
rvss0 = dsn.route(grid=r12, mn=[r12.mn(in0.pins['RAIL'])[0], _mn_end])
# VDD
rvdd0 = dsn.route(grid=r12, mn=[r12.mn(ip0.pins['RAIL'])[0], r12.mn(ip5.pins['RAIL'])[1]])

# 6. Create pins.
pinp0 = dsn.pin(name='INP', grid=r23, mn=r23.mn.bbox(rinp0))
pinm0 = dsn.pin(name='INM', grid=r23, mn=r23.mn.bbox(rinm0))
pclk0 = dsn.pin(name='CLK', grid=r23, mn=r23.mn.bbox(rclk0))
poutp0 = dsn.pin(name='OUTP', grid=r23, mn=r23.mn.bbox(routp0))
poutm0 = dsn.pin(name='OUTM', grid=r23, mn=r23.mn.bbox(routm0))
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
