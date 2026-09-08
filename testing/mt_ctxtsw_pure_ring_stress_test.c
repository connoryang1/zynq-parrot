/**
 * mt_ctxtsw_pure_ring_stress_test.c
 *
 * Dense 4-context context-switch ring with no bookkeeping between its eight
 * consecutive switches. A final untimed lap records each peer's logical ID
 * after that stream completes. This is a stress/regression test, not a benchmark.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS < 2 || BP_NUM_CONTEXTS < 4
#error "The four-context ring requires at least two banks and four logical contexts"
#endif

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];
static volatile uint64_t peer_contexts[3] __attribute__((used, aligned(8)));

#define RECORD_COMPLETION(offset) \
    "la t0, peer_contexts\n" \
    "csrr t1, 0x800\n" \
    "sd t1, " offset "(t0)\n" \
    "fence rw, rw\n"

void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    RECORD_COMPLETION("0")
    "csrwi 0x800, 2\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t2_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    RECORD_COMPLETION("8")
    "csrwi 0x800, 3\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t3_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    RECORD_COMPLETION("16")
    "csrwi 0x800, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

int main(void) {
  bp_print_string("=== Pure Context-Switch Ring Stress Test ===\n");
  bp_print_string("4 contexts, 8 consecutive csrwi per context, no loop bookkeeping.\n");

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  __asm__ volatile(
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
  );

  /* Each peer is suspended at the end of its eighth switch. Resume all three
   * once more to collect completion evidence outside the dense stream. */
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");
  for (unsigned i = 0; i < 3; ++i) {
    if (peer_contexts[i] != i + 1) {
      bp_print_string("[BSG-FAIL] pure ctxtsw ring peer completion missing\n");
      bp_finish(1);
      return 1;
    }
  }

  bp_print_string("[BSG-PASS] pure ctxtsw ring stress completed\n");
  bp_finish(0);
  return 0;
}
