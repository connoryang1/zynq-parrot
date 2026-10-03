/* Bare-metal replication of the Linux atomic fence comparison. */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Use two resident banks and four logical contexts"
#endif

#define TURNS 128
#define SAMPLES 16
#define STACK_WORDS 256

static uint64_t peer_stack[STACK_WORDS];
static volatile uint64_t ready_word __attribute__((aligned(64))) = 4;
static volatile uint64_t observed_context __attribute__((aligned(64)));
static volatile uint64_t peer_complete __attribute__((aligned(64)));

static inline uint64_t cycles(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

#define PEER(name, ordering)                                                 \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))          \
void name(void)                                                              \
{                                                                            \
  __asm__ volatile(                                                          \
    ".option push\n.option norvc\n"                                         \
    "la t2, ready_word\nli t0, 128\n1:\nli t3, 4\n"                     \
    "amoswap.d.aqrl t4, t3, (t2)\n" ordering                               \
    ".option arch, +zbb\nctz t4, t4\ncsrw 0x800, t4\n"                   \
    "addi t0, t0, -1\nbnez t0, 1b\n"                                      \
    "la t1, observed_context\ncsrr t3, 0x800\nsd t3, 0(t1)\n"           \
    "la t1, peer_complete\nli t3, 1\nsd t3, 0(t1)\n"                       \
    "fence rw, rw\ncsrw 0x800, zero\n2: j 2b\n.option pop\n"               \
    ::: "memory");                                                           \
}

#define RING(name, ordering)                                                 \
static __attribute__((noinline, aligned(8))) void name(void)                 \
{                                                                            \
  __asm__ volatile(                                                          \
    ".option push\n.option norvc\n"                                         \
    "la t2, ready_word\nli t0, 128\n1:\nli t3, 1\n"                     \
    "amoswap.d.aqrl t4, t3, (t2)\n" ordering                               \
    ".option arch, +zbb\nctz t4, t4\ncsrw 0x800, t4\n"                   \
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"                       \
    ::: "t0", "t1", "t2", "t3", "t4", "memory");                       \
}

PEER(peer_fence, "fence rw, rw\n")
PEER(peer_aqrl, "")
RING(ring_fence, "fence rw, rw\n")
RING(ring_aqrl, "")

static int trial(void (*ring)(void), void (*peer)(void), uint64_t *elapsed)
{
  ready_word = 4;
  observed_context = UINT64_MAX;
  peer_complete = 0;
  seed_npc(2, (uint64_t)peer);
  __asm__ volatile("fence rw, rw" ::: "memory");
  uint64_t begin = cycles();
  ring();
  __asm__ volatile("li t0, 2\ncsrw 0x800, t0" ::: "t0", "memory");
  *elapsed = cycles() - begin;
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  return observed_context == 2 && peer_complete == 1 && ready_word == 4 &&
         source == 0;
}

static void report(unsigned sample, const char *mode, uint64_t elapsed, int ok)
{
  uint64_t source;
  __asm__ volatile("csrr %0, 0x800" : "=r"(source) :: "memory");
  bp_print_string("Atomic fence sample/mode/cycles/x100-per-op/ok/observed/complete/word/source: ");
  bp_hprint_uint64(sample);
  bp_print_string(" ");
  bp_print_string((char *)mode);
  bp_print_string(" ");
  bp_hprint_uint64(elapsed);
  bp_print_string(" ");
  bp_hprint_uint64(elapsed * 100 / (2 * TURNS + 2));
  bp_print_string(" ");
  bp_hprint_uint64((uint64_t)ok);
  bp_print_string(" ");
  bp_hprint_uint64(observed_context);
  bp_print_string(" ");
  bp_hprint_uint64(peer_complete);
  bp_print_string(" ");
  bp_hprint_uint64(ready_word);
  bp_print_string(" ");
  bp_hprint_uint64(source);
  bp_print_string("\n");
}

int main(void)
{
  uint64_t elapsed;
  int pass = 1;
  seed_thread(2, &peer_stack[STACK_WORDS], (uint64_t)peer_fence);
  for (unsigned pair = 0; pair < SAMPLES; ++pair) {
    if (pair & 1) {
      int ok = trial(ring_aqrl, peer_aqrl, &elapsed);
      pass &= ok;
      report(pair, "aqrl", elapsed, ok);
      ok = trial(ring_fence, peer_fence, &elapsed);
      pass &= ok;
      report(pair, "fence", elapsed, ok);
    } else {
      int ok = trial(ring_fence, peer_fence, &elapsed);
      pass &= ok;
      report(pair, "fence", elapsed, ok);
      ok = trial(ring_aqrl, peer_aqrl, &elapsed);
      pass &= ok;
      report(pair, "aqrl", elapsed, ok);
    }
  }
  if (!pass) {
    bp_print_string("[BSG-FAIL] atomic fence cost\n");
    bp_finish(1);
    return 1;
  }
  bp_print_string("[BSG-PASS] atomic fence cost\n");
  bp_finish(0);
  return 0;
}
