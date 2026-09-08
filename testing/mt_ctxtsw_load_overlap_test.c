/* Verify load-ahead data and register ownership across a resident handoff.
 * A trace must separately prove useful peer retirement before critical refill;
 * the program's PASS establishes correctness, not memory-overlap timing.
 * The x0 operation is an ordinary faulting byte load, not a prefetch hint.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_load_ahead.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "This test requires the maintained two-bank/four-context topology"
#endif

#define ROUNDS 8
struct cache_line { uint64_t value, padding[7]; };
#define LINE(n) { 0x9100000000000000ULL + (n), {0} }
static const volatile struct cache_line input[1 + 2 * ROUNDS]
  __attribute__((aligned(64), used)) = {
    LINE(0), LINE(1), LINE(2), LINE(3), LINE(4), LINE(5), LINE(6), LINE(7),
    LINE(8), LINE(9), LINE(10), LINE(11), LINE(12), LINE(13), LINE(14),
    LINE(15), LINE(16)
  };
static volatile uint64_t result[2] __attribute__((aligned(64), used));

/* Both contexts deliberately use a5. A delayed source load must update its
 * original bank without corrupting the peer's independent computation.
 */
static __attribute__((naked, noinline, used, aligned(64)))
uint64_t delayed_load(const volatile uint64_t *address)
{
  __asm__ volatile (
    ".option push\n.option norvc\n"
    "ld a5, 0(a0)\ncsrwi 0x800, 1\nmv a0, a5\nret\n"
    ".option pop\n");
}

/* Byte access accepts any readable byte address. It still translates, checks
 * permissions, can fault, and can access MMIO: use only valid cacheable data.
 * The demand load on resume verifies that the cache-warming request preserves
 * memory contents. Whether it hits is established by the waveform, not PASS.
 */
static __attribute__((naked, noinline, used, aligned(64)))
uint64_t load_ahead(const volatile uint64_t *address)
{
  __asm__ volatile (
    ".option push\n.option norvc\n"
    BP_LOAD_AHEAD_ASM("a0")
    "csrwi 0x800, 1\nld a0, 0(a0)\nret\n"
    ".option pop\n");
}

static __attribute__((naked, noinline, noreturn, used, aligned(64)))
void peer(void)
{
  __asm__ volatile (
    ".option push\n.option norvc\n"
    "mv a5, a1\n"
    ".global overlap_peer_work\noverlap_peer_work:\n"
    ".rept 32\naddi a5, a5, 3\n.endr\n"
    "sd a5, 0(a0)\ncsrr t0, 0x800\nsd t0, 8(a0)\n"
    "fence rw, rw\ncsrwi 0x800, 0\n1: j 1b\n"
    ".option pop\n");
}

static void trial(unsigned mode, unsigned line)
{
  const uint64_t operand = 0x1000 + line * 13;
  result[0] = result[1] = 0;
  seed_reg(1, 10, (uint64_t)result);
  seed_reg(1, 11, operand);
  seed_npc(1, (uint64_t)peer);
  const uint64_t observed = mode ? load_ahead(&input[line].value)
                                 : delayed_load(&input[line].value);
  uint64_t context;
  __asm__ volatile ("csrr %0, 0x800" : "=r"(context) : : "memory");
  if (observed != 0x9100000000000000ULL + line
      || result[0] != operand + 96 || result[1] != 1 || context != 0) {
    bp_print_string("[BSG-FAIL] load-ahead data/context/register mismatch\n");
    bp_finish(1);
  }
}

int main(void)
{
  for (unsigned mode = 0; mode < 2; ++mode) {
    /* Warm source and peer instruction paths without touching measured lines. */
    trial(mode, 0);
    for (unsigned round = 0; round < ROUNDS; ++round)
      trial(mode, 1 + mode * ROUNDS + round);
  }
  bp_print_string("[BSG-PASS] resident delayed-load and load-ahead data/register checks\n");
  bp_finish(0);
  return 0;
}
