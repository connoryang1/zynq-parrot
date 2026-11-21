module axi_response_delay_wrapper
 #(parameter int COUNTER_WIDTH = 32, parameter int FIFO_ELS = 512)
  (input logic clk_i, reset_i, cfg_v_i, cfg_safe_i
   , input logic [8:0] cfg_delay_i
   , output logic cfg_ready_o, cfg_accepted_o, cfg_error_o, idle_o
   , output logic [8:0] active_delay_o
   , output logic [31:0] cycle_o, counter_width_o, fifo_els_o
   , input logic r_v_i
   , output logic r_ready_o
   , input logic [72:0] r_payload_i
   , output logic r_v_o
   , input logic r_ready_i
   , output logic [72:0] r_payload_o
   , input logic b_v_i
   , output logic b_ready_o
   , input logic [7:0] b_payload_i
   , output logic b_v_o
   , input logic b_ready_i
   , output logic [7:0] b_payload_o
   , output logic [31:0] r_occupancy_o, b_occupancy_o
   , output logic r_full_o, b_full_o
   , output logic [31:0] r_full_stall_cycles_o, b_full_stall_cycles_o
   );
  localparam int count_width_lp = $clog2(FIFO_ELS+1);
  logic [COUNTER_WIDTH-1:0] cycle_lo;
  logic [count_width_lp-1:0] r_count_lo, b_count_lo;
  assign cycle_o = 32'(cycle_lo);
  assign r_occupancy_o = 32'(r_count_lo);
  assign b_occupancy_o = 32'(b_count_lo);
  assign counter_width_o = COUNTER_WIDTH;
  assign fifo_els_o = FIFO_ELS;
  bp_axi_response_delay
   #(.r_payload_width_p(73), .b_payload_width_p(8), .max_delay_p(384), .fifo_els_p(FIFO_ELS)
     ,.cycle_width_p(COUNTER_WIDTH), .reset_delay_p(0), .cycle_init_p({COUNTER_WIDTH{1'b1}}-COUNTER_WIDTH'(15))) dut
    (.clk_i(clk_i), .reset_i(reset_i), .cfg_v_i(cfg_v_i), .cfg_safe_i(cfg_safe_i), .cfg_delay_i(cfg_delay_i)
     ,.cfg_ready_o(cfg_ready_o), .cfg_accepted_o(cfg_accepted_o), .cfg_error_o(cfg_error_o), .idle_o(idle_o)
     ,.active_delay_o(active_delay_o), .cycle_o(cycle_lo)
     ,.r_v_i(r_v_i), .r_ready_o(r_ready_o), .r_payload_i(r_payload_i), .r_v_o(r_v_o), .r_ready_i(r_ready_i), .r_payload_o(r_payload_o)
     ,.b_v_i(b_v_i), .b_ready_o(b_ready_o), .b_payload_i(b_payload_i), .b_v_o(b_v_o), .b_ready_i(b_ready_i), .b_payload_o(b_payload_o)
     ,.r_occupancy_o(r_count_lo), .b_occupancy_o(b_count_lo), .r_full_o(r_full_o), .b_full_o(b_full_o)
     ,.r_full_stall_cycles_o(r_full_stall_cycles_o), .b_full_stall_cycles_o(b_full_stall_cycles_o));
endmodule
