Next, the connection commands. Read them; you will connect nets in a later step.
Reply only with a short confirmation.

## Grids
- `'r12'`: horizontal tracks on local interconnect (li1); its row 0 is the metal1 power rail.
  Use it for connections inside one device row and for the rails.
- `'r23'`: vertical tracks on metal1. Use it for connections between the nfet row and the pfet row.

## Commands
```python
vss_w, vdd_w = c.rails()                                         # both power rails across the whole cell
w = c.connect('A', [(n_a, 'G'), (p_a, 'G')], 'r23')            # a net between pins; returns its main wire
c.port('A', 'r23', w)                                            # make that wire the cell port A
```
- `rails()`: draws `VSS` over every nfet and `VDD` over every pfet and returns the two wires (use them for
  the `VSS` and `VDD` ports).
- `connect(net, pins, grid)`: `pins` is a list of `(instance, pin_name)` or `(instance, pin_name, end)`
  where `end` is `'left'` or `'right'` for pins that span several columns (`'S'`, `'RAIL'`; default
  `'left'`). If the pins share a column or a row and the straight wire is free, it is drawn directly;
  otherwise the cell searches nearby tracks and uses the first free one, with stubs and vias added as
  needed. It refuses any wire that would touch another net or violate the spacing rules and raises
  `SafeError` naming the obstacle. Every pin in the list is assigned to `net`; a pin already on another
  net is refused.
- A net with more than two pins: list **all** its pins in one `connect()` call (every terminal whose
  dictionary value is that net, gates included). If you split it over several calls, later calls must
  share a pin with an earlier one; `check()` reports a net that was left in separate pieces.
- A pin whose net in the netlist differs from `net` is refused immediately (the message names the netlist net).
- `port(name, grid, wire)`: marks a wire returned by `connect()` as the port `name`. `name` must be
  exactly a port name from the netlist, each port exactly once.
- `check()` (already in the skeleton) reports every pin whose net differs from the netlist,
  every unconnected pin, wrong ties and missing ports.
