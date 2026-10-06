/* Exercise the synthesizable accepted-miss recorder through its custom CSRs.
 * The test proves both I- and D-side histories capture their intended cold
 * lines, remain readable after disarming, and expose sane counts/status.
 */
#include <stdint.h>
#include "bp_utils.h"

#define TRACE_CONTROL 0x805
#define TRACE_SELECT  0x806
#define TRACE_DATA    0x807

struct cache_line { uint64_t word[8]; };
static const volatile struct cache_line cold_data
  __attribute__((aligned(4096), used)) =
  {{UINT64_C(0x9472a8b1c3d5e6f0), 1, 2, 3, 4, 5, 6, 7}};

static uint64_t __attribute__((noinline, aligned(4096), used))
cold_code(const volatile uint64_t *p)
{
  return *p ^ UINT64_C(0x0123456789abcdef);
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

static inline uint64_t trace_record(unsigned dcache, unsigned index)
{
  const uint64_t selector = ((uint64_t)dcache << 8) | index;
  uint64_t value;
  __asm__ volatile(
    "csrw 0x806, %1\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "csrr %0, 0x807\n"
    : "=r"(value) : "r"(selector) : "memory");
  return value;
}

static void __attribute__((noreturn)) fail(const char *reason)
{
  bp_print_string("[BSG-FAIL] accepted cache-miss trace: ");
  bp_print_string(reason);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

int main(void)
{
  // Bit 0 arms and bit 1 clears both histories.
  trace_control(3);
  const uint64_t observed = cold_code(&cold_data.word[0]);
  if (observed != (cold_data.word[0] ^ UINT64_C(0x0123456789abcdef)))
    fail("cold operation data");
  trace_control(0);

  // Leave enough retirement distance for the disarm write to take effect.
  __asm__ volatile("nop\nnop\nnop" : : : "memory");
  const uint64_t status = trace_status();
  const unsigned icount = status & 0x1ff;
  const unsigned dcount = (status >> 9) & 0x1ff;
  if ((status >> 20) & 1) fail("still armed");
  if ((status >> 18) & 3) fail("overflow");
  if (icount == 0 || dcount == 0) fail("empty history");

  const uint64_t code_line = (((uintptr_t)cold_code) >> 6) & 0x0fffffff;
  const uint64_t data_line = (((uintptr_t)&cold_data.word[0]) >> 6) & 0x0fffffff;
  uint64_t code_record = 0, data_record = 0;
  unsigned saw_code = 0, saw_data = 0;

  for (unsigned i = 0; i < icount; ++i) {
    const uint64_t record = trace_record(0, i);
    if ((record & 0x0fffffff) == code_line) {
      saw_code = 1;
      code_record = record;
    }
  }
  for (unsigned i = 0; i < dcount; ++i) {
    const uint64_t record = trace_record(1, i);
    if ((record & 0x0fffffff) == data_line) {
      saw_data = 1;
      data_record = record;
    }
  }
  if (!saw_code) fail("cold instruction line absent");
  if (!saw_data) fail("cold data line absent");

  bp_print_string("MISS-TRACE i-count=");
  bp_hprint_uint64(icount);
  bp_print_string(" d-count=");
  bp_hprint_uint64(dcount);
  bp_print_string(" i-cycle=");
  bp_hprint_uint64(code_record >> 32);
  bp_print_string(" d-cycle=");
  bp_hprint_uint64(data_record >> 32);
  bp_print_string("\n");

  bp_print_string("[BSG-PASS] accepted cache-miss trace\n");
  bp_finish(0);
  return 0;
}
