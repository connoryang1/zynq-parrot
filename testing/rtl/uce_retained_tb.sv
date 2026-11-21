// Real data UCE and shared retained BRAM backend, with scalar memory endpoints.
`include "bp_common_defines.svh"
`include "bp_me_defines.svh"
module uce_retained_tb
 import bp_common_pkg::*;
 import bp_me_pkg::*;
 #(parameter int retained_lines_p=64
   , parameter bit instruction_p=0
   , parameter bp_params_e bp_params_p=e_bp_custom_cfg
   `declare_bp_proc_params(bp_params_p)
   )
 (input clk_i,reset_i,enable_i,demand_capture_i,capture_cancel_i,clear_i,mutation_i
  ,input [63:0] mutation_addr_i
  ,input req_v_i,input [3:0] req_type_i,input [63:0] req_addr_i
  ,input metadata_v_i,metadata_dirty_i,input [2:0] metadata_way_i
  ,input preview_v_i,preview_cancel_i,input [63:0] preview_addr_i
  ,input arrays_accept_i, resident_i,input [63:0] resident_addr_i
  ,output req_yumi_o,req_lock_o,critical_o,last_o,idle_o,credits_empty_o
  ,output preview_ready_o,preview_idle_o
  ,output data_v_o,tag_v_o,input fwd_ready_i,output fwd_v_o
  ,output [2:0] fwd_size_o,output [3:0] fwd_type_o
  ,output [63:0] fwd_addr_o,fwd_word_o,output [7:0] fwd_way_o
  ,output [2:0] fwd_state_o,output fwd_prefetch_o
  ,input rev_v_i,output rev_ready_o,input [3:0] rev_type_i
  ,input [2:0] rev_size_i,input [63:0] rev_addr_i,rev_word_i,rev_word1_i
  ,input [7:0] rev_way_i,input [2:0] rev_state_i,input rev_prefetch_i
  ,output [63:0] data_word_o,data_word1_o,output [7:0] data_fill_o
  ,output [1:0] data_opcode_o,output [63:0] data_addr_o
  ,output logic [31:0] lookups_o,hits_o,published_o
  ,output [31:0] capacity_o,fill_words_o,bus_words_o
  ,output instruction_o
  );
 localparam sets_lp=4,assoc_lp=8,block_lp=512,fill_lp=instruction_p?icache_fill_width_p:64,id_lp=4;
 localparam cache_data_lp=instruction_p?icache_data_width_p:dcache_data_width_p;
 localparam offset_lp=6,index_lp=2,tag_lp=paddr_width_p-offset_lp-index_lp;
 `declare_bp_cache_engine_generic_if(paddr_width_p,tag_lp,sets_lp,assoc_lp,
   cache_data_lp,block_lp,fill_lp,id_lp,cache);
 `declare_bp_bedrock_if(paddr_width_p,lce_id_width_p,cce_id_width_p,did_width_p,lce_assoc_p);
 bp_cache_req_s req;
 bp_cache_req_metadata_s metadata;
 bp_cache_tag_mem_pkt_s tag_pkt;
 bp_cache_tag_info_s tag_info;
 bp_cache_data_mem_pkt_s data_pkt;
 bp_cache_stat_mem_pkt_s stat_pkt;
 bp_bedrock_mem_fwd_header_s fwd;
 bp_bedrock_mem_rev_header_s rev;
 logic stat_v;
 logic maintenance,preview_ready,detached_ready;
 logic [bedrock_fill_width_p-1:0] fwd_data;
 logic [bedrock_fill_width_p-1:0] rev_data;
 logic [1:0] lookup_v,lookup_ready,resp_v,resp_ready,resp_hit;
 logic [1:0] insert_v,insert_ready,insert_replace,insert_cancel,insert_done,insert_published,busy,wrap;
 logic [1:0][paddr_width_p-1:0] lookup_addr,insert_addr;
 logic [1:0][511:0] resp_data,insert_data;
 logic [511:0] dirty_line;
 always_comb begin
   req='0;req.msg_type=bp_cache_req_msg_type_e'(req_type_i);
   req.addr=paddr_width_p'(req_addr_i);req.size=e_size_64B;req.id=4'h9;
   metadata='0;metadata.hit_or_repl_way=metadata_way_i;metadata.dirty=metadata_dirty_i;
   tag_info='0;
   if (resident_i) begin
     tag_info.state=e_COH_M;tag_info.tag=resident_addr_i[8+:tag_lp];
   end else if (metadata_dirty_i) begin
     tag_info.state=e_COH_M;tag_info.tag=tag_lp'(32'h800001);
   end
   rev='0;rev.msg_type=bp_bedrock_msg_u'(rev_type_i);
   rev.size=bp_bedrock_msg_size_e'(rev_size_i);rev.addr=paddr_width_p'(rev_addr_i);
   rev.payload.way_id=$bits(rev.payload.way_id)'(rev_way_i);
   rev.payload.state=bp_coh_states_e'(rev_state_i);rev.payload.prefetch=rev_prefetch_i;
   for (int i=0;i<8;i++) dirty_line[64*i+:64]=64'hfedc000000000000+64'(i);
 end
 assign data_word_o=data_pkt.data;
 if(fill_lp>64)assign data_word1_o=data_pkt.data[64+:64];else assign data_word1_o=0;
 assign data_fill_o=data_pkt.fill_index;
 assign data_opcode_o=data_pkt.opcode;
 assign data_addr_o=64'(data_pkt.addr);
 assign fwd_addr_o=64'(fwd.addr);
 assign fwd_word_o=fwd_data;
 assign fwd_size_o=fwd.size;
 assign fwd_type_o=fwd.msg_type;
 assign fwd_way_o=8'(fwd.payload.way_id);
 assign fwd_state_o=fwd.payload.state;
 assign fwd_prefetch_o=fwd.payload.prefetch;
 assign capacity_o=retained_lines_p;
 assign fill_words_o=fill_lp/64;
 assign bus_words_o=bedrock_fill_width_p/64;
 if(bedrock_fill_width_p==128)assign rev_data={rev_word1_i,rev_word_i};else assign rev_data=rev_word_i;
 assign instruction_o=instruction_p;
 assign preview_ready_o=instruction_p?detached_ready:preview_ready;
 assign lookup_v[0]=0;assign lookup_addr[0]='0;assign resp_ready[0]=1;
 assign insert_v[0]=0;assign insert_addr[0]='0;assign insert_data[0]='0;
 assign insert_replace[0]=1;assign insert_cancel[0]=0;
 always_ff @(posedge clk_i) begin
   if(reset_i) begin lookups_o<=0;hits_o<=0;published_o<=0;end
   else begin
     if(lookup_v[1]&&lookup_ready[1])lookups_o<=lookups_o+1;
     if(resp_v[1]&&resp_ready[1]&&resp_hit[1])hits_o<=hits_o+1;
     if(insert_published[1])published_o<=published_o+1;
   end
 end
 bp_retained_line_store #(.paddr_width_p(paddr_width_p),.sets_p(64),.i_lines_p(0),.d_lines_p(retained_lines_p))
 store(.clk_i({clk_i,clk_i}),.reset_i({reset_i,reset_i}),.clear_i({(clear_i|maintenance),1'b0}),
   .invalidate_v_i({mutation_i,1'b0}),.invalidate_addr_i({paddr_width_p'(mutation_addr_i),{paddr_width_p{1'b0}}}),
   .lookup_v_i(lookup_v),.lookup_ready_o(lookup_ready),.lookup_addr_i(lookup_addr),
   .resp_v_o(resp_v),.resp_ready_i(resp_ready),.resp_hit_o(resp_hit),.resp_data_o(resp_data),
   .insert_v_i(insert_v),.insert_ready_o(insert_ready),.insert_addr_i(insert_addr),.insert_data_i(insert_data),
   .insert_replace_i(insert_replace),.insert_cancel_i(insert_cancel),.insert_done_o(insert_done),
   .insert_published_o(insert_published),.busy_o(busy),.epoch_wrap_o(wrap));
 bp_uce #(.bp_params_p(bp_params_p),.writeback_p(!instruction_p),.prefetch_p(1),.assoc_p(assoc_lp),.sets_p(sets_lp),
   .block_width_p(block_lp),.fill_width_p(fill_lp),.data_width_p(cache_data_lp),
   .tag_width_p(tag_lp),.id_width_p(id_lp),.prefetch_els_p(2),.prefetch_full_line_p(1),
   .prefetch_critical_forward_p(0),.retained_buffer_p(1))
 dut(.clk_i(clk_i),.reset_i(reset_i),.did_i('0),.lce_id_i('0),
   .cache_req_i(req),.cache_req_v_i(req_v_i),.cache_req_yumi_o(req_yumi_o),.cache_req_lock_o(req_lock_o),
   .cache_req_metadata_i(metadata),.cache_req_metadata_v_i(metadata_v_i),.cache_req_id_o(),
   .cache_req_critical_o(critical_o),.cache_req_last_o(last_o),.cache_req_credits_full_o(),.cache_req_credits_empty_o(credits_empty_o),
   .preview_paddr_i(paddr_width_p'(preview_addr_i)),.preview_v_i(preview_v_i&&!instruction_p),.preview_cancel_i(preview_cancel_i),
   .preview_ready_o(preview_ready),.preview_idle_o(preview_idle_o),
   .detached_prefetch_addr_i(paddr_width_p'(preview_addr_i)),.detached_prefetch_v_i(preview_v_i&&instruction_p),
   .detached_prefetch_ready_and_o(detached_ready),.prefetch_outstanding_o(),.prefetch_complete_o(),
   .retained_enable_i(enable_i),.retained_demand_capture_i(demand_capture_i),.retained_capture_cancel_i(capture_cancel_i),
   .retained_clear_i(clear_i),.retained_maintenance_o(maintenance),.retained_mutation_v_i(mutation_i),
   .retained_mutation_paddr_i(paddr_width_p'(mutation_addr_i)),.retained_idle_o(idle_o),
   .retained_lookup_v_o(lookup_v[1]),.retained_lookup_ready_i(lookup_ready[1]),.retained_lookup_addr_o(lookup_addr[1]),
   .retained_resp_v_i(resp_v[1]),.retained_resp_ready_o(resp_ready[1]),.retained_resp_hit_i(resp_hit[1]),.retained_resp_data_i(resp_data[1]),
   .retained_insert_v_o(insert_v[1]),.retained_insert_ready_i(insert_ready[1]),.retained_insert_addr_o(insert_addr[1]),
   .retained_insert_data_o(insert_data[1]),.retained_insert_replace_o(insert_replace[1]),.retained_insert_cancel_o(insert_cancel[1]),
   .retained_insert_done_i(insert_done[1]),.retained_insert_published_i(insert_published[1]),.retained_backend_busy_i(busy[1]),
   .tag_mem_pkt_o(tag_pkt),.tag_mem_pkt_v_o(tag_v_o),.tag_mem_pkt_yumi_i(tag_v_o&arrays_accept_i),.tag_mem_i(tag_info),
   .data_mem_pkt_o(data_pkt),.data_mem_pkt_v_o(data_v_o),.data_mem_pkt_yumi_i(data_v_o&arrays_accept_i),.data_mem_i(dirty_line),
   .stat_mem_pkt_o(stat_pkt),.stat_mem_pkt_v_o(stat_v),.stat_mem_pkt_yumi_i(stat_v&arrays_accept_i),.stat_mem_i('0),
   .mem_fwd_header_o(fwd),.mem_fwd_data_o(fwd_data),.mem_fwd_v_o(fwd_v_o),.mem_fwd_ready_and_i(fwd_ready_i),
   .mem_rev_header_i(rev),.mem_rev_data_i(rev_data),.mem_rev_v_i(rev_v_i),.mem_rev_ready_and_o(rev_ready_o));
 initial assert(bedrock_fill_width_p==64||bedrock_fill_width_p==128) else $fatal(1,"UCE retained test needs64/128b physical stream");
endmodule
