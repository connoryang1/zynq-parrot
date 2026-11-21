// Optional FPGA observation, independent of software retention controls.
// Lane0 is I/positive core clock; lane1 is D/inverted core clock. Outputs are
// {D16,I16}; a saturated field is a lower bound, never a wrapping difference.
module bp_retained_use_counters
  (input [1:0] clk_i
   , input reset_i // External AXI reset ONLY, not CPU stop/tag/retention clear.
   , input bp_reset_i
   , input [1:0] hit_i, published_i, write_beat_i
   , output [31:0] hits_o, published_o, write_beats_o
   );
  for (genvar lane=0; lane<2; lane++) begin : lanes
    logic [15:0] hits_r, published_r, write_beats_r;
    always_ff @(posedge clk_i[lane] or posedge reset_i) begin
      if (reset_i) begin
        hits_r <= '0;
        published_r <= '0;
        write_beats_r <= '0;
      end else if (!bp_reset_i) begin
        if (hit_i[lane] && !(&hits_r))
          hits_r <= hits_r+16'd1;
        if (published_i[lane] && !(&published_r))
          published_r <= published_r+16'd1;
        if (write_beat_i[lane] && !(&write_beats_r))
          write_beats_r <= write_beats_r+16'd1;
      end
    end
    assign hits_o[16*lane+:16] = hits_r;
    assign published_o[16*lane+:16] = published_r;
    assign write_beats_o[16*lane+:16] = write_beats_r;
  end
endmodule
