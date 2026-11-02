/* Measure whether hot physical-preview traffic delays a cold target-context
 * instruction fetch at resident handoff.  Matched zero-, one-, and four-hint
 * bodies invalidate L1-I before issuing previews, so the peer's first
 * instruction must contend for the shared forward/L2 path.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Physical-preview I-cache contention requires two resident contexts"
#endif

#define SAMPLES 7

struct cache_line { uint64_t value, padding[7]; };
static volatile struct cache_line targets[4]
  __attribute__((aligned(256), used)) = {
    {1, {0}}, {2, {0}}, {3, {0}}, {4, {0}}
  };
static volatile uint64_t peer_entry_cycle __attribute__((aligned(64), used));

static __attribute__((naked, noinline, noreturn, aligned(64)))
void peer(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, 0xcc0\n"
    "la t1, peer_entry_cycle\n"
    "sd t0, 0(t1)\n"
    "csrwi 0x800, 0\n"
    "1: j 1b\n"
    ".option pop\n");
}

#define RUN_BEGIN \
  ".option push\n.option norvc\n" \
  "csrr a4, 0xcc0\n" \
  "fence.i\n"
#define RUN_END \
  "csrwi 0x800, 1\n" \
  "la t0, peer_entry_cycle\n" \
  "ld a0, 0(t0)\n" \
  "sub a0, a0, a4\n" \
  "ret\n.option pop\n"

static __attribute__((naked, noinline, aligned(64)))
uint64_t run_zero(const volatile void *a, const volatile void *b,
                  const volatile void *c, const volatile void *d)
{
  __asm__ volatile(RUN_BEGIN "nop\nnop\nnop\nnop\n" RUN_END);
}

static __attribute__((naked, noinline, aligned(64)))
uint64_t run_one(const volatile void *a, const volatile void *b,
                 const volatile void *c, const volatile void *d)
{
  __asm__ volatile(RUN_BEGIN
                   "csrw 0x9c0, a0\nnop\nnop\nnop\n"
                   RUN_END);
}

static __attribute__((naked, noinline, aligned(64)))
uint64_t run_four(const volatile void *a, const volatile void *b,
                  const volatile void *c, const volatile void *d)
{
  __asm__ volatile(RUN_BEGIN
                   "csrw 0x9c0, a0\ncsrw 0x9c0, a1\n"
                   "csrw 0x9c0, a2\ncsrw 0x9c0, a3\n"
                   RUN_END);
}

static void wait_preview_idle(void)
{
  uint64_t idle;

  do
    __asm__ volatile("csrr %0, 0x9c0" : "=r"(idle) : : "memory");
  while (!(idle & 1));
}

typedef uint64_t (*run_fn)(const volatile void *, const volatile void *,
                           const volatile void *, const volatile void *);

static uint64_t run_sample(run_fn fn)
{
  uint64_t hot = 0;

  for (unsigned i = 0; i < 4; ++i)
    hot += targets[i].value;
  if (hot != 10) {
    bp_print_string("[BSG-FAIL] physical preview contention hot data\n");
    bp_finish(1);
  }
  wait_preview_idle();
  seed_npc(1, (uint64_t)peer);
  peer_entry_cycle = 0;
  __asm__ volatile("fence rw, rw" : : : "memory");
  uint64_t cycles = fn(&targets[0], &targets[1], &targets[2], &targets[3]);
  wait_preview_idle();
  return cycles;
}

int main(void)
{
  run_fn modes[3] = {run_zero, run_one, run_four};
  uint64_t cycles[SAMPLES][3] = {{0}};

  for (unsigned mode = 0; mode < 3; ++mode)
    (void)run_sample(modes[mode]);
  for (unsigned sample = 0; sample < SAMPLES; ++sample) {
    for (unsigned position = 0; position < 3; ++position) {
      unsigned mode = (position + sample) % 3;
      cycles[sample][mode] = run_sample(modes[mode]);
    }
  }
  if (cycles[0][1] != cycles[0][2] || cycles[0][1] < cycles[0][0]) {
    bp_print_string("[BSG-FAIL] physical preview cold-I first sample\n");
    bp_finish(1);
  }
  for (unsigned sample = 1; sample < SAMPLES; ++sample)
    if (cycles[sample][1] != cycles[sample][2]
        || cycles[sample][1] != cycles[sample][0] + 1) {
      bp_print_string("[BSG-FAIL] physical preview cold-I steady samples\n");
      bp_finish(1);
    }
  bp_print_string("PHYSICAL-PREVIEW-ICACHE steady-preview-penalty=1-cycle\n");
  bp_print_string("[BSG-PASS] physical preview I-cache contention benchmark\n");
  bp_finish(0);
  return 0;
}
