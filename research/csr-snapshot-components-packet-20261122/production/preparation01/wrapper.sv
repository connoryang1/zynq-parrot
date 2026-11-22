module csr_snapshot_production_wrapper
 #(parameter bit negative_p=0)
  (input logic clk_i,reset_i
   ,input logic instret_i,csrw_i,ctxtsw_i,addr801_i,rebind_i
   ,input logic [1:0] legacy_access_i
   ,input logic current_bank_i,retire_bank_i,save_bank_i,reservation_bank_i
   ,input logic [1:0] save_context_i,seed_context_i,read_context_i
   ,input logic [1665:0] bank0_data_i,bank1_data_i
   ,output logic mismatch_o,qualification_mismatch_o,exclusive_violation_o
   ,output logic save_intent_o,seed_intent_o,read_valid_o,reservation_owner_o
   ,output logic [3:0] valid_vector_o
   ,output logic [1665:0] read_data_o);
  // Exact production wrapper masks retire fields/T by retire bank, then selects
  // BOTH commit.ctxtsw and ctx_npc_write_v using current_bank. Reservation bank
  // is intentionally not the write owner. save_bank selects common save data.
  logic [1:0] instret_bank,csrw_bank,ctxtsw_bank,npc_bank,commit_bank;
  for(genvar i=0;i<2;i++)begin:g
    assign instret_bank[i]=instret_i & (retire_bank_i==1'(i));
    assign csrw_bank[i]=csrw_i & (retire_bank_i==1'(i));
    assign ctxtsw_bank[i]=ctxtsw_i & (retire_bank_i==1'(i));
    assign commit_bank[i]=instret_bank[i] & ctxtsw_bank[i];
    assign npc_bank[i]=csrw_bank[i] & ~ctxtsw_bank[i] & addr801_i & legacy_access_i[i];
  end
  wire save_v=commit_bank[current_bank_i];
  wire seed_command=npc_bank[current_bank_i];
  wire [1665:0] common_data=save_bank_i?bank1_data_i:bank0_data_i;
  logic [3:0] reference_valid;
  logic reference_rvalid;logic [1665:0] reference_data;
  wire ref_seed_v=seed_command & (rebind_i | ~reference_valid[seed_context_i]);
  wire candidate_seed_v=seed_command & (rebind_i | ~valid_vector_o[seed_context_i]);
  wire write_v=save_v | candidate_seed_v;
  csr_snapshot_reference reference_store
   (.clk_i(clk_i),.reset_i(reset_i),.save_v_i(save_v),.seed_v_i(ref_seed_v)
    ,.save_addr_i(save_context_i),.seed_addr_i(seed_context_i),.read_addr_i(read_context_i)
    ,.save_data_i(common_data),.seed_data_i(common_data)
    ,.valid_o(reference_valid),.read_valid_o(reference_rvalid),.read_data_o(reference_data));
  bp_be_csr_snapshot_store_production candidate
   (.clk_i(clk_i),.reset_i(reset_i),.write_v_i(write_v & ~negative_p)
    ,.write_addr_i(candidate_seed_v?seed_context_i:save_context_i),.read_addr_i(read_context_i)
    ,.write_data_i(common_data),.valid_o(valid_vector_o),.read_valid_o(read_valid_o),.read_data_o(read_data_o));
  assign save_intent_o=save_v;
  assign seed_intent_o=candidate_seed_v;
  assign qualification_mismatch_o=(ref_seed_v!=candidate_seed_v);
  assign exclusive_violation_o=save_v & (ref_seed_v | candidate_seed_v);
  assign mismatch_o=(reference_valid!=valid_vector_o) | (reference_rvalid!=read_valid_o) | (reference_data!=read_data_o);
  // Keep the independent reservation owner observable in TRACE without using
  // it to authorize a write; C++ oracle exercises both values.
  assign reservation_owner_o=reservation_bank_i;
endmodule
