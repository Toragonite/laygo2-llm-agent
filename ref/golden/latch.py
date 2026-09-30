##################################################
#                                                #
#        LATCH with 2CLK Layout Gernerator       #
#            Created by Hyungjoo Park            #
#                                                #
##################################################

import os
import numpy as np
import pprint
import laygo2
import laygo2.interface
import laygo2_tech as tech
import _subcells  # ref/golden/_subcells.py: builds inv_2x, tinv_2x, tinv_small_1x in the same library
# Parameter definitions #############
# Variables
cell_type = 'latch_2ck'
nf_list = [2]  # golden: single cell latch_2ck_2x
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
# Output contract: everything goes to $LAYOUT_OUT_DIR (default <repo>/runs/golden/latch_2ck_2x/),
# nothing is written into the laygo2_workspace_sky130 submodule.
_repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
out_dir = os.path.abspath(os.environ.get('LAYOUT_OUT_DIR', os.path.join(_repo_root, 'runs', 'golden', cell_type+'_2x')))
os.makedirs(os.path.join(out_dir, libname), exist_ok=True)  # magic saves .mag into <out_dir>/<libname>/
# End of parameter definitions ######

# Generation start ##################
# 1. Load templates and grids.
print("Load templates")
templates = tech.load_templates()
# (removed) import of logic_ver2_templates.yaml: the file does not exist in the pinned workspace
# (the primitive generators create it by appending into the submodule). The sub-cell templates
# come from _subcells.build() below instead.
tpmos, tnmos = templates[tpmos_name], templates[tnmos_name]

print("Load grids")
grids = tech.load_grids(templates=templates)
pg, r12, r23, r34 = grids[pg_name], grids[r12_name], grids[r23_name], grids[r34_name]

for nf in nf_list:
   cellname = cell_type+'_'+str(nf)+'x'
   print('--------------------')
   print('Now Creating '+cellname)

   # 2. Create a design hierarchy
   lib = laygo2.object.database.Library(name=libname)
   dsn = laygo2.object.database.Design(name=cellname, libname=libname)
   # Sub-cells first: magic.export writes designs in library order, and the top cell's getcell
   # must find them already in memory.
   tlogic = _subcells.build(lib, templates, grids, nf)
   lib.append(dsn)

   # 3. Create istances.
   print("Create instances")
   tinv0 = tlogic['tinv_'+str(nf)+'x'].generate(name='I0')
   tinv_small0 = tlogic['tinv_small_1x'].generate(name='I1')
   inv0 = tlogic['inv_'+str(nf)+'x'].generate(name='I2')

   # 4. Place instances.
   dsn.place(grid=pg, inst=tinv0, mn=[0,0])
   dsn.place(grid=pg, inst=tinv_small0, mn=pg.mn.bottom_right(tinv0))
   dsn.place(grid=pg, inst=inv0, mn=pg.mn.bottom_right(tinv_small0))
   
   # 5. Create and place wires.
   print("Create wires")
   _mn = [r34.mn(tinv0.pins['ENB'])[0], r34.mn(tinv_small0.pins['EN'])[0]]
   _track = [None, r34.mn(tinv0.pins['ENB'])[0,1]]
   rclkb0 = dsn.route_via_track(grid=r34, mn=_mn, track=_track)
   
   _track[1] += 2
   _mn = [r23.mn(tinv0.pins['EN'])[0], r23.mn(tinv_small0.pins['ENB'])[0]]
   rclk0 = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
   
   _mn = [r23.mn(tinv0.pins['O'])[0], [r23.mn(tinv_small0.pins['O'])[0][0],r23.mn(tinv0.pins['O'])[0][1]], r23.mn(tinv_small0.pins['O'])[0]]
   dsn.route(grid=r23, mn=_mn, via_tag=[False, True, False])
   _mn = [r12.mn(tinv_small0.pins['O'])[0], r12.mn(inv0.pins['I'])[0]]
   _track = [_mn[0][0]+2,None]
   dsn.route_via_track(grid=r12, mn=_mn, track=_track)  
#    _track[1] += 1
#    _mn = [r34.mn(tinv0.pins['O'])[0], r34.mn(tinv_small0.pins['O'])[0]]
#    dsn.route_via_track(grid=r34, mn=_mn, track=_track)
#    _mn = [r34.mn(tinv_small0.pins['O'])[0], r34.mn(inv0.pins['I'])[0]]
#    dsn.route_via_track(grid=r34, mn=_mn, track=_track)
   
   _track = [None,(r23.mn(tinv_small0.pins['I'])[0,1]+r23.mn(tinv_small0.pins['I'])[1,1])/2]
   _mn = [r23.mn(tinv_small0.pins['I'])[0], r23.mn(inv0.pins['O'])[0]]
   rout0 = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
   
   # VSS
   rvss0 = dsn.route(grid=r12, mn=[r12.mn.bottom_left(tinv0), r12.mn.bottom_right(inv0)])
   
   # VDD
   rvdd0 = dsn.route(grid=r12, mn=[r12.mn.top_left(tinv0), r12.mn.top_right(inv0)])
   
   # 6. Create pins.
   pin0 = dsn.pin(name='I', grid=r23, mn=r23.mn.bbox(tinv0.pins['I']))
   pclkb0 = dsn.pin(name='CLKB', grid=r23, mn=r23.mn.bbox(tinv0.pins['ENB']))
   pclk0 = dsn.pin(name='CLK', grid=r23, mn=r23.mn.bbox(tinv0.pins['EN']))
   pout0 = dsn.pin(name='O', grid=r23, mn=r23.mn.bbox(inv0.pins['O']))
   pvss0 = dsn.pin(name='VSS', grid=r12, mn=r12.mn.bbox(rvss0))
   pvdd0 = dsn.pin(name='VDD', grid=r12, mn=r12.mn.bbox(rvdd0))
   
   # 7. Export to physical database.
   print("Export design")
   # (removed) NetMap export: laygo2.object.netmap is not in public laygo2 (LVS helper, not needed for layout)
   # Uncomment for BAG export
   # cellname=None: one TCL with every design in lib (inv_2x, tinv_2x, tinv_small_1x, then the latch)
   laygo2.interface.magic.export(lib, filename=os.path.join(out_dir, cellname+'.tcl'), cellname=None, libpath=out_dir, scale=0.5, reset_library=False, tech_library='sky130A')

# 8. Export to a template database file (out_dir only; the shared submodule yaml is not touched).
   nat_temp = dsn.export_to_template()  # obstacle_layers= not supported in pinned laygo2
   laygo2.interface.yaml.export_template(nat_temp, filename=os.path.join(out_dir, libname+'_templates.yaml'), mode='append')