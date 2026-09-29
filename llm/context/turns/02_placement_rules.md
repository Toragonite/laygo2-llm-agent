Next, the basic placement rules and commands. Read them; you will write placement code in the next step.
Reply only with a short confirmation.

## Transistor templates
```python
tnmos, tpmos = templates['nmos'], templates['pmos']
inst = tnmos.generate(name='MN0', params={'nf': 2, 'tie': 'S'})
inst = tpmos.generate(name='MP0', transform='MX', params={'nf': 2, 'tie': 'S'})
```
- `name`: instance name. Use `MN<i>` for `N<i>` and `MP<i>` for `P<i>` from the dictionaries.
- `nf`: number of gate fingers, an even number. One finger of `nmos` is W = 0.5 µm and one finger of
  `pmos` is W = 1.0 µm, both L = 0.15 µm. So a device with multiplier `m` uses `nf = m`.
- `tie`: `'S'` connects the source to the power rail inside the template, `'D'` connects the drain,
  `None` (default) connects neither. A tied terminal no longer has its own pin.
- `transform='MX'` mirrors the instance vertically. Use it for every pmos so its rail is at the top.
- Pins of a generated instance: `inst.pins['G']`, `inst.pins['D']`, `inst.pins['S']` (only if the source
  is not tied), and `inst.pins['RAIL']` (the power rail segment of that instance).

## Placement commands
```python
pg = grids['placement_basic']
dsn.place(grid=pg, inst=inst, mn=[0, 0])                       # one instance
dsn.place(grid=pg, inst=[[N_a, N_b], [P_a, P_b]], mn=[0, 0])     # rows of instances
```
- With a 2D list, the first row is placed at `mn` and each following row is stacked directly on top of
  the row below. Inside a row, instances are placed left to right with no gap.
- Helpers on the placement grid return abstract coordinates of a placed instance:
  `pg.mn.bottom_left(inst)`, `pg.mn.bottom_right(inst)`, `pg.mn.top_left(inst)`,
  `pg.mn.top_right(inst)`, `pg.mn.height_vec(inst)`, `pg.mn.width_vec(inst)`.

## Basic placement rules (shared by CMOS logic cells)
1. NMOS devices go in the bottom row, PMOS devices in the row directly above.
2. A device whose source is on `VSS` (nfet) or `VDD` (pfet) uses `tie='S'`. If its drain is on the
   rail instead, use `tie='D'`.
3. Alignment strategy: an nfet and a pfet driven by the same gate net go in the same column, so their
   gates can be joined by one vertical wire.
4. Devices connected in series (sharing an internal net that is not a port) sit next to each other in the
   same row.
