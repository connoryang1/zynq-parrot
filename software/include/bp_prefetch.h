#ifndef BP_PREFETCH_H
#define BP_PREFETCH_H

/* Standard Zicbop prefetch.r with offset zero. The ORI-to-x0 encoding keeps
 * this header usable with assemblers that do not recognize the mnemonic.
 *
 * This is a nonfaulting, best-effort hint, with no register result or ordering
 * guarantee. BlackParrot currently accepts permitted DTLB hits to cacheable,
 * idempotent DRAM in its noncoherent writeback configuration and may drop a
 * hint for any unavailable translation or cache/request capacity. Unsupported
 * hardware executes it as a no-op; qualify actual request issuance in a trace
 * before interpreting benchmark timing. The memory clobber constrains the
 * compiler, not the hardware memory-ordering model.
 */
#define BP_PREFETCH_R_ASM(base) "ori zero, " base ", 1\n"

static inline void bp_prefetch_r(const volatile void *address)
{
  __asm__ volatile (BP_PREFETCH_R_ASM("%0") : : "r"(address) : "memory");
}

#endif
