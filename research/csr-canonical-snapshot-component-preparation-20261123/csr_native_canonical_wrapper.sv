// SOURCE ONLY UNELABORATED real CSR-bank producer/consumer boundary.
// Same wrapper for both storage arms. No raw snapshot/bank/prior-image ports.
`include "bp_common_defines.svh"
`include "bp_be_defines.svh"

module csr_native_canonical_wrapper
 import bp_common_pkg::*;
 import bp_be_pkg::*;
 #(parameter bp_params_e bp_params_p = bsg_blackparrot_pkg::bp_cfg_gp
   , parameter bit retained_buffer_p = 1'b1
   `declare_bp_proc_params(bp_params_p)
   `declare_bp_be_if_widths(vaddr_width_p, paddr_width_p, asid_width_p, branch_metadata_fwd_width_p, fetch_ptr_p, issue_ptr_p)
   , localparam cfg_bus_width_lp = `bp_cfg_bus_width(vaddr_width_p, hio_width_p, core_id_width_p, cce_id_width_p, lce_id_width_p, did_width_p)
   , localparam csr_context_csrs_lp = 26
   , localparam csr_context_width_lp = csr_context_csrs_lp*dword_width_gp + rv64_priv_width_gp
   )
  (input                                     clk_i
   , input                                   reset_i

   , input [63:0] retained_control_status_i
   , output logic retained_control_cmd_v_o
   , output logic [3:0] retained_control_o

   , input [cfg_bus_width_lp-1:0]            cfg_bus_i

   // CSR check interface
   , input                                   csr_r_v_i
   , input [rv64_csr_addr_width_gp-1:0]      csr_r_addr_i
   , output logic [dword_width_gp-1:0]       csr_r_data_o
   , output logic                            csr_r_illegal_o

   // Misc interface
   , input [retire_pkt_width_lp-1:0]         retire_pkt_i
   , input                                   retire_ctxtsw_v_i
   , input rv64_fflags_s                     fflags_acc_i
   , input                                   frf_w_v_i

   // Interrupts — broadcast to all threads so mip stays current
   , input                                   debug_irq_i
   , input                                   timer_irq_i
   , input                                   software_irq_i
   , input                                   m_external_irq_i
   , input                                   s_external_irq_i
   , output logic                            irq_pending_o
   , output logic                            irq_waiting_o

   // The final commit packet
   , output logic [commit_pkt_width_lp-1:0]  commit_pkt_o

   // Slow signals
   , output logic [decode_info_width_lp-1:0] decode_info_o
   , output logic [trans_info_width_lp-1:0]  trans_info_o
   , output logic [trans_info_width_lp-1:0]  reservation_trans_info_o
   , output rv64_frm_e                       frm_dyn_o

   // Current thread selects the active per-thread CSR instance.
   , input [thread_id_width_p-1:0]           current_physical_thread_id_i
   // Software-visible virtual context ID returned by CSR 0x800.
   , input [context_id_width_p-1:0]          current_virtual_context_id_i
   // CSR reads belong to the instruction in the reservation station.
   , input [thread_id_width_p-1:0]           csr_thread_id_i
   // Retire thread owns the instruction currently committing in the backend.
   , input [thread_id_width_p-1:0]           retire_thread_id_i

   // Bootstrap: write target NPC for a virtual context (CSR 0x801)
   , output logic                            ctx_npc_write_v_o
   , output logic                            ctx_npc_write_rebind_o
   , output logic                            ctx_npc_write_rpc_entry_o
   , output logic [context_id_width_p-1:0]   ctx_npc_write_virtual_context_id_o
   , output logic [vaddr_width_p-1:0]        ctx_npc_write_npc_o

   // CSR 0x802 remote register write into a virtual context
   , output logic                            ctx_rpush_v_o
   , output logic                            ctx_rpush_fp_v_o
   , output logic [context_id_width_p-1:0]   ctx_rpush_virtual_context_id_o
   , output logic [reg_addr_width_gp-1:0]    ctx_rpush_reg_o
   , output logic [dpath_width_gp-1:0]       ctx_rpush_data_o

   // Context-cache L1 D$ service CSR path.
   , input                                   ctx_l1_ready_i
   , input                                   ctx_l1_resp_v_i
   , input [dword_width_gp-1:0]              ctx_l1_resp_data_i
   , output logic                            ctx_l1_cmd_v_o
   , output logic                            ctx_l1_cmd_w_o
   , output logic [paddr_width_p-1:0]        ctx_l1_cmd_paddr_o
   , output logic [dword_width_gp-1:0]       ctx_l1_cmd_data_o

   , input                                   icache_replay_ready_i
   , output logic                            icache_replay_v_o
   , output logic [paddr_width_p-1:0]        icache_replay_paddr_o
   , input [63:0]                            icache_retention_status_i
   , output logic                            icache_retention_cmd_v_o
   , output logic [1:0]                      icache_retention_mode_o
   , input [dword_width_gp-1:0]              icache_prefix_status_i
   , output logic                            icache_prefix_entry_v_o
   , output logic [7:0]                      icache_prefix_entry_index_o
   , output logic [paddr_width_p-1:0]        icache_prefix_entry_paddr_o
   , output logic                            icache_prefix_count_v_o
   , output logic [8:0]                      icache_prefix_count_o
   , output logic                            icache_prefix_trigger_v_o
   , output logic                            icache_prefix_trigger_range_v_o
   , output logic [7:0]                      icache_prefix_trigger_start_o
   , output logic [8:0]                      icache_prefix_trigger_count_o
   , output logic                            icache_prefix_clear_v_o
   , input                                   physical_preview_idle_i
   , output logic                            physical_preview_v_o
   , output logic [paddr_width_p-1:0]        physical_preview_paddr_o
   , input [dword_width_gp-1:0]              dcache_replay_status_i
   , output logic                            dcache_replay_entry_v_o
   , output logic                            dcache_replay_config_v_o
   , output logic                            dcache_replay_trigger_v_o
   , output logic [dword_width_gp-1:0]       dcache_replay_payload_o

   // Literal current bp_be_top controller-state cut; no arbitrary CSR images.
   , input context_cache_commit_v_li,context_cache_launch_v_li
   , input pending_ctxtsw_sent_r,pending_rpc_call_v_r,rpc_entry_valid_r
   , input [thread_id_width_p-1:0] context_cache_victim_physical_thread_id_r
   , input [thread_id_width_p-1:0] pending_ctxtsw_prev_physical_thread_id_r
   , input [thread_id_width_p-1:0] pending_ctxtsw_physical_thread_id_r
   , input [context_id_width_p-1:0] context_cache_victim_virtual_context_id_r
   , input [context_id_width_p-1:0] context_cache_target_virtual_context_id_r
   , input [num_contexts_p-1:0] virtual_context_resident_v_r
   , input [num_contexts_p-1:0][thread_id_width_p-1:0] virtual_context_slot_r
   , input [num_contexts_p-1:0][vaddr_width_p-1:0] virtual_context_npc_r
   , input [vaddr_width_p-1:0] rpc_entry_r
   );

  `declare_bp_be_if(vaddr_width_p, paddr_width_p, asid_width_p, branch_metadata_fwd_width_p, fetch_ptr_p, issue_ptr_p);
  bp_be_commit_pkt_s commit_pkt;
  assign commit_pkt=commit_pkt_o;
  wire [thread_id_width_p-1:0] current_physical_thread_id_lo=current_physical_thread_id_i;
  wire [context_id_width_p-1:0] current_virtual_context_id_r=current_virtual_context_id_i;
  wire [thread_id_width_p-1:0] retire_thread_id_lo=retire_thread_id_i;
  logic [num_contexts_p-1:0] virtual_context_csr_valid_r;
  logic [csr_context_width_lp-1:0] virtual_context_csr_read_data_lo;
  logic ctx_npc_write_resident_v_li;
  logic [thread_id_width_p-1:0] ctx_npc_write_physical_thread_id_li;
  logic ctx_npc_write_v_lo,ctx_npc_write_rebind_lo,ctx_npc_write_rpc_entry_lo;
  logic [context_id_width_p-1:0] ctx_npc_write_virtual_context_id_lo;
  logic [vaddr_width_p-1:0] ctx_npc_write_npc_lo;
  assign ctx_npc_write_v_o=ctx_npc_write_v_lo;
  assign ctx_npc_write_rebind_o=ctx_npc_write_rebind_lo;
  assign ctx_npc_write_rpc_entry_o=ctx_npc_write_rpc_entry_lo;
  assign ctx_npc_write_virtual_context_id_o=ctx_npc_write_virtual_context_id_lo;
  assign ctx_npc_write_npc_o=ctx_npc_write_npc_lo;

  logic [csr_context_width_lp-1:0] csr_context_save_data_lo;
  wire [thread_id_width_p-1:0] csr_context_save_physical_thread_id_li =
    context_cache_commit_v_li
    ? context_cache_victim_physical_thread_id_r
    : pending_ctxtsw_sent_r ? pending_ctxtsw_prev_physical_thread_id_r : current_physical_thread_id_lo;
  // Only inactive CSR snapshots move to the single-write store. The exact
  // retirement decoder excludes simultaneous committed save and NPC seed.
  wire [context_id_width_p-1:0] csr_snapshot_save_context_id_li =
    context_cache_commit_v_li
    ? context_cache_victim_virtual_context_id_r : current_virtual_context_id_r;
  wire csr_snapshot_save_v_li = commit_pkt.ctxtsw
    && (csr_snapshot_save_context_id_li < num_contexts_p);
  wire csr_snapshot_seed_v_li = ctx_npc_write_v_lo
    && (ctx_npc_write_virtual_context_id_lo < num_contexts_p)
    && (ctx_npc_write_rebind_lo
        || !virtual_context_csr_valid_r[ctx_npc_write_virtual_context_id_lo]);
  // synthesis translate_off
  bit verify_noncanonical = 1'b0;
  // synthesis translate_on
  logic [csr_context_width_lp-1:0] canonical_write_data_li;
  always_comb begin
    canonical_write_data_li = csr_context_save_data_lo;
    // synthesis translate_off
    if (verify_noncanonical && (csr_snapshot_save_v_li | csr_snapshot_seed_v_li))
      canonical_write_data_li[rv64_priv_width_gp+63] = ~canonical_write_data_li[rv64_priv_width_gp+63];
    // synthesis translate_on
  end
  // synthesis translate_off
  initial begin
    if ($test$plusargs("NONCANONICAL_WRITE")) verify_noncanonical = 1'b1;
  end
  // synthesis translate_on
  bp_be_csr_snapshot_store_canonical
   #(.bp_params_p(bp_params_p)
     ,.contexts_p(num_contexts_p)
     ,.width_p(csr_context_width_lp)
     ,.addr_width_p(context_id_width_p))
   csr_snapshot_store
    (.clk_i(clk_i)
     ,.reset_i(reset_i)
     ,.write_v_i(csr_snapshot_save_v_li | csr_snapshot_seed_v_li)
     ,.write_addr_i(csr_snapshot_seed_v_li
                    ? ctx_npc_write_virtual_context_id_lo : csr_snapshot_save_context_id_li)
     ,.read_addr_i(context_cache_target_virtual_context_id_r)
     ,.write_data_i(canonical_write_data_li)
     ,.valid_o(virtual_context_csr_valid_r)
     ,.read_valid_o()
     ,.read_data_o(virtual_context_csr_read_data_lo));
  // First NPC seeding clones the caller's CSR image. A resident target never
  // takes the context-cache install path, so initialize its inactive physical
  // bank at that same committed seed. Existing contexts keep their own CSRs
  // when reseeded; a self-seed must not restore over its retiring instruction.
  wire csr_context_cache_restore_v_li = context_cache_launch_v_li;
  wire csr_context_resident_init_v_li = ctx_npc_write_resident_v_li
    && (ctx_npc_write_virtual_context_id_lo < num_contexts_p)
    && (ctx_npc_write_physical_thread_id_li < num_threads_p)
    && (ctx_npc_write_rebind_lo
        || !virtual_context_csr_valid_r[ctx_npc_write_virtual_context_id_lo])
    && (ctx_npc_write_physical_thread_id_li != csr_context_save_physical_thread_id_li);
  wire csr_context_restore_v_li = csr_context_cache_restore_v_li | csr_context_resident_init_v_li;
  // A committed NPC write to an initialized inactive resident bank changes
  // its next trap PC without cloning the caller's architectural CSR image.
  // Pending switches can separate active, retiring, and save-bank ownership;
  // exclude all three so a self-seed cannot replace live retirement state.
  wire rpc_target_apc_write_v_li = commit_pkt.ctxtsw
    && pending_rpc_call_v_r
    && (pending_ctxtsw_physical_thread_id_r < num_threads_p);
  wire csr_context_apc_write_v_li = rpc_target_apc_write_v_li
    || (ctx_npc_write_resident_v_li
    && (ctx_npc_write_virtual_context_id_lo < num_contexts_p)
    && (ctx_npc_write_physical_thread_id_li < num_threads_p)
    && virtual_context_csr_valid_r[ctx_npc_write_virtual_context_id_lo]
    && !ctx_npc_write_rebind_lo
    && (ctx_npc_write_physical_thread_id_li != current_physical_thread_id_lo)
    && (ctx_npc_write_physical_thread_id_li != retire_thread_id_lo)
    && (ctx_npc_write_physical_thread_id_li != csr_context_save_physical_thread_id_li)
    && !csr_context_restore_v_li);
  wire [thread_id_width_p-1:0] csr_context_restore_physical_thread_id_li =
    csr_context_cache_restore_v_li ? context_cache_victim_physical_thread_id_r
    : rpc_target_apc_write_v_li ? pending_ctxtsw_physical_thread_id_r
    : ctx_npc_write_physical_thread_id_li;
  wire csr_context_restore_reset_li =
    csr_context_cache_restore_v_li
    & ~virtual_context_csr_valid_r[context_cache_target_virtual_context_id_r];
  wire [csr_context_width_lp-1:0] csr_context_restore_data_li =
    csr_context_cache_restore_v_li
    ? virtual_context_csr_read_data_lo
    : csr_context_save_data_lo;
  wire [vaddr_width_p-1:0] csr_context_restore_npc_li =
    csr_context_cache_restore_v_li
    ? virtual_context_npc_r[context_cache_target_virtual_context_id_r]
    : rpc_target_apc_write_v_li ? rpc_entry_r : ctx_npc_write_npc_lo;

  always_comb begin
    ctx_npc_write_resident_v_li = 1'b0;
    ctx_npc_write_physical_thread_id_li = '0;
    if (ctx_npc_write_v_lo && (ctx_npc_write_virtual_context_id_lo < num_contexts_p)) begin
      ctx_npc_write_resident_v_li = virtual_context_resident_v_r[ctx_npc_write_virtual_context_id_lo];
      ctx_npc_write_physical_thread_id_li = virtual_context_slot_r[ctx_npc_write_virtual_context_id_lo];
    end
  end

  bp_be_csr_wrapper_mt
   #(.bp_params_p(bp_params_p),.retained_buffer_p(retained_buffer_p))
   real_csr
    (.clk_i(clk_i)
     ,.reset_i(reset_i)
     ,.retained_control_status_i(retained_control_status_i)
     ,.retained_control_cmd_v_o(retained_control_cmd_v_o)
     ,.retained_control_o(retained_control_o)
     ,.cfg_bus_i(cfg_bus_i)
     ,.csr_r_v_i(csr_r_v_i)
     ,.csr_r_addr_i(csr_r_addr_i)
     ,.csr_r_data_o(csr_r_data_o)
     ,.csr_r_illegal_o(csr_r_illegal_o)
     ,.retire_pkt_i(retire_pkt_i)
     ,.retire_ctxtsw_v_i(retire_ctxtsw_v_i)
     ,.fflags_acc_i(fflags_acc_i)
     ,.frf_w_v_i(frf_w_v_i)
     ,.debug_irq_i(debug_irq_i)
     ,.timer_irq_i(timer_irq_i)
     ,.software_irq_i(software_irq_i)
     ,.m_external_irq_i(m_external_irq_i)
     ,.s_external_irq_i(s_external_irq_i)
     ,.irq_pending_o(irq_pending_o)
     ,.irq_waiting_o(irq_waiting_o)
     ,.commit_pkt_o(commit_pkt_o)
     ,.decode_info_o(decode_info_o)
     ,.trans_info_o(trans_info_o)
     ,.reservation_trans_info_o(reservation_trans_info_o)
     ,.frm_dyn_o(frm_dyn_o)
     ,.current_physical_thread_id_i(current_physical_thread_id_i)
     ,.current_virtual_context_id_i(current_virtual_context_id_i)
     ,.legacy_context_user_enable_i(~rpc_entry_valid_r)
     ,.csr_thread_id_i(csr_thread_id_i)
     ,.retire_thread_id_i(retire_thread_id_i)
     ,.csr_context_restore_v_i(csr_context_restore_v_li)
     ,.csr_context_apc_write_v_i(csr_context_apc_write_v_li)
     ,.csr_context_restore_reset_i(csr_context_restore_reset_li)
     ,.csr_context_restore_physical_thread_id_i(csr_context_restore_physical_thread_id_li)
     ,.csr_context_restore_data_i(csr_context_restore_data_li)
     ,.csr_context_restore_npc_i(csr_context_restore_npc_li)
     ,.csr_context_save_physical_thread_id_i(csr_context_save_physical_thread_id_li)
     ,.csr_context_save_data_o(csr_context_save_data_lo)
     ,.ctx_npc_write_v_o(ctx_npc_write_v_lo)
     ,.ctx_npc_write_rebind_o(ctx_npc_write_rebind_lo)
     ,.ctx_npc_write_rpc_entry_o(ctx_npc_write_rpc_entry_lo)
     ,.ctx_npc_write_virtual_context_id_o(ctx_npc_write_virtual_context_id_lo)
     ,.ctx_npc_write_npc_o(ctx_npc_write_npc_lo)
     ,.ctx_rpush_v_o(ctx_rpush_v_o)
     ,.ctx_rpush_fp_v_o(ctx_rpush_fp_v_o)
     ,.ctx_rpush_virtual_context_id_o(ctx_rpush_virtual_context_id_o)
     ,.ctx_rpush_reg_o(ctx_rpush_reg_o)
     ,.ctx_rpush_data_o(ctx_rpush_data_o)
     ,.ctx_l1_ready_i(ctx_l1_ready_i)
     ,.ctx_l1_resp_v_i(ctx_l1_resp_v_i)
     ,.ctx_l1_resp_data_i(ctx_l1_resp_data_i)
     ,.ctx_l1_cmd_v_o(ctx_l1_cmd_v_o)
     ,.ctx_l1_cmd_w_o(ctx_l1_cmd_w_o)
     ,.ctx_l1_cmd_paddr_o(ctx_l1_cmd_paddr_o)
     ,.ctx_l1_cmd_data_o(ctx_l1_cmd_data_o)
     ,.miss_trace_status_i('0)
     ,.miss_trace_data_i('0)
     ,.miss_trace_ctrl_v_o()
     ,.miss_trace_arm_o()
     ,.miss_trace_clear_o()
     ,.miss_trace_read_v_o()
     ,.miss_trace_read_source_o()
     ,.miss_trace_read_index_o()
     ,.icache_replay_ready_i(icache_replay_ready_i)
     ,.icache_replay_v_o(icache_replay_v_o)
     ,.icache_replay_paddr_o(icache_replay_paddr_o)
     ,.icache_retention_status_i(icache_retention_status_i)
     ,.icache_retention_cmd_v_o(icache_retention_cmd_v_o)
     ,.icache_retention_mode_o(icache_retention_mode_o)
     ,.icache_prefix_status_i(icache_prefix_status_i)
     ,.icache_prefix_entry_v_o(icache_prefix_entry_v_o)
     ,.icache_prefix_entry_index_o(icache_prefix_entry_index_o)
     ,.icache_prefix_entry_paddr_o(icache_prefix_entry_paddr_o)
     ,.icache_prefix_count_v_o(icache_prefix_count_v_o)
     ,.icache_prefix_count_o(icache_prefix_count_o)
     ,.icache_prefix_trigger_v_o(icache_prefix_trigger_v_o)
     ,.icache_prefix_trigger_range_v_o(icache_prefix_trigger_range_v_o)
     ,.icache_prefix_trigger_start_o(icache_prefix_trigger_start_o)
     ,.icache_prefix_trigger_count_o(icache_prefix_trigger_count_o)
     ,.icache_prefix_clear_v_o(icache_prefix_clear_v_o)
     ,.physical_preview_idle_i(physical_preview_idle_i)
     ,.physical_preview_v_o(physical_preview_v_o)
     ,.physical_preview_paddr_o(physical_preview_paddr_o)
     ,.dcache_replay_status_i(dcache_replay_status_i)
     ,.dcache_replay_entry_v_o(dcache_replay_entry_v_o)
     ,.dcache_replay_config_v_o(dcache_replay_config_v_o)
     ,.dcache_replay_trigger_v_o(dcache_replay_trigger_v_o)
     ,.dcache_replay_payload_o(dcache_replay_payload_o));
endmodule
