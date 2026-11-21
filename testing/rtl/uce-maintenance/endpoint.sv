// Combinational endpoint equivalence, not a reachable clocked-FSM traffic test.
module uce_maintenance_endpoint
 (input logic [4:0] state_i, input logic [3:0] opcode_i, install_i
  ,input logic [8:0] flags_i
  ,output logic [15:0] before_yumi_o,after_yumi_o,before_m_o,after_m_o);
 for(genvar variant=0;variant<16;variant++) begin: variants
   if (!((variant&1) && ((variant>>2)&1))) begin: legal_configuration
   wire before_clear,after_clear;
   assign before_clear=flags_i[6]|before_i.maintenance;
   assign after_clear=flags_i[6]|after_i.maintenance;
   uce_maintenance_before #(.test_retained_p(variant&1),.test_priority_p((variant>>1)&1),
     .test_sidebuffer_p((variant>>2)&1),.instruction_p((variant>>3)&1))
   before_i(.clk_i(1'b0),.reset_i(1'b1),.enable_i(1'b1),.demand_capture_i(1'b1),
     .capture_cancel_i(1'b0),.clear_i(before_clear),.mutation_i(1'b0),.mutation_addr_i('0),
     .req_v_i(flags_i[0]),.req_type_i(opcode_i),.req_addr_i(64'h80001018),.test_hit_i(flags_i[8]),
     .metadata_v_i(1'b0),.metadata_dirty_i(1'b0),.metadata_way_i('0),
     .preview_v_i(1'b0),.preview_cancel_i(1'b0),.preview_addr_i('0),
     .arrays_accept_i(1'b1),.resident_i(1'b0),.resident_addr_i('0),.fwd_ready_i(1'b1),
     .rev_v_i(1'b0),.rev_type_i('0),.rev_size_i('0),.rev_addr_i('0),.rev_word_i('0),
     .rev_word1_i('0),.rev_way_i('0),.rev_state_i('0),.rev_prefetch_i(1'b0));
   uce_maintenance_after #(.test_retained_p(variant&1),.test_priority_p((variant>>1)&1),
     .test_sidebuffer_p((variant>>2)&1),.instruction_p((variant>>3)&1))
   after_i(.clk_i(1'b0),.reset_i(1'b1),.enable_i(1'b1),.demand_capture_i(1'b1),
     .capture_cancel_i(1'b0),.clear_i(after_clear),.mutation_i(1'b0),.mutation_addr_i('0),
     .req_v_i(flags_i[0]),.req_type_i(opcode_i),.req_addr_i(64'h80001018),.test_hit_i(flags_i[8]),
     .metadata_v_i(1'b0),.metadata_dirty_i(1'b0),.metadata_way_i('0),
     .preview_v_i(1'b0),.preview_cancel_i(1'b0),.preview_addr_i('0),
     .arrays_accept_i(1'b1),.resident_i(1'b0),.resident_addr_i('0),.fwd_ready_i(1'b1),
     .rev_v_i(1'b0),.rev_type_i('0),.rev_size_i('0),.rev_addr_i('0),.rev_word_i('0),
     .rev_word1_i('0),.rev_way_i('0),.rev_state_i('0),.rev_prefetch_i(1'b0));
   // Force only explicit combinational endpoint/state knobs; both actual UCE
   // sources retain their original final-yumi logic and actual clear feedback.
   // Arbitrary combinations intentionally include unreachable FSM endpoints.
   /* verilator lint_off ENUMVALUE */
   always_comb begin
     force before_i.dut.state_r=state_i;
     force after_i.dut.state_r=state_i;
     force before_i.dut.cache_req_ready_lo=flags_i[1];
     force after_i.dut.cache_req_ready_lo=flags_i[1];
     force before_i.dut.cache_req_v_r=flags_i[2];
     force after_i.dut.cache_req_v_r=flags_i[2];
     force before_i.dut.prefetch_free_v=flags_i[3];
     force after_i.dut.prefetch_free_v=flags_i[3];
     force before_i.dut.prefetch_duplicate_v=flags_i[4];
     force after_i.dut.prefetch_duplicate_v=flags_i[4];
     force before_i.dut.prefetch_metadata_can_accept=flags_i[5];
     force after_i.dut.prefetch_metadata_can_accept=flags_i[5];
     force before_i.dut.prefetch_install_acquire=flags_i[7];
     force after_i.dut.prefetch_install_acquire=flags_i[7];
     force before_i.dut.prefetch_install_state_r=install_i;
     force after_i.dut.prefetch_install_state_r=install_i;
   end
   /* verilator lint_on ENUMVALUE */
   assign before_yumi_o[variant]=before_i.req_yumi_o;
   assign after_yumi_o[variant]=after_i.req_yumi_o;
   assign before_m_o[variant]=before_i.maintenance;
   assign after_m_o[variant]=after_i.maintenance;
   end else begin: rejected_configuration
     // The production RTL expressly rejects retained+legacy sidebuffer.
     assign before_yumi_o[variant]=0;
     assign after_yumi_o[variant]=0;
     assign before_m_o[variant]=0;
     assign after_m_o[variant]=0;
   end
 end
endmodule
