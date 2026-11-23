`timescale 1ps/1ps
`include "bp_common_defines.svh"
`include "bp_be_defines.svh"
// No run performed. DUT may be behavioral or the exact fixed-geometry mapped top.
`ifndef CSR_PRIMARY_DUT_MODULE
`define CSR_PRIMARY_DUT_MODULE csr_native_canonical_wrapper
`endif
module csr_primary_miter
 import bp_common_pkg::*;
 import bp_be_pkg::*;
 #(parameter bp_params_e bp_params_p = bsg_blackparrot_pkg::bp_cfg_gp
   , parameter bit retained_buffer_p = 1'b1
   `declare_bp_proc_params(bp_params_p)
   `declare_bp_be_if_widths(vaddr_width_p, paddr_width_p, asid_width_p, branch_metadata_fwd_width_p, fetch_ptr_p, issue_ptr_p)
   , localparam cfg_bus_width_lp = `bp_cfg_bus_width(vaddr_width_p, hio_width_p, core_id_width_p, cce_id_width_p, lce_id_width_p, did_width_p)
   , localparam csr_context_csrs_lp = 26
   , localparam csr_context_width_lp = csr_context_csrs_lp*dword_width_gp + rv64_priv_width_gp
   ) ();
  `declare_bp_be_if(vaddr_width_p,paddr_width_p,asid_width_p,branch_metadata_fwd_width_p,fetch_ptr_p,issue_ptr_p);
  logic clk_i;
  logic reset_i;
  logic [63:0] retained_control_status_i;
  logic [cfg_bus_width_lp-1:0] cfg_bus_i;
  logic csr_r_v_i;
  logic [rv64_csr_addr_width_gp-1:0] csr_r_addr_i;
  logic [retire_pkt_width_lp-1:0] retire_pkt_i;
  logic retire_ctxtsw_v_i;
  rv64_fflags_s fflags_acc_i;
  logic frf_w_v_i;
  logic debug_irq_i;
  logic timer_irq_i;
  logic software_irq_i;
  logic m_external_irq_i;
  logic s_external_irq_i;
  logic [thread_id_width_p-1:0] current_physical_thread_id_i;
  logic [context_id_width_p-1:0] current_virtual_context_id_i;
  logic [thread_id_width_p-1:0] csr_thread_id_i;
  logic [thread_id_width_p-1:0] retire_thread_id_i;
  logic ctx_l1_ready_i;
  logic ctx_l1_resp_v_i;
  logic [dword_width_gp-1:0] ctx_l1_resp_data_i;
  logic icache_replay_ready_i;
  logic [63:0] icache_retention_status_i;
  logic [dword_width_gp-1:0] icache_prefix_status_i;
  logic physical_preview_idle_i;
  logic [dword_width_gp-1:0] dcache_replay_status_i;
  logic context_cache_commit_v_li;
  logic context_cache_launch_v_li;
  logic pending_ctxtsw_sent_r;
  logic pending_rpc_call_v_r;
  logic rpc_entry_valid_r;
  logic [thread_id_width_p-1:0] context_cache_victim_physical_thread_id_r;
  logic [thread_id_width_p-1:0] pending_ctxtsw_prev_physical_thread_id_r;
  logic [thread_id_width_p-1:0] pending_ctxtsw_physical_thread_id_r;
  logic [context_id_width_p-1:0] context_cache_victim_virtual_context_id_r;
  logic [context_id_width_p-1:0] context_cache_target_virtual_context_id_r;
  logic [num_contexts_p-1:0] virtual_context_resident_v_r;
  logic [num_contexts_p-1:0][thread_id_width_p-1:0] virtual_context_slot_r;
  logic [num_contexts_p-1:0][vaddr_width_p-1:0] virtual_context_npc_r;
  logic [vaddr_width_p-1:0] rpc_entry_r;
  typedef struct packed {
    logic retained_control_cmd_v_o;
    logic [3:0] retained_control_o;
    logic [dword_width_gp-1:0] csr_r_data_o;
    logic csr_r_illegal_o;
    logic irq_pending_o;
    logic irq_waiting_o;
    logic [commit_pkt_width_lp-1:0] commit_pkt_o;
    logic [decode_info_width_lp-1:0] decode_info_o;
    logic [trans_info_width_lp-1:0] trans_info_o;
    logic [trans_info_width_lp-1:0] reservation_trans_info_o;
    rv64_frm_e frm_dyn_o;
    logic ctx_npc_write_v_o;
    logic ctx_npc_write_rebind_o;
    logic ctx_npc_write_rpc_entry_o;
    logic [context_id_width_p-1:0] ctx_npc_write_virtual_context_id_o;
    logic [vaddr_width_p-1:0] ctx_npc_write_npc_o;
    logic ctx_rpush_v_o;
    logic ctx_rpush_fp_v_o;
    logic [context_id_width_p-1:0] ctx_rpush_virtual_context_id_o;
    logic [reg_addr_width_gp-1:0] ctx_rpush_reg_o;
    logic [dpath_width_gp-1:0] ctx_rpush_data_o;
    logic ctx_l1_cmd_v_o;
    logic ctx_l1_cmd_w_o;
    logic [paddr_width_p-1:0] ctx_l1_cmd_paddr_o;
    logic [dword_width_gp-1:0] ctx_l1_cmd_data_o;
    logic icache_replay_v_o;
    logic [paddr_width_p-1:0] icache_replay_paddr_o;
    logic icache_retention_cmd_v_o;
    logic [1:0] icache_retention_mode_o;
    logic icache_prefix_entry_v_o;
    logic [7:0] icache_prefix_entry_index_o;
    logic [paddr_width_p-1:0] icache_prefix_entry_paddr_o;
    logic icache_prefix_count_v_o;
    logic [8:0] icache_prefix_count_o;
    logic icache_prefix_trigger_v_o;
    logic icache_prefix_trigger_range_v_o;
    logic [7:0] icache_prefix_trigger_start_o;
    logic [8:0] icache_prefix_trigger_count_o;
    logic icache_prefix_clear_v_o;
    logic physical_preview_v_o;
    logic [paddr_width_p-1:0] physical_preview_paddr_o;
    logic dcache_replay_entry_v_o;
    logic dcache_replay_config_v_o;
    logic dcache_replay_trigger_v_o;
    logic [dword_width_gp-1:0] dcache_replay_payload_o;
  } observed_s;
  observed_s g,d;
  bp_be_retire_pkt_s retirement;
  bp_be_commit_pkt_s gc,dc;
  bp_be_trans_info_s gt,dt;
  assign retire_pkt_i=retirement;
  assign gc=g.commit_pkt_o; assign dc=d.commit_pkt_o;
  assign gt=g.trans_info_o; assign dt=d.trans_info_o;
  csr_primary_gold gold
    (.clk_i(clk_i)
     ,.reset_i(reset_i)
     ,.retained_control_status_i(retained_control_status_i)
     ,.retained_control_cmd_v_o(g.retained_control_cmd_v_o)
     ,.retained_control_o(g.retained_control_o)
     ,.cfg_bus_i(cfg_bus_i)
     ,.csr_r_v_i(csr_r_v_i)
     ,.csr_r_addr_i(csr_r_addr_i)
     ,.csr_r_data_o(g.csr_r_data_o)
     ,.csr_r_illegal_o(g.csr_r_illegal_o)
     ,.retire_pkt_i(retire_pkt_i)
     ,.retire_ctxtsw_v_i(retire_ctxtsw_v_i)
     ,.fflags_acc_i(fflags_acc_i)
     ,.frf_w_v_i(frf_w_v_i)
     ,.debug_irq_i(debug_irq_i)
     ,.timer_irq_i(timer_irq_i)
     ,.software_irq_i(software_irq_i)
     ,.m_external_irq_i(m_external_irq_i)
     ,.s_external_irq_i(s_external_irq_i)
     ,.irq_pending_o(g.irq_pending_o)
     ,.irq_waiting_o(g.irq_waiting_o)
     ,.commit_pkt_o(g.commit_pkt_o)
     ,.decode_info_o(g.decode_info_o)
     ,.trans_info_o(g.trans_info_o)
     ,.reservation_trans_info_o(g.reservation_trans_info_o)
     ,.frm_dyn_o(g.frm_dyn_o)
     ,.current_physical_thread_id_i(current_physical_thread_id_i)
     ,.current_virtual_context_id_i(current_virtual_context_id_i)
     ,.csr_thread_id_i(csr_thread_id_i)
     ,.retire_thread_id_i(retire_thread_id_i)
     ,.ctx_npc_write_v_o(g.ctx_npc_write_v_o)
     ,.ctx_npc_write_rebind_o(g.ctx_npc_write_rebind_o)
     ,.ctx_npc_write_rpc_entry_o(g.ctx_npc_write_rpc_entry_o)
     ,.ctx_npc_write_virtual_context_id_o(g.ctx_npc_write_virtual_context_id_o)
     ,.ctx_npc_write_npc_o(g.ctx_npc_write_npc_o)
     ,.ctx_rpush_v_o(g.ctx_rpush_v_o)
     ,.ctx_rpush_fp_v_o(g.ctx_rpush_fp_v_o)
     ,.ctx_rpush_virtual_context_id_o(g.ctx_rpush_virtual_context_id_o)
     ,.ctx_rpush_reg_o(g.ctx_rpush_reg_o)
     ,.ctx_rpush_data_o(g.ctx_rpush_data_o)
     ,.ctx_l1_ready_i(ctx_l1_ready_i)
     ,.ctx_l1_resp_v_i(ctx_l1_resp_v_i)
     ,.ctx_l1_resp_data_i(ctx_l1_resp_data_i)
     ,.ctx_l1_cmd_v_o(g.ctx_l1_cmd_v_o)
     ,.ctx_l1_cmd_w_o(g.ctx_l1_cmd_w_o)
     ,.ctx_l1_cmd_paddr_o(g.ctx_l1_cmd_paddr_o)
     ,.ctx_l1_cmd_data_o(g.ctx_l1_cmd_data_o)
     ,.icache_replay_ready_i(icache_replay_ready_i)
     ,.icache_replay_v_o(g.icache_replay_v_o)
     ,.icache_replay_paddr_o(g.icache_replay_paddr_o)
     ,.icache_retention_status_i(icache_retention_status_i)
     ,.icache_retention_cmd_v_o(g.icache_retention_cmd_v_o)
     ,.icache_retention_mode_o(g.icache_retention_mode_o)
     ,.icache_prefix_status_i(icache_prefix_status_i)
     ,.icache_prefix_entry_v_o(g.icache_prefix_entry_v_o)
     ,.icache_prefix_entry_index_o(g.icache_prefix_entry_index_o)
     ,.icache_prefix_entry_paddr_o(g.icache_prefix_entry_paddr_o)
     ,.icache_prefix_count_v_o(g.icache_prefix_count_v_o)
     ,.icache_prefix_count_o(g.icache_prefix_count_o)
     ,.icache_prefix_trigger_v_o(g.icache_prefix_trigger_v_o)
     ,.icache_prefix_trigger_range_v_o(g.icache_prefix_trigger_range_v_o)
     ,.icache_prefix_trigger_start_o(g.icache_prefix_trigger_start_o)
     ,.icache_prefix_trigger_count_o(g.icache_prefix_trigger_count_o)
     ,.icache_prefix_clear_v_o(g.icache_prefix_clear_v_o)
     ,.physical_preview_idle_i(physical_preview_idle_i)
     ,.physical_preview_v_o(g.physical_preview_v_o)
     ,.physical_preview_paddr_o(g.physical_preview_paddr_o)
     ,.dcache_replay_status_i(dcache_replay_status_i)
     ,.dcache_replay_entry_v_o(g.dcache_replay_entry_v_o)
     ,.dcache_replay_config_v_o(g.dcache_replay_config_v_o)
     ,.dcache_replay_trigger_v_o(g.dcache_replay_trigger_v_o)
     ,.dcache_replay_payload_o(g.dcache_replay_payload_o)
     ,.context_cache_commit_v_li(context_cache_commit_v_li)
     ,.context_cache_launch_v_li(context_cache_launch_v_li)
     ,.pending_ctxtsw_sent_r(pending_ctxtsw_sent_r)
     ,.pending_rpc_call_v_r(pending_rpc_call_v_r)
     ,.rpc_entry_valid_r(rpc_entry_valid_r)
     ,.context_cache_victim_physical_thread_id_r(context_cache_victim_physical_thread_id_r)
     ,.pending_ctxtsw_prev_physical_thread_id_r(pending_ctxtsw_prev_physical_thread_id_r)
     ,.pending_ctxtsw_physical_thread_id_r(pending_ctxtsw_physical_thread_id_r)
     ,.context_cache_victim_virtual_context_id_r(context_cache_victim_virtual_context_id_r)
     ,.context_cache_target_virtual_context_id_r(context_cache_target_virtual_context_id_r)
     ,.virtual_context_resident_v_r(virtual_context_resident_v_r)
     ,.virtual_context_slot_r(virtual_context_slot_r)
     ,.virtual_context_npc_r(virtual_context_npc_r)
     ,.rpc_entry_r(rpc_entry_r));
  `CSR_PRIMARY_DUT_MODULE dut
    (.clk_i(clk_i)
     ,.reset_i(reset_i)
     ,.retained_control_status_i(retained_control_status_i)
     ,.retained_control_cmd_v_o(d.retained_control_cmd_v_o)
     ,.retained_control_o(d.retained_control_o)
     ,.cfg_bus_i(cfg_bus_i)
     ,.csr_r_v_i(csr_r_v_i)
     ,.csr_r_addr_i(csr_r_addr_i)
     ,.csr_r_data_o(d.csr_r_data_o)
     ,.csr_r_illegal_o(d.csr_r_illegal_o)
     ,.retire_pkt_i(retire_pkt_i)
     ,.retire_ctxtsw_v_i(retire_ctxtsw_v_i)
     ,.fflags_acc_i(fflags_acc_i)
     ,.frf_w_v_i(frf_w_v_i)
     ,.debug_irq_i(debug_irq_i)
     ,.timer_irq_i(timer_irq_i)
     ,.software_irq_i(software_irq_i)
     ,.m_external_irq_i(m_external_irq_i)
     ,.s_external_irq_i(s_external_irq_i)
     ,.irq_pending_o(d.irq_pending_o)
     ,.irq_waiting_o(d.irq_waiting_o)
     ,.commit_pkt_o(d.commit_pkt_o)
     ,.decode_info_o(d.decode_info_o)
     ,.trans_info_o(d.trans_info_o)
     ,.reservation_trans_info_o(d.reservation_trans_info_o)
     ,.frm_dyn_o(d.frm_dyn_o)
     ,.current_physical_thread_id_i(current_physical_thread_id_i)
     ,.current_virtual_context_id_i(current_virtual_context_id_i)
     ,.csr_thread_id_i(csr_thread_id_i)
     ,.retire_thread_id_i(retire_thread_id_i)
     ,.ctx_npc_write_v_o(d.ctx_npc_write_v_o)
     ,.ctx_npc_write_rebind_o(d.ctx_npc_write_rebind_o)
     ,.ctx_npc_write_rpc_entry_o(d.ctx_npc_write_rpc_entry_o)
     ,.ctx_npc_write_virtual_context_id_o(d.ctx_npc_write_virtual_context_id_o)
     ,.ctx_npc_write_npc_o(d.ctx_npc_write_npc_o)
     ,.ctx_rpush_v_o(d.ctx_rpush_v_o)
     ,.ctx_rpush_fp_v_o(d.ctx_rpush_fp_v_o)
     ,.ctx_rpush_virtual_context_id_o(d.ctx_rpush_virtual_context_id_o)
     ,.ctx_rpush_reg_o(d.ctx_rpush_reg_o)
     ,.ctx_rpush_data_o(d.ctx_rpush_data_o)
     ,.ctx_l1_ready_i(ctx_l1_ready_i)
     ,.ctx_l1_resp_v_i(ctx_l1_resp_v_i)
     ,.ctx_l1_resp_data_i(ctx_l1_resp_data_i)
     ,.ctx_l1_cmd_v_o(d.ctx_l1_cmd_v_o)
     ,.ctx_l1_cmd_w_o(d.ctx_l1_cmd_w_o)
     ,.ctx_l1_cmd_paddr_o(d.ctx_l1_cmd_paddr_o)
     ,.ctx_l1_cmd_data_o(d.ctx_l1_cmd_data_o)
     ,.icache_replay_ready_i(icache_replay_ready_i)
     ,.icache_replay_v_o(d.icache_replay_v_o)
     ,.icache_replay_paddr_o(d.icache_replay_paddr_o)
     ,.icache_retention_status_i(icache_retention_status_i)
     ,.icache_retention_cmd_v_o(d.icache_retention_cmd_v_o)
     ,.icache_retention_mode_o(d.icache_retention_mode_o)
     ,.icache_prefix_status_i(icache_prefix_status_i)
     ,.icache_prefix_entry_v_o(d.icache_prefix_entry_v_o)
     ,.icache_prefix_entry_index_o(d.icache_prefix_entry_index_o)
     ,.icache_prefix_entry_paddr_o(d.icache_prefix_entry_paddr_o)
     ,.icache_prefix_count_v_o(d.icache_prefix_count_v_o)
     ,.icache_prefix_count_o(d.icache_prefix_count_o)
     ,.icache_prefix_trigger_v_o(d.icache_prefix_trigger_v_o)
     ,.icache_prefix_trigger_range_v_o(d.icache_prefix_trigger_range_v_o)
     ,.icache_prefix_trigger_start_o(d.icache_prefix_trigger_start_o)
     ,.icache_prefix_trigger_count_o(d.icache_prefix_trigger_count_o)
     ,.icache_prefix_clear_v_o(d.icache_prefix_clear_v_o)
     ,.physical_preview_idle_i(physical_preview_idle_i)
     ,.physical_preview_v_o(d.physical_preview_v_o)
     ,.physical_preview_paddr_o(d.physical_preview_paddr_o)
     ,.dcache_replay_status_i(dcache_replay_status_i)
     ,.dcache_replay_entry_v_o(d.dcache_replay_entry_v_o)
     ,.dcache_replay_config_v_o(d.dcache_replay_config_v_o)
     ,.dcache_replay_trigger_v_o(d.dcache_replay_trigger_v_o)
     ,.dcache_replay_payload_o(d.dcache_replay_payload_o)
     ,.context_cache_commit_v_li(context_cache_commit_v_li)
     ,.context_cache_launch_v_li(context_cache_launch_v_li)
     ,.pending_ctxtsw_sent_r(pending_ctxtsw_sent_r)
     ,.pending_rpc_call_v_r(pending_rpc_call_v_r)
     ,.rpc_entry_valid_r(rpc_entry_valid_r)
     ,.context_cache_victim_physical_thread_id_r(context_cache_victim_physical_thread_id_r)
     ,.pending_ctxtsw_prev_physical_thread_id_r(pending_ctxtsw_prev_physical_thread_id_r)
     ,.pending_ctxtsw_physical_thread_id_r(pending_ctxtsw_physical_thread_id_r)
     ,.context_cache_victim_virtual_context_id_r(context_cache_victim_virtual_context_id_r)
     ,.context_cache_target_virtual_context_id_r(context_cache_target_virtual_context_id_r)
     ,.virtual_context_resident_v_r(virtual_context_resident_v_r)
     ,.virtual_context_slot_r(virtual_context_slot_r)
     ,.virtual_context_npc_r(virtual_context_npc_r)
     ,.rpc_entry_r(rpc_entry_r));

  always #25000 clk_i=~clk_i;
  int cycles=0,comparisons=0,reads=0,saves=0,loads=0;
  int negative=0;
  bit reset_seen=0,negative_armed=0;
  task automatic compare_outputs;
    observed_s observed;
    bit injected;
    observed=d; injected=0;
    if (reset_seen && !reset_i) begin
      if (gc.ctxtsw && g.ctx_npc_write_v_o) $fatal(1,"OLD decoder save/seed overlap");
      if (dc.ctxtsw && d.ctx_npc_write_v_o) $fatal(1,"DUT decoder save/seed overlap");
      if (negative && negative_armed && csr_r_v_i && csr_r_addr_i==12'h341) begin
        // Actual externally observed MEPC bit2, not an internal raw image bit.
        observed.csr_r_data_o[2]=~observed.csr_r_data_o[2]; injected=1;
      end
      comparisons++;
      if (observed !== g) begin
        if (injected && d===g && g.csr_r_data_o===64'h1200) begin
          $display("CSR_PRIMARY_NEGATIVE_DETECTED interface=mepc bit=2 cycles=%0d checks=%0d",cycles,comparisons);
          $finish;
        end
        $fatal(1,"CSR_PRIMARY_MISMATCH cycle=%0d read=%h gold=%h dut=%h",cycles,csr_r_addr_i,g.csr_r_data_o,d.csr_r_data_o);
      end
    end
  endtask
  task automatic step;
    #1; compare_outputs();
    @(posedge clk_i); #1; compare_outputs();
    @(negedge clk_i); #1; cycles++;
  endtask
  task automatic clear_op;
    retirement='0;retire_ctxtsw_v_i=0;csr_r_v_i=0;
    context_cache_commit_v_li=0;context_cache_launch_v_li=0;
    pending_ctxtsw_sent_r=0;pending_rpc_call_v_r=0;
  endtask
  task automatic actor(input int bank,input int context_id);
    current_physical_thread_id_i=thread_id_width_p'(bank);
    current_virtual_context_id_i=context_id_width_p'(context_id);
    retire_thread_id_i=thread_id_width_p'(bank);csr_thread_id_i=thread_id_width_p'(bank);
    pending_ctxtsw_prev_physical_thread_id_r=thread_id_width_p'(bank);
  endtask
  task automatic wr(input int bank,input logic[11:0] addr,input logic[63:0] value);
    clear_op();actor(bank,bank); retirement.v=1;retirement.queue_v=1;retirement.instret=1;
    retirement.special.csrw=1;retirement.data=value;
    retirement.instr=rv64_instr_s'((32'(addr)<<20)|32'h00001073);step();clear_op();
  endtask
  task automatic rd(input int bank,input logic[11:0] addr);
    clear_op();csr_thread_id_i=thread_id_width_p'(bank);csr_r_addr_i=addr;csr_r_v_i=1;
    step();reads++;
  endtask
  task automatic expect_read(input int bank,input logic[11:0] addr,input logic[63:0] value);
    rd(bank,addr);
    if (g.csr_r_illegal_o || d.csr_r_illegal_o || g.csr_r_data_o!==value || d.csr_r_data_o!==value)
      $fatal(1,"architectural read bank%0d CSR%h expected%h gold%h dut%h",bank,addr,value,g.csr_r_data_o,d.csr_r_data_o);
    clear_op();
  endtask
  task automatic save(input int bank,input int context_id);
    clear_op();actor(bank,context_id);context_cache_commit_v_li=1;
    context_cache_victim_physical_thread_id_r=thread_id_width_p'(bank);
    context_cache_victim_virtual_context_id_r=context_id_width_p'(context_id);
    retirement.v=1;retirement.instret=1;retire_ctxtsw_v_i=1;step();saves++;clear_op();
  endtask
  task automatic reload(input int context_id,input int bank);
    clear_op();context_cache_target_virtual_context_id_r=context_id_width_p'(context_id);
    context_cache_victim_physical_thread_id_r=thread_id_width_p'(bank);
    context_cache_launch_v_li=1;step();loads++;clear_op();actor(bank,context_id);
  endtask
  task automatic seed(input int context_id,input bit rebind);
    logic[63:0] value;value=(64'(rebind)<<63)|(64'(context_id)<<vaddr_width_p)|64'h4000;
    wr(0,12'h801,value);
  endtask
  initial begin
    clk_i='0;
    reset_i='0;
    retained_control_status_i='0;
    cfg_bus_i='0;
    csr_r_v_i='0;
    csr_r_addr_i='0;
    retire_ctxtsw_v_i='0;
    fflags_acc_i='0;
    frf_w_v_i='0;
    debug_irq_i='0;
    timer_irq_i='0;
    software_irq_i='0;
    m_external_irq_i='0;
    s_external_irq_i='0;
    current_physical_thread_id_i='0;
    current_virtual_context_id_i='0;
    csr_thread_id_i='0;
    retire_thread_id_i='0;
    ctx_l1_ready_i='0;
    ctx_l1_resp_v_i='0;
    ctx_l1_resp_data_i='0;
    icache_replay_ready_i='0;
    icache_retention_status_i='0;
    icache_prefix_status_i='0;
    physical_preview_idle_i='0;
    dcache_replay_status_i='0;
    context_cache_commit_v_li='0;
    context_cache_launch_v_li='0;
    pending_ctxtsw_sent_r='0;
    pending_rpc_call_v_r='0;
    rpc_entry_valid_r='0;
    context_cache_victim_physical_thread_id_r='0;
    pending_ctxtsw_prev_physical_thread_id_r='0;
    pending_ctxtsw_physical_thread_id_r='0;
    context_cache_victim_virtual_context_id_r='0;
    context_cache_target_virtual_context_id_r='0;
    virtual_context_resident_v_r='0;
    virtual_context_slot_r='0;
    virtual_context_npc_r='0;
    rpc_entry_r='0;
    retirement='0; reset_i=1;
    if (num_threads_p!=2 || num_contexts_p!=4 || csr_context_width_lp!=1666) $fatal(1,"actual profile");
    if ($value$plusargs("NEGATIVE=%d",negative)) begin end
    repeat(3) step(); reset_seen=1;reset_i=0;step();
    // Invalid inactive image must select architectural reset, never raw RAM bits.
    reload(3,1);expect_read(1,12'h341,0);
    for (int b=0;b<2;b++) begin
      wr(b,12'h320,5);wr(b,12'h341,64'h2000+64'(b)*256);
      expect_read(b,12'h341,64'h2000+64'(b)*256);
    end
    // Reservation reads are independent of current and retire owners.
    actor(0,0);expect_read(1,12'h341,64'h2100);expect_read(0,12'h341,64'h2000);
    for (int c=0;c<4;c++) begin
      wr(c%2,12'h341,64'h1000+64'(c)*256);
      wr(c%2,12'h340,64'h10000000+64'(c)*17);save(c%2,c);
    end
    for (int c=0;c<4;c++) begin
      reload(c,(c+1)%2);expect_read((c+1)%2,12'h341,64'h1000+64'(c)*256);
      expect_read((c+1)%2,12'h340,64'h10000000+64'(c)*17);
    end
    // Observable architectural negative is armed only after actual context reload.
    reload(2,0);negative_armed=1;expect_read(0,12'h341,64'h1200);negative_armed=0;
    if (negative) $fatal(1,"negative oracle not detected");
    // Attempted but unretired switch/801 overlap writes neither snapshot.
    actor(0,0);retirement='0;retirement.v=1;retirement.special.csrw=1;
    retirement.instr=rv64_instr_s'(32'h80101073);retirement.data=64'h8000000000009000;
    retire_ctxtsw_v_i=1;step();clear_op();reload(0,1);expect_read(1,12'h341,64'h1000);
    // Decoder-overlap adversary: actual T masks CSR write, no seeded context.
    actor(0,0);context_cache_commit_v_li=1;context_cache_victim_virtual_context_id_r=0;
    context_cache_victim_physical_thread_id_r=0;retirement='0;retirement.instret=1;
    retirement.special.csrw=1;retirement.instr=rv64_instr_s'(32'h80101073);
    retirement.data=64'h8000010000004000;retire_ctxtsw_v_i=1;step();clear_op();
    // Existing ordinary NPC reseed preserves the private CSR image.
    seed(2,0);reload(2,1);expect_read(1,12'h341,64'h1200);
    wr(0,12'h341,64'h8000);seed(2,1);reload(2,1);expect_read(1,12'h341,64'h8000);
    // Resident rebind clones caller; self seed does not restore over live retirement.
    virtual_context_resident_v_r=4'b0011;virtual_context_slot_r[0]=0;virtual_context_slot_r[1]=1;
    wr(0,12'h341,64'h9000);seed(1,1);expect_read(1,12'h341,64'h9000);
    wr(1,12'h341,64'ha000);seed(1,0);expect_read(1,12'h341,64'ha000);
    seed(0,1);expect_read(0,12'h341,64'h9000);
    reload(1,1);expect_read(1,12'h341,64'h9000);
    // Descriptor install and protected-call APC update at the real interfaces.
    wr(0,12'h801,(64'h1<<62)|(64'h1<<vaddr_width_p)|64'h4800);
    rpc_entry_valid_r=1;rpc_entry_r=vaddr_width_p'(64'h4800);actor(0,0);
    context_cache_commit_v_li=1;context_cache_victim_virtual_context_id_r=0;
    context_cache_victim_physical_thread_id_r=0;pending_rpc_call_v_r=1;
    pending_ctxtsw_physical_thread_id_r=1;retirement='0;retirement.v=1;
    retirement.instret=1;retire_ctxtsw_v_i=1;step();clear_op();
    expect_read(1,12'h341,64'h9000);rpc_entry_valid_r=0;
    // CSR WARL/truncation travels through real CSR write and restore consumers.
    wr(0,12'h305,64'hffffffffffffffff);wr(0,12'h180,64'hffffffffffffffff);
    save(0,2);reload(2,1);rd(1,12'h305);rd(1,12'h180);clear_op();
    timer_irq_i=1;software_irq_i=1;m_external_irq_i=1;s_external_irq_i=1;step();
    rd(0,12'h344);rd(1,12'h344);
    if (!g.csr_r_data_o[7] || !g.csr_r_data_o[3] || !g.csr_r_data_o[11]) $fatal(1,"broadcast IRQ bits");clear_op();
    timer_irq_i=0;software_irq_i=0;m_external_irq_i=0;s_external_irq_i=0;step();
    // Retire owner can differ from current owner; write must affect only bank1.
    wr(0,12'h341,64'hb000);wr(1,12'h341,64'hc000);
    actor(0,0);retire_thread_id_i=1;retirement='0;retirement.v=1;retirement.instret=1;
    retirement.special.csrw=1;retirement.instr=rv64_instr_s'(32'h34101073);retirement.data=64'hd000;
    step();clear_op();expect_read(0,12'h341,64'hb000);expect_read(1,12'h341,64'hd000);
    // Genuine MRET enters S; saved privilege/translation image reloads into other bank.
    wr(0,12'h300,64'h800);actor(0,0);retirement='0;retirement.v=1;retirement.instret=1;
    retirement.special.mret=1;retirement.instr=rv64_instr_s'(32'h30200073);step();clear_op();
    if (gt.priv_mode!=1 || dt.priv_mode!=1) $fatal(1,"MRET S transition");
    save(0,3);reload(3,1);step();if(gt.priv_mode!=1 || dt.priv_mode!=1) $fatal(1,"S restore");
    retirement='0;retirement.v=1;retirement.exception.ecall_s=1;step();clear_op();
    if (gt.priv_mode!=3 || dt.priv_mode!=3) $fatal(1,"S ECALL M transition");
    // Fresh production-bound sweep. Every image is generated by the REAL
    // CSR banks, never by arbitrary raw1666-bit test inputs or a model codec.
    reset_i=1;repeat(2)step();reset_i=0;step();
    for (int bank=0;bank<2;bank++) begin
      for (int field_index=0;field_index<26;field_index++) begin
        logic [11:0] field_addr;
        case(field_index)
          0:field_addr=12'h7b0; 1:field_addr=12'h7b1;
          2:field_addr=12'h7b2; 3:field_addr=12'h7b3;
          4:field_addr=12'h300; 5:field_addr=12'h302;
          6:field_addr=12'h303; 7:field_addr=12'h304;
          8:field_addr=12'h305; 9:field_addr=12'h306;
          10:field_addr=12'h340;11:field_addr=12'h341;
          12:field_addr=12'h342;13:field_addr=12'h343;
          14:field_addr=12'h344;15:field_addr=12'hb00;
          16:field_addr=12'hb02;17:field_addr=12'h320;
          18:field_addr=12'h105;19:field_addr=12'h106;
          20:field_addr=12'h140;21:field_addr=12'h141;
          22:field_addr=12'h142;23:field_addr=12'h143;
          24:field_addr=12'h180;default:field_addr=12'h003;
        endcase
        for (int bit_index=0;bit_index<64;bit_index++) begin
          for (int context_id=0;context_id<4;context_id++) begin
            wr(bank,field_addr,64'(1)<<bit_index);
            save(bank,context_id);
            reload(context_id,1-bank);
            rd(1-bank,field_addr);clear_op();
          end
        end
      end
    end
    $display("CSR_CANONICAL_REAL_PRODUCER_SWEEP_PASS banks=2 contexts=4 fields=26 inputbits=64 writes=13312");
    // Midstream reset invalidates all images, including a previously populated target.
    reset_i=1;repeat(2)step();reset_i=0;step();reload(2,0);expect_read(0,12'h341,0);
    $display("CSR_PRIMARY_EQUIVALENCE_PASS checks=%0d cycles=%0d reads=%0d saves=%0d reloads=%0d",comparisons,cycles,reads,saves,loads);
    $finish;
  end
  initial begin #(64'd10000000000); $fatal(1,"fixed HDL watchdog"); end
endmodule
