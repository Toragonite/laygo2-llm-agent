Next, the connection commands. Read them; you will connect nets in a later step.
Reply only with a short confirmation.

## Grids
- `'r12'`: horizontal tracks on local interconnect (li1); its row 0 is the metal1 power rail.
  Use it for connections inside one device row and for the rails.
- `'r23'`: vertical tracks on metal1. Use it for connections between the nfet row and the pfet row.

## Commands
```python
w = c.connect('A', [(n_a, 'G'), (p_a, 'G')], 'r23')            # a net between pins; returns its main wire
w = c.connect('VSS', [(n_a, 'RAIL'), (n_b, 'RAIL', 'right')], 'r12')
c.port('A', 'r23', w)                                            # make that wire the cell port A
```
- `connect(net, pins, grid)`: `pins` is a list of `(instance, pin_name)` or `(instance, pin_name, end)`
  where `end` is `'left'` or `'right'` for pins that span several columns (`'S'`, `'RAIL'`; default
  `'left'`). If the pins share a column or a row and the straight wire is free, it is drawn directly;
  otherwise the cell searches nearby tracks and uses the first free one, with stubs and vias added as
  needed. It refuses any wire that would touch another net or violate the spacing rules and raises
  `SafeError` naming the obstacle. Every pin in the list is assigned to `net`; a pin already on another
  net is refused.
- A net with more than two pins can be built with several `connect()` calls of the same net name;
  each call needs at least two pins and must share at least one pin with an earlier call of that net
  (that shared pin is where the wires meet).
- `port(name, grid, wire)`: marks a wire returned by `connect()` as the port `name`. `name` must be
  exactly a port name from the netlist, each port exactly once.
- `check(netlist_path)` (already in the skeleton) reports every pin whose net differs from the netlist,
  every unconnected pin, wrong ties and missing ports.
