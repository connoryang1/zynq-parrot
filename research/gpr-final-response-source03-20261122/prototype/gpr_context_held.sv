module gpr_context_held
 (input logic clk_i,reset_i,input logic [1:0] w_v_i,
  input logic [1:0][1:0] w_context_i,input logic [1:0][4:0] w_reg_i,
  input logic [1:0][63:0] w_data_i,input logic r_v_i,
  input logic [1:0] r_context_i,input logic r_line_i,
  output logic r_v_o,output logic [1:0] r_context_o,
  output logic r_line_o,output logic [1023:0] r_data_o,
  output logic [1023:0] held_raw_o,output logic [15:0] held_valid_o,
  output logic collision_o);
  logic [3:0][31:0] valid_r;
  wire port_sel=w_v_i[1];
  wire [1:0] wc=w_context_i[port_sel];
  wire [4:0] wr=w_reg_i[port_sel];
  assign collision_o=(|w_v_i)&&r_v_i&&({wc,wr[4]}=={r_context_i,r_line_i});
  for(genvar k=0;k<16;k++)begin:lane
    (* ram_style="block" *) logic [63:0] payload_ram[8];
    // Canonical independent synchronous 1R1W. The read-port enable holds
    // its actual response across idle/writes, NOT an extra bypass/hold latch.
    // Inference/mapped primitive mode/hold must still be measured/qualified.
    always_ff @(posedge clk_i)begin
      if((|w_v_i)&&(wr[3:0]==4'(k)))payload_ram[{wc,wr[4]}]<=w_data_i[port_sel];
      if(r_v_i)held_raw_o[64*k+:64]<=payload_ram[{r_context_i,r_line_i}];
    end
    assign r_data_o[64*k+:64]=held_valid_o[k]?held_raw_o[64*k+:64]:64'd0;
  end
  always_ff @(posedge clk_i)begin
    if(reset_i)begin
      valid_r<='0;r_v_o<=0;r_context_o<='0;r_line_o<=0;held_valid_o<='0;
    end else begin
      r_v_o<=r_v_i;
      if(r_v_i)begin
        r_context_o<=r_context_i;r_line_o<=r_line_i;
        for(int k=0;k<16;k++)held_valid_o[k]<=valid_r[r_context_i][{r_line_i,4'(k)}];
      end
      if(|w_v_i)valid_r[wc][wr]<=1;
    end
  end
endmodule
