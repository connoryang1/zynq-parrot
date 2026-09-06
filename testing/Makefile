TOP ?= $(shell git rev-parse --show-toplevel)
include $(TOP)/Makefile.env

# Ensure LOG_DIR is a solid absolute path
LOG_DIR := $(shell pwd)/logs

# Preserve the simulator's exit status when concise run output is filtered.
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c

# Default NUM_THREADS if not specified on command line
NUM_THREADS ?= 4
NUM_CONTEXTS ?= $(NUM_THREADS)

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
    mt_abi_preservation_test \
    mt_ctxtsw_gpr_ring_stress \
    mt_ctxtsw_late_wb_hazard_test \
    mt_ctxtsw_pure_ring_stress_test

BENCHMARKS :=

NONRESIDENT_TESTS :=

TESTS := $(SMOKE_TESTS) $(CORRECTNESS_TESTS) $(BENCHMARKS) $(NONRESIDENT_TESTS)

.PHONY: all clean build-sim rebuild-sim help $(addprefix run-, $(TESTS))

all: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))

$(LOG_DIR):
	@mkdir -p $@

define TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/$(1).riscv: $(TOP)/testing/$(1).c $(TOP)/testing/mt_seed.h | $(LOG_DIR)
	@echo "  [CC]    Compiling $(1).riscv (Threads: $(NUM_THREADS))..."
	@$$(CC) -o $$@ $$< $$(CFLAGS) >> $(LOG_DIR)/software_build.log 2>&1

run-$(1): $(ZP_RISCV_DIR)/bp-tests/$(1).riscv
	@echo "  [CLEAN] Refreshing $(1) environment..."
	@rm -f $$(SIM_DIR)/prog.riscv $$(SIM_DIR)/prog.mem $$(SIM_DIR)/prog.nbf
	@echo "  [RUN]   Executing $(1) in simulator..."
	@set +e; \
	$$(MAKE) -C $$(SIM_DIR) run PROG=$(1) NUM_THREADS=$$(NUM_THREADS) NUM_CONTEXTS=$$(NUM_CONTEXTS) $$(if $$(TRACE),TRACE=$$(TRACE),) | grep -E "$$(RUN_LOG_FILTER)"; \
	sim_rc=$$$${PIPESTATUS[0]}; \
	set -e; \
	if (( sim_rc != 0 )) \
	   && ! { grep -q "BSG PASS" $$(SIM_DIR)/run.log \
	           && grep -q "final block executed before fini() was called" $$(SIM_DIR)/run.log; }; then \
		exit $$$$sim_rc; \
	fi
	@! grep -Eq "CORE FAIL|\\[BSG-FAIL\\]|BSG FAIL|trace timeout reached" $$(SIM_DIR)/run.log
	@if grep -Eq "Assertion failed|%Error:|Aborting" $$(SIM_DIR)/run.log \
		&& ! { grep -q "BSG PASS" $$(SIM_DIR)/run.log \
		       && grep -q "final block executed before fini() was called" $$(SIM_DIR)/run.log; }; then \
		echo "ERROR: simulator reported a fatal error before a successful guest result"; \
		exit 1; \
	fi
endef

$(foreach t,$(TESTS),$(eval $(call TEST_RULES,$(t))))

clean::
	@echo "  [RM] Cleaning build artifacts..."
	@$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))
	@$(RM) -rf $(LOG_DIR)

build-sim: | $(LOG_DIR)
	@echo "  [MODEL] Building Verilator model (Threads: $(NUM_THREADS))..."
	@$(MAKE) -C $(SIM_DIR) build $(if $(filter-out 4,$(NUM_THREADS)),NUM_THREADS=$(NUM_THREADS),) > $(LOG_DIR)/verilator_build.log 2>&1 || \
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
