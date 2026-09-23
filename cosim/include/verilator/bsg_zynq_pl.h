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
