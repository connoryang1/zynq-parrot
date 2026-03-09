# testing/Makefile
#
# Compile and run BlackParrot custom tests against the Verilator simulator.
#
# Usage:
#   make run-<test>    compile (if stale) and run a single test
#   make all           run all tests (no simulator rebuild)
#   make sim           rebuild the Verilator simulator from RTL (expensive)
#   make clean         delete compiled test binaries and NBF files
#   make help          list available tests and targets
#
# Examples:
#   make run-mt_frf_isolation_test
#   make run-mt_benchmark
#   make sim && make all

TOP  := $(shell git rev-parse --show-toplevel)
CURR := $(shell pwd)

include $(TOP)/Makefile.common

CC            := riscv64-unknown-elf-dramfs-gcc
RISCV_OBJCOPY := riscv64-unknown-elf-dramfs-objcopy
CFLAGS        := -march=rv64gc -mabi=lp64d -mcmodel=medany \
                 -I$(BP_SDK_INSTALL_DIR)/include
LDFLAGS       := -T$(BP_SDK_INSTALL_DIR)/linker/riscv.ld \
                 -L$(BP_SDK_LIB_DIR) \
                 -Wl,--whole-archive -lperchbm -Wl,--no-whole-archive

SRC_DIR := $(TOP)/testing
BIN_DIR := $(TOP)/testing/bin
VDIR    := $(TOP)/cosim/black-parrot-example/verilator
NBF_PY  := $(BP_COMMON_DIR)/software/py/nbf.py

# All tests — add new ones here
TESTS := \
    multithreading_demo \
    mt_csr_isolation_test \
    mt_benchmark \
    mt_frf_isolation_test \
    mt_banyan_benchmark \
    mt_regfile_test

.PHONY: all sim clean help

# Default: run all tests (simulator must already be built; use 'make sim' to rebuild)
all: $(addprefix run-, $(TESTS))

# Generate explicit compile + run rules for each test.
# Pattern rules combined with .PHONY are unreliable in GNU make, so we use
# eval/foreach to produce one concrete rule per test.
define TEST_RULES
.PHONY: run-$(1)
run-$(1): $(BIN_DIR)/$(1).nbf
	$$(MAKE) -C $(VDIR) run NBF_FILE=$(BIN_DIR)/$(1).nbf

$(BIN_DIR)/$(1).nbf: $(BIN_DIR)/$(1).riscv
	$(RISCV_OBJCOPY) -O verilog $$< $(BIN_DIR)/$(1).mem
	$(SED) -i "s/@8/@0/g" $(BIN_DIR)/$(1).mem
	$(PYTHON3) $(NBF_PY) --debug --skip_zeros --config --mem $(BIN_DIR)/$(1).mem --ncpus 1 > $$@
	rm $(BIN_DIR)/$(1).mem

$(BIN_DIR)/$(1).riscv: $(SRC_DIR)/$(1).c
	mkdir -p $(BIN_DIR)
	$(CC) -o $$@ $$< $(CFLAGS) $(LDFLAGS)
endef
$(foreach t,$(TESTS),$(eval $(call TEST_RULES,$(t))))

# Rebuild the Verilator simulator from RTL.
# Run this whenever RTL changes.
sim:
	$(MAKE) -C $(VDIR) obj_dir/Vbsg_nonsynth_zynq_testbench

clean:
	rm -rf $(BIN_DIR)

help:
	@echo "Targets:"
	@echo "  make run-<test>   compile (if stale) and run one test"
	@echo "  make all          compile (if stale) and run all tests"
	@echo "  make sim          rebuild Verilator simulator from RTL"
	@echo "  make clean        remove compiled test binaries and NBF files"
	@echo ""
	@echo "Available tests:"
	@$(foreach t,$(TESTS),echo "  $(t)";)
