// Component proof of the global retention command's retirement-bank routing
// and existing decoder privilege semantics; not a complete processor test.
`include "bp_common_defines.svh"
`include "bp_be_defines.svh"
module retention_csr_tb
 import bp_common_pkg::*;
 import bp_be_pkg::*;
 #(parameter bp_params_e bp_params_p = e_bp_custom_cfg
   `declare_bp_proc_params(bp_params_p)
   `declare_bp_be_if_widths(vaddr_width_p,paddr_width_p,asid_width_p,branch_metadata_fwd_width_p,fetch_ptr_p,issue_ptr_p)
   )
 (input clk_i, reset_i,
  input current_thread_i, read_thread_i, retire_thread_i,
  input write_i, instret_i, ctxtsw_i,
  input [11:0] csr_addr_i,
  input [63:0] payload_i,
  input restore_i,
  input [1:0] restore_priv_i,
  input decode_write_i,
  output [63:0] read_data_o,
  output illegal_o, command_o,
  output [1:0] mode_o);
 `declare_bp_be_if(vaddr_width_p,paddr_width_p,asid_width_p,branch_metadata_fwd_width_p,fetch_ptr_p,issue_ptr_p);
 localparam restore_width_lp = 26*64+rv64_priv_width_gp;
 bp_be_retire_pkt_s retire_pkt;
 bp_be_decode_info_s decode_info;
 bp_be_preissue_pkt_s preissue;
 logic [restore_width_lp-1:0] restore_data;
 logic [63:0] status_r;
 always_comb begin
   retire_pkt = '0;
   retire_pkt.special.csrw = write_i;
   retire_pkt.instret = instret_i;
   retire_pkt.instr = {csr_addr_i,5'd1,3'b001,5'd1,7'b1110011};
   retire_pkt.data = payload_i;
   restore_data = '0;
   restore_data[0+:rv64_priv_width_gp] = restore_priv_i;
   preissue = '0;
   preissue.instr = {csr_addr_i,5'(decode_write_i),
                     decode_write_i ? 3'b001 : 3'b010,5'd1,7'b1110011};
 end
 // Stand-in for the cache-owned state. Every CSR bank observes this one value.
 always_ff @(posedge clk_i)
   if (reset_i) status_r <= 64'h8000000000000000;
   else if (command_o) status_r <= 64'h8000000000000000 | 64'(mode_o);
 bp_be_csr_wrapper_mt #(.bp_params_p(bp_params_p)) dut
  (.clk_i(clk_i),.reset_i(reset_i),.cfg_bus_i('0)
   ,.csr_r_v_i(1'b1),.csr_r_addr_i(csr_addr_i),.csr_r_data_o(read_data_o),.csr_r_illegal_o()
   ,.retire_pkt_i(retire_pkt),.retire_ctxtsw_v_i(ctxtsw_i),.fflags_acc_i('0),.frf_w_v_i(1'b0)
   ,.debug_irq_i(1'b0),.timer_irq_i(1'b0),.software_irq_i(1'b0)
   ,.m_external_irq_i(1'b0),.s_external_irq_i(1'b0),.decode_info_o(decode_info)
   ,.current_physical_thread_id_i(current_thread_i),.current_virtual_context_id_i('0)
   ,.legacy_context_user_enable_i(1'b0),.csr_thread_id_i(read_thread_i),.retire_thread_id_i(retire_thread_i)
   ,.csr_context_restore_v_i(restore_i),.csr_context_apc_write_v_i(1'b0),.csr_context_restore_reset_i(1'b0)
   ,.csr_context_restore_physical_thread_id_i(retire_thread_i),.csr_context_restore_data_i(restore_data)
   ,.csr_context_restore_npc_i('0),.csr_context_save_physical_thread_id_i(current_thread_i)
   ,.ctx_l1_ready_i(1'b0),.ctx_l1_resp_v_i(1'b0),.ctx_l1_resp_data_i('0)
   ,.miss_trace_status_i('0),.miss_trace_data_i('0),.icache_replay_ready_i(1'b0)
   ,.icache_retention_status_i(status_r),.icache_retention_cmd_v_o(command_o),.icache_retention_mode_o(mode_o)
   ,.icache_prefix_status_i('0),.physical_preview_idle_i(1'b0),.dcache_replay_status_i('0));
 bp_be_instr_decoder #(.bp_params_p(bp_params_p)) decoder
  (.preissue_pkt_i(preissue),.decode_info_i(decode_info),.illegal_instr_o(illegal_o));
endmodule
