/*
 * Register-form context switches must use the newest source-register value,
 * not a stale bank value. Cover short ALU gaps, late results, same-context
 * writes, and computed returns on resident and SRAM-backed round trips.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Use two resident banks and four logical contexts"
#endif

static volatile uint64_t observed, bad_return;
static uint64_t peer_stack[256] __attribute__((aligned(16)));
static volatile uint64_t lines[128] __attribute__((aligned(64)));
/* Never touched before the tested loads: exercise actual miss completion too. */
static volatile uint64_t cold_lines[32] __attribute__((aligned(64))) = {
  [0] = 1, [8] = 2
};

/* a3 establishes the old RF value well before the producer under test.
 * a0 is the target, a1 a load address, and a2 the multiply/divide identity. */
typedef void (*switch_fn)(uint64_t, volatile uint64_t *, uint64_t, uint64_t);
#define SWITCH(name, producer, gap) \
static void __attribute__((naked, noinline)) name( \
    uint64_t a __attribute__((unused)), volatile uint64_t *p __attribute__((unused)), \
    uint64_t b __attribute__((unused)), uint64_t old __attribute__((unused))) \
{ __asm__ volatile ( \
    ".option push\n.option norvc\n" \
    "mv t0, a3\n.rept 8\nnop\n.endr\n" \
    producer "\n.rept " #gap "\nnop\n.endr\n" \
    "csrw 0x800, t0\nret\n.option pop\n" ::: "memory"); }

SWITCH(alu0, "mv t0, a0", 0)
SWITCH(alu1, "mv t0, a0", 1)
SWITCH(alu2, "mv t0, a0", 2)
SWITCH(alu3, "mv t0, a0", 3)
SWITCH(alu4, "mv t0, a0", 4)
SWITCH(alu5, "mv t0, a0", 5)
SWITCH(load0, "ld t0, 0(a1)", 0)
SWITCH(mul0, "mul t0, a0, a2", 0)
SWITCH(div0, "divu t0, a0, a2", 0)
SWITCH(csr0, "csrr t0, mscratch", 0)

static void __attribute__((naked, noinline, noreturn)) peer_immediate(void)
{
  __asm__ volatile (
    "csrr t1, 0x800\nla t2, observed\nsd t1, 0(t2)\n"
    "csrwi 0x800, 0\n1: j 1b\n" ::: "memory");
}

static void __attribute__((naked, noinline, noreturn)) peer_register(void)
{
  __asm__ volatile (
    ".option push\n.option norvc\n"
    "csrr t1, 0x800\nla t2, observed\nsd t1, 0(t2)\n"
    "mv t0, t1\n.rept 8\nnop\n.endr\n"
    "li t0, 0\ncsrw 0x800, t0\n"
    /* A failed computed return is recoverable, but must fail the test. */
    "li t1, 1\nla t2, bad_return\nsd t1, 0(t2)\n"
    "csrwi 0x800, 0\n1: j 1b\n.option pop\n" ::: "memory");
}

static void seed(unsigned peer, uint64_t entry)
{
  observed = bad_return = 0;
  seed_thread(peer, &peer_stack[256], entry);
}

int main(void)
{
  const switch_fn cases[] = {alu0, alu1, alu2, alu3, alu4, alu5,
                            load0, mul0, div0, csr0};
  unsigned stage = 0;
  for (unsigned peer = 1; peer <= 2; ++peer) {
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); ++i) {
      stage = peer * 100 + i;
      seed(peer, (uint64_t)peer_immediate);
      lines[i * 8] = peer;
      __asm__ volatile ("csrw mscratch, %0" :: "r"((uint64_t)peer) : "memory");
      cases[i](peer, &lines[i * 8], 1, 0);
      if (observed != peer) goto fail;

      /* Stale nonzero target must not turn a write of current ID 0 into a switch. */
      stage = peer * 100 + 20 + i;
      seed(peer, (uint64_t)peer_immediate);
      lines[i * 8] = 0;
      __asm__ volatile ("csrw mscratch, zero" ::: "memory");
      cases[i](0, &lines[i * 8], 1, peer);
      if (observed) goto fail;
    }
    stage = peer * 100 + 40;
    seed(peer, (uint64_t)peer_register);
    if (peer == 1) __asm__ volatile ("csrwi 0x800, 1" ::: "memory");
    else __asm__ volatile ("csrwi 0x800, 2" ::: "memory");
    if (observed != peer || bad_return) goto fail;

    stage = peer * 100 + 41;
    seed(peer, (uint64_t)peer_immediate);
    load0(peer, &cold_lines[(peer - 1) * 8], 1, 0);
    if (observed != peer) goto fail;
    stage = peer * 100 + 42;
    seed(peer, (uint64_t)peer_immediate);
    load0(0, &cold_lines[16 + (peer - 1) * 8], 1, peer);
    if (observed) goto fail;
  }
  bp_print_string("[BSG-PASS] register targets and computed returns\n");
  bp_finish(0);
  return 0;
fail:
  bp_print_string("[BSG-FAIL] register target stage ");
  bp_hprint_uint64(stage);
  bp_print_string("\n");
  bp_finish(1);
  return 1;
}
