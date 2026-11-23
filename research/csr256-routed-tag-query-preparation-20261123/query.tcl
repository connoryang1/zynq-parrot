# ROOT-owned read-only query only; not a timing-model or constraint mutation.
if {[llength $argv]!=1} {error "one exact routed checkpoint"}
set base [file dirname [file normalize [info script]]]
source [file join $base pins.tcl]
if {[llength $tag_clock_pins]!=42 || [llength $tag_unconstrained_pins]!=76} {error "exact policy scope42/76"}
set_param general.maxThreads 8
if {[version -short] ne "2024.2" || [get_param general.maxThreads]!=8} {error "actual tool/thread identity"}
puts "TAG_QUERY_TOOL [version -short] THREADS [get_param general.maxThreads]"
proc phase {name} {set f [open progress.tsv w];puts $f $name;close $f}
proc onepin {name} {set p [get_pins -quiet $name];if {[llength $p]!=1} {error "missing/nonunique exact pin $name"};return [lindex $p 0]}
proc ref {p} {if {[get_property CLASS $p] eq "port"} {return TOP_LEVEL_PORT};set c [get_cells -quiet -of_objects $p];if {[llength $c]!=1} {error "single cell required $p"};return [get_property REF_NAME [lindex $c 0]]}
proc cell_domains {p} {
 if {[get_property CLASS $p] eq "port"} {return {}}
 set c [get_cells -quiet -of_objects $p]
 if {[llength $c]!=1} {error "one cell required for endpoint clock lookup $p"}
 set domains {}
 foreach cp [get_pins -quiet -of_objects $c -filter {IS_CLOCK == 1 && IS_LEAF == 1 && DIRECTION == IN}] {foreach d [get_clocks -quiet -of_objects $cp] {lappend domains $d}}
 return [lsort -unique $domains]
}
proc clean {value} {return [string map [list "\t" {\t} "\n" {\n}] $value]}
proc available {object property} {if {[lsearch -exact [list_property $object] $property]<0} {return ABSENT};return [clean [get_property $property $object]]}
proc direct {p} {set n [get_nets -quiet -segments -of_objects $p];if {![llength $n]} {return {}};return [lsort [get_pins -quiet -of_objects $n -filter {DIRECTION == OUT && IS_LEAF == 1}]]}
phase open
open_checkpoint [lindex $argv 0]
update_timing
report_clocks -file clocks.rpt
set f [open clocks.tsv w];puts $f "clock\tperiod\twaveform\tgenerated\tsources"
foreach c [lsort [get_clocks -quiet]] {puts $f "$c\t[get_property PERIOD $c]\t[get_property WAVEFORM $c]\t[get_property IS_GENERATED $c]\t[get_property SOURCE_PINS $c]"};close $f
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} existing-constraints.xdc
phase exact_pins
set f [open pin-domain-drivers.tsv w];puts $f "pin\tcell_ref\tpin_ref\tclock_domains\tlogic_value\tdirect_drivers\tdriver_refs"
set cells {};set targets {}
foreach name [concat [list $tag_root_C $tag_root_Q] $tag_clock_pins $tag_unconstrained_pins] {
 set p [onepin $name];set c [get_cells -quiet -of_objects $p];lappend cells [lindex $c 0]
 set drivers [direct $p];set refs {};foreach d $drivers {lappend refs [ref $d]}
 set domains [lsort [get_clocks -quiet -of_objects $p]]
 puts $f [join [list $p [ref $p] [available $p REF_PIN_NAME] [join $domains ,] [available $p LOGIC_VALUE] [join $drivers ,] [join $refs ,]] "\t"]
 if {[lsearch -exact $tag_clock_pins $name]>=0} {
  if {[llength $domains]} {error "existing tag pin unexpectedly gained a clock; no clock creation allowed"}
  if {[llength $drivers]!=1 || [lsearch -exact $tag_allowed_direct_drivers [lindex $drivers 0]]<0} {error "new unexplained tag driver $p $drivers"}
 }
}
close $f
set f [open net-properties.tsv w];puts $f "net\tproperty\tvalue"
set nets {}
foreach name [concat [list $tag_root_C $tag_root_Q] $tag_clock_pins] {foreach n [get_nets -quiet -segments -of_objects [onepin $name]] {lappend nets $n}}
foreach n [lsort -unique $nets] {foreach prop {NAME IS_CLOCK CLOCK_DEDICATED_ROUTE ROUTE_STATUS} {puts $f "$n\t$prop\t[available $n $prop]"}}
close $f
set f [open cell-properties.tsv w];puts $f "cell\tproperty\tvalue"
foreach c [lsort -unique $cells] {
 foreach property {REF_NAME ORIG_REF_NAME INIT IS_C_INVERTED IS_R_INVERTED IS_S_INVERTED ASYNC_REG DONT_TOUCH} {puts $f "$c\t$property\t[available $c $property]"}
 foreach p [lsort [get_pins -quiet -of_objects $c]] {
  set rp [get_property REF_PIN_NAME $p]
  if {$rp in {C D CE R S CLR PRE}} {puts $f "$c\tPIN_${rp}_LOGIC_VALUE\t[available $p LOGIC_VALUE]"}
 }
}
close $f
phase bounded_fanin
set f [open endpoint-startpoints.tsv w];puts $f "endpoint\tstartpoint\tcell_ref"
# Only the76 exact untimed endpoint pins; no broad core/register fanin walk.
foreach name $tag_unconstrained_pins {
 set p [onepin $name];set roots [lsort [all_fanin -flat -startpoints_only -to $p]]
 if {[llength $roots]>4096} {error "bounded endpoint fanin exceeded; preserve partial and stop"}
 if {![llength $roots]} {puts $f "$p\tNONE_RETURNED\tNOT_AN_INACTIVITY_PROOF"}
 foreach r $roots {puts $f "$p\t$r\t[ref $r]"}
}
close $f
phase bounded_fanout
set f [open root-and-crossing-fanout.tsv w];puts $f "source\tendpoint\tcell_ref\tclock_domains"
set sources [list $tag_root_Q]
foreach name $tag_clock_pins {
 if {[string match {*bsg_SYNC_LNCH_r_reg*} $name] || [string match {*tag_data_reg/data_r_reg*} $name]} {
  lappend sources [string range $name 0 end-1]Q
 }
}
if {[llength $sources]!=5} {error "exact root plus two launch/two data Q crossings"}
foreach name $sources {
 set p [onepin $name];set ends [lsort [all_fanout -flat -endpoints_only -from $p]]
 if {[llength $ends]>4096} {error "bounded crossing fanout exceeded; preserve partial and stop"}
 if {![llength $ends]} {puts $f "$p\tNONE_RETURNED\tNOT_AN_INACTIVITY_PROOF\t"}
 foreach e $ends {puts $f [join [list $p $e [ref $e] [join [cell_domains $e] ,]] "\t"]}
}
close $f
phase reports
check_timing -verbose -override_defaults {no_clock} -file no-clock.rpt
check_timing -verbose -override_defaults {constant_clock} -file constant-clock.rpt
check_timing -verbose -override_defaults {unconstrained_internal_endpoints} -file unconstrained.rpt
report_timing_summary -report_unconstrained -max_paths 10 -file timing.rpt
set f [open result.tsv w];puts $f "result\tREAD_ONLY_TAG_QUERY_REQUIRES_ROOT_REVIEW\nclock_pins\t42\nendpoint_pins\t76\nconstraint_mutations\t0";close $f
puts "TAG_QUERY_COMPLETE exact_tag_clock_pins=42 exact_unconstrained=76 constraint_mutations=0"
phase complete
close_design
exit 0
