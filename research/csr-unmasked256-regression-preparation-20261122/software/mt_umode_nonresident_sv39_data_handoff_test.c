/*
 * Validate translated target-context instruction and data replay across a
 * nonresident SRAM-backed handoff. This wrapper enables Sv39 and forces a
 * target-side store before the target ECALL so both ITLB and DTLB paths run.
 */

#define BP_ENABLE_SV39 1
#define BP_TARGET_PRE_ECALL_STORE 1
#include "mt_umode_nonresident_handoff_test.c"
