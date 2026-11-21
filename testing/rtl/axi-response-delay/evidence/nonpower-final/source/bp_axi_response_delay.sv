/*
 * Response-stream delay, not a memory-latency model. Place once on the COMMON
 * R/B return path before demand/prefetch demultiplexing. Payloads are opaque:
 * all IDs, data, response codes and LAST bits retain input order and contents.
 * N=0 is a combinational native wire, including ready/backpressure.
 *
 * With N>0, each accepted beat becomes eligible N response-clock cycles later.
 * Independent timestamped R/B BRAM rings preserve one-beat/clock throughput
 * after filling; N is not restarted for each serial word. Full rings may
 * backpressure input and report those cycles. Queueing/downstream stalls are
 * additional observed costs, not silently included in a claimed DRAM latency.
 *
 * Configuration changes only when both response streams are empty/quiescent
 * AND cfg_safe_i proves external AR/AW outstanding work has drained. Rejected
 * commands retain the old level and all data. Reset flushes queues as AXI reset;
 * it must reset the transaction domain, not serve as a live-data drain command.
 */
module bp_axi_response_delay
 #(parameter int unsigned r_payload_width_p = 73
   , parameter int unsigned b_payload_width_p = 8
   , parameter int unsigned max_delay_p = 384
   , parameter int unsigned fifo_els_p = 512
   , parameter int unsigned cycle_width_p = 32
   , parameter int unsigned reset_delay_p = 0
   , parameter logic [cycle_width_p-1:0] cycle_init_p = '0
   , localparam int delay_width_lp = (max_delay_p > 0) ? $clog2(max_delay_p+1) : 1
   , localparam int count_width_lp = $clog2(fifo_els_p+1)
   )
  (input logic clk_i, reset_i
   , input logic cfg_v_i, cfg_safe_i
   , input logic [delay_width_lp-1:0] cfg_delay_i
   , output logic cfg_ready_o, cfg_accepted_o, cfg_error_o, idle_o
   , output logic [delay_width_lp-1:0] active_delay_o
   , output logic [cycle_width_p-1:0] cycle_o

   , input logic r_v_i
   , output logic r_ready_o
   , input logic [r_payload_width_p-1:0] r_payload_i
   , output logic r_v_o
   , input logic r_ready_i
   , output logic [r_payload_width_p-1:0] r_payload_o
   , input logic b_v_i
   , output logic b_ready_o
   , input logic [b_payload_width_p-1:0] b_payload_i
   , output logic b_v_o
   , input logic b_ready_i
   , output logic [b_payload_width_p-1:0] b_payload_o

   , output logic [count_width_lp-1:0] r_occupancy_o, b_occupancy_o
   , output logic r_full_o, b_full_o
   , output logic [31:0] r_full_stall_cycles_o, b_full_stall_cycles_o
   );

  logic [delay_width_lp-1:0] delay_r;
  logic [cycle_width_p-1:0] cycle_r;
  logic rq_v, rq_ready, bq_v, bq_ready;
  logic [r_payload_width_p-1:0] rq_payload;
  logic [b_payload_width_p-1:0] bq_payload;
  wire native = (delay_r == 0);
  assign active_delay_o = delay_r;
  assign cycle_o = cycle_r;
  assign idle_o = (r_occupancy_o == 0) && (b_occupancy_o == 0) && !r_v_i && !b_v_i;
  assign cfg_ready_o = idle_o && cfg_safe_i && !reset_i;
  wire cfg_commit = cfg_v_i && cfg_ready_o && (cfg_delay_i <= delay_width_lp'(max_delay_p));

  assign r_v_o = native ? r_v_i : rq_v;
  assign r_payload_o = native ? r_payload_i : rq_payload;
  assign r_ready_o = native ? r_ready_i : rq_ready;
  assign b_v_o = native ? b_v_i : bq_v;
  assign b_payload_o = native ? b_payload_i : bq_payload;
  assign b_ready_o = native ? b_ready_i : bq_ready;

  bp_axi_response_delay_fifo
   #(.payload_width_p(r_payload_width_p), .fifo_els_p(fifo_els_p)
     ,.cycle_width_p(cycle_width_p), .delay_width_p(delay_width_lp)) r_fifo
    (.clk_i(clk_i), .reset_i(reset_i), .cycle_i(cycle_r), .delay_i(delay_r)
     ,.v_i(r_v_i && !native), .ready_o(rq_ready), .payload_i(r_payload_i)
     ,.v_o(rq_v), .ready_i(r_ready_i && !native), .payload_o(rq_payload)
     ,.count_o(r_occupancy_o), .full_o(r_full_o));
  bp_axi_response_delay_fifo
   #(.payload_width_p(b_payload_width_p), .fifo_els_p(fifo_els_p)
     ,.cycle_width_p(cycle_width_p), .delay_width_p(delay_width_lp)) b_fifo
    (.clk_i(clk_i), .reset_i(reset_i), .cycle_i(cycle_r), .delay_i(delay_r)
     ,.v_i(b_v_i && !native), .ready_o(bq_ready), .payload_i(b_payload_i)
     ,.v_o(bq_v), .ready_i(b_ready_i && !native), .payload_o(bq_payload)
     ,.count_o(b_occupancy_o), .full_o(b_full_o));

  always_ff @(posedge clk_i) begin
    if (reset_i) begin
      cycle_r <= cycle_init_p; delay_r <= delay_width_lp'(reset_delay_p);
      cfg_accepted_o <= 1'b0; cfg_error_o <= 1'b0;
      r_full_stall_cycles_o <= '0; b_full_stall_cycles_o <= '0;
    end else begin
      cycle_r <= cycle_r + 1'b1; cfg_accepted_o <= cfg_commit;
      if (cfg_commit) begin
        delay_r <= cfg_delay_i; cfg_error_o <= 1'b0;
        r_full_stall_cycles_o <= '0; b_full_stall_cycles_o <= '0;
      end else begin
        if (cfg_v_i) cfg_error_o <= 1'b1;
        if (!native && r_v_i && !r_ready_o && !(&r_full_stall_cycles_o))
          r_full_stall_cycles_o <= r_full_stall_cycles_o + 1'b1;
        if (!native && b_v_i && !b_ready_o && !(&b_full_stall_cycles_o))
          b_full_stall_cycles_o <= b_full_stall_cycles_o + 1'b1;
      end
    end
  end

  always @(posedge clk_i) if (!reset_i) begin
    if (native) assert ((r_occupancy_o == 0) && (b_occupancy_o == 0))
      else $fatal(1,"native bypass selected with queued responses");
  end
  initial begin
    assert (reset_delay_p <= max_delay_p && cycle_width_p > delay_width_lp)
      else $fatal(1,"invalid AXI response-delay range/counter configuration");
  end
endmodule
