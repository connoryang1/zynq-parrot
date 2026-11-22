# Read-only mapped clock-sink qualification; no opt/place/route or new clocks.
set arm [lindex $argv 0]
set input [lindex $argv 1]
if {$arm ni {entry baseline}} {error "one fixed read-only stage"}
set_param general.maxThreads 8
if {[version -short] ne "2024.2" || [get_param general.maxThreads]!=8} {error "tool/settings"}
proc phase {name} {
 set f [open progress.json.tmp w]
 puts $f "\{\"phase\":\"$name\",\"started_epoch\":[clock seconds]\}"
 close $f;file rename -force progress.json.tmp progress.json
}
proc cell_ref {pin} {
 set cells [get_cells -quiet -of_objects $pin]
 if {[llength $cells]!=1} {error "not exactly one cell for leaf pin $pin"}
 set ref [get_property REF_NAME [lindex $cells 0]]
 if {$ref eq ""} {error "empty primitive cell reference for $pin"}
 return $ref
}
phase open
open_checkpoint $input
update_timing
report_clocks -file clocks.rpt
set f [open clocks.tsv w];puts $f "clock\tperiod\twaveform\tgenerated\tsources"
foreach c [lsort [get_clocks -quiet]] {
 puts $f "$c\t[get_property PERIOD $c]\t[get_property WAVEFORM $c]\t[get_property IS_GENERATED $c]\t[get_property SOURCE_PINS $c]"
}
close $f
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} constraints.xdc
set f [open ports.tsv w]
foreach p [lsort [get_ports -quiet]] {puts $f "$p\t[get_property DIRECTION $p]"};close $f
set f [open blackboxes.txt w]
puts -nonewline $f [join [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}] \n];close $f
phase inspect
set TAGROOT {black_parrot_bd_1_i/top_0/inst/top/inst/top_fpga_inst/bb/tag_clk_reg/data_r_reg[0]/Q}
set f [open clock-sinks.tsv w]
puts $f "pin\tcell_ref\tpin_ref\tregion\tclass\tclock_domains\tlogic_value\tdirect_drivers\tfanin_startpoints"
set counts [dict create]
set pins [lsort [get_pins -hier -quiet -filter {IS_CLOCK == 1 && IS_LEAF == 1 && DIRECTION == IN}]]
foreach p $pins {
 set ref [cell_ref $p]
 set rp [get_property REF_PIN_NAME $p]
 set region SHELL
 if {[string match */processor/* $p]} {set region PROCESSOR}
 if {[string match */core_minimal/* $p]} {set region CORE}
 set clocks [lsort [get_clocks -quiet -of_objects $p]]
 set value [get_property LOGIC_VALUE $p]
 set drivers {};set roots {}
 if {[llength $clocks]} {
  set class CLOCKED
 } else {
  # Fanin is intentionally limited to UNclocked sinks, not every core flop.
  set nets [get_nets -quiet -segments -of_objects $p]
  if {[llength $nets]} {set drivers [lsort [get_pins -quiet -of_objects $nets -filter {DIRECTION == OUT && IS_LEAF == 1}]]}
  set constant 1;set levels {}
  if {![llength $drivers]} {set constant 0}
  foreach d $drivers {
   set dr [cell_ref $d]
   if {$dr ni {GND VCC}} {set constant 0}
   lappend levels $dr
  }
  if {$constant && [regexp {^RAMB(18|36)E1$} $ref]} {
   set class STATIC_RAM_[join [lsort -unique $levels] _]
  } else {
   set roots [lsort [all_fanin -flat -startpoints_only -to $p]]
   if {[llength $roots]==1 && [lindex $roots 0] eq $TAGROOT} {
    set class TAG_ROOT_CANDIDATE
   } elseif {$constant} {
    set class STATIC_NONRAM_REVIEW
   } else {
    set class UNEXPLAINED
   }
  }
 }
 puts $f "$p\t$ref\t$rp\t$region\t$class\t[join $clocks ,]\t$value\t[join $drivers ,]\t[join $roots ,]"
 dict incr counts [join [list $class $region $ref $rp [join $clocks ,]] \t]
}
close $f
set f [open sink-signatures.tsv w]
dict for {key n} $counts {puts $f "$key\t$n"};close $f
phase reports
check_timing -verbose -override_defaults {no_clock} -file check-no-clock.rpt
check_timing -verbose -override_defaults {constant_clock} -file check-constant-clock.rpt
check_timing -verbose -override_defaults {unconstrained_internal_endpoints} -file check-unconstrained.rpt
report_timing_summary -report_unconstrained -max_paths 10 -file timing-summary.rpt
report_utilization -file utilization.rpt
set f [open result.tsv w]
puts $f "arm\t$arm\nresult\tREAD_ONLY_DIAGNOSTIC_REQUIRES_ROOT_REVIEW";close $f
puts "CLOCK_DIAGNOSTIC_COMPLETE $arm leaf_clock_pins=[llength $pins]; no optimization or acceptance"
phase complete
close_design
exit 0
