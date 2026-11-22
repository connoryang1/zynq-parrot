module gpr_prefetch_miter #(parameter int negative_p=0)
 (input logic clk_i,reset_i,miss_i,commit_i,redirect_i,drain_i,dirty_i,fe_yumi_i,
  input logic [1:0] target_i,input logic [1:0] w_v_i,
  input logic [1:0][1:0] w_context_i,input logic [1:0][4:0] w_reg_i,
  input logic [1:0][63:0] w_data_i,
  output logic mismatch_o,collision_o,lease_violation_o,
  output logic req_o,req_line_o,output logic [1:0] req_context_o,
  output logic response_o,response_line_o,output logic [1:0] response_context_o,
  output logic [1023:0] response_data_o,
  output logic line_write_o,line_index_o,launch_o,
  output logic [1023:0] line_data_o,output logic [2:0] state_o);
  wire rq,rl,rv,rrl,lw,li,la,co,lv;
  wire [1:0] rc,rrc,slots,bs;
  wire [2:0] st;
  wire [1023:0] rd,ld;
  gpr_prefetch_shell #(.borrow_p(0)) reference(.*,.req_o(rq),.req_line_o(rl),.req_context_o(rc),
    .response_o(rv),.response_line_o(rrl),.response_context_o(rrc),.response_data_o(rd),
    .line_write_o(lw),.line_index_o(li),.launch_o(la),.line_data_o(ld),.slot_valid_o(slots),
    .state_o(st),.collision_o(co),.lease_violation_o(lv));
  wire cc,cl;
  gpr_prefetch_shell #(.borrow_p(1),.negative_p(negative_p)) candidate(.*,
    .slot_valid_o(bs),.collision_o(cc),.lease_violation_o(cl));
  assign collision_o=co|cc;
  assign lease_violation_o=lv|cl;
  assign mismatch_o=({req_o,req_line_o,req_context_o,response_o,response_line_o,response_context_o,
    line_write_o,line_index_o,launch_o,bs,state_o}!=={rq,rl,rc,rv,rrl,rrc,lw,li,la,slots,st})
    ||(response_o&&(response_data_o!==rd))||(line_write_o&&(line_data_o!==ld));
endmodule
