# Makefile.env declares clean first; never make bare invocation destructive.
.DEFAULT_GOAL := help
TOP ?= $(shell git rev-parse --show-toplevel)
include $(TOP)/Makefile.env

# Ensure LOG_DIR is a solid absolute path
LOG_DIR := $(shell pwd)/logs

# Preserve the simulator's exit status when concise run output is filtered.
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c

# Default to the accepted static FPGA topology, including SRAM eviction.
NUM_THREADS ?= 2
NUM_CONTEXTS ?= 4

CC     := $(ZP_INSTALL_DIR)/bin/riscv64-unknown-elf-gcc
CFLAGS = -O2 \
          -I$(ZP_INSTALL_DIR)/riscv64-unknown-elf/include \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/dramfs.specs \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/perch.specs \
          -DNUM_THREADS=$(NUM_THREADS) \
          -DBP_NUM_THREADS=$(NUM_THREADS) \
          -DBP_NUM_CONTEXTS=$(NUM_CONTEXTS)

SIM_DIR := $(TOP)/cosim/black-parrot-minimal-example/verilator
RUN_LOG_FILTER := ps.cpp:|BSG-INFO:|Benchmark|minstret|Contexts:|Switches/context:|Warmup|Unroll|Same-loop|Total cycles:|Total switches:|Measured throughput|Excess cycles|Expected TRACE|Fatal:|%Error:|Aborting|CORE PASS|CORE FAIL|BSG PASS|BSG FAIL

SMOKE_TESTS := \
    mt_csr_isolation_test \
    mt_ctxtsw_smoke_test \
    mt_ctxtsw_logical_csr_readback_test \
    mt_frf_isolation_test \
    mt_regfile_test

CORRECTNESS_TESTS := \
    mt_umode_resident_sv39_data_handoff_test \
    mt_ctxtsw_register_target_test \
    mt_abi_preservation_test \
    mt_ctxtsw_gpr_ring_stress \
    mt_ctxtsw_late_wb_hazard_test \
    mt_ctxtsw_pure_ring_stress_test

BENCHMARKS := \
    mt_ctxtsw_nonresident_overhead_benchmark

NONRESIDENT_TESTS := \
    mt_umode_nonresident_handoff_test \
    mt_umode_nonresident_sv39_handoff_test \
    mt_umode_nonresident_sv39_data_handoff_test

TESTS := $(SMOKE_TESTS) $(CORRECTNESS_TESTS) $(BENCHMARKS) $(NONRESIDENT_TESTS)

.PHONY: all clean build-sim rebuild-sim help check-harness FORCE $(addprefix run-, $(TESTS))

# Test programs are small. Recompile to prevent stale topology/flag combinations
# even when a user alternates A -> B -> A with the same output ELF name.
FORCE:

all: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))

$(LOG_DIR):
	@mkdir -p $@

define TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/$(1).riscv: $(TOP)/testing/$(1).c $(TOP)/testing/mt_seed.h FORCE | $(LOG_DIR)
	@echo "  [CC]    Compiling $(1).riscv (Threads: $(NUM_THREADS))..."
	@$$(CC) -o $$@ $$< $$(CFLAGS) >> $(LOG_DIR)/software_build.log 2>&1

run-$(1): $(ZP_RISCV_DIR)/bp-tests/$(1).riscv
	@echo "  [CLEAN] Refreshing $(1) environment..."
	@rm -f $$(SIM_DIR)/prog.riscv $$(SIM_DIR)/prog.mem $$(SIM_DIR)/prog.nbf $$(SIM_DIR)/run.log
	@$$(MAKE) -C $$(SIM_DIR) build NUM_THREADS=$$(NUM_THREADS) NUM_CONTEXTS=$$(NUM_CONTEXTS) $$(if $$(TRACE),TRACE=$$(TRACE),) > $(LOG_DIR)/verilator_build.log 2>&1 || \
		{ echo "ERROR: model build failed; no previous runtime result is valid"; exit 1; }
	@echo "  [RUN]   Executing $(1) in simulator..."
	@set +e; \
	$$(MAKE) -C $$(SIM_DIR) run PROG=$(1) NUM_THREADS=$$(NUM_THREADS) NUM_CONTEXTS=$$(NUM_CONTEXTS) $$(if $$(TRACE),TRACE=$$(TRACE),) | grep -E "$$(RUN_LOG_FILTER)"; \
	sim_rc=$$$${PIPESTATUS[0]}; \
	set -e; \
	python3 $$(TOP)/testing/check_run.py $$(SIM_DIR)/run.log --exit-code $$$$sim_rc
endef

$(foreach t,$(TESTS),$(eval $(call TEST_RULES,$(t))))

$(ZP_RISCV_DIR)/bp-tests/mt_umode_nonresident_sv39_handoff_test.riscv: $(TOP)/testing/mt_umode_nonresident_handoff_test.c
$(ZP_RISCV_DIR)/bp-tests/mt_umode_nonresident_sv39_data_handoff_test.riscv: $(TOP)/testing/mt_umode_nonresident_handoff_test.c

.PHONY: check-nonresident-config
check-nonresident-config:
	@if (( $(NUM_THREADS) != 2 || $(NUM_CONTEXTS) != 4 )); then \
		echo "ERROR: maintained nonresident gates require NUM_THREADS=2 NUM_CONTEXTS=4"; \
		exit 1; \
	fi

run-mt_umode_nonresident_handoff_test: check-nonresident-config
run-mt_umode_resident_sv39_data_handoff_test: check-nonresident-config
run-mt_umode_nonresident_sv39_handoff_test: check-nonresident-config
run-mt_umode_nonresident_sv39_data_handoff_test: check-nonresident-config
run-mt_ctxtsw_nonresident_overhead_benchmark: check-nonresident-config

clean::
	@echo "  [RM] Cleaning build artifacts..."
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))
	@$(RM) -rf $(LOG_DIR)

build-sim: | $(LOG_DIR)
	@echo "  [MODEL] Building Verilator model (Threads: $(NUM_THREADS))..."
	@$(MAKE) -C $(SIM_DIR) build NUM_THREADS=$(NUM_THREADS) NUM_CONTEXTS=$(NUM_CONTEXTS) $(if $(TRACE),TRACE=$(TRACE),) > $(LOG_DIR)/verilator_build.log 2>&1 || \
		(echo "ERROR: Verilator build failed. Check $(LOG_DIR)/verilator_build.log"; exit 1)
	@echo "  [SUCCESS] Model ready."

rebuild-sim:
	@echo "  [CLEAN] Removing old Verilator objects (obj_dir)..."
	@rm -rf $(SIM_DIR)/obj_dir $(SIM_DIR)/bsg_blackparrot_pkg.sv
	@$(MAKE) build-sim

help:
	@echo "Targets:"
	@echo "  make all                compile all tests"
	@echo "  make run-<test>         compile and run one test"
	@echo "  make build-sim          build hardware model"
	@echo "  make rebuild-sim        clean hardware and rebuild"
	@echo "  make check-harness      run host-side verdict unit tests"
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
	@echo "Nonresident tests (run with NUM_THREADS=2 NUM_CONTEXTS=4):"
	@$(foreach t,$(NONRESIDENT_TESTS),echo "  $(t)";)

check-harness:
	@python3 -m unittest discover -s $(TOP)/testing -p test_check_run.py
