# Same exact original synthesis recipe; append read-only mapped queries only.
set original {/home/coyang/zynq-parrot-linux-host-observer/research/csr-native-bank-register-preparation-20261122/probe-primary.tcl}
source $original
# The sourced script validates one arm, all7defines/actual CFG, actual2workers,
# part/options/clock, key type widths, no blackboxes and storage realization.
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
