module hp0_observer_tb_top
  (input logic clk_i, reset_i
   ,input logic arvalid_i, arready_i
   ,input logic [63:0] araddr_i
   ,input logic [7:0] arid_i
   ,input logic [7:0] arlen_i
   ,input logic [2:0] arsize_i
   ,input logic [1:0] arburst_i
   ,input logic rvalid_i, rready_i, rlast_i
   ,input logic [7:0] rid_i
   ,input logic [1:0] rresp_i
   ,input logic awvalid_i, awready_i, wvalid_i, wready_i, wlast_i, bvalid_i, bready_i
   ,input logic freeze_i
   ,output logic frozen_o, freeze_pending_o, busy_o
   ,output logic [31:0] version_o, status_o, errors_o
   ,output logic [31:0] ar_count_o, ignored_ar_count_o, record_total_o
   ,output logic [15:0] read_outstanding_o, aw_outstanding_o, w_outstanding_o
   ,output logic [4:0] record_count_o, valid_count_o
   ,output logic [3:0] write_pointer_o
   ,input logic rd_v_i
   ,input logic [6:0] rd_index_i
   ,output logic rd_ready_o, rd_resp_v_o
   ,input logic rd_resp_ready_i
   ,output logic [6:0] rd_resp_index_o
   ,output logic [31:0] rd_resp_data_o
   ,input logic small_i
   );
  logic [1:0] frozen_o_s;
  logic [1:0] freeze_pending_o_s;
  logic [1:0] busy_o_s;
  logic [1:0][31:0] version_o_s;
  logic [1:0][31:0] status_o_s;
  logic [1:0][31:0] errors_o_s;
  logic [1:0][31:0] ar_count_o_s;
  logic [1:0][31:0] ignored_ar_count_o_s;
  logic [1:0][31:0] record_total_o_s;
  logic [1:0][15:0] read_outstanding_o_s;
  logic [1:0][15:0] aw_outstanding_o_s;
  logic [1:0][15:0] w_outstanding_o_s;
  logic [1:0][4:0] record_count_o_s;
  logic [1:0][4:0] valid_count_o_s;
  logic [1:0][3:0] write_pointer_o_s;
  logic [1:0] rd_ready_o_s;
  logic [1:0] rd_resp_v_o_s;
  logic [1:0][6:0] rd_resp_index_o_s;
  logic [1:0][31:0] rd_resp_data_o_s;
  for(genvar n=0;n<2;n++)begin : instances
    localparam int aw=(n==0)?32:64, iw=(n==0)?6:8;
    hp0_passive_read_timing_observer #(.addr_width_p(aw),.id_width_p(iw),
      .cycle_width_p((n==0)?32:8),.latency_width_p((n==0)?16:6),
      .count_width_p((n==0)?16:3),.sequence_width_p((n==0)?32:5)) dut
      (.reset_i(reset_i||(small_i!=1'(n))),.araddr_i(aw'(araddr_i)),.arid_i(iw'(arid_i)),.rid_i(iw'(rid_i))
       ,.clk_i(clk_i)
       ,.arvalid_i(arvalid_i)
       ,.arready_i(arready_i)
       ,.arlen_i(arlen_i)
       ,.arsize_i(arsize_i)
       ,.arburst_i(arburst_i)
       ,.rvalid_i(rvalid_i)
       ,.rready_i(rready_i)
       ,.rlast_i(rlast_i)
       ,.rresp_i(rresp_i)
       ,.awvalid_i(awvalid_i)
       ,.awready_i(awready_i)
       ,.wvalid_i(wvalid_i)
       ,.wready_i(wready_i)
       ,.wlast_i(wlast_i)
       ,.bvalid_i(bvalid_i)
       ,.bready_i(bready_i)
       ,.freeze_i(freeze_i)
       ,.rd_v_i(rd_v_i)
       ,.rd_index_i(rd_index_i)
       ,.rd_resp_ready_i(rd_resp_ready_i)
       ,.frozen_o(frozen_o_s[n])
       ,.freeze_pending_o(freeze_pending_o_s[n])
       ,.busy_o(busy_o_s[n])
       ,.version_o(version_o_s[n])
       ,.status_o(status_o_s[n])
       ,.errors_o(errors_o_s[n])
       ,.ar_count_o(ar_count_o_s[n])
       ,.ignored_ar_count_o(ignored_ar_count_o_s[n])
       ,.record_total_o(record_total_o_s[n])
       ,.read_outstanding_o(read_outstanding_o_s[n])
       ,.aw_outstanding_o(aw_outstanding_o_s[n])
       ,.w_outstanding_o(w_outstanding_o_s[n])
       ,.record_count_o(record_count_o_s[n])
       ,.valid_count_o(valid_count_o_s[n])
       ,.write_pointer_o(write_pointer_o_s[n])
       ,.rd_ready_o(rd_ready_o_s[n])
       ,.rd_resp_v_o(rd_resp_v_o_s[n])
       ,.rd_resp_index_o(rd_resp_index_o_s[n])
       ,.rd_resp_data_o(rd_resp_data_o_s[n])
      );
  end
  assign frozen_o=frozen_o_s[small_i];
  assign freeze_pending_o=freeze_pending_o_s[small_i];
  assign busy_o=busy_o_s[small_i];
  assign version_o=version_o_s[small_i];
  assign status_o=status_o_s[small_i];
  assign errors_o=errors_o_s[small_i];
  assign ar_count_o=ar_count_o_s[small_i];
  assign ignored_ar_count_o=ignored_ar_count_o_s[small_i];
  assign record_total_o=record_total_o_s[small_i];
  assign read_outstanding_o=read_outstanding_o_s[small_i];
  assign aw_outstanding_o=aw_outstanding_o_s[small_i];
  assign w_outstanding_o=w_outstanding_o_s[small_i];
  assign record_count_o=record_count_o_s[small_i];
  assign valid_count_o=valid_count_o_s[small_i];
  assign write_pointer_o=write_pointer_o_s[small_i];
  assign rd_ready_o=rd_ready_o_s[small_i];
  assign rd_resp_v_o=rd_resp_v_o_s[small_i];
  assign rd_resp_index_o=rd_resp_index_o_s[small_i];
  assign rd_resp_data_o=rd_resp_data_o_s[small_i];
endmodule
