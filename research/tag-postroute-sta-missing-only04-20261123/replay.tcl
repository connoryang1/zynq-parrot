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
clock_table before-clocks.tsv
set source [onepin $tag_root_C]
set masters [get_clocks -quiet -of_objects $source]
if {[llength [get_clocks -quiet]]!=5 || $masters ne {clk_out1_vps_bd_1_clk_wiz_0_0} || [get_property PERIOD [lindex $masters 0]]!=50.0} {error "same five clocks/source20MHz"}
set rootcell [get_cells -quiet -of_objects $source]
set serializer_Q [string map {tag_clk_reg tag_data_reg} $tag_root_Q]
set serializer [onepin $serializer_Q]
set serialcell [get_cells -quiet -of_objects $serializer]
if {[llength $rootcell]!=1 || [llength $serialcell]!=1 || [get_property REF_NAME $rootcell] ne "FDSE" || [get_property REF_NAME $serialcell] ne "FDRE"} {error "exact synchronous-set root/serializer primitives"}
set serialC [onepin "$serialcell/C"]
foreach p [list $source $serialC] {if {[effective_C_inverted $p]!=0 || [get_clocks -quiet -of_objects $p] ne $masters} {error "same positive source/serializer edge"}}
set f [open tag-polarity.tsv w];puts $f "pin\tref\tinverted\tdriver"
foreach name $tag_clock_pins {
 set p [onepin $name];set inv [effective_C_inverted $p];set drv [direct $p]
 puts $f "$p\t[ref $p]\t$inv\t[join $drv ,]"
 if {$inv!=0 || [llength [get_clocks -quiet -of_objects $p]] || [llength $drv]!=1 || [lsearch -exact $tag_allowed_direct_drivers [lindex $drv 0]]<0} {error "same42 unclocked positive tag sinks"}
}
close $f
foreach name $tag_unconstrained_pins {onepin $name}
# Only literal one-LUT cones. Do not traverse the full design.
proc origin {pin} {
 set ds [direct $pin];if {[llength $ds]!=1} {error "one direct signal driver $pin"};set d [lindex $ds 0]
 if {[ref $d] in {BUFG BUFGCTRL}} {
  set c [get_cells -quiet -of_objects $d]
  set ins [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == I || REF_PIN_NAME == I0}]
  if {[llength $ins]!=1} {error "one known buffer data input"}
  set ds [direct [lindex $ins 0]];if {[llength $ds]!=1} {error "one buffer input driver"};set d [lindex $ds 0]
 }
 return $d
}
proc init_number {s} {
 if {[regexp {^[0-9]+'[hH]([0-9a-fA-F]+)$} $s -> digits]} {scan $digits %x value;return $value}
 if {[regexp {^[0-9]+'[bB]([01]+)$} $s -> digits]} {set n 0;foreach d [split $digits {}] {set n [expr {2*$n+$d}]};return $n}
 if {[string is integer -strict $s]} {return $s}
 error "unrecognized INIT representation $s"
}
set expectedV [string map {bb/tag_clk_reg/data_r_reg[0]/Q zps/csr_data_new_r_reg[1]/Q} $tag_root_Q]
onepin $expectedV
set f [open logic.tsv w];puts $f "role\tobject\tref\tINIT\tdirect_driver\tresolved_origin"
foreach pair [list [list root $rootcell] [list serializer $serialcell]] {
 lassign $pair role c
 foreach p [get_pins -quiet -of_objects $c] {
  set rp [get_property REF_PIN_NAME $p];if {$rp ni {C D CE R S}} {continue}
  set drv [direct $p];puts $f "$role/$rp\t$p\t[ref $p]\t[available $c INIT]\t[join $drv ,]\t[origin $p]"
 }
}
foreach spec [list [list rootD "$rootcell/D" 7] [list dataCE "$serialcell/CE" 8]] {
 lassign $spec role name truth
 set p [onepin $name];set drv [direct $p]
 if {[llength $drv]!=1 || [ref [lindex $drv 0]] ne "LUT2"} {error "exact LUT2 $role"}
 set lut [get_cells -quiet -of_objects [lindex $drv 0]]
 if {[init_number [get_property INIT $lut]]!=$truth} {error "NAND7/AND8 truth table changed"}
 set origins {}
 foreach ip [lsort [get_pins -quiet -of_objects $lut -filter {DIRECTION == IN}]] {
  set o [origin $ip];lappend origins $o
  puts $f "$role/input\t$ip\t[ref $ip]\t[get_property INIT $lut]\t[join [direct $ip] ,]\t$o"
 }
 if {[lsort $origins] ne [lsort [list $tag_root_Q $expectedV]]} {error "same literal q/v operands required"}
}
foreach spec [list [list "$rootcell/CE" VCC] [list "$serialcell/R" GND]] {
 lassign $spec name constant;set ds [direct [onepin $name]]
 if {[llength $ds]!=1 || [ref [lindex $ds 0]] ne $constant} {error "rootCE VCC/serializerR GND required"}
}
set sd [direct [onepin "$rootcell/S"]]
if {[llength $sd]!=1 || [ref [lindex $sd 0]] ne "LUT1" || [init_number [get_property INIT [get_cells -quiet -of_objects [lindex $sd 0]]]]!=1} {error "exact synchronous rootS invert cone"}
foreach ip [get_pins -quiet -of_objects [get_cells -quiet -of_objects [lindex $sd 0]] -filter {DIRECTION == IN}] {puts $f "rootS/input\t$ip\t[ref $ip]\t1\t[join [direct $ip] ,]\t[origin $ip]"}
close $f
# Same sole model addition as03. No disable_timing, falsepath, multicycle,
# case assumptions, IO changes, implementation or other clock additions.
create_generated_clock -add -name tag_conservative50 -source $source -master_clock [lindex $masters 0] -divide_by 1 [onepin $tag_root_Q]
update_timing
clock_table after-clocks.tsv
if {[llength [get_clocks -quiet]]!=6} {error "exactly one clock addition"}
set f [open tag-coverage.tsv w];puts $f "pin\tdomain"
foreach name $tag_clock_pins {
 set p [onepin $name];set domains [get_clocks -quiet -of_objects $p]
 puts $f "$p\t[join $domains ,]"
 if {$domains ne {tag_conservative50}} {error "all42 exact tag clock"}
}
close $f
check_timing -verbose -override_defaults {no_clock} -file after-no-clock.rpt
check_timing -verbose -override_defaults {unconstrained_internal_endpoints} -file after-unconstrained.rpt
report_exceptions -file exceptions.rpt
report_cdc -details -file cdc.rpt
report_route_status -file route.rpt
report_drc -file drc.rpt
set f [open drc-severity.tsv w];puts $f "violation\tseverity"
foreach v [lsort [get_drc_violations -quiet]] {puts $f "$v\t[available $v SEVERITY]"};close $f
puts "TAG_MISSING_COLLECTION_COMPLETE logic_checked=1 tag_sinks=42; ROOT_REVIEW_REQUIRED"
close_design
exit 0
