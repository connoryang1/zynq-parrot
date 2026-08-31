#ifndef MT_SEED_H
#define MT_SEED_H

#include <stdint.h>

/* CSR seeding helpers for BlackParrot hardware threading.
 *
 * CSR 0x800 (CTXT)    : read/write current thread ID; write triggers NPC redirect
 * CSR 0x801 (CTXT_NPC): seed the NPC for a target thread
 *   bits [38:0]                    = NPC (vaddr_width_p = 39)
 *   bits [38+BP_CONTEXT_BITS : 39] = logical context ID
 * CSR 0x802 (CTXT_REG): seed an integer or FP register for a target thread
 *   bits [38:0]                    = value (sign-extended to vaddr_width_p)
 *   bits [38+BP_CONTEXT_BITS : 39] = logical context ID
 *   bits [38+BP_CONTEXT_BITS+5 : 39+BP_CONTEXT_BITS] = register address (5-bit)
 *   bit  [39+BP_CONTEXT_BITS+5]    = fp_sel (1 = FP regfile, 0 = INT regfile)
 *
 * Set BP_NUM_THREADS and BP_NUM_CONTEXTS before including this header
 * (or pass -DBP_NUM_THREADS=N -DBP_NUM_CONTEXTS=M) to match RTL elaboration.
 * BP_NUM_CONTEXTS defaults to BP_NUM_THREADS.
 */

#ifndef BP_NUM_THREADS
#define BP_NUM_THREADS 4
#endif

#ifndef BP_NUM_CONTEXTS
#define BP_NUM_CONTEXTS BP_NUM_THREADS
#endif

#if   BP_NUM_CONTEXTS <= 2
#  define BP_CONTEXT_BITS 1
#elif BP_NUM_CONTEXTS <= 4
#  define BP_CONTEXT_BITS 2
#elif BP_NUM_CONTEXTS <= 8
#  define BP_CONTEXT_BITS 3
#elif BP_NUM_CONTEXTS <= 16
#  define BP_CONTEXT_BITS 4
#elif BP_NUM_CONTEXTS <= 32
#  define BP_CONTEXT_BITS 5
#elif BP_NUM_CONTEXTS <= 64
#  define BP_CONTEXT_BITS 6
#else
#  error "BP_NUM_CONTEXTS > 64 not supported"
#endif

#define BP_CONTEXT_MASK ((1ULL << BP_CONTEXT_BITS) - 1ULL)
#define BP_NPC_MASK  0x7FFFFFFFFFULL        /* vaddr_width_p = 39 */
#define BP_VAL_MASK  0x7FFFFFFFFFULL
#define BP_REG_MASK  0x1FULL                /* 5-bit register address */
#define BP_CONTEXT_SHIFT 39                 /* vaddr_width_p */
#define BP_REG_SHIFT (BP_CONTEXT_SHIFT + BP_CONTEXT_BITS)
#define BP_FP_SHIFT  (BP_REG_SHIFT + 5)

static inline void seed_npc(uint64_t context_id, uint64_t npc) {
  uint64_t v = ((context_id & BP_CONTEXT_MASK) << BP_CONTEXT_SHIFT) | (npc & BP_NPC_MASK);
  __asm__ volatile("csrw 0x801, %0" : : "r"(v) : "memory");
}

static inline void seed_reg(uint64_t context_id, uint64_t reg, uint64_t val) {
  uint64_t v = (val & BP_VAL_MASK)
             | ((context_id & BP_CONTEXT_MASK) << BP_CONTEXT_SHIFT)
             | ((reg & BP_REG_MASK) << BP_REG_SHIFT);
  __asm__ volatile("csrw 0x802, %0" : : "r"(v) : "memory");
}

static inline void seed_fp_reg(uint64_t context_id, uint64_t reg, uint64_t val) {
  /* val is written directly into the FP regfile storage encoding. For recoded
   * FP implementations this is not the same as an IEEE double bit pattern. */
  uint64_t v = (val & BP_VAL_MASK)
             | ((context_id & BP_CONTEXT_MASK) << BP_CONTEXT_SHIFT)
             | ((reg & BP_REG_MASK) << BP_REG_SHIFT)
             | (1ULL << BP_FP_SHIFT);
  __asm__ volatile("csrw 0x802, %0" : : "r"(v) : "memory");
}

/* Convenience: seed gp, sp, and NPC for a thread. */
static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t entry) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));
  seed_reg(tid, 3 /* gp */, gp_val);
  seed_reg(tid, 2 /* sp */, (uint64_t)stack_top);
  seed_npc(tid, entry);
}

#endif /* MT_SEED_H */
