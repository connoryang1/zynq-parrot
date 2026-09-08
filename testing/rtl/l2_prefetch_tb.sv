// Scalar endpoints for the real two-bank L2 controller and its stream pumps.
// The C++ driver supplies ordered cache-bank responses with controlled stalls.
`include "bp_common_defines.svh"
`include "bp_me_defines.svh"
`include "bsg_cache.svh"
module l2_prefetch_tb
  import bp_common_pkg::*;
  import bp_me_pkg::*;
  import bsg_cache_pkg::*;
  #(parameter bp_params_e bp_params_p = e_bp_unicore_zynqparrot_prefetch_cfg
    `declare_bp_proc_params(bp_params_p)
    )
  (input clk_i, reset_i, fwd_v_i,
   input [63:0] fwd_addr_i, fwd_data_i,
   input fwd_write_i, fwd_amo_i,
   input [2:0] fwd_size_i,
   input fwd_prefetch_i,
   input [7:0] fwd_way_i,
   output fwd_ready_o,
   output rev_v_o,
   input rev_ready_i,
   output [63:0] rev_addr_o, rev_data_o,
   output [2:0] rev_size_o,
   output [7:0] rev_way_o,
   output rev_prefetch_o,
   output rev_write_o, rev_amo_o,
   input [1:0] bank_accept_i, bank_response_v_i,
   input [63:0] bank_data0_i, bank_data1_i,
   output [1:0] bank_pkt_v_o, bank_response_yumi_o,
   output [63:0] bank_addr0_o, bank_addr1_o,
   output [63:0] bank_data0_o, bank_data1_o,
   output [5:0] bank_opcode0_o, bank_opcode1_o,
   output [5:0] opcode_tagst_o, opcode_aflinv_o, opcode_ld_o,
   output [5:0] opcode_lm_o, opcode_sd_o, opcode_sm_o, opcode_amoswap_o,
   output ready_o,
   output [63:0] uncached_base_o
   );
  `declare_bp_bedrock_if(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p);
  `declare_bsg_cache_pkt_s(daddr_width_p, l2_data_width_p);
  bp_bedrock_mem_fwd_header_s fwd;
  bp_bedrock_mem_rev_header_s rev;
  bsg_cache_pkt_s [1:0] pkt;
  always_comb begin
    fwd = '0;
    fwd.msg_type = fwd_write_i ? e_bedrock_mem_wr : fwd_amo_i ? e_bedrock_mem_amo : e_bedrock_mem_rd;
    fwd.subop = fwd_amo_i ? e_bedrock_amoswap : e_bedrock_store;
    fwd.size = bp_bedrock_msg_size_e'(fwd_size_i);
    fwd.addr = paddr_width_p'(fwd_addr_i);
    fwd.payload.prefetch = fwd_prefetch_i;
    fwd.payload.way_id = $bits(fwd.payload.way_id)'(fwd_way_i);
  end
  assign rev_addr_o = 64'(rev.addr);
  assign rev_size_o = rev.size;
  assign rev_way_o = 8'(rev.payload.way_id);
  assign rev_prefetch_o = rev.payload.prefetch;
  assign rev_write_o = rev.msg_type == e_bedrock_mem_wr;
  assign rev_amo_o = rev.msg_type == e_bedrock_mem_amo;
  assign bank_addr0_o = 64'(pkt[0].addr);
  assign bank_addr1_o = 64'(pkt[1].addr);
  assign bank_opcode0_o = pkt[0].opcode;
  assign bank_opcode1_o = pkt[1].opcode;
  assign bank_data0_o = pkt[0].data;
  assign bank_data1_o = pkt[1].data;
  assign opcode_tagst_o = TAGST;
  assign opcode_aflinv_o = AFLINV;
  assign opcode_ld_o = LD;
  assign opcode_lm_o = LM;
  assign opcode_sd_o = SD;
  assign opcode_sm_o = SM;
  assign opcode_amoswap_o = AMOSWAP_D;
  assign ready_o = dut.is_ready;
  assign uncached_base_o = 64'(1) << caddr_width_p;
  bp_me_cache_controller #(.bp_params_p(bp_params_p)) dut
    (.clk_i(clk_i), .reset_i(reset_i),
     .mem_fwd_header_i(fwd), .mem_fwd_data_i(fwd_data_i), .mem_fwd_v_i(fwd_v_i),
     .mem_fwd_ready_and_o(fwd_ready_o),
     .mem_rev_header_o(rev), .mem_rev_data_o(rev_data_o), .mem_rev_v_o(rev_v_o),
     .mem_rev_ready_and_i(rev_ready_i),
     .cache_pkt_o(pkt), .cache_pkt_v_o(bank_pkt_v_o),
     .cache_pkt_yumi_i(bank_pkt_v_o & bank_accept_i),
     .cache_data_i({bank_data1_i, bank_data0_i}), .cache_data_v_i(bank_response_v_i),
     .cache_data_yumi_o(bank_response_yumi_o));
  initial assert (l2_banks_p == 2 && l2_data_width_p == 64
                  && bedrock_fill_width_p == 64 && l2_block_width_p == 512
                  && num_threads_p == 2 && num_contexts_p == 4)
    else $fatal(1, "L2 endpoint requires the full two-bank, two-resident/four-logical configuration");
endmodule
