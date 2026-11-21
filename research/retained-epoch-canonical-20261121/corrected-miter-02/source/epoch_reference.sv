/* Exact BP225 dense-D epoch writer/read shape, isolated for paired inference.
 * Outer controller supplies state_is_clear and clear_now (clear or wrap).
 */
module epoch_reference
 #(parameter int unsigned sets_p=256, width_p=8
   , localparam int addr_width_lp=(sets_p>1)?$clog2(sets_p):1)
  (input logic clk_i, reset_i, state_is_clear_i, clear_now_i, invalidate_v_i
   , input logic [addr_width_lp-1:0] clear_set_i, inv_set_i, read_set_i
   , output logic [width_p-1:0] line_epoch_o, inv_epoch_o);
  (* ram_style = "distributed" *) logic [width_p-1:0] epochs_r [sets_p];
  assign line_epoch_o=epochs_r[read_set_i];
  assign inv_epoch_o=epochs_r[inv_set_i];
  always_ff @(posedge clk_i) begin
    if (!reset_i) begin
      if (state_is_clear_i) epochs_r[clear_set_i] <= '0;
      else if (!clear_now_i && invalidate_v_i)
        epochs_r[inv_set_i] <= epochs_r[inv_set_i] + 1'b1;
    end
  end
endmodule
