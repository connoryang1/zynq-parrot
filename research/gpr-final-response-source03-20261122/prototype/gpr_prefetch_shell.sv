// Extracted production no-FP handoff envelope, not a replacement whole BE.
// bp_be_top:466-470,500-533,1023-1090,1144-1215,1239-1264.
module gpr_prefetch_shell #(parameter bit borrow_p=0,parameter int negative_p=0)
 (input logic clk_i,reset_i,miss_i,commit_i,redirect_i,drain_i,dirty_i,fe_yumi_i,
  input logic [1:0] target_i,input logic [1:0] w_v_i,
  input logic [1:0][1:0] w_context_i,input logic [1:0][4:0] w_reg_i,
  input logic [1:0][63:0] w_data_i,
  output logic req_o,req_line_o,output logic [1:0] req_context_o,
  output logic response_o,response_line_o,output logic [1:0] response_context_o,
  output logic [1023:0] response_data_o,
  output logic line_write_o,line_index_o,launch_o,
  output logic [1023:0] line_data_o,
  output logic [1:0] slot_valid_o,output logic [2:0] state_o,
  output logic collision_o,lease_violation_o);
  localparam logic [2:0] idle=0,wait_commit=1,wait_drain=2,save_restore=3,launch_fe=4,done=5;
  logic [2:0] state_r;
  logic [1:0] target_r,line_v_r;
  logic issue_done_r,issue_line_r,install_line_r;
  logic [1023:0] first_line_r;
  // Elaboration removes this entirely in the borrowed candidate.
  if(!borrow_p)begin:old_copy
    logic [1023:0] second_line_r;
    gpr_context_reference mem(.*,.r_v_i(req_o),.r_context_i(req_context_o),.r_line_i(req_line_o),
      .r_v_o(response_o),.r_context_o(response_context_o),.r_line_o(response_line_o),.r_data_o(response_data_o));
    always_ff @(posedge clk_i)
      if(reset_i)second_line_r<='0;
      else if(response_o&&response_line_o)second_line_r<=response_data_o;
    assign line_data_o=install_line_r?second_line_r:first_line_r;
  end else begin:borrow_final
    wire [1023:0] raw;
    wire [15:0] mask;
    gpr_context_held mem(.*,.r_v_i(req_o),.r_context_i(req_context_o),.r_line_i(req_line_o),
      .r_v_o(response_o),.r_context_o(response_context_o),.r_line_o(response_line_o),
      .r_data_o(response_data_o),.held_raw_o(raw),.held_valid_o(mask));
    wire [15:0] effective_mask=mask ^ ((negative_p==2&&install_line_r)?16'h8000:16'd0);
    for(genvar k=0;k<16;k++)begin:out_lane
      wire [63:0] value=effective_mask[k]?raw[64*k+:64]:64'd0;
      assign line_data_o[64*k+:64]=install_line_r
        ?value ^ ((negative_p==1&&k==15)?64'h8000_0000_0000_0000:64'd0)
        :first_line_r[64*k+:64];
    end
  end
  assign req_o=((state_r==wait_commit)||(state_r==wait_drain))&&!issue_done_r;
  assign req_context_o=target_r;assign req_line_o=issue_line_r;
  assign line_write_o=((state_r==save_restore)||((state_r==wait_drain)&&drain_i&&dirty_i))&&line_v_r[install_line_r];
  assign line_index_o=install_line_r;
  assign launch_o=(state_r==launch_fe)||((state_r==save_restore)&&line_v_r[install_line_r]&&install_line_r);
  assign state_o=state_r;assign slot_valid_o=line_v_r;
  // A new read while line1 remains leased is forbidden. Reset, abort or
  // completed final use explicitly terminates that ownership interval.
  logic final_lease_r;
  assign lease_violation_o=req_o&&final_lease_r;
  always_ff @(posedge clk_i)begin
    if(reset_i)begin
      state_r<=idle;target_r<='0;issue_done_r<=0;issue_line_r<=0;
      install_line_r<=0;line_v_r<='0;first_line_r<='0;final_lease_r<=0;
    end else begin
      if(response_o)begin
        line_v_r[response_line_o]<=1;
        if(!response_line_o)first_line_r<=response_data_o;
        else final_lease_r<=1;
      end
      if(req_o)begin if(req_line_o)issue_done_r<=1;else issue_line_r<=1;end
      if(line_write_o&&install_line_r)final_lease_r<=0;
      case(state_r)
        idle:if(miss_i)begin
          state_r<=wait_commit;target_r<=target_i;issue_done_r<=0;issue_line_r<=0;
          install_line_r<=0;line_v_r<='0;final_lease_r<=0;
        end
        wait_commit:if(commit_i)state_r<=wait_drain;
          else if(redirect_i)begin state_r<=idle;final_lease_r<=0;end
        wait_drain:begin
          if(line_write_o)install_line_r<=install_line_r+1'b1;
          if(drain_i)state_r<=dirty_i?save_restore:launch_fe;
        end
        save_restore:if(line_write_o)begin
          if(install_line_r)state_r<=fe_yumi_i?done:launch_fe;
          else install_line_r<=1;
        end
        launch_fe:if(fe_yumi_i)state_r<=done;
        done:state_r<=idle;
        default:state_r<=idle;
      endcase
    end
  end
endmodule

