/* Canonical no-reset single-write/two-asynchronous-read epoch storage.
 * The owning controller supplies the existing clear sweep and invalidation
 * priority. No initialization, policy, latency or additional BRAM is implied.
 */
module bp_retained_epoch_ram
 #(parameter int unsigned sets_p = 256
   , parameter int unsigned width_p = 8
   , localparam int addr_width_lp = (sets_p > 1) ? $clog2(sets_p) : 1
   )
  (input logic clk_i
   , input logic write_v_i
   , input logic [addr_width_lp-1:0] write_addr_i
   , input logic [width_p-1:0] write_data_i
   , input logic [addr_width_lp-1:0] read_addr_i, invalidate_addr_i
   , output logic [width_p-1:0] read_data_o, invalidate_data_o
   );
  (* ram_style = "distributed" *) logic [width_p-1:0] mem [sets_p];
  assign read_data_o = mem[read_addr_i];
  assign invalidate_data_o = mem[invalidate_addr_i];
  always_ff @(posedge clk_i)
    if (write_v_i) mem[write_addr_i] <= write_data_i;
endmodule
