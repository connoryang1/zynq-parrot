#ifndef BP_LOAD_AHEAD_H
#define BP_LOAD_AHEAD_H

/* Faulting cache warming for BlackParrot's existing load-miss path.
 *
 * This is one ordinary byte load to x0, not a nonfaulting prefetch hint. Use
 * only a currently readable, cacheable data address: translation/permission
 * faults and MMIO side effects remain ordinary load behavior. The byte access
 * imposes no alignment requirement. It adds no outstanding-miss capacity.
 * The compiler barrier keeps surrounding memory operations on their intended
 * side; it is not a hardware fence or a guarantee of asynchronous completion.
 */
#define BP_LOAD_AHEAD_ASM(base) "lbu zero, 0(" base ")\n"

static inline void bp_load_ahead(const volatile void *address)
{
  __asm__ volatile (BP_LOAD_AHEAD_ASM("%0") : : "r"(address) : "memory");
}

#endif
