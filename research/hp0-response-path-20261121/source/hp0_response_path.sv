`ifndef BP_AXI_RESPONSE_DELAY
`define BP_AXI_RESPONSE_DELAY 0
`endif
module hp0_response_path #(parameter bit RETAINED=1, BYPASS=0)
 (input logic aclk,aresetn,hp0_axi_rvalid,hp0_axi_bvalid,consume_rready,consume_bready,
  input logic [63:0] hp0_axi_rdata, input logic [5:0] hp0_axi_rid,hp0_axi_bid,
  input logic [1:0] hp0_axi_rresp,hp0_axi_bresp, input logic hp0_axi_rlast,
  output logic hp0_axi_rready,hp0_axi_bready,rvalid_o,bvalid_o,
  output logic [63:0] rdata_o, output logic [5:0] rid_o,bid_o,
  output logic [1:0] rresp_o,bresp_o, output logic rlast_o);
 localparam C_HP0_AXI_DATA_WIDTH=64;
 localparam retained_buffer_p=RETAINED, prefetch_axi_bypass_lp=BYPASS;
 wire unused_native_inputs = &{1'b0,aclk,aresetn};
   localparam integer axi_response_delay_lp = `BP_AXI_RESPONSE_DELAY;
   // One common return path, BEFORE blackparrot's ordinary/prefetch ID demux.
   // All I/D demand and prefetch responses that reach HP0 share this setting.
   // AR/AW/W and all cache geometry remain unchanged. Queue reset is the AXI
   // transaction-domain reset, never a live BP/control reset or drain command.
   logic bp_hp0_bvalid, bp_hp0_bready;
   logic [5:0] bp_hp0_bid;
   logic [1:0] bp_hp0_bresp;
   logic bp_hp0_rvalid, bp_hp0_rready, bp_hp0_rlast;
   logic [5:0] bp_hp0_rid;
   logic [C_HP0_AXI_DATA_WIDTH-1:0] bp_hp0_rdata;
   logic [1:0] bp_hp0_rresp;

   initial begin
      if (axi_response_delay_lp < 0 || axi_response_delay_lp > 384)
        $fatal(1,"BP_AXI_RESPONSE_DELAY must be in 0..384");
      // A direct DRAM prefetch can miss dirty allocating-L2 data. Retaining
      // that reply would turn an old advisory preview into stale demand data.
      if (retained_buffer_p && prefetch_axi_bypass_lp)
        $fatal(1,"retained full-line stores require allocating L2; disable prefetch AXI bypass");
   end

   if (axi_response_delay_lp == 0) begin : hp0_native_response
      assign bp_hp0_rvalid = hp0_axi_rvalid;
      assign {bp_hp0_rid, bp_hp0_rdata, bp_hp0_rresp, bp_hp0_rlast}
        = {hp0_axi_rid, hp0_axi_rdata, hp0_axi_rresp, hp0_axi_rlast};
      assign hp0_axi_rready = bp_hp0_rready;
      assign bp_hp0_bvalid = hp0_axi_bvalid;
      assign {bp_hp0_bid, bp_hp0_bresp} = {hp0_axi_bid, hp0_axi_bresp};
      assign hp0_axi_bready = bp_hp0_bready;
   end else begin : hp0_delayed_response
      // These trace-visible quantities measure return-queue occupancy/stalls,
      // not CPU stalls or DRAM service time. No runtime configuration exists.
      logic cfg_ready, cfg_accepted, cfg_error, idle;
      logic [8:0] active_delay;
      logic [31:0] cycle_count, r_full_stall_cycles, b_full_stall_cycles;
      logic [9:0] r_occupancy, b_occupancy;
      logic r_full, b_full;
      bp_axi_response_delay
       #(.r_payload_width_p(C_HP0_AXI_DATA_WIDTH+9), .b_payload_width_p(8)
         ,.max_delay_p(384), .fifo_els_p(512), .cycle_width_p(32)
         ,.reset_delay_p(axi_response_delay_lp)) return_delay
        (.clk_i(aclk), .reset_i(~aresetn)
         ,.cfg_v_i(1'b0), .cfg_safe_i(1'b0), .cfg_delay_i('0)
         ,.cfg_ready_o(cfg_ready), .cfg_accepted_o(cfg_accepted), .cfg_error_o(cfg_error)
         ,.idle_o(idle), .active_delay_o(active_delay), .cycle_o(cycle_count)
         ,.r_v_i(hp0_axi_rvalid), .r_ready_o(hp0_axi_rready)
         ,.r_payload_i({hp0_axi_rid,hp0_axi_rdata,hp0_axi_rresp,hp0_axi_rlast})
         ,.r_v_o(bp_hp0_rvalid), .r_ready_i(bp_hp0_rready)
         ,.r_payload_o({bp_hp0_rid,bp_hp0_rdata,bp_hp0_rresp,bp_hp0_rlast})
         ,.b_v_i(hp0_axi_bvalid), .b_ready_o(hp0_axi_bready)
         ,.b_payload_i({hp0_axi_bid,hp0_axi_bresp})
         ,.b_v_o(bp_hp0_bvalid), .b_ready_i(bp_hp0_bready)
         ,.b_payload_o({bp_hp0_bid,bp_hp0_bresp})
         ,.r_occupancy_o(r_occupancy), .b_occupancy_o(b_occupancy)
         ,.r_full_o(r_full), .b_full_o(b_full)
         ,.r_full_stall_cycles_o(r_full_stall_cycles)
         ,.b_full_stall_cycles_o(b_full_stall_cycles));
      wire unused_status = &{1'b0,cfg_ready,cfg_accepted,cfg_error,idle,active_delay,
                              cycle_count,r_occupancy,b_occupancy,r_full,b_full,
                              r_full_stall_cycles,b_full_stall_cycles};
   end
   assign bp_hp0_rready=consume_rready,bp_hp0_bready=consume_bready;
assign rvalid_o=bp_hp0_rvalid,bvalid_o=bp_hp0_bvalid;
assign rdata_o=bp_hp0_rdata,rid_o=bp_hp0_rid,rresp_o=bp_hp0_rresp,rlast_o=bp_hp0_rlast;
assign bid_o=bp_hp0_bid,bresp_o=bp_hp0_bresp;
endmodule
