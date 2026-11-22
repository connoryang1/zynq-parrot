// Exact update/priority shape extracted from bb575 bp_be_top.sv:835-914.
// Inputs are the already qualified, in-range save and conditional reseed intents.
// No architectural CSR update, privilege, or context-owner logic is moved here.
module csr_snapshot_reference
 #(parameter int contexts_p=4, width_p=1666
   , parameter int addr_width_p=(contexts_p>1)?$clog2(contexts_p):1)
  (input logic clk_i, reset_i, save_v_i, seed_v_i
   , input logic [addr_width_p-1:0] save_addr_i,seed_addr_i,read_addr_i
   , input logic [width_p-1:0] save_data_i,seed_data_i
   , output logic [contexts_p-1:0] valid_o
   , output logic read_valid_o
   , output logic [width_p-1:0] read_data_o);
  logic [contexts_p-1:0] valid_r;
  logic [contexts_p-1:0][width_p-1:0] data_r;
  always_ff @(posedge clk_i) begin
    if (reset_i) begin
      for (int i=0;i<contexts_p;i++) begin
        valid_r[i]<=1'b0; data_r[i]<='0;
      end
    end else begin
      if (save_v_i && int'(save_addr_i)<contexts_p) begin
        valid_r[save_addr_i]<=1'b1; data_r[save_addr_i]<=save_data_i;
      end
      if (seed_v_i && int'(seed_addr_i)<contexts_p) begin
        valid_r[seed_addr_i]<=1'b1; data_r[seed_addr_i]<=seed_data_i;
      end
    end
  end
  assign valid_o=valid_r;
  always_comb begin
    read_valid_o=1'b0;read_data_o='0;
    if (int'(read_addr_i)<contexts_p) begin
      read_valid_o=valid_r[read_addr_i];read_data_o=data_r[read_addr_i];
    end
  end
endmodule
