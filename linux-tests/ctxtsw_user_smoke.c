/*
 * Minimal user-mode Linux smoke test for the BlackParrot context-switch CSRs.
 *
 * The primary Linux context (0) seeds context 2 with a naked trampoline and
 * switches to it.  The trampoline immediately switches back to context 0.
 * It deliberately uses no stack, globals, libc, or ABI state in context 2:
 * this is a handoff demonstration, not an attempt to make context 2 a Linux
 * task.  On return, the original C function proves that its saved context was
 * restored correctly.
 */

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#define BP_CSR_CTXT      0x800
#define BP_CSR_CTXT_NPC  0x801
#define BP_CONTEXT_BITS  2
#define BP_NPC_MASK      UINT64_C(0x7fffffffff)
#define BP_CONTEXT_SHIFT 39
#define BP_TARGET_MAGIC  UINT64_C(0x4354585452475432)

static volatile uint64_t target_result[2] __attribute__((used, aligned(16)));

static inline uint64_t bp_read_context(void)
{
  uint64_t value;
  __asm__ volatile ("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

static inline void bp_seed_npc(uint64_t context, uintptr_t npc)
{
  uint64_t value = ((context & ((UINT64_C(1) << BP_CONTEXT_BITS) - 1))
                    << BP_CONTEXT_SHIFT)
                   | ((uint64_t)npc & BP_NPC_MASK);

  __asm__ volatile ("csrw 0x801, %0" : : "r"(value) : "memory");
}

/* Context 2 begins with an otherwise uninitialized architectural register
 * file.  Keep this entry entirely register/stack independent and never let it
 * fall through into compiler-generated code. */
static void __attribute__((naked, noinline, used)) context2_trampoline(void)
{
  __asm__ volatile (
    "lla t0, target_result\n\t"
    "li t1, 0x4354585452475432\n\t"
    "sd t1, 0(t0)\n\t"
    "csrr t1, 0x800\n\t"
    "sd t1, 8(t0)\n\t"
    "fence rw, rw\n\t"
    "csrwi 0x800, 0\n\t"
    "1: j 1b\n\t"
  );
}

int main(void)
{
  const uint64_t initial = bp_read_context();

  printf("[BP-LINUX-CTXTSW] initial context=%" PRIu64 "\n", initial);
  if (initial != 0) {
    puts("[BP-LINUX-CTXTSW] FAIL: Linux did not start in context 0");
    return 1;
  }

  puts("[BP-LINUX-CTXTSW] seeding context 2 trampoline");
  fflush(stdout);
  bp_seed_npc(2, (uintptr_t)context2_trampoline);

  puts("[BP-LINUX-CTXTSW] switching 0 -> 2 -> 0");
  fflush(stdout);
  __asm__ volatile ("csrwi 0x800, 2" : : : "memory");

  printf("[BP-LINUX-CTXTSW] target marker=0x%016" PRIx64
         " target context=%" PRIu64 "\n",
         target_result[0], target_result[1]);
  if (target_result[0] != BP_TARGET_MAGIC || target_result[1] != 2) {
    puts("[BP-LINUX-CTXTSW] FAIL: target-side evidence is invalid");
    return 1;
  }

  const uint64_t resumed = bp_read_context();
  printf("[BP-LINUX-CTXTSW] resumed context=%" PRIu64 "\n", resumed);
  if (resumed != 0) {
    puts("[BP-LINUX-CTXTSW] FAIL: resumed in the wrong context");
    return 1;
  }

  puts("[BP-LINUX-CTXTSW] PASS: user-mode context handoff completed");
  return 0;
}
