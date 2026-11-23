# ROOT-owned leaf only. Parent verifies exact admission, inputs/source/tool,
# fresh output, resource/time bounds and one-vendor ownership before entry.
if {[llength $argv] != 6} {error "INPUT_DCP HWH POLICY OUT CLOSED07_COLLECT CLOSED07_COVERAGE"}
lassign $argv input hwh policy out collector gate_script
if {[file exists $out]} {error "fresh output required"}
file mkdir $out
cd $out
set progress_root [pwd]
proc phase {name} {
 set f [open [file join $::progress_root progress.json.tmp] w]
 puts $f "\{\"phase\":\"$name\",\"started_epoch\":[clock seconds]\}"
 close $f
 file rename -force [file join $::progress_root progress.json.tmp] [file join $::progress_root progress.json]
 puts "ROUTED_BITGEN_PHASE $name"
}
set_param general.maxThreads 8
if {[version -short] ne "2024.2" || [get_param general.maxThreads] != 8} {error "wrong tool/threads"}
source $collector
proc clockgate {} {
 set expected [dict create clk_fpga_0 {20 0 10} black_parrot_bd_1_i/vps_0/inst/clk_wiz_0/inst/clk_in1 {20 0 10} clkfbout_vps_bd_1_clk_wiz_0_0 {20 0 10} clk_out1_vps_bd_1_clk_wiz_0_0 {50 0 25} clk_out2_vps_bd_1_clk_wiz_0_0 {125 0 62.5}]
 if {[lsort [get_clocks -quiet]] ne [lsort [dict keys $expected]]} {error "five clock identity mismatch"}
 dict for {n tuple} $expected {
  set actual [concat [get_property PERIOD [get_clocks $n]] [get_property WAVEFORM [get_clocks $n]]]
  if {[llength $actual] != 3} {error "clock tuple width"}
  foreach x $actual y $tuple {if {abs($x-$y)>0.000001} {error "clock waveform/period mismatch $n"}}
 }
}
proc routed_gate {tag} {
 update_timing
 clockgate
 set status [report_route_status -return_string]
 set f [open ${tag}-route.rpt w];puts $f $status;close $f
 foreach {label expected} {{routable nets} 84324 {fully routed nets} 84324 {nets with routing errors} 0} {
  set matches [regexp -all -inline -line -- [format {# of %s\.+ : *([0-9]+) :} $label] $status]
  if {[llength $matches] != 2 || [lindex $matches 1] != $expected} {error "closed route status mismatch: $label"}
 }
 foreach kind {max min} {
  set paths [get_timing_paths -quiet -delay_type $kind -max_paths 1]
  if {[llength $paths] != 1 || [get_property SLACK [lindex $paths 0]] < 0} {error "constrained timing failure/absence $kind"}
 }
 report_timing_summary -report_unconstrained -max_paths 20 -file ${tag}-timing.rpt
 report_drc -file ${tag}-drc.rpt
 report_utilization -file ${tag}-utilization.rpt
 coverage $tag
}
# Byte-identical body of the maintained vivado_gen_map, with only proc name
# kept unchanged. Archived HWH exact identity is enforced by ROOT parent.
proc vivado_gen_map { proj_hwh proj_map } {
    set f [open ${proj_hwh} "r"]
    set m [open ${proj_map} "w"]
    set search "*MEMRANGE*"
    while {[gets ${f} line] >= 0} {
        if {[string match ${search} ${line}]} {
            regexp -nocase -line -- {BASEVALUE="(.*?)"} ${line} value base
            regexp -nocase -line -- {([A-Z][A-Z][0-9])_AXI} ${line} value port
            puts "Found Port ${port}: ${base}"
            puts -nonewline $m "-D${port}_ADDR_BASE=${base} "
        }
    }
    close $m
    close $f
}
phase open
open_checkpoint $input
if {[get_property PART [current_project]] ne "xc7z020clg400-1"} {error "wrong part"}
routed_gate input
phase bitgen
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY} [current_project]
write_bitstream -force black_parrot_bd_1.bit
# BIT is retained even if any subsequent reporting/coverage/handoff step fails.
phase reports
routed_gate output
file copy $hwh black_parrot_bd_1.hwh
vivado_gen_map black_parrot_bd_1.hwh black_parrot_bd_1.map
set f [open result.txt w]
puts $f "BITGEN_COMMAND_COMPLETED; ROOT route/DRC/source/package review pending; tag42/unconstrained76 limitation retained"
close $f
phase complete
close_design
