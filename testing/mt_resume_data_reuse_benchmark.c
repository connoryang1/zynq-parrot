/* Checked data reuse across a four-logical-context/two-resident-slot ring.
 * Ordinary lookup demands only: no address table, prefetch or cache policy.
 * Complete ring timing is a bare-metal simulator diagnostic, not Linux/FPGA.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "../linux-tests/resume_workload.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "This control requires two physical slots and four logical contexts"
#endif
#if defined(BP_RESUME_ZLIB) && BP_RESUME_ZLIB
#error "This bounded control uses plain lookup only"
#endif
#ifndef BP_RESUME_DATA_COMPACT
#define BP_RESUME_DATA_COMPACT 0
#endif
#if BP_RESUME_DATA_COMPACT != 0 && BP_RESUME_DATA_COMPACT != 1
#error "BP_RESUME_DATA_COMPACT must be0 or1"
#endif

enum { actors = 4, warm_rounds = 8, timed_rounds = 8,
       total_rounds = warm_rounds + timed_rounds, stack_words = 512 };
/* Initialized data survives CRT BSS clear after an offline NBF word patch. */
volatile uint64_t resume_data_config __attribute__((used, aligned(8))) = UINT64_MAX;
static struct resume_workload work[actors];
static uint64_t stacks[actors - 1][stack_words];
struct request_phase { uint64_t begin, end; };
static volatile struct request_phase phases[actors][total_rounds];
static volatile uint64_t sums[actors], completed[actors];
static uint64_t warm_begin, timed_begin, timed_end;

#define CYCLE_AT(label, output) \
  __asm__ volatile(".global " #label "\n" #label ":\ncsrr %0, 0xcc0" \
                   : "=r"(output) : : "memory")

static uint64_t seed_for(unsigned actor)
{
  return UINT64_C(0x95cba137) + actor * UINT64_C(0x9e3779b9);
}

static void __attribute__((noreturn, noinline)) fail(char *why)
{
  bp_print_string("[BSG-FAIL] data reuse: ");
  bp_print_string(why); bp_print_string("\n"); bp_finish(1);
  for (;;) ;
}

static void __attribute__((noinline, noclone)) request(unsigned actor, unsigned epoch)
{
  uint64_t begin, end, current;
  __asm__ volatile("csrr %0, 0x800" : "=r"(current));
  if (current != actor) fail("logical actor mismatch");
  CYCLE_AT(resume_data_request_begin, begin);
  uint64_t value = resume_workload_run(&work[actor]);
  CYCLE_AT(resume_data_request_end, end);
  phases[actor][epoch].begin = begin;
  phases[actor][epoch].end = end;
  sums[actor] += value;
  completed[actor] = epoch + 1;
}

static void __attribute__((noinline, noreturn, used)) peer(uint64_t actor)
{
  if (actor < 1 || actor > 3) fail("peer argument");
  for (unsigned epoch = 0; epoch < total_rounds; ++epoch) {
    request((unsigned)actor, epoch);
    if (actor == 1) __asm__ volatile("fence rw, rw\ncsrwi 0x800, 2" : : : "memory");
    else if (actor == 2) __asm__ volatile("fence rw, rw\ncsrwi 0x800, 3" : : : "memory");
    else __asm__ volatile("fence rw, rw\ncsrwi 0x800, 0" : : : "memory");
  }
  fail("peer resumed beyond final ring");
}

static void lap(unsigned epoch)
{
  request(0, epoch);
  __asm__ volatile("fence rw, rw\ncsrwi 0x800, 1" : : : "memory");
}

static void field(char *name, uint64_t value)
{
  bp_print_string(name); bp_hprint_uint64(value);
}

int main(void)
{
  uint64_t kib = resume_data_config;
  if (kib != 1 && kib != 32) fail("config must be1 or32KiB");
  for (unsigned a = 0; a < actors; ++a)
    if (resume_workload_init(&work[a], "lookup", (unsigned)kib, seed_for(a)))
      fail("private corpus allocation");
  for (unsigned a = 1; a < actors; ++a) {
    seed_reg(a, 10, a);
    seed_thread(a, &stacks[a - 1][stack_words], (uint64_t)peer);
  }
  CYCLE_AT(resume_data_warm_begin, warm_begin);
  for (unsigned epoch = 0; epoch < warm_rounds; ++epoch) lap(epoch);
  CYCLE_AT(resume_data_timed_begin, timed_begin);
  for (unsigned epoch = warm_rounds; epoch < total_rounds; ++epoch) lap(epoch);
  CYCLE_AT(resume_data_timed_end, timed_end);

  /* Checks recompute all16 expected request values from the independent
   * generator, never from a second actual accumulator or corpus reread.
   */
  for (unsigned a = 0; a < actors; ++a) {
    if (work[a].kind != resume_lookup || work[a].bytes != kib * 1024
        || work[a].count != kib * 64 || work[a].records != kib * 32
        || work[a].seed != seed_for(a) || work[a].runs != total_rounds
        || completed[a] != total_rounds
        || !resume_workload_check_total(&work[a], sums[a]))
      fail("independent16-epoch checksum/metadata");
    for (unsigned epoch = 0; epoch < total_rounds; ++epoch) {
      uint64_t begin = phases[a][epoch].begin, end = phases[a][epoch].end;
      if (begin >= end) fail("nonmonotonic request phase");
      if (epoch >= warm_rounds && (begin < timed_begin || end > timed_end))
        fail("request outside complete timed ring");
      if (a && phases[a - 1][epoch].end >= begin)
        fail("actor ring order");
      if (!a && epoch && phases[3][epoch - 1].end >= begin)
        fail("epoch ring order");
    }
  }

#if BP_RESUME_DATA_COMPACT
  /* Retired CSR labels retain all request boundaries in the selected FST.
   * Keep checks/stores above; avoid64 post-check UART diagnostic rows.
   */
  bp_print_string("DATA_REUSE_PROTOCOL compact-v1\n");
#endif
  bp_print_string("DATA_REUSE_CONFIG lookup actors=4 resident=2 warm=8 timed=8 kib=");
  bp_hprint_uint64(kib); bp_print_string("\n");
  for (unsigned a = 0; a < actors; ++a) {
    bp_print_string("DATA_REUSE_REGION actor="); bp_cprint('0' + a);
    field(" base=", (uintptr_t)work[a].data); field(" bytes=", work[a].bytes);
    field(" runs=", work[a].runs); field(" sum=", sums[a]); bp_print_string("\n");
    if (a) {
      bp_print_string("DATA_REUSE_STACK actor="); bp_cprint('0' + a);
      field(" base=", (uintptr_t)stacks[a - 1]);
      field(" bytes=", sizeof(stacks[0])); bp_print_string("\n");
    }
  }
#if !BP_RESUME_DATA_COMPACT
  for (unsigned epoch = 0; epoch < total_rounds; ++epoch)
    for (unsigned a = 0; a < actors; ++a) {
      bp_print_string("DATA_REUSE_EPOCH actor="); bp_cprint('0' + a);
      bp_print_string(" epoch=0x"); bp_hprint(epoch >> 4); bp_hprint(epoch & 15);
      field(" begin=", phases[a][epoch].begin);
      field(" end=", phases[a][epoch].end); bp_print_string("\n");
    }
#endif
  bp_print_string("DATA_REUSE_PHASES"); field(" warm_begin=", warm_begin);
  field(" timed_begin=", timed_begin); field(" timed_end=", timed_end);
  field(" cycles=", timed_end - timed_begin); bp_print_string("\n");
  bp_print_string("[BSG-PASS] checked nonresident data reuse ring lookup\n");
  bp_finish(0);
  for (;;) ;
}
