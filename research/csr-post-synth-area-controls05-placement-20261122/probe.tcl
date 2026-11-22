# Single saved ExploreArea placement follow-up. No opt_design, synthesis or IP rebuild.
set arm [lindex $argv 0]
set input [lindex $argv 1]
set policy [lindex $argv 2]
set gate_script [file join [file dirname [info script]] coverage.py]
source [file join [file dirname [info script]] collect.tcl]
if {$arm ne "area1-placement-followup"} {error "unreviewed arm"}
set_param general.maxThreads 8
if {[get_param general.maxThreads] != 8 || [version -short] ne "2024.2"} {error "wrong tool/settings"}
puts "ACTUAL_TOOL_VERSION [version -short] ACTUAL_MAX_THREADS [get_param general.maxThreads]"
set progress_root [pwd]
proc phase {name} {
 set f [open [file join $::progress_root progress.json.tmp] w]
 puts $f "\{\"phase\":\"$name\",\"started_epoch\":[clock seconds]\}"
 close $f
 file rename -force [file join $::progress_root progress.json.tmp] [file join $::progress_root progress.json]
 puts "REUSE_PHASE $name"
}
proc value {text label} {
 foreach line [split $text \n] {
  set cols [split $line |]
  if {[llength $cols]>2 && [string trim [lindex $cols 1]] eq $label} {
   return [string map {, {}} [string trim [lindex $cols 2]]]
  }
 }
 error "missing resource $label"
}
proc clockgate {} {
 set expected [dict create clk_fpga_0 {20.0 0.0 10.0} black_parrot_bd_1_i/vps_0/inst/clk_wiz_0/inst/clk_in1 {20.0 0.0 10.0} clkfbout_vps_bd_1_clk_wiz_0_0 {20.0 0.0 10.0} clk_out1_vps_bd_1_clk_wiz_0_0 {50.0 0.0 25.0} clk_out2_vps_bd_1_clk_wiz_0_0 {125.0 0.0 62.5}]
 if {[lsort [get_clocks -quiet]] ne [lsort [dict keys $expected]]} {error "actual five clock identities absent/different after update_timing"}
 dict for {name tuple} $expected {
  set c [get_clocks $name];set actual [concat [get_property PERIOD $c] [get_property WAVEFORM $c]]
  foreach x $actual y $tuple {if {abs($x-$y)>0.000001} {error "clock period/waveform mismatch $name"}}
 }
}
proc inspect {tag} {
 update_timing
 clockgate
 set u [report_utilization -return_string]
 set f [open ${tag}-utilization.rpt w];puts $f $u;close $f
 set cs [report_control_sets -return_string]
 set f [open ${tag}-control-sets.rpt w];puts $f $cs;close $f
 set d [dict create LUT [value $u {Slice LUTs*}] logic_LUT [value $u {LUT as Logic}] memory_LUT [value $u {LUT as Memory}] LUTRAM [value $u {LUT as Distributed RAM}] SRL [value $u {LUT as Shift Register}] FF [value $u {Slice Registers}] control_sets RAW_REPORT_REQUIRES_CLOSURE_PARSE]
 dict set d BRAM_half [expr {2*[llength [get_cells -hier -quiet -filter {REF_NAME == RAMB36E1}]]+[llength [get_cells -hier -quiet -filter {REF_NAME == RAMB18E1}]]}]
 dict set d DSP [llength [get_cells -hier -quiet -filter {REF_NAME == DSP48E1}]]
 set f [open ${tag}-metrics.tsv w];dict for {k v} $d {puts $f "$k\t$v"};close $f
 set f [open ${tag}-clocks.tsv w]
 foreach c [lsort [get_clocks -quiet]] {puts $f "$c\t[get_property PERIOD [get_clocks $c]]\t[get_property WAVEFORM [get_clocks $c]]"};close $f
 set f [open ${tag}-clock-sources.tsv w]
 foreach c [lsort [get_clocks -quiet]] {puts $f "$c\t[get_property IS_GENERATED [get_clocks $c]]\t[get_property SOURCE_PINS [get_clocks $c]]"};close $f
 set f [open ${tag}-ports.tsv w]
 foreach p [lsort [get_ports -quiet]] {puts $f "$p\t[get_property DIRECTION [get_ports $p]]"};close $f
 set bb [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}]
 set f [open ${tag}-blackboxes.txt w];puts -nonewline $f [join $bb \n];close $f
 if {[llength $bb]} {error "checkpoint not fully linked: blackboxes"}
 report_timing_summary -max_paths 10 -file ${tag}-timing.rpt
 report_drc -file ${tag}-drc.rpt
 return $d
}
proc decision {state} {
 set f [open result.tsv w];puts $f "arm\t$::arm\nresult\t$state";close $f
 puts "POST_SYNTH_REUSE_COMPLETE $::arm $state"
 phase complete
}
phase open
open_checkpoint $input
update_timing
clockgate
if {[get_property PART [current_project]] ne "xc7z020clg400-1"} {error "wrong device"}
coverage input
phase reports
inspect input
# Reopened checkpoint was matched to the actual qualified ExploreArea opt table.
phase place
if {[catch {place_design -directive Explore} msg]} {
 set f [open place-error.txt w];puts $f $msg;close $f
 phase reports
 inspect place-failed
 write_checkpoint -force place-failed.dcp
 coverage place-failed
 decision PLACE_FAILED
 close_design
 exit 0
}
phase reports
inspect placed
write_checkpoint -force placed.dcp
coverage placed
phase physopt
phys_opt_design -directive Explore
phase reports
inspect physopt
write_checkpoint -force physopt.dcp
phase route
route_design -directive Explore -tns_cleanup
phase postroute
phys_opt_design -directive Explore
phase reports
inspect routed
write_checkpoint -force routed.dcp
coverage routed
report_route_status -file routed-status.rpt
report_timing_summary -max_paths 20 -report_unconstrained -file routed-timing.rpt
# A routed result is still a control result. No bitstream/deploy/fit acceptance
# is implied; ROOT must inspect timing/route/DRC, then clean-rebuild it.
decision ROUTED_REQUIRES_ROOT_ACCEPTANCE_AND_CLEAN_REBUILD
close_design
exit 0
