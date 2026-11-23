# ROOT-only conditional timing diagnostic; no implementation change.
if {[llength $argv]!=1} {error "one ROOT-bound routed DCP"}
source {/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr256-routed-tag-query-preparation-20261123/pins.tcl}
set_param general.maxThreads 8
if {[version -short] ne "2024.2" || [get_param general.maxThreads]!=8} {error "actual2024.2/eight threads"}
puts "TAG_STA_TOOL [version -short] THREADS [get_param general.maxThreads]"
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
proc pins_report {path} {
 set f [open $path r];set text [read $f];close $f;set result {}
 foreach line [split $text \n] {if {[string match {black_parrot_bd_1_i/*} $line]} {lappend result [string trim $line]}}
 return [lsort $result]
}
proc clock_table {path} {
 set f [open $path w];puts $f "clock\tperiod\twaveform\tgenerated\tsources"
 foreach c [lsort [get_clocks -quiet]] {puts $f "$c\t[get_property PERIOD $c]\t[get_property WAVEFORM $c]\t[get_property IS_GENERATED $c]\t[get_property SOURCE_PINS $c]"}
 close $f
}
proc exact_bit {value} {
 if {$value in {0 1'b0 1'h0 FALSE false}} {return 0}
 if {$value in {1 1'b1 1'h1 TRUE true}} {return 1}
 error "inversion property is not explicit binary: <$value>; raw properties retained"
}
proc effective_C_inverted {pin} {
 set c [get_cells -quiet -of_objects $pin]
 if {[llength $c]!=1 || [ref $pin] ni {FDRE FDSE}} {error "known FDRE/FDSE primitive required"}
 # UG9122024.2: IS_INVERTED is a PIN Boolean. The installed exact
 # FDRE/FDSE models default to positive C; this explicit pin override is
 # authoritative. Empty CELL.IS_C_INVERTED is NOT converted to Boolean0.
 set pvalue [available $pin IS_INVERTED]
 set inversion [exact_bit $pvalue]
 set cvalue [available [lindex $c 0] IS_C_INVERTED]
 if {$cvalue ne {} && $cvalue ne {ABSENT} && [exact_bit $cvalue]!=$inversion} {error "cell/pin inversion evidence disagrees"}
 return $inversion
}
open_checkpoint [lindex $argv 0]
update_timing
report_utilization -file utilization.rpt
clock_table before-clocks.tsv
report_clocks -file before-clocks.rpt
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} before-constraints.xdc
report_route_status -file before-route.rpt
check_timing -verbose -override_defaults {no_clock} -file before-no-clock.rpt
check_timing -verbose -override_defaults {unconstrained_internal_endpoints} -file before-unconstrained.rpt
if {[pins_report before-no-clock.rpt] ne [lsort $tag_clock_pins] || [pins_report before-unconstrained.rpt] ne [lsort $tag_unconstrained_pins]} {error "independent exact42/76 precheck mismatch; no clock added"}
set source [onepin $tag_root_C]
set masters [get_clocks -quiet -of_objects $source]
if {[llength $masters]!=1 || [lindex $masters 0] ne "clk_out1_vps_bd_1_clk_wiz_0_0" || [get_property PERIOD [lindex $masters 0]]!=50.0} {error "actual tag source must be20MHz"}
# Capture every requested cell+clock-pin property before any polarity gate.
# report_property -all writes raw native evidence to the retained console;
# this parallel table preserves all literal property names/values too.
set serializer_Q [string map {tag_clk_reg tag_data_reg} $tag_root_Q]
set serializer [get_pins -quiet $serializer_Q]
set serializer_cell {};set serializer_C {}
if {[llength $serializer]==1} {
 set serializer_cell [get_cells -quiet -of_objects $serializer]
 if {[llength $serializer_cell]==1} {set serializer_C [get_pins -quiet -of_objects $serializer_cell -filter {REF_PIN_NAME == C}]}
}
set f [open raw-cell-pin-properties.tsv w];puts $f "object\tproperty\tvalue"
set raw_targets [concat $tag_clock_pins [list $tag_root_C]]
if {[llength $serializer_C]==1} {lappend raw_targets [lindex $serializer_C 0]}
foreach name $raw_targets {
 set cp [onepin $name];set cells [get_cells -quiet -of_objects $cp]
 if {[llength $cells]!=1} {error "one actual cell for raw C pin"}
 foreach object [concat $cells [list $cp]] {
  puts "RAW_PROPERTY_BEGIN $object"
  report_property -all $object
  puts "RAW_PROPERTY_END $object"
  foreach property [lsort [list_property $object]] {puts $f "$object\t$property\t[clean [get_property $property $object]]"}
 }
}
close $f
if {[llength $serializer]!=1 || [llength $serializer_cell]!=1 || [llength $serializer_C]!=1} {error "exact serializer FF/C missing; all available raw tag/root properties retained"}
set f [open tag-polarity-before.tsv w];puts $f "pin\tcell_ref\tC_inverted\tdirect_driver"
foreach name $tag_clock_pins {
 set p [onepin $name];set cells [get_cells -quiet -of_objects $p]
 if {[llength $cells]!=1 || [ref $p] ni {FDRE FDSE}} {error "known real positive-edge tag state changed"}
 set inv [effective_C_inverted $p]
 set drv [direct $p]
 puts $f "$p\t[ref $p]\t$inv\t[join $drv ,]"
 if {$inv!=0 || [llength [get_clocks -quiet -of_objects $p]] || [llength $drv]!=1 || [lsearch -exact $tag_allowed_direct_drivers [lindex $drv 0]]<0} {error "tag polarity/driver/unclocked contract; no clock added"}
}
close $f
foreach name $tag_unconstrained_pins {onepin $name}
set serializer_Q [string map {tag_clk_reg tag_data_reg} $tag_root_Q]
set serializer [onepin $serializer_Q]
set serializer_cell [get_cells -quiet -of_objects $serializer]
if {[llength $serializer_cell]!=1} {error "exact serializer data FF unavailable; ROOT mapping review required"}
set source_cell [get_cells -quiet -of_objects $source]
if {[effective_C_inverted $source]!=0 || [effective_C_inverted [lindex $serializer_C 0]]!=0} {error "root/source-data edge polarity unresolved"}
set f [open serializer-source-properties.tsv w];puts $f "cell_or_pin\tproperty\tvalue"
foreach c [concat $source_cell $serializer_cell] {
 foreach prop {REF_NAME INIT IS_C_INVERTED IS_R_INVERTED IS_S_INVERTED} {puts $f "$c\t$prop\t[available $c $prop]"}
 foreach p [get_pins -quiet -of_objects $c] {
  set rp [get_property REF_PIN_NAME $p]
  if {$rp in {C D CE R S}} {
   puts $f "$p\tclock_domains\t[join [cell_domains $p] ,]"
   foreach d [direct $p] {
    set dc [get_cells -quiet -of_objects $d]
    puts $f "$p\tdriver\t$d"
    foreach prop {REF_NAME INIT} {if {[llength $dc]==1} {puts $f "$d\t$prop\t[available [lindex $dc 0] $prop]"}}
   }
   if {$rp eq "CE"} {set roots [all_fanin -flat -startpoints_only -to $p];if {[llength $roots]>64} {error "bounded serializer CE cone exceeded"};puts $f "$p\tCE_startpoints\t[join [lsort $roots] ,]"}
  }
 }
}
close $f
set original_clock_objects [get_clocks -quiet]
set tag_endpoints {};foreach name $tag_unconstrained_pins {lappend tag_endpoints [onepin $name]}
# ONLY timing-model addition. It is a conservative sufficient envelope, NOT
# actual tag frequency: legal normal rising interval>=100ns; modeled50ns.
# No multicycle/falsepath/hold correction, disabled timing or case assumptions.
create_generated_clock -name tag_conservative50 -source $source -master_clock [lindex $masters 0] -divide_by 1 [onepin $tag_root_Q]
update_timing
clock_table after-clocks.tsv
report_clocks -file after-clocks.rpt
write_xdc -force -constraints ALL -no_tool_comments -type {timing io misc} after-constraints.xdc
set f [open tag-coverage-after.tsv w];puts $f "pin\tclock_domains"
foreach name $tag_clock_pins {
 set p [onepin $name];set domains [lsort [get_clocks -quiet -of_objects $p]]
 puts $f "$p\t[join $domains ,]"
 if {$domains ne {tag_conservative50}} {error "generated clock did not cover exactly each known sink"}
}
close $f
# Reports are written before interpreting violations. Failing timing is useful
# diagnostic evidence and is never converted into a source-data hold waiver.
check_timing -verbose -file full-check-timing.rpt
check_timing -verbose -override_defaults {no_clock} -file after-no-clock.rpt
check_timing -verbose -override_defaults {unconstrained_internal_endpoints} -file after-unconstrained.rpt
report_timing_summary -report_unconstrained -max_paths 20 -file timing.rpt
report_timing -delay_type max -max_paths 20 -file setup-recovery.rpt
report_timing -delay_type min -max_paths 20 -file hold-removal.rpt
proc report_pair {base from to} {
 foreach delay {max min} {
  set path "${base}-${delay}.rpt"
  report_timing -from $from -to $to -delay_type $delay -path_type full_clock_expanded -max_paths 20 -file $path
  if {![file exists $path]} {set f [open $path w];puts $f "NO_PATH_RETURNED; REQUIRES_ROOT_REVIEW; NOT_INACTIVE_PROOF";close $f}
 }
}
set tag_clock [get_clocks tag_conservative50]
report_pair serializer-to-tag [list $serializer] $tag_endpoints
report_pair tag-internal $tag_clock $tag_clock
report_pair original-to-tag $original_clock_objects $tag_clock
report_pair tag-to-original $tag_clock $original_clock_objects
set async_pins [all_registers -async_pins -quiet]
set f [open async-targets.tsv w];foreach p [lsort $async_pins] {puts $f $p};close $f
if {[llength $async_pins]} {
 report_timing -to $async_pins -delay_type max -max_paths 20 -file asynchronous-recovery.rpt
 report_timing -to $async_pins -delay_type min -max_paths 20 -file asynchronous-removal.rpt
} else {
 foreach name {asynchronous-recovery.rpt asynchronous-removal.rpt} {set f [open $name w];puts $f "NO_ASYNC_REGISTER_PINS_RETURNED; full timing summary still required";close $f}
}
set f [open endpoint-paths.tsv w];puts $f "endpoint\tdelay_type\tslack\tstartpoint\tendpoint_clock"
foreach name $tag_unconstrained_pins {
 set p [onepin $name]
 foreach delay {max min} {
  set paths [get_timing_paths -quiet -to $p -delay_type $delay -max_paths 1]
  if {![llength $paths]} {puts $f "$p\t$delay\tNONE_RETURNED_REQUIRES_REVIEW\t\t"}
  foreach path $paths {puts $f "$p\t$delay\t[available $path SLACK]\t[available $path STARTPOINT_PIN]\t[available $path ENDPOINT_CLOCK]"}
 }
}
close $f
report_cdc -details -file cdc.rpt
report_drc -file drc.rpt
report_route_status -file after-route.rpt
set f [open drc-severity.tsv w];puts $f "violation\tseverity"
foreach v [lsort [get_drc_violations -quiet]] {puts $f "$v\t[available $v SEVERITY]"};close $f
puts "TAG_STA_COLLECTION_COMPLETE clocks_added=1 tag_sinks=42 original_endpoints=76; ROOT_REVIEW_REQUIRED"
close_design
exit 0
