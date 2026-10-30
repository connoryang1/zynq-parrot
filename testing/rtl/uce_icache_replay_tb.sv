// Directed wrapper for the physical full-line I-cache replay path.
`include "bp_common_defines.svh"
`include "bp_me_defines.svh"
module uce_icache_replay_tb
  import bp_common_pkg::*;
  import bp_me_pkg::*;
  #(parameter bp_params_e bp_params_p = e_bp_unicore_cfg
    , parameter bit side_buffer_p = 1'b0
    `declare_bp_proc_params(bp_params_p)
    )
  (input clk_i, reset_i,
   input replay_v_i,
   input [63:0] replay_addr_i,
   output replay_ready_o,
   input req_v_i,
   input [3:0] req_type_i,
   input [63:0] req_addr_i,
   input metadata_v_i,
   input [2:0] metadata_way_i,
   input [2:0] tag_state_i,
   input [63:0] tag_value_i,
   input arrays_accept_i,
   output req_yumi_o, req_lock_o, critical_o, last_o,
   output credits_full_o, credits_empty_o,
   output [3:0] req_id_o,
   output tag_v_o, data_v_o, stat_v_o,
   output [2:0] tag_opcode_o,
   output [1:0] data_opcode_o, stat_opcode_o,
   output [3:0] data_fill_o,
   output [63:0] data_word0_o, data_word1_o,
   output [3:0] install_state_o,
   output [3:0] replay_valid_o, replay_sent_o, replay_complete_o, replay_cancel_o,
   output fwd_v_o,
   input fwd_ready_i,
   output [3:0] fwd_type_o,
   output [2:0] fwd_size_o,
   output [63:0] fwd_addr_o,
   output [7:0] fwd_way_o,
   output [2:0] fwd_state_o,
   output fwd_prefetch_o,
   input rev_v_i,
   output rev_ready_o,
   input [3:0] rev_type_i,
   input [2:0] rev_size_i,
   input [63:0] rev_addr_i,
   input [7:0] rev_way_i,
   input [2:0] rev_state_i,
   input rev_prefetch_i,
   input [63:0] rev_word0_i, rev_word1_i
   );

  localparam assoc_lp = dcache_assoc_p;
  localparam sets_lp = 4;
  localparam block_lp = dcache_block_width_p;
  localparam fill_lp = dcache_fill_width_p;
  localparam tag_lp = paddr_width_p-$clog2(sets_lp)-$clog2(block_lp/8);
  localparam id_lp = 4;
  `declare_bp_cache_engine_generic_if(paddr_width_p, tag_lp, sets_lp, assoc_lp,
                                      dcache_data_width_p, block_lp, fill_lp, id_lp, cache);
  `declare_bp_bedrock_if(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p);

  bp_cache_req_s req;
  bp_cache_req_metadata_s metadata;
  bp_cache_tag_mem_pkt_s tag_pkt;
  bp_cache_tag_info_s tag_info;
  bp_cache_data_mem_pkt_s data_pkt;
  bp_cache_stat_mem_pkt_s stat_pkt;
  bp_bedrock_mem_fwd_header_s fwd;
  logic [bedrock_fill_width_p-1:0] fwd_data;
  bp_bedrock_mem_rev_header_s rev;

  always_comb begin
    req = '0;
    req.msg_type = bp_cache_req_msg_type_e'(req_type_i);
    req.addr = paddr_width_p'(req_addr_i);
    req.size = e_size_64B;
    req.id = 4'h9;
    metadata = '0;
    metadata.hit_or_repl_way = metadata_way_i;
    tag_info = '0;
    tag_info.state = bp_coh_states_e'(tag_state_i);
    tag_info.tag = tag_lp'(tag_value_i);
    rev = '0;
    rev.msg_type = bp_bedrock_msg_u'(rev_type_i);
    rev.size = bp_bedrock_msg_size_e'(rev_size_i);
    rev.addr = paddr_width_p'(rev_addr_i);
    rev.payload.way_id = $bits(rev.payload.way_id)'(rev_way_i);
    rev.payload.state = bp_coh_states_e'(rev_state_i);
    rev.payload.prefetch = rev_prefetch_i;
  end

  assign tag_opcode_o = tag_pkt.opcode;
  assign data_opcode_o = data_pkt.opcode;
  assign stat_opcode_o = stat_pkt.opcode;
  assign data_fill_o = data_pkt.fill_index;
  assign data_word0_o = data_pkt.data[0+:64];
  assign data_word1_o = data_pkt.data[64+:64];
  assign fwd_type_o = fwd.msg_type;
  assign fwd_size_o = fwd.size;
  assign fwd_addr_o = 64'(fwd.addr);
  assign fwd_way_o = 8'(fwd.payload.way_id);
  assign fwd_state_o = fwd.payload.state;
  assign fwd_prefetch_o = fwd.payload.prefetch;

  bp_uce #(.bp_params_p(bp_params_p), .writeback_p(0), .assoc_p(assoc_lp),
           .prefetch_p(1), .prefetch_els_p(4), .prefetch_full_line_p(1),
           .prefetch_demand_priority_p(1), .prefetch_critical_forward_p(0),
           .prefetch_side_buffer_p(side_buffer_p),
           .sets_p(sets_lp), .block_width_p(block_lp), .fill_width_p(fill_lp),
           .data_width_p(dcache_data_width_p), .tag_width_p(tag_lp), .id_width_p(id_lp))
    dut (.clk_i(clk_i), .reset_i(reset_i), .did_i('0), .lce_id_i('0),
         .cache_req_i(req), .cache_req_v_i(req_v_i), .cache_req_yumi_o(req_yumi_o),
         .cache_req_lock_o(req_lock_o), .cache_req_metadata_i(metadata),
         .cache_req_metadata_v_i(metadata_v_i), .cache_req_id_o(req_id_o),
         .cache_req_critical_o(critical_o), .cache_req_last_o(last_o),
         .cache_req_credits_full_o(credits_full_o), .cache_req_credits_empty_o(credits_empty_o),
         .detached_prefetch_addr_i(paddr_width_p'(replay_addr_i)),
         .detached_prefetch_v_i(replay_v_i),
         .detached_prefetch_ready_and_o(replay_ready_o),
         .tag_mem_pkt_o(tag_pkt), .tag_mem_pkt_v_o(tag_v_o),
         .tag_mem_pkt_yumi_i(tag_v_o & arrays_accept_i), .tag_mem_i(tag_info),
         .data_mem_pkt_o(data_pkt), .data_mem_pkt_v_o(data_v_o),
         .data_mem_pkt_yumi_i(data_v_o & arrays_accept_i), .data_mem_i('0),
         .stat_mem_pkt_o(stat_pkt), .stat_mem_pkt_v_o(stat_v_o),
         .stat_mem_pkt_yumi_i(stat_v_o & arrays_accept_i), .stat_mem_i('0),
         .mem_fwd_header_o(fwd), .mem_fwd_data_o(fwd_data), .mem_fwd_v_o(fwd_v_o),
         .mem_fwd_ready_and_i(fwd_ready_i), .mem_rev_header_i(rev),
         .mem_rev_data_i({rev_word1_i, rev_word0_i}), .mem_rev_v_i(rev_v_i),
         .mem_rev_ready_and_o(rev_ready_o));

  assign install_state_o = dut.prefetch_install_state_r;
  assign replay_valid_o = dut.prefetch_valid_r;
  assign replay_sent_o = dut.prefetch_sent_r;
  assign replay_complete_o = dut.prefetch_complete_r;
  assign replay_cancel_o = dut.prefetch_cancel_r;

  initial assert (block_lp == 512 && fill_lp == 128 && bedrock_fill_width_p == 128
                  && assoc_lp == 8)
    else $fatal(1, "standalone endpoint requires 512-bit lines and 128-bit fills");
endmodule
