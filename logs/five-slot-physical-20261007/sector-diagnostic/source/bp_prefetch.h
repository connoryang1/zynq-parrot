#ifndef BP_PREFETCH_H
#define BP_PREFETCH_H

/* Standard Zicbop prefetch.r with offset zero. The ORI-to-x0 encoding keeps
 * this header usable with assemblers that do not recognize the mnemonic.
 *
 * This is a nonfaulting, best-effort hint, with no register result or ordering
 * guarantee. BlackParrot accepts permitted DTLB hits to cacheable DRAM in its
 * noncoherent writeback configuration and may drop a hint for missing
 * translations or cache/request capacity. Accepted hints now use the normal
 * demand-miss path (full-line request), so they can fill L1 state and satisfy
 * a later demand on the same line. Unsupported hardware executes it as a
 * no-op. Qualify actual request issuance and same-line demand completion in a
 * trace before interpreting benchmark timing. The memory clobber constrains the
 * compiler, not the hardware memory-ordering model.
 */
#define BP_PREFETCH_R_ASM(base) "ori zero, " base ", 1\n"

static inline void bp_prefetch_r(const volatile void *address)
{
  __asm__ volatile (BP_PREFETCH_R_ASM("%0") : : "r"(address) : "memory");
}

#endif
