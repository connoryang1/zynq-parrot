/*
 * Repeated register-form context targets must consume the producer's newest
 * value on every round trip.  The one-shot register-target test did not catch
 * a routed fixed-delay interlock regression, which stalled only after a
 * producer/switch dependency recurred across handoffs.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Use two resident banks and four logical contexts"
#endif

#define TURNS 128
#define STACK_WORDS 256

static uint64_t peer_stack[BP_NUM_CONTEXTS][STACK_WORDS];
static volatile uint64_t source_word __attribute__((aligned(64)));
static volatile uint64_t peer_word __attribute__((aligned(64)));
static volatile uint64_t observed __attribute__((aligned(64)));
static volatile uint64_t complete __attribute__((aligned(64)));

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

#define PEER(name, setup, sequence)                                      \
static void __attribute__((naked, noinline, noreturn, used, aligned(8))) \
name(void)                                                               \
{                                                                        \
  __asm__ volatile(                                                      \
    ".option push\n.option norvc\n" setup                              \
    "li t0, 128\n1:\n" sequence                                      \
    "addi t0, t0, -1\nbnez t0, 1b\n"                                  \
    "la t1, observed\ncsrr t3, 0x800\nsd t3, 0(t1)\n"               \
    "la t1, complete\nli t3, 1\nsd t3, 0(t1)\n"                       \
    "fence rw, rw\ncsrw 0x800, zero\n2: j 2b\n.option pop\n"           \
    ::: "memory");                                                      \
}

#define RING(name, setup, sequence)                                      \
static void __attribute__((noinline, aligned(8))) name(void)             \
{                                                                        \
  __asm__ volatile(                                                      \
    ".option push\n.option norvc\n" setup                              \
    "li t0, 128\n1:\n" sequence                                      \
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"                     \
    ::: "t0", "t1", "t2", "t3", "t4", "memory");                    \
}

PEER(peer_register, "li t4, 0\n", "csrw 0x800, t4\n")
PEER(peer_loaded, "la t2, peer_word\n",
     "ld t4, 0(t2)\ncsrw 0x800, t4\n")
PEER(peer_bitmap, "la t2, peer_word\n",
     ".option arch, +zbb\nld t4, 0(t2)\nctz t4, t4\ncsrw 0x800, t4\n")

RING(ring_register_1, "li t4, 1\n", "csrw 0x800, t4\n")
RING(ring_register_2, "li t4, 2\n", "csrw 0x800, t4\n")
RING(ring_loaded, "la t2, source_word\n",
     "ld t4, 0(t2)\ncsrw 0x800, t4\n")
RING(ring_bitmap, "la t2, source_word\n",
     ".option arch, +zbb\nld t4, 0(t2)\nctz t4, t4\ncsrw 0x800, t4\n")

typedef void (*ring_fn)(void);
typedef void (*peer_fn)(void);

static int trial(uint64_t target, ring_fn ring, peer_fn peer,
                 uint64_t source_value, uint64_t peer_value,
                 uint64_t *cycles)
{
  source_word = source_value;
  peer_word = peer_value;
  observed = UINT64_MAX;
  complete = 0;
  seed_thread(target, &peer_stack[target][STACK_WORDS], (uint64_t)peer);
  __asm__ volatile("fence rw, rw" ::: "memory");

  uint64_t begin = read_global_cycle();
  ring();
  /* Resume the peer's final loop tail; it records independent completion and
   * returns directly to context zero outside the measured round trips. */
  __asm__ volatile("csrw 0x800, %0" :: "r"(target) : "memory");
  *cycles = read_global_cycle() - begin;
  return observed == target && complete == 1;
}

static void report(const char *name, uint64_t target, uint64_t cycles)
{
  bp_print_string("Target bypass ");
  bp_print_string(name);
  bp_print_string(" context/cycles/cycles-per-op-x100: ");
  bp_hprint_uint64(target);
  bp_print_string(" ");
  bp_hprint_uint64(cycles);
  bp_print_string(" ");
  bp_hprint_uint64((cycles * 100) / (2 * TURNS + 2));
  bp_print_string("\n");
}

int main(void)
{
  uint64_t cycles;
  int pass = 1;

#define RUN(label, target, ring, peer, source_value, peer_value) do {      \
    int ok = trial(target, ring, peer, source_value, peer_value, &cycles); \
    report(label, target, cycles);                                         \
    pass &= ok;                                                            \
  } while (0)

  RUN("register", 1, ring_register_1, peer_register, 1, 0);
  RUN("register", 2, ring_register_2, peer_register, 2, 0);
  RUN("loaded", 1, ring_loaded, peer_loaded, 1, 0);
  RUN("loaded", 2, ring_loaded, peer_loaded, 2, 0);
  RUN("bitmap", 1, ring_bitmap, peer_bitmap, 2, 1);
  RUN("bitmap", 2, ring_bitmap, peer_bitmap, 4, 1);

  if (!pass) {
    bp_print_string("[BSG-FAIL] sustained register target bypass\n");
    bp_finish(1);
    return 1;
  }
  bp_print_string("[BSG-PASS] sustained register target bypass\n");
  bp_finish(0);
  return 0;
}
