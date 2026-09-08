This directory contains build support for ZynqParrot host environments and small target-side helpers. The load-ahead helper uses BlackParrot's existing memory instructions; its behavior and limits are described below.

## BlackParrot load-ahead helper

Include `bp_load_ahead.h` with `-Isoftware/include` to issue a discarded byte
load before doing independent work:

```c
#include "bp_load_ahead.h"

bp_load_ahead(address);
/* Independent computation, optionally in a resident context. */
value = *address;
```

The helper emits `lbu x0` and a compiler memory barrier. It is an ordinary
faulting load, not a nonfaulting prefetch hint: the address must be readable and
cacheable, and MMIO side effects are not suppressed. A byte access needs no
alignment, but this does not remove translation checks or add hardware miss
capacity. It neither fences hardware memory operations nor guarantees overlap.
Inspect generated code when measuring overlap: a compiler may move independent
register arithmetic even though memory operations respect the compiler barrier.

The [load-overlap test](../testing/mt_ctxtsw_load_overlap_test.c) checks data and
context ownership; the [matched benchmark](../testing/mt_load_ahead_benchmark.c)
compares scheduling choices. See [research direction](../PAPER_DIRECTION.md)
for measured results and the remaining application-level work.

# ZynqParrot Software Environments

This directory is used to cross-compile software support for ZynqParrot hosts. Currently supported are x86, Zynq 7000 and Zynq UltraScale+. By running the setup here, users will be able to use their host x86 system and compile programs that run on Zynq. As a proof of concept, Verilator is provided as a cross-compiled example.

Makefile targets:
			# Set TARGET\_NAME to one of x86, pynqz2, ultra96v2
            xsa: Creates a default xsa file for the host selected
            environment-setup: Creates an environment setup script to init the cross-compile env
			verilator: Creates verilator bin which verilates on x86 but can be compiled on host
            clean: Removes working directory for specific target
