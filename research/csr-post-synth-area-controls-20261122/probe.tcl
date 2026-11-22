# Fixed post-synthesis controls only. No read_verilog/synth_design/IP rebuild.
set arm [lindex $argv 0]
set input [lindex $argv 1]
set baseline [lindex $argv 2]
if {$arm ni {baseline entry area1 area2}} {error "unreviewed arm"}
set_param general.maxThreads 8
if {[get_param general.maxThreads] != 8 || [version -short] ne "2024.2"} {error "wrong tool/settings"}
puts "ACTUAL_TOOL_VERSION [version -short] ACTUAL_MAX_THREADS [get_param general.maxThreads]"
proc phase {name} {
 set f [open progress.json.tmp w]
 puts $f "\{\"phase\":\"$name\",\"started_epoch\":[clock seconds]\}"
 close $f
 file rename -force progress.json.tmp progress.json
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
 set d [dict create LUT [value $u {Slice LUTs*}] logic_LUT [value $u {LUT as Logic}] memory_LUT [value $u {LUT as Memory}] LUTRAM [value $u {LUT as Distributed RAM}] SRL [value $u {LUT as Shift Register}] FF [value $u {Slice Registers}] control_sets [value $cs {Total control sets}]]
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
proc baseline_metrics {file} {
 set f [open $file r];set d [dict create]
 foreach row [split [read $f] \n] {if {$row ne ""} {lassign [split $row \t] k v;dict set d $k $v}}
 close $f;return $d
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
report_clocks -file input-report-clocks.rpt
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} input-constraints.xdc
set ef [open input-endpoints.tsv w]
foreach {pattern period} {{*/core_minimal/clk_i} 50.0 {*/processor/rt_clk_i} 125.0} {
 set pins [get_pins -hier -quiet -filter [format {NAME =~ %s} $pattern]]
 if {![llength $pins]} {error "missing required clock endpoint $pattern"}
 foreach p $pins {
  set clocks [get_clocks -quiet -of_objects $p]
  if {![llength $clocks]} {error "unconstrained endpoint $p after update_timing"}
  foreach c $clocks {
   if {abs([get_property PERIOD $c]-$period)>0.000001} {error "wrong endpoint clock $p"}
   puts $ef "$p\t$c\t[get_property PERIOD $c]\t[get_property WAVEFORM $c]"
  }
 }
}
close $ef
if {[get_property PART [current_project]] ne "xc7z020clg400-1"} {error "wrong device"}
if {$arm in {baseline entry}} {
 phase reports
 inspect $arm
 decision READ_ONLY_[string toupper $arm]
 close_design
 exit 0
}
foreach file {input-constraints.xdc input-endpoints.tsv} {
 set f [open $file r];set actual [read $f];close $f
 set f [open [file join [file dirname $baseline] .. entry $file] r];set expected [read $f];close $f
 if {$actual ne $expected} {error "entry constraint/endpoint drift before opt"}
}
phase opt
if {$arm eq "area1"} {opt_design -directive ExploreArea} else {opt_design -directive ExploreSequentialArea}
phase reports
set metrics [inspect opt]
write_checkpoint -force optimized.dcp
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} opt-constraints.xdc
foreach {actual expected} {opt-clocks.tsv baseline-clocks.tsv opt-clock-sources.tsv baseline-clock-sources.tsv opt-ports.tsv baseline-ports.tsv opt-constraints.xdc input-constraints.xdc} {
 set f [open $actual r];set body [read $f];close $f
 set f [open [file join [file dirname $baseline] $expected] r];set prior [read $f];close $f
 if {$body ne $prior} {error "postopt constraint/clock/source/port coverage differs before place: $actual"}
}
# Fixed engineering screening rule, not a theorem about placement:
# reject only if every recorded resource is no better and at least one
# packing-limiting resource (LUT/control sets/BRAM) strictly worsens.
set b [baseline_metrics $baseline]
set nobetter 1
foreach k {LUT logic_LUT memory_LUT LUTRAM SRL FF control_sets BRAM_half DSP} {
 if {[dict get $metrics $k] < [dict get $b $k]} {set nobetter 0}
}
set worse [expr {[dict get $metrics LUT]>[dict get $b LUT] || [dict get $metrics control_sets]>[dict get $b control_sets] || [dict get $metrics BRAM_half]>[dict get $b BRAM_half]}]
if {$nobetter && $worse} {decision RESOURCE_DOMINATED;close_design;exit 0}
phase place
if {[catch {place_design -directive Explore} msg]} {
 set f [open place-error.txt w];puts $f $msg;close $f
 phase reports
 inspect place-failed
 write_checkpoint -force place-failed.dcp
 decision PLACE_FAILED
 close_design
 exit 0
}
phase reports
inspect placed
write_checkpoint -force placed.dcp
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
report_route_status -file routed-status.rpt
report_timing_summary -max_paths 20 -report_unconstrained -file routed-timing.rpt
write_checkpoint -force routed.dcp
# A routed result is still a control result. No bitstream/deploy/fit acceptance
# is implied; ROOT must inspect timing/route/DRC, then clean-rebuild it.
decision ROUTED_REQUIRES_ROOT_ACCEPTANCE_AND_CLEAN_REBUILD
close_design
exit 0
