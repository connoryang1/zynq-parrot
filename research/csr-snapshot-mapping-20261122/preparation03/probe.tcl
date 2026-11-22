if {[llength $argv]!=1 || [lsearch -exact {baseline-single-source resetless-single} [lindex $argv 0]]<0} {error "one fixed arm"}
set arm [lindex $argv 0]
set base [file dirname [file normalize [info script]]]
set_param general.maxThreads 2
create_project -in_memory -part xc7z020clg400-1
puts "ACTUAL_TOOL_VERSION [version -short]"
puts "ACTUAL_MAX_THREADS [get_param general.maxThreads]"
if {![string match 2024.2* [version -short]] || [get_param general.maxThreads]!=2} {error "tool/thread identity"}
if {$arm eq "baseline-single-source"} {
 read_verilog -sv [file join $base reference.sv]
 read_verilog -sv -define CSR_SNAPSHOT_BASELINE [file join $base wrapper.sv]
} else {
 read_verilog -sv [file join $base candidate.sv]
 read_verilog -sv [file join $base wrapper.sv]
}
read_xdc [file join $base clock.xdc]
synth_design -top csr_snapshot_consumer_wrapper -part xc7z020clg400-1 -mode out_of_context -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1
set bb [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
set f [open blackboxes.txt w];puts $f $bb;close $f
if {[llength $bb]} {error "blackboxes"}
set f [open clocks.tsv w]
foreach c [get_clocks] {puts $f [join [list $c [get_property PERIOD $c] [get_property WAVEFORM $c]] "\t"]}
close $f
set f [open ports.tsv w];puts $f "name\tdirection\tbits"
foreach {n w} {clk_i 1 reset_i 1 cache_restore_i 1 resident_init_i 1 prior_image_i 1666 restore_v_o 1 restore_reset_o 1 instret_i 1 csrw_i 1 ctxtsw_i 1 addr801_i 1 rebind_i 1 legacy_access_i 2 current_bank_i 1 retire_bank_i 1 save_bank_i 1 reservation_bank_i 1 save_context_i 2 seed_context_i 2 read_context_i 2 bank0_data_i 1666 bank1_data_i 1666 save_intent_o 1 seed_intent_o 1 read_valid_o 1 reservation_owner_o 1 valid_vector_o 4 restored_image_o 1666} {
 if {$w==1} {set p [get_ports -quiet $n]} else {set p [get_ports -quiet [format {%s[*]} $n]]}
 if {[llength $p]!=$w} {error "missing/pruned port $n expected$w got[llength $p]"}
 puts $f [join [list $n [get_property DIRECTION [lindex $p 0]] [llength $p]] "\t"]
}
close $f
set f [open payload-drivers.tsv w];puts $f "port\tnet\tdriver_cell\tREF_NAME"
foreach p [get_ports {restored_image_o[*]}] {
 set n [get_nets -of_objects $p]
 set c [get_cells -quiet -of_objects [get_pins -quiet -of_objects $n -filter {DIRECTION == OUT}]]
 if {[llength $c]==0} {error "payload driver missing $p"}
 foreach d $c {
  set r [get_property REF_NAME $d]
  if {$r eq "GND" || $r eq "VCC"} {error "constant/pruned payload output $p"}
  puts $f [join [list $p $n $d $r] "\t"]
 }
}
close $f
report_utilization -hierarchical -file utilization.rpt
report_timing_summary -report_unconstrained -file timing-summary.rpt
report_timing -max_paths 20 -file timing-paths.rpt
report_control_sets -verbose -file control-sets.rpt
set f [open primitives.tsv w];puts $f "name\tREF_NAME\tIS_PRIMITIVE"
foreach c [lsort [get_cells -hier]] {puts $f [join [list $c [get_property REF_NAME $c] [get_property IS_PRIMITIVE $c]] "\t"]}
close $f
# Retain actual per-instance storage properties and all properties of one
# actual representative per used primitive REF_NAME. Macro/leaf overlap is
# reported, not summed into physical memory sites. No mapped simulation here.
set f [open storage-properties.tsv w];puts $f "cell\tREF_NAME\tproperty\tvalue"
set r [open used-ref-properties.tsv w];puts $r "REF_NAME\tactual_representative_cell\tproperty\tvalue"
set seen [dict create]
foreach c [lsort [get_cells -hier -filter {IS_PRIMITIVE == 1}]] {
 set ref [get_property REF_NAME $c]
 set first [expr {![dict exists $seen $ref]}]
 if {$first} {dict set seen $ref $c}
 set storage [expr {[string match RAM* $ref] || [string match FD* $ref]}]
 if {$storage || $first} {
  set properties [lsort [list_property $c]]
  foreach prop $properties {
   # Full configuration is retained once per actual used REF_NAME. Per-cell
   # FD rows need only semantic, polarity, clock, reset and enable properties;
   # full netlist/DCP preserve every connection and mapped primitive.
   set needed [expr {[lsearch -exact {REF_NAME IS_PRIMITIVE INIT IS_C_INVERTED IS_CE_INVERTED IS_R_INVERTED IS_S_INVERTED IS_CLR_INVERTED IS_PRE_INVERTED} $prop]>=0}]
   set ram [string match RAM* $ref]
   set ram_needed [expr {$ram && ([string match INIT* $prop] || [string match IS_*_INVERTED $prop] || [string match READ_* $prop] || [string match WRITE_* $prop] || [string match DO*_REG $prop] || [string match SRVAL* $prop] || $prop eq "RAM_MODE" || $prop eq "REF_NAME" || $prop eq "IS_PRIMITIVE")}]
   if {$first || ($storage && ($ram_needed || $needed))} {
    set value [string map [list "\t" {\t} "\n" {\n}] [get_property $prop $c]]
    if {$storage && ($ram_needed || $needed)} {puts $f [join [list $c $ref $prop $value] "\t"]}
    if {$first} {puts $r [join [list $ref $c $prop $value] "\t"]}
   }
  }
  if {$storage && [string match RAM* $ref]} {
   foreach pin [get_pins -of_objects $c -filter {REF_PIN_NAME =~ *CLK* || REF_PIN_NAME =~ WE* || REF_PIN_NAME =~ EN* || REF_PIN_NAME =~ RST*}] {
    puts $f [join [list $c $ref [format {PIN:%s} [get_property REF_PIN_NAME $pin]] [get_nets -of_objects $pin]] "\t"]
   }
  }
  if {$storage && [string match FD* $ref]} {
   foreach pin [get_pins -of_objects $c -filter {REF_PIN_NAME == C || REF_PIN_NAME == CE || REF_PIN_NAME == R || REF_PIN_NAME == S || REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}] {
    set nets [get_nets -of_objects $pin]
    puts $f [join [list $c $ref [format {PIN:%s} [get_property REF_PIN_NAME $pin]] $nets] "\t"]
   }
  }
 }
}
close $f;close $r
write_checkpoint -force synthesized.dcp
write_verilog -mode funcsim functional.v
puts "CSR_SNAPSHOT_MAPPING_COMPLETE $arm"
