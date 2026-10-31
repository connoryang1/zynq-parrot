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

/* A detached reply must not leave the UCE or memory link in a state that only
 * fails on a later architectural miss.  This body is deliberately larger
 * than L1-I and is executed after replay retirement to force ordinary refill
 * traffic instead of ending the test while the replayed prefix is still hot. */
static void __attribute__((naked, noinline, aligned(64), used))
post_replay_demand_stream(void)
{
  __asm__ volatile(
    ".rept 16384\n"
    "nop\n"
    ".endr\n"
    "ret\n");
}

static volatile uint64_t observed_status, observed_cause, observed_phase;

static void replay_enqueue(const void *paddr)
{
  uint64_t ready;
  do {
    __asm__ volatile("csrr %0, 0x7c0" : "=r"(ready));
  } while (!(ready & 1));
  __asm__ volatile("csrw 0x7c0, %0" : : "r"((uintptr_t)paddr) : "memory");
}

static void prefix_set(unsigned index, const void *paddr)
{
  uint64_t payload = ((uint64_t)index << 56) | (uintptr_t)paddr;
  __asm__ volatile("csrw 0x7c1, %0" : : "r"(payload) : "memory");
}

static uint64_t prefix_status(void)
{
  uint64_t status;
  __asm__ volatile("csrr %0, 0x5c0" : "=r"(status));
  return status;
}

static uint64_t wait_prefix_idle(void)
{
  uint64_t status;
  unsigned waits = 0;
  do {
    status = prefix_status();
    observed_status = status;
  } while ((status & (1UL << 1)) && ++waits < 10000);
  return status;
}

static void fail(void);

static void __attribute__((naked, noinline, used)) supervisor_prefix_trigger(void)
{
  __asm__ volatile(
    "li t0, 1\n"
    "csrw 0x5c0, t0\n"
    "ecall\n"
    "ret\n");
}

static void __attribute__((naked, aligned(4), used)) supervisor_trap(void)
{
  __asm__ volatile(
    "csrr t0, mcause\n"
    "la t2, observed_cause\n"
    "sd t0, 0(t2)\n"
    "li t1, 9\n"
    "bne t0, t1, 1f\n"
    "csrr t0, mepc\n"
    "addi t0, t0, 4\n"
    "csrw mepc, t0\n"
    /* Return from the S-mode ECALL in M mode. */
    "csrr t0, mstatus\n"
    "li t1, 0x1800\n"
    "not t1, t1\n"
    "and t0, t0, t1\n"
    "li t1, 0x1800\n"
    "or t0, t0, t1\n"
    "csrw mstatus, t0\n"
    "mret\n"
    "1: j fail\n");
}

static void __attribute__((naked, noinline)) enter_supervisor_trigger(void)
{
  __asm__ volatile(
    "csrw medeleg, zero\n"
    "la t0, supervisor_trap\n"
    "csrw mtvec, t0\n"
    "la t0, supervisor_prefix_trigger\n"
    "csrw mepc, t0\n"
    /* Select S mode as mret's destination. */
    "csrr t0, mstatus\n"
    "li t1, 0x1800\n"
    "not t1, t1\n"
    "and t0, t0, t1\n"
    "li t1, 0x800\n"
    "or t0, t0, t1\n"
    "csrw mstatus, t0\n"
    "mret\n");
}

static void fail(void)
{
  bp_print_string("[BSG-FAIL] shared-prefix I-cache replay\n");
  bp_print_string("phase/cause/status: ");
  bp_hprint_uint64(observed_phase);
  bp_hprint_uint64(observed_cause);
  bp_hprint_uint64(observed_status);
  bp_print_string("\n");
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

  /* Machine mode configures physical addresses once. A single trigger then
   * feeds the four-slot replay lane without exposing those addresses through
   * the supervisor trigger interface. A second trigger while active must be
   * counted and dropped, not restart or corrupt the running sequence. */
  prefix_set(0, replay_target_a);
  prefix_set(1, replay_target_b);
  prefix_set(2, replay_target_c);
  prefix_set(3, replay_target_d);
  __asm__ volatile("csrw 0x7c2, %0" : : "r"(4UL) : "memory");
  observed_phase = 1;
  enter_supervisor_trigger();
  observed_phase = 2;

  uint64_t status = wait_prefix_idle();
  observed_phase = 3;
  if (((status >> 4) & 0x1ff) != 4
      || ((status >> 22) & 0xffff) != 4
      || ((status >> 38) & 0xff) != 1
      || ((status >> 46) & 0xff) != 0)
    fail();

  for (volatile unsigned i = 0; i < 256; ++i)
    __asm__ volatile("nop");

  if (replay_target_a(100) != 117 || replay_target_b(100) != 129
      || replay_target_c(100) != 141 || replay_target_d(100) != 153)
    fail();

  /* Replaying the same prefix while all four completed lines remain in the
   * advisory buffer must query and drop them rather than withdrawing and
   * refetching them through the UCE. */
  observed_phase = 4;
  enter_supervisor_trigger();
  status = wait_prefix_idle();
  if (((status >> 22) & 0xffff) != 4
      || ((status >> 38) & 0xff) != 2
      || ((status >> 55) & 0x1ff) != 4)
    fail();

  /* fence.i invalidates completed advisory-buffer lines. The next trigger
   * must therefore admit the same four addresses again instead of reporting
   * stale residency. */
  observed_phase = 5;
  __asm__ volatile("fence.i" : : : "memory");
  enter_supervisor_trigger();
  status = wait_prefix_idle();
  if (((status >> 22) & 0xffff) != 8
      || ((status >> 38) & 0xff) != 3
      || ((status >> 55) & 0x1ff) != 4)
    fail();
  if (replay_target_a(200) != 217 || replay_target_b(200) != 229
      || replay_target_c(200) != 241 || replay_target_d(200) != 253)
    fail();

  post_replay_demand_stream();

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

  bp_print_string("[BSG-PASS] shared-prefix and physical I-cache replay\n");
  bp_finish(0);
  return 0;
}
