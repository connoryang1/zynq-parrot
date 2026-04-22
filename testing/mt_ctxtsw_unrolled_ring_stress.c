#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v));
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v));
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t entry) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, entry);
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ring(void) {
  __asm__ volatile(
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "csrwi 0x081, 2\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t2_ring(void) {
  __asm__ volatile(
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "csrwi 0x081, 3\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t3_ring(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "csrwi 0x081, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

int main(void) {
  bp_print_string("=== Pure unrolled ctxtsw ring stress ===\n");
  bp_print_string("4 contexts, 8 consecutive csrwi per context, no loop bookkeeping.\n");

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  __asm__ volatile(
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
    "csrwi 0x081, 1\n"
  );

  bp_print_string("[BSG-PASS] pure unrolled ctxtsw ring stress completed\n");
  bp_finish(0);
  return 0;
}
