module prefetch_mshr_table_tb
  (input clk_i, reset_i, alloc_v_i, issue_v_i, response_v_i, response_last_i,
   input [55:0] alloc_addr_i, input [1:0] alloc_context_i, input [2:0] alloc_way_i,
   input [1:0] issue_id_i, response_id_i,
   output alloc_ready_o, alloc_yumi_o, issue_ready_o, response_ready_o,
   output [1:0] alloc_id_o, output [1:0] valid_o, output [1:0] issued_o,
   output [55:0] addr0_o, addr1_o, output [1:0] context0_o, context1_o,
   output [2:0] way0_o, way1_o);
  logic [1:0] valid, issued;
  logic [1:0][55:0] addr;
  logic [1:0][1:0] ctx;
  logic [1:0][2:0] way;
  bp_prefetch_mshr_table #(.addr_width_p(56), .id_width_p(2), .context_width_p(2),
                            .way_width_p(3), .els_p(2)) dut
    (.clk_i, .reset_i, .alloc_ready_o, .alloc_v_i, .alloc_addr_i,
     .alloc_context_i, .alloc_way_i, .alloc_id_o, .alloc_yumi_o,
     .issue_v_i, .issue_id_i, .issue_ready_o, .response_v_i, .response_id_i,
     .response_ready_o, .response_last_i, .valid_o(valid), .issued_o(issued),
     .addr_o(addr), .context_o(ctx), .way_o(way));
  assign valid_o = valid; assign issued_o = issued;
  assign addr0_o = addr[0]; assign addr1_o = addr[1];
  assign context0_o = ctx[0]; assign context1_o = ctx[1];
  assign way0_o = way[0]; assign way1_o = way[1];
endmodule
