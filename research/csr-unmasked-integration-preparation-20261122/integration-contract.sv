// Uncompiled simulation-only bind contract. Never add this ghost RAM to FPGA sources.
// Reference writes mirror the original bb575 packed-array block, independently
// of the candidate's qualified write intents and unmasked invalid read data.
module csr_snapshot_integration_reference
 #(parameter int contexts_p=4, threads_p=2, width_p=1666
   ,parameter int context_width_p=(contexts_p>1)?$clog2(contexts_p):1
   ,parameter int physical_width_p=(threads_p>1)?$clog2(threads_p):1)
  (input logic clk_i,reset_i,raw_save_v_i,raw_seed_v_i,rebind_i
   ,input logic actual_save_v_i,actual_seed_v_i
   ,input logic [context_width_p-1:0] expected_save_id_i,actual_save_id_i,seed_id_i,read_id_i
   ,input logic [physical_width_p-1:0] restore_physical_id_i
   ,input logic [width_p-1:0] common_data_i,selected_restore_data_i
   ,input logic [contexts_p-1:0] valid_i
   ,input logic cache_restore_v_i,resident_restore_v_i,restore_v_i,restore_reset_i);
  bit seen_reset_r=0;
  logic [contexts_p-1:0] valid_ref_r;
  logic [width_p-1:0] image_ref_r [0:contexts_p-1];
  logic seed_expected;
  always_comb begin
    seed_expected=0;
    if (raw_seed_v_i && int'(seed_id_i)<contexts_p)
      seed_expected=rebind_i || !valid_ref_r[seed_id_i];
  end
  always @(posedge clk_i) begin
    if (reset_i) begin
      seen_reset_r<=1;
      valid_ref_r<='0;
      for (int c=0;c<contexts_p;c++) image_ref_r[c]<='0;
    end else if (seen_reset_r) begin
      assert (!$isunknown({raw_save_v_i,raw_seed_v_i,actual_save_v_i,actual_seed_v_i,
                           cache_restore_v_i,resident_restore_v_i,restore_v_i}))
        else $fatal(1,"CSR integration unknown active control");
      assert (!(raw_save_v_i && raw_seed_v_i))
        else $fatal(1,"CSR integration decoder allowed simultaneous save and seed");
      assert (valid_i===valid_ref_r)
        else $fatal(1,"CSR integration valid-vector differs from original array");
      assert (actual_save_v_i===(raw_save_v_i && int'(expected_save_id_i)<contexts_p))
        else $fatal(1,"CSR integration save qualification changed");
      assert (actual_seed_v_i===seed_expected)
        else $fatal(1,"CSR integration rebind/first-seed qualification changed");
      if (raw_save_v_i) begin
        assert (!$isunknown(expected_save_id_i) && actual_save_id_i===expected_save_id_i)
          else $fatal(1,"CSR integration save owner changed");
      end
      if (raw_seed_v_i) begin
        assert (!$isunknown({seed_id_i,rebind_i}))
          else $fatal(1,"CSR integration unknown seed identity");
      end
      assert (restore_v_i===(cache_restore_v_i || resident_restore_v_i))
        else $fatal(1,"CSR integration restore enable changed");
      if (restore_v_i) begin
        assert (!$isunknown(restore_physical_id_i) && int'(restore_physical_id_i)<threads_p)
          else $fatal(1,"CSR integration consumed out-of-range physical context");
        if (cache_restore_v_i) begin
          assert (!$isunknown(read_id_i) && int'(read_id_i)<contexts_p)
            else $fatal(1,"CSR integration consumed out-of-range virtual context");
          if (int'(read_id_i)<contexts_p) begin
            assert (restore_reset_i===!valid_ref_r[read_id_i])
              else $fatal(1,"CSR integration invalid-image reset priority changed");
            if (valid_ref_r[read_id_i]) begin
              assert (!$isunknown(selected_restore_data_i)
                      && selected_restore_data_i===image_ref_r[read_id_i])
                else $fatal(1,"CSR integration valid full1666 image differs from reference");
            end
            // Invalid raw memory is intentionally unobserved; reset-priority
            // supplies image3 in unchanged bp_be_csr:864-927.
          end
        end else begin
          assert (!restore_reset_i && selected_restore_data_i===common_data_i)
            else $fatal(1,"CSR integration resident restore changed live save-data bypass");
        end
      end
      // Original ordering retained in the ghost even though exclusion forbids both.
      if (raw_save_v_i && int'(expected_save_id_i)<contexts_p) begin
        image_ref_r[expected_save_id_i]<=common_data_i;
        valid_ref_r[expected_save_id_i]<=1;
      end
      if (seed_expected) begin
        image_ref_r[seed_id_i]<=common_data_i;
        valid_ref_r[seed_id_i]<=1;
      end
    end
  end
endmodule

// Scope binding is for a NEW integration verification model only. The new store
// is in the production source-list preview; this checker is a separate test input.
bind bp_be_top csr_snapshot_integration_reference
 #(.contexts_p(num_contexts_p),.threads_p(num_threads_p),.width_p(csr_context_width_lp)
   ,.context_width_p(context_id_width_p),.physical_width_p(thread_id_width_p))
 csr_snapshot_integration_checker
  (.clk_i(clk_i),.reset_i(reset_i)
   ,.raw_save_v_i(commit_pkt.ctxtsw),.raw_seed_v_i(ctx_npc_write_v_lo)
   ,.rebind_i(ctx_npc_write_rebind_lo)
   ,.actual_save_v_i(csr_snapshot_save_v_li),.actual_seed_v_i(csr_snapshot_seed_v_li)
   ,.expected_save_id_i(context_cache_commit_v_li
                        ? context_cache_victim_virtual_context_id_r : current_virtual_context_id_r)
   ,.actual_save_id_i(csr_snapshot_save_context_id_li)
   ,.seed_id_i(ctx_npc_write_virtual_context_id_lo)
   ,.read_id_i(context_cache_target_virtual_context_id_r)
   ,.restore_physical_id_i(csr_context_restore_physical_thread_id_li)
   ,.common_data_i(csr_context_save_data_lo)
   ,.selected_restore_data_i(csr_context_restore_data_li)
   ,.valid_i(virtual_context_csr_valid_r)
   ,.cache_restore_v_i(csr_context_cache_restore_v_li)
   ,.resident_restore_v_i(csr_context_resident_init_v_li)
   ,.restore_v_i(csr_context_restore_v_li),.restore_reset_i(csr_context_restore_reset_li));
