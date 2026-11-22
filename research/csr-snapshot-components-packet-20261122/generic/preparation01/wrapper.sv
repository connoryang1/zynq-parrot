module csr_snapshot_wrapper
 #(parameter bit negative_p=0)
  (input logic clk_i,reset_i,save_v_i,seed_v_i
   ,input logic [1:0] save_addr_i,seed_addr_i,read_addr_i
   ,input logic [1665:0] save_data_i,seed_data_i
   ,output logic mismatch_o,single_mismatch_o,read_valid_o
   ,output logic [3:0] valid_vector_o
   ,output logic [1665:0] read_data_o);
  logic rv;logic [1665:0] rd;logic [3:0] ref_valid;
  csr_snapshot_reference reference4(.*,.valid_o(ref_valid),.read_valid_o(rv),.read_data_o(rd));
  bp_be_csr_snapshot_store candidate4
   (.clk_i(clk_i),.reset_i(reset_i),.save_v_i(save_v_i),.seed_v_i(seed_v_i & ~negative_p)
    ,.save_addr_i(save_addr_i),.seed_addr_i(seed_addr_i),.read_addr_i(read_addr_i)
    ,.save_data_i(save_data_i),.seed_data_i(seed_data_i),.valid_o(valid_vector_o),.read_valid_o(read_valid_o),.read_data_o(read_data_o));
  assign mismatch_o=(ref_valid != valid_vector_o) | (rv != read_valid_o) | (rd != read_data_o);
  logic sr,sc,svr,svc; logic [64:0] dr,dc;
  csr_snapshot_reference #(.contexts_p(1),.width_p(65)) reference1
   (.clk_i(clk_i),.reset_i(reset_i),.save_v_i(save_v_i),.seed_v_i(seed_v_i)
    ,.save_addr_i(save_addr_i[0]),.seed_addr_i(seed_addr_i[0]),.read_addr_i(read_addr_i[0])
    ,.save_data_i(save_data_i[64:0]),.seed_data_i(seed_data_i[64:0]),.valid_o(svr),.read_valid_o(sr),.read_data_o(dr));
  bp_be_csr_snapshot_store #(.contexts_p(1),.width_p(65)) candidate1
   (.clk_i(clk_i),.reset_i(reset_i),.save_v_i(save_v_i),.seed_v_i(seed_v_i)
    ,.save_addr_i(save_addr_i[0]),.seed_addr_i(seed_addr_i[0]),.read_addr_i(read_addr_i[0])
    ,.save_data_i(save_data_i[64:0]),.seed_data_i(seed_data_i[64:0]),.valid_o(svc),.read_valid_o(sc),.read_data_o(dc));
  assign single_mismatch_o=(svr != svc) | (sr != sc) | (dr != dc);
endmodule
