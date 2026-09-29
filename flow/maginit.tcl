# Magic rc file (replaces the workspace's .maginit, which hardcodes the author's paths).
# Usage: PDK_ROOT=$HOME/pdk magic -dnull -noconsole -rcfile flow/maginit.tcl
source $env(PDK_ROOT)/sky130A/libs.tech/magic/sky130A.magicrc

set ws [file normalize [file join [file dirname [info script]] .. third_party laygo2_workspace_sky130]]
addpath $ws/magic_layout/skywater130_microtemplates_dense
addpath $ws/magic_layout/logic_ver2
