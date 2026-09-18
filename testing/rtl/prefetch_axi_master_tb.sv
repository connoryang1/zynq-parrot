// Exercise the dedicated prefetch AXI bridge through scalar testbench ports.
// The production ZynqParrot cache-line and BedRock widths are used directly.
`include "bp_common_defines.svh"
`include "bp_me_defines.svh"

module prefetch_axi_master_tb
  import bp_common_pkg::*;
  import bp_me_pkg::*;
  #(parameter bp_params_e bp_params_p = e_bp_unicore_zynqparrot_cfg
    , parameter axi_data_width_p = 32
    `declare_bp_proc_params(bp_params_p)
    `declare_bp_bedrock_if_widths(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p)
    )
  (input clk_i, reset_i
   , input req_v_i
   , input [63:0] req_addr_i
   , output req_ready_o
   , output [31:0] araddr_o
   , output [2:0] arid_o
   , output [7:0] arlen_o
   , output [2:0] arsize_o
   , output [1:0] arburst_o
   , output [7:0] axi_data_width_o
   , output arvalid_o
   , input arready_i
   , input [2:0] rid_i
   , input [axi_data_width_p-1:0] rdata_i
   , input [1:0] rresp_i
   , input rlast_i, rvalid_i
   , output rready_o
   , output [63:0] rev_addr_o
   , output [63:0] rev_data_o
   , output rev_v_o
   , input rev_ready_i
   );

  `declare_bp_bedrock_if(paddr_width_p, lce_id_width_p, cce_id_width_p, did_width_p, lce_assoc_p);
  bp_bedrock_mem_fwd_header_s fwd_header;
  bp_bedrock_mem_rev_header_s rev_header;
  logic [bedrock_fill_width_p-1:0] rev_data;

  always_comb begin
    fwd_header = '0;
    fwd_header.addr = paddr_width_p'(req_addr_i);
    fwd_header.msg_type = e_bedrock_mem_rd;
    fwd_header.size = e_bedrock_msg_size_64;
    fwd_header.payload.prefetch = 1'b1;
  end

  assign rev_addr_o = 64'(rev_header.addr);
  assign rev_data_o = rev_data;
  assign axi_data_width_o = 8'(axi_data_width_p);

  bp_prefetch_axi_master
   #(.bp_params_p(bp_params_p)
     ,.axi_addr_width_p(32)
     ,.axi_data_width_p(axi_data_width_p)
     ,.axi_id_width_p(3)
     ,.outstanding_p(3)
     )
   dut
    (.clk_i
     ,.reset_i
     ,.mem_fwd_header_i(fwd_header)
     ,.mem_fwd_data_i('0)
     ,.mem_fwd_v_i(req_v_i)
     ,.mem_fwd_ready_and_o(req_ready_o)
     ,.mem_rev_header_o(rev_header)
     ,.mem_rev_data_o(rev_data)
     ,.mem_rev_v_o(rev_v_o)
     ,.mem_rev_ready_and_i(rev_ready_i)
     ,.axi_araddr_o(araddr_o)
     ,.axi_arid_o(arid_o)
     ,.axi_arlen_o(arlen_o)
     ,.axi_arsize_o(arsize_o)
     ,.axi_arburst_o(arburst_o)
     ,.axi_arvalid_o(arvalid_o)
     ,.axi_arready_i(arready_i)
     ,.axi_rid_i(rid_i)
     ,.axi_rdata_i(rdata_i)
     ,.axi_rresp_i(rresp_i)
     ,.axi_rlast_i(rlast_i)
     ,.axi_rvalid_i(rvalid_i)
     ,.axi_rready_o(rready_o)
     );

  initial assert (bedrock_fill_width_p == 64 && dcache_block_width_p == 512)
    else $fatal(1, "standalone bridge test requires the ZynqParrot memory widths");

endmodule
