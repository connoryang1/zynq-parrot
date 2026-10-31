// Directed wrapper for the detached instruction replay buffer.
`include "bp_common_defines.svh"
`include "bp_fe_defines.svh"
module icache_replay_buffer_tb
  import bp_common_pkg::*;
  import bp_fe_pkg::*;
  #(parameter bp_params_e bp_params_p = e_bp_unicore_cfg
    `declare_bp_proc_params(bp_params_p)
    )
  (input clk_i, reset_i,
   input init_v_i,
   input [1:0] init_index_i,
   output init_yumi_o,
   input replay_v_i,
   input [63:0] replay_addr_i,
   input [3:0] replay_fill_i,
   input [63:0] replay_word0_i, replay_word1_i,
   output replay_yumi_o,
   input fetch_v_i,
   input fence_i,
   input [63:0] fetch_addr_i,
   input query_v_i,
   input [63:0] query_addr_i,
   output query_hit_o,
   output fetch_yumi_o,
   output hit_v_o,
   output miss_req_v_o,
   output [63:0] data_o
   );

  localparam sets_lp = 4;
  localparam assoc_lp = 2;
  localparam block_lp = 512;
  localparam fill_lp = 128;
  localparam data_lp = 64;
  localparam tag_lp = paddr_width_p-$clog2(sets_lp)-$clog2(block_lp/8);
  localparam id_lp = 4;
  `declare_bp_fe_icache_engine_if(paddr_width_p, tag_lp, sets_lp, assoc_lp,
                                  data_lp, block_lp, fill_lp, id_lp);
  `declare_bp_fe_icache_pkt_s(vaddr_width_p);

  bp_fe_icache_pkt_s icache_pkt;
  bp_fe_icache_req_s cache_req;
  bp_fe_icache_req_metadata_s cache_metadata;
  bp_fe_icache_tag_mem_pkt_s tag_pkt;
  bp_fe_icache_data_mem_pkt_s data_pkt;
  bp_fe_icache_stat_mem_pkt_s stat_pkt;
  bp_fe_icache_tag_info_s tag_data;
  bp_fe_icache_stat_info_s stat_data;
  logic cache_req_v, cache_req_yumi, cache_metadata_v;
  logic data_pkt_v, data_pkt_yumi;
  logic tag_pkt_v, tag_pkt_yumi;
  logic stat_pkt_v, stat_pkt_yumi;
  logic [block_lp-1:0] data_mem;
  logic [data_lp-1:0] fetch_data;
  logic miss_v, fence_v;

  always_comb begin
    icache_pkt = '0;
    icache_pkt.vaddr = vaddr_width_p'(fetch_addr_i);
    icache_pkt.op = fence_i ? e_icache_inval : e_icache_fetch;
    icache_pkt.spec = 1'b0;

    tag_pkt = '0;
    tag_pkt.opcode = e_cache_tag_mem_set_clear;
    tag_pkt.index = init_index_i;
    tag_pkt_v = init_v_i;

    data_pkt = '0;
    data_pkt.opcode = e_cache_data_mem_prefetch;
    data_pkt.addr = paddr_width_p'(replay_addr_i);
    data_pkt.data = {replay_word1_i, replay_word0_i};
    data_pkt.fill_index = replay_fill_i;
    data_pkt_v = replay_v_i;

    stat_pkt = '0;
    stat_pkt_v = 1'b0;
  end

  // Only invalidations need a synthetic cache-engine completion. Demand
  // misses remain visible at the wrapper boundary for the negative checks.
  assign cache_req_yumi = cache_req_v
    & (cache_req.msg_type == e_cache_inval);
  assign init_yumi_o = tag_pkt_yumi;
  assign replay_yumi_o = data_pkt_yumi;
  assign miss_req_v_o = cache_req_v;
  assign data_o = fetch_data;

  bp_fe_icache
   #(.bp_params_p(bp_params_p)
     ,.sets_p(sets_lp), .assoc_p(assoc_lp)
     ,.block_width_p(block_lp), .fill_width_p(fill_lp)
     ,.data_width_p(data_lp), .tag_width_p(tag_lp), .id_width_p(id_lp)
     ,.replay_buffer_p(1'b1), .replay_buffer_els_p(4)
     )
   dut
    (.clk_i(clk_i), .reset_i(reset_i)
     ,.icache_pkt_i(icache_pkt), .v_i(fetch_v_i), .force_i(1'b0)
     ,.miss_abort_i(1'b0), .yumi_o(fetch_yumi_o), .tl_flush_i(1'b0)
     ,.ptag_i(fetch_addr_i[page_offset_width_gp+:ptag_width_p])
     ,.ptag_v_i(1'b1), .ptag_uncached_i(1'b0), .ptag_nonidem_i(1'b0)
     ,.ptag_dram_i(1'b1), .tv_flush_i(1'b0), .tv_we_o()
     ,.data_o(fetch_data), .hit_v_o(hit_v_o), .miss_v_o(miss_v)
     ,.fence_v_o(fence_v), .yumi_i(hit_v_o | fence_v)
     ,.replay_query_v_i(query_v_i)
     ,.replay_query_paddr_i(paddr_width_p'(query_addr_i))
     ,.replay_query_hit_o(query_hit_o)
     ,.cache_req_o(cache_req), .cache_req_v_o(cache_req_v)
     ,.cache_req_yumi_i(cache_req_yumi), .cache_req_lock_i(1'b0)
     ,.cache_req_metadata_o(cache_metadata)
     ,.cache_req_metadata_v_o(cache_metadata_v), .cache_req_id_i('0)
     ,.cache_req_critical_i(1'b0), .cache_req_last_i(1'b1)
     ,.cache_req_credits_full_i(1'b0), .cache_req_credits_empty_i(1'b1)
     ,.data_mem_pkt_v_i(data_pkt_v), .data_mem_pkt_i(data_pkt)
     ,.data_mem_pkt_yumi_o(data_pkt_yumi), .data_mem_o(data_mem)
     ,.tag_mem_pkt_v_i(tag_pkt_v), .tag_mem_pkt_i(tag_pkt)
     ,.tag_mem_pkt_yumi_o(tag_pkt_yumi), .tag_mem_o(tag_data)
     ,.stat_mem_pkt_v_i(stat_pkt_v), .stat_mem_pkt_i(stat_pkt)
     ,.stat_mem_pkt_yumi_o(stat_pkt_yumi), .stat_mem_o(stat_data)
     );
endmodule
