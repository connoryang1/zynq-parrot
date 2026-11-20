// Ordinary-refill driver for the opt-in demand-populated replay capacity control.
`include "bp_common_defines.svh"
`include "bp_fe_defines.svh"
module icache_demand_capture_tb
  import bp_common_pkg::*;
  import bp_fe_pkg::*;
  #(parameter bp_params_e bp_params_p = e_bp_unicore_cfg
    , parameter bit capture_enabled_p = 1'b0
    `declare_bp_proc_params(bp_params_p)
    )
  (input clk_i, reset_i,
   input init_v_i,
   input [1:0] init_index_i,
   output init_yumi_o,
   input data_v_i,
   input [1:0] data_kind_i, // cached write, uncached reply, detached replay
   input [63:0] data_addr_i,
   input [3:0] data_fill_i,
   input [63:0] data_word0_i, data_word1_i,
   input data_first_i, data_last_i,
   output data_yumi_o,
   input fetch_v_i, fetch_uncached_i, fence_i, abort_i, flush_i,
   input [63:0] fetch_addr_i,
   input query_v_i,
   input [63:0] query_addr_i,
   output query_hit_o,
   output fetch_yumi_o, hit_v_o, miss_req_v_o, fence_accept_o,
   output [63:0] data_o
   );
  localparam sets_lp = 4;
  localparam assoc_lp = 8;
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
  logic data_pkt_yumi, tag_pkt_v, tag_pkt_yumi, stat_pkt_yumi;
  logic [block_lp-1:0] data_mem;
  logic [data_lp-1:0] fetch_data;
  logic miss_v, fence_v, fence_complete_r, fence_active_r;
  logic [1:0] fence_index_r;
  logic stat_pkt_v;
  always_comb begin
    icache_pkt = '0;
    icache_pkt.vaddr = vaddr_width_p'(fetch_addr_i);
    icache_pkt.op = fence_i ? e_icache_inval : e_icache_fetch;
    icache_pkt.spec = 1'b0;
    tag_pkt = '0;
    tag_pkt.opcode = (init_v_i | fence_active_r)
      ? e_cache_tag_mem_set_clear : e_cache_tag_mem_set_tag;
    tag_pkt.index = fence_active_r ? fence_index_r
      : init_v_i ? init_index_i : data_addr_i[6+:2];
    tag_pkt.way_id = '0;
    tag_pkt.state = e_COH_M;
    tag_pkt.tag = data_addr_i[8+:tag_lp];
    tag_pkt_v = init_v_i | fence_active_r
      | (data_v_i & data_first_i & (data_kind_i == 0));
    data_pkt = '0;
    data_pkt.opcode = data_kind_i == 0 ? e_cache_data_mem_write
      : data_kind_i == 1 ? e_cache_data_mem_uncached : e_cache_data_mem_prefetch;
    data_pkt.addr = paddr_width_p'(data_addr_i);
    data_pkt.index = data_addr_i[6+:2];
    data_pkt.way_id = '0;
    data_pkt.data = {data_word1_i, data_word0_i};
    data_pkt.fill_index = data_fill_i;
    stat_pkt = '0;
    stat_pkt.opcode = e_cache_stat_mem_set_clear;
    stat_pkt.index = fence_active_r ? fence_index_r : init_index_i;
    stat_pkt_v = init_v_i | fence_active_r;
  end
  assign cache_req_yumi = cache_req_v;
  assign fence_accept_o = cache_req_yumi & (cache_req.msg_type == e_cache_inval);
  // Minimal ordinary-engine invalidation sweep. Completing a synthetic
  // fence without clearing the ordinary tags would invalidate only the side
  // store and make the post-fence main-cache miss check meaningless.
  always_ff @(posedge clk_i) begin
    if (reset_i) begin
      fence_complete_r <= 1'b0;
      fence_active_r <= 1'b0;
      fence_index_r <= '0;
    end else begin
      fence_complete_r <= 1'b0;
      if (fence_accept_o) begin
        fence_active_r <= 1'b1;
        fence_index_r <= '0;
      end else if (fence_active_r & tag_pkt_yumi & stat_pkt_yumi) begin
        if (&fence_index_r) begin
          fence_active_r <= 1'b0;
          fence_complete_r <= 1'b1;
        end else fence_index_r <= fence_index_r + 1'b1;
      end
    end
  end
  assign init_yumi_o = tag_pkt_yumi & stat_pkt_yumi;
  assign data_yumi_o = data_pkt_yumi;
  assign miss_req_v_o = cache_req_v & (cache_req.msg_type != e_cache_inval);
  assign data_o = fetch_data;
  bp_fe_icache
   #(.bp_params_p(bp_params_p), .sets_p(sets_lp), .assoc_p(assoc_lp)
     ,.block_width_p(block_lp), .fill_width_p(fill_lp)
     ,.data_width_p(data_lp), .tag_width_p(tag_lp), .id_width_p(id_lp)
     ,.replay_buffer_p(1'b1), .replay_buffer_els_p(32)
     ,.replay_buffer_demand_capture_p(capture_enabled_p)
     )
   dut
    (.clk_i(clk_i), .reset_i(reset_i)
     ,.icache_pkt_i(icache_pkt), .v_i(fetch_v_i), .force_i(1'b0)
     ,.miss_abort_i(abort_i), .yumi_o(fetch_yumi_o), .tl_flush_i(flush_i)
     ,.ptag_i(fetch_addr_i[page_offset_width_gp+:ptag_width_p])
     ,.ptag_v_i(1'b1), .ptag_uncached_i(fetch_uncached_i), .ptag_nonidem_i(1'b0)
     ,.ptag_dram_i(1'b1), .tv_flush_i(flush_i), .tv_we_o()
     ,.data_o(fetch_data), .hit_v_o(hit_v_o), .miss_v_o(miss_v)
     ,.fence_v_o(fence_v), .yumi_i(hit_v_o | fence_v)
     ,.replay_query_v_i(query_v_i)
     ,.replay_query_paddr_i(paddr_width_p'(query_addr_i))
     ,.replay_query_hit_o(query_hit_o)
     ,.cache_req_o(cache_req), .cache_req_v_o(cache_req_v)
     ,.cache_req_yumi_i(cache_req_yumi), .cache_req_lock_i(fence_active_r)
     ,.cache_req_metadata_o(cache_metadata)
     ,.cache_req_metadata_v_o(cache_metadata_v), .cache_req_id_i('0)
     ,.cache_req_critical_i(fence_complete_r | (data_v_i & data_first_i))
     ,.cache_req_last_i(fence_complete_r | (data_v_i & data_last_i))
     ,.cache_req_credits_full_i(1'b0), .cache_req_credits_empty_i(1'b1)
     ,.data_mem_pkt_v_i(data_v_i), .data_mem_pkt_i(data_pkt)
     ,.data_mem_pkt_yumi_o(data_pkt_yumi), .data_mem_o(data_mem)
     ,.tag_mem_pkt_v_i(tag_pkt_v), .tag_mem_pkt_i(tag_pkt)
     ,.tag_mem_pkt_yumi_o(tag_pkt_yumi), .tag_mem_o(tag_data)
     ,.stat_mem_pkt_v_i(stat_pkt_v), .stat_mem_pkt_i(stat_pkt)
     ,.stat_mem_pkt_yumi_o(stat_pkt_yumi), .stat_mem_o(stat_data)
     );
endmodule
