/* Check that four detached target words survive four older side-buffer words.
 * The prefetch5 configuration has five slots. Physical/admitted/issued/
 * published counters must reach four before target loads, and the accepted
 * D-cache demand-miss recorder must then stay empty for those loads.
 */
#include <stdint.h>

#include "bp_prefetch.h"
#include "bp_utils.h"

struct line { uint64_t word[8]; };
#define LINE(value) {{(value), 1, 2, 3, 4, 5, 6, 7}}

static const volatile struct line stale[4]
  __attribute__((aligned(4096), used)) = {
    LINE(0x510), LINE(0x511), LINE(0x512), LINE(0x513)
  };
static const volatile struct line target[4]
  __attribute__((aligned(4096), used)) = {
    LINE(0x710), LINE(0x711), LINE(0x712), LINE(0x713)
  };
static const volatile struct line off[4]
  __attribute__((aligned(4096), used)) = {
    LINE(0x910), LINE(0x911), LINE(0x912), LINE(0x913)
  };

static void __attribute__((noreturn)) fail(const char *why)
{
  bp_print_string("[BSG-FAIL] preview side-buffer pressure: ");
  bp_print_string(why);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

static inline void trace_control(uint64_t value)
{
  __asm__ volatile("csrw 0x805, %0" : : "r"(value) : "memory");
}

static inline uint64_t trace_status(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x805" : "=r"(value) : : "memory");
  return value;
}

static uint64_t trace_record(unsigned index)
{
  uint64_t value;
  // In address-preview mode publication slots live in the I history;
  // removals and demand misses remain in the D history.
  const uint64_t selector = (index >= 248 ? 0 : 0x100) + index;
  __asm__ volatile(
    "csrw 0x806, %1\n"
    "nop\nnop\nnop\n"
    "csrr %0, 0x807\n"
    : "=r"(value) : "r"(selector) : "memory");
  return value;
}

static uint64_t trace_remove_meta(unsigned index)
{
  uint64_t value;
  const uint64_t selector = index; // I history mirrors D removal indices.
  __asm__ volatile(
    "csrw 0x806, %1\n"
    "nop\nnop\nnop\n"
    "csrr %0, 0x807\n"
    : "=r"(value) : "r"(selector) : "memory");
  return value;
}

static uint64_t wait_four_published(void)
{
  for (unsigned i = 0; i < 4096; ++i) {
    uint64_t status = trace_status();
    if (((status >> 45) & 0xff) == 4)
      return status;
  }
  fail("four responses never published");
}

static void require_four_stages(uint64_t status)
{
  if (((status >> 21) & 0xff) != 4 || ((status >> 29) & 0xff) != 4
      || ((status >> 37) & 0xff) != 4 || ((status >> 45) & 0xff) != 4)
    fail("physical/admitted/issued/published mismatch");
}

static void hint_four(const volatile struct line *lines)
{
  bp_prefetch_r(&lines[0].word[0]);
  bp_prefetch_r(&lines[1].word[0]);
  bp_prefetch_r(&lines[2].word[0]);
  bp_prefetch_r(&lines[3].word[0]);
}

static uint64_t load_four(const volatile struct line *lines, uint64_t values[4],
                          uint64_t load_pc[4])
{
  uint64_t status;
  __asm__ volatile(
    "la %5, 1f\n"
    "la %6, 2f\n"
    "la %7, 3f\n"
    "la %8, 4f\n"
    "1: ld %0, 0(%9)\n"
    "2: ld %1, 64(%9)\n"
    "3: ld %2, 128(%9)\n"
    "4: ld %3, 192(%9)\n"
    "nop\nnop\nnop\nnop\nnop\nnop\n"
    "csrr %4, 0x805\n"
    : "=&r"(values[0]), "=&r"(values[1]), "=&r"(values[2]),
      "=&r"(values[3]), "=&r"(status), "=&r"(load_pc[0]),
      "=&r"(load_pc[1]), "=&r"(load_pc[2]), "=&r"(load_pc[3])
    : "r"(lines) : "memory");
  return status;
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  bp_print_string("PREVIEW-SIDEBUF begin\n");
  trace_control(2); // Clear counters; leave demand recorder disarmed.
  hint_four(stale);
  require_four_stages(wait_four_published());
  bp_print_string("PREVIEW-SIDEBUF older batch published\n");

  // A complete older batch occupies four of the five slots. Do not load it.
  trace_control(6); // Clear and trace publications before demand recording.
  hint_four(target);
  require_four_stages(wait_four_published());

  uint64_t values[4];
  uint64_t target_pc[4];
  trace_control(5); // Arm demand misses without clearing publication records.
  uint64_t target_status = load_four(target, values, target_pc);
  trace_control(0);
  bp_print_string("PREVIEW-SIDEBUF target batch published\n");
  for (unsigned i = 0; i < 4; ++i)
    if (values[i] != 0x710 + i) fail("target data");
  if (((target_status >> 9) & 0x1ff) != 0)
    fail("published target word became a demand miss");
  if ((target_status >> 19) & 1) fail("target recorder overflow");
  if (((target_status >> 53) & 0xf) != 4 || ((target_status >> 57) & 1)
      || !((target_status >> 58) & 1))
    fail("publication trace count, mode, or overflow");
  for (unsigned i = 0; i < 4; ++i) {
    uint64_t record = trace_record(248 + i);
    if (((record >> 30) & 3) != 3
        || ((record & 0x3fffffff) << 4)
           != (uint64_t)(uintptr_t)&target[i].word[0])
      fail("publication address record");
  }
  unsigned removal_count = (unsigned)((target_status >> 59) & 0x1f);
  if (removal_count < 4 || removal_count > 16)
    fail("side-buffer removal count");
  uint64_t seen_pc[4] = {0, 0, 0, 0};
  for (unsigned i = 0; i < 4; ++i) {
    unsigned found = 0;
    for (unsigned j = 0; j < removal_count; ++j) {
      uint64_t record = trace_record(232 + j);
      if (((record >> 30) & 3) == 0
          && ((record & 0x3fffffff) << 4)
             == (uint64_t)(uintptr_t)&target[i].word[0]) {
        uint64_t meta = trace_remove_meta(232 + j);
        uint64_t pc = meta & ((UINT64_C(1) << 39) - 1);
        if (!((meta >> 40) & 1) || !pc)
          fail("target consume lacks a request PC");
        if (pc != (target_pc[i] & ((UINT64_C(1) << 39) - 1)))
          fail("target consume PC differs from its load instruction");
        for (unsigned prior = 0; prior < i; ++prior)
          if (pc == seen_pc[prior])
            fail("distinct target loads share a request PC");
        seen_pc[i] = pc;
        ++found;
      }
    }
    if (found != 1) fail("target consume address record");
  }

  // Separate cold lines demonstrate that the no-miss result was useful data,
  // rather than a recorder that never sees accepted D-cache demand misses.
  trace_control(3);
  uint64_t off_status = load_four(off, values, target_pc);
  trace_control(0);
  for (unsigned i = 0; i < 4; ++i)
    if (values[i] != 0x910 + i) fail("off data");
  if (((off_status >> 9) & 0x1ff) != 4)
    fail("cold off control did not miss four times");

  bp_print_string("[BSG-PASS] preview side-buffer pressure preserves four target words\n");
  bp_finish(0);
  return 0;
}
