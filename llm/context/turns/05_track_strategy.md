Next, how to access pins and the track-based routing strategy. Read them; you will route in the next step.
Reply only with a short confirmation.

## Pin access
```python
r23.mn(inst.pins['G'])        # -> array [[m_ll, n_ll], [m_ur, n_ur]]
r23.mn(inst.pins['G'])[0]     # lower-left point  [m, n]
r23.mn(inst.pins['G'])[1]     # upper-right point [m, n]
r23.mn(inst.pins['G'])[0, 0]  # column index m of the lower-left point
```
- `G` and `D` pins are single points (lower-left equals upper-right).
- `S` (when not tied) and `RAIL` span several columns; use `[0]` for the left end and `[1]` for the right end.

## Track-based routing strategy
1. **Rails:** `VSS` is one horizontal `r12` wire from the left end of the leftmost nfet `RAIL` to the right
   end of the rightmost nfet `RAIL`. `VDD` is the same over the pfet row.
2. **Between rows:** a net that connects an nfet terminal to a pfet terminal (a shared gate input, the
   output) uses a vertical `r23` wire from the nfet pin to the pfet pin, with `via_tag=[True, True]`.
3. **Inside a row:** a net that connects terminals in the same row (an internal node between series
   devices, drains of parallel devices) uses `r12`.
4. **Track conflicts:** if the direct vertical wire of a net would run on the same column as another
   net's wire, use `route_via_track` on a free neighbouring column instead (for example the column
   `pin_m - 1`).
5. Every port gets a pin: signal ports on their `r23` wire, `VSS`/`VDD` on their rail wire.
