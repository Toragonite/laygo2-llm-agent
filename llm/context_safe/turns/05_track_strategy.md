Next, the connection strategy. Read it; you will connect the nets in the next step.
Reply only with a short confirmation.

## Which grid for which net
1. **Rails:** `VSS` from the leftmost nfet's `('RAIL')` to the rightmost nfet's `('RAIL', 'right')` on
   `'r12'`; `VDD` the same over the pfet row.
2. **Inside a row** (an internal node between series devices, drains of parallel devices in the same
   row): `'r12'`.
3. **Between the rows** (a gate net shared by an nfet and a pfet, the output joining an nfet drain and a
   pfet drain): `'r23'`.

## Order
Connect in this order, so that the constrained nets get the direct wires: rails, internal series
nodes, outputs (drains), then inputs (gates). If `connect()` reports that no free path exists, try the
other end of a spanning pin, the other grid, or a different placement.

## Ports
Every netlist port gets exactly one `port()` call on a wire of that net: signal ports on their `'r23'`
wire, `VSS`/`VDD` on their rail wire.
