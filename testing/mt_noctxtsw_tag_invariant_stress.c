/**
 * mt_noctxtsw_tag_invariant_stress.c
 *
 * This test stresses ordinary single-thread execution while simulator-only
 * assertions verify that every added physical-thread tag and selector stays
 * zero.  It never executes a context-switch or remote-context CSR.
 */

#include <stdint.h>
#include "bp_utils.h"

#define ITERATIONS 512u
#define MEMORY_WORDS 256u
#define TRAP_ITERATIONS 64u
#define TRAP_INFLIGHT_MAGIC 0x747261705f746167ULL

struct trap_record {
  uint64_t last_mcause;
  uint64_t count;
};

static volatile struct trap_record traps __attribute__((aligned(64)));
// A nonzero initializer keeps this in the loaded data image.  Each external
// run therefore starts clean, while an unexpected in-target restart retains a
// magic value because crt0 does not reinitialize .data.
static volatile uint64_t trap_inflight = ~TRAP_INFLIGHT_MAGIC;
static volatile uint64_t memory_words[MEMORY_WORDS] __attribute__((aligned(64)));
static volatile uint64_t atomic_word __attribute__((aligned(64)));

uintptr_t handle_trap(uintptr_t epc, uintptr_t mcause, uintptr_t mtval,
                      uintptr_t regs[32])
{
  (void)regs;
  (void)mtval;

  traps.last_mcause = mcause;
  traps.count++;
  trap_inflight = 0;
  return epc + 4;
}

static inline uint64_t load_u64(const volatile void *p)
{
  uint64_t v;
  __asm__ volatile("ld %0, 0(%1)" : "=r"(v) : "r"(p) : "memory");
  return v;
}

static inline uint64_t load_u32(const volatile void *p)
{
  uint64_t v;
  __asm__ volatile("lwu %0, 0(%1)" : "=r"(v) : "r"(p) : "memory");
  return v;
}

static inline uint64_t load_u16(const volatile void *p)
{
  uint64_t v;
  __asm__ volatile("lhu %0, 0(%1)" : "=r"(v) : "r"(p) : "memory");
  return v;
}

static inline uint64_t load_u8(const volatile void *p)
{
  uint64_t v;
  __asm__ volatile("lbu %0, 0(%1)" : "=r"(v) : "r"(p) : "memory");
  return v;
}

static inline void store_u64(volatile void *p, uint64_t v)
{
  __asm__ volatile("sd %0, 0(%1)" : : "r"(v), "r"(p) : "memory");
}

static inline void store_u32(volatile void *p, uint64_t v)
{
  __asm__ volatile("sw %0, 0(%1)" : : "r"(v), "r"(p) : "memory");
}

static inline void store_u16(volatile void *p, uint64_t v)
{
  __asm__ volatile("sh %0, 0(%1)" : : "r"(v), "r"(p) : "memory");
}

static inline void store_u8(volatile void *p, uint64_t v)
{
  __asm__ volatile("sb %0, 0(%1)" : : "r"(v), "r"(p) : "memory");
}

static uint64_t __attribute__((noinline)) branch_dependency_mix(uint64_t x, uint64_t i)
{
  switch (i & 7u) {
    case 0: x = (x << 7) ^ (x >> 3) ^ i; break;
    case 1: x = (x + 0x9e3779b97f4a7c15ULL) ^ (i << 17); break;
    case 2: x = (x - i) ^ (x << 11); break;
    case 3: x = (x | (i + 1u)) + (x >> 13); break;
    case 4: x = (x & ~(i << 9)) ^ (x >> 19); break;
    case 5: x = (x ^ 0xd1b54a32d192ed03ULL) + i; break;
    case 6: x = (x << (i & 31u)) | (x >> ((64u - i) & 63u)); break;
    default: x = (x * 33u) ^ (i + (x >> 29)); break;
  }

  __asm__ volatile(
      "add %0, %0, %1\n"
      "xor %0, %0, %1\n"
      "sub %0, %0, %1\n"
      : "+r"(x) : "r"(i));
  return x;
}

static void fail(const char *message)
{
  bp_print_string(message);
  bp_finish(1);
  for (;;)
    ;
}

int main(void)
{
  uint64_t start_cycle;
  uint64_t end_cycle;
  uint64_t state = 0x243f6a8885a308d3ULL;

  if (trap_inflight == TRAP_INFLIGHT_MAGIC) {
    trap_inflight = 0;
    fail("[BSG-FAIL] trap redirected to startup instead of returning\n");
  }

  traps.count = 0;
  traps.last_mcause = 0;
  trap_inflight = 0;
  __asm__ volatile("csrr %0, cycle" : "=r"(start_cycle));

  bp_print_string("=== no-context-switch tag invariant stress ===\n");

  for (uint64_t i = 0; i < ITERATIONS; i++) {
    uint64_t idx = (i * 73u + (state >> 11)) & (MEMORY_WORDS - 1u);
    volatile uint8_t *p = (volatile uint8_t *)&memory_words[idx];
    uint64_t seed = state ^ (i * 0x94d049bb133111ebULL);
    uint64_t byte = (seed >> 9) & 0xffu;
    uint64_t half = (seed >> 21) & 0xffffu;
    uint64_t word = (seed >> 32) & 0xffffffffu;
    uint64_t expected;

    store_u64(p, seed);
    if (load_u64(p) != seed)
      fail("[BSG-FAIL] 64-bit load/store dependency mismatch\n");

    store_u8(p, byte);
    store_u16(p + 2, half);
    store_u32(p + 4, word);
    expected = (word << 32) | (seed & 0xff00ULL) | (half << 16) | byte;
    if (load_u8(p) != byte || load_u16(p + 2) != half
        || load_u32(p + 4) != word || load_u64(p) != expected)
      fail("[BSG-FAIL] mixed-width memory operation mismatch\n");
    if (i == 0)
      bp_print_string("[BSG-INFO] memory phase completed\n");

    state = branch_dependency_mix(expected ^ state, i);
    if (i == 0)
      bp_print_string("[BSG-INFO] branch/dependency phase completed\n");

    if ((i & 31u) == 0) {
      uint64_t old;
      __asm__ volatile("amoadd.d %0, %2, (%1)"
                       : "=r"(old) : "r"(&atomic_word), "r"(1ULL) : "memory");
      if (old != (i >> 5))
        fail("[BSG-FAIL] atomic return/dependency mismatch\n");
      if (i == 0)
        bp_print_string("[BSG-INFO] atomic phase completed\n");
      __asm__ volatile("sfence.vma x0, x0" : : : "memory");
      if (i == 0)
        bp_print_string("[BSG-INFO] sfence.vma phase completed\n");
      __asm__ volatile("fence.i" : : : "memory");
      if (i == 0)
        bp_print_string("[BSG-INFO] fence.i phase completed\n");
    }

    if ((i & 127u) == 0) {
      uint64_t misa, mstatus;
      __asm__ volatile("csrr %0, misa" : "=r"(misa));
      __asm__ volatile("csrr %0, mstatus" : "=r"(mstatus));
      if (misa == 0)
        fail("[BSG-FAIL] ordinary CSR read mismatch\n");
    }
  }

  bp_print_string("[BSG-INFO] ordinary instruction stress completed\n");
  for (uint64_t i = 0; i < TRAP_ITERATIONS; i++) {
    trap_inflight = TRAP_INFLIGHT_MAGIC;
    __asm__ volatile(".word 0xffffffff" : : : "memory");
    if (trap_inflight != 0)
      fail("[BSG-FAIL] trap handler did not clear its sentinel\n");
  }
  bp_print_string("[BSG-INFO] trap/return phase completed\n");

  __asm__ volatile("csrr %0, cycle" : "=r"(end_cycle));

  if (traps.count != TRAP_ITERATIONS || traps.last_mcause != 2u)
    fail("[BSG-FAIL] trap/return stress mismatch\n");
  if (atomic_word != (ITERATIONS / 32u))
    fail("[BSG-FAIL] final atomic state mismatch\n");
  if (end_cycle <= start_cycle)
    fail("[BSG-FAIL] cycle CSR did not advance\n");

  bp_print_string("[BSG-PASS] no-context-switch tag invariant stress completed\n");
  bp_finish(0);
  return 0;
}
