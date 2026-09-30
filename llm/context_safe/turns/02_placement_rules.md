Next, the basic placement rules and commands. Read them; you will write placement code in the next step.
Reply only with a short confirmation.

## Devices
```python
n = c.nmos('MN0', nf=2, tie='S', ref='XM1')
p = c.pmos('MP0', nf=2, tie='S', ref='XM2')
```
- The first argument is the instance name. Use `MN<i>` for `N<i>` and `MP<i>` for `P<i>`.
- `nf`: number of gate fingers, an even number. One finger of an nmos is W = 0.5 µm and one finger of a
  pmos is W = 1.0 µm, both L = 0.15 µm. So a device with multiplier `m` uses `nf = m`.
- `tie`: `'S'` connects the source to the power rail inside the template, `'D'` connects the drain,
  `None` (default) connects neither. A tied terminal no longer has its own pin.
- `ref`: the device's name in the netlist (`"ref"` of its dictionary). `check()` uses it.
- pmos instances are mirrored automatically so that their rail is at the top.
- Pins of an instance: `'G'`, `'D'`, `'S'` (only if the source is not tied) and `'RAIL'` (its power rail
  segment). `c.pins(inst)` lists them.

## Placement
```python
c.place_rows([n_a, n_b], [p_a, p_b])
```
- The first list is the nfet row (placed left to right at the bottom), the second the pfet row (placed
  left to right directly above). The two lists may have different lengths.

## Basic placement rules (shared by CMOS logic cells)
1. NMOS devices go in the bottom row, PMOS devices in the row directly above.
2. A device whose source is on `VSS` (nfet) or `VDD` (pfet) uses `tie='S'`. If its drain is on the
   rail instead, use `tie='D'`.
3. Alignment strategy: an nfet and a pfet driven by the same gate net go in the same column (same
   index in the two lists), so their gates can be joined by one vertical wire.
4. Devices connected in series (sharing an internal net that is not a port) sit next to each other in the
   same row.
