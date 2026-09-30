Read the SPICE netlist of cell `{{cell}}` below. Convert it to a Python dictionary format.

Rules:
- One dictionary per transistor. Name nfets `N0, N1, ...` and pfets `P0, P1, ...` in the order they appear.
- Map each terminal to its net: `"D"` (drain), `"G"` (gate), `"S"` (source).
- Add `"m"` with the device multiplier from the netlist (1 if absent) and `"ref"` with the device name
  from the netlist (for example `"XM1"`).
- After the dictionaries, list the subcircuit ports as `ports = [...]` in the order of the `.subckt` line.

Format example (the values are only an illustration):
```python
N0 = {"D": "O", "G": "A", "S": "INT", "m": 1, "ref": "XM1"}
ports = ["A", "O", "VDD", "VSS"]
```

Netlist:
```spice
{{netlist}}
```
