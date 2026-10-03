#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define REPEATS 1
#define SWITCHES 256

static volatile uint64_t result[3] __attribute__((aligned(16)));
static volatile uint64_t source_target_word __attribute__((aligned(64))) = 1;
static volatile uint64_t peer_target_word __attribute__((aligned(64))) = 0;
static volatile uint64_t source_ready_bitmap __attribute__((aligned(64))) = 2;
static volatile uint64_t peer_ready_bitmap __attribute__((aligned(64))) = 1;

static inline uint64_t cycles(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

#define PEER(name, setup, switch_instruction)                             \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))       \
void name(void)                                                           \
{                                                                         \
  __asm__ volatile(                                                       \
    ".option push\n.option norvc\n.option arch,+zbb\n" setup             \
    "li t0, 4\n1:\n.rept 32\n" switch_instruction "\n.endr\n"            \
    "addi t0, t0, -1\nbnez t0, 1b\n"                                    \
    "la t1, result\ncsrr t2, 0x800\nsd t2, 0(t1)\n"                    \
    "sd s11, 8(t1)\nli t2, 128\nsd t2, 16(t1)\n"                     \
    "fence rw, rw\n" setup switch_instruction                            \
    "\n2: j 2b\n.option pop\n");                                         \
}

PEER(peer_register, "li t4, 0\n", "csrw 0x800, t4")
PEER(peer_loaded, "la t2, peer_target_word\n",
     "ld t4, 0(t2)\ncsrw 0x800, t4")
PEER(peer_bitmap, "la t2, peer_ready_bitmap\n",
     "ld t4, 0(t2)\nctz t4, t4\ncsrw 0x800, t4")

#define RING(name, setup, switch_instruction)                             \
static __attribute__((noinline, aligned(8))) void name(void)              \
{                                                                         \
  __asm__ volatile(                                                       \
    ".option push\n.option norvc\n.option arch,+zbb\n" setup             \
    "li t0, 4\n1:\n.rept 32\n" switch_instruction "\n.endr\n"            \
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"                      \
    : : : "t0", "t1", "t2", "memory");                                  \
}

RING(resident_register_ring, "li t1, 1\n", "csrw 0x800, t1")
RING(nonresident_register_ring, "li t1, 2\n", "csrw 0x800, t1")
RING(resident_loaded_ring, "la t2, source_target_word\n",
     "ld t1, 0(t2)\ncsrw 0x800, t1")
RING(nonresident_loaded_ring, "la t2, source_target_word\n",
     "ld t1, 0(t2)\ncsrw 0x800, t1")
RING(resident_bitmap_ring, "la t2, source_ready_bitmap\n",
     "ld t1, 0(t2)\nctz t1, t1\ncsrw 0x800, t1")
RING(nonresident_bitmap_ring, "la t2, source_ready_bitmap\n",
     "ld t1, 0(t2)\nctz t1, t1\ncsrw 0x800, t1")

static uint64_t trial(unsigned target, unsigned policy)
{
  void (*ring)(void) = policy == 0
    ? (target == 1 ? resident_register_ring : nonresident_register_ring)
    : policy == 1
      ? (target == 1 ? resident_loaded_ring : nonresident_loaded_ring)
      : (target == 1 ? resident_bitmap_ring : nonresident_bitmap_ring);
  void (*peer)(void) = policy == 0 ? peer_register
    : policy == 1 ? peer_loaded : peer_bitmap;

  source_target_word = target;
  source_ready_bitmap = UINT64_C(1) << target;
  result[0] = result[1] = result[2] = 0;
  uint64_t peer_gp;
  __asm__ volatile("mv %0, gp" : "=r"(peer_gp));
  seed_reg(target, 3, peer_gp);
  seed_reg(target, 27, UINT64_C(0x2468ace0));
  seed_npc(target, (uint64_t)peer);
  uint64_t begin = cycles();
  ring();
  uint64_t elapsed = cycles() - begin;
  __asm__ volatile("csrw 0x800, %0" : : "r"((uint64_t)target) : "memory");
  if (result[0] != target || result[1] != UINT64_C(0x2468ace0)
      || result[2] != 128) {
    bp_print_string("[BSG-FAIL] simulator ready-selection state\n");
    bp_finish(1);
  }
  return elapsed;
}

static void report(const char *name, uint64_t samples[REPEATS])
{
  for (unsigned i = 1; i < REPEATS; ++i) {
    uint64_t value = samples[i];
    unsigned j = i;
    while (j && samples[j - 1] > value) {
      samples[j] = samples[j - 1];
      --j;
    }
    samples[j] = value;
  }
  bp_print_string(name);
  bp_print_string(" median aggregate cycles: ");
  bp_hprint_uint64(samples[REPEATS / 2]);
  bp_print_string(" cycles/switch x100: ");
  bp_hprint_uint64(samples[REPEATS / 2] * 100 / SWITCHES);
  bp_print_string("\n");
}

int main(void)
{
  static const char *names[6] = {
    "register_resident", "register_nonresident",
    "loaded_target_resident", "loaded_target_nonresident",
    "ready_bitmap_resident", "ready_bitmap_nonresident"
  };
  uint64_t samples[6][REPEATS];
  __asm__ volatile("mv s11, %0" : : "r"(UINT64_C(0x13579bdf)) : "s11");
  for (unsigned mode = 0; mode < 6; ++mode) {
    unsigned target = (mode & 1) ? 2 : 1;
    unsigned policy = mode >> 1;
    for (unsigned i = 0; i < REPEATS; ++i) {
      (void)trial(target, policy);
      samples[mode][i] = trial(target, policy);
    }
    report(names[mode], samples[mode]);
  }
  bp_print_string("[BSG-PASS] simulator ready-selection benchmark\n");
  bp_finish(0);
  return 0;
}
