#include <stdint.h>
#include "bp_utils.h"

/* The replay CSR consumes physical addresses. This bare-metal target runs
 * without address translation, so function addresses are also their physical
 * DRAM addresses. Keep every target on a distinct I-cache line and make the
 * bodies small enough that one 64-byte replay covers each complete function. */
#define REPLAY_TARGET(name, delta)                                      \
  static uint64_t __attribute__((naked, noinline, aligned(64), used))    \
  name(uint64_t value)                                                   \
  {                                                                      \
    __asm__ volatile("addi a0, a0, " #delta "\nret\n");                 \
  }

REPLAY_TARGET(replay_target_a, 17)
REPLAY_TARGET(replay_target_b, 29)
REPLAY_TARGET(replay_target_c, 41)
REPLAY_TARGET(replay_target_d, 53)
REPLAY_TARGET(replay_target_cancel, 61)

static void replay_enqueue(const void *paddr)
{
  uint64_t ready;
  do {
    __asm__ volatile("csrr %0, 0x7c0" : "=r"(ready));
  } while (!(ready & 1));
  __asm__ volatile("csrw 0x7c0, %0" : : "r"((uintptr_t)paddr) : "memory");
}

static void fail(void)
{
  bp_print_string("[BSG-FAIL] physical I-cache replay\n");
  bp_finish(1);
  for (;;) ;
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  /* Fill all four replay slots before executing any target. This exercises
   * queue backpressure as well as independent full-line response buffering. */
  replay_enqueue(replay_target_a);
  replay_enqueue(replay_target_b);
  replay_enqueue(replay_target_c);
  replay_enqueue(replay_target_d);
  for (volatile unsigned i = 0; i < 256; ++i)
    __asm__ volatile("nop");

  if (replay_target_a(100) != 117 || replay_target_b(100) != 129
      || replay_target_c(100) != 141 || replay_target_d(100) != 153)
    fail();

  /* fence.i must cancel the old replay epoch. An already-issued response may
   * return, but it must drain without publishing and ordinary demand must
   * still fetch and execute the target correctly. */
  replay_enqueue(replay_target_cancel);
  __asm__ volatile("fence.i" : : : "memory");
  if (replay_target_cancel(100) != 161)
    fail();

  /* A duplicate line is acknowledged rather than consuming another slot. */
  replay_enqueue(replay_target_a);
  replay_enqueue(replay_target_a);
  if (replay_target_a(7) != 24)
    fail();

  bp_print_string("[BSG-PASS] physical I-cache replay and fence cancellation\n");
  bp_finish(0);
  return 0;
}
