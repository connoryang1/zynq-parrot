# Exact post-synthesis DCPs only. No read_verilog, synth, route or phys_opt.
if {[llength $argv]!=2 || [lsearch -exact {baseline04 unmasked05} [lindex $argv 0]]<0} {error "fixed arm/DCP required"}
set arm [lindex $argv 0]
set input [file normalize [lindex $argv 1]]
set_param general.maxThreads 2
puts "ACTUAL_TOOL_VERSION [version -short]"
puts "ACTUAL_MAX_THREADS [get_param general.maxThreads]"
if {![string match 2024.2* [version -short]] || [get_param general.maxThreads]!=2} {error "tool/thread"}
open_checkpoint $input
if {[get_property PART [current_design]] ne "xc7z020clg400-1"} {error "part mismatch"}
if {[llength [get_clocks]]!=1} {error "one embedded owning clock required"}
set c [get_clocks owning_clock]
if {[llength $c]!=1 || [get_property PERIOD $c]!=50.0 || [get_property WAVEFORM $c] ne "0.000 25.000"} {
 # Numeric waveform check tolerates tool display precision only.
 if {[llength $c]!=1 || [get_property PERIOD $c]!=50.0 || [get_property WAVEFORM $c] ne "0 25"} {error "embedded clock changed"}
}
write_xdc -force loaded-constraints.xdc
set f [open design-properties.tsv w];puts $f "property\tvalue"
foreach p [lsort [list_property [current_design]]] {puts $f [join [list $p [get_property $p [current_design]]] "\t"]}
close $f
if {[llength [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}]]} {error "input blackbox"}
report_utilization -hierarchical -file input-utilization.rpt
opt_design -directive Default
report_utilization -hierarchical -file post-opt-utilization.rpt
place_design -directive Default
report_utilization -hierarchical -file placed-utilization.rpt
report_utilization -file placed-flat-utilization.rpt
report_control_sets -verbose -file control-sets.rpt
report_timing_summary -report_unconstrained -file timing-summary.rpt
report_timing -max_paths 20 -file timing-paths.rpt
# Actual unique sites, not arithmetic LUT/4 or FF/8 projections. Macro/leaf
# cells may repeat sites; de-duplicate each site before counting.
set cells [get_cells -hier -filter {IS_PRIMITIVE == 1}]
set used [dict create]
foreach s [lsort -unique [get_sites -quiet -of_objects $cells]] {
 dict set used $s [get_property SITE_TYPE $s]
}
set sl 0;set sm 0
set f [open occupied-sites.tsv w];puts $f "site\tSITE_TYPE"
foreach s [lsort [dict keys $used]] {
 set type [dict get $used $s]
 puts $f [join [list $s $type] "\t"]
 if {$type eq "SLICEL"} {incr sl}
 if {$type eq "SLICEM"} {incr sm}
}
close $f
if {$sl+$sm==0} {error "no actual occupied slice sites"}
set f [open slice-summary.tsv w]
puts $f "SLICEL\t$sl";puts $f "SLICEM\t$sm";puts $f "total\t[expr {$sl+$sm}]"
close $f
# Full placed checkpoint retains actual placement/constraints/connectivity.
write_checkpoint -force placed.dcp
puts "CSR_COMPONENT_PACKING_COMPLETE $arm SLICEL=$sl SLICEM=$sm total=[expr {$sl+$sm}]"
