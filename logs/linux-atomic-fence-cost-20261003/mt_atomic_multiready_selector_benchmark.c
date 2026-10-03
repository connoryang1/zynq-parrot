/* Atomic one-of-many ready selection with a preserved spectator context. */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS < 4
#error "Use two resident banks and at least four logical contexts"
#endif

#ifndef PEER_CONTEXT
#define PEER_CONTEXT 1
#endif

#if PEER_CONTEXT == 1
#define PEER_READY_BIT 2
#elif PEER_CONTEXT == 2
#define PEER_READY_BIT 4
#else
#error "PEER_CONTEXT must be resident context 1 or nonresident context 2"
#endif

#define TURNS 128
#define SAMPLES 16
#define STACK_WORDS 256
#define SPECTATOR_BIT 8
#define EXPECTED_READY (PEER_READY_BIT | SPECTATOR_BIT)
#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)

static uint64_t peer_stack[STACK_WORDS];
static volatile uint64_t ready_word __attribute__((aligned(64))) =
    EXPECTED_READY;
static volatile uint64_t observed_context __attribute__((aligned(64)));
static volatile uint64_t peer_complete __attribute__((aligned(64)));
static volatile uint64_t ring_sc_failures __attribute__((aligned(64)));
static volatile uint64_t peer_sc_failures __attribute__((aligned(64)));

static inline uint64_t cycles(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

#define LRSC_BODY(source_bit)                                                \
    "li t1, 0\n"                                                          \
    "1: lr.d.aq t4, (t2)\n"                                               \
    "beqz t4, 1b\n"                                                       \
    ".option arch, +zbb\n"                                                \
    "ctz t5, t4\n"                                                       \
    "li t6, 1\n"                                                         \
    "sll t6, t6, t5\n"                                                   \
    "not t6, t6\n"                                                       \
    "and t6, t4, t6\n"                                                   \
    "ori t6, t6, " STRINGIFY(source_bit) "\n"                           \
    "sc.d.rl t3, t6, (t2)\n"                                             \
    "beqz t3, 2f\n"                                                       \
    "addi t1, t1, 1\n"                                                   \
    "j 1b\n"                                                             \
    "2: csrw 0x800, t5\n"

static __attribute__((naked, noinline, noreturn, used, aligned(8)))
void peer_lrsc(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "la t2, ready_word\nli t0, 128\n"
    LRSC_BODY(PEER_READY_BIT)
    "addi t0, t0, -1\nbnez t0, 1b\n"
    "la t2, peer_sc_failures\nsd t1, 0(t2)\n"
    "la t2, observed_context\ncsrr t3, 0x800\nsd t3, 0(t2)\n"
    "la t2, peer_complete\nli t3, 1\nsd t3, 0(t2)\n"
    "fence rw, rw\ncsrw 0x800, zero\n3: j 3b\n.option pop\n"
    ::: "memory");
}

static __attribute__((noinline, aligned(8))) void ring_lrsc(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "la t2, ready_word\nli t0, 128\n"
    LRSC_BODY(1)
    "addi t0, t0, -1\nbnez t0, 1b\n"
    "la t2, ring_sc_failures\nsd t1, 0(t2)\n"
    ".option pop\n"
    ::: "t0", "t1", "t2", "t3", "t4", "t5", "t6", "memory");
}

static int trial(uint64_t *elapsed)
{
  ready_word = EXPECTED_READY;
  observed_context = UINT64_MAX;
  peer_complete = 0;
  ring_sc_failures = UINT64_MAX;
  peer_sc_failures = UINT64_MAX;
  seed_npc(PEER_CONTEXT, (uint64_t)peer_lrsc);
  __asm__ volatile("fence rw, rw" ::: "memory");
  uint64_t begin = cycles();
  ring_lrsc();
  __asm__ volatile("li t0, %0\ncsrw 0x800, t0"
                   :: "i"(PEER_CONTEXT) : "t0", "memory");
  *elapsed = cycles() - begin;
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  return observed_context == PEER_CONTEXT && peer_complete == 1
         && ready_word == EXPECTED_READY && source == 0
         && ring_sc_failures == 0 && peer_sc_failures == 0;
}

static void report(unsigned sample, uint64_t elapsed, int ok)
{
  bp_print_string("Atomic multiready sample/peer/cycles/x100-per-op/ok/"
                  "observed/complete/word/source/ring-sc/peer-sc: ");
  bp_hprint_uint64(sample); bp_print_string(" ");
  bp_hprint_uint64(PEER_CONTEXT); bp_print_string(" ");
  bp_hprint_uint64(elapsed); bp_print_string(" ");
  bp_hprint_uint64(elapsed * 100 / (2 * TURNS + 2)); bp_print_string(" ");
  bp_hprint_uint64((uint64_t)ok); bp_print_string(" ");
  bp_hprint_uint64(observed_context); bp_print_string(" ");
  bp_hprint_uint64(peer_complete); bp_print_string(" ");
  bp_hprint_uint64(ready_word); bp_print_string(" ");
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  bp_hprint_uint64(source); bp_print_string(" ");
  bp_hprint_uint64(ring_sc_failures); bp_print_string(" ");
  bp_hprint_uint64(peer_sc_failures); bp_print_string("\n");
}

int main(void)
{
  uint64_t elapsed;
  int pass = 1;
  seed_thread(PEER_CONTEXT, &peer_stack[STACK_WORDS], (uint64_t)peer_lrsc);
  for (unsigned sample = 0; sample < SAMPLES; ++sample) {
    int ok = trial(&elapsed);
    pass &= ok;
    report(sample, elapsed, ok);
  }
  if (!pass) {
    bp_print_string("[BSG-FAIL] atomic multiready selector\n");
    bp_finish(1);
    return 1;
  }
  bp_print_string("[BSG-PASS] atomic multiready selector\n");
  bp_finish(0);
  return 0;
}
