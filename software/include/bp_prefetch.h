#ifndef BP_PREFETCH_H
#define BP_PREFETCH_H

/* Standard Zicbop prefetch.r with offset zero. The ORI-to-x0 encoding keeps
 * this header usable with assemblers that do not recognize the mnemonic.
 *
 * This is a nonfaulting, best-effort hint, with no register result or ordering
 * guarantee. BlackParrot accepts permitted DTLB hits to cacheable DRAM in its
 * noncoherent writeback configuration and may drop a hint for missing
 * translations or cache/request capacity. In the current configuration an
 * accepted hint requests 16 bytes into the D-cache side buffer; it does not
 * install a full L1 line. A later load of either returned word can hit that
 * buffer. Unsupported hardware executes it as a no-op. Qualify request issue
 * and useful demand consumption in a trace before interpreting timing. The
 * memory clobber constrains the compiler, not hardware memory ordering.
 */
#define BP_PREFETCH_R_ASM(base) "ori zero, " base ", 1\n"

static inline void bp_prefetch_r(const volatile void *address)
{
  __asm__ volatile (BP_PREFETCH_R_ASM("%0") : : "r"(address) : "memory");
}

#endif
