/*
 * bp_common_pkg.sv
 *
 * This package defines the Zynq-Parrot simulation and FPGA configurations.
 * Named configurations provide reproducible synthesis endpoints; experimental
 * configurations still require simulation, routed timing, and board validation.
 */

  `include "bp_common_defines.svh"

package bp_common_pkg;

  `include "bp_common_accelerator_pkgdef.svh"
  `include "bp_common_addr_pkgdef.svh"
  `include "bp_common_host_pkgdef.svh"
  //`include "bp_common_aviary_pkgdef.svh"
  `include "bp_common_aviary_cfg_pkgdef.svh"

  localparam bp_proc_param_s bp_unicore_zynqparrot_cfg_override_p =
    '{paddr_width: 34

      // This historical schema has no separate logical-context count. Keep
      // the resident register banks at the validated PYNQ-Z2 fit dimension.
      ,num_threads: 2

      ,icache_fill_width: 64

      ,dcache_fill_width: 64

      ,acache_fill_width: 64

      ,bedrock_fill_width: 64

      ,l2_data_width: 64
      ,l2_fill_width: 64
      // Keep the PYNQ-Z2 implementation within the xc7z020 LUT/slice budget.
      ,l2_slices    : 1
`ifdef BP_ZYNQ_PREFETCH_TWO_BANKS
      // Experimental downstream capacity: retain 4 KiB total (2 ways, 64 B
      // lines), with adjacent lines in different banks. Each bank still has
      // one miss handler; the shared controller must also admit both requests
      // before this can overlap cold fills. Requires full-top and routed gates.
      ,l2_banks     : 2
      ,l2_sets      : bp_default_cfg_p.l2_sets / 2
      ,dcache_prefetch_els: 10
`else
      ,l2_banks     : 1
`endif

      ,itlb_els_4k : 16
      ,itlb_els_2m : 1
      ,itlb_els_1g : 1
      ,dtlb_els_4k : 16
      ,dtlb_els_2m : 4
      ,dtlb_els_1g : 1

      ,default : "inv"
      };
  `bp_aviary_derive_cfg(bp_unicore_zynqparrot_cfg_p
                        ,bp_unicore_zynqparrot_cfg_override_p
                        ,bp_default_cfg_p
                        );

  localparam bp_proc_param_s bp_multicore_zynqparrot_cfg_override_p =
    '{paddr_width: 34
      ,cce_type : e_cce_fsm
      ,ic_y_dim : 1

      ,icache_fill_width: 64

      ,dcache_fill_width: 64

      ,acache_fill_width: 64

      ,bedrock_fill_width: 64

      ,coh_noc_flit_width : 64
      ,mem_noc_flit_width : 64
      ,dma_noc_flit_width : 64

      ,icache_features      : (1 << e_cfg_enabled) | (1 << e_cfg_coherent)
                              | (1 << e_cfg_misaligned)
      ,dcache_features      : (1 << e_cfg_enabled)
                              | (1 << e_cfg_coherent)
                              | (1 << e_cfg_writeback)
                              | (1 << e_cfg_lr_sc)
                              | (1 << e_cfg_amo_swap)
                              | (1 << e_cfg_amo_fetch_logic)
                              | (1 << e_cfg_amo_fetch_arithmetic)
      ,l2_features          : (1 << e_cfg_enabled) | (1 << e_cfg_writeback)
                              | (1 << e_cfg_word_tracking)

      ,l2_data_width: 64
      ,l2_fill_width: 64
      ,l2_slices    : 1
      ,l2_banks     : 1

      ,itlb_els_4k : 16
      ,itlb_els_2m : 1
      ,itlb_els_1g : 1
      ,dtlb_els_4k : 16
      ,dtlb_els_2m : 4
      ,dtlb_els_1g : 1

      ,default : "inv"
      };
  `bp_aviary_derive_cfg(bp_multicore_zynqparrot_cfg_p
                        ,bp_multicore_zynqparrot_cfg_override_p
                        ,bp_default_cfg_p
                        );

  // Explicit synthesis endpoint: no environment-only define is needed to
  // reproduce the two-bank, same-capacity prefetch experiment on the FPGA.
  localparam bp_proc_param_s bp_unicore_zynqparrot_prefetch_cfg_override_p =
    '{l2_banks: 2
      // Four detached fills fit the PYNQ-Z2 target while the parameterized
      // simulator can still request ten for the ten-worker experiment.
      ,dcache_prefetch_els: 4
      // Branch metadata includes the resident thread ID. The default has four
      // slots; this two-slot endpoint needs one fewer bit (50 rather than 51).
      ,branch_metadata_fwd_width: bp_default_cfg_p.branch_metadata_fwd_width
                                  - $clog2(bp_default_cfg_p.num_threads)
                                  + $clog2(bp_unicore_zynqparrot_cfg_p.num_threads)
      ,l2_sets: (bp_unicore_zynqparrot_cfg_p.l2_banks
                 * bp_unicore_zynqparrot_cfg_p.l2_sets) / 2
      ,default: "inv"
      };
  `bp_aviary_derive_cfg(bp_unicore_zynqparrot_prefetch_cfg_p
                        ,bp_unicore_zynqparrot_prefetch_cfg_override_p
                        ,bp_unicore_zynqparrot_cfg_p
                        );

  // Area-exploration endpoint for the original ten-worker workload: two
  // resident register banks, ten SRAM-backed logical contexts, and enough
  // detached fills to retain every worker's first-lap hint. Keep the routed
  // four-entry configuration above stable; this endpoint still requires board
  // qualification before it becomes the physical acceptance image.
  localparam bp_proc_param_s bp_unicore_zynqparrot_prefetch10_cfg_override_p =
    '{num_contexts: 10
      ,dcache_prefetch_els: 10
      ,default: "inv"
      };
  `bp_aviary_derive_cfg(bp_unicore_zynqparrot_prefetch10_cfg_p
                        ,bp_unicore_zynqparrot_prefetch10_cfg_override_p
                        ,bp_unicore_zynqparrot_prefetch_cfg_p
                        );

  // Small routed endpoint for the corrected queue-depth knee. It retains the
  // ten logical contexts of the sustained workload while reducing only the
  // detached full-line transaction table from ten entries to five.
  localparam bp_proc_param_s bp_unicore_zynqparrot_prefetch5_cfg_override_p =
    '{num_contexts: 10
      ,dcache_prefetch_els: 5
      ,default: "inv"
      };
  `bp_aviary_derive_cfg(bp_unicore_zynqparrot_prefetch5_cfg_p
                        ,bp_unicore_zynqparrot_prefetch5_cfg_override_p
                        ,bp_unicore_zynqparrot_prefetch_cfg_p
                        );

  // Retention-capacity experiment for early Linux data previews.  Keep the
  // accepted four-context/four-slot endpoint unchanged except for growing
  // each two-way L2 bank from 16 to 64 sets (4 KiB to 16 KiB total).
  // Retained fg/bg experiment (branch experiment/retained-preserve-capture):
  // Linux runs on one hart and switches in software, so drop the unused
  // hardware multi-context state (second CSR file/register bank, context
  // cache, CSR snapshot store) to fit the retained store and HP0 delay shim.
  // BP_ZP_L2_SETS (default 64, i.e. 16 KiB) sizes the L2 for the equal-area
  // baseline: the retained store's BRAM spent on L2 capacity instead.
`ifndef BP_ZP_L2_SETS
`define BP_ZP_L2_SETS 64
`endif
  // BP_ZP_DCACHE_PF_FULL=1 installs whole prefetched lines into the L1 D-cache
  // (address-replay experiment) instead of the narrow advisory sector buffer.
  // It only takes effect without the retained store (BP_RETAINED_BUFFER=0).
`ifndef BP_ZP_DCACHE_PF_FULL
`define BP_ZP_DCACHE_PF_FULL 0
`endif
  // BP_ZP_DCACHE_PF_ELS: detached D-cache hint slots (replay parallelism).
  // BP_ZP_L2_BANKS: L2 bank count (each bsg_cache bank blocks on one miss,
  // so banks bound coherent replay parallelism). Capacity is
  // banks * BP_ZP_L2_SETS * 2 ways * 64 B.
`ifndef BP_ZP_L2_BANKS
`define BP_ZP_L2_BANKS 2
`endif
`ifndef BP_ZP_DCACHE_PF_ELS
`define BP_ZP_DCACHE_PF_ELS 4
`endif
  localparam bp_proc_param_s bp_unicore_zynqparrot_prefetch16k_cfg_override_p =
    '{l2_sets: `BP_ZP_L2_SETS
      ,l2_banks: `BP_ZP_L2_BANKS
      ,dcache_prefetch_full_line: `BP_ZP_DCACHE_PF_FULL
      ,dcache_prefetch_els: `BP_ZP_DCACHE_PF_ELS
      ,num_threads: 1
      ,num_contexts: 1
      ,branch_metadata_fwd_width: bp_default_cfg_p.branch_metadata_fwd_width
                                  - $clog2(bp_default_cfg_p.num_threads)
`ifdef BP_ZP_LEAN
      // FPGA fit (replay experiment): drop the catch-up integer pipe and the
      // two-bit-per-iteration dividers. ISA-neutral; changes timing only, so
      // compare against references measured on the same configuration.
      ,integer_support: (1 << e_basic)
      ,muldiv_support : (1 << e_idiv) | (1 << e_imul) | (1 << e_imulh)
      ,fpu_support    : (1 << e_fma) | (1 << e_fdivsqrt)
`endif
      ,default: "inv"
      };
  `bp_aviary_derive_cfg(bp_unicore_zynqparrot_prefetch16k_cfg_p
                        ,bp_unicore_zynqparrot_prefetch16k_cfg_override_p
                        ,bp_unicore_zynqparrot_prefetch_cfg_p
                        );

  parameter bp_proc_param_s [max_cfgs-1:0] all_cfgs_gp =
  {
    bp_unicore_zynqparrot_prefetch16k_cfg_p
    ,bp_unicore_zynqparrot_prefetch5_cfg_p
    ,bp_unicore_zynqparrot_prefetch10_cfg_p
    ,bp_unicore_zynqparrot_prefetch_cfg_p
    ,bp_multicore_zynqparrot_cfg_p
    ,bp_unicore_zynqparrot_cfg_p

    // A custom BP configuration generated from Makefile
    ,bp_custom_cfg_p
    // The default BP
    ,bp_default_cfg_p
  };

  // This enum MUST be kept up to date with the parameter array above
  typedef enum bit [lg_max_cfgs-1:0]
  {
    e_bp_unicore_zynqparrot_prefetch16k_cfg         = 7
    ,e_bp_unicore_zynqparrot_prefetch5_cfg           = 6
    ,e_bp_unicore_zynqparrot_prefetch10_cfg          = 5
    ,e_bp_unicore_zynqparrot_prefetch_cfg           = 4
    ,e_bp_multicore_zynqparrot_cfg                  = 3
    ,e_bp_unicore_zynqparrot_cfg                    = 2

    // A custom BP configuration generated from `defines
    ,e_bp_custom_cfg                                = 1
    // The default BP
    ,e_bp_default_cfg                               = 0
  } bp_params_e;

  `include "bp_common_bedrock_pkgdef.svh"
  `include "bp_common_cache_pkgdef.svh"
  `include "bp_common_cache_engine_pkgdef.svh"
  `include "bp_common_cfg_bus_pkgdef.svh"
  `include "bp_common_clint_pkgdef.svh"
  `include "bp_common_core_pkgdef.svh"
  `include "bp_common_host_pkgdef.svh"
  `include "bp_common_rv64_pkgdef.svh"

endpackage
