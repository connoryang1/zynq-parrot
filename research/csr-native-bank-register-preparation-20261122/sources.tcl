# Exact closed sources and native header-search order; both map to the397 production bridge.
set actual_sources [list \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/cosim/black-parrot-example/v/bp_common_pkg.sv} \
 {/run/user/1001/zp-linux-csr-unmasked256-trace0-cad-20261122-02/zynq-parrot-fpga-20261122T151115Z-a44c03bb7/cosim/black-parrot-example/vivado/bsg_blackparrot_pkg.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_be/src/include/bp_be_pkg.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_dff.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_dff_reset.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_dff_reset_set_clear.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_scan.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_encode_one_hot.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_priority_encode_one_hot_out.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc/bsg_priority_encode.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_be/src/v/bp_be_calculator/bp_be_csr.sv} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_be/src/v/bp_be_csr_wrapper_mt.sv}]
set actual_include_dirs [list \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/full01/verilator} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/cosim/include/common} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/cosim/include/verilator} \
 {/home/coyang/zynq-parrot-linux-research/install/include} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_mem} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot-subsystems/blackparrot/src} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/bsg_replicant/libraries} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_test} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/cosim/black-parrot-example/v} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_async} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_misc} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_noc} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/basejump_stl/bsg_tag} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot-subsystems/manycore/v} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_cache} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_dataflow} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_dmc} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_mem} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_misc} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_test} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/basejump_stl/bsg_noc} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/HardFloat/source} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/external/HardFloat/source/RISCV} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_common/src/include} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_fe/src/include} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_be/src/include} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_me/src/include} \
 {/run/user/1001/zp-csr-unmasked256-fullcore-20261122-01/source/import/black-parrot/bp_top/src/include}]
set actual_defines {BP_RETAINED_BUFFER=1 BP_RETAINED_I_LINES=256 BP_RETAINED_D_LINES=256 BP_RETAINED_SETS=256 BP_RETAINED_OBSERVE=1 BP_AXI_RESPONSE_DELAY=0 BP_CACHE_MISS_TRACE=0}
