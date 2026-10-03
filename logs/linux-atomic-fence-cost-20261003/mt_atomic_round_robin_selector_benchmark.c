/* Fair three-context LR/SC scheduler: context 0 -> 1 -> 3 -> 0. */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS < 4
#error "Use two resident banks and at least four logical contexts"
#endif

#define TURNS 128
#define SAMPLES 16
#define STACK_WORDS 256
#define EXPECTED_READY 0xA
#define EXPECTED_COMPLETE 0xA
#define SWITCHES_PER_SAMPLE (3 * TURNS + 2)

static uint64_t peer1_stack[STACK_WORDS];
static uint64_t peer3_stack[STACK_WORDS];
static volatile uint64_t ready_word __attribute__((aligned(64))) =
    EXPECTED_READY;
static volatile uint64_t complete_word __attribute__((aligned(64)));
static volatile uint64_t sc_failures[4] __attribute__((aligned(64)));

static inline uint64_t cycles(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

#define ROUND_ROBIN_BODY                                                     \
    "li t1, 0\n"                                                          \
    "1: lr.d.aq t4, (t2)\n"                                               \
    "beqz t4, 1b\n"                                                       \
    "csrr t3, 0x800\n"                                                    \
    "addi t5, t3, 1\n"                                                    \
    ".option arch, +zbb\n"                                                \
    "ror t6, t4, t5\n"                                                    \
    "ctz t6, t6\n"                                                       \
    "add t5, t5, t6\n"                                                   \
    "andi t5, t5, 63\n"                                                  \
    "li t6, 1\n"                                                         \
    "sll t6, t6, t5\n"                                                   \
    "not t6, t6\n"                                                       \
    "and t6, t4, t6\n"                                                   \
    "li t4, 1\n"                                                         \
    "sll t4, t4, t3\n"                                                   \
    "or t6, t6, t4\n"                                                    \
    "sc.d.rl t4, t6, (t2)\n"                                             \
    "beqz t4, 2f\n"                                                       \
    "addi t1, t1, 1\n"                                                   \
    "j 1b\n"                                                             \
    "2: csrw 0x800, t5\n"

static __attribute__((naked, noinline, noreturn, used, aligned(8)))
void peer_round_robin(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "la t2, ready_word\nli t0, 128\n"
    ROUND_ROBIN_BODY
    "addi t0, t0, -1\nbnez t0, 1b\n"
    "csrr t3, 0x800\n"
    "la t2, sc_failures\nslli t4, t3, 3\nadd t2, t2, t4\n"
    "sd t1, 0(t2)\n"
    "li t4, 1\nsll t4, t4, t3\n"
    "la t2, complete_word\namoor.d.aqrl zero, t4, (t2)\n"
    "li t5, 3\nli t4, 1\nbeq t3, t4, 3f\nli t5, 0\n"
    "3: fence rw, rw\ncsrw 0x800, t5\n4: j 4b\n.option pop\n"
    ::: "memory");
}

static __attribute__((noinline, aligned(8))) void ring_round_robin(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "la t2, ready_word\nli t0, 128\n"
    ROUND_ROBIN_BODY
    "addi t0, t0, -1\nbnez t0, 1b\n"
    "la t2, sc_failures\nsd t1, 0(t2)\n"
    ".option pop\n"
    ::: "t0", "t1", "t2", "t3", "t4", "t5", "t6", "memory");
}

static int trial(uint64_t *elapsed)
{
  ready_word = EXPECTED_READY;
  complete_word = 0;
  for (unsigned i = 0; i < 4; ++i) sc_failures[i] = UINT64_MAX;
  seed_npc(1, (uint64_t)peer_round_robin);
  seed_npc(3, (uint64_t)peer_round_robin);
  __asm__ volatile("fence rw, rw" ::: "memory");
  uint64_t begin = cycles();
  ring_round_robin();
  __asm__ volatile("li t0, 1\ncsrw 0x800, t0" ::: "t0", "memory");
  *elapsed = cycles() - begin;
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  return ready_word == EXPECTED_READY && complete_word == EXPECTED_COMPLETE
         && source == 0 && sc_failures[0] == 0 && sc_failures[1] == 0
         && sc_failures[3] == 0;
}

static void report(unsigned sample, uint64_t elapsed, int ok)
{
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  bp_print_string("Atomic roundrobin sample/cycles/x100-per-op/ok/ready/"
                  "complete/source/sc0/sc1/sc3: ");
  bp_hprint_uint64(sample); bp_print_string(" ");
  bp_hprint_uint64(elapsed); bp_print_string(" ");
  bp_hprint_uint64(elapsed * 100 / SWITCHES_PER_SAMPLE); bp_print_string(" ");
  bp_hprint_uint64((uint64_t)ok); bp_print_string(" ");
  bp_hprint_uint64(ready_word); bp_print_string(" ");
  bp_hprint_uint64(complete_word); bp_print_string(" ");
  bp_hprint_uint64(source); bp_print_string(" ");
  bp_hprint_uint64(sc_failures[0]); bp_print_string(" ");
  bp_hprint_uint64(sc_failures[1]); bp_print_string(" ");
  bp_hprint_uint64(sc_failures[3]); bp_print_string("\n");
}

int main(void)
{
  uint64_t elapsed;
  int pass = 1;
  seed_thread(1, &peer1_stack[STACK_WORDS],
              (uint64_t)peer_round_robin);
  seed_thread(3, &peer3_stack[STACK_WORDS],
              (uint64_t)peer_round_robin);
  for (unsigned sample = 0; sample < SAMPLES; ++sample) {
    int ok = trial(&elapsed);
    pass &= ok;
    report(sample, elapsed, ok);
  }
  if (!pass) {
    bp_print_string("[BSG-FAIL] atomic roundrobin selector\n");
    bp_finish(1);
    return 1;
  }
  bp_print_string("[BSG-PASS] atomic roundrobin selector\n");
  bp_finish(0);
  return 0;
}
