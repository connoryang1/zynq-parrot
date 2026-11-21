module retained_line_store_wrapper
 #(parameter int I_LINES = 93, parameter int D_LINES = 131)
  (input logic [1:0] clk_i, reset_i, clear_i, invalidate_v_i
   , input logic [33:0] invalidate_addr0_i, invalidate_addr1_i
   , input logic [1:0] lookup_v_i
   , output logic [1:0] lookup_ready_o
   , input logic [33:0] lookup_addr0_i, lookup_addr1_i
   , output logic [1:0] resp_v_o
   , input logic [1:0] resp_ready_i
   , output logic [1:0] resp_hit_o
   , output logic [511:0] resp_data0_o, resp_data1_o
   , input logic [1:0] insert_v_i
   , output logic [1:0] insert_ready_o
   , input logic [33:0] insert_addr0_i, insert_addr1_i
   , input logic [511:0] insert_data0_i, insert_data1_i
   , input logic [1:0] insert_replace_i, insert_cancel_i
   , output logic [1:0] insert_done_o, insert_published_o, busy_o, epoch_wrap_o
   , output logic [1:0] debug_data_v_o, debug_data_w_o
   , output logic [2:0] debug_word0_o, debug_word1_o
   , output logic [31:0] i_lines_o, d_lines_o
   );
  assign i_lines_o = I_LINES;
  assign d_lines_o = D_LINES;
  bp_retained_line_store
   #(.paddr_width_p(34), .sets_p(64), .i_lines_p(I_LINES), .d_lines_p(D_LINES), .epoch_width_p(2)) dut
   (.clk_i(clk_i), .reset_i(reset_i), .clear_i(clear_i)
    ,.invalidate_v_i(invalidate_v_i), .invalidate_addr_i({invalidate_addr1_i,invalidate_addr0_i})
    ,.lookup_v_i(lookup_v_i), .lookup_ready_o(lookup_ready_o), .lookup_addr_i({lookup_addr1_i,lookup_addr0_i})
    ,.resp_v_o(resp_v_o), .resp_ready_i(resp_ready_i), .resp_hit_o(resp_hit_o), .resp_data_o({resp_data1_o,resp_data0_o})
    ,.insert_v_i(insert_v_i), .insert_ready_o(insert_ready_o), .insert_addr_i({insert_addr1_i,insert_addr0_i})
    ,.insert_data_i({insert_data1_i,insert_data0_i}), .insert_replace_i(insert_replace_i), .insert_cancel_i(insert_cancel_i)
    ,.insert_done_o(insert_done_o), .insert_published_o(insert_published_o), .busy_o(busy_o), .epoch_wrap_o(epoch_wrap_o));
  assign debug_data_v_o = dut.data_v;
  assign debug_data_w_o = dut.data_w;
  assign debug_word0_o = dut.data_addr[0][2:0];
  assign debug_word1_o = dut.data_addr[1][2:0];
endmodule
