// Ring slots remain occupied until OUTPUT acceptance. Head and next registers
// mirror ring contents; they do not advertise storage beyond fifo_els_p. A
// synchronous RAM read fetches the next-next slot while consuming the head.
// Write forwarding handles one/two-entry cases without read/write collisions,
// so N=1 and sustained streams do not incur a per-beat bubble.
module bp_axi_response_delay_fifo
 #(parameter int unsigned payload_width_p = 73
   , parameter int unsigned fifo_els_p = 512
   , parameter int unsigned cycle_width_p = 32
   , parameter int unsigned delay_width_p = 9
   , localparam int ptr_width_lp = (fifo_els_p > 1) ? $clog2(fifo_els_p) : 1
   , localparam int count_width_lp = $clog2(fifo_els_p+1)
   )
  (input logic clk_i, reset_i
   , input logic [cycle_width_p-1:0] cycle_i
   , input logic [delay_width_p-1:0] delay_i
   , input logic v_i
   , output logic ready_o
   , input logic [payload_width_p-1:0] payload_i
   , output logic v_o
   , input logic ready_i
   , output logic [payload_width_p-1:0] payload_o
   , output logic [count_width_lp-1:0] count_o
   , output logic full_o
   );
  localparam int entry_width_lp = cycle_width_p + payload_width_p;
  /* verilator tracing_off */
  (* ram_style = "block" *) logic [entry_width_lp-1:0] mem [fifo_els_p];
  /* verilator tracing_on */
  logic [ptr_width_lp-1:0] rptr_r, wptr_r;
  logic [count_width_lp-1:0] count_r;
  logic [entry_width_lp-1:0] head_r, ram_q, forward_r;
  logic head_v_r, next_v_r, next_forward_r, eligible_r;
  wire [entry_width_lp-1:0] entry = {cycle_i,payload_i};
  wire [entry_width_lp-1:0] next_entry = next_forward_r ? forward_r : ram_q;
  wire [cycle_width_p-1:0] head_time = head_r[entry_width_lp-1:payload_width_p];
  // Subtract enqueue time, not an unsigned future deadline. Across a32-bit
  // wrap this cannot make a young entry eligible early. Once eligible, latch
  // that fact so VALID never falls during arbitrarily long head backpressure.
  wire age_done = eligible_r || ((cycle_i - head_time) >= cycle_width_p'(delay_i));
  assign v_o = head_v_r && age_done && !reset_i;
  assign payload_o = head_r[payload_width_p-1:0];
  assign count_o = count_r;
  assign full_o = (count_r == count_width_lp'(fifo_els_p));
  wire pop = v_o && ready_i;
  assign ready_o = (!full_o || pop) && !reset_i;
  wire push = v_i && ready_o;
  function automatic logic [ptr_width_lp-1:0] advance(input logic [ptr_width_lp-1:0] ptr);
    return (ptr == ptr_width_lp'(fifo_els_p-1)) ? '0 : ptr + 1'b1;
  endfunction
  wire read_v = pop && (count_r > count_width_lp'(2));
  wire [ptr_width_lp-1:0] read_addr = advance(advance(rptr_r));

  // Single-clock simple dual-port BRAM: one write and one registered read.
  // No memory reset, asynchronous read, or write/read collision forwarding
  // inside the RAM process; the small external bypass is independent of depth.
  always_ff @(posedge clk_i) begin
    if (push) mem[wptr_r] <= entry;
    if (read_v) ram_q <= mem[read_addr];
  end

  always_ff @(posedge clk_i) begin
    if (reset_i) begin
      rptr_r <= '0; wptr_r <= '0; count_r <= '0;
      head_v_r <= 1'b0; next_v_r <= 1'b0; next_forward_r <= 1'b0; eligible_r <= 1'b0;
    end else begin
      if (push) wptr_r <= advance(wptr_r);
      if (pop) rptr_r <= advance(rptr_r);
      case ({push,pop})
        2'b10: count_r <= count_r + 1'b1;
        2'b01: count_r <= count_r - 1'b1;
        default: begin end
      endcase
      if (pop) begin
        eligible_r <= 1'b0;
        if (count_r > count_width_lp'(1)) begin head_r <= next_entry; head_v_r <= 1'b1; end
        else if (push) begin head_r <= entry; head_v_r <= 1'b1; end
        else head_v_r <= 1'b0;
      end else if ((count_r == 0) && push) begin
        head_r <= entry; head_v_r <= 1'b1; eligible_r <= 1'b0;
      end else if (head_v_r && age_done) eligible_r <= 1'b1;

      if (pop) begin
        if (count_r > count_width_lp'(2)) begin next_v_r <= 1'b1; next_forward_r <= 1'b0; end
        else if ((count_r == count_width_lp'(2)) && push) begin
          forward_r <= entry; next_v_r <= 1'b1; next_forward_r <= 1'b1;
        end else next_v_r <= 1'b0;
      end else if ((count_r == count_width_lp'(1)) && push) begin
        forward_r <= entry; next_v_r <= 1'b1; next_forward_r <= 1'b1;
      end
    end
  end

  always @(posedge clk_i) if (!reset_i) begin
    if (push && full_o) assert (pop) else $fatal(1,"response FIFO accepted into a full ring without pop");
    assert (head_v_r == (count_r != 0)) else $fatal(1,"response FIFO head ownership mismatch");
    assert (next_v_r == (count_r > count_width_lp'(1))) else $fatal(1,"response FIFO prefetch ownership mismatch");
    if (read_v && push) assert (read_addr != wptr_r) else $fatal(1,"response FIFO read/write collision");
    if (pop) assert (count_r != 0) else $fatal(1,"response FIFO underflow");
  end
  // At depth2^k-1 the k-bit count's entire range is legal, so a numerical
  // upper-bound assertion is tautological. Ownership/full-accept checks above
  // remain active; other depths also check representable out-of-range counts.
  if ((fifo_els_p & (fifo_els_p+1)) != 0) begin : count_range_check
    always @(posedge clk_i) if (!reset_i)
      assert (count_r <= count_width_lp'(fifo_els_p)) else $fatal(1,"response FIFO overflow");
  end
  initial assert (fifo_els_p >= 2) else $fatal(1,"response FIFO requires at least two slots");
endmodule
