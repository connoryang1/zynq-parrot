/*
 * Convert full-line BedRock prefetch reads into bounded, independently tagged
 * AXI bursts. This gives detached UCE hints enough transport capacity to
 * overlap external memory latency without changing demand traffic.
 */

`include "bsg_defines.sv"
`include "bp_common_defines.svh"
`include "bp_me_defines.svh"

module bp_prefetch_axi_master
 import bp_common_pkg::*;
 import bp_me_pkg::*;
 #(parameter bp_params_e bp_params_p = e_bp_default_cfg
   `declare_bp_proc_params(bp_params_p)
   `declare_bp_bedrock_if_widths(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p)

   , parameter `BSG_INV_PARAM(axi_addr_width_p)
   , parameter `BSG_INV_PARAM(axi_data_width_p)
   , parameter `BSG_INV_PARAM(axi_id_width_p)
   , parameter outstanding_p = 10
   , localparam slot_width_lp = `BSG_SAFE_CLOG2(outstanding_p)
   , localparam axi_bytes_lp = axi_data_width_p / 8
   , localparam block_beats_lp = dcache_block_width_p / axi_data_width_p
   , localparam beat_count_width_lp = `BSG_SAFE_CLOG2(block_beats_lp)
   , localparam beats_per_bedrock_lp = bedrock_fill_width_p / axi_data_width_p
   , localparam subbeat_count_width_lp = `BSG_SAFE_CLOG2(beats_per_bedrock_lp)
   )
  (input                                         clk_i
   , input                                       reset_i

   , input [mem_fwd_header_width_lp-1:0]         mem_fwd_header_i
   , input [bedrock_fill_width_p-1:0]            mem_fwd_data_i
   , input                                       mem_fwd_v_i
   , output logic                                mem_fwd_ready_and_o

   , output logic [mem_rev_header_width_lp-1:0]  mem_rev_header_o
   , output logic [bedrock_fill_width_p-1:0]     mem_rev_data_o
   , output logic                                mem_rev_v_o
   , input                                       mem_rev_ready_and_i

   , output logic [axi_addr_width_p-1:0]         axi_araddr_o
   , output logic [axi_id_width_p-1:0]           axi_arid_o
   , output logic [7:0]                          axi_arlen_o
   , output logic [2:0]                          axi_arsize_o
   , output logic [1:0]                          axi_arburst_o
   , output logic                                axi_arvalid_o
   , input                                       axi_arready_i

   , input [axi_id_width_p-1:0]                  axi_rid_i
   , input [axi_data_width_p-1:0]                axi_rdata_i
   , input [1:0]                                 axi_rresp_i
   , input                                       axi_rlast_i
   , input                                       axi_rvalid_i
   , output logic                                axi_rready_o
   );

  `declare_bp_bedrock_if(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p);
  bp_bedrock_mem_fwd_header_s mem_fwd_header_cast_i;
  assign mem_fwd_header_cast_i = mem_fwd_header_i;

  logic [outstanding_p-1:0] slot_v_r;
  bp_bedrock_mem_rev_header_s slot_header_r [outstanding_p];
  logic [outstanding_p-1:0][beat_count_width_lp-1:0] slot_beat_r;
  logic [outstanding_p-1:0][subbeat_count_width_lp-1:0] slot_subbeat_r;
  logic [outstanding_p-1:0][bedrock_fill_width_p-1:0] slot_fill_data_r;

  logic free_v;
  logic [slot_width_lp-1:0] free_slot;
  always_comb begin
    free_v = 1'b0;
    free_slot = '0;
    for (int i = outstanding_p-1; i >= 0; i--)
      if (!slot_v_r[i]) begin
        free_v = 1'b1;
        free_slot = slot_width_lp'(i);
      end
  end

  assign axi_araddr_o = mem_fwd_header_cast_i.addr[0+:axi_addr_width_p];
  assign axi_arid_o = axi_id_width_p'(free_slot + 1'b1);
  assign axi_arlen_o = 8'(block_beats_lp-1);
  assign axi_arsize_o = 3'($clog2(axi_bytes_lp));
  assign axi_arburst_o = 2'b01;
  assign axi_arvalid_o = mem_fwd_v_i & free_v;
  assign mem_fwd_ready_and_o = axi_arready_i & free_v;
  wire request_accept = mem_fwd_v_i & mem_fwd_ready_and_o;

  wire response_id_valid = (axi_rid_i > 0) && (axi_rid_i <= outstanding_p);
  wire [slot_width_lp-1:0] response_slot = slot_width_lp'(axi_rid_i - 1'b1);
  logic response_slot_valid;
  bp_bedrock_mem_rev_header_s response_header;
  logic [subbeat_count_width_lp-1:0] response_subbeat;
  logic [bedrock_fill_width_p-1:0] response_fill_data;
  always_comb begin
    response_slot_valid = 1'b0;
    response_header = '0;
    response_subbeat = '0;
    response_fill_data = '0;
    if (response_id_valid) begin
      response_slot_valid = slot_v_r[response_slot];
      response_header = slot_header_r[response_slot];
      response_subbeat = slot_subbeat_r[response_slot];
      response_fill_data = slot_fill_data_r[response_slot];
    end
    response_fill_data[response_subbeat*axi_data_width_p +: axi_data_width_p] = axi_rdata_i;
  end

  assign mem_rev_header_o = response_header;
  assign mem_rev_data_o = response_fill_data;
  wire response_fill_complete = response_subbeat == beats_per_bedrock_lp-1;
  assign mem_rev_v_o = axi_rvalid_i & response_slot_valid & response_fill_complete;
  assign axi_rready_o = response_slot_valid
    & (!response_fill_complete | mem_rev_ready_and_i);
  wire response_accept = axi_rvalid_i & axi_rready_o;

  always_ff @(posedge clk_i) begin
    if (reset_i) begin
      slot_v_r <= '0;
      slot_beat_r <= '0;
      slot_subbeat_r <= '0;
      slot_fill_data_r <= '0;
    end else begin
      if (request_accept) begin
        slot_v_r[free_slot] <= 1'b1;
        slot_header_r[free_slot] <= mem_fwd_header_cast_i;
        slot_beat_r[free_slot] <= '0;
        slot_subbeat_r[free_slot] <= '0;
        slot_fill_data_r[free_slot] <= '0;
      end

      if (response_accept) begin
        slot_beat_r[response_slot] <= slot_beat_r[response_slot] + 1'b1;
        slot_fill_data_r[response_slot] <= response_fill_data;
        if (!response_fill_complete) begin
          slot_subbeat_r[response_slot] <= response_subbeat + 1'b1;
        end else begin
          slot_subbeat_r[response_slot] <= '0;
          if (axi_rlast_i) begin
            slot_v_r[response_slot] <= 1'b0;
            slot_beat_r[response_slot] <= '0;
            slot_fill_data_r[response_slot] <= '0;
          end
        end
      end
    end
  end

  wire unused = &{mem_fwd_data_i, 1'b0};

  initial begin
    if (outstanding_p < 2 || outstanding_p >= (1 << axi_id_width_p))
      $fatal(1, "Prefetch AXI outstanding count does not fit nonzero AXI IDs");
    if ((axi_data_width_p != 32 && axi_data_width_p != 64)
        || bedrock_fill_width_p != 64 || dcache_block_width_p != 512)
      $fatal(1, "Prefetch AXI bridge requires 512-bit lines, 64-bit BedRock fills, and 32- or 64-bit AXI");
  end

  // synopsys translate_off
  always_ff @(negedge clk_i) if (!reset_i) begin
    if (request_accept)
      assert (mem_fwd_header_cast_i.payload.prefetch
              && (mem_fwd_header_cast_i.msg_type == e_bedrock_mem_rd)
              && (mem_fwd_header_cast_i.size == e_bedrock_msg_size_64))
        else $error("Prefetch AXI bridge accepted a malformed BedRock request");
    if (axi_rvalid_i)
      assert (response_slot_valid)
        else $error("Prefetch AXI bridge received an invalid AXI response ID");
    if (response_accept) begin
      assert (axi_rresp_i == 2'b00)
        else $error("Prefetch AXI bridge received an AXI error response");
      assert (axi_rlast_i == (slot_beat_r[response_slot] == block_beats_lp-1))
        else $error("Prefetch AXI bridge received AXI RLAST at the wrong beat");
      assert (!axi_rlast_i || response_fill_complete)
        else $error("Prefetch AXI bridge received AXI RLAST on a partial BedRock beat");
    end
  end
  // synopsys translate_on

endmodule

`BSG_ABSTRACT_MODULE(bp_prefetch_axi_master)
