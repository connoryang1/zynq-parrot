# SOURCE-ONLY recipe. ROOT admission/owned worker is required before use.
if {[llength $argv]!=1 || [lsearch -exact {raw canonical} [lindex $argv 0]]<0} {error "one fixed primary arm"}
set arm [lindex $argv 0]
set base [file dirname [file normalize [info script]]]
source [file join $base sources.tcl]

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
set f [open source-context.tsv a]
puts $f "read_verilog\t/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_production.sv"
read_verilog -sv {/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_production.sv}
if {$arm eq "raw"} {
 set top csr_native_consumer_wrapper
 puts $f "read_verilog\t/home/coyang/zynq-parrot-linux-host-observer/research/csr-native-bank-register-preparation-20261122/csr_native_consumer_wrapper.sv"
 read_verilog -sv {/home/coyang/zynq-parrot-linux-host-observer/research/csr-native-bank-register-preparation-20261122/csr_native_consumer_wrapper.sv}
} else {
 set top csr_native_canonical_wrapper
 puts $f "read_verilog\t/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_canonical.sv"
 puts $f "read_verilog\t/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr-canonical-snapshot-component-preparation-20261123/csr_native_canonical_wrapper.sv"
 read_verilog -sv {/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_canonical.sv}
 read_verilog -sv {/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr-canonical-snapshot-component-preparation-20261123/csr_native_canonical_wrapper.sv}
}
close $f
read_xdc [file join $base clock.xdc]
# Both arms identical; OOC/2 workers differ explicitly from whole-device/8.
synth_design -top $top -part xc7z020clg400-1 -mode out_of_context -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1
# Preserve completed tool state before any parser/report/property inspection.
write_checkpoint -force synthesized.dcp
write_verilog -mode funcsim functional.v
set f [open snapshot-shape.tsv w];puts $f "cell\tREF_NAME\tORIG_REF_NAME"
set snapshot_cells [get_cells -quiet -hier -filter {NAME =~ *csr_snapshot_store* || NAME =~ *encoded_store*}]
foreach c [lsort $snapshot_cells] {
 set orig {};if {[lsearch -exact [list_property $c] ORIG_REF_NAME]>=0} {set orig [get_property ORIG_REF_NAME $c]}
 puts $f [join [list $c [get_property REF_NAME $c] $orig] "\t"]
}
close $f
# The source-identical behavioral run measured1666/741/4 four times.
# Rebuilt/retimed module names are recorded only; surviving RAM bit liveness is
# not inferred from a mangled module name or a requested source dimension.
puts "CANONICAL_SOURCE_CONTRACT expanded=1666 encoded=741 contexts=4; actual primitives recorded separately"

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
if {![llength $ram]} {error "RAM control storage absent; do not force liveness"}
set f [open realization.tsv w]
puts $f "scope\tREAL CSR BANKS WITH CONTROLLER CUT; NOT WHOLE CPU"
puts $f "arm\t$arm"
puts $f "RAM_primitive_rows\t[llength $ram]"
puts $f "SRL_primitive_rows\t[llength $srl]"
puts $f "FF_primitive_rows\t[llength $ff]"
puts $f "note\tMacro/leaf rows not additive tiles; FF includes actual resident CSR banks"
close $f
puts "CSR_CANONICAL_PRIMARY_MAPPING_COMPLETE $arm"

set expected [dict create]
foreach pair [list {clk_i IN} {reset_i IN} {retained_control_status_i IN} {retained_control_cmd_v_o OUT} {retained_control_o OUT} {cfg_bus_i IN} {csr_r_v_i IN} {csr_r_addr_i IN} {csr_r_data_o OUT} {csr_r_illegal_o OUT} {retire_pkt_i IN} {retire_ctxtsw_v_i IN} {fflags_acc_i IN} {frf_w_v_i IN} {debug_irq_i IN} {timer_irq_i IN} {software_irq_i IN} {m_external_irq_i IN} {s_external_irq_i IN} {irq_pending_o OUT} {irq_waiting_o OUT} {commit_pkt_o OUT} {decode_info_o OUT} {trans_info_o OUT} {reservation_trans_info_o OUT} {frm_dyn_o OUT} {current_physical_thread_id_i IN} {current_virtual_context_id_i IN} {csr_thread_id_i IN} {retire_thread_id_i IN} {ctx_npc_write_v_o OUT} {ctx_npc_write_rebind_o OUT} {ctx_npc_write_rpc_entry_o OUT} {ctx_npc_write_virtual_context_id_o OUT} {ctx_npc_write_npc_o OUT} {ctx_rpush_v_o OUT} {ctx_rpush_fp_v_o OUT} {ctx_rpush_virtual_context_id_o OUT} {ctx_rpush_reg_o OUT} {ctx_rpush_data_o OUT} {ctx_l1_ready_i IN} {ctx_l1_resp_v_i IN} {ctx_l1_resp_data_i IN} {ctx_l1_cmd_v_o OUT} {ctx_l1_cmd_w_o OUT} {ctx_l1_cmd_paddr_o OUT} {ctx_l1_cmd_data_o OUT} {icache_replay_ready_i IN} {icache_replay_v_o OUT} {icache_replay_paddr_o OUT} {icache_retention_status_i IN} {icache_retention_cmd_v_o OUT} {icache_retention_mode_o OUT} {icache_prefix_status_i IN} {icache_prefix_entry_v_o OUT} {icache_prefix_entry_index_o OUT} {icache_prefix_entry_paddr_o OUT} {icache_prefix_count_v_o OUT} {icache_prefix_count_o OUT} {icache_prefix_trigger_v_o OUT} {icache_prefix_trigger_range_v_o OUT} {icache_prefix_trigger_start_o OUT} {icache_prefix_trigger_count_o OUT} {icache_prefix_clear_v_o OUT} {physical_preview_idle_i IN} {physical_preview_v_o OUT} {physical_preview_paddr_o OUT} {dcache_replay_status_i IN} {dcache_replay_entry_v_o OUT} {dcache_replay_config_v_o OUT} {dcache_replay_trigger_v_o OUT} {dcache_replay_payload_o OUT} {context_cache_commit_v_li IN} {context_cache_launch_v_li IN} {pending_ctxtsw_sent_r IN} {pending_rpc_call_v_r IN} {rpc_entry_valid_r IN} {context_cache_victim_physical_thread_id_r IN} {pending_ctxtsw_prev_physical_thread_id_r IN} {pending_ctxtsw_physical_thread_id_r IN} {context_cache_victim_virtual_context_id_r IN} {context_cache_target_virtual_context_id_r IN} {virtual_context_resident_v_r IN} {virtual_context_slot_r IN} {virtual_context_npc_r IN} {rpc_entry_r IN}] {dict set expected [lindex $pair 0] [lindex $pair 1]}
if {[dict size $expected]!=86} {error "fixed logical interface"}
set grouped [dict create]
set f [open mapped-bit-ports.tsv w];puts $f "name\tlogical\tdirection"
foreach p [lsort [get_ports]] {
 set name [get_property NAME $p]
 set bracket [string first {[} $name]
 set logical [expr {$bracket<0 ? $name : [string range $name 0 [expr {$bracket-1}]]}]
 set direction [get_property DIRECTION $p]
 if {![dict exists $expected $logical] || $direction ne [dict get $expected $logical]} {error "unexpected mapped port $name $direction"}
 dict lappend grouped $logical $name
 puts $f [join [list $name $logical $direction] "\t"]
}
close $f
if {[dict size $grouped]!=86} {error "missing mapped logical port"}
set f [open mapped-logical-ports.tsv w];puts $f "logical\tdirection\tbits"
foreach logical [lsort [dict keys $expected]] {
 if {![dict exists $grouped $logical] || ![llength [dict get $grouped $logical]]} {error "empty mapped port $logical"}
 puts $f [join [list $logical [dict get $expected $logical] [llength [dict get $grouped $logical]]] "\t"]
}
close $f
# Configuration once per actual used primitive kind; full connections/INIT remain
# in the saved netlist and DCP. No keep, forcing liveness or net modifications.
set f [open used-primitive-properties.tsv w]
puts $f "REF_NAME\trepresentative\tproperty\tvalue"
set seen [dict create]
foreach c [lsort [get_cells -hier -filter {IS_PRIMITIVE == 1}]] {
 set ref [get_property REF_NAME $c]
 if {[dict exists $seen $ref]} {continue}
 dict set seen $ref $c
 foreach property [lsort [list_property $c]] {
  set value [string map [list "\t" {\t} "\n" {\n}] [get_property $property $c]]
  puts $f [join [list $ref $c $property $value] "\t"]
 }
}
close $f
puts "CSR_PRIMARY_PORT_INVENTORY_COMPLETE arm=$arm logical_ports=86 bit_ports=[llength [get_ports]]"
