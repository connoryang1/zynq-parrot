/* Simulation-only AXI memory with overlapping read service intervals.
 *
 * Each accepted AR starts its own fixed-latency service interval immediately.
 * A bounded queue preserves global response order; completed requests can wait
 * for older bursts or RREADY without restarting their latency. R payloads are
 * registered and remain stable under backpressure, including concurrent writes.
 * Storage initialization and byte-strobe behavior follow the existing BaseJump
 * bsg_nonsynth_axi_mem model; this module does not modify that dependency.
 * Aligned FIXED/INCR/WRAP bursts, including narrow transfers, are supported.
 * Unsupported or malformed transactions fail explicitly instead of aliasing RAM.
 */
module bp_nonsynth_axi_mem_pipelined
  #(parameter int axi_id_width_p = 6
    , parameter int axi_addr_width_p = 32
    , parameter int axi_data_width_p = 64
    , parameter int axi_len_width_p = 8
    , parameter int mem_els_p = 1024
    , parameter logic [31:0] init_data_p = 32'hdead_beef
    , parameter int read_latency_p = 40
    , parameter int read_queue_els_p = 4
    , localparam int strb_width_lp = axi_data_width_p / 8
    , localparam int ram_index_width_lp = mem_els_p > 1 ? $clog2(mem_els_p) : 1
    )
  (input logic clk_i, reset_i
   , input logic [axi_id_width_p-1:0] axi_awid_i
   , input logic [axi_addr_width_p-1:0] axi_awaddr_i
   , input logic [axi_len_width_p-1:0] axi_awlen_i
   , input logic [2:0] axi_awsize_i
   , input logic [1:0] axi_awburst_i
   , input logic axi_awvalid_i
   , output logic axi_awready_o
   , input logic [axi_data_width_p-1:0] axi_wdata_i
   , input logic [strb_width_lp-1:0] axi_wstrb_i
   , input logic axi_wlast_i, axi_wvalid_i
   , output logic axi_wready_o
   , output logic [axi_id_width_p-1:0] axi_bid_o
   , output logic [1:0] axi_bresp_o
   , output logic axi_bvalid_o
   , input logic axi_bready_i
   , input logic [axi_id_width_p-1:0] axi_arid_i
   , input logic [axi_addr_width_p-1:0] axi_araddr_i
   , input logic [axi_len_width_p-1:0] axi_arlen_i
   , input logic [2:0] axi_arsize_i
   , input logic [1:0] axi_arburst_i
   , input logic axi_arvalid_i
   , output logic axi_arready_o
   , output logic [axi_id_width_p-1:0] axi_rid_o
   , output logic [axi_data_width_p-1:0] axi_rdata_o
   , output logic [1:0] axi_rresp_o
   , output logic axi_rlast_o, axi_rvalid_o
   , input logic axi_rready_i
   );

  logic [axi_data_width_p-1:0] ram [mem_els_p];
  typedef struct packed {
    logic [axi_id_width_p-1:0] id;
    logic [axi_addr_width_p-1:0] addr;
    logic [axi_len_width_p-1:0] len;
    logic [2:0] size;
    logic [1:0] burst;
    logic [63:0] due;
  } read_request_s;
  read_request_s read_queue_r [read_queue_els_p];
  int unsigned read_head_r, read_tail_r, read_count_r, read_beat_r;
  logic [63:0] cycle_r;

  logic write_active_r;
  logic [axi_id_width_p-1:0] write_id_r;
  logic [axi_addr_width_p-1:0] write_addr_r;
  logic [axi_len_width_p-1:0] write_len_r;
  logic [2:0] write_size_r;
  logic [1:0] write_burst_r;
  int unsigned write_beat_r;

  wire ar_accept = axi_arvalid_i && axi_arready_o;
  wire r_finish = axi_rvalid_o && axi_rready_i && axi_rlast_o;
  wire aw_accept = axi_awvalid_i && axi_awready_o;
  wire w_accept = axi_wvalid_i && axi_wready_o;
  assign axi_arready_o = !reset_i && (read_count_r < read_queue_els_p);
  assign axi_awready_o = !reset_i && !write_active_r && !axi_bvalid_o;
  assign axi_wready_o = !reset_i && write_active_r;
  assign axi_bresp_o = 2'b00;
  assign axi_rresp_o = 2'b00;

  function automatic int unsigned next_slot(input int unsigned slot);
    return slot == read_queue_els_p - 1 ? 0 : slot + 1;
  endfunction

  function automatic logic [63:0] beat_address
    (input logic [axi_addr_width_p-1:0] start
     , input logic [axi_len_width_p-1:0] len
     , input logic [2:0] size
     , input logic [1:0] burst
     , input int unsigned beat);
    logic [63:0] step, span, increment, boundary;
    step = 64'd1 << size;
    span = step * (64'(len) + 1);
    increment = 64'(start) + 64'(beat) * step;
    boundary = 64'(start) & ~(span - 1);
    case (burst)
      2'b00: return 64'(start);
      2'b01: return increment;
      2'b10: return boundary | (increment & (span - 1));
      default: return '0;
    endcase
  endfunction

  // Reads sample RAM when a beat enters the output register. Writes committed
  // on that same edge become visible to later samples, not to an already
  // asserted or stalled R beat. This is the model's read/write collision rule.
  function automatic logic [axi_data_width_p-1:0] read_word(input logic [63:0] address);
    logic [axi_data_width_p-1:0] value;
    value = ram[ram_index_width_lp'((address / 64'(strb_width_lp)) & (mem_els_p-1))];
    for (int bit_index = 0; bit_index < axi_data_width_p; bit_index++)
      if (value[bit_index] === 1'bx)
        value[bit_index] = init_data_p[bit_index % 32];
    return value;
  endfunction

  task automatic check_address
    (input logic [axi_addr_width_p-1:0] address
     , input logic [axi_len_width_p-1:0] len
     , input logic [2:0] size
     , input logic [1:0] burst);
    logic [63:0] step, span;
    step = 64'd1 << size;
    span = step * (64'(len) + 1);
    if (step > 64'(strb_width_lp) || (64'(address) & (step - 1)) != 0)
      $fatal(1, "AXI memory requires aligned transfers no wider than the data bus");
    if (burst == 2'b11)
      $fatal(1, "AXI memory received reserved burst type");
    if (burst == 2'b00 && len > 15)
      $fatal(1, "AXI FIXED burst exceeds sixteen beats");
    if (burst == 2'b10 && !(len inside {1, 3, 7, 15}))
      $fatal(1, "AXI WRAP burst requires 2, 4, 8, or 16 beats");
    if (burst == 2'b01 && (64'(address) % 4096) + span > 4096)
      $fatal(1, "AXI INCR burst crosses a 4 KiB boundary: addr=%h len=%0d size=%0d burst=%0d bytes=%0d",
             address, len, size, burst, span);
    // The standard nonsynthesizable model aliases the physical address into
    // its finite backing store. Preserve that behavior for boot traffic while
    // retaining alignment and burst-shape checks above.
  endtask

  initial begin
    if (read_queue_els_p < 2 || read_latency_p < 2 || mem_els_p < 1
        || (mem_els_p & (mem_els_p - 1)) != 0
        || axi_data_width_p < 32 || (axi_data_width_p % 32) != 0
        || (strb_width_lp & (strb_width_lp - 1)) != 0 || axi_addr_width_p > 64)
      $fatal(1, "Invalid pipelined AXI memory parameters");
    $display("[BP-AXI-MEM] pipelined reads queue=%0d latency=%0d cycles from AR acceptance",
             read_queue_els_p, read_latency_p);
    // Explicit initialization is deterministic in both two-state Verilator
    // and four-state simulators. Reset clears transactions, not RAM contents.
    for (int unsigned word_index = 0; word_index < mem_els_p; word_index++)
      ram[word_index] = {(axi_data_width_p/32){init_data_p}};
  end

  always_ff @(posedge clk_i) begin : memory_state
    int unsigned selected_head, selected_beat;
    logic selected_valid;
    logic [63:0] address;
    if (reset_i) begin
      read_head_r <= 0;
      read_tail_r <= 0;
      read_count_r <= 0;
      read_beat_r <= 0;
      cycle_r <= 0;
      axi_rvalid_o <= 0;
      axi_rid_o <= '0;
      axi_rdata_o <= '0;
      axi_rlast_o <= 0;
      write_active_r <= 0;
      write_id_r <= '0;
      write_addr_r <= '0;
      write_len_r <= '0;
      write_size_r <= '0;
      write_burst_r <= '0;
      write_beat_r <= 0;
      axi_bvalid_o <= 0;
      axi_bid_o <= '0;
    end else begin
      cycle_r <= cycle_r + 1;
      case ({ar_accept, r_finish})
        2'b10: read_count_r <= read_count_r + 1;
        2'b01: read_count_r <= read_count_r - 1;
        default: begin end
      endcase
      if (ar_accept) begin
        check_address(axi_araddr_i, axi_arlen_i, axi_arsize_i, axi_arburst_i);
        read_queue_r[read_tail_r] <= '{id: axi_arid_i, addr: axi_araddr_i,
          len: axi_arlen_i, size: axi_arsize_i, burst: axi_arburst_i,
          due: cycle_r + 64'(read_latency_p)};
        read_tail_r <= next_slot(read_tail_r);
      end
      if (r_finish) read_head_r <= next_slot(read_head_r);

      // A free output register can take the next beat immediately. Eligibility
      // uses the request's absolute due cycle even while older responses stall.
      if (!axi_rvalid_o || axi_rready_i) begin
        selected_head = r_finish ? next_slot(read_head_r) : read_head_r;
        selected_valid = r_finish ? (read_count_r > 1) : (read_count_r != 0);
        selected_beat = r_finish ? 0
          : ((axi_rvalid_o && axi_rready_i) ? read_beat_r + 1 : read_beat_r);
        axi_rvalid_o <= 0;
        if (selected_valid && cycle_r + 1 >= read_queue_r[selected_head].due) begin
          address = beat_address(read_queue_r[selected_head].addr,
                                 read_queue_r[selected_head].len,
                                 read_queue_r[selected_head].size,
                                 read_queue_r[selected_head].burst, selected_beat);
          axi_rvalid_o <= 1;
          axi_rid_o <= read_queue_r[selected_head].id;
          axi_rdata_o <= read_word(address);
          axi_rlast_o <= selected_beat == int'(read_queue_r[selected_head].len);
          read_beat_r <= selected_beat;
        end else if (r_finish) begin
          read_beat_r <= 0;
        end
      end

      if (axi_bvalid_o && axi_bready_i) axi_bvalid_o <= 0;
      if (aw_accept) begin
        check_address(axi_awaddr_i, axi_awlen_i, axi_awsize_i, axi_awburst_i);
        write_active_r <= 1;
        write_id_r <= axi_awid_i;
        write_addr_r <= axi_awaddr_i;
        write_len_r <= axi_awlen_i;
        write_size_r <= axi_awsize_i;
        write_burst_r <= axi_awburst_i;
        write_beat_r <= 0;
      end
      if (w_accept) begin
        if (axi_wlast_i != (write_beat_r == int'(write_len_r)))
          $fatal(1, "AXI WLAST does not match AWLEN");
        address = beat_address(write_addr_r, write_len_r, write_size_r,
                               write_burst_r, write_beat_r);
        for (int lane = 0; lane < strb_width_lp; lane++) begin
          if (axi_wstrb_i[lane]) begin
            if (64'(lane) < address % 64'(strb_width_lp)
                || 64'(lane) >= address % 64'(strb_width_lp) + (64'd1 << write_size_r))
              $fatal(1, "AXI WSTRB selects a byte outside the narrow transfer");
            ram[ram_index_width_lp'((address / 64'(strb_width_lp)) & (mem_els_p-1))][lane*8+:8] <= axi_wdata_i[lane*8+:8];
          end
        end
        if (axi_wlast_i) begin
          write_active_r <= 0;
          axi_bvalid_o <= 1;
          axi_bid_o <= write_id_r;
        end else begin
          write_beat_r <= write_beat_r + 1;
        end
      end
    end
  end
endmodule
