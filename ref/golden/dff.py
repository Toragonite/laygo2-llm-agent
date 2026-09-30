###########################################
#                                         #
#      D-Flip Flop Layout Generator       #
#         Created by Taeho Shin           #   
#                                         #
###########################################


import os
import numpy as np
import pprint
import laygo2
import laygo2.interface
import laygo2_tech as tech
import _subcells  # ref/golden/_subcells.py: builds inv_2x, tinv_2x, tinv_small_1x in the same library
# Parameter definitions #############
# Variables
cell_type = 'dff'
nf_list = [2]  # golden: single cell dff_2x
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
# Output contract: everything goes to $LAYOUT_OUT_DIR (default <repo>/runs/golden/dff_2x/),
# nothing is written into the laygo2_workspace_sky130 submodule.
_repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
out_dir = os.path.abspath(os.environ.get('LAYOUT_OUT_DIR', os.path.join(_repo_root, 'runs', 'golden', cell_type+'_2x')))
os.makedirs(os.path.join(out_dir, libname), exist_ok=True)  # magic saves .mag into <out_dir>/<libname>/
# End of parameter definitions ######

# Generation start ##################
# 1. Load templates and grids.
print("Load templates")
templates = tech.load_templates()
tpmos, tnmos = templates[tpmos_name], templates[tnmos_name]
# (removed) import of logic_ver2_templates.yaml: the file does not exist in the pinned workspace
# (the primitive generators create it by appending into the submodule). The sub-cell templates
# come from _subcells.build() below instead.
#print(templates[tpmos_name], templates[tnmos_name], sep="\n")

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
   tlib = _subcells.build(lib, templates, grids, nf)
   lib.append(dsn)

# 3. Create istances.
   print("Create instances")
   inv0 = tlib['inv_'+str(nf)+'x'].generate(name='inv0', netmap={"I": "CLK", "O": "ICLKB"})
   inv1 = tlib['inv_'+str(nf)+'x'].generate(name='inv1', netmap={"I": "ICLKB", "O": "ICLK"})
   inv2 = tlib['inv_'+str(nf)+'x'].generate(name='inv2', netmap={"I": "FLCH", "O": "LCH"})
   inv3 = tlib['inv_'+str(nf)+'x'].generate(name='inv3', netmap={"I": "BLCH", "O": "O"}) 

   tinv0 = tlib['tinv_'+str(nf)+'x'].generate(name='tinv0', netmap={"I": "I", "O": "FLCH", "EN": "ICLKB", "ENB": "ICLK"})
   tinv1 = tlib['tinv_'+str(nf)+'x'].generate(name='tinv1', netmap={"I": "LCH", "O": "BLCH", "EN": "ICLK", "ENB": "ICLKB"})

   tinv_small0 = tlib['tinv_small_1x'].generate(name='tinv_small0', netmap={"I": "LCH", "O": "FLCH", "EN": "ICLK", "ENB": "ICLKB"})
   tinv_small1 = tlib['tinv_small_1x'].generate(name='tinv_small1', netmap={"I": "OUT", "O": "BLCH", "EN": "ICLKB", "ENB": "ICLK"})

# 4. Place instances.
   dsn.place(grid=pg, inst=inv0, mn=[0,0])
   dsn.place(grid=pg, inst=inv1, mn=pg.mn.bottom_right(inv0))
   dsn.place(grid=pg, inst=tinv0, mn=pg.mn.bottom_right(inv1))
   dsn.place(grid=pg, inst=tinv_small0, mn=pg.mn.bottom_right(tinv0))
   dsn.place(grid=pg, inst=inv2, mn=pg.mn.bottom_right(tinv_small0))
   dsn.place(grid=pg, inst=tinv1, mn=pg.mn.bottom_right(inv2))
   dsn.place(grid=pg, inst=tinv_small1, mn=pg.mn.bottom_right(tinv1))
   dsn.place(grid=pg, inst=inv3, mn=pg.mn.bottom_right(tinv_small1))
   
   # 5. Create and place wires.
   print("Create wires")
   
   # 1st M4
   
   _mn = [r34.mn(inv1.pins['O'])[0], r34.mn(tinv_small1.pins['ENB'])[0]]
   _track = [None, r34.mn(inv1.pins['O'])[0,1]-2]
   mn_list=[]
   mn_list.append(r34.mn(inv1.pins['O'])[0])
   mn_list.append(r34.mn(tinv0.pins['ENB'])[0])
   mn_list.append(r34.mn(tinv1.pins['EN'])[0])
   mn_list.append(r34.mn(tinv_small0.pins['EN'])[0])
   mn_list.append(r34.mn(tinv_small1.pins['ENB'])[0])
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
   
   # 2nd M4
   _track[1] += 1
   mn_list=[]
   mn_list.append(r34.mn(inv0.pins['O'])[0])
   mn_list.append(r34.mn(inv1.pins['I'])[0])
   mn_list.append(r34.mn(tinv0.pins['EN'])[0])
   mn_list.append(r34.mn(tinv1.pins['ENB'])[0])
   mn_list.append(r34.mn(tinv_small0.pins['ENB'])[0])
   mn_list.append(r34.mn(tinv_small1.pins['EN'])[0])
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
   
   # 3rd M4
   _track[1] += 1
   mn_list=[]
   mn_list.append(r34.mn(inv2.pins['I'])[0])
   mn_list.append(r34.mn(tinv0.pins['O'])[0])
   mn_list.append(r34.mn(tinv_small0.pins['O'])[0])
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
 
   mn_list=[]
   mn_list.append(r34.mn(inv3.pins['I'])[0])
   mn_list.append(r34.mn(tinv1.pins['O'])[0])
   mn_list.append(r34.mn(tinv_small1.pins['O'])[0])
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
   
   # 4th M4
   _track[1] += 1
   mn_list=[]
   mn_list.append(r34.mn(inv2.pins['O'])[0])
   mn_list.append(r34.mn(tinv1.pins['I'])[0])
   mn_list.append(r34.mn(tinv_small0.pins['I'])[0])
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
  
   mn_list=[]
   mn_list.append(r34.mn(inv3.pins['O'])[0])
   mn_list.append(r34.mn(tinv_small1.pins['I'])[0]) 
   dsn.route_via_track(grid=r34, mn=mn_list, track=_track)
  
   # VSS
   rvss0 = dsn.route(grid=r12, mn=[r12.mn.bottom_left(inv0), r12.mn.bottom_right(inv3)])
   
   # VDD
   rvdd0 = dsn.route(grid=r12, mn=[r12.mn.top_left(inv0), r12.mn.top_right(inv3)])
   
   # 6. Create pins.
   pin0 = dsn.pin(name='I', grid=r23, mn=r23.mn.bbox(tinv0.pins['I']))
   pclk0 = dsn.pin(name='CLK', grid=r23, mn=r23.mn.bbox(inv0.pins['I']))
   pout0 = dsn.pin(name='O', grid=r23, mn=r23.mn.bbox(inv3.pins['O']))
   pvss0 = dsn.pin(name='VSS', grid=r12, mn=r12.mn.bbox(rvss0))
   pvdd0 = dsn.pin(name='VDD', grid=r12, mn=r12.mn.bbox(rvdd0))
   
   # 7. Export to physical database.
   print("Export design")
   # (removed) NetMap export: laygo2.object.netmap is not in public laygo2 (LVS helper, not needed for layout)
   # Uncomment for BAG export
   # cellname=None: one TCL with every design in lib (inv_2x, tinv_2x, tinv_small_1x, then the dff)
   # tech_library fixed to 'sky130A': tech.name is 'sky130B', which is also installed under ~/pdk
   laygo2.interface.magic.export(lib, filename=os.path.join(out_dir, cellname+'.tcl'), cellname=None, libpath=out_dir, scale=0.5, reset_library=False, tech_library='sky130A')
   # 8. Export to a template database file (out_dir only; the shared submodule yaml is not touched).
   nat_temp = dsn.export_to_template()  # metal_table=/net_ignore= not supported in pinned laygo2
   laygo2.interface.yaml.export_template(nat_temp, filename=os.path.join(out_dir, libname+'_templates.yaml'), mode='append')
   # laygo2.interface.yaml.export_design(dsn, filename=ref_dir_template+libname+'_templates.yaml',obs_layers=['metal1','metal2'], mode='append')
