TOP ?= $(shell git rev-parse --show-toplevel)
include $(TOP)/Makefile.env

CC     := $(ZP_INSTALL_DIR)/bin/riscv64-unknown-elf-gcc
CFLAGS := -O2 \
          -I$(ZP_INSTALL_DIR)/riscv64-unknown-elf/include \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/dramfs.specs \
          --specs=$(ZP_INSTALL_DIR)/riscv64-unknown-elf/lib/perch.specs

SIM_DIR := $(TOP)/cosim/black-parrot-minimal-example/verilator

TESTS := \
    multithreading_demo \
    mt_csr_isolation_test \
    mt_benchmark \
    mt_ctxtsw_microbench \
    mt_ctxtsw_repeat_benchmark \
    mt_ctxtsw_partial_unroll_benchmark \
    mt_ctxtsw_hotness_benchmark \
    mt_ctxtsw_boundary_benchmark \
    mt_frf_isolation_test \
    mt_banyan_benchmark \
    mt_regfile_test

.PHONY: all clean help $(addprefix run-, $(TESTS))

all: $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))

define TEST_RULES
$(ZP_RISCV_DIR)/bp-tests/$(1).riscv: $(TOP)/testing/$(1).c
	$$(CC) -o $$@ $$< $$(CFLAGS)

run-$(1): $(ZP_RISCV_DIR)/bp-tests/$(1).riscv
	rm -f $$(SIM_DIR)/prog.riscv $$(SIM_DIR)/prog.mem $$(SIM_DIR)/prog.nbf
	$$(MAKE) -C $$(SIM_DIR) run PROG=$(1)
endef
$(foreach t,$(TESTS),$(eval $(call TEST_RULES,$(t))))

clean::
	$(RM) $(addprefix $(ZP_RISCV_DIR)/bp-tests/, $(addsuffix .riscv, $(TESTS)))

help:
	@echo "Targets:"
	@echo "  make all              compile all tests"
	@echo "  make run-<test>       compile (if stale) and run one test"
	@echo ""
	@echo "Available tests:"
	@$(foreach t,$(TESTS),echo "  $(t)";)
