#!/usr/bin/env bash
# flow/lvs.sh — compare an extracted netlist against a reference netlist with netgen (SKY130 setup).
#
# Usage: flow/lvs.sh <extracted.spice> <cell> <ref.spice> <ref_cell> <out.log>
#   <cell>      subckt name in the extracted netlist (magic top cell, e.g. logic_ver2_inv_2x)
#   <ref_cell>  subckt name in the reference netlist
#   <out.log>   netgen report; netgen's console output goes to <out.log>.stdout
#
# Exit codes (the last line printed is "LVS_RESULT <word>"):
#   0 match            "Circuits match uniquely", top-level pin names agree, no property errors
#   1 mismatch         "Netlists do not match" (connectivity / device count / device type)
#   2 pin_mismatch     circuits match but a top-level pin name differs or is missing.
#                      netgen 1.5.133 still says "match" here and only marks **Mismatch** or
#                      "(no matching pin)" in the pin table; newer netgen fails such cells.
#   3 property_errors  topology matches but device properties (W, L, nf, ...) differ
#   4 error            bad arguments, missing file, netgen failed or gave no verdict
set -u

if [ $# -ne 5 ]; then
    echo "usage: $0 <extracted.spice> <cell> <ref.spice> <ref_cell> <out.log>" >&2
    echo "LVS_RESULT error"; exit 4
fi
ext=$(realpath -m "$1"); cell=$2; ref=$(realpath -m "$3"); ref_cell=$4; log=$(realpath -m "$5")
PDK_ROOT=${PDK_ROOT:-$HOME/pdk}
setup=$PDK_ROOT/sky130A/libs.tech/netgen/sky130A_setup.tcl

for f in "$ext" "$ref" "$setup"; do
    [ -r "$f" ] || { echo "missing file: $f" >&2; echo "LVS_RESULT error"; exit 4; }
done
mkdir -p "$(dirname "$log")"
rm -f "$log"    # never read a verdict left over from a previous run

# netgen refuses to compare a file with itself ("Cannot compare") -> use a copy for self-LVS.
if [ "$ext" = "$ref" ]; then
    cp "$ref" "${log%.*}.refcopy.spice"; ref="${log%.*}.refcopy.spice"
fi

# Run from the log's directory so any stray netgen files stay next to the log.
(cd "$(dirname "$log")" && netgen-lvs -batch lvs "$ext $cell" "$ref $ref_cell" "$setup" "$log") \
    > "$log.stdout" 2>&1
rc=$?

# Hierarchical LVS compares subcells bottom-up; the last verdict line in the report is the top cell.
verdict=$(grep -E "^(Circuits match uniquely|Netlists do not match|Netlists match with|Circuits match with)" \
          "$log" 2>/dev/null | tail -n 1)
if [ $rc -ne 0 ] || [ -z "$verdict" ]; then
    echo "netgen exit=$rc, no verdict in $log; tail of $log.stdout:" >&2
    tail -n 20 "$log.stdout" >&2
    echo "LVS_RESULT error"; exit 4
fi
echo "$verdict"
case "$verdict" in
    "Circuits match uniquely"*)
        # Top-level pin table = the last "Subcircuit pins:" block in the report.
        if awk '/^Subcircuit pins:/{blk=""} {blk=blk $0 "\n"} END{printf "%s", blk}' "$log" \
               | grep -qE '\*\*Mismatch\*\*|\(no matching pin\)'; then
            echo "LVS_RESULT pin_mismatch"; exit 2
        fi
        if grep -q "Property errors were found" "$log"; then
            echo "LVS_RESULT property_errors"; exit 3
        fi
        echo "LVS_RESULT match"; exit 0 ;;
    *)
        echo "LVS_RESULT mismatch"; exit 1 ;;
esac
