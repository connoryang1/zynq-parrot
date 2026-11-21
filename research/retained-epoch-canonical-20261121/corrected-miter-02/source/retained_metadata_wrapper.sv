module retained_metadata_wrapper
 #(parameter int I_LINES = 93, parameter int D_LINES = 131, parameter int RETAINED_SETS = 256, parameter int EPOCH_WIDTH = 8)
  (input logic [1:0] clk_i, reset_i, clear_i, invalidate_v_i
   , input logic [33:0] invalidate_addr0_i, invalidate_addr1_i
   , input logic [1:0] lookup_v_i
   , output logic [1:0] lookup_ready_o
   , input logic [33:0] lookup_addr0_i, lookup_addr1_i
   , output logic [1:0] resp_v_o
   , input logic [1:0] resp_ready_i
   , output logic [1:0] resp_hit_o
   , output logic [511:0] resp_data0_o, resp_data1_o
   , input logic [1:0] insert_v_i
   , output logic [1:0] insert_ready_o
   , input logic [33:0] insert_addr0_i, insert_addr1_i
   , input logic [511:0] insert_data0_i, insert_data1_i
   , input logic [1:0] insert_replace_i, insert_cancel_i
   , output logic [1:0] insert_done_o, insert_published_o, busy_o, epoch_wrap_o
   , output logic [1:0] debug_data_v_o, debug_data_w_o
   , output logic [2:0] debug_word0_o, debug_word1_o
   , output logic [31:0] i_lines_o, d_lines_o, retained_sets_o
   , output logic [1:0] mismatch_o
   , output logic [3:0] debug_state0_o, debug_state1_o
   , output logic [31:0] debug_clear0_o, debug_clear1_o, epoch_width_o
   );
  assign retained_sets_o = RETAINED_SETS;
  assign i_lines_o = I_LINES;
  assign d_lines_o = D_LINES;
  logic [1:0] ref_lookup_ready, ref_resp_v, ref_resp_hit, ref_insert_ready, ref_insert_done, ref_insert_published, ref_busy, ref_epoch_wrap;
  logic [1:0][511:0] ref_resp_data;
  bp_retained_line_store
   #(.paddr_width_p(34), .sets_p(RETAINED_SETS), .i_lines_p(I_LINES), .d_lines_p(D_LINES), .epoch_width_p(EPOCH_WIDTH)) dut
   (.clk_i(clk_i), .reset_i(reset_i), .clear_i(clear_i)
    ,.invalidate_v_i(invalidate_v_i), .invalidate_addr_i({invalidate_addr1_i,invalidate_addr0_i})
    ,.lookup_v_i(lookup_v_i), .lookup_ready_o(lookup_ready_o), .lookup_addr_i({lookup_addr1_i,lookup_addr0_i})
    ,.resp_v_o(resp_v_o), .resp_ready_i(resp_ready_i), .resp_hit_o(resp_hit_o), .resp_data_o({resp_data1_o,resp_data0_o})
    ,.insert_v_i(insert_v_i), .insert_ready_o(insert_ready_o), .insert_addr_i({insert_addr1_i,insert_addr0_i})
    ,.insert_data_i({insert_data1_i,insert_data0_i}), .insert_replace_i(insert_replace_i), .insert_cancel_i(insert_cancel_i)
    ,.insert_done_o(insert_done_o), .insert_published_o(insert_published_o), .busy_o(busy_o), .epoch_wrap_o(epoch_wrap_o));
  bp_retained_line_store_reference
   #(.paddr_width_p(34), .sets_p(RETAINED_SETS), .i_lines_p(I_LINES), .d_lines_p(D_LINES), .epoch_width_p(EPOCH_WIDTH)) reference
   (.clk_i(clk_i), .reset_i(reset_i), .clear_i(clear_i)
    ,.invalidate_v_i(invalidate_v_i), .invalidate_addr_i({invalidate_addr1_i,invalidate_addr0_i})
    ,.lookup_v_i(lookup_v_i), .lookup_ready_o(ref_lookup_ready), .lookup_addr_i({lookup_addr1_i,lookup_addr0_i})
    ,.resp_v_o(ref_resp_v), .resp_ready_i(resp_ready_i), .resp_hit_o(ref_resp_hit), .resp_data_o(ref_resp_data)
    ,.insert_v_i(insert_v_i), .insert_ready_o(ref_insert_ready), .insert_addr_i({insert_addr1_i,insert_addr0_i})
    ,.insert_data_i({insert_data1_i,insert_data0_i}), .insert_replace_i(insert_replace_i), .insert_cancel_i(insert_cancel_i)
    ,.insert_done_o(ref_insert_done), .insert_published_o(ref_insert_published), .busy_o(ref_busy), .epoch_wrap_o(ref_epoch_wrap));
  assign debug_data_v_o = dut.data_v;
  assign debug_data_w_o = dut.data_w;
  assign debug_word0_o = dut.data_addr[0][2:0];
  assign debug_word1_o = dut.data_addr[1][2:0];
  assign debug_state0_o = 4'(dut.lane_fsm[0].state_r);
  assign debug_state1_o = 4'(dut.lane_fsm[1].state_r);
  assign debug_clear0_o = 32'(dut.lane_fsm[0].clear_slot_r);
  assign debug_clear1_o = 32'(dut.lane_fsm[1].clear_slot_r);
  assign epoch_width_o = EPOCH_WIDTH;
  for (genvar l=0; l<2; l++) begin : miter
    always_comb begin
      mismatch_o[l] = epoch_mismatch;
      if (!reset_i[l]) begin
        mismatch_o[l] |= ({lookup_ready_o[l],resp_v_o[l],insert_ready_o[l],insert_done_o[l],
                         insert_published_o[l],busy_o[l],epoch_wrap_o[l]}
                     !== {ref_lookup_ready[l],ref_resp_v[l],ref_insert_ready[l],ref_insert_done[l],
                          ref_insert_published[l],ref_busy[l],ref_epoch_wrap[l]});
        if (resp_v_o[l]) begin
          mismatch_o[l] |= resp_hit_o[l] !== ref_resp_hit[l];
          if (resp_hit_o[l]) mismatch_o[l] |= (l==0 ? resp_data0_o : resp_data1_o) !== ref_resp_data[l];
        end
        mismatch_o[l] |= {dut.tag_v[l],dut.tag_w[l],dut.data_v[l],dut.data_w[l]}
                     !== {reference.tag_v[l],reference.tag_w[l],reference.data_v[l],reference.data_w[l]};
        if (dut.tag_v[l]) begin
          mismatch_o[l] |= dut.tag_addr[l] !== reference.tag_addr[l];
          if (dut.tag_w[l]) mismatch_o[l] |= dut.tag_wdata[l] !== reference.tag_wdata[l];
        end
        if (dut.data_v[l]) begin
          mismatch_o[l] |= dut.data_addr[l] !== reference.data_addr[l];
          if (dut.data_w[l]) mismatch_o[l] |= dut.data_wdata[l] !== reference.data_wdata[l];
        end
        mismatch_o[l] |= {dut.lane_fsm[l].state_r,dut.lane_fsm[l].clear_slot_r,
                         dut.lane_fsm[l].slot_r,dut.lane_fsm[l].word_r}
                    !== {reference.lane_fsm[l].state_r,reference.lane_fsm[l].clear_slot_r,
                         reference.lane_fsm[l].slot_r,reference.lane_fsm[l].word_r};
      end
    end
    localparam int LINES_FOR_EPOCH = (l==0) ? I_LINES : D_LINES;
    logic epoch_mismatch;
    if ((l != 0) && (LINES_FOR_EPOCH >= RETAINED_SETS)) begin : dense_epoch_check
      always_comb begin
        epoch_mismatch = 1'b0;
        for (int q=0; q<RETAINED_SETS; q++)
          epoch_mismatch |= dut.lane_fsm[l].distributed_epochs.epoch_ram.mem[q]
                         !== reference.lane_fsm[l].epochs_r[q];
      end
      initial for (int q=0; q<RETAINED_SETS; q++) begin
        dut.lane_fsm[l].distributed_epochs.epoch_ram.mem[q] = '1;
        reference.lane_fsm[l].epochs_r[q] = '1;
      end
    end else begin : flop_epoch_check
      always_comb begin
        epoch_mismatch = 1'b0;
        for (int q=0; q<RETAINED_SETS; q++)
          epoch_mismatch |= dut.lane_fsm[l].flop_epochs.epochs_r[q]
                         !== reference.lane_fsm[l].epochs_r[q];
      end
      initial for (int q=0; q<RETAINED_SETS; q++) begin
        dut.lane_fsm[l].flop_epochs.epochs_r[q] = '1;
        reference.lane_fsm[l].epochs_r[q] = '1;
      end
    end
    // Deliberately nonzero initial metadata. These test-only writes are not
    // in implementation RTL and do not assume any power-up RAM contents.
    localparam int LINES = (l==0) ? I_LINES : D_LINES;
    initial begin
      for (int q=0; q<((LINES>0)?LINES:1); q++) begin
        dut.lane_fsm[l].tag_mem[q] = '1;
        reference.lane_fsm[l].tag_mem[q] = '1;
      end
      for (int q=0; q<((LINES>0)?LINES:1)*8; q++) begin
        dut.lane_fsm[l].payload_mem[q] = 64'hd1e2f30415263748;
        reference.lane_fsm[l].payload_mem[q] = 64'hd1e2f30415263748;
      end
      for (int s=0; s<RETAINED_SETS; s++) begin
        dut.lane_fsm[l].rr_r[s] = '1;
        reference.lane_fsm[l].rr_r[s] = '1;
      end
    end
  end
endmodule
