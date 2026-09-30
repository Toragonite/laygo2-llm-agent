##########################################################################
#                                                                        #
#   Sub-cells for the hierarchical goldens (ref/golden/latch.py, dff.py) #
#                                                                        #
##########################################################################
# The original gate-level generators (logic_ver2/latch_2ck.py, dff_ver2.py) read their sub-cells
# (inv_2x, tinv_2x, tinv_small_1x) as templates from logic_ver2_templates.yaml, a file the primitive
# generators build by appending into the workspace submodule. That file does not exist in the pinned
# workspace and we never write into the submodule. Instead, build() creates the sub-cell designs in
# the SAME laygo2 Library as the top cell and returns their templates (dsn.export_to_template(), the
# same object the yaml round-trip would give). magic.export(lib, cellname=None) then writes every
# sub-cell before the top cell into the one TCL, so the top cell's `getcell logic_ver2_<sub>.mag`
# finds the in-memory sub-cell (and never the stale .mag files under the workspace's
# magic_layout/logic_ver2, which is on maginit.tcl's search path).
#
# Bodies are copies of the other goldens / originals, with the same fixes (nf=2 only, no NetMap,
# no export/yaml writes -- the caller exports the whole library):
#   make_inv        <- ref/golden/inv.py  (logic_ver2/inv_ver2.py,  cell_type 'inv')
#   make_tinv       <- ref/golden/tinv.py (logic_ver2/tinv_ver2.py, cell_type 'tinv')
#   make_tinv_small <- logic_ver2/tinv_small_ver2.py (no golden of its own; body unchanged,
#                      the commented-out "DRC ISSUE" block stays out)

import numpy as np
import laygo2

# Templates / grids (same names as in all logic_ver2 generators)
tpmos_name = 'pmos'
tnmos_name = 'nmos'
pg_name = 'placement_basic'
r12_name = 'routing_12_cmos'
r23_name = 'routing_23_cmos'
r34_name = 'routing_34_basic'


def _grids(grids):
   return grids[pg_name], grids[r12_name], grids[r23_name], grids[r34_name]


def _new_design(lib, cellname):
   dsn = laygo2.object.database.Design(name=cellname, libname=lib.name)
   lib.append(dsn)
   return dsn


def _dearray(dsn):
   """Replace every arrayed via inside the transistor VirtualInstances (the 1x2 via_M1_M2_1 on the
   tied / extended source rows of an nf=2 nmos/pmos) by single vias at the same positions.

   Why: magic 8.3.460 (extflat/EFflat.c, efFlatNodesDeviceless) decrements a cell's use counter once
   per ARRAY ELEMENT of each deviceless use but counts the array as one use. Each nf=2 transistor
   carries exactly one 1x2 via array, so for inv_2x/tinv_2x the counter ends at 0, the cell is
   flagged DEF_NODEVICES, and hierarchical ext2spice silently drops its instances from the parent
   (the latch netlist came out with only the tinv_small instance). Top cells are always written,
   so the flat primitive goldens never hit this. Geometry is unchanged: element (i, j) of an array
   sits at xy + (i*pitch_x, j*pitch_y) in the VirtualInstance frame, which is where magic's
   `array` puts it too."""
   for vinst in dsn.virtual_instances.values():
      ne = vinst.native_elements
      for name in list(ne.keys()):
         e = ne[name]
         if type(e) is not laygo2.object.physical.Instance or e.shape is None or np.prod(e.shape) <= 1:
            continue
         del ne[name]
         for i, j in np.ndindex(*e.shape):
            _name = name + '_' + str(i) + '_' + str(j)
            ne[_name] = laygo2.object.physical.Instance(
               xy=e.xy + np.array([i * e.pitch[0], j * e.pitch[1]]), libname=e.libname,
               cellname=e.cellname, transform=e.transform, unit_size=e.unit_size, name=_name)


def make_inv(lib, templates, grids, nf=2):
   """inv_<nf>x: pins I, O, VSS, VDD. Returns its NativeInstanceTemplate."""
   tpmos, tnmos = templates[tpmos_name], templates[tnmos_name]
   pg, r12, r23, r34 = _grids(grids)
   dsn = _new_design(lib, 'inv_'+str(nf)+'x')

   in0 = tnmos.generate(name='MN0', params={'nf': nf, 'tie': 'S'})
   ip0 = tpmos.generate(name='MP0', transform='MX', params={'nf': nf,'tie': 'S'})

   dsn.place(grid=pg, inst=in0, mn=[0,0])
   dsn.place(grid=pg, inst=ip0, mn=pg.mn.top_left(in0) + pg.mn.height_vec(ip0))

   # IN
   _mn = [r23.mn(in0.pins['G'])[0], r23.mn(ip0.pins['G'])[0]]
   _track = [r23.mn(in0.pins['G'])[0,0]-1, None]
   rin0 = dsn.route_via_track(grid=r23, mn=_mn, track=_track)
   # OUT
   _mn = [r23.mn(in0.pins['D'])[1], r23.mn(ip0.pins['D'])[1]]
   vout0, rout0, vout1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
   # VSS
   rvss0 = dsn.route(grid=r12, mn=[r12.mn(in0.pins['RAIL'])[0], r12.mn(in0.pins['RAIL'])[1]])
   # VDD
   rvdd0 = dsn.route(grid=r12, mn=[r12.mn(ip0.pins['RAIL'])[0], r12.mn(ip0.pins['RAIL'])[1]])

   dsn.pin(name='I', grid=r23, mn=r23.mn.bbox(rin0[2]))
   dsn.pin(name='O', grid=r23, mn=r23.mn.bbox(rout0))
   dsn.pin(name='VSS', grid=r12, mn=r12.mn.bbox(rvss0))
   dsn.pin(name='VDD', grid=r12, mn=r12.mn.bbox(rvdd0))
   _dearray(dsn)
   return dsn.export_to_template()


def make_tinv(lib, templates, grids, nf=2):
   """tinv_<nf>x: O = not I when EN=1/ENB=0. Pins I, EN, ENB, O, VSS, VDD."""
   tpmos, tnmos = templates[tpmos_name], templates[tnmos_name]
   pg, r12, r23, r34 = _grids(grids)
   dsn = _new_design(lib, 'tinv_'+str(nf)+'x')

   in0 = tnmos.generate(name='MN0', params={'nf': nf, 'tie': 'S'})
   ip0 = tpmos.generate(name='MP0', transform='MX', params={'nf': nf, 'tie': 'S'})
   in1 = tnmos.generate(name='MN1', params={'nf': nf}) # trackswap not allowed in this version
   ip1 = tpmos.generate(name='MP1', transform='MX', params={'nf': nf}) # trackswap not allowed in this version

   dsn.place(grid=pg, inst=in0, mn=[0,0])
   dsn.place(grid=pg, inst=ip0, mn=pg.mn.top_left(in0) + pg.mn.height_vec(ip0))
   dsn.place(grid=pg, inst=in1, mn=pg.mn.bottom_right(in0))
   dsn.place(grid=pg, inst=ip1, mn=pg.mn.top_right(ip0))

   # IN
   _mn = [r23.mn(in0.pins['G'])[0], r23.mn(ip0.pins['G'])[0]]
   v0, rin0, v1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
   # OUT
   _mn = [r23.mn(in1.pins['D'])[1], r23.mn(ip1.pins['D'])[1]]
   vout0, rout0, vout1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
   # EN
   _mn = [r23.mn(in1.pins['G'])[1]+[1,0], r23.mn(ip1.pins['G'])[1]+[1,0]]
   ven0, ren0 = dsn.route(grid=r23, mn=_mn, via_tag=[True, False])
   _mn = [r23.mn(in1.pins['G'])[1], r23.mn(in1.pins['G'])[1]+[1,0]]
   dsn.route(grid=r23, mn=_mn)
   # ENB
   _mn = [r23.mn(in1.pins['G'])[1]+[-1,0], r23.mn(ip1.pins['G'])[1]+[-1,0]]
   renb0, venb0 = dsn.route(grid=r23, mn=_mn, via_tag=[False, True])
   _mn = [r23.mn(ip1.pins['G'])[1], r23.mn(ip1.pins['G'])[1]+[-1,0]]
   dsn.route(grid=r23, mn=_mn)
   # Internal (trackswap not allowed -> straight line not allowed)
   _mn = [r12.mn(ip0.pins['D'])[0], r12.mn(ip1.pins['S'])[0]]
   _track = [r12.mn(ip1.pins['S'])[0][0]-1,None]
   dsn.route_via_track(grid=r12, mn=_mn, track=_track)
   _mn = [r12.mn(in0.pins['D'])[0], r12.mn(in1.pins['S'])[0]]
   _track = [r12.mn(in1.pins['S'])[0][0]-1,None]
   dsn.route_via_track(grid=r12, mn=_mn, track=_track)
   # VSS
   rvss0 = dsn.route(grid=r12, mn=[r12.mn(in0.pins['RAIL'])[0], r12.mn(in1.pins['RAIL'])[1]])
   # VDD
   rvdd0 = dsn.route(grid=r12, mn=[r12.mn(ip0.pins['RAIL'])[0], r12.mn(ip1.pins['RAIL'])[1]])

   dsn.pin(name='I', grid=r23, mn=r23.mn.bbox(rin0))
   dsn.pin(name='EN', grid=r23, mn=r23.mn.bbox(ren0))
   dsn.pin(name='ENB', grid=r23, mn=r23.mn.bbox(renb0))
   dsn.pin(name='O', grid=r23, mn=r23.mn.bbox(rout0))
   dsn.pin(name='VSS', grid=r12, mn=r12.mn.bbox(rvss0))
   dsn.pin(name='VDD', grid=r12, mn=r12.mn.bbox(rvdd0))
   _dearray(dsn)
   return dsn.export_to_template()


def make_tinv_small(lib, templates, grids):
   """tinv_small_1x: 1-finger tri-state inverter from 2-stack microtemplates (series NMOS/PMOS pair).
   Pins I, EN, ENB, O, VSS, VDD."""
   pg, r12, r23, r34 = _grids(grids)
   dsn = _new_design(lib, 'tinv_small_1x')

   nstack = templates['nmos130_fast_center_2stack'].generate(name='nstack')
   nbndl = templates['nmos130_fast_boundary'].generate(name='nbndl')
   nbndr = templates['nmos130_fast_boundary'].generate(name='nbndr')
   nspace0 = templates['nmos130_fast_space'].generate(name='nspace0')
   nspace1 = templates['nmos130_fast_space'].generate(name='nspace1')
   pstack = templates['pmos130_fast_center_2stack'].generate(name='pstack', transform='MX')
   pbndl = templates['pmos130_fast_boundary'].generate(name='pbndl', transform='MX')
   pbndr = templates['pmos130_fast_boundary'].generate(name='pbndr', transform='MX')
   pspace0 = templates['pmos130_fast_space'].generate(name='pspace0', transform='MX')
   pspace1 = templates['pmos130_fast_space'].generate(name='pspace1', transform='MX')

   dsn.place(grid=pg, inst=nbndl, mn=[0,0])
   dsn.place(grid=pg, inst=nstack, mn=pg.mn.bottom_right(nbndl))
   dsn.place(grid=pg, inst=nbndr, mn=pg.mn.bottom_right(nstack))
   dsn.place(grid=pg, inst=nspace0, mn=pg.mn.bottom_right(nbndr))
   dsn.place(grid=pg, inst=nspace1, mn=pg.mn.bottom_right(nspace0))
   dsn.place(grid=pg, inst=pbndl, mn=pg.mn.top_left(nbndl)+pg.mn.height_vec(pbndl))
   dsn.place(grid=pg, inst=pstack, mn=pg.mn.top_right(pbndl))
   dsn.place(grid=pg, inst=pbndr, mn=pg.mn.top_right(pstack))
   dsn.place(grid=pg, inst=pspace0, mn=pg.mn.top_right(pbndr))
   dsn.place(grid=pg, inst=pspace1, mn=pg.mn.top_right(pspace0))

   # IN
   _mn = [r12.mn(nstack.pins['G0'])[0], r12.mn(pstack.pins['G0'])[0]]
   rin0 = dsn.route(grid=r23, mn=_mn)
   _mn = [r12.mn(nstack.pins['G0'])[0], r12.mn(pstack.pins['G0'])[0]]
   dsn.route(grid=r12, mn=_mn)
   _mn = [np.mean(r23.mn.bbox(rin0), axis=0, dtype=int), np.mean(r23.mn.bbox(rin0), axis=0, dtype=int)+[2,0]]
   dsn.route(grid=r23, mn=_mn, via_tag=[True, False])
   dsn.via(grid=r12, mn=np.mean(r23.mn.bbox(rin0), axis=0, dtype=int))
   # OUT
   _mn = [r23.mn(nstack.pins['D0'])[0], r23.mn(pstack.pins['D0'])[1]]
   vout0, rout0, vout1 = dsn.route(grid=r23, mn=_mn, via_tag=[True, True])
   dsn.via(grid=r12, mn=r23.mn(nstack.pins['D0'])[0])
   dsn.via(grid=r12, mn=r23.mn(pstack.pins['D0'])[1])
   # EN
   _mn = [r23.mn(nstack.pins['G1'])[0], r23.mn(nstack.pins['G1'])[0]+[1,0]]
   ren0, ven0 = dsn.route(grid=r23, mn=_mn, via_tag=[False, True])
   dsn.via(grid=r12, mn=r12.mn(nstack.pins['G1'])[0])
   _mn = [r23.mn(nstack.pins['G1'])[0]+[1,0], r23.mn(pstack.pins['G1'])[0]+[1,0]]
   ren1 = dsn.route(grid=r23, mn=_mn)
   # ENB
   _mn = [r23.mn(pstack.pins['G1'])[0], r23.mn(pstack.pins['G1'])[0]+[-1,0]]
   renb0, venb0 = dsn.route(grid=r23, mn=_mn, via_tag=[False, True])
   dsn.via(grid=r12, mn=r12.mn(pstack.pins['G1'])[0])
   _mn = [r23.mn(pstack.pins['G1'])[0]+[-1,0], r23.mn(nstack.pins['G1'])[0]+[-1,0]]
   renb1 = dsn.route(grid=r23, mn=_mn)
   # VSS: M2 rail + tie of the stack source
   _mn = [r12.mn.bottom_left(nbndl), r12.mn.bottom_right(nspace1)]
   rvss0 = dsn.route(grid=r12, mn=_mn)
   _mn = [r12.mn(nstack.pins['S0'])[0], r12.mn(nstack.pins['S0'])[0]+[0,-1]]
   dsn.route(grid=r12, mn=_mn, via_tag=[False, True])
   # VDD: M2 rail + tie of the stack source
   _mn = [r12.mn.top_left(pbndl), r12.mn.top_right(pspace1)]
   rvdd0 = dsn.route(grid=r12, mn=_mn)
   _mn = [r12.mn(pstack.pins['S0'])[1], r12.mn(rvdd0)[0]+[1,0]]
   dsn.route(grid=r12, mn=_mn, via_tag=[False, True])

   dsn.pin(name='I', grid=r23, mn=r23.mn.bbox(rin0))
   dsn.pin(name='O', grid=r23, mn=r23.mn.bbox(rout0))
   dsn.pin(name='EN', grid=r23, mn=r23.mn.bbox(ren1))
   dsn.pin(name='ENB', grid=r23, mn=r23.mn.bbox(renb1))
   dsn.pin(name='VSS', grid=r12, mn=r12.bbox(rvss0))
   dsn.pin(name='VDD', grid=r12, mn=r12.bbox(rvdd0))
   _dearray(dsn)
   return dsn.export_to_template()


def build(lib, templates, grids, nf=2):
   """Create inv_<nf>x, tinv_<nf>x and tinv_small_1x in `lib` (before the top cell is appended)
   and return {cellname: template}, the same keys as the original `tlib[...]` lookups."""
   return {
      'inv_'+str(nf)+'x': make_inv(lib, templates, grids, nf),
      'tinv_'+str(nf)+'x': make_tinv(lib, templates, grids, nf),
      'tinv_small_1x': make_tinv_small(lib, templates, grids),
   }
