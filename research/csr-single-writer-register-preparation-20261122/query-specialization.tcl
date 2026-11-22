# SOURCE ONLY. ROOT must pin the exact closed synthesized DCP and release first.
# No synthesis, implementation, property mutation or checkpoint write is allowed.
if {[llength $argv] != 2} {error "exact closed DCP and fresh output directory required"}
set dcp [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {![file isfile $dcp] || [file exists $output]} {error "closed DCP/fresh output required"}
open_checkpoint $dcp
file mkdir $output
set stores [get_cells -quiet -hier -filter {NAME =~ */csr_snapshot_store}]
if {[llength $stores] != 1} {error "exact integrated store hierarchy not preserved; no guessed projection"}
set store [lindex $stores 0]
set ref [get_property REF_NAME $store]
if {![string match bp_be_csr_snapshot_store_production* $ref]} {error "unexpected store reference"}
proc field {value} {return [string map [list "\t" {\t} "\n" {\n}] $value]}
set identity [open [file join $output identity.tsv] w]
puts $identity "scope\tREAD ONLY raw current integrated specialization; not a passing projection"
puts $identity "dcp\t[field $dcp]"
puts $identity "tool\t[version -short]"
puts $identity "part\t[get_property PART [current_design]]"
puts $identity "store\t[field $store]"
puts $identity "reference\t[field $ref]"
puts $identity "declared_TOP_external_ROOT_binding_required\ta44c03bb7bc520a3b5727c2bb619a055a7ed5acd"
puts $identity "declared_BP_external_ROOT_binding_required\t1e7aa2fdc94a56373a26f95b145aff361d4d0aaa"
foreach clock [get_clocks] {puts $identity "clock\t[field $clock]\t[get_property PERIOD $clock]\t[get_property WAVEFORM $clock]"}
close $identity

# Preserve pin/net/driver/sink identities. Equal names, missing pins and temporal
# correlations are not silently converted into a field/constant equivalence.
set connectivity [open [file join $output connectivity.tsv] w]
puts $connectivity "store_pin\tdirection\tnet\tpeer_pin\tpeer_direction\tpeer_cell\tREF_NAME\tIS_PRIMITIVE"
set pins [get_pins -quiet -of_objects $store]
foreach pin [lsort $pins] {
 set direction [get_property DIRECTION $pin]
 foreach net [get_nets -quiet -of_objects $pin] {
  set peers [get_pins -quiet -of_objects $net]
  if {![llength $peers]} {puts $connectivity "[field $pin]\t$direction\t[field $net]\tNO_EXPOSED_PEER\t\t\t\t"}
  foreach peer [lsort $peers] {
   set cells [get_cells -quiet -of_objects $peer]
   if {![llength $cells]} {puts $connectivity "[field $pin]\t$direction\t[field $net]\t[field $peer]\t[get_property DIRECTION $peer]\tNO_CELL\t\t"}
   foreach cell $cells {
    puts $connectivity "[field $pin]\t$direction\t[field $net]\t[field $peer]\t[get_property DIRECTION $peer]\t[field $cell]\t[get_property REF_NAME $cell]\t[get_property IS_PRIMITIVE $cell]"
   }
  }
 }
}
close $connectivity
set bits [open [file join $output payload-bit-presence.tsv] w]
puts $bits "port\tbit\texposed_pin\tstatus"
set pins_by_reference [dict create]
foreach pin $pins {dict lappend pins_by_reference [get_property REF_PIN_NAME $pin] $pin}
foreach port {write_data_i read_data_o} {
 for {set bit 0} {$bit < 1666} {incr bit} {
  set found {}
  set key [format {%s[%d]} $port $bit]
  if {[dict exists $pins_by_reference $key]} {set found [dict get $pins_by_reference $key]}
  if {[llength $found] > 1} {error "ambiguous actual payload pin"}
  if {[llength $found]} {
   puts $bits "$port\t$bit\t[field [lindex $found 0]]\tEXPOSED"
  } else {
   puts $bits "$port\t$bit\t\tABSENT_UNCLASSIFIED_NOT_ASSUMED_ZERO"
  }
 }
}
close $bits
puts "CSR_STORE_SPECIALIZATION_QUERY_COMPLETE raw-evidence-only"
close_design
