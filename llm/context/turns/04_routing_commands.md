Next, the basic routing rules and commands. Read them; you will route in a later step.
Reply only with a short confirmation.

## Routing grids
```python
r12 = grids['routing_12_cmos']   # vertical tracks on locali; horizontal tracks on locali (track 0 on metal1)
r23 = grids['routing_23_cmos']   # vertical tracks on metal1
```
A wire always lies on the tracks of the grid you pass. The same point has different `mn` values on
different grids, so always convert with the grid you route on.

## Commands
```python
w = dsn.route(grid=r12, mn=[mn_a, mn_b])                                   # returns one wire (Rect)
v0, w, v1 = dsn.route(grid=r23, mn=[mn_a, mn_b], via_tag=[True, True])     # wire with a via at each end
objs = dsn.route_via_track(grid=r23, mn=[mn_a, mn_b], track=[m, None])     # see below
v = dsn.via(grid=r23, mn=mn_a)                                             # a single via
p = dsn.pin(name='A', grid=r23, mn=r23.mn.bbox(w))                         # a pin on an existing wire
```
- `route` draws a straight wire between two points on the same track.
  `via_tag=[True, True]` adds vias at both ends to connect down to the pins below.
- `route_via_track` connects several points through one shared track: `track=[m, None]` is the vertical
  track at column `m`, `track=[None, n]` the horizontal track at row `n`. It draws a short stub from each
  point to the track, and the track wire. The **last** element of the returned list is the track wire.
- `pin` marks a wire as a cell port. `name` must be exactly the port name from the netlist.
- Basic rules: every net is one connected set of wires; two different nets must never share a track
  segment; a wire connects to a pin below it only through a via.
