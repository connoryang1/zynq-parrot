# SOURCE-ONLY recipe. ROOT admission/owned worker is required before use.
if {[llength $argv]!=1 || [lsearch -exact {ram registers} [lindex $argv 0]]<0} {error "one fixed primary arm"}
set arm [lindex $argv 0]
set base [file dirname [file normalize [info script]]]
source [file join $base sources.tcl]
set store_base [file normalize [file join $base .. csr-single-writer-register-preparation-20261122]]
set_param general.maxThreads 2
create_project -in_memory -part xc7z020clg400-1
if {![string match 2024.2* [version -short]] || [get_param general.maxThreads]!=2} {error "tool/thread identity"}
puts "PRIMARY_TOOL [version -short] THREADS [get_param general.maxThreads]"
# Actual closed final-BD synth_1 fileset semantics, all seven defines retained.
set_property verilog_define $actual_defines [get_filesets sources_1]
set_property include_dirs $actual_include_dirs [get_filesets sources_1]
if {[get_property verilog_define [get_filesets sources_1]] ne $actual_defines} {error "seven defines changed"}
if {[get_property include_dirs [get_filesets sources_1]] ne $actual_include_dirs} {error "include order changed"}
set f [open source-context.tsv w]
puts $f "verilog_define\t[get_property verilog_define [get_filesets sources_1]]"
puts $f "include_dirs\t[get_property include_dirs [get_filesets sources_1]]"
foreach s $actual_sources {puts $f "read_verilog\t$s";read_verilog -sv $s}
close $f
read_verilog -sv [file join $store_base store-${arm}.sv]
read_verilog -sv [file join $base csr_native_consumer_wrapper.sv]
read_xdc [file join $store_base clock.xdc]
# Both arms identical; OOC/2 workers differ explicitly from whole-device/8.
synth_design -top csr_native_consumer_wrapper -part xc7z020clg400-1 -mode out_of_context -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1
set bb [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
set f [open blackboxes.txt w];puts $f $bb;close $f
if {[llength $bb]} {error "unresolved CSR dependency"}
# Boundary type widths, not an assumption that all stored bits remain live.
set f [open type-widths.tsv w];puts $f "port\tbits"
foreach {n w} {current_physical_thread_id_i 1 csr_thread_id_i 1 retire_thread_id_i 1 current_virtual_context_id_i 2 ctx_npc_write_virtual_context_id_o 2 virtual_context_resident_v_r 4 virtual_context_slot_r 4 virtual_context_npc_r 156 ctx_npc_write_npc_o 39 ctx_l1_cmd_paddr_o 34 csr_r_data_o 64 retained_control_o 4} {
 if {$w==1} {set p [get_ports -quiet $n]} else {set p [get_ports -quiet [format {%s[*]} $n]]}
 if {[llength $p]!=$w} {error "actual CFG width $n expected $w got [llength $p]"}
 puts $f "$n\t[llength $p]"
}
close $f
set f [open clocks.tsv w]
foreach c [get_clocks] {puts $f [join [list $c [get_property PERIOD $c] [get_property WAVEFORM $c]] "\t"]}
close $f
report_utilization -hierarchical -file utilization.rpt
report_timing_summary -report_unconstrained -file timing-summary.rpt
report_timing -max_paths 20 -file timing-paths.rpt
report_control_sets -verbose -file control-sets.rpt
set f [open primitives.tsv w];puts $f "name\tREF_NAME\tIS_PRIMITIVE"
foreach c [lsort [get_cells -hier]] {puts $f [join [list $c [get_property REF_NAME $c] [get_property IS_PRIMITIVE $c]] "\t"]}
close $f
# Do not attribute retimed primitive cost to a preserved cell name. RAM-free
# candidate + surviving FFs is necessary, not a proof of every bit's liveness.
set ram [get_cells -hier -filter {IS_PRIMITIVE == 1 && REF_NAME =~ RAM*}]
set srl [get_cells -hier -filter {IS_PRIMITIVE == 1 && REF_NAME =~ SRL*}]
set ff [get_cells -hier -filter {IS_PRIMITIVE == 1 && REF_NAME =~ FD*}]
set bram [get_cells -hier -filter {IS_PRIMITIVE == 1 && REF_NAME =~ RAMB*}]
set dsp [get_cells -hier -filter {IS_PRIMITIVE == 1 && REF_NAME =~ DSP*}]
if {[llength $bram] || [llength $dsp]} {error "unexpected BRAM/DSP"}
if {$arm eq "ram" && ![llength $ram]} {error "RAM control storage absent; do not force liveness"}
if {$arm eq "registers" && ([llength $ram] || [llength $srl] || ![llength $ff])} {error "register inference not established"}
set f [open realization.tsv w]
puts $f "scope\tREAL CSR BANKS WITH CONTROLLER CUT; NOT WHOLE CPU"
puts $f "arm\t$arm"
puts $f "RAM_primitive_rows\t[llength $ram]"
puts $f "SRL_primitive_rows\t[llength $srl]"
puts $f "FF_primitive_rows\t[llength $ff]"
puts $f "note\tMacro/leaf rows not additive tiles; FF includes actual resident CSR banks"
close $f
write_checkpoint -force synthesized.dcp
write_verilog -mode funcsim functional.v
puts "CSR_REAL_BANK_PRIMARY_MAPPING_COMPLETE $arm"
