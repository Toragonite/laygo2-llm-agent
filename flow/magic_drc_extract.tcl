# flow/magic_drc_extract.tcl — one laygo2-exported cell: build layout -> DRC -> extract SPICE.
#
# Usage (ONE magic process per cell; run with cwd = output dir so .ext files land there):
#   cd <out> && MAG_TCL=<cell.tcl> MAG_OUT=<out> MAG_CELL=<cell> \
#     magic -dnull -noconsole -rcfile <repo>/flow/maginit.tcl <repo>/flow/magic_drc_extract.tcl </dev/null
#
# Inputs (env vars):
#   MAG_TCL   TCL written by laygo2.interface.magic.export (required)
#   MAG_OUT   output dir for <cell>.spice, drc.txt, *.ext (default: current dir)
#   MAG_CELL  logical cell name, e.g. inv_2x; picks the top cell among exported cells
#             and names the SPICE file (default: the last exported cell)
#
# Output lines on stdout (parsed by check_cell.py):
#   TOPCELL <magic cell>        e.g. logic_ver2_inv_2x (laygo2 names cells <libname>_<cell>)
#   BBOX_UM <llx> <lly> <urx> <ury>
#   AREA_UM2 <float>
#   DRC_COUNT <int>             drc(full) error count on a flattened copy (details: <out>/drc.txt)
#   SPICE_OUT <path>
#   FLOW_ERROR <stage> <msg>    stage = setup | source | load | drc | extract
#   FLOW_DONE
# Nothing is saved on quit: the microtemplate cells show as "modified" (magic rescales them on
# read), so a save-all would write into the workspace submodule.

proc flow_fail {stage msg} {
    puts "FLOW_ERROR $stage [string map {"\n" " | "} $msg]"
    quit -noprompt
}

if {![info exists env(MAG_TCL)]} { flow_fail setup "MAG_TCL env var not set" }
set tclfile [file normalize $env(MAG_TCL)]
set outdir  [file normalize [expr {[info exists env(MAG_OUT)] ? $env(MAG_OUT) : [pwd]}]]
set want    [expr {[info exists env(MAG_CELL)] ? $env(MAG_CELL) : ""}]
if {![file readable $tclfile]} { flow_fail setup "cannot read $tclfile" }
file mkdir $outdir
cd $outdir

# 1. Find exported cells: top-level "_laygo2_create_layout <libpath> <cell> <tech>" lines after the
#    first "# exporting" comment (the header's _laygo2_test proc also contains such a line).
#    Pre-create each libpath: magic's `save` cannot create the directory itself.
set fh [open $tclfile r]; set lines [split [read $fh] "\n"]; close $fh
set cells {}
set in_body 0
foreach ln $lines {
    if {[string match "# exporting *" $ln]} { set in_body 1 }
    if {$in_body && [regexp {^_laygo2_create_layout\s+(\S+)\s+(\S+)\s+(\S+)} $ln -> libpath cname tech]} {
        # The TCL would `tech load` another tech (e.g. laygo2_tech's tech.name is sky130B).
        if {$tech ne [tech name]} { flow_fail setup "TCL asks for tech '$tech', flow uses '[tech name]'" }
        catch {file mkdir $libpath}
        lappend cells [list $libpath $cname]
    }
}
if {[llength $cells] == 0} { flow_fail setup "no _laygo2_create_layout call found in $tclfile" }
set top ""
foreach c $cells {
    lassign $c libpath cname
    if {$cname eq $want || $cname eq "[file tail $libpath]_$want"} { set top $cname }
}
if {$top eq ""} { set top [lindex [lindex $cells end] 1] }
puts "TOPCELL $top"

# 2. Build the layout by sourcing the exported TCL (paints rects, places microtemplates, saves .mag).
if {[catch {source $tclfile} err]} { flow_fail source $err }

# 3. Load top cell and measure its bounding box (internal units -> microns via CIF output scale).
if {[catch {load $top} err]} { flow_fail load $err }
select top cell
lassign [box values] llx lly urx ury
set s [cif scale out]
puts [format "BBOX_UM %.4f %.4f %.4f %.4f" [expr {$llx*$s}] [expr {$lly*$s}] [expr {$urx*$s}] [expr {$ury*$s}]]
puts [format "AREA_UM2 %.4f" [expr {($urx-$llx)*$s * ($ury-$lly)*$s}]]

# 4. DRC with the full rule deck (the rc default is drc(fast)) on a FLATTENED copy of the top cell.
#    Flat = only errors of the assembled layout. Hierarchically, `drc listall count` also counts
#    each microtemplate/via checked standalone (e.g. via min-area), which neighbours fix in context.
#    drc.txt: "<n boxes>\t<rule>" per violated rule. The flat copy is never saved.
if {[catch {
    drc style drc(full)
    drc euclidean on
    flatten __flow_flat__
    load __flow_flat__
    select top cell
    drc check
    drc catchup
    set ndrc [drc list count total]
    if {$ndrc eq ""} { set ndrc 0 }
    set fh [open [file join $outdir drc.txt] w]
    foreach {why boxes} [drc listall why] { puts $fh "[llength $boxes]\t$why" }
    close $fh
    load $top
} err]} { flow_fail drc $err }
puts "DRC_COUNT $ndrc"

# 5. Extract. "extract do local" writes every .ext into cwd (= outdir), not next to the
#    microtemplate .mag files inside the submodule. "ext2spice lvs" = LVS-friendly options.
set spice [file join $outdir [expr {$want ne "" ? $want : $top}].spice]
if {[catch {
    extract do local
    extract all
    ext2spice lvs
    ext2spice -o $spice
} err]} { flow_fail extract $err }
if {![file exists $spice]} { flow_fail extract "ext2spice produced no $spice" }
puts "SPICE_OUT $spice"
puts "FLOW_DONE"
quit -noprompt
