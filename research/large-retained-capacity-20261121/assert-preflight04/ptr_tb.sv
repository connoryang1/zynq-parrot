// Exact unchanged BaseJump nonpower-of-two pointer, independent of retention.
module ptr_tb(input clk_i, reset_i, add_i, output [1:0] ptr_o, next_o);
  bsg_circular_ptr #(.slots_p(3), .max_add_p(1)) dut
    (.clk(clk_i),.reset_i(reset_i),.add_i(add_i),.o(ptr_o),.n_o(next_o));
endmodule
