/* Check writes made by a re-launched resident context before its first switch.
 * The source launches the same target entry twice without reseeding its GPRs.
 * Each launch initializes three registers, switches away, and verifies that
 * those new values survive when the target resumes.
 */
#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"
#ifdef BP_RELAUNCH_PREFETCH
#include "bp_prefetch.h"
#endif

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Resident relaunch regression requires two resident slots/four contexts"
#endif

#define T0_MARKER UINT64_C(0x12345678)
#define T1_MARKER UINT64_C(0x23456789)
#define A2_MARKER UINT64_C(0x3456789a)
#define PASS_MARKER UINT64_C(0x50415353)
#ifndef BP_RELAUNCH_ROUNDS
#define BP_RELAUNCH_ROUNDS 1
#endif
#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)

static volatile uint64_t result[5] __attribute__((aligned(64), used));
#ifdef BP_RELAUNCH_PREFETCH
static const volatile uint64_t probe __attribute__((aligned(64), used)) = 0xabcdef;
#define OPTIONAL_PREFETCH \
    "lla t2, probe\n" BP_PREFETCH_R_ASM("t2")
#define PASS_TEXT "[BSG-PASS] resident relaunch prefetch register preservation\n"
#define FAIL_TEXT "[BSG-FAIL] resident relaunch prefetch register preservation\n"
#else
#define OPTIONAL_PREFETCH
#define PASS_TEXT "[BSG-PASS] resident relaunch register preservation\n"
#define FAIL_TEXT "[BSG-FAIL] resident relaunch register preservation\n"
#endif

static void __attribute__((naked, noinline, noreturn, used, aligned(64)))
target(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n.option norelax\n"
    "li t0, 0x12345678\n"
    "li t1, 0x23456789\n"
    "li a2, 0x3456789a\n"
    "li a3, " STRINGIFY(BP_RELAUNCH_ROUNDS) "\n"
    "1:\n"
    OPTIONAL_PREFETCH
    "csrwi 0x800, 0\n"
    "li t2, 0x12345678\n"
    "bne t0, t2, 2f\n"
    "li t2, 0x23456789\n"
    "bne t1, t2, 2f\n"
    "li t2, 0x3456789a\n"
    "bne a2, t2, 2f\n"
    "addi a3, a3, -1\n"
    "bnez a3, 1b\n"
    "la t3, result\n"
    "li t4, 0x50415353\n"
    "sd t4, 0(t3)\n"
    "j 3f\n"
    "2: la t3, result\n"
    "sd t0, 8(t3)\n"
    "sd t1, 16(t3)\n"
    "sd a2, 24(t3)\n"
    "csrr t4, 0x800\n"
    "sd t4, 32(t3)\n"
    "3: fence rw, rw\n"
    "csrwi 0x800, 0\n"
    "4: j 4b\n"
    ".option pop\n"
    ::: "memory");
}

static int launch(unsigned number)
{
  for (unsigned i = 0; i < 5; ++i)
    result[i] = 0;
  __asm__ volatile("fence rw, rw" ::: "memory");
  seed_npc(1, (uint64_t)target);
  for (unsigned round = 0; round <= BP_RELAUNCH_ROUNDS; ++round)
    __asm__ volatile("csrwi 0x800, 1" ::: "memory");
  if (result[0] == PASS_MARKER)
    return 1;
  bp_print_string("[BSG-INFO] resident relaunch mismatch launch/t0/t1/a2/context: ");
  bp_hprint_uint64(number);
  for (unsigned i = 1; i < 5; ++i)
    bp_hprint_uint64(result[i]);
  bp_print_string("\n");
  return 0;
}

int main(void)
{
  int pass = launch(1) && launch(2);
  if (pass) {
    bp_print_string(PASS_TEXT);
    bp_finish(0);
  } else {
    bp_print_string(FAIL_TEXT);
    bp_finish(1);
  }
  return !pass;
}
