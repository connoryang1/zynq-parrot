// This is an implementation of the standardized host bsg_zynq_pl API
// that can be swapped out with a separate implementation to run on the PS
//

#ifndef BSG_ZYNQ_PL_H
#define BSG_ZYNQ_PL_H

#include "bsg_axil.h"
#include "bsg_nonsynth_dpi_clock_gen.hpp"
#include "bsg_nonsynth_dpi_gpio.hpp"
#include "bsg_peripherals.h"
#include "bsg_printing.h"
#include "zynq_headers.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <new>
#include <stdio.h>
#include <string>

#include "Vbsg_nonsynth_zynq_testbench.h"
#include "Vbsg_nonsynth_zynq_testbench___024root.h"
#include "Vbsg_nonsynth_zynq_testbench_bp_be_csr__Bz2.h"
#include "bsg_zynq_pl_simulation.h"
#include "verilated.h"

extern "C" {
void bsg_dpi_finish(void);
int bsg_dpi_time(void);
}

class bsg_zynq_pl : public bsg_zynq_pl_simulation {
    std::unique_ptr<VerilatedContext> contextp;
    std::unique_ptr<Vbsg_nonsynth_zynq_testbench> tb;

  public:
    bsg_zynq_pl(int argc, char *argv[]) {

        // Create verilated context
        contextp = std::make_unique<VerilatedContext>();

        // Set debug level, 0 is off, 9 is highest presently used
        contextp->debug(0);

        // Randomization reset policy
        contextp->randReset(2);

        // Verilator must compute traced signals
        contextp->traceEverOn(true);

        // Initialize Verilators variables
        contextp->commandArgs(argc, argv);

        // Create the TB pointer
        tb = std::make_unique<Vbsg_nonsynth_zynq_testbench>(contextp.get(),
                                                            "TOP");
        tick();
        init();
    }

    ~bsg_zynq_pl(void) {
        // The AXI wrappers own DPI GPIO objects. Their destructors must call
        // bsg_dpi_fini() while the Verilated module still exists and before
        // final blocks check that every exported DPI endpoint was released.
        co_list.clear();
        axi_gp0.reset();
        axi_gp1.reset();
        axi_gp2.reset();
        axi_hp0.reset();
        axi_hp1.reset();
        axi_hp2.reset();
        axi_sp0.reset();
        axi_sp1.reset();
        axi_sp2.reset();
        axi_mp0.reset();
        axi_mp1.reset();
        axi_mp2.reset();
        tb->final();
        contextp->statsPrintSummary();
    }

    // Each bsg_timekeeper::next() moves to the next clock edge
    //   so we need 2 to perform one full clock cycle.
    // If your design does not evaluate things on negedge, you could omit
    //   the first eval, but BSG designs tend to do assertions on negedge
    //   at the least.
    void tick(void) override {
        tb->eval();
        bsg_nonsynth_dpi::bsg_timekeeper::next();
        tb->eval();
        bsg_nonsynth_dpi::bsg_timekeeper::next();
    }

    int done(void) override {
        bsg_pr_info("  bsg_zynq_pl: done() called, exiting\n");
        return status;
    }

    // Fast initialization for the simulation-only AXI RAM. top_zynq.sv maps
    // a guest DRAM address by removing 0x8000_0000 and adding the low 32 bits
    // of the allocated physical base. Mirror that mapping exactly here.
    void initialize_dram_word(uint64_t guest_addr, uint64_t data,
                              unsigned bytes, unsigned long physical_base) {
        assert(guest_addr >= 0x80000000ULL);
        assert(bytes == 4 || bytes == 8);
        const uint32_t translated =
            static_cast<uint32_t>(guest_addr ^ 0x80000000ULL)
            + static_cast<uint32_t>(physical_base);
        auto &ram = tb->rootp
            ->bsg_nonsynth_zynq_testbench__DOT__axi_mem__DOT__ram;
        for (unsigned byte = 0; byte < bytes; ++byte) {
            const uint32_t address = translated + byte;
            const uint32_t index = (address >> 2) & 0x0fffffffU;
            const uint32_t shift = (address & 3U) * 8U;
            const uint32_t mask = 0xffU << shift;
            ram[index] = (ram[index] & ~mask)
                         | ((static_cast<uint32_t>(data >> (byte * 8U)) & 0xffU)
                            << shift);
        }
    }

    void zero_dram(unsigned long physical_base, size_t bytes) {
        assert((bytes & 3U) == 0);
        auto &ram = tb->rootp
            ->bsg_nonsynth_zynq_testbench__DOT__axi_mem__DOT__ram;
        const uint32_t base_index =
            (static_cast<uint32_t>(physical_base) >> 2) & 0x0fffffffU;
        for (size_t word = 0; word < bytes / 4; ++word)
            ram[(base_index + word) & 0x0fffffffU] = 0;
    }

    // Report enough architectural state to identify an early-boot loop when
    // the simulated program has not brought up its console yet. This is a
    // simulation-only observation of Verilator state; it does not perturb RTL.
    void print_processor_state(void) {
#ifdef GP1_ENABLE
        // The full-system wrapper instantiates the processor hierarchy rather
        // than the minimal core hierarchy used by this optional reporter.
        bsg_pr_info("ps.cpp: processor state reporter unavailable in full-system topology\n");
#else
        auto *root = tb->rootp;
        auto *csr = root
            ->__PVT__bsg_nonsynth_zynq_testbench__DOT__dut__DOT__top_fpga_inst__DOT__blackparrot__DOT__core_minimal__DOT__be__DOT__calculator__DOT__pipe_sys__DOT__csr__DOT__gen_csr__BRA__0__KET____DOT__csr_inst;
        const unsigned long long next_pc = root
            ->bsg_nonsynth_zynq_testbench__DOT__dut__DOT__top_fpga_inst__DOT__blackparrot__DOT__core_minimal__DOT__fe__DOT__pc_gen__DOT__next_pc;
        const unsigned long long expected_npc = root
            ->bsg_nonsynth_zynq_testbench__DOT__dut__DOT__top_fpga_inst__DOT__blackparrot__DOT__core_minimal__DOT__be__DOT__expected_npc_lo;

        bsg_pr_info("ps.cpp: processor state: next_pc=0x%llx expected_npc=0x%llx\n",
                    next_pc, expected_npc);
        bsg_pr_info("ps.cpp: processor state: debug=%u privilege=%u mcause=0x%x\n",
                    csr->__PVT__debug_mode_reg__DOT__data_r,
                    csr->__PVT__priv_mode_reg__DOT__data_r,
                    csr->__PVT__mcause_reg__DOT__data_r);
        // The generated members expose BlackParrot's compact CSR storage:
        // EPCs omit bit 0 and mtvec omits its two fixed alignment bits.
        bsg_pr_info("ps.cpp: processor state: mepc=0x%llx dpc=0x%llx mtvec=0x%llx satp=0x%llx\n",
                    (unsigned long long)csr->__PVT__mepc_reg__DOT__data_r << 1,
                    (unsigned long long)csr->__PVT__dpc_reg__DOT__data_r << 1,
                    (unsigned long long)csr->__PVT__mtvec_reg__DOT__data_r << 2,
                    (unsigned long long)csr->__PVT__satp_reg__DOT__data_r);
#endif
    }

    void *allocate_dram(unsigned long len_in_bytes,
                        unsigned long *physical_ptr) {
        // The simulated physical address is this host pointer. Preserve the
        // guest's page offset when translating DRAM addresses, or an aligned
        // guest cache-line burst can spuriously cross an AXI 4 KiB boundary.
        // posix_memalign accepts arbitrary byte counts and remains free()-able.
        void *virtual_ptr = nullptr;
        *physical_ptr = 0;
        const int error = posix_memalign(&virtual_ptr, 4096, len_in_bytes);
        if (error != 0) {
            bsg_pr_err("  bsg_zynq_pl: DRAM allocation of %lu bytes failed: %s\n",
                       len_in_bytes, std::strerror(error));
            // Callers program the returned address without a null check.
            // Fail before they can install a bogus DRAM base or access it.
            throw std::bad_alloc();
        }
        bsg_pr_info("  bsg_zynq_pl: Allocated dummy DRAM\n");
        *physical_ptr = (unsigned long)virtual_ptr;

        return virtual_ptr;
    }

    void free_dram(void *virtual_ptr) {
        bsg_pr_info("  bsg_zynq_pl: Freeing dummy DRAM\n");
        free(virtual_ptr);
    }
};

#endif
