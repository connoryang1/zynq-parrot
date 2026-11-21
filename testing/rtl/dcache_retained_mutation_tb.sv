// Exercise accepted mutation events on the real Dcache hit/atomic pipeline.
`include "bp_common_defines.svh"
`include "bp_be_defines.svh"
module dcache_retained_mutation_tb
 import bp_common_pkg::*;
 import bp_be_pkg::*;
 #(parameter bp_params_e bp_params_p=e_bp_custom_cfg
   `declare_bp_proc_params(bp_params_p)
   )
 (input clk_i,reset_i,v_i,uncached_i
  ,input [5:0] opcode_i,input [63:0] addr_i,store_data_i
  ,input [2:0] engine_i,input [63:0] engine_addr_i,engine_data_i
  ,input [2:0] engine_word_i,input engine_complete_i
  ,output logic engine_yumi_o
  ,output mutation_o,maintenance_o,result_v_o,request_o
  ,output [63:0] mutation_addr_o,result_data_o
  );
 `declare_bp_be_dcache_pkt_s(vaddr_width_p);
 `declare_bp_be_dcache_engine_if(paddr_width_p,dcache_tag_width_p,dcache_sets_p,dcache_assoc_p,
   dcache_data_width_p,dcache_block_width_p,dcache_fill_width_p,dcache_req_id_width_p);
 bp_be_dcache_pkt_s pkt;
 bp_be_dcache_data_mem_pkt_s data_pkt;
 bp_be_dcache_tag_mem_pkt_s tag_pkt;
 bp_be_dcache_stat_mem_pkt_s stat_pkt;
 logic data_v,tag_v,stat_v,data_yumi,tag_yumi,stat_yumi;
 logic [paddr_width_p-1:0] addr_tl_r,mutation_addr;
 logic uc_tl_r;
 always_ff @(posedge clk_i) begin
   addr_tl_r<=paddr_width_p'(addr_i);uc_tl_r<=uncached_i;
 end
 always_comb begin
   pkt='0;pkt.opcode=bp_be_dcache_fu_op_e'(opcode_i);pkt.vaddr=vaddr_width_p'(addr_i);pkt.rd_addr=1;
   data_pkt='0;data_pkt.opcode=e_cache_data_mem_write;
   data_pkt.addr=paddr_width_p'(engine_addr_i);data_pkt.index=engine_addr_i[6+:$clog2(dcache_sets_p)];
   data_pkt.fill_index=1<<engine_word_i;data_pkt.data=engine_data_i;
   tag_pkt='0;tag_pkt.index=data_pkt.index;tag_pkt.way_id=0;tag_pkt.state=e_COH_M;
   tag_pkt.tag=engine_addr_i[6+$clog2(dcache_sets_p)+:dcache_tag_width_p];
   tag_pkt.opcode=engine_i==1?e_cache_tag_mem_set_clear:e_cache_tag_mem_set_tag;
   stat_pkt='0;stat_pkt.opcode=e_cache_stat_mem_set_clear;stat_pkt.index=data_pkt.index;
   data_v=engine_i==3;tag_v=(engine_i==1)||(engine_i==2);stat_v=engine_i==4;
   engine_yumi_o=(data_v&&data_yumi)||(tag_v&&tag_yumi)||(stat_v&&stat_yumi);
 end
 assign mutation_addr_o=64'(mutation_addr);
 bp_be_dcache #(.bp_params_p(bp_params_p),.retained_buffer_p(1))
 dut(.clk_i(clk_i),.reset_i(reset_i),.busy_o(),.ordered_o(),.dcache_pkt_i(pkt),.v_i(v_i),.replay_i(0),
   .ptag_i(addr_tl_r[paddr_width_p-1:12]),.ptag_v_i(1),.ptag_uncached_i(uc_tl_r),.ptag_dram_i(1),
   .st_data_i(store_data_i),.flush_i(0),.v_o(result_v_o),.data_o(result_data_o),.rd_addr_o(),.thread_id_o(),.tag_o(),
   .unsigned_o(),.int_o(),.float_o(),.ptw_o(),.ret_o(),.late_o(),.prefetch_replay_o(),
   .replay_issue_o(),.replay_done_o(),.replay_accepted_o(),
   .retained_mutation_v_o(mutation_o),.retained_mutation_paddr_o(mutation_addr),.retained_maintenance_v_o(maintenance_o),
   .cache_req_o(),.cache_req_v_o(request_o),.cache_req_yumi_i(1),.cache_req_lock_i(0),.cache_req_metadata_o(),.cache_req_metadata_v_o(),
   .cache_req_id_i('0),.cache_req_critical_i(engine_complete_i),.cache_req_last_i(engine_complete_i),
   .cache_req_credits_full_i(0),.cache_req_credits_empty_i(1),
   .data_mem_pkt_v_i(data_v),.data_mem_pkt_i(data_pkt),.data_mem_pkt_yumi_o(data_yumi),.data_mem_o(),
   .tag_mem_pkt_v_i(tag_v),.tag_mem_pkt_i(tag_pkt),.tag_mem_pkt_yumi_o(tag_yumi),.tag_mem_o(),
   .stat_mem_pkt_v_i(stat_v),.stat_mem_pkt_i(stat_pkt),.stat_mem_pkt_yumi_o(stat_yumi),.stat_mem_o());
 initial assert(dcache_sets_p==4&&dcache_assoc_p==8&&dcache_fill_width_p==64&&dcache_block_width_p==512)
   else $fatal(1,"Mutation unit requires explicit small32line L1 fixture");
endmodule
