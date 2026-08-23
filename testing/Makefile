TOP ?= $(shell git rev-parse --show-toplevel)
include $(TOP)/Makefile.env

# Ensure LOG_DIR is a solid absolute path
LOG_DIR := $(shell pwd)/logs

# Default NUM_THREADS if not specified on command line
NUM_THREADS ?= 4
NUM_CONTEXTS ?= $(NUM_THREADS)
SCALE_SWITCHES ?= 2048
SCALE_WARMUP ?= 256
SCALE_UNROLL ?= 256
SCALE_ALIGN ?= 64
SCALE_SAME_LOOP ?= 1

CC     := $(ZP_INSTALL_DIR)/bin/riscv64-unknown-elf-gcc
LD     := $(ZP_INSTALL_DIR)/bin/riscv64-unknown-elf-ld
OBJCOPY := $(ZP_INSTALL_DIR)/bin/riscv64-unknown-elf-objcopy
CFLAGS = -O2 \
          -I$(ZP_INSTALL_DIR)/riscv64-unknown-elf/include \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/dramfs.specs \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/perch.specs \
          -DNUM_THREADS=$(NUM_THREADS) \
          -DBP_NUM_THREADS=$(NUM_THREADS) \
          -DBP_NUM_CONTEXTS=$(NUM_CONTEXTS)

SIM_DIR := $(TOP)/cosim/black-parrot-minimal-example/verilator
FPGA_CRT_SRC_DIR := $(TOP)/import/black-parrot-sdk/libgloss-dramfs/misc
FPGA_BUILD_DIR := $(LOG_DIR)/fpga
FPGA_CRT_OBJ := $(FPGA_BUILD_DIR)/dramfs_integer_crt0.o
FPGA_SMOKE_TESTS := \
    mt_fpga_current_toolchain_smoke \
    mt_ctxtsw_fpga_stage_test
FPGA_CORRECTNESS_TESTS := \
    mt_ctxtsw_nonresident_ring_test \
    mt_ctxtsw_gpr_ring_stress \
    mt_ctxtsw_late_wb_hazard_test
FPGA_BENCHMARKS := \
    mt_ctxtsw_nonresident_cold_icache_benchmark
FPGA_TESTS := $(FPGA_SMOKE_TESTS) $(FPGA_CORRECTNESS_TESTS) $(FPGA_BENCHMARKS)
BP_NBF_SCRIPT := $(TOP)/import/black-parrot/bp_common/software/py/nbf.py
RUN_LOG_FILTER := ps.cpp:|BSG-INFO:|\[STAGE\]|Benchmark|minstret|Contexts:|Switches/context:|Warmup|Unroll|Same-loop|Total cycles:|Total switches:|Measured throughput|Excess cycles|Expected TRACE

SMOKE_TESTS := \
    mt_csr_isolation_test \
    mt_ctxtsw_smoke_test \
    mt_frf_isolation_test \
    mt_regfile_test

CORRECTNESS_TESTS := \
    mt_abi_preservation_test \
    mt_ctxtsw_asid_translation_test \
    mt_ctxtsw_4ctx_ring_isolation \
    mt_ctxtsw_gpr_ring_stress \
    mt_ctxtsw_late_wb_hazard_test \
    mt_ctxtsw_privilege_isolation_test \
    mt_ctxtsw_pure_ring_stress_test

BENCHMARKS := \
    mt_ctxtsw_roundtrip_benchmark \
    mt_ctxtsw_gap8_benchmark \
    mt_ctxtsw_ring_throughput_benchmark \
    mt_ctxtsw_ring_overhead_benchmark \
    mt_ctxtsw_nonresident_fp_overhead_benchmark \
    mt_ctxtsw_nonresident_gpr_overhead_benchmark \
    mt_ctxtsw_nonresident_cold_icache_benchmark \
    mt_ctxtsw_nonresident_overhead_benchmark \
    mt_ctxtsw_single_overhead_benchmark \
    mt_ctxtsw_banyan_poll_worker_benchmark \
    mt_ctxtsw_predictor_pollution \
    mt_ctxtsw_return_predictor_test

BEST_CONTEXT_BENCHMARKS := \
    ctxtsw_benchmark

DEMOS := \
    multithreading_demo

EXPERIMENTAL_TESTS := \
    mt_fpga_current_toolchain_smoke \
    mt_ctxtsw_context_cache_cooperative_image \
    mt_context_cache_l1_service_test \
    mt_ctxtsw_nonresident_fp_ring_test \
    mt_ctxtsw_nonresident_fp_target_test \
    mt_ctxtsw_fpga_stage_test \
    mt_ctxtsw_nonresident_ring_test \
    mt_ctxtsw_nonresident_target_test \
    mt_ctxtsw_sv39_asid_remap_test

# These tests deliberately address logical contexts beyond the two physical
# resident slots.  Keep their software and simulator configurations coupled so
# a default four-thread build cannot silently turn the cold path into a
# resident context switch.
NONRESIDENT_TESTS := \
    mt_fpga_current_toolchain_smoke \
    mt_ctxtsw_nonresident_fp_overhead_benchmark \
    mt_ctxtsw_nonresident_gpr_overhead_benchmark \
    mt_ctxtsw_nonresident_cold_icache_benchmark \
    mt_ctxtsw_nonresident_overhead_benchmark \
    mt_ctxtsw_nonresident_fp_ring_test \
    mt_ctxtsw_nonresident_fp_target_test \
    mt_ctxtsw_fpga_stage_test \
    mt_ctxtsw_nonresident_ring_test \
    mt_ctxtsw_nonresident_target_test

NONRESIDENT_TARGETS := \
    $(addprefix run-,$(NONRESIDENT_TESTS)) \
    $(addprefix $(ZP_RISCV_DIR)/bp-tests/,$(addsuffix .riscv,$(NONRESIDENT_TESTS)))

$(NONRESIDENT_TARGETS): NUM_THREADS=2
$(NONRESIDENT_TARGETS): NUM_CONTEXTS=4

SCALE_CONTEXTS := 8 16 32 64
SCALE_TESTS := $(foreach n,$(SCALE_CONTEXTS),mt_ctxtsw_$(n)ctx_ring_throughput_benchmark)

TESTS := $(SMOKE_TESTS) $(CORRECTNESS_TESTS) $(BENCHMARKS) $(DEMOS)

.PHONY: all clean build-sim rebuild-sim $(addprefix rebuild-sim-, $(addsuffix ctx, $(SCALE_CONTEXTS))) help $(addprefix run-, $(TESTS) $(EXPERIMENTAL_TESTS) $(SCALE_TESTS) $(BEST_CONTEXT_BENCHMARKS))

all: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))

.PHONY: fpga-tests fpga-smoke-tests fpga-correctness-tests fpga-benchmarks
fpga-tests: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.nbf, $(FPGA_TESTS)))
fpga-smoke-tests: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.nbf, $(FPGA_SMOKE_TESTS)))
fpga-correctness-tests: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.nbf, $(FPGA_CORRECTNESS_TESTS)))
fpga-benchmarks: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.nbf, $(FPGA_BENCHMARKS)))

$(LOG_DIR):
	@mkdir -p $@

$(FPGA_CRT_OBJ): $(TOP)/testing/mt_fpga_early_start.S \
                 $(FPGA_CRT_SRC_DIR)/crt0.S \
                 $(FPGA_CRT_SRC_DIR)/crtmain.S \
                 $(FPGA_CRT_SRC_DIR)/tls.c \
                 $(FPGA_CRT_SRC_DIR)/traps.c \
                 $(FPGA_CRT_SRC_DIR)/main.c | $(LOG_DIR)
	@echo "  [CRT]   Building integer-only FPGA startup..."
	@mkdir -p $(FPGA_BUILD_DIR)
	@$(CC) -c $(TOP)/testing/mt_fpga_early_start.S -o $(FPGA_BUILD_DIR)/early.o \
		-I$(FPGA_CRT_SRC_DIR) -I$(TOP)/import/black-parrot-sdk/libgloss-dramfs \
		-D__ASSEMBLY__ -mcmodel=medany -mstrict-align
	@$(CC) -c $(FPGA_CRT_SRC_DIR)/crt0.S -o $(FPGA_BUILD_DIR)/crt0.o \
		-I$(FPGA_CRT_SRC_DIR) -I$(TOP)/import/black-parrot-sdk/libgloss-dramfs \
		-D__ASSEMBLY__ -D_start=dramfs_start -U__riscv_flen \
		-mcmodel=medany -mstrict-align
	@$(CC) -c $(FPGA_CRT_SRC_DIR)/crtmain.S -o $(FPGA_BUILD_DIR)/crtmain.o \
		-I$(FPGA_CRT_SRC_DIR) -I$(TOP)/import/black-parrot-sdk/libgloss-dramfs \
		-D__ASSEMBLY__ -mcmodel=medany -mstrict-align
	@for src in tls traps main; do \
		$(CC) -c $(FPGA_CRT_SRC_DIR)/$$src.c -o $(FPGA_BUILD_DIR)/$$src.o \
		-I$(FPGA_CRT_SRC_DIR) -I$(TOP)/import/black-parrot-sdk/libgloss-dramfs \
		-fno-common -fno-builtin -mcmodel=medany -nostdlib -nostartfiles -mstrict-align; \
	done
	@$(LD) -r -o $@ $(FPGA_BUILD_DIR)/early.o $(FPGA_BUILD_DIR)/crt0.o \
		$(FPGA_BUILD_DIR)/crtmain.o $(FPGA_BUILD_DIR)/tls.o \
		$(FPGA_BUILD_DIR)/traps.o $(FPGA_BUILD_DIR)/main.o

define FPGA_TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/$(1)_fpga.riscv: $(TOP)/testing/$(1).c $(FPGA_CRT_OBJ) $(TOP)/testing/mt_seed.h | $(LOG_DIR)
	@echo "  [CC]    Compiling $(1)_fpga.riscv (Threads: $$(NUM_THREADS), Contexts: $$(NUM_CONTEXTS))..."
	@$$(CC) -o $$@ $$(FPGA_CRT_OBJ) $$< $$(CFLAGS) -nostartfiles >> $(LOG_DIR)/software_build.log 2>&1

$(ZP_RISCV_DIR)/bp-tests/$(1)_fpga.mem: $(ZP_RISCV_DIR)/bp-tests/$(1)_fpga.riscv
	@$$(OBJCOPY) -O verilog $$< $$@
	@sed -i "s/@8/@0/g" $$@

$(ZP_RISCV_DIR)/bp-tests/$(1)_fpga.nbf: $(ZP_RISCV_DIR)/bp-tests/$(1)_fpga.mem
	@echo "  [NBF]   Packaging $(1)_fpga.nbf with config preamble..."
	@python3 $$(BP_NBF_SCRIPT) --skip_zeros --config --debug \
		--mem $$< --ncpus 1 > $$@
endef

$(foreach t,$(FPGA_TESTS),$(eval $(call FPGA_TEST_RULES,$(t))))

define TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/$(1).riscv: $(TOP)/testing/$(1).c $(TOP)/testing/mt_seed.h $(TOP)/testing/mt_context_image.h | $(LOG_DIR)
	@echo "  [CC]    Compiling $(1).riscv (Threads: $$(NUM_THREADS), Contexts: $$(NUM_CONTEXTS))..."
	@$$(CC) -o $$@ $$< $$(CFLAGS) >> $(LOG_DIR)/software_build.log 2>&1

run-$(1): $(ZP_RISCV_DIR)/bp-tests/$(1).riscv
	@echo "  [CLEAN] Refreshing $(1) environment..."
	@rm -f $$(SIM_DIR)/prog.riscv $$(SIM_DIR)/prog.mem $$(SIM_DIR)/prog.nbf
	@echo "  [RUN]   Executing $(1) in simulator..."
	@$$(MAKE) -C $$(SIM_DIR) run PROG=$(1) NUM_THREADS=$$(NUM_THREADS) NUM_CONTEXTS=$$(NUM_CONTEXTS) $$(if $$(TRACE),TRACE=$$(TRACE),) | grep -E "$$(RUN_LOG_FILTER)"
	@! grep -Eq "CORE FAIL|\\[BSG-FAIL\\]" $$(SIM_DIR)/run.log
endef

$(foreach t,$(TESTS) $(EXPERIMENTAL_TESTS),$(eval $(call TEST_RULES,$(t))))

$(ZP_RISCV_DIR)/bp-tests/mt_ctxtsw_gap8_benchmark.riscv: $(TOP)/testing/mt_ctxtsw_gap_benchmark_common.h

$(ZP_RISCV_DIR)/bp-tests/ctxtsw_benchmark.riscv: NUM_THREADS=16
$(ZP_RISCV_DIR)/bp-tests/ctxtsw_benchmark.riscv: $(TOP)/testing/ctxtsw_benchmark.c $(TOP)/testing/mt_seed.h | $(LOG_DIR)
	@echo "  [CC]    Compiling ctxtsw_benchmark.riscv (Threads: 16)..."
	@$(CC) -o $@ $< $(CFLAGS) >> $(LOG_DIR)/software_build.log 2>&1

run-ctxtsw_benchmark: NUM_THREADS=16
run-ctxtsw_benchmark: $(ZP_RISCV_DIR)/bp-tests/ctxtsw_benchmark.riscv
	@echo "  [CLEAN] Refreshing ctxtsw_benchmark environment..."
	@rm -f $(SIM_DIR)/prog.riscv $(SIM_DIR)/prog.mem $(SIM_DIR)/prog.nbf
	@echo "  [RUN]   Executing ctxtsw_benchmark in 16-context simulator..."
	@$(MAKE) -C $(SIM_DIR) run PROG=ctxtsw_benchmark NUM_THREADS=16 NUM_CONTEXTS=16 $(if $(TRACE),TRACE=$(TRACE),) | grep -E "$(RUN_LOG_FILTER)"
	@! grep -Eq "CORE FAIL|\[BSG-FAIL\]" $(SIM_DIR)/run.log

define SCALE_TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/mt_ctxtsw_$(1)ctx_ring_throughput_benchmark.riscv: NUM_THREADS=$(1)
$(ZP_RISCV_DIR)/bp-tests/mt_ctxtsw_$(1)ctx_ring_throughput_benchmark.riscv: $(TOP)/testing/mt_ctxtsw_8ctx_ring_throughput_benchmark.c $(TOP)/testing/mt_seed.h $(TOP)/testing/Makefile | $(LOG_DIR)
	@echo "  [CC]    Compiling mt_ctxtsw_$(1)ctx_ring_throughput_benchmark.riscv (Threads: $(1))..."
	@$$(CC) -o $$@ $$< $$(CFLAGS) -DNUM_CONTEXTS=$(1) -DSWITCHES_PER_CONTEXT=$$(SCALE_SWITCHES) -DWARMUP_SWITCHES_PER_CONTEXT=$$(SCALE_WARMUP) -DUNROLL_FACTOR=$$(SCALE_UNROLL) -DHOT_ALIGN_MODE=$$(SCALE_ALIGN) -DSAME_LOOP_WARMUP=$$(SCALE_SAME_LOOP) >> $(LOG_DIR)/software_build.log 2>&1

run-mt_ctxtsw_$(1)ctx_ring_throughput_benchmark: NUM_THREADS=$(1)
run-mt_ctxtsw_$(1)ctx_ring_throughput_benchmark: $(ZP_RISCV_DIR)/bp-tests/mt_ctxtsw_$(1)ctx_ring_throughput_benchmark.riscv
	@echo "  [CLEAN] Refreshing mt_ctxtsw_$(1)ctx_ring_throughput_benchmark environment..."
	@rm -f $$(SIM_DIR)/prog.riscv $$(SIM_DIR)/prog.mem $$(SIM_DIR)/prog.nbf
	@echo "  [RUN]   Executing mt_ctxtsw_$(1)ctx_ring_throughput_benchmark in $(1)-context simulator..."
	@$$(MAKE) -C $$(SIM_DIR) run PROG=mt_ctxtsw_$(1)ctx_ring_throughput_benchmark NUM_THREADS=$(1) NUM_CONTEXTS=$(1) $$(if $$(TRACE),TRACE=$$(TRACE),) | grep -E "$$(RUN_LOG_FILTER)"
	@! grep -Eq "CORE FAIL|\\[BSG-FAIL\\]" $$(SIM_DIR)/run.log
endef

$(foreach n,$(SCALE_CONTEXTS),$(eval $(call SCALE_TEST_RULES,$(n))))

clean::
	@echo "  [RM] Cleaning build artifacts..."
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS) $(EXPERIMENTAL_TESTS) $(SCALE_TESTS) $(BEST_CONTEXT_BENCHMARKS)))
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.riscv, $(FPGA_TESTS)))
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.mem, $(FPGA_TESTS)))
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix _fpga.nbf, $(FPGA_TESTS)))
	@$(RM) -rf $(LOG_DIR)

build-sim: | $(LOG_DIR)
	@echo "  [MODEL] Building Verilator model (Threads: $(NUM_THREADS), Contexts: $(NUM_CONTEXTS))..."
	@$(MAKE) -C $(SIM_DIR) build NUM_THREADS=$(NUM_THREADS) NUM_CONTEXTS=$(NUM_CONTEXTS) > $(LOG_DIR)/verilator_build.log 2>&1 || \
		(echo "ERROR: Verilator build failed. Check $(LOG_DIR)/verilator_build.log"; exit 1)
	@echo "  [SUCCESS] Model ready."

rebuild-sim:
	@echo "  [CLEAN] Removing old Verilator objects (obj_dir)..."
	@rm -rf $(SIM_DIR)/obj_dir $(SIM_DIR)/bsg_blackparrot_pkg.sv
	@$(MAKE) build-sim

define SCALE_SIM_RULES
rebuild-sim-$(1)ctx:
	@$$(MAKE) rebuild-sim NUM_THREADS=$(1)
endef

$(foreach n,$(SCALE_CONTEXTS),$(eval $(call SCALE_SIM_RULES,$(n))))

help:
	@echo "Targets:"
	@echo "  make all                compile all tests"
	@echo "  make run-<test>         compile and run one test"
	@echo "  make build-sim          build hardware model"
	@echo "  make rebuild-sim        clean hardware and rebuild"
	@echo "  make rebuild-sim-Nctx   clean hardware and rebuild for N contexts (8/16/32/64)"
	@echo "  SCALE_SWITCHES=N        measured switches/context for scale benchmarks (default: 2048)"
	@echo "  SCALE_WARMUP=N          unmeasured warmup switches/context (default: 256)"
	@echo "  SCALE_UNROLL=N          straight-line csrw unroll factor (default: 256)"
	@echo "  SCALE_ALIGN=0|64        hot-region alignment mode (default: 64)"
	@echo "  SCALE_SAME_LOOP=0|1     reuse one hot loop body for warmup and measurement (default: 1)"
	@echo "  make run-ctxtsw_benchmark"
	@echo "                          run hardcoded 16-context best-case benchmark"
	@echo ""
	@echo "Smoke tests:"
	@$(foreach t,$(SMOKE_TESTS),echo "  $(t)";)
	@echo ""
	@echo "Correctness tests:"
	@$(foreach t,$(CORRECTNESS_TESTS),echo "  $(t)";)
	@echo ""
	@echo "Benchmarks:"
	@$(foreach t,$(BENCHMARKS),echo "  $(t)";)
	@echo ""
	@echo "Demos:"
	@$(foreach t,$(DEMOS),echo "  $(t)";)
	@echo ""
	@echo "Experimental tests:"
	@$(foreach t,$(EXPERIMENTAL_TESTS),echo "  $(t)";)
	@echo ""
	@echo "Scale tests:"
	@$(foreach t,$(SCALE_TESTS),echo "  $(t)";)
	@echo ""
	@echo "Best-case benchmark:"
	@$(foreach t,$(BEST_CONTEXT_BENCHMARKS),echo "  $(t)";)
